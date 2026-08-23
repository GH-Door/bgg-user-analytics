"""
이 모듈은 서로 다른 두 가지를 담당한다 — 이름은 첫 번째 것만 가리키니 주의:

1. 체크포인트 파일 I/O (load_checkpoint/append_checkpoint)
   collection/thing/plays 세 수집기가 각자 `_load_checkpoint`를 복붙해 두던 것을
   여기 하나로 모은다. 완료한 id(user_id 또는 objectid)를 텍스트 파일에 한 줄씩
   append하고, 재시작 시 그 파일을 읽어 이미 끝난 id를 건너뛴다. 실패(영구적
   오류로 제외된) id도 별도 파일에 같은 방식으로 남긴다 — 체크포인트와 합쳐서
   "이미 처리됨(성공이든 제외든)"으로 간주해 무한 재시도를 막는다.

2. 진행률/ETA 로깅 (report_progress)
   수 시간 걸리는 배치 작업의 진행 상황을 주기적으로 로깅한다. 체크포인트와는
   별개 관심사지만 세 수집기가 똑같이 필요로 해서 여기 같이 둔다. "진행률
   로깅 유틸 어디 있지"로 찾을 때 이 파일명(checkpoint.py)이 바로 안 떠오를
   수 있다는 점을 감안할 것 — collect_phase1_screening.py가 한동안 이 함수를
   안 쓰고 직접 재구현했던 게 그 예시였다(scripts/_common.py 통합 때 정리됨).
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def load_checkpoint(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(path.read_text(encoding="utf-8").splitlines())


def append_checkpoint(path: Path, item_id: str) -> None:
    """checkpoint_path(성공)와 failed_path(영구적 오류로 제외) 둘 다 이 함수로 기록한다.
    포맷이 같아 load_checkpoint로 그대로 읽힌다 — 실패 사유 자체는 파일이 아니라
    로그(logging)에 남긴다."""
    with path.open("a", encoding="utf-8") as f:
        f.write(item_id + "\n")
        f.flush()


def report_progress(
    label: str, done: int, total: int, every: int = 50, start_time: float | None = None
) -> None:
    """수 시간 걸릴 수 있는 수집 작업이 살아있는지 알 수 있도록 주기적으로 로깅한다.
    every마다, 그리고 마지막 1건에서 기록 — 매 건마다 찍으면 로그가 너무 시끄럽다.

    start_time(time.monotonic() 기준)을 넘기면 경과·예상 잔여 시간도 같이 남긴다
    (phase1 스크린 스크립트가 자체 루프에서 하던 계산을 공용 유틸로 승격)."""
    if done % every == 0 or done == total:
        msg = f"[{label}] {done}/{total}"
        if start_time is not None:
            elapsed = time.monotonic() - start_time
            rate = elapsed / done if done else 0
            remaining = rate * (total - done)
            msg += f" · 경과 {elapsed/60:.1f}분 · 예상 잔여 {remaining/60:.1f}분"
        logger.info(msg)
