"""Runtime resource path resolution for dev and PyInstaller frozen environments."""

from __future__ import annotations

import sys
from pathlib import Path


def get_resource_path(relative: str) -> Path:
    """PyInstaller frozen 환경과 개발 환경 모두에서 리소스 경로를 반환.

    --onedir 모드: sys._MEIPASS (추출 디렉터리) 기준
    개발 환경: 프로젝트 루트 기준
    """
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent.parent.parent
    return base / relative
