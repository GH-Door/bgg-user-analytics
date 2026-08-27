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

from .bgg_client import BGGClient, BGGRequestError, BGGTransientError
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
    start_time: float | None = None,
) -> None:
    """user_ids(샘플)를 순회하며 각 유저의 전체 플레이 로그를 페이지네이션으로
    수집한다. 완료한 user_id는 체크포인트에 기록해 재시작 시 건너뛴다.

    한 유저의 모든 페이지를 메모리에 모았다가 전부 성공했을 때만 한 번에
    CSV에 쓴다(평균 수백 행, 최대치도 메모리 부담 없는 수준). 이렇게 하면
    페이지네이션 도중 실패(영구/일시 오류, 또는 프로세스가 강제 종료되는 경우)해도
    그 유저의 행이 하나도 안 쓰여 있으므로, "이미 받은 페이지 + 재시작 후 재수집한
    전체"가 중복되는 문제 자체가 생기지 않는다 — collection/thing처럼 별도
    dedup guard를 덧붙이는 대신 원인을 없앴다."""
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
            buffer: list[dict] = []
            try:
                while True:
                    root = client.get("plays", {"username": user_id, "page": page})
                    rows, page_total = _parse_page(root, user_id)
                    if not rows:
                        break
                    buffer.extend(rows)
                    collected += len(rows)
                    if collected >= page_total:
                        break
                    page += 1
            except BGGTransientError as e:
                # 일시적 오류로 재시도 예산 소진 — 이 유저는 무효가 아니라 "아직
                # 못 받음"이므로 failed_path에 기록하지 않는다(다음 실행에서 재시도).
                # buffer를 안 쓰고 버리므로 부분 행이 안 남는다.
                logger.warning(f"유저 {user_id} plays 수집 보류(일시적 오류, 다음 실행에 재시도, page={page}): {e}")
                continue
            except BGGRequestError as e:
                logger.warning(f"유저 {user_id} plays 수집 제외 (page={page}): {e}")
                append_checkpoint(failed_path, user_id)
                report_progress("plays", i, total, start_time=start_time)
                continue

            writer.writerows(buffer)
            f.flush()
            append_checkpoint(checkpoint_path, user_id)
            report_progress("plays", i, total, start_time=start_time)
