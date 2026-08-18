"""
체크포인트 + 진행 상황 로깅 공용 유틸.

collection/thing/plays 세 수집기가 각자 `_load_checkpoint`를 복붙해 두던 것을
여기 하나로 모은다. 완료한 id(user_id 또는 objectid)를 텍스트 파일에 한 줄씩
append하고, 재시작 시 그 파일을 읽어 이미 끝난 id를 건너뛴다.

실패(영구적 오류로 제외된) id도 별도 파일에 같은 방식으로 남긴다 — 체크포인트와
합쳐서 "이미 처리됨(성공이든 제외든)"으로 간주해 무한 재시도를 막는다.
"""
from __future__ import annotations

import logging
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


def report_progress(label: str, done: int, total: int, every: int = 50) -> None:
    """수 시간 걸릴 수 있는 수집 작업이 살아있는지 알 수 있도록 주기적으로 로깅한다.
    every마다, 그리고 마지막 1건에서 기록 — 매 건마다 찍으면 로그가 너무 시끄럽다."""
    if done % every == 0 or done == total:
        logger.info(f"[{label}] {done}/{total}")
