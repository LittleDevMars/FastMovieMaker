"""FFmpeg utilities for finding ffmpeg and ffprobe executables."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def find_ffmpeg() -> str | None:
    """Find ffmpeg executable."""
    from .config import FFMPEG_PATH
    if Path(FFMPEG_PATH).is_file():
        return FFMPEG_PATH
    return shutil.which("ffmpeg")


def find_ffprobe() -> str | None:
    """Find ffprobe executable (usually alongside ffmpeg)."""
    # Try ffprobe directly
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        return ffprobe

    # Try to find it alongside ffmpeg
    ffmpeg_path = find_ffmpeg()
    if ffmpeg_path:
        ffmpeg_dir = Path(ffmpeg_path).parent
        ffprobe_path = ffmpeg_dir / ("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
        if ffprobe_path.is_file():
            return str(ffprobe_path)

    return None
