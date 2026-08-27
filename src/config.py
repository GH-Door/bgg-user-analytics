"""
프로젝트 공용 경로. fresh clone에는 data/·logs/가 없다(.gitignore로 내용물만
제외하고 디렉터리 자체는 git에 없음) — 수집 스크립트가 시작 전에 이 모듈의
ensure_dirs()를 호출해 만든다. 안 만들면 첫 파일 쓰기에서 FileNotFoundError로
죽는다(TROUBLESHOOTING.md 참고).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path("data")
LOGS_DIR = Path("logs")


def ensure_dirs() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)


@dataclass(frozen=True)
class StagePaths:
    """체크포인트/실패/시작시각 파일 경로를 label 하나로 파생시킨다.

    기존 4개 드라이버(user/collection/thing/plays)는 이미 굳어진 상수 파일명을
    쓰고 있어(예: .user_info_started_at처럼 label과 안 맞는 것도 있음) 여기로
    옮기지 않는다 — 진행 중이던 로그 파일명이 바뀌는 리스크만 생긴다. 새
    드라이버(frame/wishlist)부터 이 관례를 쓴다."""
    label: str

    @property
    def checkpoint(self) -> Path:
        return DATA_DIR / f"{self.label}_checkpoint.txt"

    @property
    def failed(self) -> Path:
        return DATA_DIR / f"{self.label}_failed.txt"

    @property
    def started_at(self) -> Path:
        return DATA_DIR / f".{self.label}_started_at"
