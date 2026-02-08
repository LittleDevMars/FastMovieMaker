"""FFmpeg utilities for finding ffmpeg and ffprobe executables."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def find_ffmpeg() -> str | None:
    """
    Find ffmpeg executable.

    Search order:
    1. User-configured path (config.FFMPEG_PATH)
    2. System PATH (ffmpeg command)
    3. Bundled FFmpeg (imageio-ffmpeg) - auto-download if needed

    Returns:
        Path to ffmpeg or None if not found
    """
    # 1. Try user-configured path
    from .config import FFMPEG_PATH
    if Path(FFMPEG_PATH).is_file():
        return FFMPEG_PATH

    # 2. Try system PATH
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    # 3. Try bundled FFmpeg (auto-download)
    try:
        from .ffmpeg_bundled import get_bundled_ffmpeg
        return get_bundled_ffmpeg()
    except Exception:
        # Bundled FFmpeg not available
        pass

    return None


def find_ffprobe() -> str | None:
    """
    Find ffprobe executable (usually alongside ffmpeg).

    Returns:
        Path to ffprobe or None if not found
    """
    # Try ffprobe directly in PATH
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

    # Try bundled version
    try:
        from .ffmpeg_bundled import get_bundled_ffprobe
        bundled = get_bundled_ffprobe()
        if bundled:
            return bundled
    except Exception:
        pass

    return None
