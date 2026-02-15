"""Project state model."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.models.image_overlay import ImageOverlayTrack
from src.models.style import SubtitleStyle
from src.models.subtitle import SubtitleTrack
from src.models.video_clip import VideoClipTrack
from src.models.text_overlay import TextOverlayTrack
from src.models.audio import AudioTrack


@dataclass(slots=True)
class ProjectState:
    """Holds the current state of the editing session."""

    video_path: Path | None = None
    subtitle_tracks: list[SubtitleTrack] = field(default_factory=lambda: [SubtitleTrack(name="Default")])
    active_track_index: int = 0
    duration_ms: int = 0
    default_style: SubtitleStyle = field(default_factory=SubtitleStyle)
    video_has_audio: bool = False  # Whether video file has audio track
    image_overlay_track: ImageOverlayTrack = field(default_factory=ImageOverlayTrack)
    video_tracks: list[VideoClipTrack] = field(default_factory=lambda: [VideoClipTrack()])
    text_overlay_track: TextOverlayTrack = field(default_factory=TextOverlayTrack)
    bgm_tracks: list[AudioTrack] = field(default_factory=lambda: [AudioTrack()])

    @property
    def video_clip_track(self) -> VideoClipTrack:
        """Return the primary video track (backward-compatible)."""
        if not self.video_tracks:
            self.video_tracks = [VideoClipTrack()]
        return self.video_tracks[0]

    @video_clip_track.setter
    def video_clip_track(self, track: VideoClipTrack | None) -> None:
        """Set the primary video track (backward-compatible)."""
        if track is None:
            self.video_tracks = [VideoClipTrack()]
        else:
            if not self.video_tracks:
                self.video_tracks = [track]
            else:
                self.video_tracks[0] = track

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

    def all_video_paths(self) -> list[Path]:
        """Return all unique video file paths used in the project."""
        paths: set[Path] = set()
        if self.video_path:
            paths.add(self.video_path)
        for vt in self.video_tracks:
            for clip in vt:
                if clip.source_path:
                    paths.add(Path(clip.source_path))
        return sorted(paths)

    def reset(self) -> None:
        self.video_path = None
        self.subtitle_tracks = [SubtitleTrack(name="Default")]
        self.active_track_index = 0
        self.duration_ms = 0
        self.default_style = SubtitleStyle()
        self.image_overlay_track = ImageOverlayTrack()
        self.video_tracks = [VideoClipTrack()]
        self.text_overlay_track = TextOverlayTrack()
        self.bgm_tracks = [AudioTrack()]
