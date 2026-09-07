"""
트랙 B — 신규 표집틀 검증표본 수집 (frame_candidates.csv → user + collection API).

frame.py가 만든 frame_candidates.csv(5,911명, thing ratingcomments 기반 신규
표집틀)에서 무작위 600명을 뽑아 실제 user/collection API로 데이터를 확보한다.
용도는 frame.py 헤더에 이미 적어둔 두 가지 중 (2)번:
  - 2025~2026 코호트 보강(기존 user_list.csv 표집틀엔 이 시기 가입자가 0명)
  - 두 표집틀(user_list.csv vs frame_candidates.csv)의 실측 비교 대상

collect_users()/collect_collections()를 그대로 재사용한다(own=1, 새 파서
없음) — 출력 파일명만 _v2 접미사로 분기해 기존 본수집 산출물과 안 섞이게 한다.
run_stage()를 두 번 호출해 user 단계 → collection 단계를 순차 진행한다(각자
독립적인 체크포인트/실패 파일을 가지므로 중단 후 재실행해도 이어서 된다).
"""
from __future__ import annotations

import csv
import logging
import random

from dotenv import load_dotenv

from scripts._common import run_stage
from src.collectors.collection_collector import collect_collections
from src.collectors.user_collector import collect_users
from src.config import DATA_DIR

load_dotenv()

SEED = 20260827
SAMPLE_N = 600

CANDIDATES_PATH = DATA_DIR / "frame_candidates.csv"
SAMPLE_LOG_PATH = DATA_DIR / "frame_verify_sample.csv"
USER_INFO_V2_PATH = DATA_DIR / "user_info_v2.csv"

logger = logging.getLogger("verify_frame")


def _load_user_sample() -> list[str]:
    """이미 뽑아둔 표본이 있으면 재사용(재현성) — user.py의 _load_sample()과
    동일한 패턴. frame_candidates.csv는 (user_id, source_objectid) long
    포맷이라 유저 하나가 여러 행에 나올 수 있어 먼저 distinct한다."""
    if SAMPLE_LOG_PATH.exists():
        with SAMPLE_LOG_PATH.open(newline="", encoding="utf-8") as f:
            return [row["user_id"] for row in csv.DictReader(f)]

    with CANDIDATES_PATH.open(newline="", encoding="utf-8") as f:
        all_users = sorted({row["user_id"] for row in csv.DictReader(f)})

    random.seed(SEED)
    sample = random.sample(all_users, min(SAMPLE_N, len(all_users)))

    with SAMPLE_LOG_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["user_id"])
        writer.writerows([[u] for u in sample])

    logger.info(f"신규 표집틀 {len(all_users)}명 중 {len(sample)}명 무작위 추출 → {SAMPLE_LOG_PATH}")
    return sample


def _load_valid_users_v2() -> list[str]:
    """1단계(user API)에서 유효했던 계정만 2단계(collection API) 대상으로 삼는다
    — user.py → collection.py의 관계와 동일."""
    with USER_INFO_V2_PATH.open(newline="", encoding="utf-8") as f:
        return [row["user_id"] for row in csv.DictReader(f)]


def main() -> None:
    sample = _load_user_sample()
    run_stage("verify_user", lambda: sample, collect_users, USER_INFO_V2_PATH)
    run_stage(
        "verify_collection", _load_valid_users_v2, collect_collections, DATA_DIR,
        own=1,
        item_filename="item_info_v2.csv",
        user_item_filename="user_item_v2.csv",
    )


if __name__ == "__main__":
    main()
