"""Export video with hard-burned subtitles via FFmpeg."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from src.models.subtitle import SubtitleTrack
from src.services.subtitle_exporter import export_srt
from src.utils.config import find_ffmpeg


def export_video(
    video_path: Path,
    track: SubtitleTrack,
    output_path: Path,
    on_progress: callable | None = None,
) -> None:
    """Burn subtitles into video using FFmpeg's subtitles filter.

    Args:
        video_path: Source video file.
        track: Subtitle track to burn.
        output_path: Destination video file.
        on_progress: Optional callback(duration_sec, current_sec) for progress.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found")

    # Write a temporary SRT file
    tmp_srt = Path(tempfile.mktemp(suffix=".srt"))
    try:
        export_srt(track, tmp_srt)

        # Escape path for FFmpeg subtitles filter
        srt_str = str(tmp_srt).replace("\\", "/")
        if sys.platform == "win32":
            srt_str = srt_str.replace(":", "\\:")
            srt_filter = f"subtitles='{srt_str}'"
        else:
            # On macOS/Linux, escape colons and use without quotes
            srt_str = srt_str.replace(":", "\\:")
            srt_filter = f"subtitles={srt_str}"

        cmd = [
            ffmpeg,
            "-i", str(video_path),
            "-vf", srt_filter,
            "-c:a", "copy",
            "-y",
            "-progress", "pipe:1",
            str(output_path),
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        # Parse -progress output for duration tracking
        total_duration = _get_video_duration(ffmpeg, video_path)

        if process.stdout:
            for line in process.stdout:
                line = line.strip()
                if line.startswith("out_time_us="):
                    try:
                        us = int(line.split("=")[1])
                        current_sec = us / 1_000_000
                        if on_progress and total_duration > 0:
                            on_progress(total_duration, current_sec)
                    except (ValueError, IndexError):
                        pass

        process.wait()
        if process.returncode != 0:
            stderr = process.stderr.read() if process.stderr else ""
            raise RuntimeError(f"FFmpeg failed (code {process.returncode}): {stderr[:500]}")

    finally:
        tmp_srt.unlink(missing_ok=True)


def _get_video_duration(ffmpeg: str, video_path: Path) -> float:
    """Get video duration in seconds using ffprobe or FFmpeg."""
    ffprobe = str(Path(ffmpeg).parent / "ffprobe.exe")
    if not Path(ffprobe).is_file():
        ffprobe = str(Path(ffmpeg).parent / "ffprobe")
    if not Path(ffprobe).is_file():
        return 0.0

    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0
