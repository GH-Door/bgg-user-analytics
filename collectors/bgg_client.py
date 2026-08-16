"""
BGG XML API v2 공통 HTTP 계층.

기존 팀 프로젝트(크롤링 코드(주석확인해주세욥).ipynb)의 문제를 한 곳에서 해결한다:
  - 인증 헤더 없음            → 401 (2025-10경부터 BGG가 토큰 인증을 의무화함)
  - 정상 경로에 sleep 없음     → 429가 나야만 대기, rate limit 미준수
  - 202 Accepted를 성공 취급  → collection API는 큐잉 중이면 202를 반환하고
                                재요청해야 진짜 데이터가 옴
  - BeautifulSoup(..., "lxml") → XML에 HTML 파서. 표준 라이브러리로 충분해서 교체.

각 collector는 이 클라이언트로 요청만 하고, 파싱은 각자 담당한다.
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests

BASE_URL = "https://boardgamegeek.com/xmlapi2"

# ponytail: 요청 간격은 상수 하나로 시작. 토큰 발급 후 공식 rate limit 문서를
# 확인하면 이 값을 교체한다. 지금은 기존 코드가 따르던 관행치(5초)를 기본값으로 둔다.
MIN_INTERVAL_SEC = 5.0

MAX_RETRIES = 5


class BGGAuthError(RuntimeError):
    """토큰이 없거나 무효함(401). 재시도해도 소용없으므로 즉시 중단시키는 용도."""


class BGGRequestError(RuntimeError):
    """재시도를 다 소진했는데도 실패한 경우."""


@dataclass
class BGGClient:
    token: str
    min_interval: float = MIN_INTERVAL_SEC
    max_retries: int = MAX_RETRIES
    _last_request_at: float = 0.0

    def _wait_for_slot(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.min_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def get(self, endpoint: str, params: dict) -> ET.Element:
        """
        endpoint 예: "thing", "collection", "user", "plays"
        성공 시 파싱된 XML 루트를 반환한다. 실패 시 예외를 던진다(값을 삼키지 않음).
        """
        url = f"{BASE_URL}/{endpoint}"
        headers = {"Authorization": f"Bearer {self.token}"}

        for attempt in range(1, self.max_retries + 1):
            self._wait_for_slot()
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            self._last_request_at = time.monotonic()

            if resp.status_code == 401:
                # 토큰 문제는 재시도해도 의미 없다. 바로 실패시켜서 원인을 명확히 한다.
                raise BGGAuthError(
                    f"401 Unauthorized — BGG_API_TOKEN이 없거나 무효합니다. "
                    f"https://boardgamegeek.com/using_the_xml_api 에서 토큰을 발급받으세요. "
                    f"응답 본문: {resp.text[:200]!r}"
                )

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", 2 ** attempt))
                time.sleep(retry_after)
                continue

            if resp.status_code == 202:
                # collection API가 큐잉 중일 때 202를 반환한다. 지수 백오프 후 재요청.
                time.sleep(min(2 ** attempt, 30))
                continue

            if resp.status_code != 200:
                # TODO: 재시도로 못 살리는 상태코드(404 등)는 여기서 즉시 실패시켜도 됨.
                # 초안이므로 일단 재시도 루프에 태워 최종적으로 BGGRequestError로 수렴시킨다.
                time.sleep(min(2 ** attempt, 30))
                continue

            return ET.fromstring(resp.content)

        raise BGGRequestError(
            f"{endpoint} 요청이 {self.max_retries}회 재시도 후에도 실패했습니다. "
            f"params={params}"
        )
