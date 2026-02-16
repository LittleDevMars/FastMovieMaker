"""Application configuration constants."""

from __future__ import annotations

import shutil
from pathlib import Path

APP_NAME = "FastMovieMaker"
APP_VERSION = "0.4.0"
ORG_NAME = "FastMovieMaker"

# FFmpeg
import sys
if sys.platform == "darwin":
    FFMPEG_PATH = "/opt/homebrew/bin/ffmpeg"
elif sys.platform == "win32":
    FFMPEG_PATH = r"E:\Python\Scripts\ffmpeg.exe"
else:
    FFMPEG_PATH = "ffmpeg"


def find_ffmpeg() -> str | None:
    """Return FFmpeg path (config path → PATH → bundled). Lazy import to avoid circular deps."""
    from src.utils.ffmpeg_utils import find_ffmpeg as _find
    return _find()

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

# Supported image formats
IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff"]
IMAGE_FILTER = "Image Files ({});;All Files (*)".format(
    " ".join(f"*{ext}" for ext in IMAGE_EXTENSIONS)
)

# Supported audio formats
AUDIO_EXTENSIONS = [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"]
AUDIO_FILTER = "Audio Files ({});;All Files (*)".format(
    " ".join(f"*{ext}" for ext in AUDIO_EXTENSIONS)
)

# Combined media filter (for media library import)
MEDIA_FILTER = "Media Files ({});;Video Files ({});;Image Files ({});;Audio Files ({});;Subtitle Files (*.srt *.smi);;All Files (*)".format(
    " ".join(f"*{ext}" for ext in VIDEO_EXTENSIONS + IMAGE_EXTENSIONS + AUDIO_EXTENSIONS + [".srt", ".smi"]),
    " ".join(f"*{ext}" for ext in VIDEO_EXTENSIONS),
    " ".join(f"*{ext}" for ext in IMAGE_EXTENSIONS),
    " ".join(f"*{ext}" for ext in AUDIO_EXTENSIONS),
)

# TTS settings
TTS_DEFAULT_VOICE = "ko-KR-SunHiNeural"
TTS_DEFAULT_RATE = "+0%"
TTS_DEFAULT_SPEED = 1.0  # 1.0 = normal speed
TTS_VOICES = {
    "Korean": {
        "Female": ["ko-KR-SunHiNeural"],
        "Male": ["ko-KR-InJoonNeural", "ko-KR-HyunsuMultilingualNeural"]
    },
    "English": {
        "Female": ["en-US-JennyNeural", "en-US-AriaNeural"],
        "Male": ["en-US-GuyNeural", "en-US-ChristopherNeural"]
    }
}

# TTS Engine types
class TTSEngine:
    EDGE_TTS = "edge_tts"
    ELEVENLABS = "elevenlabs"

# ElevenLabs default voices (official starter voices)
ELEVENLABS_DEFAULT_VOICES = {
    "Rachel (Female)": "21m00Tcm4TlvDq8ikWAM",
    "Bella (Female)": "EXAVITQu4vr4xnSDxMaL",
    "Antoni (Male)": "ErXwobaYiN019PkySvjV",
    "Josh (Male)": "TxGEqnHWrfWFTfGW9XjX",
    "Adam (Male)": "pNInz6obpgDQGcFmaJgB",
    "Sam (Male)": "yoZ06aMxZJJ28mfd3POQ",
}

# UI
TIMELINE_HEIGHT = 300  # Accommodates ruler + video clips + subtitles + TTS audio + video waveform + image overlays (multi-row)
SUBTITLE_FONT_SIZE = 18
SUBTITLE_OVERLAY_MARGIN_BOTTOM = 40
