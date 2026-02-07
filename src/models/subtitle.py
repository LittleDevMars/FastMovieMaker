"""Subtitle data models (pure Python, no Qt dependency)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SubtitleSegment:
    """A single subtitle segment with start/end times in milliseconds."""

    start_ms: int
    end_ms: int
    text: str

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass
class SubtitleTrack:
    """An ordered collection of subtitle segments."""

    segments: list[SubtitleSegment] = field(default_factory=list)
    language: str = ""

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
