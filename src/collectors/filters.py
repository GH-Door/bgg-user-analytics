"""
수집 대상 필터 — 국가/가입연도 범위.

이 저장소를 clone해서 쓰는 다른 사람이 반드시 이 프로젝트와 동일한 모집단
(전세계, 전체 가입연도)을 수집할 필요는 없다. user_info.csv(스크리닝 결과)에
이미 country/yearregistered가 있으므로, 2단계(collection) 이후 진행할 유저를
여기서 거른다 — user API 자체엔 "국가별로 검색" 같은 쿼리 파라미터가 없어서
사전 필터링이 아니라 스크리닝 이후 후처리로만 가능하다.

config.yaml(저장소 루트)에서 읽는다 — .env가 아닌 이유: .env는 토큰/프로젝트 ID
같은 비밀값·환경별 값 전용이고, 필터는 도메인 설정값(리스트 포함)이라 성격이
다르다. config.yaml에 아무것도 안 채우면(기본값) 전부 통과 — 이 프로젝트가
실제로 쓴 값과 동일하게 무필터로 동작한다.
"""
from __future__ import annotations

from pathlib import Path

import yaml

CONFIG_PATH = Path("config.yaml")


def load_filter_from_config() -> tuple[set[str] | None, int | None, int | None]:
    if not CONFIG_PATH.exists():
        return None, None, None
    with CONFIG_PATH.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    collect_cfg = raw.get("collect") or {}
    countries = set(collect_cfg.get("countries") or []) or None
    return countries, collect_cfg.get("min_year"), collect_cfg.get("max_year")


def filter_users(
    rows: list[dict],
    countries: set[str] | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
) -> list[str]:
    """rows는 user_info.csv를 csv.DictReader로 읽은 dict 리스트(user_id/country/
    yearregistered 컬럼 필요). 조건 중 설정 안 된 것(None)은 통과시킨다.
    yearregistered가 빈 문자열인 행은 연도 필터가 걸려 있으면 제외한다(비교 불가)."""
    result = []
    for row in rows:
        if countries is not None and row.get("country", "") not in countries:
            continue
        if min_year is not None or max_year is not None:
            year_raw = row.get("yearregistered", "")
            if not year_raw:
                continue
            year = int(year_raw)
            if min_year is not None and year < min_year:
                continue
            if max_year is not None and year > max_year:
                continue
        result.append(row["user_id"])
    return result


def _demo() -> None:
    rows = [
        {"user_id": "a", "country": "United States", "yearregistered": "2010"},
        {"user_id": "b", "country": "Germany", "yearregistered": "2020"},
        {"user_id": "c", "country": "United States", "yearregistered": "2023"},
        {"user_id": "d", "country": "", "yearregistered": ""},
    ]
    assert filter_users(rows) == ["a", "b", "c", "d"], "필터 없으면 전부 통과해야 함"
    assert filter_users(rows, countries={"United States"}) == ["a", "c"]
    assert filter_users(rows, min_year=2015) == ["b", "c"]
    assert filter_users(rows, max_year=2015) == ["a"]
    assert filter_users(rows, countries={"United States"}, max_year=2015) == ["a"]

    countries, min_year, max_year = load_filter_from_config()
    assert (countries, min_year, max_year) == (None, None, None), (
        "config.yaml 기본값(전부 빔)은 무필터여야 함"
    )
    print("OK — filters 셀프 체크 6건 통과")


if __name__ == "__main__":
    _demo()
