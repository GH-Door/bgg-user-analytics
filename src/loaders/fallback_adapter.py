"""
2024 팀 프로젝트 CSV(구 스키마) → 신규 수집 스키마와 동일한 모양으로 변환.

목적: raw 테이블의 컬럼 구성을 데이터 출처(2024 폴백 vs 실제 재수집)와 무관하게
항상 동일하게 유지한다. 그래야 이 위에 짜는 staging/mart SQL을 나중에 다시 쓸
필요가 없다 — 재수집이 끝나면 이 어댑터 파일 하나만 버리면 된다.

한계 (백필 불가능한 것):
  item_stats(wishing/wanting 등), item_rank(subtype별 상세), user_play는
  2024 데이터에 대응하는 정보가 아예 없다. 이 어댑터는 그 테이블들을
  만들지 않는다 — 트랙 A(PLAN.md §13)의 지표는 이 테이블들을 쓰지 않으므로
  문제없고, 필요한 지표(Play-to-Wish 가설, 실측 코호트)는 트랙 B로 미뤄져 있다.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd

from ..collectors.user_collector import FIELDS as USER_INFO_FIELDS
from ..collectors.collection_collector import ITEM_FIELDS, USER_ITEM_FIELDS
from ..collectors.thing_collector import DETAIL_FIELDS, LINK_FIELDS

# 2024 CSV의 link 컬럼명 → 실제 BGG thing API의 link type 문자열
# (오픈소스 래퍼 lcosmin/boardgamegeek의 game.py에서 실측 확인한 값).
# 이렇게 맞춰둬야 나중에 진짜 수집한 item_link와 link_type 값이 똑같아져서
# 이걸 참조하는 SQL을 두 벌 짤 필요가 없다.
LINK_COLUMN_TO_TYPE = {
    "category": "boardgamecategory",
    "mechanic": "boardgamemechanic",
    "family": "boardgamefamily",
    "expansion": "boardgameexpansion",
    "accessory": "boardgameaccessory",
    "implementation": "boardgameimplementation",
    "designer": "boardgamedesigner",
    "artist": "boardgameartist",
    "publisher": "boardgamepublisher",
}


def _parse_tuple_list(cell) -> list[tuple[str, str]]:
    """"[('1050', 'Ancient'), ...]" 같은 파이썬 리터럴 문자열을 파싱한다.
    결측/빈 문자열/파싱 실패는 빈 리스트로 처리 — 값을 지어내지 않고 skip."""
    if not isinstance(cell, str) or not cell.strip():
        return []
    try:
        return ast.literal_eval(cell)
    except (ValueError, SyntaxError):
        return []


def adapt_user_info(csv_path: Path) -> pd.DataFrame:
    return pd.read_csv(csv_path, dtype=str)[USER_INFO_FIELDS]


def adapt_item_info(csv_path: Path) -> pd.DataFrame:
    return pd.read_csv(csv_path, dtype=str)[ITEM_FIELDS]


def adapt_user_item(csv_path: Path) -> pd.DataFrame:
    """2024 CSV엔 own=1로 수집했다는 사실 자체가 없고 status 플래그(own/want/
    wishlist 등)도 아예 없었다 — own만 "1"로 채우고 나머지는 빈 값으로 둔다.
    이 컬럼들은 2024 데이터로는 백필 불가능, 재수집 후에만 채워진다."""
    df = pd.read_csv(csv_path, dtype=str)
    df["own"] = "1"
    return df.reindex(columns=USER_ITEM_FIELDS, fill_value="")


def adapt_item_details(csv_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """반환: (item_details 모양 DataFrame, item_link 모양 DataFrame).

    yearpublished는 2024 item_details.csv에 없는 컬럼이다 — item_info.yearpublished가
    이미 있으므로 여기선 빈 값으로 두고, staging에서 item_info를 join해 채운다."""
    df = pd.read_csv(csv_path, dtype=str)

    detail_df = pd.DataFrame({
        "objectid": df["objectid"],
        "name": df["name"],
        "yearpublished": "",
        "minage": df["minage"],
        "description": df["description"],
        "avg_weights": df["avg_weights"],
    })[DETAIL_FIELDS]

    link_rows = [
        {"objectid": row["objectid"], "link_type": link_type, "ref_id": ref_id, "value": value}
        for _, row in df.iterrows()
        for column, link_type in LINK_COLUMN_TO_TYPE.items()
        for ref_id, value in _parse_tuple_list(row.get(column))
    ]
    link_df = pd.DataFrame(link_rows, columns=LINK_FIELDS)

    return detail_df, link_df
