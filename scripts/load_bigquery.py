"""
실제 재수집 CSV(data/*.csv) → BigQuery bgg_raw 적재.

load_fallback_2024.py와 같은 유틸(src/loaders/bigquery_loader.py)을 쓰지만,
2024 데이터와 달리 수집 스키마가 이미 목표 스키마 그대로라 fallback_adapter.py
같은 변환이 필요 없다 — CSV를 곧바로 적재한다.

WRITE_TRUNCATE라 재실행해도 멱등하다(2024 폴백이 들어있던 자리를 그대로 교체).
실행: uv run python -m scripts.load_bigquery (저장소 루트에서)
필요: .env에 GCP_PROJECT_ID, gcloud auth application-default login 완료
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from google.cloud import bigquery

from src.config import DATA_DIR
from src.loaders.bigquery_loader import ensure_dataset, load_csv_to_raw

load_dotenv()

PROJECT_ID = os.environ["GCP_PROJECT_ID"]
DATASET_RAW = os.environ.get("BQ_DATASET_RAW", "bgg_raw")

logger = logging.getLogger("load_bigquery")

# table_name -> CSV 파일명. item_info/item_details/.../user_play는 own=1
# 본수집 산출물. user_wishlist는 wishlist=1로 별도 수집한 결과(scripts/collect/wishlist.py).
TABLE_TO_CSV = {
    "user_info": "user_info.csv",
    "item_info": "item_info.csv",
    "user_item": "user_item.csv",
    "item_details": "item_details.csv",
    "item_stats": "item_stats.csv",
    "item_link": "item_link.csv",
    "item_rank": "item_rank.csv",
    "user_play": "user_play.csv",
    "user_wishlist": "user_wishlist.csv",
    "plays_sample": "plays_sample_users.csv",
}


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
    )
    client = bigquery.Client(project=PROJECT_ID)
    ensure_dataset(client, PROJECT_ID, DATASET_RAW)

    for table_name, csv_name in TABLE_TO_CSV.items():
        csv_path = DATA_DIR / csv_name
        if not csv_path.exists():
            logger.warning(f"{csv_path} 없음 — {table_name} 스킵")
            continue
        load_csv_to_raw(client, PROJECT_ID, DATASET_RAW, table_name, csv_path)

    logger.info("=== bgg_raw 적재 완료 (2024 폴백 → 실제 재수집 데이터로 전량 교체) ===")


if __name__ == "__main__":
    main()
