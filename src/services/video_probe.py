"""Probe video metadata using ffprobe."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.services.ffmpeg_logger import log_ffmpeg_command
from src.infrastructure.ffmpeg_runner import get_ffmpeg_runner


@dataclass
class VideoInfo:
    """Metadata extracted from a video file."""

    width: int = 0
    height: int = 0
    duration_ms: int = 0
    has_audio: bool = False


def probe_video(video_path: Path | str) -> VideoInfo:
    """Probe a video file for dimensions, duration, and audio presence.

    Returns *VideoInfo* with defaults (0 / False) on any failure.
    """
    runner = get_ffmpeg_runner()
    if not runner.ffprobe_path:
        return VideoInfo()

    try:
        args = [
            "-v", "error",
            "-show_entries", "stream=codec_type,width,height",
            "-show_entries", "format=duration",
            "-of", "json",
            str(video_path),
        ]
        log_ffmpeg_command(["ffprobe"] + args)
        result = runner.run_ffprobe(args, timeout=15)

        data = json.loads(result.stdout)

        width = height = 0
        has_audio = False
        for stream in data.get("streams", []):
            codec_type = stream.get("codec_type", "")
            if codec_type == "video" and width == 0:
                width = int(stream.get("width", 0))
                height = int(stream.get("height", 0))
            elif codec_type == "audio":
                has_audio = True

        duration_ms = 0
        dur_str = data.get("format", {}).get("duration")
        if dur_str:
            duration_ms = int(float(dur_str) * 1000)

        return VideoInfo(
            width=width,
            height=height,
            duration_ms=duration_ms,
            has_audio=has_audio,
        )
    except Exception:
        return VideoInfo()
