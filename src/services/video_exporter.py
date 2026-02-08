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
    audio_path: Path | None = None,
    scale_width: int = 0,
    scale_height: int = 0,
    codec: str = "h264",
) -> None:
    """Burn subtitles into video using FFmpeg's subtitles filter.

    Args:
        video_path: Source video file.
        track: Subtitle track to burn.
        output_path: Destination video file.
        on_progress: Optional callback(duration_sec, current_sec) for progress.
        audio_path: Optional path to replacement audio file (e.g. TTS mixed audio).
                    When provided, replaces the original audio with this file.
        scale_width: Target width in pixels (0 = keep original).
        scale_height: Target height in pixels (0 = keep original).
        codec: Video codec - "h264" or "hevc" (default "h264").
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

        # Determine encoder based on output container
        from src.utils.hw_accel import get_hw_encoder

        if output_path.suffix.lower() == ".webm":
            video_encoder = "libvpx-vp9"
            encoder_flags = ["-crf", "30", "-b:v", "0"]
            audio_codec_flags = ["-c:a", "libvorbis", "-b:a", "128k"]
        else:
            video_encoder, encoder_flags = get_hw_encoder(codec)
            audio_codec_flags = ["-c:a", "aac", "-b:a", "192k"]

        # Build video filter chain
        vf_parts: list[str] = []
        if scale_width > 0 and scale_height > 0:
            vf_parts.append(
                f"scale={scale_width}:{scale_height}"
                f":force_original_aspect_ratio=decrease,"
                f"pad={scale_width}:{scale_height}:(ow-iw)/2:(oh-ih)/2"
            )
        vf_parts.append(srt_filter)
        vf_string = ",".join(vf_parts)

        if audio_path and audio_path.exists():
            # Use replacement audio: video from input 0, audio from input 1
            cmd = [
                ffmpeg,
                "-i", str(video_path),
                "-i", str(audio_path),
                "-vf", vf_string,
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", video_encoder,
                *encoder_flags,
                *audio_codec_flags,
                "-y",
                "-progress", "pipe:1",
                str(output_path),
            ]
        else:
            cmd = [
                ffmpeg,
                "-i", str(video_path),
                "-vf", vf_string,
                "-c:v", video_encoder,
                *encoder_flags,
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
