"""
트랙 B — 2차 본수집 패스 (collection API).

1차 스크리닝(scripts/collect/user.py)에서 유효했던 계정(data/user_info.csv,
2,954명)을 대상으로 collection API(own=1)를 호출해 item_info/user_item을 채운다.

collect_collections()가 순회·체크포인트·실패 처리·진행 로깅까지 전부 내부에서
처리하므로 여기서는 1회 호출로 끝낸다.

국가/가입연도 필터: 이 저장소를 clone해서 다른 모집단을 수집하고 싶은 경우
저장소 루트의 config.yaml(collect.countries/min_year/max_year)을 채우면 된다.
user API 자체엔 국가별 검색 쿼리가 없어서, 스크리닝(user API)으로
country/yearregistered를 이미 받아둔 user_info.csv를 여기서 후처리
필터링한다 — 전부 비워두면(기본값) 이 프로젝트가 실제로 쓴 것과 동일하게
무필터(전원 통과)로 동작한다.

own=1 유지 이유, 예외 처리 원칙(영구 오류=제외 후 계속/네트워크 오류=재시도)은
CLAUDE.md §1·PLAN.md §4-2 참고. 로깅 설정은 scripts/_common.py 공용 유틸 사용.
"""
from __future__ import annotations

import csv
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from scripts._common import get_or_set_started_at, setup_logging
from src.collectors.bgg_client import BGGClient
from src.collectors.collection_collector import collect_collections
from src.collectors.filters import filter_users, load_filter_from_config

load_dotenv()

DATA_DIR = Path("data")

USER_INFO_PATH = DATA_DIR / "user_info.csv"
CHECKPOINT_PATH = DATA_DIR / "collection_checkpoint.txt"
FAILED_PATH = DATA_DIR / "collection_failed.txt"
STARTED_AT_PATH = DATA_DIR / ".collection_started_at"

OWN = 1

logger = logging.getLogger("collection")


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
    started_at = get_or_set_started_at(STARTED_AT_PATH)
    setup_logging(started_at, "collection")

    user_ids = _load_valid_users()
    logger.info(f"=== 본수집 시작 · 대상 {len(user_ids)}명 (own={OWN}) ===")

    client = BGGClient(token=os.environ["BGG_API_TOKEN"])
    t0 = time.monotonic()
    collect_collections(
        client, user_ids, DATA_DIR,
        CHECKPOINT_PATH, FAILED_PATH,
        own=OWN, start_time=t0,
    )
    logger.info(
        f"=== 본수집 완료 · 이번 실행 소요 {(time.monotonic()-t0)/60:.1f}분 · "
        f"최초 시작부터 누적 {(time.time()-started_at)/60:.1f}분 ==="
    )


if __name__ == "__main__":
    main()
