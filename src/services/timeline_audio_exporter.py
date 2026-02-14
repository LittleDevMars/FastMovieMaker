"""Export audio from edited timeline for Whisper transcription."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

from src.models.video_clip import VideoClipTrack
from src.utils.config import AUDIO_SAMPLE_RATE, find_ffmpeg


def export_timeline_audio(
    clip_track: VideoClipTrack,
    output_path: Path | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> Path:
    """Export audio from edited timeline as WAV for Whisper.

    This function takes the current timeline's clip configuration and
    exports only the audio track, applying all edits (cuts, speed, volume).

    Args:
        clip_track: The video clip track to export audio from.
        output_path: Optional output path. If None, creates a temp file.
        on_progress: Optional progress callback (0-100).

    Returns:
        Path to the exported 16kHz mono WAV file.

    Raises:
        FileNotFoundError: If FFmpeg is not found.
        RuntimeError: If FFmpeg export fails.
        ValueError: If clip_track is empty or invalid.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise FileNotFoundError("FFmpeg not found. Please install FFmpeg.")

    if not clip_track or len(clip_track.clips) == 0:
        raise ValueError("Clip track is empty. Cannot export audio.")

    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        output_path = Path(tmp.name)

    clips = clip_track.clips

    # Build input file list and source index map
    source_paths = []
    source_index_map = {}
    for clip in clips:
        src = str(clip.source_path) if clip.source_path else None
        if src and src not in source_index_map:
            source_index_map[src] = len(source_paths)
            source_paths.append(src)

    # If all clips use the same source (or no source_path), use single-source mode
    if len(source_paths) <= 1:
        source_index_map = None
        if source_paths:
            primary_source = source_paths[0]
        else:
            raise ValueError("No valid source paths found in clips.")
    else:
        primary_source = None

    # Build FFmpeg command
    cmd = [ffmpeg, "-y"]

    # Add inputs
    if source_index_map:
        for src in source_paths:
            cmd.extend(["-i", src])
    else:
        cmd.extend(["-i", primary_source])

    # Build audio filter chain
    filter_parts = _build_audio_concat_filter(clips, source_index_map)
    filter_complex = ";".join(filter_parts)

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[outa]",
        "-acodec", "pcm_s16le",
        "-ar", str(AUDIO_SAMPLE_RATE),
        "-ac", "1",  # mono
        str(output_path),
    ])

    # Run FFmpeg
    kwargs = dict(capture_output=True, text=True)
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    if on_progress:
        on_progress(0)

    result = subprocess.run(cmd, **kwargs)

    if on_progress:
        on_progress(100)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio export failed:\n{result.stderr[:500]}")

    return output_path


def _build_audio_concat_filter(
    clips: list,
    source_index_map: dict | None = None,
) -> list[str]:
    """Build FFmpeg audio-only concat filter for timeline clips.

    Args:
        clips: List of VideoClip objects.
        source_index_map: Maps source_path → FFmpeg input index.
            When None, all clips use input 0.

    Returns:
        List of filter strings for -filter_complex.
    """
    parts: list[str] = []
    a_labels = []

    for i, clip in enumerate(clips):
        if source_index_map is not None:
            idx = source_index_map.get(str(clip.source_path) if clip.source_path else None, 0)
        else:
            idx = 0

        start_s = clip.source_in_ms / 1000.0
        end_s = clip.source_out_ms / 1000.0
        al = f"a{i}"

        a_filter = f"[{idx}:a]atrim=start={start_s:.3f}:end={end_s:.3f},asetpts=PTS-STARTPTS"

        # Apply speed adjustment
        if hasattr(clip, "speed") and clip.speed != 1.0:
            speed = clip.speed
            # FFmpeg atempo only supports 0.5-2.0, so chain multiple if needed
            while speed > 2.0:
                a_filter += ",atempo=2.0"
                speed /= 2.0
            while speed < 0.5:
                a_filter += ",atempo=0.5"
                speed /= 0.5
            a_filter += f",atempo={speed:.3f}"

        # Apply volume adjustment
        if hasattr(clip, "volume") and clip.volume != 1.0:
            a_filter += f",volume={clip.volume:.3f}"

        a_filter += f"[{al}]"
        parts.append(a_filter)
        a_labels.append(al)

    # Concatenate all audio segments
    if len(clips) == 1:
        parts.append(f"[{a_labels[0]}]acopy[outa]")
    else:
        concat_inputs = "".join(f"[{label}]" for label in a_labels)
        parts.append(f"{concat_inputs}concat=n={len(clips)}:v=0:a=1[outa]")

    return parts
