"""
BGG user API 수집 — user_info 테이블.

호출: GET /xmlapi2/user?name={user_id}
가장 단순한 엔드포인트. 기존 팀 프로젝트의 user_info 스키마를 그대로 따른다.
"""
from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from pathlib import Path

from .bgg_client import BGGClient

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


def collect_users(client: BGGClient, user_ids: list[str], out_path: Path) -> None:
    """user_ids를 순회하며 out_path에 append. 체크포인트는 collection_collector와
    동일 패턴(완료 user_id를 별도 파일에 기록)을 쓰면 되지만, user API는 응답이
    가볍고 실패 시 재실행 비용이 낮아 초안에서는 생략 — 필요해지면 추가."""
    is_new = not out_path.exists()
    with out_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        for user_id in user_ids:
            root = client.get("user", {"name": user_id})
            writer.writerow(parse_user(root, user_id))
            f.flush()
