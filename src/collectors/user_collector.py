"""
BGG user API 수집 — user_info 테이블.

호출: GET /xmlapi2/user?name={user_id}
가장 단순한 엔드포인트. 기존 팀 프로젝트의 user_info 스키마를 그대로 따른다.
"""
from __future__ import annotations

import csv
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from .bgg_client import BGGClient, BGGRequestError, BGGTransientError
from .checkpoint import append_checkpoint, load_checkpoint, report_progress

logger = logging.getLogger(__name__)

FIELDS = [
    "user_id", "yearregistered", "lastlogin", "country",
    "stateorprovince", "traderating",
]


def _attr(el: ET.Element | None, key: str = "value") -> str:
    return el.get(key, "") if el is not None else ""


def parse_user(root: ET.Element, user_id: str) -> dict:
    return {
        "user_id": user_id,
        "yearregistered": _attr(root.find("yearregistered")),
        "lastlogin": _attr(root.find("lastlogin")),
        "country": _attr(root.find("country")),
        "stateorprovince": _attr(root.find("stateorprovince")),
        "traderating": _attr(root.find("traderating")),
    }


def collect_users(
    client: BGGClient,
    user_ids: list[str],
    out_path: Path,
    checkpoint_path: Path,
    failed_path: Path,
    start_time: float | None = None,
) -> None:
    """user_ids를 순회하며 out_path에 append하고, 완료/실패를 체크포인트에
    기록한다 — collection_collector/thing_collector/plays_collector와 동일한
    시그니처·재시작 계약(checkpoint_path/failed_path/start_time)을 쓴다.

    영구적 오류(BGGRequestError)는 user_ids 전체를 중단시키지 않고 그 유저만
    건너뛰어 failed_path에 기록한다 — 실패 사유는 로그에 남는다(다른 세
    수집기와 동일)."""
    done = load_checkpoint(checkpoint_path)
    failed = load_checkpoint(failed_path)
    total = len(user_ids)
    is_new = not out_path.exists() or out_path.stat().st_size == 0

    with out_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()

        for i, user_id in enumerate(user_ids, start=1):
            if user_id in done or user_id in failed:
                continue

            try:
                root = client.get("user", {"name": user_id})
            except BGGTransientError as e:
                # 일시적 오류가 재시도 예산을 다 씀 — 이 유저는 무효가 아니라 "아직
                # 못 받음"이므로 failed_path에 기록하지 않는다(다음 실행에서 재시도).
                logger.warning(f"유저 {user_id} 수집 보류(일시적 오류, 다음 실행에 재시도): {e}")
                continue
            except BGGRequestError as e:
                logger.warning(f"유저 {user_id} 수집 제외: {e}")
                append_checkpoint(failed_path, user_id)
                report_progress("user", i, total, start_time=start_time)
                continue

            writer.writerow(parse_user(root, user_id))
            f.flush()
            append_checkpoint(checkpoint_path, user_id)
            report_progress("user", i, total, start_time=start_time)
