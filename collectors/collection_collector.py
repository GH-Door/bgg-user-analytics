"""
BGG collection API 수집 — user_item(+ item_info 기초 피처).

호출: GET /xmlapi2/collection?username={user_id}&own={0|1}&stats=1

기존 코드(크롤링 코드(주석확인해주세욥).ipynb) 대비 수정한 점:
  1. own을 인자로 노출 — 기본은 기획서와 동일하게 own=1 유지하지만, 한 줄로
     own=0(전체 컬렉션)으로 전환 가능하게 열어둔다. own=1을 쓰는 한 퍼널의
     "가입→수집가" 전환율은 측정 불가하다는 한계를 PLAN.md에 명시했다.
  2. 저장 방식 — 루프 안에서 전체 DataFrame을 concat/drop_duplicates/to_csv 하던
     것을 제거. 유저 단위로 모은 행을 CSV에 append만 한다. (O(n²) → O(n))
  3. 체크포인트 — 완료한 user_id를 별도 파일에 append. 재시작 시 이미 완료된
     유저를 건너뛴다. 기존 코드처럼 iloc 인덱스를 손으로 찾지 않아도 된다.
  4. 중복 키를 objectid로 판단 (기존 코드는 name으로 판단해 동명이품이 유실됨).
"""
from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from pathlib import Path

from .bgg_client import BGGClient

ITEM_FIELDS = [
    "objectid", "name", "yearpublished", "minplayers", "maxplayers",
    "minplaytime", "maxplaytime", "playingtime", "numowned",
    "average", "bayesaverage", "stddev", "rank",
]

USER_ITEM_FIELDS = ["user_id", "objectid", "user_rating", "numplays", "comment"]


def _stat_attr(item: ET.Element, tag: str, key: str = "value") -> str:
    stats = item.find("stats")
    if stats is None:
        return ""
    el = stats.find(tag) if tag not in ("maxplayers", "minplayers", "maxplaytime",
                                          "minplaytime", "playingtime", "numowned") else None
    if el is not None:
        return el.get(key, "")
    # maxplayers 등은 <stats> 태그 자체의 속성이다.
    return stats.get(tag, "")


def parse_collection_item(item: ET.Element) -> tuple[dict, dict]:
    """<item> 엘리먼트 하나를 (item_info 행, user_item 행)으로 분해한다."""
    stats = item.find("stats")
    rank_el = stats.find("rating/ranks/rank[@friendlyname]") if stats is not None else None
    # TODO: rank는 subtype별로 여러 개 나올 수 있음(Strategy/Family 등).
    # 초안에서는 첫 rank만 취하고, thing_collector 쪽에서 subtype별 long 포맷으로
    # 별도 수집한다(item_rank 테이블). 여기서는 "대표 순위" 정도로만 둔다.

    item_row = {
        "objectid": item.get("objectid", ""),
        "name": (item.findtext("name") or ""),
        "yearpublished": (item.findtext("yearpublished") or ""),
        "minplayers": _stat_attr(item, "minplayers"),
        "maxplayers": _stat_attr(item, "maxplayers"),
        "minplaytime": _stat_attr(item, "minplaytime"),
        "maxplaytime": _stat_attr(item, "maxplaytime"),
        "playingtime": _stat_attr(item, "playingtime"),
        "numowned": _stat_attr(item, "numowned"),
        "average": (stats.find("rating/average").get("value") if stats is not None and stats.find("rating/average") is not None else ""),
        "bayesaverage": (stats.find("rating/bayesaverage").get("value") if stats is not None and stats.find("rating/bayesaverage") is not None else ""),
        "stddev": (stats.find("rating/stddev").get("value") if stats is not None and stats.find("rating/stddev") is not None else ""),
        "rank": (rank_el.get("value") if rank_el is not None else ""),
    }

    rating_el = stats.find("rating") if stats is not None else None
    user_item_row = {
        "user_id": "",  # 호출부에서 채움
        "objectid": item.get("objectid", ""),
        "user_rating": (rating_el.get("value") if rating_el is not None else ""),
        "numplays": (item.findtext("numplays") or "0"),
        "comment": (item.findtext("comment") or ""),
    }
    return item_row, user_item_row


def _load_checkpoint(checkpoint_path: Path) -> set[str]:
    if not checkpoint_path.exists():
        return set()
    return set(checkpoint_path.read_text(encoding="utf-8").splitlines())


def collect_collections(
    client: BGGClient,
    user_ids: list[str],
    item_out_path: Path,
    user_item_out_path: Path,
    checkpoint_path: Path,
    own: int = 1,
) -> None:
    done = _load_checkpoint(checkpoint_path)
    seen_objectids: set[str] = set()  # 이번 실행에서 이미 쓴 아이템은 재작성하지 않음(경량 중복 방지)

    item_is_new = not item_out_path.exists()
    user_item_is_new = not user_item_out_path.exists()

    with item_out_path.open("a", newline="", encoding="utf-8") as item_f, \
         user_item_out_path.open("a", newline="", encoding="utf-8") as ui_f, \
         checkpoint_path.open("a", encoding="utf-8") as ckpt_f:

        item_writer = csv.DictWriter(item_f, fieldnames=ITEM_FIELDS)
        ui_writer = csv.DictWriter(ui_f, fieldnames=USER_ITEM_FIELDS)
        if item_is_new:
            item_writer.writeheader()
        if user_item_is_new:
            ui_writer.writeheader()

        for user_id in user_ids:
            if user_id in done:
                continue

            root = client.get("collection", {
                "username": user_id, "own": own, "stats": 1,
            })

            for item in root.findall("item"):
                if item.get("subtype") != "boardgame":
                    continue
                item_row, user_item_row = parse_collection_item(item)
                user_item_row["user_id"] = user_id

                if item_row["objectid"] not in seen_objectids:
                    item_writer.writerow(item_row)
                    seen_objectids.add(item_row["objectid"])
                ui_writer.writerow(user_item_row)

            item_f.flush()
            ui_f.flush()
            ckpt_f.write(user_id + "\n")
            ckpt_f.flush()
