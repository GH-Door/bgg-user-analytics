"""
수집 드라이버 스크립트(collect_phase*.py) 공용 유틸 — 시작 시각 영속화 + 로깅 설정.

src/ 밑이 아니라 scripts/ 안에 두는 이유: bgg_client.py 등 src/collectors 모듈은
로거만 만들고(logging.getLogger(__name__)) 실제 핸들러 설정은 호출부(스크립트)
책임이라는 원칙을 이미 갖고 있다. 로그 파일 위치·포맷을 정하는 것도 같은
"스크립트 레벨 관심사"라 여기 둔다.

로그 파일명 규칙(CLAUDE.md §3): logs/{label}_{YYYYMMDD}.log, 날짜는 "지금"이
아니라 그 작업이 최초로 시작된 날짜 — get_or_set_started_at()으로 영속화한
시작 시각 기준. 재시작하거나 자정을 넘겨도 로그가 파일 하나로 이어진다.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

LOGS_DIR = Path("logs")


def get_or_set_started_at(started_at_path: Path) -> float:
    """최초 실행 시각(epoch)을 파일에 영속화한다. 스크립트를 재시작해도
    이 값은 그대로라 '최초 시작부터 누적 경과 시간'과 로그 파일명이 안 바뀐다."""
    if started_at_path.exists():
        return float(started_at_path.read_text().strip())
    now = time.time()
    started_at_path.write_text(str(now))
    return now


def setup_logging(started_at: float, label: str) -> None:
    date_str = datetime.fromtimestamp(started_at).strftime("%Y%m%d")
    log_path = LOGS_DIR / f"{label}_{date_str}.log"
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
