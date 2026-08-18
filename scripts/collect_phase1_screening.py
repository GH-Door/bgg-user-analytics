"""
트랙 B — 1차 스크리닝 패스.

후보 풀(data/user_list.csv, 194,643명)에서 무작위 3,000명을 뽑아 가벼운 user API만
호출한다. 표본 크기·SRS를 쓰는 이유는 docs/sampling_design.md 참고.

재시작해도 이미 수집된 user_id는 건너뛴다(user_collector.collect_users 자체엔
체크포인트가 없어 출력 CSV를 직접 확인해 걸러낸다).

user_list.csv는 2024년 시점 후보 목록이라 그새 탈퇴/개명된 계정이 섞여 있다.
BGGRequestError(4xx)는 "이 후보는 무효"로 보고 excluded_users.csv에 사유와 함께
기록한 뒤 다음 후보로 넘어간다 — collect_users가 반환하는 실패 목록을 그대로 씀.
BGGAuthError(401)는 토큰 문제라 즉시 중단한다(재시도해도 의미 없음).

로그는 logging 모듈로 logs/screen_YYYYMMDD.log에 남긴다. 날짜는 "지금"이 아니라
이 작업이 최초로 시작된 날짜(영속화된 시작 시각 기준) — 재시작하거나 자정을
넘겨도 로그가 파일 하나로 이어진다.
"""
from __future__ import annotations

import csv
import logging
import os
import random
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from src.collectors.bgg_client import BGGClient
from src.collectors.user_collector import collect_users

load_dotenv()

DATA_DIR = Path("data")
LOGS_DIR = Path("logs")
SEED = 20260818
SCREENING_N = 3000

USER_LST_PATH = DATA_DIR / "user_list.csv"
OUT_PATH = DATA_DIR / "user_info.csv"
SAMPLE_LOG_PATH = DATA_DIR / "sample_users.csv"
EXCLUDED_LOG_PATH = DATA_DIR / "excluded_users.csv"
STARTED_AT_PATH = DATA_DIR / ".user_info_started_at"

logger = logging.getLogger("screen")


def _get_or_set_started_at() -> float:
    """최초 실행 시각(epoch)을 파일에 영속화한다. 스크립트를 재시작해도
    이 값은 그대로라 '최초 시작부터 누적 경과 시간'과 로그 파일명이 안 바뀐다."""
    if STARTED_AT_PATH.exists():
        return float(STARTED_AT_PATH.read_text().strip())
    now = time.time()
    STARTED_AT_PATH.write_text(str(now))
    return now


def _setup_logging(started_at: float) -> None:
    date_str = datetime.fromtimestamp(started_at).strftime("%Y%m%d")
    log_path = LOGS_DIR / f"screen_{date_str}.log"
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)


def _load_sample() -> list[str]:
    if SAMPLE_LOG_PATH.exists():
        # 재현성: 이미 뽑아둔 표본이 있으면 그대로 재사용 (재실행해도 다른 사람이 안 뽑히게)
        with SAMPLE_LOG_PATH.open(newline="", encoding="utf-8") as f:
            return [row["user_id"] for row in csv.DictReader(f)]

    with USER_LST_PATH.open(newline="", encoding="utf-8") as f:
        all_users = [row["user_id"] for row in csv.DictReader(f)]

    random.seed(SEED)
    sample = random.sample(all_users, SCREENING_N)

    with SAMPLE_LOG_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["user_id"])
        writer.writerows([[u] for u in sample])

    return sample


def _user_ids_in(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as f:
        return {row["user_id"] for row in csv.DictReader(f)}


def _log_excluded(user_id: str, reason: str) -> None:
    is_new = not EXCLUDED_LOG_PATH.exists()
    with EXCLUDED_LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["user_id", "reason"])
        writer.writerow([user_id, reason])


def main() -> None:
    started_at = _get_or_set_started_at()
    _setup_logging(started_at)

    sample = _load_sample()
    done = _user_ids_in(OUT_PATH)
    excluded = _user_ids_in(EXCLUDED_LOG_PATH)
    todo = [u for u in sample if u not in done and u not in excluded]

    logger.info(
        f"=== 스크리닝 시작 · 표본 {len(sample)}명 중 완료 {len(done)}명, "
        f"제외 {len(excluded)}명, 남음 {len(todo)}명 ==="
    )
    if not todo:
        logger.info("이미 전부 완료됨")
        return

    client = BGGClient(token=os.environ["BGG_API_TOKEN"])
    t0 = time.monotonic()
    for i, user_id in enumerate(todo, 1):
        failed = collect_users(client, [user_id], OUT_PATH)
        for uid, reason in failed:
            _log_excluded(uid, reason)

        if i % 100 == 0 or i == len(todo):
            elapsed_run = time.monotonic() - t0
            elapsed_total = time.time() - started_at  # 최초 시작부터 누적(재시작 downtime 포함)
            rate = elapsed_run / i  # 초/명, 이번 실행 기준
            remaining = rate * (len(todo) - i)
            logger.info(
                f"{i}/{len(todo)} 처리 · "
                f"이번 실행 경과 {elapsed_run/60:.1f}분 · "
                f"최초 시작부터 누적 {elapsed_total/60:.1f}분 · "
                f"예상 잔여 {remaining/60:.1f}분"
            )

    logger.info(
        f"=== 전체 완료 · 이번 실행 소요 {(time.monotonic()-t0)/60:.1f}분 · "
        f"최초 시작부터 누적 {(time.time()-started_at)/60:.1f}분 ==="
    )


if __name__ == "__main__":
    main()
