"""
트랙 C — 신규 표집틀 구축 패스 (thing API의 ratingcomments).

user_list.csv(2024년 팀 프로젝트 유래)는 표집틀 시점이 2024-07에 고정돼
2025~2026 가입자가 표본에 전혀 없다(docs/sampling_design.md 참고). 이 문제를
100개 게임으로 검증(verify_frame.py, 600명)한 뒤, 이제 이 방식 자체를
본표본으로 승격한다 — user_list.csv는 이후 아예 참조하지 않는다.

기존(2,862명) 수집으로 이미 보유한 게임 카탈로그(item_stats.csv, BGG_DATA_DIR
무관하게 참고용으로 계속 씀 — §게임 카탈로그는 유저 명단과 달리 시간 편향이
없다, 프로젝트 대화 기록 참고) 중 복잡도(averageweight) 5분위 × 40개 = 200개를
무작위로 뽑아, 그 게임들을 평가한 유저명을 thing API의 ratingcomments로
모은다. 이렇게 얻은 frame_candidates.csv에서 main_frame.py가 스크리닝
표본(3,000명)을 뽑아 본수집으로 이어간다.

복잡도 5분위로 게임을 층화하는 이유: 무작위로 게임을 뽑으면 표집틀 자체가
다시 "인기/헤비 게임 평가자" 쪽으로 쏠릴 수 있다 — 게임 층화로 이 위험을
차단한다.
"""
from __future__ import annotations

import csv
import logging
import random

from dotenv import load_dotenv

from scripts._common import run_stage
from src.collectors.frame_collector import collect_rating_usernames
from src.config import DATA_DIR

load_dotenv()

SEED = 20260826
GAMES_PER_QUINTILE = 40
ITEM_STATS_PATH = DATA_DIR / "item_stats.csv"
OUT_PATH = DATA_DIR / "frame_candidates.csv"

logger = logging.getLogger("frame")


def _load_game_sample() -> list[str]:
    """전체 objectid를 averageweight 기준으로 5등분한 뒤 구간마다 20개씩
    무작위 추출한다. 이미 뽑은 적 있으면(재실행) 그대로 재사용하지 않는다 —
    frame_candidates.csv 자체가 체크포인트 역할(objectid 단위)을 하므로,
    게임 목록은 매번 같은 SEED로 재계산해도 결과가 동일하다(재현성)."""
    weights: dict[str, float] = {}
    with ITEM_STATS_PATH.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                w = float(row["averageweight"] or 0)
            except ValueError:
                continue
            if w > 0:
                weights[row["objectid"]] = w

    ranked = sorted(weights.items(), key=lambda kv: kv[1])
    n = len(ranked)
    quintile_size = n // 5

    random.seed(SEED)
    sample: list[str] = []
    for q in range(5):
        start = q * quintile_size
        end = n if q == 4 else start + quintile_size
        pool = [oid for oid, _ in ranked[start:end]]
        picked = random.sample(pool, min(GAMES_PER_QUINTILE, len(pool)))
        sample.extend(picked)

    logger.info(f"복잡도 5분위 × {GAMES_PER_QUINTILE}개 — 총 {len(sample)}개 게임 표본(전체 {n}개 중)")
    return sample


def main() -> None:
    run_stage(
        "frame", _load_game_sample, collect_rating_usernames, OUT_PATH,
        unit="개",
    )


if __name__ == "__main__":
    main()
