"""JSON-based project save / load (.fmm.json)."""

from __future__ import annotations

import json
from pathlib import Path

from src.models.project import ProjectState
from src.models.style import SubtitleStyle
from src.models.subtitle import SubtitleSegment, SubtitleTrack

PROJECT_VERSION = 2


def _style_to_dict(style: SubtitleStyle) -> dict:
    return {
        "font_family": style.font_family,
        "font_size": style.font_size,
        "font_bold": style.font_bold,
        "font_italic": style.font_italic,
        "font_color": style.font_color,
        "outline_color": style.outline_color,
        "outline_width": style.outline_width,
        "bg_color": style.bg_color,
        "position": style.position,
        "margin_bottom": style.margin_bottom,
    }


def _dict_to_style(d: dict) -> SubtitleStyle:
    return SubtitleStyle(
        font_family=d.get("font_family", "Arial"),
        font_size=d.get("font_size", 18),
        font_bold=d.get("font_bold", True),
        font_italic=d.get("font_italic", False),
        font_color=d.get("font_color", "#FFFFFF"),
        outline_color=d.get("outline_color", "#000000"),
        outline_width=d.get("outline_width", 1),
        bg_color=d.get("bg_color", ""),
        position=d.get("position", "bottom-center"),
        margin_bottom=d.get("margin_bottom", 40),
    )


def _segment_to_dict(seg: SubtitleSegment) -> dict:
    d = {
        "start_ms": seg.start_ms,
        "end_ms": seg.end_ms,
        "text": seg.text,
    }
    if seg.style is not None:
        d["style"] = _style_to_dict(seg.style)
    return d


def _dict_to_segment(d: dict) -> SubtitleSegment:
    style = _dict_to_style(d["style"]) if "style" in d else None
    return SubtitleSegment(
        start_ms=d["start_ms"],
        end_ms=d["end_ms"],
        text=d["text"],
        style=style,
    )


def save_project(project: ProjectState, path: Path) -> None:
    """Serialize *project* to a JSON file (v2 format)."""
    tracks_data = []
    for track in project.subtitle_tracks:
        tracks_data.append({
            "name": track.name,
            "language": track.language,
            "segments": [_segment_to_dict(seg) for seg in track],
        })

    data = {
        "version": PROJECT_VERSION,
        "video_path": str(project.video_path) if project.video_path else None,
        "duration_ms": project.duration_ms,
        "default_style": _style_to_dict(project.default_style),
        "active_track_index": project.active_track_index,
        "tracks": tracks_data,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_project(path: Path) -> ProjectState:
    """Deserialize a project from a JSON file (v1 or v2)."""
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    version = data.get("version", 1)

    project = ProjectState()
    if data.get("video_path"):
        project.video_path = Path(data["video_path"])
    project.duration_ms = data.get("duration_ms", 0)

    if version >= 2:
        # v2 format
        project.default_style = _dict_to_style(data.get("default_style", {}))
        project.active_track_index = data.get("active_track_index", 0)
        tracks = []
        for track_data in data.get("tracks", []):
            track = SubtitleTrack(
                language=track_data.get("language", ""),
                name=track_data.get("name", ""),
            )
            for seg_data in track_data.get("segments", []):
                track.add_segment(_dict_to_segment(seg_data))
            tracks.append(track)
        if tracks:
            project.subtitle_tracks = tracks
        else:
            project.subtitle_tracks = [SubtitleTrack(name="Default")]
    else:
        # v1 migration: single track, no style
        track = SubtitleTrack(
            language=data.get("language", ""),
            name="Default",
        )
        for seg_data in data.get("segments", []):
            track.add_segment(SubtitleSegment(
                start_ms=seg_data["start_ms"],
                end_ms=seg_data["end_ms"],
                text=seg_data["text"],
            ))
        project.subtitle_tracks = [track]
        project.active_track_index = 0
        project.default_style = SubtitleStyle()

    return project
