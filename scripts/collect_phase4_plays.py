"""
트랙 B — 4차 플레이 로그 수집 패스 (plays API, 샘플 유저 한정, 마지막 단계).

표본 설계(2026-08-24, docs/sampling_design.md 갱신 예정):
  - 목적이 1차 스크리닝(전체 모집단 비율 추정, ±2%p)과 다르다 — 여기는
    "코호트별(가입연도) 리텐션 곡선 비교"가 목적이라 코호트 단위로 안정적이면
    충분하므로 마진을 ±15%p로 완화한다.
    n0 = Z²·0.25/e² = 1.96²·0.25/0.15² ≈ 43 → 코호트당 목표 43명.
  - 1차 스크리닝 때는 SRS를 썼다(실제 코호트 분포를 몰랐어서 인위적 하한이
    무의미했음). 지금은 data/user_info.csv에 실제 가입연도 분포가 있으므로
    층화추출로 전환 — 인구가 43명 미만인 코호트는 전수(그 인구 그대로 사용).
  - 코호트 안에서는 순수 무작위(numplays/소유 게임 수로 헤비 유저를 우대하지
    않음) — 우대하면 "그 코호트의 전형적 리텐션"이 아니라 "가장 활발한 유저의
    리텐션"을 재는 선택 편향이 생긴다(검토 후 기각).
  - 헤비 유저 세그먼트 분석은 이 표본과 무관 — 이미 수집된 data/user_item.csv
    (2,946명 전체)로 한다. 이 표본은 오직 코호트 리텐션 전용.
"""
from __future__ import annotations

import csv
import logging
import os
import random
import time
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

from scripts._common import get_or_set_started_at, setup_logging
from src.collectors.bgg_client import BGGClient
from src.collectors.plays_collector import collect_plays

load_dotenv()

DATA_DIR = Path("data")

USER_INFO_PATH = DATA_DIR / "user_info.csv"
SAMPLE_PATH = DATA_DIR / "plays_sample_users.csv"
OUT_PATH = DATA_DIR / "user_play.csv"
CHECKPOINT_PATH = DATA_DIR / "plays_checkpoint.txt"
FAILED_PATH = DATA_DIR / "plays_failed.txt"
STARTED_AT_PATH = DATA_DIR / ".plays_started_at"

SEED = 20260824
MARGIN = 0.15  # 코호트별 허용 오차 ±15%p, 95% CI
Z = 1.96

logger = logging.getLogger("plays")


def _cohort_cap() -> int:
    n0 = (Z ** 2 * 0.25) / (MARGIN ** 2)
    return round(n0)


def _select_sample() -> list[str]:
    """표본을 한 번 뽑으면 파일에 영속화해서 재실행해도 같은 표본을 쓴다
    (screen 단계의 sample_users.csv와 동일 원칙 — 재현성)."""
    if SAMPLE_PATH.exists():
        with SAMPLE_PATH.open(newline="", encoding="utf-8") as f:
            return [row["user_id"] for row in csv.DictReader(f)]

    by_cohort: dict[str, list[str]] = defaultdict(list)
    with USER_INFO_PATH.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            year = row["yearregistered"]
            if year:
                by_cohort[year].append(row["user_id"])

    cap = _cohort_cap()
    random.seed(SEED)
    sample: list[tuple[str, str]] = []  # (user_id, yearregistered) — 감사 로그용
    for year, users in by_cohort.items():
        chosen = users if len(users) <= cap else random.sample(users, cap)
        sample.extend((u, year) for u in chosen)

    logger.info(
        f"코호트당 목표 n={cap}(±{MARGIN*100:.0f}%p, 95% CI) · "
        f"{len(by_cohort)}개 코호트 · 총 표본 {len(sample)}명"
    )

    with SAMPLE_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["user_id", "yearregistered"])
        writer.writerows(sample)

    return [u for u, _ in sample]


def main() -> None:
    started_at = get_or_set_started_at(STARTED_AT_PATH)
    setup_logging(started_at, "plays")

    user_ids = _select_sample()
    logger.info(f"=== plays 수집 시작 · 대상 {len(user_ids)}명 ===")

    client = BGGClient(token=os.environ["BGG_API_TOKEN"])
    t0 = time.monotonic()
    collect_plays(
        client, user_ids,
        OUT_PATH, CHECKPOINT_PATH, FAILED_PATH,
        start_time=t0,
    )
    logger.info(
        f"=== plays 수집 완료 · 이번 실행 소요 {(time.monotonic()-t0)/60:.1f}분 · "
        f"최초 시작부터 누적 {(time.time()-started_at)/60:.1f}분 ==="
    )


if __name__ == "__main__":
    main()
