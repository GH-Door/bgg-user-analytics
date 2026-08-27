"""
BGG thing API 수집 — item_details + item_stats(추가 피처) + item_category /
item_mechanic / item_rank(브리지 테이블, long 포맷).

호출: GET /xmlapi2/thing?id=1,2,3,...&stats=1
  - thing API는 id를 콤마로 여러 개 넘길 수 있다. collection_collector처럼
    유저 단위로 1건씩 부르지 않고 배치로 묶어 요청 수를 크게 줄인다.
  - BATCH_SIZE=20은 실측 확인됨(2026-08-23) — 20개는 200, 21개부터 즉시 400.

주의: thing API는 배치 요청 중 존재하지 않는/병합된 id가 섞여 있으면 4xx가 아니라
HTTP 200 + 그 id만 빠진 응답을 준다(실측 확인: id=13,999999999,68448 요청 →
item 2개만 응답, 에러 표시 없음). 그래서 배치 응답에서 실제로 돌아온 id를
확인해 요청한 id 집합과 비교하고, 빠진 id는 성공 체크포인트가 아니라
failed_path로 분리한다 — 안 그러면 데이터 없는 objectid가 "수집 완료"로
영구 기록되어 다시는 재시도되지 않는다.

기존 데이터의 category/mechanic/family/designer/publisher가
"[('1050', 'Ancient'), ...]" 같은 파이썬 튜플 문자열로 저장되어 있던 문제를
여기서 원천 차단한다 — 애초에 (objectid, link_type, ref_id, value) long 포맷
브리지 테이블로 뽑아낸다. 나중에 SQL에서 파싱할 필요가 없어진다.

기획서의 numwishing 외에 같은 응답에 이미 들어있는 stats 전체
(wishing/wanting/trading/owned/numcomments/numweights/averageweight)도
함께 뽑는다 — 추가 API 호출 비용 없이 얻는 피처.

체크포인트: 배치(BATCH_SIZE개) 단위로 완료 시 그 배치의 모든 objectid를
기록한다. 약 29,000개 게임 × 20개씩이면 1,450번 이상 요청해야 하고 5초
간격이면 2시간 이상 걸리는데, 체크포인트가 없으면 중간에 죽었을 때 처음부터
다시 돌려야 하고 그러면 이미 쓴 행이 전부 중복된다.
"""
from __future__ import annotations

import csv
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from .bgg_client import BGGClient, BGGRequestError, BGGTransientError
from .checkpoint import (
    append_checkpoint, load_checkpoint, load_existing_column_values, report_progress,
)

logger = logging.getLogger(__name__)

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


def _attr(item: ET.Element, tag: str, key: str = "value") -> str:
    el = item.find(tag)
    return el.get(key, "") if el is not None else ""


def parse_thing(item: ET.Element) -> tuple[dict, dict, list[dict], list[dict]]:
    objectid = item.get("id", "")

    detail_row = {
        "objectid": objectid,
        "name": _attr(item, "name"),
        # yearpublished/minage는 <tag value="X"/> 속성 기반이라 findtext로는
        # 항상 빈 문자열이 나온다 (fixtures/thing_id8148.xml로 실측 확인).
        "yearpublished": _attr(item, "yearpublished"),
        "minage": _attr(item, "minage"),
        "description": (item.findtext("description") or ""),  # 이건 진짜 텍스트 콘텐츠
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
    output_dir: Path,
    checkpoint_path: Path,
    failed_path: Path,
    start_time: float | None = None,
) -> None:
    detail_out_path = output_dir / "item_details.csv"
    stats_out_path = output_dir / "item_stats.csv"
    link_out_path = output_dir / "item_link.csv"
    rank_out_path = output_dir / "item_rank.csv"

    done = load_checkpoint(checkpoint_path)
    failed = load_checkpoint(failed_path)
    pending = [oid for oid in object_ids if oid not in done and oid not in failed]
    total_ids = len(object_ids)
    seen_objectids = load_existing_column_values(detail_out_path, "objectid")

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
        done_count = total_ids - len(pending)
        for batch in _batched(pending, BATCH_SIZE):
            try:
                root = client.get("thing", {"id": ",".join(batch), "stats": 1})
            except BGGTransientError as e:
                # 일시적 오류로 재시도 예산 소진 — 이 배치의 id들은 무효가 아니라
                # "아직 못 받음"이므로 failed_path에 기록하지 않는다(다음 실행이
                # done/failed 둘 다에 없는 id로 인식해 자동 재시도한다).
                logger.warning(f"thing 배치 수집 보류(일시적 오류, 다음 실행에 재시도) (id={','.join(batch)}): {e}")
                continue
            except BGGRequestError as e:
                # 배치 전체를 영구 실패로 표시 — id별로 쪼개 재시도하지 않고
                # 배치째 건너뛴다(ponytail: 배치 재시도보다 단순, 필요해지면 세분화).
                logger.warning(f"thing 배치 수집 제외 (id={','.join(batch)}): {e}")
                for oid in batch:
                    append_checkpoint(failed_path, oid)
                done_count += len(batch)
                report_progress("thing", done_count, total_ids, start_time=start_time)
                continue

            items = root.findall("item")
            returned_ids = {item.get("id", "") for item in items}
            missing_ids = [oid for oid in batch if oid not in returned_ids]
            if missing_ids:
                # thing API는 삭제/병합된 id가 섞여도 4xx가 아니라 200 + 그 id만
                # 빠진 응답을 준다(실측 확인). 빠진 id를 성공으로 체크포인트하면
                # 데이터 없이 "완료"로 영구 기록되어 다시는 재시도 안 된다 — 반드시
                # failed_path로 분리한다.
                logger.warning(
                    f"thing 배치 일부 누락 (요청 {len(batch)}개 중 {len(missing_ids)}개 "
                    f"응답 없음, id={','.join(missing_ids)}) — 삭제/병합된 게임일 가능성"
                )
                for oid in missing_ids:
                    append_checkpoint(failed_path, oid)

            for item in items:
                objectid = item.get("id", "")
                if objectid in seen_objectids:
                    continue  # 재시작 시 크래시 윈도우로 인한 중복 방지
                detail_row, stats_row, link_rows, rank_rows = parse_thing(item)
                detail_w.writerow(detail_row)
                stats_w.writerow(stats_row)
                link_w.writerows(link_rows)
                rank_w.writerows(rank_rows)
                seen_objectids.add(objectid)
            for f in files:
                f.flush()
            # 실제로 응답에 있었던 id만 성공 체크포인트.
            for oid in batch:
                if oid in returned_ids:
                    append_checkpoint(checkpoint_path, oid)
            done_count += len(batch)
            report_progress("thing", done_count, total_ids, start_time=start_time)
    finally:
        for f in files:
            f.close()
