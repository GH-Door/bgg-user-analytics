"""
BGG thing API 수집 — item_details + item_stats(추가 피처) + item_category /
item_mechanic / item_rank(브리지 테이블, long 포맷).

호출: GET /xmlapi2/thing?id=1,2,3,...&stats=1
  - thing API는 id를 콤마로 여러 개 넘길 수 있다. collection_collector처럼
    유저 단위로 1건씩 부르지 않고 배치로 묶어 요청 수를 크게 줄인다.
  - TODO: 배치 크기(BATCH_SIZE)의 실제 상한은 토큰 발급 후 공식 문서에서 확인.
    초안에서는 보수적으로 20으로 시작.

기존 데이터의 category/mechanic/family/designer/publisher가
"[('1050', 'Ancient'), ...]" 같은 파이썬 튜플 문자열로 저장되어 있던 문제를
여기서 원천 차단한다 — 애초에 (objectid, link_type, ref_id, value) long 포맷
브리지 테이블로 뽑아낸다. 나중에 SQL에서 파싱할 필요가 없어진다.

기획서의 numwishing 외에 같은 응답에 이미 들어있는 stats 전체
(wishing/wanting/trading/owned/numcomments/numweights/averageweight)도
함께 뽑는다 — 추가 API 호출 비용 없이 얻는 피처.
"""
from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from pathlib import Path

from .bgg_client import BGGClient

BATCH_SIZE = 20

DETAIL_FIELDS = [
    "objectid", "name", "yearpublished", "minage", "description",
    "avg_weights",
]

STATS_FIELDS = [
    "objectid", "usersrated", "average", "bayesaverage", "stddev",
    "owned", "trading", "wanting", "wishing", "numcomments",
    "numweights", "averageweight",
]

# link type=category/mechanic/family/boardgamedesigner/boardgamepublisher 등을
# 전부 이 한 테이블에 담는다. link_type으로 나중에 SQL에서 걸러 쓰면 된다.
LINK_FIELDS = ["objectid", "link_type", "ref_id", "value"]

# subtype별 순위 — Strategy Game Rank / Family Game Rank 등을 행으로 분리.
RANK_FIELDS = ["objectid", "rank_type", "friendlyname", "value", "bayesaverage"]


def _batched(seq: list[str], size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def parse_thing(item: ET.Element) -> tuple[dict, dict, list[dict], list[dict]]:
    objectid = item.get("id", "")

    detail_row = {
        "objectid": objectid,
        "name": (item.find("name").get("value") if item.find("name") is not None else ""),
        "yearpublished": (item.findtext("yearpublished") or ""),
        "minage": (item.findtext("minage") or ""),
        "description": (item.findtext("description") or ""),
        "avg_weights": "",  # averageweight는 statistics 쪽에 있음 → stats_row에서 채움
    }

    ratings = item.find("statistics/ratings")
    def rv(tag: str) -> str:
        el = ratings.find(tag) if ratings is not None else None
        return el.get("value", "") if el is not None else ""

    stats_row = {
        "objectid": objectid,
        "usersrated": rv("usersrated"),
        "average": rv("average"),
        "bayesaverage": rv("bayesaverage"),
        "stddev": rv("stddev"),
        "owned": rv("owned"),
        "trading": rv("trading"),
        "wanting": rv("wanting"),
        "wishing": rv("wishing"),
        "numcomments": rv("numcomments"),
        "numweights": rv("numweights"),
        "averageweight": rv("averageweight"),
    }
    detail_row["avg_weights"] = stats_row["averageweight"]

    link_rows = [
        {
            "objectid": objectid,
            "link_type": link.get("type", ""),
            "ref_id": link.get("id", ""),
            "value": link.get("value", ""),
        }
        for link in item.findall("link")
    ]

    rank_rows = []
    ranks_el = ratings.find("ranks") if ratings is not None else None
    if ranks_el is not None:
        for rank in ranks_el.findall("rank"):
            rank_rows.append({
                "objectid": objectid,
                "rank_type": rank.get("type", ""),
                "friendlyname": rank.get("friendlyname", ""),
                "value": rank.get("value", ""),
                "bayesaverage": rank.get("bayesaverage", ""),
            })

    return detail_row, stats_row, link_rows, rank_rows


def collect_things(
    client: BGGClient,
    object_ids: list[str],
    detail_out_path: Path,
    stats_out_path: Path,
    link_out_path: Path,
    rank_out_path: Path,
) -> None:
    paths_fields = [
        (detail_out_path, DETAIL_FIELDS),
        (stats_out_path, STATS_FIELDS),
        (link_out_path, LINK_FIELDS),
        (rank_out_path, RANK_FIELDS),
    ]
    files = [p.open("a", newline="", encoding="utf-8") for p, _ in paths_fields]
    writers = []
    for (path, fields), f in zip(paths_fields, files):
        w = csv.DictWriter(f, fieldnames=fields)
        if not path.exists() or path.stat().st_size == 0:
            w.writeheader()
        writers.append(w)
    detail_w, stats_w, link_w, rank_w = writers

    try:
        for batch in _batched(object_ids, BATCH_SIZE):
            root = client.get("thing", {"id": ",".join(batch), "stats": 1})
            for item in root.findall("item"):
                detail_row, stats_row, link_rows, rank_rows = parse_thing(item)
                detail_w.writerow(detail_row)
                stats_w.writerow(stats_row)
                link_w.writerows(link_rows)
                rank_w.writerows(rank_rows)
            for f in files:
                f.flush()
    finally:
        for f in files:
            f.close()
