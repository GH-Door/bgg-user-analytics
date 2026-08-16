"""
bgg_client의 핵심 로직 셀프 체크. 실제 네트워크 호출 없이 requests.get을 모킹한다.
프레임워크 없이 assert만 사용 — python3 collectors/test_bgg_client.py 로 실행.

검증 대상:
  1. 401 응답은 재시도 없이 즉시 BGGAuthError로 실패한다 (토큰 문제는 재시도해도
     무의미하므로 조기 실패가 의도된 동작).
  2. 연속 요청 사이에 min_interval 만큼의 대기가 강제된다 (레이트리밋 준수).
  3. 202(큐잉 중) 이후 200이 오면 최종적으로 파싱된 결과를 정상 반환한다.
"""
from unittest.mock import patch, MagicMock

from bgg_client import BGGClient, BGGAuthError


def test_401_raises_immediately():
    client = BGGClient(token="invalid", min_interval=0)
    resp = MagicMock(status_code=401, text="Unauthorized")
    with patch("bgg_client.requests.get", return_value=resp):
        try:
            client.get("thing", {"id": 13})
        except BGGAuthError:
            pass
        else:
            raise AssertionError("401이면 BGGAuthError가 발생해야 합니다")


def test_min_interval_enforced():
    client = BGGClient(token="t", min_interval=5.0)
    ok_resp = MagicMock(status_code=200, content=b"<items></items>")
    sleep_calls = []
    with patch("bgg_client.requests.get", return_value=ok_resp), \
         patch("bgg_client.time.sleep", side_effect=lambda s: sleep_calls.append(s)):
        client.get("thing", {"id": 1})
        client._last_request_at -= 1.0  # 방금 1초 전에 요청한 것처럼 시간을 되돌림
        client.get("thing", {"id": 2})
    assert any(s > 0 for s in sleep_calls), "간격이 부족하면 sleep이 호출되어야 합니다"
    assert abs(sleep_calls[-1] - 4.0) < 0.5, f"약 4초 대기가 기대되나 {sleep_calls[-1]}초였습니다"


def test_202_then_200_returns_parsed_root():
    client = BGGClient(token="t", min_interval=0)
    queued = MagicMock(status_code=202)
    ok = MagicMock(status_code=200, content=b"<items><item id='1'/></items>")
    with patch("bgg_client.requests.get", side_effect=[queued, ok]), \
         patch("bgg_client.time.sleep"):
        root = client.get("thing", {"id": 1})
    assert root.tag == "items"
    assert root.find("item").get("id") == "1"


if __name__ == "__main__":
    test_401_raises_immediately()
    test_min_interval_enforced()
    test_202_then_200_returns_parsed_root()
    print("OK — bgg_client 셀프 체크 3건 통과")
