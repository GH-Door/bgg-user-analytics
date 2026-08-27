"""
2024 팀 프로젝트 CSV를 신규 수집 스키마로 변환해 BigQuery bgg_raw에 적재한다.
PLAN.md 트랙 A 1번 작업 — 이후 모든 트랙 A 작업(전처리/지표/EDA/marts)의 전제.

1회성 스크립트. 실제 재수집이 끝나면 다시 쓸 일 없다 — fallback_adapter.py와
함께 그때 지워도 된다.

실행: uv run python -m scripts.load_fallback_2024 (저장소 루트에서, scripts/collect/*.py와
동일한 실행 방식 — 이러면 src/가 sys.path에 잡혀서 수동 삽입이 필요 없다)
필요: .env에 GCP_PROJECT_ID, gcloud auth application-default login 완료

주의: 이 스크립트는 트랙 B(실제 재수집)와 동일한 경로(data/user_info.csv 등)에
덮어쓰기 모드로 쓰고, BigQuery엔 WRITE_TRUNCATE로 적재한다. 트랙 B 수집이
시작된 뒤 실수로 재실행하면 실제 수집 데이터가 통째로 2024 데이터로 되돌아간다 —
그래서 아래 _guard_against_live_data()가 (1) 각 수집 단계의 시작-시각 마커 파일과
(2) 실제 출력 CSV에 헤더 외 데이터가 있는지를 함께 확인해 막는다. 마커 파일명은
scripts/collect/*.py 드라이버 이름과 하드 커플링하지 않는다 — 저 스크립트들을
리네이밍/이동해도 여기가 ImportError로 죽지 않게, 문자열 목록으로만 관리한다.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import bigquery

from src.config import DATA_DIR
from src.loaders.bigquery_loader import ensure_dataset, load_csv_to_raw
from src.loaders.fallback_adapter import (
    adapt_user_info, adapt_item_info, adapt_user_item, adapt_item_details,
)

load_dotenv()

SRC_2024 = Path("/Users/mungughyeon/Documents/Bootcamp/zero-base/Final Project/data")

PROJECT_ID = os.environ["GCP_PROJECT_ID"]
DATASET_RAW = os.environ.get("BQ_DATASET_RAW", "bgg_raw")

logger = logging.getLogger("load_fallback_2024")

# 각 수집 단계의 STARTED_AT_PATH 파일명. 드라이버 모듈을 import하지 않고 문자열로만
# 관리 — user.py/collection.py/thing.py/plays.py 리네이밍·이동에 이 가드가 안 걸린다.
_TRACK_B_MARKERS = [
    ".user_started_at", ".user_info_started_at",  # 리네이밍 전/후 둘 다 확인
    ".collection_started_at", ".thing_started_at", ".plays_started_at",
]
# 마커 파일이 지워져도(예: 실수로 rm) 실제 데이터가 남아있으면 걸러내기 위한
# 이중 체크 — 헤더 한 줄만 있는 게 아니라 실제 행이 있는지 본다.
_TRACK_B_OUTPUTS = ["user_info.csv", "item_info.csv", "item_details.csv", "user_play.csv"]


def _has_real_rows(csv_path: Path) -> bool:
    if not csv_path.exists():
        return False
    with csv_path.open(encoding="utf-8") as f:
        next(f, None)  # 헤더
        return next(f, None) is not None


def _guard_against_live_data() -> None:
    found_markers = [m for m in _TRACK_B_MARKERS if (DATA_DIR / m).exists()]
    found_outputs = [name for name in _TRACK_B_OUTPUTS if _has_real_rows(DATA_DIR / name)]
    if found_markers or found_outputs:
        raise RuntimeError(
            f"트랙 B 실제 수집이 이미 시작됨(마커: {found_markers}, 데이터: {found_outputs}) "
            "— load_fallback_2024를 재실행하면 실제 수집 데이터가 2024 데이터로 "
            "덮어써진다. 정말 필요하면 이 가드를 직접 지우고 실행할 것."
        )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
    )
    _guard_against_live_data()
    DATA_DIR.mkdir(exist_ok=True)
    client = bigquery.Client(project=PROJECT_ID)
    ensure_dataset(client, PROJECT_ID, DATASET_RAW)

    simple_adapters = {
        "user_info": lambda: adapt_user_info(SRC_2024 / "user_info.csv"),
        "item_info": lambda: adapt_item_info(SRC_2024 / "item_info.csv"),
        "user_item": lambda: adapt_user_item(SRC_2024 / "user_item.csv"),
    }
    for table_name, adapt_fn in simple_adapters.items():
        df = adapt_fn()
        out_path = DATA_DIR / f"{table_name}.csv"
        df.to_csv(out_path, index=False)
        load_csv_to_raw(client, PROJECT_ID, DATASET_RAW, table_name, out_path)

    detail_df, link_df = adapt_item_details(SRC_2024 / "item_details.csv")
    for table_name, df in [("item_details", detail_df), ("item_link", link_df)]:
        out_path = DATA_DIR / f"{table_name}.csv"
        df.to_csv(out_path, index=False)
        load_csv_to_raw(client, PROJECT_ID, DATASET_RAW, table_name, out_path)

    logger.info(
        "완료 — item_stats/item_rank/user_play는 2024 데이터로 백필 불가하여 "
        "스킵(PLAN.md 트랙 B에서 재수집 후 적재)"
    )


if __name__ == "__main__":
    main()
