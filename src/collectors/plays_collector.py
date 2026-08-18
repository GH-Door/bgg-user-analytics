"""
BGG plays API 수집 — user_play (신규, 기획서에 없던 테이블).

호출: GET /xmlapi2/plays?username={user_id}&page={n}

기획서의 최대 약점은 "클릭스트림이 없어 lastlogin 기반 Proxy 코호트로
근사한다"는 것이었다. plays API는 유저가 직접 기록한 개별 플레이의
날짜(playdate)를 제공하므로, 이 데이터를 확보하면 Proxy가 아닌
실제 월별 코호트 리텐션을 계산할 수 있다.

유저 1명당 페이지네이션이 필요해 수집 비용이 크다 — 전체 유저가 아니라
샘플 유저(대상 목록은 호출부에서 주입)로 제한한다. 샘플 크기/추출 방법은
PLAN.md의 "수집 설계 결정 로그"에 근거와 함께 기록한다.
"""
from __future__ import annotations

import csv
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from .bgg_client import BGGClient, BGGRequestError
from .checkpoint import append_checkpoint, load_checkpoint, report_progress

logger = logging.getLogger(__name__)

FIELDS = [
    "play_id", "user_id", "objectid", "play_date",
    "quantity", "length", "incomplete", "location",
]


def _parse_page(root: ET.Element, user_id: str) -> tuple[list[dict], int]:
    rows = []
    for play in root.findall("play"):
        item_el = play.find("item")
        rows.append({
            "play_id": play.get("id", ""),
            "user_id": user_id,
            "objectid": item_el.get("objectid", "") if item_el is not None else "",
            "play_date": play.get("date", ""),
            "quantity": play.get("quantity", ""),
            "length": play.get("length", ""),
            "incomplete": play.get("incomplete", ""),
            "location": play.get("location", ""),
        })
    total = int(root.get("total", "0"))
    return rows, total


def collect_plays(
    client: BGGClient,
    user_ids: list[str],
    out_path: Path,
    checkpoint_path: Path,
    failed_path: Path,
    page_size: int = 100,
) -> None:
    """user_ids(샘플)를 순회하며 각 유저의 전체 플레이 로그를 페이지네이션으로
    수집한다. 완료한 user_id는 체크포인트에 기록해 재시작 시 건너뛴다.

    페이지네이션 도중 영구적 오류가 나면 그 유저는 통째로 건너뛰고 failed_path에
    기록한다 — 이미 받은 페이지까지는 out_path에 남지만(버리지 않음), 그 유저는
    "완료"로 체크포인트되지 않으므로 나중에 필요하면 처음부터 재수집 대상으로
    식별할 수 있다(ponytail: 페이지 단위 재개는 지금 범위 밖, 필요해지면 추가)."""
    done = load_checkpoint(checkpoint_path)
    failed = load_checkpoint(failed_path)
    is_new = not out_path.exists()
    total = len(user_ids)

    with out_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()

        for i, user_id in enumerate(user_ids, start=1):
            if user_id in done or user_id in failed:
                continue

            page = 1
            collected = 0
            try:
                while True:
                    root = client.get("plays", {"username": user_id, "page": page})
                    rows, page_total = _parse_page(root, user_id)
                    if not rows:
                        break
                    writer.writerows(rows)
                    collected += len(rows)
                    if collected >= page_total:
                        break
                    page += 1
            except BGGRequestError as e:
                logger.warning(f"유저 {user_id} plays 수집 제외 (page={page}): {e}")
                f.flush()
                append_checkpoint(failed_path, user_id)
                report_progress("plays", i, total)
                continue

            f.flush()
            append_checkpoint(checkpoint_path, user_id)
            report_progress("plays", i, total)
