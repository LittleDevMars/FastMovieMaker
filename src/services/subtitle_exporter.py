"""Export subtitle tracks to SRT format."""

from pathlib import Path

from src.models.subtitle import SubtitleTrack
from src.utils.time_utils import ms_to_srt_time


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
