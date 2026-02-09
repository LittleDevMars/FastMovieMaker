"""Video clip data models for cut editing (pure Python, no Qt dependency)."""

from __future__ import annotations

from dataclasses import dataclass, field

# Sentinel: "no source filter" (consider all clips regardless of source_path).
# Distinct from None, which means "only clips with source_path=None (primary video)".
_NO_SOURCE_FILTER = object()


@dataclass
class VideoClip:
    """A contiguous segment of a source video.

    When *source_path* is ``None`` the clip belongs to the project's
    primary video.  Otherwise it references an external video file,
    enabling multi-video timelines.
    """

    source_in_ms: int   # Start position in source video
    source_out_ms: int  # End position in source video
    source_path: str | None = None  # None = project primary video

    @property
    def duration_ms(self) -> int:
        return self.source_out_ms - self.source_in_ms

    def to_dict(self) -> dict:
        d: dict = {
            "source_in_ms": self.source_in_ms,
            "source_out_ms": self.source_out_ms,
        }
        if self.source_path is not None:
            d["source_path"] = self.source_path
        return d

    @classmethod
    def from_dict(cls, data: dict) -> VideoClip:
        return cls(
            source_in_ms=data["source_in_ms"],
            source_out_ms=data["source_out_ms"],
            source_path=data.get("source_path"),
        )


