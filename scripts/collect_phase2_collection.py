"""
트랙 B — 2차 본수집 패스 (collection API).

1차 스크리닝(collect_phase1_screening.py)에서 유효했던 계정(data/user_info.csv,
2,954명)을 대상으로 collection API(own=1)를 호출해 item_info/user_item을 채운다.

phase1과 달리 유저별 루프를 이 스크립트가 직접 돌지 않는다 — collection_collector
.collect_collections()가 순회·체크포인트·실패 처리·진행 로깅까지 전부 내부에서
처리하므로 여기서는 1회 호출로 끝낸다.

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

load_dotenv()

DATA_DIR = Path("data")

USER_INFO_PATH = DATA_DIR / "user_info.csv"
ITEM_OUT_PATH = DATA_DIR / "item_info.csv"
USER_ITEM_OUT_PATH = DATA_DIR / "user_item.csv"
CHECKPOINT_PATH = DATA_DIR / "collection_checkpoint.txt"
FAILED_PATH = DATA_DIR / "collection_failed.txt"
STARTED_AT_PATH = DATA_DIR / ".collection_started_at"

OWN = 1

logger = logging.getLogger("collection")


def _load_valid_users() -> list[str]:
    with USER_INFO_PATH.open(newline="", encoding="utf-8") as f:
        return [row["user_id"] for row in csv.DictReader(f)]


def main() -> None:
    started_at = get_or_set_started_at(STARTED_AT_PATH)
    setup_logging(started_at, "collection")

    user_ids = _load_valid_users()
    logger.info(f"=== 본수집 시작 · 대상 {len(user_ids)}명 (own={OWN}) ===")

    client = BGGClient(token=os.environ["BGG_API_TOKEN"])
    t0 = time.monotonic()
    collect_collections(
        client, user_ids,
        ITEM_OUT_PATH, USER_ITEM_OUT_PATH,
        CHECKPOINT_PATH, FAILED_PATH,
        own=OWN, start_time=t0,
    )
    logger.info(
        f"=== 본수집 완료 · 이번 실행 소요 {(time.monotonic()-t0)/60:.1f}분 · "
        f"최초 시작부터 누적 {(time.time()-started_at)/60:.1f}분 ==="
    )


if __name__ == "__main__":
    main()
