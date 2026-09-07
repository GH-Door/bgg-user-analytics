"""
트랙 C — 신규 표집틀 기반 본수집 (frame_candidates.csv → user + collection API).

verify_frame.py가 600명으로 검증만 하고 끝냈던 것과 달리, 여기서는 그 신규
표집틀(frame_candidates.csv, thing ratingcomments 기반, user_list.csv/2024년
명단과 무관)에서 스크리닝 버퍼 3,000명을 뽑아 이번 프로젝트의 **본표본**으로
삼는다(docs/sampling_design.md의 목표 유효 표본 2,400명 산정 근거를 그대로
따름). user_list.csv는 이제 아예 참조하지 않는다.

collect_users()/collect_collections()를 그대로 재사용한다(own=1, 새 파서
없음) — verify_frame.py와 동일한 두 단계(user → collection) 패턴이지만
출력 파일명에 _v2/verify 접미사를 안 붙인다. BGG_DATA_DIR=data/after로
실행하면 이 파일들이 곧 그 폴더의 주 산출물이 되기 때문이다.
"""
from __future__ import annotations

import csv
import logging
import random

from dotenv import load_dotenv

from scripts._common import run_stage
from src.collectors.collection_collector import collect_collections
from src.collectors.filters import filter_users, load_filter_from_config
from src.collectors.user_collector import collect_users
from src.config import DATA_DIR

load_dotenv()

SEED = 20260902
SCREENING_N = 3000

CANDIDATES_PATH = DATA_DIR / "frame_candidates.csv"
SAMPLE_LOG_PATH = DATA_DIR / "main_sample_users.csv"
USER_INFO_PATH = DATA_DIR / "user_info.csv"

logger = logging.getLogger("main_frame")


def _load_user_sample() -> list[str]:
    """이미 뽑아둔 표본이 있으면 재사용(재현성) — user.py의 _load_sample()과
    동일한 패턴. frame_candidates.csv는 (user_id, source_objectid) long
    포맷이라 유저 하나가 여러 행에 나올 수 있어 먼저 distinct한다."""
    if SAMPLE_LOG_PATH.exists():
        with SAMPLE_LOG_PATH.open(newline="", encoding="utf-8") as f:
            return [row["user_id"] for row in csv.DictReader(f)]

    with CANDIDATES_PATH.open(newline="", encoding="utf-8") as f:
        all_users = sorted({row["user_id"] for row in csv.DictReader(f)})

    random.seed(SEED)
    sample = random.sample(all_users, min(SCREENING_N, len(all_users)))

    with SAMPLE_LOG_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["user_id"])
        writer.writerows([[u] for u in sample])

    logger.info(f"신규 표집틀 {len(all_users)}명 중 {len(sample)}명 무작위 추출 → {SAMPLE_LOG_PATH}")
    return sample


def _load_valid_users() -> list[str]:
    """1단계(user API)에서 유효했던 계정만 2단계(collection API) 대상으로 삼는다.
    국가/가입연도 필터: config.yaml(collect.countries/min_year/max_year)을 채우면
    적용된다 — 전부 비워두면(기본값) 이 프로젝트가 실제로 쓴 것과 동일하게
    무필터(전원 통과)로 동작한다(src/collectors/filters.py 참고)."""
    with USER_INFO_PATH.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    countries, min_year, max_year = load_filter_from_config()
    user_ids = filter_users(rows, countries, min_year, max_year)
    if countries or min_year or max_year:
        logger.info(
            f"필터 적용(countries={countries}, min_year={min_year}, max_year={max_year}) "
            f"— {len(rows)}명 중 {len(user_ids)}명 통과"
        )
    return user_ids


def main() -> None:
    sample = _load_user_sample()
    run_stage("user", lambda: sample, collect_users, USER_INFO_PATH)
    run_stage(
        "collection", _load_valid_users, collect_collections, DATA_DIR,
        own=1,
        item_filename="item_info.csv",
        user_item_filename="user_item.csv",
    )


if __name__ == "__main__":
    main()
