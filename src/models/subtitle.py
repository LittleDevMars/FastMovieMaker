"""Subtitle data models (pure Python, no Qt dependency)."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.style import SubtitleStyle


@dataclass(slots=True)
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


@dataclass(slots=True)
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
        """Return the segment active at the given position, or None.

        이진 탐색(CLRS Ch.2.3)으로 O(log n) — segments는 start_ms 기준 정렬 상태 유지.
        """
        if not self.segments:
            return None
        # bisect_right: position_ms 이하인 start_ms를 가진 세그먼트의 오른쪽 경계
        idx = bisect.bisect_right(self.segments, position_ms, key=lambda s: s.start_ms)
        if idx > 0:
            seg = self.segments[idx - 1]
            if seg.start_ms <= position_ms < seg.end_ms:
                return seg
        return None

    def add_segment(self, segment: SubtitleSegment) -> None:
        """Add a segment and keep the list sorted by start time.

        bisect.insort로 O(n) 삽입 (전체 정렬 O(n log n) 대비 개선).
        """
        bisect.insort(self.segments, segment, key=lambda s: s.start_ms)

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
        """Change start/end of the segment at *index* and re-sort.

        기존 위치에서 제거 후 bisect.insort로 올바른 위치에 재삽입 — O(n).
        """
        if 0 <= index < len(self.segments):
            seg = self.segments.pop(index)
            seg.start_ms = start_ms
            seg.end_ms = end_ms
            bisect.insort(self.segments, seg, key=lambda s: s.start_ms)
