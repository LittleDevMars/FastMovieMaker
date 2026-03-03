"""Utility for logging FFmpeg output to a file."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path


def get_ffmpeg_log_path() -> Path:
    """Return a writable path for the FFmpeg log file."""
    candidates = [
        Path.home() / ".fastmoviemaker" / "logs",
        Path.cwd() / ".fastmoviemaker" / "logs",
        Path(tempfile.gettempdir()) / "fastmoviemaker" / "logs",
    ]
    for log_dir in candidates:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "ffmpeg.log"
            with log_path.open("a", encoding="utf-8"):
                pass
            return log_path
        except OSError:
            continue
    raise OSError("No writable directory available for FFmpeg logs.")


def _setup_logger() -> logging.Logger:
    """Create/configure logger without crashing app on I/O errors."""
    logger = logging.getLogger("ffmpeg_output")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    if logger.handlers:
        return logger

    try:
        handler: logging.Handler = logging.FileHandler(
            get_ffmpeg_log_path(), encoding="utf-8"
        )
    except OSError:
        # Keep app/tests running even when file logging is unavailable.
        handler = logging.NullHandler()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


_logger = _setup_logger()

def log_ffmpeg_command(args: list[str]) -> None:
    """Log the FFmpeg command being executed."""
    _logger.info(f"Executing: {' '.join(args)}")

def log_ffmpeg_line(line: str) -> None:
    """Log a single line of FFmpeg output."""
    _logger.debug(line.rstrip())
