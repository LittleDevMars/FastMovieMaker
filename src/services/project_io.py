"""JSON-based project save / load (.fmm.json)."""

from __future__ import annotations

import json
from pathlib import Path

from src.models.project import ProjectState
from src.models.subtitle import SubtitleSegment, SubtitleTrack


def save_project(project: ProjectState, path: Path) -> None:
    """Serialize *project* to a JSON file."""
    data = {
        "version": 1,
        "video_path": str(project.video_path) if project.video_path else None,
        "duration_ms": project.duration_ms,
        "segments": [
            {
                "start_ms": seg.start_ms,
                "end_ms": seg.end_ms,
                "text": seg.text,
            }
            for seg in project.subtitle_track
        ],
        "language": project.subtitle_track.language,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_project(path: Path) -> ProjectState:
    """Deserialize a project from a JSON file."""
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    project = ProjectState()
    if data.get("video_path"):
        project.video_path = Path(data["video_path"])
    project.duration_ms = data.get("duration_ms", 0)
    track = SubtitleTrack(language=data.get("language", ""))
    for seg_data in data.get("segments", []):
        track.add_segment(
            SubtitleSegment(
                start_ms=seg_data["start_ms"],
                end_ms=seg_data["end_ms"],
                text=seg_data["text"],
            )
        )
    project.subtitle_track = track
    return project