@dataclass
class VideoClipTrack:
    """Ordered collection of video clips defining the output timeline.

    Clips are stored in playback order. The output timeline is the
    sequential concatenation of all clips. Each clip references a
    region of the single source video via source_in_ms / source_out_ms.
    """

    clips: list[VideoClip] = field(default_factory=list)

    @classmethod
    def from_full_video(cls, duration_ms: int, source_path: str | None = None) -> VideoClipTrack:
        """Create a track with one clip spanning the full video."""
        track = cls()
        if duration_ms > 0:
            track.clips = [VideoClip(0, duration_ms, source_path=source_path)]
        return track

    @property
    def output_duration_ms(self) -> int:
        """Total output timeline length (sum of all clip durations)."""
        return sum(c.duration_ms for c in self.clips)

    # -------------------------------------------------------- Time mapping

    def timeline_to_source(self, timeline_ms: int) -> int | None:
        """Convert output-timeline position to source-video position.

        Returns None if timeline_ms is beyond end of all clips.
        """
        if timeline_ms < 0:
            return self.clips[0].source_in_ms if self.clips else None
        offset = 0
        for clip in self.clips:
            clip_dur = clip.duration_ms
            if timeline_ms < offset + clip_dur:
                return clip.source_in_ms + (timeline_ms - offset)
            offset += clip_dur
        return None

    def source_to_timeline(self, source_ms: int, source_path=_NO_SOURCE_FILTER) -> int | None:
        """Convert source-video position to output-timeline position.

        Returns timeline position within the first clip containing source_ms,
        or None if source_ms is not in any clip (deleted region).

        *source_path* controls filtering:
        - ``_NO_SOURCE_FILTER`` (default): consider all clips (backward compat).
        - ``None``: only clips with ``source_path is None`` (primary video).
        - ``"path.mp4"``: only clips with that exact source_path.
        """
        offset = 0
        last_match_clip = None
        last_match_offset = 0
        for clip in self.clips:
            if source_path is not _NO_SOURCE_FILTER and clip.source_path != source_path:
                offset += clip.duration_ms
                continue
            if clip.source_in_ms <= source_ms < clip.source_out_ms:
                return offset + (source_ms - clip.source_in_ms)
            last_match_clip = clip
            last_match_offset = offset
            offset += clip.duration_ms
        # Check if exactly at end of last matching clip
        if last_match_clip is not None and source_ms == last_match_clip.source_out_ms:
            return last_match_offset + last_match_clip.duration_ms
        # Fallback: no source_path filter
        if source_path is _NO_SOURCE_FILTER and self.clips and source_ms == self.clips[-1].source_out_ms:
            return offset
        return None

    def clip_at_timeline(self, timeline_ms: int) -> tuple[int, VideoClip] | None:
        """Return (index, clip) at given timeline position, or None."""
        offset = 0
        for i, clip in enumerate(self.clips):
            if timeline_ms < offset + clip.duration_ms:
                return (i, clip)
            offset += clip.duration_ms
        return None

    def clip_timeline_start(self, index: int) -> int:
        """Return the timeline start position of the clip at index."""
        return sum(self.clips[i].duration_ms for i in range(index))

    def clip_boundaries_ms(self) -> list[int]:
        """Return list of timeline-ms values at clip boundaries.

        Includes 0 and the total duration. Length = len(clips) + 1.
        """
        boundaries = []
        offset = 0
        for clip in self.clips:
            boundaries.append(offset)
            offset += clip.duration_ms
        boundaries.append(offset)
        return boundaries

    def next_clip_source_in(self, source_ms: int) -> int | None:
        """Find the source_in_ms of the next clip after source_ms.

        Used for auto-skipping deleted regions during playback.
        """
        for clip in self.clips:
            if clip.source_in_ms > source_ms:
                return clip.source_in_ms
        return None

    # -------------------------------------------------------- Editing

    def split_at_timeline(self, timeline_ms: int) -> bool:
        """Split the clip at timeline_ms into two clips.

        Returns True if a split occurred, False if position is invalid
        or too close to an edge (< 100ms from either end).
        """
        result = self.clip_at_timeline(timeline_ms)
        if result is None:
            return False

        idx, clip = result
        offset = self.clip_timeline_start(idx)
        local_offset = timeline_ms - offset

        # Too close to clip edges
        if local_offset < 100 or local_offset > clip.duration_ms - 100:
            return False

        source_split = clip.source_in_ms + local_offset
        first = VideoClip(clip.source_in_ms, source_split, source_path=clip.source_path)
        second = VideoClip(source_split, clip.source_out_ms, source_path=clip.source_path)

        self.clips[idx] = first
        self.clips.insert(idx + 1, second)
        return True

    def remove_clip(self, index: int) -> VideoClip | None:
        """Remove clip at index. Returns the removed clip or None."""
        if index < 0 or index >= len(self.clips):
            return None
        if len(self.clips) <= 1:
            return None  # Cannot remove the last clip
        return self.clips.pop(index)

    def trim_clip_left(self, index: int, new_source_in: int) -> None:
        """Adjust source_in of clip (trim from left)."""
        if index < 0 or index >= len(self.clips):
            return
        clip = self.clips[index]
        new_source_in = max(0, new_source_in)
        new_source_in = min(new_source_in, clip.source_out_ms - 100)
        clip.source_in_ms = new_source_in

    def trim_clip_right(self, index: int, new_source_out: int) -> None:
        """Adjust source_out of clip (trim from right)."""
        if index < 0 or index >= len(self.clips):
            return
        clip = self.clips[index]
        new_source_out = max(clip.source_in_ms + 100, new_source_out)
        clip.source_out_ms = new_source_out

    # -------------------------------------------------------- Queries

    def unique_source_paths(self) -> list[str]:
        """Return deduplicated list of source paths used by clips.

        Clips with ``source_path=None`` (primary video) are excluded.
        """
        seen: set[str] = set()
        result: list[str] = []
        for clip in self.clips:
            if clip.source_path and clip.source_path not in seen:
                seen.add(clip.source_path)
                result.append(clip.source_path)
        return result

    def has_multiple_sources(self) -> bool:
        """Return True if clips reference more than one source video."""
        sources: set[str | None] = set()
        for clip in self.clips:
            sources.add(clip.source_path)
            if len(sources) > 1:
                return True
        return False

    def is_full_video(self, source_duration_ms: int) -> bool:
        """Check if track is a single clip covering the full source."""
        if len(self.clips) != 1:
            return False
        c = self.clips[0]
        return c.source_in_ms == 0 and c.source_out_ms == source_duration_ms

    def __len__(self) -> int:
        return len(self.clips)

    def __iter__(self):
        return iter(self.clips)

    def __getitem__(self, index: int) -> VideoClip:
        return self.clips[index]
