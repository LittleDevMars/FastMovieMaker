"""Project state model."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.models.image_overlay import ImageOverlayTrack
from src.models.style import SubtitleStyle
from src.models.subtitle import SubtitleTrack
from src.models.video_clip import VideoClipTrack


@dataclass
class ProjectState:
    """Holds the current state of the editing session."""

    video_path: Path | None = None
    subtitle_tracks: list[SubtitleTrack] = field(default_factory=lambda: [SubtitleTrack(name="Default")])
    active_track_index: int = 0
    duration_ms: int = 0
    default_style: SubtitleStyle = field(default_factory=SubtitleStyle)
    video_has_audio: bool = False  # Whether video file has audio track
    image_overlay_track: ImageOverlayTrack = field(default_factory=ImageOverlayTrack)
    video_clip_track: VideoClipTrack | None = None  # None = no clipping (legacy/full video)

    @property
    def subtitle_track(self) -> SubtitleTrack:
        """Return the active subtitle track (backward-compatible)."""
        if 0 <= self.active_track_index < len(self.subtitle_tracks):
            return self.subtitle_tracks[self.active_track_index]
        return self.subtitle_tracks[0]

    @subtitle_track.setter
    def subtitle_track(self, track: SubtitleTrack) -> None:
        """Replace the active track (backward-compatible)."""
        if 0 <= self.active_track_index < len(self.subtitle_tracks):
            self.subtitle_tracks[self.active_track_index] = track
        else:
            self.subtitle_tracks = [track]
            self.active_track_index = 0

    @property
    def has_video(self) -> bool:
        return self.video_path is not None

    @property
    def has_subtitles(self) -> bool:
        return len(self.subtitle_track) > 0

    def reset(self) -> None:
        self.video_path = None
        self.subtitle_tracks = [SubtitleTrack(name="Default")]
        self.active_track_index = 0
        self.duration_ms = 0
        self.default_style = SubtitleStyle()
        self.image_overlay_track = ImageOverlayTrack()
        self.video_clip_track = None
