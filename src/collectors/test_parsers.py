"""
파싱 함수 회귀 테스트 — 실제 BGG 서버 응답(fixtures/*.xml)을 대상으로 검증한다.

fixtures/*.xml은 오픈소스 BGG API 래퍼(lcosmin/boardgamegeek)의 테스트 스위트가
과거에 실제로 캡처해둔 응답이다. bgg_client.py의 셀프 체크(test_bgg_client.py)는
HTTP 계층(레이트리밋/401/202 처리)만 mock으로 검증하고, 정작 가장 실수하기 쉬운
XML 파싱 로직은 검증하지 않았다 — 이 파일이 그 구멍을 메운다.

실제로 이 테스트를 짜는 과정에서 thing_collector.py의 yearpublished/minage가
findtext()로 잘못 읽혀 항상 빈 문자열이 나오는 버그를 발견해 고쳤다
(PLAN.md 결정 로그 참고). 프레임워크 없이 assert만 사용 — 상대 임포트를 쓰므로
반드시 저장소 루트에서 `uv run python -m src.collectors.test_parsers`로 실행.
"""
import xml.etree.ElementTree as ET
from pathlib import Path

from .thing_collector import parse_thing
from .collection_collector import parse_collection_item
from .plays_collector import _parse_page
from .user_collector import parse_user

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_thing():
    root = ET.parse(FIXTURES / "thing_id8148.xml").getroot()
    item = root.find("item")
    detail, stats, links, ranks = parse_thing(item)

    assert detail["objectid"] == "8148"
    assert detail["name"] == "Trio"
    assert detail["yearpublished"] == "1972", "속성 기반 필드 — findtext로 읽으면 빈 문자열이 나옴"
    assert detail["minage"] == "7", "속성 기반 필드 — findtext로 읽으면 빈 문자열이 나옴"
    assert "Similar to Mag-Nif" in detail["description"]

    assert stats["usersrated"] == "7"
    assert stats["wishing"] == "5"
    assert stats["averageweight"] == "1"
    assert detail["avg_weights"] == stats["averageweight"]

    link_types = {l["link_type"] for l in links}
    assert "boardgamecategory" in link_types
    assert "boardgamemechanic" in link_types

    rank_types = {r["rank_type"] for r in ranks}
    assert "subtype" in rank_types
    assert "family" in rank_types
    assert all(r["value"] == "Not Ranked" for r in ranks), "이 게임은 실제로 미랭크 상태"


def test_parse_collection_item():
    root = ET.parse(FIXTURES / "collection_fagentu007.xml").getroot()
    item = root.find("item[@subtype='boardgame']")
    item_row, user_item_row = parse_collection_item(item)

    assert item_row["objectid"] == "147253"
    assert item_row["name"] == "The Ancient World"
    assert item_row["yearpublished"] == "2014"
    assert item_row["average"] == "7.19396"
    assert item_row["rank"] == "891"  # subtype(전체) 순위 — 대표값

    assert user_item_row["objectid"] == "147253"
    assert user_item_row["user_rating"] == "N/A"  # 실제로 미평가 유저가 있음
    assert user_item_row["numplays"] == "0"
    assert user_item_row["own"] == "1"
    assert user_item_row["wishlist"] == "0"
    assert user_item_row["lastmodified"] == "2016-05-31 22:30:02"


def test_parse_page_plays():
    root = ET.parse(FIXTURES / "plays_fagentu007.xml").getroot()
    rows, total = _parse_page(root, "fagentu007")

    assert total == 32
    assert len(rows) > 0
    first = rows[0]
    assert first["play_id"] == "17162553"
    assert first["play_date"] == "2016-01-07"
    assert first["objectid"] == "155873"
    assert first["user_id"] == "fagentu007"


def test_parse_user():
    root = ET.parse(FIXTURES / "user_fagentu007.xml").getroot()
    row = parse_user(root, "fagentu007")

    assert row["yearregistered"] == "2014"
    assert row["lastlogin"] == "2017-12-20"
    assert row["country"] == "Romania"


if __name__ == "__main__":
    test_parse_thing()
    test_parse_collection_item()
    test_parse_page_plays()
    test_parse_user()
    print("OK — 실제 BGG 응답 fixture 기준 파서 회귀 테스트 4건 통과")
