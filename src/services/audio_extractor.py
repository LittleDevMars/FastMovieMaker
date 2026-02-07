"""Extract audio from video files using FFmpeg."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from src.utils.config import AUDIO_SAMPLE_RATE, find_ffmpeg


def extract_audio_to_wav(video_path: Path, output_path: Path | None = None) -> Path:
    """Extract audio from video as 16kHz mono WAV for Whisper.

    Args:
        video_path: Path to the source video file.
        output_path: Optional output path. If None, creates a temp file.

    Returns:
        Path to the extracted WAV file.

    Raises:
        FileNotFoundError: If FFmpeg is not found.
        RuntimeError: If FFmpeg extraction fails.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise FileNotFoundError("FFmpeg not found. Please install FFmpeg.")

    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        output_path = Path(tmp.name)

    cmd = [
        ffmpeg,
        "-y",                   # overwrite
        "-i", str(video_path),
        "-vn",                  # no video
        "-acodec", "pcm_s16le",
        "-ar", str(AUDIO_SAMPLE_RATE),
        "-ac", "1",             # mono
        str(output_path),
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed:\n{result.stderr[:500]}")

    return output_path
