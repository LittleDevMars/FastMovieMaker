"""Project state model."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.models.subtitle import SubtitleTrack


@dataclass
class ProjectState:
    """Holds the current state of the editing session."""

    video_path: Path | None = None
    subtitle_track: SubtitleTrack = field(default_factory=SubtitleTrack)
    duration_ms: int = 0

    @property
    def has_video(self) -> bool:
        return self.video_path is not None

    @property
    def has_subtitles(self) -> bool:
        return len(self.subtitle_track) > 0

    def reset(self) -> None:
        self.video_path = None
        self.subtitle_track = SubtitleTrack()
        self.duration_ms = 0
