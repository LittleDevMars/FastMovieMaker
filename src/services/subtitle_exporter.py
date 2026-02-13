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

def _color_to_ass(hex_color: str, alpha: int = 0) -> str:
    """Convert hex color (#RRGGBB) to ASS color (&HBBGGRR&)."""
    if not hex_color or not hex_color.startswith("#"):
        return "&H00FFFFFF"
    
    # Strip #
    hex_color = hex_color.lstrip("#")
    
    if len(hex_color) == 6:
        r = hex_color[0:2]
        g = hex_color[2:4]
        b = hex_color[4:6]
        # ASS is BGR
        return f"&H{alpha:02X}{b}{g}{r}"
    return "&H00FFFFFF"


def _ms_to_ass_time(ms: int) -> str:
    """Convert milliseconds to ASS time 'H:MM:SS.cs'."""
    if ms < 0:
        ms = 0
    hours = ms // 3_600_000
    remainder = ms % 3_600_000
    minutes = remainder // 60_000
    remainder = remainder % 60_000
    seconds = remainder // 1000
    centiseconds = (remainder % 1000) // 10
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def export_ass(track: SubtitleTrack, output_path: Path, video_width: int = 1920, video_height: int = 1080) -> None:
    """Export a SubtitleTrack to an ASS file.
    
    Args:
        track: The subtitle track to export.
        output_path: Path to write the ASS file.
        video_width: Width of the video (used for positioning).
        video_height: Height of the video (used for positioning).
    """
    lines = []
    
    # Script Info
    lines.append("[Script Info]")
    lines.append("ScriptType: v4.00+")
    lines.append("PlayResX: " + str(video_width))
    lines.append("PlayResY: " + str(video_height))
    lines.append("WrapStyle: 0")  # 0: Smart wrapping, top line is wider
    lines.append("")
    
    # Styles
    lines.append("[V4+ Styles]")
    lines.append("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
    
    # Default Style (fallback)
    # Alignment 2 is Bottom-Center in ASS
    lines.append("Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1")
    
    # Generate unique styles present in the track
    # Map (style properties) -> Style Name
    style_map = {}
    style_counter = 1
    
    for seg in track.segments:
        if seg.style:
            # Create a hashable representation of the style
            s = seg.style
            key = (s.font_family, s.font_size, s.font_bold, s.font_italic, s.font_color, 
                   s.outline_color, s.outline_width, s.bg_color, s.position, s.margin_bottom, s.custom_x, s.custom_y)
            
            if key not in style_map:
                name = f"Style{style_counter}"
                style_map[key] = name
                style_counter += 1
                
                # Convert properties to ASS
                # Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
                
                bold = "-1" if s.font_bold else "0"
                italic = "-1" if s.font_italic else "0"
                
                primary_color = _color_to_ass(s.font_color, 0)
                outline_color = _color_to_ass(s.outline_color, 0)
                back_color = "&H00000000" # Transparent background for now
                
                # Alignment mapping
                # 1: Left, 2: Center, 3: Right
                # 4: Top-Left, 5: Top-Center, 6: Top-Right
                # 7: Top-Left (legacy?), usually 1/2/3 is bottom, 7/8/9 is top
                # ASS Alignment numpad based: 1=SW, 2=S, 3=SE, 4=W, 5=C, 6=E, 7=NW, 8=N, 9=NE
                
                alignment = 2 # Default bottom-center
                
                # Logic to map 'bottom-center' etc.
                if s.position == 'bottom-left': alignment = 1
                elif s.position == 'bottom-center': alignment = 2
                elif s.position == 'bottom-right': alignment = 3
                elif s.position == 'top-left': alignment = 7
                elif s.position == 'top-center': alignment = 8
                elif s.position == 'top-right': alignment = 9
                
                # Margins
                margin_v = s.margin_bottom
                margin_l = 20
                margin_r = 20
                
                # Custom positioning (override alignment if custom)
                # Note: ASS uses margins for alignment-relative positioning.
                # True absolute positioning requires {\pos(x,y)} tag in the event, not style.
                # But style defines default.
                
                lines.append(f"Style: {name},{s.font_family},{s.font_size},{primary_color},&H000000FF,{outline_color},{back_color},{bold},{italic},0,0,100,100,0,0,1,{s.outline_width},0,{alignment},{margin_l},{margin_r},{margin_v},1")

    lines.append("")
    
    # Events
    lines.append("[Events]")
    lines.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")
    
    for seg in track.segments:
        start = _ms_to_ass_time(seg.start_ms)
        end = _ms_to_ass_time(seg.end_ms)
        
        style_name = "Default"
        if seg.style:
            s = seg.style
            key = (s.font_family, s.font_size, s.font_bold, s.font_italic, s.font_color, 
                   s.outline_color, s.outline_width, s.bg_color, s.position, s.margin_bottom, s.custom_x, s.custom_y)
            style_name = style_map.get(key, "Default")
            
        text = seg.text.replace("\n", "\\N")
        
        # Apply custom positioning tag if needed
        if seg.style and seg.style.custom_x is not None and seg.style.custom_y is not None:
             text = f"{{\\pos({seg.style.custom_x},{seg.style.custom_y})}}{text}"
        
        lines.append(f"Dialogue: 0,{start},{end},{style_name},,0,0,0,,{text}")
        
    output_path.write_text("\n".join(lines), encoding="utf-8")
