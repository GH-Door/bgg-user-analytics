"""
BGG thing API의 ratingcomments 응답에서 유저명을 모아 신규 표집틀을 만든다.

호출: GET /xmlapi2/thing?id={objectid}&ratingcomments=1&page={n}&pagesize=100

배경: 기존 표집틀 user_list.csv(2024년 팀 프로젝트 유래)는 가입연도가
2024년에서 끊긴다(§docs/sampling_validity.md) — 2025·2026 가입자가 표본에
전혀 없다. BGG API는 유저를 열거하는 엔드포인트가 없어서, 이미 보유한
objectid로 "그 게임을 평가한 유저"를 역으로 모아 새 표집틀을 만든다.

주의(실측 확인, 2026-08-26, fixtures/thing_ratingcomments_id268586.xml):
comments는 rating 오름차순으로 정렬되어 온다(1점 유저가 항상 먼저 나옴).
그래서 매 게임마다 page=1만 가져오면 "그 게임에 낮은 평점을 준 유저"만
체계적으로 뽑혀, 새 표집틀을 만드는 목적(활동성/평점 편향 진단) 자체가
무의미해진다. 1차 호출로 totalitems를 확인한 뒤, 전체가 한 페이지(≤100)를
넘으면 무작위 페이지를 다시 요청해 그 페이지만 채택한다(≤100건이면 그
페이지가 전수라 애초에 편향이 없다).

이 표집틀의 한계: "게임을 평가한 유저"만 모이므로 평가 이전 이탈자는 여기도
못 잡는다 — 주 표본을 대체하지 않고 검증·보강용으로만 쓴다(PLAN 참고).
"""
from __future__ import annotations

import csv
import logging
import random
import xml.etree.ElementTree as ET
from pathlib import Path

from .bgg_client import BGGClient, BGGRequestError, BGGTransientError
from .checkpoint import append_checkpoint, load_checkpoint, report_progress

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
FIELDS = ["user_id", "source_objectid"]


def _parse_usernames(root: ET.Element) -> tuple[list[str], int]:
    comments_el = root.find("item/comments")
    if comments_el is None:
        return [], 0
    total = int(comments_el.get("totalitems", "0"))
    usernames = [c.get("username", "") for c in comments_el.findall("comment") if c.get("username")]
    return usernames, total


def collect_rating_usernames(
    client: BGGClient,
    object_ids: list[str],
    out_path: Path,
    checkpoint_path: Path,
    failed_path: Path,
    seed: int = 20260826,
    start_time: float | None = None,
) -> None:
    """object_ids(표본 게임)를 순회하며 각 게임을 평가한 유저명 최대 100명을
    (user_id, source_objectid)로 out_path에 append한다. 같은 유저가 여러
    게임에서 중복 등장할 수 있다 — dedup은 호출부(표집틀을 실제로 쓰는 단계)
    책임이다(여기서는 "어느 게임에서 뽑혔는지" 감사 로그로 남기는 게 더 값짐)."""
    random.seed(seed)
    done = load_checkpoint(checkpoint_path)
    failed = load_checkpoint(failed_path)
    is_new = not out_path.exists() or out_path.stat().st_size == 0
    total = len(object_ids)

    with out_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()

        for i, oid in enumerate(object_ids, start=1):
            if oid in done or oid in failed:
                continue

            try:
                root = client.get("thing", {
                    "id": oid, "ratingcomments": 1, "page": 1, "pagesize": PAGE_SIZE,
                })
                usernames, total_items = _parse_usernames(root)
                total_pages = -(-total_items // PAGE_SIZE)  # ceil
                if total_pages > 1:
                    # rating 오름차순 정렬 편향 방지 — 무작위 페이지로 다시 채택.
                    page = random.randint(1, total_pages)
                    root = client.get("thing", {
                        "id": oid, "ratingcomments": 1, "page": page, "pagesize": PAGE_SIZE,
                    })
                    usernames, _ = _parse_usernames(root)
            except BGGTransientError as e:
                logger.warning(f"objectid {oid} 표집틀 수집 보류(일시적 오류, 다음 실행에 재시도): {e}")
                continue
            except BGGRequestError as e:
                logger.warning(f"objectid {oid} 표집틀 수집 제외: {e}")
                append_checkpoint(failed_path, oid)
                report_progress("frame", i, total, start_time=start_time)
                continue

            for user_id in usernames:
                writer.writerow({"user_id": user_id, "source_objectid": oid})
            f.flush()
            append_checkpoint(checkpoint_path, oid)
            report_progress("frame", i, total, start_time=start_time)
