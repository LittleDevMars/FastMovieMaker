"""Export / import subtitle tracks in SRT format."""

from __future__ import annotations

import re
from pathlib import Path

from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.utils.time_utils import ms_to_srt_time, srt_time_to_ms


def export_srt(track: SubtitleTrack, output_path: Path) -> None:
    """Export a SubtitleTrack to an SRT file.

    Args:
        track: The subtitle track to export.
        output_path: Path to write the SRT file.
    """
    lines: list[str] = []
    for i, seg in enumerate(track, start=1):
        lines.append(str(i))
        lines.append(f"{ms_to_srt_time(seg.start_ms)} --> {ms_to_srt_time(seg.end_ms)}")
        lines.append(seg.text)
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


_TIME_RE = re.compile(
    r"(\d{1,2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{3})"
)


def import_srt(path: Path) -> SubtitleTrack:
    """Read an SRT file and return a SubtitleTrack."""
    text = path.read_text(encoding="utf-8-sig")
    track = SubtitleTrack()
    blocks = re.split(r"\n\s*\n", text.strip())
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue
        m = _TIME_RE.search(lines[1] if len(lines) > 1 else lines[0])
        if not m:
            continue
        start = srt_time_to_ms(m.group(1))
        end = srt_time_to_ms(m.group(2))
        content = "\n".join(lines[2:]).strip()
        if content:
            track.add_segment(SubtitleSegment(start, end, content))
    return track
