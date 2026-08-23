"""
2024 팀 프로젝트 CSV를 신규 수집 스키마로 변환해 BigQuery bgg_raw에 적재한다.
PLAN.md 트랙 A 1번 작업 — 이후 모든 트랙 A 작업(전처리/지표/EDA/marts)의 전제.

1회성 스크립트. 실제 재수집이 끝나면 다시 쓸 일 없다 — fallback_adapter.py와
함께 그때 지워도 된다.

실행: uv run python -m scripts.load_fallback_2024 (저장소 루트에서, collect_phase*.py와
동일한 실행 방식 — 이러면 src/가 sys.path에 잡혀서 수동 삽입이 필요 없다)
필요: .env에 GCP_PROJECT_ID, gcloud auth application-default login 완료
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import bigquery

from src.loaders.bigquery_loader import ensure_dataset, load_csv_to_raw
from src.loaders.fallback_adapter import (
    adapt_user_info, adapt_item_info, adapt_user_item, adapt_item_details,
)

load_dotenv()

SRC_2024 = Path("/Users/mungughyeon/Documents/Bootcamp/zero-base/Final Project/data")
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

PROJECT_ID = os.environ["GCP_PROJECT_ID"]
DATASET_RAW = os.environ.get("BQ_DATASET_RAW", "bgg_raw")


def main() -> None:
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

    print(
        "완료 — item_stats/item_rank/user_play는 2024 데이터로 백필 불가하여 "
        "스킵(PLAN.md 트랙 B에서 재수집 후 적재)"
    )


if __name__ == "__main__":
    main()
