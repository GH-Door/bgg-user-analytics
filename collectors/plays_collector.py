"""
BGG plays API 수집 — user_play (신규, 기획서에 없던 테이블).

호출: GET /xmlapi2/plays?username={user_id}&page={n}

기획서의 최대 약점은 "클릭스트림이 없어 lastlogin 기반 Proxy 코호트로
근사한다"는 것이었다. plays API는 유저가 직접 기록한 개별 플레이의
날짜(playdate)를 제공하므로, 이 데이터를 확보하면 Proxy가 아닌
실제 월별 코호트 리텐션을 계산할 수 있다.

유저 1명당 페이지네이션이 필요해 수집 비용이 크다 — 전체 유저가 아니라
샘플 유저(대상 목록은 호출부에서 주입)로 제한한다. 샘플 크기/추출 방법은
README의 "수집 설계 결정 로그"에 근거와 함께 기록한다.
"""
from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from pathlib import Path

from .bgg_client import BGGClient

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


def _load_checkpoint(checkpoint_path: Path) -> set[str]:
    if not checkpoint_path.exists():
        return set()
    return set(checkpoint_path.read_text(encoding="utf-8").splitlines())


def collect_plays(
    client: BGGClient,
    user_ids: list[str],
    out_path: Path,
    checkpoint_path: Path,
    page_size: int = 100,
) -> None:
    """user_ids(샘플)를 순회하며 각 유저의 전체 플레이 로그를 페이지네이션으로
    수집한다. 완료한 user_id는 체크포인트에 기록해 재시작 시 건너뛴다."""
    done = _load_checkpoint(checkpoint_path)
    is_new = not out_path.exists()

    with out_path.open("a", newline="", encoding="utf-8") as f, \
         checkpoint_path.open("a", encoding="utf-8") as ckpt_f:

        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()

        for user_id in user_ids:
            if user_id in done:
                continue

            page = 1
            collected = 0
            while True:
                root = client.get("plays", {"username": user_id, "page": page})
                rows, total = _parse_page(root, user_id)
                if not rows:
                    break
                writer.writerows(rows)
                collected += len(rows)
                if collected >= total:
                    break
                page += 1

            f.flush()
            ckpt_f.write(user_id + "\n")
            ckpt_f.flush()
