"""Subtitle data models (pure Python, no Qt dependency)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.style import SubtitleStyle


@dataclass
class SubtitleSegment:
    """A single subtitle segment with start/end times in milliseconds."""

    start_ms: int
    end_ms: int
    text: str
    style: SubtitleStyle | None = None
    audio_file: str | None = None  # Path to individual audio file for this segment (TTS)
    volume: float = 1.0  # Per-segment volume (0.0~2.0, default 1.0=100%)

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass
class SubtitleTrack:
    """An ordered collection of subtitle segments."""

    segments: list[SubtitleSegment] = field(default_factory=list)
    language: str = ""
    name: str = ""
    audio_path: str = ""  # Path to associated audio file (e.g., TTS generated audio)
    audio_start_ms: int = 0  # Timeline position where audio starts playing
    audio_duration_ms: int = 0  # Total duration of the audio file
    locked: bool = False
    muted: bool = False
    hidden: bool = False

    def segment_at(self, position_ms: int) -> SubtitleSegment | None:
        """Return the segment active at the given position, or None."""
        for seg in self.segments:
            if seg.start_ms <= position_ms < seg.end_ms:
                return seg
        return None

    def add_segment(self, segment: SubtitleSegment) -> None:
        """Add a segment and keep the list sorted by start time."""
        self.segments.append(segment)
        self.segments.sort(key=lambda s: s.start_ms)

    def clear(self) -> None:
        self.segments.clear()

    def __len__(self) -> int:
        return len(self.segments)

    def __iter__(self):
        return iter(self.segments)

    def __getitem__(self, index: int) -> SubtitleSegment:
        return self.segments[index]

    def remove_segment(self, index: int) -> None:
        """Remove the segment at *index*."""
        if 0 <= index < len(self.segments):
            self.segments.pop(index)

    def update_segment_text(self, index: int, text: str) -> None:
        """Change the text of the segment at *index*."""
        if 0 <= index < len(self.segments):
            self.segments[index].text = text

    def update_segment_time(self, index: int, start_ms: int, end_ms: int) -> None:
        """Change start/end of the segment at *index* and re-sort."""
        if 0 <= index < len(self.segments):
            self.segments[index].start_ms = start_ms
            self.segments[index].end_ms = end_ms
            self.segments.sort(key=lambda s: s.start_ms)
