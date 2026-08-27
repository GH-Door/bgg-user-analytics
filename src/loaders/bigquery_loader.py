"""
CSV(수집 결과) → BigQuery bgg_raw 데이터셋 적재.

원칙:
  - 스키마는 pandas 자동추론에 맡기지 않고 명시한다. rank="Not Ranked" 같은
    혼입 문자열이 실제로 있는 컬럼이라 자동추론이 타입을 잘못 잡기 쉽다.
  - 컬럼 목록은 각 collector의 *_FIELDS를 그대로 가져다 쓴다. 예전엔 여기
    TABLE_SCHEMAS에 컬럼명을 손으로 다시 나열했는데, collector 쪽 필드가
    바뀌어도 여기가 안 바뀌면 조용히 어긋난다 — 단일 진실 공급원을 collector로
    통일해 이 드리프트를 원천 차단한다.
  - WRITE_TRUNCATE로 적재해 재실행해도 멱등(idempotent)하게 만든다.
    raw는 "가장 최근 수집 결과의 스냅샷"으로 취급하고, 이력이 필요하면
    적재 시각 컬럼을 추가하는 방향으로 나중에 확장한다.
  - staging/mart는 이 로더가 아니라 sql/staging, sql/marts의 쿼리가 담당한다.
    (원본 데이터를 파이썬으로 정제하지 않고 BigQuery SQL로 정제 — DA 포트폴리오
    관점에서 SQL 비중을 의도적으로 높이는 선택)
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

logger = logging.getLogger(__name__)

from ..collectors.user_collector import FIELDS as USER_INFO_FIELDS
from ..collectors.collection_collector import ITEM_FIELDS, USER_ITEM_FIELDS
from ..collectors.thing_collector import (
    DETAIL_FIELDS, STATS_FIELDS, LINK_FIELDS, RANK_FIELDS,
)
from ..collectors.plays_collector import FIELDS as USER_PLAY_FIELDS

# user_wishlist는 wishlist.py가 collect_collections()를 wishlist=1로 재사용해
# 만든 결과라 컬럼이 user_item과 완전히 동일하다(collection_collector.py 참고).

# TODO: 컬럼 dtype이 확정되면(수집 후 실제 데이터 확인하며) STRING 일변도에서
# INTEGER/FLOAT/DATE로 세분화. 초안에서는 결측/이상값이 흔한 원본 특성상
# 전부 STRING으로 받고 정제는 sql/staging에서 CAST로 처리하는 쪽을 택했다.
_RAW_TABLE_FIELDS: dict[str, list[str]] = {
    "user_info": USER_INFO_FIELDS,
    "item_info": ITEM_FIELDS,
    "user_item": USER_ITEM_FIELDS,
    "item_details": DETAIL_FIELDS,
    "item_stats": STATS_FIELDS,
    "item_link": LINK_FIELDS,
    "item_rank": RANK_FIELDS,
    "user_play": USER_PLAY_FIELDS,
    "user_wishlist": USER_ITEM_FIELDS,
    # plays 표집 명단(scripts/collect/plays.py의 _select_sample() 산출물) — 코호트
    # 분석의 분모(가입연도별 표본 크기)를 구하려면 "실제로 관측을 시도한 913명"
    # 목록 자체가 필요하다. stg_user_play만으로는 플레이 기록이 0건인 유저가
    # 누락되어 분모가 작게 잡힌다.
    "plays_sample": ["user_id", "yearregistered"],
}

TABLE_SCHEMAS: dict[str, list[bigquery.SchemaField]] = {
    table: [bigquery.SchemaField(name, "STRING") for name in fields]
    for table, fields in _RAW_TABLE_FIELDS.items()
}


def load_csv_to_raw(
    client: bigquery.Client,
    project_id: str,
    dataset: str,
    table_name: str,
    csv_path: Path,
) -> None:
    if table_name not in TABLE_SCHEMAS:
        raise ValueError(f"알 수 없는 테이블입니다: {table_name}. TABLE_SCHEMAS에 추가하세요.")

    df = pd.read_csv(csv_path, dtype=str)  # 전부 문자열로 읽어 스키마와 맞춘다
    table_id = f"{project_id}.{dataset}.{table_name}"

    job_config = bigquery.LoadJobConfig(
        schema=TABLE_SCHEMAS[table_name],
        write_disposition="WRITE_TRUNCATE",
    )
    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()  # 완료까지 대기, 실패 시 예외로 드러남
    logger.info(f"{table_id}: {len(df)}행 적재 완료")


def ensure_dataset(client: bigquery.Client, project_id: str, dataset: str, location: str = "US") -> None:
    dataset_id = f"{project_id}.{dataset}"
    ds = bigquery.Dataset(dataset_id)
    ds.location = location
    client.create_dataset(ds, exists_ok=True)
