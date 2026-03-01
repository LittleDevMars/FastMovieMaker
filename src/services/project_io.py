"""JSON-based project save / load (.fmm.json)."""

from __future__ import annotations

import json
from pathlib import Path

from src.models.image_overlay import ImageOverlay, ImageOverlayTrack
from src.models.project import ProjectState
from src.models.style import SubtitleStyle
from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.models.video_clip import VideoClip, VideoClipTrack
from src.models.text_overlay import TextOverlay, TextOverlayTrack

PROJECT_VERSION = 8


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
        "custom_x": style.custom_x,
        "custom_y": style.custom_y,
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
        custom_x=d.get("custom_x"),
        custom_y=d.get("custom_y"),
    )


def _segment_to_dict(seg: SubtitleSegment) -> dict:
    d = {
        "start_ms": seg.start_ms,
        "end_ms": seg.end_ms,
        "text": seg.text,
    }
    if seg.style is not None:
        d["style"] = _style_to_dict(seg.style)
    if seg.audio_file is not None:
        d["audio_file"] = seg.audio_file
    if seg.volume != 1.0:
        d["volume"] = seg.volume
    if seg.voice:
        d["voice"] = seg.voice
    if seg.speed is not None:
        d["speed"] = seg.speed
    if seg.animation is not None:
        a = seg.animation
        d["animation"] = {
            "in_effect": a.in_effect,
            "out_effect": a.out_effect,
            "in_duration_ms": a.in_duration_ms,
            "out_duration_ms": a.out_duration_ms,
            "slide_offset_px": a.slide_offset_px,
        }
    return d


def _dict_to_segment(d: dict) -> SubtitleSegment:
    from src.models.subtitle_animation import SubtitleAnimation
    style = _dict_to_style(d["style"]) if "style" in d else None
    anim_data = d.get("animation")
    animation = SubtitleAnimation(**anim_data) if anim_data else None
    return SubtitleSegment(
        start_ms=d["start_ms"],
        end_ms=d["end_ms"],
        text=d["text"],
        style=style,
        audio_file=d.get("audio_file"),
        volume=d.get("volume", 1.0),
        voice=d.get("voice"),
        speed=d.get("speed"),
        animation=animation,
    )


def save_project(project: ProjectState, path: Path) -> None:
    """Serialize *project* to a JSON file (v4 format)."""
    tracks_data = []
    for track in project.subtitle_tracks:
        tracks_data.append({
            "name": track.name,
            "language": track.language,
            "audio_path": track.audio_path,
            "audio_start_ms": track.audio_start_ms,
            "audio_duration_ms": track.audio_duration_ms,
            "locked": track.locked,
            "muted": track.muted,
            "hidden": track.hidden,
            "segments": [_segment_to_dict(seg) for seg in track],
        })

    # Image overlays
    image_overlays_data = {
        "locked": project.image_overlay_track.locked,
        "hidden": project.image_overlay_track.hidden,
        "items": [ov.to_dict() for ov in project.image_overlay_track]
    }

    # Video tracks (v6)
    video_tracks_data = []
    for vt in project.video_tracks:
        video_tracks_data.append({
            "locked": vt.locked,
            "muted": vt.muted,
            "hidden": vt.hidden,
            "name": vt.name,
            "items": [c.to_dict() for c in vt.clips]
        })

    data = {
        "version": PROJECT_VERSION,
        "video_path": str(project.video_path) if project.video_path else None,
        "duration_ms": project.duration_ms,
        "default_style": _style_to_dict(project.default_style),
        "active_track_index": project.active_track_index,
        "tracks": tracks_data,
        "image_overlays": image_overlays_data,
        "video_tracks": video_tracks_data,
        "video_clips": video_tracks_data[0] if video_tracks_data else None,
        "text_overlays": {
            "locked": project.text_overlay_track.locked,
            "hidden": project.text_overlay_track.hidden,
            "items": [ov.to_dict() for ov in project.text_overlay_track]
        }
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_project(path: Path) -> ProjectState:
    """Deserialize a project from a JSON file (v1-v4)."""
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
                audio_path=track_data.get("audio_path", ""),
                audio_start_ms=track_data.get("audio_start_ms", 0),
                audio_duration_ms=track_data.get("audio_duration_ms", 0),
                locked=track_data.get("locked", False),
                muted=track_data.get("muted", False),
                hidden=track_data.get("hidden", False),
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

    # Image overlays (backward-compatible: key may not exist)
    io_track = ImageOverlayTrack()
    io_data = data.get("image_overlays", [])
    if isinstance(io_data, dict):
        # v5 format
        io_track.locked = io_data.get("locked", False)
        io_track.hidden = io_data.get("hidden", False)
        for ov_data in io_data.get("items", []):
            io_track.add_overlay(ImageOverlay.from_dict(ov_data))
    else:
        # v4 and below
        for ov_data in io_data:
            io_track.add_overlay(ImageOverlay.from_dict(ov_data))
    project.image_overlay_track = io_track

    # Video tracks (v6, with backward compatibility for v3-v5)
    video_tracks = []
    if version >= 6:
        for vt_data in data.get("video_tracks", []):
            vt = VideoClipTrack()
            vt.locked = vt_data.get("locked", False)
            vt.muted = vt_data.get("muted", False)
            vt.hidden = vt_data.get("hidden", False)
            vt.name = vt_data.get("name", "")
            vt.clips = [VideoClip.from_dict(c) for c in vt_data.get("items", [])]
            video_tracks.append(vt)
    else:
        video_clips_data = data.get("video_clips")
        if video_clips_data is not None:
            vt = VideoClipTrack()
            if isinstance(video_clips_data, dict):
                vt.locked = video_clips_data.get("locked", False)
                vt.muted = video_clips_data.get("muted", False)
                vt.hidden = video_clips_data.get("hidden", False)
                vt.clips = [VideoClip.from_dict(c) for c in video_clips_data.get("items", [])]
            else:
                vt.clips = [VideoClip.from_dict(c) for c in video_clips_data]
            video_tracks.append(vt)

    if video_tracks:
        project.video_tracks = video_tracks
    else:
        project.video_tracks = [VideoClipTrack()]

    # Text overlays (v7)
    to_track = TextOverlayTrack()
    to_data = data.get("text_overlays")
    if isinstance(to_data, dict):
        to_track.locked = to_data.get("locked", False)
        to_track.hidden = to_data.get("hidden", False)
        for ov_data in to_data.get("items", []):
            to_track.add_overlay(TextOverlay.from_dict(ov_data))
    project.text_overlay_track = to_track

    return project
