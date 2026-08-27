"""
트랙 B — 1차 스크리닝 패스 (user API).

후보 풀(data/user_list.csv, 194,643명)에서 무작위 3,000명을 뽑아 가벼운 user API만
호출한다. 표본 크기·SRS를 쓰는 이유는 docs/sampling_design.md 참고.

collect_users()가 순회·체크포인트·실패 처리·진행 로깅까지 전부 내부에서
처리한다(collection/thing/plays와 동일 계약) — 여기서는 1회 호출로 끝낸다.

user_list.csv는 2024년 시점 후보 목록이라 그새 탈퇴/개명된 계정이 섞여 있다.
BGGRequestError(4xx)는 "이 후보는 무효"로 보고 failed_path에 기록한 뒤 다음
후보로 넘어간다. BGGAuthError(401)는 토큰 문제라 즉시 중단한다(재시도해도 의미 없음).

로깅 설정(로그 파일 위치·포맷, 시작 시각 영속화)은 scripts/_common.py 공용
유틸을 쓴다 — collection.py/thing.py/plays.py와 동일 패턴.
"""
from __future__ import annotations

import csv
import logging
import os
import random
import time
from pathlib import Path

from dotenv import load_dotenv

from scripts._common import get_or_set_started_at, setup_logging
from src.collectors.bgg_client import BGGClient
from src.collectors.user_collector import collect_users

load_dotenv()

DATA_DIR = Path("data")
SEED = 20260818
SCREENING_N = 3000

USER_LST_PATH = DATA_DIR / "user_list.csv"
OUT_PATH = DATA_DIR / "user_info.csv"
SAMPLE_LOG_PATH = DATA_DIR / "sample_users.csv"
CHECKPOINT_PATH = DATA_DIR / "user_checkpoint.txt"
FAILED_PATH = DATA_DIR / "user_failed.txt"
STARTED_AT_PATH = DATA_DIR / ".user_info_started_at"

logger = logging.getLogger("user")


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


def main() -> None:
    started_at = get_or_set_started_at(STARTED_AT_PATH)
    setup_logging(started_at, "user")

    sample = _load_sample()
    logger.info(f"=== 스크리닝 시작 · 표본 {len(sample)}명 ===")

    client = BGGClient(token=os.environ["BGG_API_TOKEN"])
    t0 = time.monotonic()
    collect_users(
        client, sample, OUT_PATH,
        CHECKPOINT_PATH, FAILED_PATH,
        start_time=t0,
    )
    logger.info(
        f"=== 전체 완료 · 이번 실행 소요 {(time.monotonic()-t0)/60:.1f}분 · "
        f"최초 시작부터 누적 {(time.time()-started_at)/60:.1f}분 ==="
    )


if __name__ == "__main__":
    main()
