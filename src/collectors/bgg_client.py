"""
BGG XML API v2 공통 HTTP 계층.

기존 팀 프로젝트(크롤링 코드(주석확인해주세욥).ipynb)의 문제를 한 곳에서 해결한다:
  - 인증 헤더 없음            → 401 (2025-10경부터 BGG가 토큰 인증을 의무화함)
  - 정상 경로에 sleep 없음     → 429가 나야만 대기, rate limit 미준수
  - 202 Accepted를 성공 취급  → collection API는 큐잉 중이면 202를 반환하고
                                재요청해야 진짜 데이터가 옴
  - BeautifulSoup(..., "lxml") → XML에 HTML 파서. 표준 라이브러리로 충분해서 교체.

4xx(클라이언트 오류)는 재시도하지 않고 즉시 실패시킨다 — 잘못된 id 하나 때문에
재시도 예산을 허비하지 않기 위함. 5xx/202/429/네트워크 예외만 재시도 대상.

네트워크 레벨 예외(연결 끊김/타임아웃)와 XML 파싱 오류(응답이 200인데 중간에
잘려서 온 경우 등)는 HTTP 상태 코드로 안 걸러지므로 별도로 잡아서 5xx와
동일하게(백오프 후 재시도) 처리한다 — 안 그러면 몇 시간짜리 무인 수집 도중
네트워크가 한 번만 끊겨도 전체 프로세스가 죽는다(TROUBLESHOOTING.md #3 참고).

각 collector는 이 클라이언트로 요청만 하고, 파싱은 각자 담당한다.
로깅은 이 모듈이 로거만 만들고(`logging.getLogger(__name__)`), 실제 핸들러
설정(어느 파일에 어떤 포맷으로 쓸지)은 최상위 실행 스크립트가 담당한다.
"""
from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

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
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=30)
            except requests.exceptions.RequestException as e:
                self._last_request_at = time.monotonic()
                wait = min(2 ** attempt, 30)
                logger.warning(
                    f"{endpoint} 요청 중 네트워크 예외 ({type(e).__name__}: {e}) — "
                    f"{attempt}/{self.max_retries}회차, {wait}초 대기 (params={params})"
                )
                time.sleep(wait)
                continue
            self._last_request_at = time.monotonic()

            if resp.status_code == 401:
                # 토큰 문제는 재시도해도 의미 없다. 바로 실패시켜서 원인을 명확히 한다.
                logger.error(f"{endpoint} 요청 401 Unauthorized — 토큰 문제로 즉시 중단")
                raise BGGAuthError(
                    f"401 Unauthorized — BGG_API_TOKEN이 없거나 무효합니다. "
                    f"https://boardgamegeek.com/using_the_xml_api 에서 토큰을 발급받으세요. "
                    f"응답 본문: {resp.text[:200]!r}"
                )

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", 2 ** attempt))
                logger.warning(
                    f"{endpoint} 요청 429(rate limit) — {attempt}/{self.max_retries}회차, "
                    f"{retry_after}초 대기 (params={params})"
                )
                time.sleep(retry_after)
                continue

            if resp.status_code == 202:
                # collection API가 큐잉 중일 때 202를 반환한다. 지수 백오프 후 재요청.
                wait = min(2 ** attempt, 30)
                logger.warning(
                    f"{endpoint} 요청 202(큐잉) — {attempt}/{self.max_retries}회차, "
                    f"{wait}초 대기 (params={params})"
                )
                time.sleep(wait)
                continue

            if 400 <= resp.status_code < 500:
                # 잘못된 id/username 같은 클라이언트 오류는 재시도해도 결과가 안 바뀐다.
                # 재시도 루프에 태우면 잘못된 값 하나 때문에 최대 5회(수십 초)를 허비한다.
                logger.warning(
                    f"{endpoint} 요청 {resp.status_code} — 재시도 대상 아님 (params={params})"
                )
                raise BGGRequestError(
                    f"{endpoint} 요청이 {resp.status_code}로 실패했습니다 (재시도 대상 아님). "
                    f"params={params}, 응답: {resp.text[:200]!r}"
                )

            if resp.status_code != 200:
                # 5xx 등 일시적일 가능성이 있는 오류만 재시도.
                wait = min(2 ** attempt, 30)
                logger.warning(
                    f"{endpoint} 요청 {resp.status_code} — {attempt}/{self.max_retries}회차, "
                    f"{wait}초 대기 (params={params})"
                )
                time.sleep(wait)
                continue

            try:
                root = ET.fromstring(resp.content)
            except ET.ParseError as e:
                wait = min(2 ** attempt, 30)
                logger.warning(
                    f"{endpoint} 요청 200이지만 XML 파싱 실패 ({e}) — "
                    f"{attempt}/{self.max_retries}회차, {wait}초 대기 (params={params})"
                )
                time.sleep(wait)
                continue

            if root.tag == "errors":
                # BGG는 잘못된 요청(예: 존재하지 않는 유저명)에도 HTTP 200을 주고
                # 본문에 <errors><error><message>...</message></error></errors>를
                # 담는 경우가 있다(collection API에서 실측, thing/user는 각자 4xx로
                # 응답해서 이 경로는 안 타지만 collection은 200으로 온다). 상태 코드만
                # 보면 성공으로 착각해 빈 데이터를 "정상 수집 완료"로 체크포인트하는
                # 버그가 됨 — 실제로 파일럿 테스트에서 발견(TROUBLESHOOTING.md 참고).
                msg_el = root.find("error/message")
                msg = msg_el.text if msg_el is not None else "(메시지 없음)"
                raise BGGRequestError(
                    f"{endpoint} 요청이 200 응답 안에 <errors>를 담고 왔습니다 "
                    f"(재시도 대상 아님): {msg!r}. params={params}"
                )

            return root

        logger.error(f"{endpoint} 요청이 {self.max_retries}회 재시도 후에도 실패 (params={params})")
        raise BGGRequestError(
            f"{endpoint} 요청이 {self.max_retries}회 재시도 후에도 실패했습니다. "
            f"params={params}"
        )
