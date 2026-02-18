"""Utility for logging FFmpeg output to a file."""

import logging
from pathlib import Path

def get_ffmpeg_log_path() -> Path:
    """Return the path to the FFmpeg log file."""
    log_dir = Path.home() / ".fastmoviemaker" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "ffmpeg.log"

# Setup a specific logger for FFmpeg
_logger = logging.getLogger("ffmpeg_output")
_logger.setLevel(logging.DEBUG)
_logger.propagate = False

# Add file handler if not already present
if not _logger.handlers:
    _fh = logging.FileHandler(get_ffmpeg_log_path(), encoding="utf-8")
    _formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    _fh.setFormatter(_formatter)
    _logger.addHandler(_fh)

def log_ffmpeg_command(args: list[str]) -> None:
    """Log the FFmpeg command being executed."""
    _logger.info(f"Executing: {' '.join(args)}")

def log_ffmpeg_line(line: str) -> None:
    """Log a single line of FFmpeg output."""
    _logger.debug(line.rstrip())