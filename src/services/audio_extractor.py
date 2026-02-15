"""Extract audio from video files using FFmpeg."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.infrastructure.ffmpeg_runner import get_ffmpeg_runner
from src.utils.config import AUDIO_SAMPLE_RATE


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
    runner = get_ffmpeg_runner()
    if not runner.is_available():
        raise FileNotFoundError("FFmpeg not found. Please install FFmpeg.")

    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        output_path = Path(tmp.name)

    args = [
        "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", str(AUDIO_SAMPLE_RATE),
        "-ac", "1",
        str(output_path),
    ]

    result = runner.run(args)

    if result.returncode != 0:
        stderr = result.stderr[:500] if result.stderr else ""
        raise RuntimeError(f"FFmpeg failed:\n{stderr}")

    return output_path
