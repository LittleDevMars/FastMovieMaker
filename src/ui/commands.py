"""QUndoCommand subclasses for subtitle and video clip editing operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from src.models.style import SubtitleStyle
    from src.models.subtitle import SubtitleSegment, SubtitleTrack
    from src.models.video_clip import VideoClip, VideoClipTrack


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


# ------------------------------------------------------------------ Video clip commands


class SplitClipCommand(QUndoCommand):
    """Split a video clip into two at a given point."""

    def __init__(self, clip_track: VideoClipTrack, clip_index: int,
                 original: VideoClip, first: VideoClip, second: VideoClip):
        super().__init__(f"Split clip {clip_index + 1}")
        self._clip_track = clip_track
        self._index = clip_index
        self._original = original
        self._first = first
        self._second = second

    def redo(self) -> None:
        self._clip_track.clips.pop(self._index)
        self._clip_track.clips.insert(self._index, self._second)
        self._clip_track.clips.insert(self._index, self._first)

    def undo(self) -> None:
        # Remove first and second, restore original
        for i, c in enumerate(self._clip_track.clips):
            if c is self._first:
                self._clip_track.clips.pop(i)
                break
        for i, c in enumerate(self._clip_track.clips):
            if c is self._second:
                self._clip_track.clips.pop(i)
                break
        self._clip_track.clips.insert(self._index, self._original)


class DeleteClipCommand(QUndoCommand):
    """Delete a video clip with subtitle ripple.

    When a clip is deleted:
    1. Subtitles fully inside the deleted clip's timeline range are removed.
    2. Subtitles after the deleted range shift left by clip.duration_ms.
    3. Subtitles straddling the boundary are truncated.
    """

    def __init__(self, clip_track: VideoClipTrack, clip_index: int,
                 removed_clip: VideoClip,
                 subtitle_track: SubtitleTrack,
                 clip_start_tl: int, clip_end_tl: int):
        super().__init__(f"Delete clip {clip_index + 1}")
        self._clip_track = clip_track
        self._clip_index = clip_index
        self._removed_clip = removed_clip
        self._sub_track = subtitle_track
        self._clip_start = clip_start_tl
        self._clip_end = clip_end_tl
        self._shift = removed_clip.duration_ms

        # Snapshot of affected subtitles for undo
        self._removed_subs: list[tuple[int, SubtitleSegment]] = []
        self._truncated_subs: list[tuple[int, int, int]] = []  # (seg_index, old_start, old_end)
        self._shifted_subs: list[tuple[int, int, int]] = []    # (seg_index, old_start, old_end)

    def redo(self) -> None:
        # 1. Remove the clip
        self._clip_track.clips.pop(self._clip_index)

        # 2. Process subtitles (iterate in reverse for safe removal)
        self._removed_subs.clear()
        self._truncated_subs.clear()
        self._shifted_subs.clear()

        to_remove = []
        for i, seg in enumerate(self._sub_track.segments):
            if seg.start_ms >= self._clip_start and seg.end_ms <= self._clip_end:
                # Fully inside deleted region
                to_remove.append(i)
            elif seg.start_ms < self._clip_end and seg.end_ms > self._clip_start:
                # Partially overlapping — truncate
                self._truncated_subs.append((i, seg.start_ms, seg.end_ms))
                if seg.start_ms < self._clip_start:
                    seg.end_ms = self._clip_start
                else:
                    seg.start_ms = self._clip_start
                    seg.end_ms = seg.end_ms - self._shift
            elif seg.start_ms >= self._clip_end:
                # After deleted region — shift left
                self._shifted_subs.append((i, seg.start_ms, seg.end_ms))
                seg.start_ms -= self._shift
                seg.end_ms -= self._shift

        # Remove fully contained subtitles (reverse order)
        for i in reversed(to_remove):
            self._removed_subs.append((i, self._sub_track.segments[i]))
            self._sub_track.segments.pop(i)

    def undo(self) -> None:
        # 1. Restore removed subtitles
        for i, seg in self._removed_subs:
            self._sub_track.segments.insert(i, seg)

        # 2. Restore truncated subtitles
        for i, old_start, old_end in self._truncated_subs:
            if i < len(self._sub_track.segments):
                self._sub_track.segments[i].start_ms = old_start
                self._sub_track.segments[i].end_ms = old_end

        # 3. Unshift moved subtitles
        for i, old_start, old_end in self._shifted_subs:
            if i < len(self._sub_track.segments):
                self._sub_track.segments[i].start_ms = old_start
                self._sub_track.segments[i].end_ms = old_end

        # 4. Restore the clip
        self._clip_track.clips.insert(self._clip_index, self._removed_clip)

        self._sub_track.segments.sort(key=lambda s: s.start_ms)


class TrimClipCommand(QUndoCommand):
    """Trim a video clip edge (change source_in or source_out)."""

    def __init__(self, clip_track: VideoClipTrack, clip_index: int,
                 old_in: int, old_out: int, new_in: int, new_out: int):
        super().__init__(f"Trim clip {clip_index + 1}")
        self._clip_track = clip_track
        self._index = clip_index
        self._old_in = old_in
        self._old_out = old_out
        self._new_in = new_in
        self._new_out = new_out

    def redo(self) -> None:
        if 0 <= self._index < len(self._clip_track.clips):
            clip = self._clip_track.clips[self._index]
            clip.source_in_ms = self._new_in
            clip.source_out_ms = self._new_out

    def undo(self) -> None:
        if 0 <= self._index < len(self._clip_track.clips):
            clip = self._clip_track.clips[self._index]
            clip.source_in_ms = self._old_in
            clip.source_out_ms = self._old_out
