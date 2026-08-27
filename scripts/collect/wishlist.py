"""
트랙 B — 위시리스트 보강 수집 (collection API, wishlist=1).

own=1로 고정 수집한 기존 user_item.csv에는 위시 항목이 298행뿐이다(2,954명
중 own=1 필터를 통과한 게 own 상태인 행뿐이라 당연한 결과) — "위시만 쌓이고
플레이 안 되는 게임" 질문(PLAN.md 핵심 질문 3)에 답하려면 개인 위시리스트
자체가 필요하다.

collect_collections()를 own 대신 wishlist=1로 호출하도록 파라미터만 바꿔
재사용한다(collection_collector.py 참고) — 새 파서를 만들지 않는다. own=1
수집 결과(item_info.csv/user_item.csv)와 안 섞이도록 출력 파일명을 다르게
지정한다.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from dotenv import load_dotenv

from scripts._common import run_stage
from src.collectors.collection_collector import collect_collections
from src.collectors.filters import filter_users, load_filter_from_config
from src.config import DATA_DIR

load_dotenv()

USER_INFO_PATH = DATA_DIR / "user_info.csv"

logger = logging.getLogger("wishlist")


def _load_valid_users() -> list[str]:
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
    run_stage(
        "wishlist", _load_valid_users, collect_collections, DATA_DIR,
        own=None, wishlist=1,
        item_filename="wishlist_item_info.csv",
        user_item_filename="user_wishlist.csv",
    )


if __name__ == "__main__":
    main()
