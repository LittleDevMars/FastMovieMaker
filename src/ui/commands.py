"""QUndoCommand subclasses for subtitle editing operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from src.models.style import SubtitleStyle
    from src.models.subtitle import SubtitleSegment, SubtitleTrack


class EditTextCommand(QUndoCommand):
    """Change the text of a subtitle segment."""

    def __init__(self, track: SubtitleTrack, index: int, old_text: str, new_text: str):
        super().__init__(f"Edit text (segment {index + 1})")
        self._track = track
        self._index = index
        self._old_text = old_text
        self._new_text = new_text

    def redo(self) -> None:
        self._track.update_segment_text(self._index, self._new_text)

    def undo(self) -> None:
        self._track.update_segment_text(self._index, self._old_text)


class EditTimeCommand(QUndoCommand):
    """Change the start/end times of a subtitle segment."""

    def __init__(self, track: SubtitleTrack, index: int,
                 old_start: int, old_end: int, new_start: int, new_end: int):
        super().__init__(f"Edit time (segment {index + 1})")
        self._track = track
        self._index = index
        self._old_start = old_start
        self._old_end = old_end
        self._new_start = new_start
        self._new_end = new_end

    def redo(self) -> None:
        self._track.update_segment_time(self._index, self._new_start, self._new_end)

    def undo(self) -> None:
        self._track.update_segment_time(self._index, self._old_start, self._old_end)


class AddSegmentCommand(QUndoCommand):
    """Add a new subtitle segment."""

    def __init__(self, track: SubtitleTrack, segment: SubtitleSegment):
        super().__init__("Add subtitle")
        self._track = track
        self._segment = segment

    def redo(self) -> None:
        self._track.add_segment(self._segment)

    def undo(self) -> None:
        # Find and remove the segment by identity
        for i, seg in enumerate(self._track.segments):
            if seg is self._segment:
                self._track.segments.pop(i)
                break


class DeleteSegmentCommand(QUndoCommand):
    """Delete a subtitle segment."""

    def __init__(self, track: SubtitleTrack, index: int, segment: SubtitleSegment):
        super().__init__(f"Delete subtitle (segment {index + 1})")
        self._track = track
        self._index = index
        self._segment = segment

    def redo(self) -> None:
        self._track.remove_segment(self._index)

    def undo(self) -> None:
        self._track.segments.insert(self._index, self._segment)
        self._track.segments.sort(key=lambda s: s.start_ms)


class MoveSegmentCommand(QUndoCommand):
    """Move a subtitle segment (change start/end via timeline drag)."""

    def __init__(self, track: SubtitleTrack, index: int,
                 old_start: int, old_end: int, new_start: int, new_end: int):
        super().__init__(f"Move segment {index + 1}")
        self._track = track
        self._index = index
        self._old_start = old_start
        self._old_end = old_end
        self._new_start = new_start
        self._new_end = new_end

    def redo(self) -> None:
        self._track.update_segment_time(self._index, self._new_start, self._new_end)

    def undo(self) -> None:
        self._track.update_segment_time(self._index, self._old_start, self._old_end)


class EditStyleCommand(QUndoCommand):
    """Change the style of a subtitle segment."""

    def __init__(self, track: SubtitleTrack, index: int,
                 old_style: SubtitleStyle | None, new_style: SubtitleStyle | None):
        super().__init__(f"Edit style (segment {index + 1})")
        self._track = track
        self._index = index
        self._old_style = old_style
        self._new_style = new_style

    def redo(self) -> None:
        if 0 <= self._index < len(self._track):
            self._track[self._index].style = self._new_style

    def undo(self) -> None:
        if 0 <= self._index < len(self._track):
            self._track[self._index].style = self._old_style


class SplitCommand(QUndoCommand):
    """Split a subtitle segment at a given time position."""

    def __init__(self, track: SubtitleTrack, index: int,
                 split_ms: int, original: SubtitleSegment,
                 first: SubtitleSegment, second: SubtitleSegment):
        super().__init__(f"Split segment {index + 1}")
        self._track = track
        self._index = index
        self._original = original
        self._first = first
        self._second = second

    def redo(self) -> None:
        # Remove original, insert two parts
        if self._index < len(self._track.segments):
            self._track.segments.pop(self._index)
        self._track.segments.insert(self._index, self._second)
        self._track.segments.insert(self._index, self._first)

    def undo(self) -> None:
        # Remove the two parts, restore original
        # Find first by identity
        for i, seg in enumerate(self._track.segments):
            if seg is self._first:
                self._track.segments.pop(i)
                break
        for i, seg in enumerate(self._track.segments):
            if seg is self._second:
                self._track.segments.pop(i)
                break
        self._track.segments.insert(self._index, self._original)
        self._track.segments.sort(key=lambda s: s.start_ms)


class MergeCommand(QUndoCommand):
    """Merge two consecutive subtitle segments."""

    def __init__(self, track: SubtitleTrack, index: int,
                 first: SubtitleSegment, second: SubtitleSegment,
                 merged: SubtitleSegment):
        super().__init__(f"Merge segments {index + 1}-{index + 2}")
        self._track = track
        self._index = index
        self._first = first
        self._second = second
        self._merged = merged

    def redo(self) -> None:
        # Remove two segments (second first to preserve index)
        if self._index + 1 < len(self._track.segments):
            self._track.segments.pop(self._index + 1)
        if self._index < len(self._track.segments):
            self._track.segments.pop(self._index)
        self._track.segments.insert(self._index, self._merged)

    def undo(self) -> None:
        for i, seg in enumerate(self._track.segments):
            if seg is self._merged:
                self._track.segments.pop(i)
                break
        self._track.segments.insert(self._index, self._first)
        self._track.segments.insert(self._index + 1, self._second)
        self._track.segments.sort(key=lambda s: s.start_ms)


class EditVolumeCommand(QUndoCommand):
    """Change the volume of a subtitle segment."""

    def __init__(self, track: SubtitleTrack, index: int,
                 old_volume: float, new_volume: float):
        super().__init__(f"Edit volume (segment {index + 1})")
        self._track = track
        self._index = index
        self._old_volume = old_volume
        self._new_volume = new_volume

    def redo(self) -> None:
        if 0 <= self._index < len(self._track):
            self._track[self._index].volume = self._new_volume

    def undo(self) -> None:
        if 0 <= self._index < len(self._track):
            self._track[self._index].volume = self._old_volume


class BatchShiftCommand(QUndoCommand):
    """Shift all subtitle times by a given offset."""

    def __init__(self, track: SubtitleTrack, offset_ms: int):
        super().__init__(f"Batch shift {'+'if offset_ms >= 0 else ''}{offset_ms}ms")
        self._track = track
        self._offset_ms = offset_ms

    def redo(self) -> None:
        for seg in self._track.segments:
            seg.start_ms = max(0, seg.start_ms + self._offset_ms)
            seg.end_ms = max(seg.start_ms + 1, seg.end_ms + self._offset_ms)

    def undo(self) -> None:
        for seg in self._track.segments:
            seg.start_ms = max(0, seg.start_ms - self._offset_ms)
            seg.end_ms = max(seg.start_ms + 1, seg.end_ms - self._offset_ms)
