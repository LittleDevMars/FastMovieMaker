"""Application configuration constants."""

from __future__ import annotations

import shutil
from pathlib import Path

APP_NAME = "FastMovieMaker"
APP_VERSION = "0.1.0"
ORG_NAME = "FastMovieMaker"

# FFmpeg
FFMPEG_PATH = r"E:\Python\Scripts\ffmpeg.exe"

def find_ffmpeg() -> str | None:
    """Return FFmpeg path if available."""
    if Path(FFMPEG_PATH).is_file():
        return FFMPEG_PATH
    return shutil.which("ffmpeg")

# Audio extraction settings
AUDIO_SAMPLE_RATE = 16000  # Whisper expects 16kHz

# Whisper
WHISPER_MODELS = ["tiny", "base", "small", "medium", "large"]
WHISPER_DEFAULT_MODEL = "medium"
WHISPER_DEFAULT_LANGUAGE = "ko"

# Supported video formats
VIDEO_EXTENSIONS = [".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv"]
VIDEO_FILTER = "Video Files ({});;All Files (*)".format(
    " ".join(f"*{ext}" for ext in VIDEO_EXTENSIONS)
)

# UI
TIMELINE_HEIGHT = 120
SUBTITLE_FONT_SIZE = 18
SUBTITLE_OVERLAY_MARGIN_BOTTOM = 40
