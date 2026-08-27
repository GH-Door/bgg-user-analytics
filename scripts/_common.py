"""
수집 드라이버 스크립트(scripts/collect/*.py) 공용 유틸 — 시작 시각 영속화 + 로깅 설정.

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
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from src.collectors.bgg_client import BGGClient
from src.config import LOGS_DIR, StagePaths, ensure_dirs


def get_or_set_started_at(started_at_path: Path) -> float:
    """최초 실행 시각(epoch)을 파일에 영속화한다. 스크립트를 재시작해도
    이 값은 그대로라 '최초 시작부터 누적 경과 시간'과 로그 파일명이 안 바뀐다.

    fresh clone에는 data/·logs/ 디렉터리 자체가 없다(.gitignore) — 여기서
    ensure_dirs()로 먼저 만들어야 이 아래 write_text()가 안 죽는다."""
    ensure_dirs()
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


def run_stage(
    label: str,
    load_ids: Callable[[], list[str]],
    collect_fn: Callable[..., None],
    output: Path,
    unit: str = "명",
    **collect_kwargs,
) -> None:
    """새 드라이버(frame/wishlist 등)의 시작시각 영속화 → 로깅 설정 →
    ensure_dirs() → client 생성 → 수집 호출 → 완료 로그를 한곳에 모은다.
    기존 4개 드라이버(user/collection/thing/plays)는 이미 완성돼 있고 진행
    중이던 로그 파일명이 바뀌는 리스크가 있어 여기로 옮기지 않는다 — 새
    드라이버부터 이 뼈대를 쓴다.

    output은 수집기 시그니처에 맞춰 드라이버가 직접 결정한다(collect_users는
    파일 하나, collect_collections는 디렉터리 — 강제로 통일하지 않는다)."""
    paths = StagePaths(label)
    started_at = get_or_set_started_at(paths.started_at)
    setup_logging(started_at, label)
    stage_logger = logging.getLogger(label)

    ids = load_ids()
    stage_logger.info(f"=== {label} 수집 시작 · 대상 {len(ids)}{unit} ===")

    client = BGGClient(token=os.environ["BGG_API_TOKEN"])
    t0 = time.monotonic()
    collect_fn(client, ids, output, paths.checkpoint, paths.failed, start_time=t0, **collect_kwargs)
    stage_logger.info(
        f"=== {label} 수집 완료 · 이번 실행 소요 {(time.monotonic()-t0)/60:.1f}분 · "
        f"최초 시작부터 누적 {(time.time()-started_at)/60:.1f}분 ==="
    )
