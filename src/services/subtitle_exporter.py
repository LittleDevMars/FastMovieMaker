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


def import_smi(path: Path) -> SubtitleTrack:
    """Read an SMI (SAMI) file and return a SubtitleTrack.
    
    Handles standard SAMI format with <SYNC Start=...> tags.
    Converts <BR> to newlines and strips HTML tags.
    """
    try:
        # Try different encodings commonly used in Korean SMI files
        content = ""
        for encoding in ["utf-8", "cp949", "euc-kr", "utf-16"]:
            try:
                content = path.read_text(encoding=encoding)
                break
            except UnicodeDecodeError:
                continue
        
        if not content:
            raise ValueError("Could not decode SMI file")

        track = SubtitleTrack()
        
        # Regex to find SYNC tags and content
        # Matches: <SYNC Start=1234>Content...
        # Case insensitive flag is important
        sync_pattern = re.compile(r"<SYNC\s+Start\s*=\s*(\d+)>(.*?)(?=<SYNC|$)", re.IGNORECASE | re.DOTALL)
        
        matches = list(sync_pattern.finditer(content))
        
        for i, m in enumerate(matches):
            start_ms = int(m.group(1))
            raw_text = m.group(2).strip()
            
            # If there's a next sync, use that as end time (or +duration logic)
            # For now, default to next sync's start, or +3000ms if last
            if i < len(matches) - 1:
                next_start = int(matches[i+1].group(1))
                end_ms = next_start
            else:
                end_ms = start_ms + 3000
                
            # Skip blank "vacant" lines often found in SMI
            if "&nbsp;" in raw_text and len(raw_text) < 10:
                continue
                
            # Clean HTML tags
            # 1. Replace <BR> with \n
            text = re.sub(r"<BR\s*/?>", "\n", raw_text, flags=re.IGNORECASE)
            # 2. Remove other tags like <P>, <FONT>, <B>, etc.
            text = re.sub(r"<[^>]+>", "", text)
            # 3. Unescape HTML entities
            text = text.replace("&nbsp;", " ").replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
            
            text = text.strip()
            
            # Simple duration sanity check (e.g. if next sync is way too far, cap at 5s)
            if end_ms - start_ms > 5000:
                end_ms = start_ms + 5000
                
            if text:
                track.add_segment(SubtitleSegment(start_ms, end_ms, text))
                
        return track
    except Exception as e:
        print(f"Error parsing SMI: {e}")
        return SubtitleTrack()
