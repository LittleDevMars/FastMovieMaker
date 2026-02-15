"""Audio clip and track models for BGM and secondary audio."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AudioClip:
    """Represents a single audio file on an audio track."""

    source_path: Path
    start_ms: int = 0  # Position on timeline
    offset_ms: int = 0  # Offset within the audio file
    duration_ms: int = 0  # Duration on timeline
    volume: float = 1.0  # 0.0 to 1.0 (or more for boost)

    def __post_init__(self):
        if isinstance(self.source_path, str):
            self.source_path = Path(self.source_path)

    def clone(self) -> AudioClip:
        return AudioClip(
            source_path=self.source_path,
            start_ms=self.start_ms,
            offset_ms=self.offset_ms,
            duration_ms=self.duration_ms,
            volume=self.volume,
        )


@dataclass
class AudioTrack:
    """A collection of audio clips."""

    name: str = "Audio Track"
    clips: list[AudioClip] = field(default_factory=list)
    volume: float = 1.0
    muted: bool = False
    locked: bool = False

    def __len__(self) -> int:
        return len(self.clips)

    def __iter__(self):
        return iter(self.clips)

    def add_clip(self, clip: AudioClip) -> None:
        self.clips.append(clip)
        self.clips.sort(key=lambda c: c.start_ms)

    def remove_clip(self, clip: AudioClip) -> None:
        if clip in self.clips:
            self.clips.remove(clip)

    def clone(self) -> AudioTrack:
        return AudioTrack(
            name=self.name,
            clips=[c.clone() for c in self.clips],
            volume=self.volume,
            muted=self.muted,
            locked=self.locked,
        )
