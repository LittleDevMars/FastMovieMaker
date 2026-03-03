"""애플리케이션 로거 설정.

RotatingFileHandler 기반 파일 로그와 콘솔 로그를 함께 제공한다.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.utils.config import APP_NAME

# ── 설정 상수 ──────────────────────────────────────────────────────────────
_LOG_DIR: Path = Path.home() / ".fastmoviemaker" / "logs"
_LOG_FORMAT = "[%(asctime)s] %(levelname)-8s %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES = 5 * 1024 * 1024   # 5 MB
_BACKUP_COUNT = 3
_ROOT_LOGGER_NAME = APP_NAME


def _build_file_handler() -> RotatingFileHandler:
    """로그 파일 핸들러를 생성한다 (디렉터리 자동 생성)."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = _LOG_DIR / f"{_ROOT_LOGGER_NAME.lower()}.log"
    handler = RotatingFileHandler(
        log_file,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    return handler


def _configure_root() -> None:
    """루트 로거를 최초 한 번만 설정한다."""
    root = logging.getLogger(_ROOT_LOGGER_NAME)
    if root.handlers:
        return   # 이미 설정됨

    root.setLevel(logging.DEBUG)

    # 파일 핸들러
    try:
        root.addHandler(_build_file_handler())
    except OSError:
        pass   # 파일 쓰기 불가 환경에서도 앱 동작 유지

    # 콘솔 핸들러 (개발 모드에서만)
    if "pytest" in sys.modules or __debug__:
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.WARNING)
        console.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
        root.addHandler(console)


def get_logger(name: str) -> logging.Logger:
    """모듈별 로거를 반환한다.

    Args:
        name: 모듈 이름 (보통 __name__ 전달).
    """
    _configure_root()
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{name}")


def get_log_dir() -> Path:
    """로그 파일 디렉터리 경로를 반환한다."""
    return _LOG_DIR
