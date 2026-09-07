"""
트랙 B/C — 3차 아이템 상세 수집 패스 (thing API, 배치 20개).

2차 본수집(scripts/collect/collection.py)에서 모인 게임 objectid
(data/item_info.csv, 이미 유니크)를 대상으로 thing API를 배치 호출해
item_details/item_stats/item_link/item_rank를 채운다.

DATA_DIR(item_stats.csv)에 이미 복잡도 값이 있는 objectid는 건너뛴다 —
트랙 C(BGG_DATA_DIR=data/after)에서 재실행할 때, 새 표집틀 수집으로
발견된 게임 중 기존 카탈로그(data/before에서 복사해온 item_stats.csv)에
이미 있는 것까지 또 조회하면 낭비다. 기존 카탈로그 전체를 처음부터
다시 만드는 트랙 B 첫 실행에서는 item_stats.csv가 비어있으므로(또는
아직 없으므로) 이 필터가 자연히 전체를 대상으로 동작한다.

collect_things()가 배치 순회·체크포인트·부분 누락 감지·재시작 중복 방지까지
전부 내부에서 처리하므로 여기서는 1회 호출로 끝낸다(collection.py와 동일 패턴).

BATCH_SIZE=20은 실측 확인됨(21개부터 즉시 400). thing API가 삭제/병합된
id를 HTTP 200 + 조용히 빠뜨리는 응답 특성 때문에, collect_things() 내부에서
요청 대비 부족하게 온 id는 failed_path로 분리한다 — 자세한 내용은
src/collectors/thing_collector.py 상단 docstring과 TROUBLESHOOTING.md 참고.
로깅 설정은 scripts/_common.py 공용 유틸 사용.
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
from src.collectors.thing_collector import collect_things
from src.config import DATA_DIR

load_dotenv()

ITEM_INFO_PATH = DATA_DIR / "item_info.csv"
ITEM_STATS_PATH = DATA_DIR / "item_stats.csv"
CHECKPOINT_PATH = DATA_DIR / "thing_checkpoint.txt"
FAILED_PATH = DATA_DIR / "thing_failed.txt"
STARTED_AT_PATH = DATA_DIR / ".thing_started_at"

logger = logging.getLogger("thing")


def _load_object_ids() -> list[str]:
    with ITEM_INFO_PATH.open(newline="", encoding="utf-8") as f:
        wanted = [row["objectid"] for row in csv.DictReader(f)]

    known: set[str] = set()
    if ITEM_STATS_PATH.exists():
        with ITEM_STATS_PATH.open(newline="", encoding="utf-8") as f:
            known = {row["objectid"] for row in csv.DictReader(f)}

    new_ids = [oid for oid in wanted if oid not in known]
    logger.info(
        f"게임 {len(wanted):,}개 중 기존 카탈로그에 이미 있는 {len(wanted) - len(new_ids):,}개 제외, "
        f"신규 {len(new_ids):,}개만 조회"
    )
    return new_ids


def main() -> None:
    started_at = get_or_set_started_at(STARTED_AT_PATH)
    setup_logging(started_at, "thing")

    object_ids = _load_object_ids()
    logger.info(f"=== thing 수집 시작 · 대상 {len(object_ids)}개 게임 (배치 20개) ===")

    client = BGGClient(token=os.environ["BGG_API_TOKEN"])
    t0 = time.monotonic()
    collect_things(
        client, object_ids, DATA_DIR,
        CHECKPOINT_PATH, FAILED_PATH,
        start_time=t0,
    )
    logger.info(
        f"=== thing 수집 완료 · 이번 실행 소요 {(time.monotonic()-t0)/60:.1f}분 · "
        f"최초 시작부터 누적 {(time.time()-started_at)/60:.1f}분 ==="
    )


if __name__ == "__main__":
    main()
