"""Video clip data models for cut editing (pure Python, no Qt dependency)."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field

# Sentinel: "no source filter" (consider all clips regardless of source_path).
# Distinct from None, which means "only clips with source_path=None (primary video)".
_NO_SOURCE_FILTER = object()


@dataclass(slots=True)
class TransitionInfo:
    """Properties of a transition effect between clips."""

    type: str = "fade"  # xfade types: fade, wipeleft, wiperight, etc.
    duration_ms: int = 500

    def to_dict(self) -> dict:
        return {"type": self.type, "duration_ms": self.duration_ms}

    @classmethod
    def from_dict(cls, data: dict) -> TransitionInfo:
        return cls(type=data["type"], duration_ms=data["duration_ms"])


@dataclass(slots=True)
class VolumePoint:
    """A point in a volume envelope.
    
    offset_ms: Position relative to clip start (visual timeline time).
    volume: Gain multiplier (0.0 to 2.0).
    """
    offset_ms: int
    volume: float

    def to_dict(self) -> dict:
        return {"offset_ms": self.offset_ms, "volume": self.volume}

    @classmethod
    def from_dict(cls, data: dict) -> VolumePoint:
        return cls(offset_ms=data["offset_ms"], volume=data["volume"])


@dataclass(slots=True)
class VideoClip:
    """A contiguous segment of a source video.

    When *source_path* is ``None`` the clip belongs to the project's
    primary video.  Otherwise it references an external video file,
    enabling multi-video timelines.
    """

    source_in_ms: int   # Start position in source video
    source_out_ms: int  # End position in source video
    source_path: str | None = None  # None = project primary video
    speed: float = 1.0  # 0.25 to 4.0
    volume: float = 1.0  # 0.0 to 2.0
    volume_points: list[VolumePoint] = field(default_factory=list)
    brightness: float = 1.0  # 0.5 to 2.0
    contrast: float = 1.0    # 0.5 to 2.0
    saturation: float = 1.0  # 0.0 to 2.0
    transition_out: TransitionInfo | None = None  # Effect transitioning into the NEXT clip

    def get_volume_at(self, offset_ms: int) -> float:
        """Calculate the interpolated volume at a given offset within the clip.

        volume_points는 offset_ms 기준 정렬 상태를 가정.
        이진 탐색(CLRS Ch.2.3)으로 O(log n) — 매 호출마다 O(n log n) sort 제거.

        Args:
            offset_ms: Offset relative to clip start (visual timeline time).

        Returns:
            Multiplier (0.0 to 2.0).
        """
        if not self.volume_points:
            return self.volume

        pts = self.volume_points  # 이미 정렬된 상태 (shift_volume_points에서 보장)

        # Before first point
        if offset_ms <= pts[0].offset_ms:
            return pts[0].volume

        # After last point
        if offset_ms >= pts[-1].offset_ms:
            return pts[-1].volume

        # 이진 탐색으로 offset_ms가 위치하는 구간 [pts[i-1], pts[i]) 찾기
        idx = bisect.bisect_right(pts, offset_ms, key=lambda p: p.offset_ms)
        p1 = pts[idx - 1]
        p2 = pts[idx]
        # Linear interpolation
        span = p2.offset_ms - p1.offset_ms
        if span == 0:
            return p1.volume
        t = (offset_ms - p1.offset_ms) / span
        return p1.volume + t * (p2.volume - p1.volume)

    def clone(self) -> VideoClip:
        """Return a deep copy of this clip."""
        tout = self.transition_out
        c = VideoClip(
            source_in_ms=self.source_in_ms,
            source_out_ms=self.source_out_ms,
            source_path=self.source_path,
            speed=self.speed,
            volume=self.volume,
            volume_points=[VolumePoint(p.offset_ms, p.volume) for p in self.volume_points],
            brightness=self.brightness,
            contrast=self.contrast,
            saturation=self.saturation,
            transition_out=TransitionInfo(tout.type, tout.duration_ms) if tout else None
        )
        return c

    def split_at(self, offset_ms: int) -> tuple[VideoClip, VideoClip]:
        """Split this clip into two at the given visual offset.
        
        Preserves volume, speed, and segments the volume points correctly.
        
        Args:
            offset_ms: Offset relative to clip start (visual timeline time).
            
        Returns:
            Tuple of (first_part, second_part).
        """
        # Calculate split point in source time
        source_split = self.source_in_ms + int(offset_ms * self.speed)
        
        # Create parts
        first = self.clone()
        first.source_out_ms = source_split
        
        second = self.clone()
        second.source_in_ms = source_split
        
        # Handle volume points
        current_vol = self.get_volume_at(offset_ms)
        
        # First part points: points before split + point at split
        first.volume_points = [
            VolumePoint(p.offset_ms, p.volume) 
            for p in self.volume_points if p.offset_ms < offset_ms
        ]
        first.volume_points.append(VolumePoint(offset_ms, current_vol))
        
        # Second part points: point at start (0) + shifted points after split
        second.volume_points = [VolumePoint(0, current_vol)]
        for p in self.volume_points:
            if p.offset_ms > offset_ms:
                second.volume_points.append(VolumePoint(p.offset_ms - offset_ms, p.volume))
        
        return first, second

    def shift_volume_points(self, delta_ms: int) -> None:
        """Shift all volume points by delta_ms.
        
        Used when the START of the clip is trimmed, shifting local offsets.
        """
        for p in self.volume_points:
            p.offset_ms += delta_ms
        
        # Remove points that are now outside the visible range?
        # Standard: keep them but they won't be interpolated if outside [0, duration].
        # Actually splitting/trimming might create points at visual 0.
        # We'll just sort them to be safe.
        self.volume_points.sort(key=lambda p: p.offset_ms)

    @property
    def duration_ms(self) -> int:
        """Visual duration on timeline, affected by speed."""
        raw = self.source_out_ms - self.source_in_ms
        return int(raw / self.speed)

    def to_dict(self) -> dict:
        d: dict = {
            "source_in_ms": self.source_in_ms,
            "source_out_ms": self.source_out_ms,
        }
        if self.source_path is not None:
            d["source_path"] = self.source_path
        if self.speed != 1.0:
            d["speed"] = self.speed
        if self.volume != 1.0:
            d["volume"] = self.volume
        if self.brightness != 1.0:
            d["brightness"] = self.brightness
        if self.contrast != 1.0:
            d["contrast"] = self.contrast
        if self.saturation != 1.0:
            d["saturation"] = self.saturation
        if self.volume_points:
            d["volume_points"] = [p.to_dict() for p in self.volume_points]
        tout = self.transition_out
        if tout:
            d["transition_out"] = tout.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> VideoClip:
        return cls(
            source_in_ms=data["source_in_ms"],
            source_out_ms=data["source_out_ms"],
            source_path=data.get("source_path"),
            speed=data.get("speed", 1.0),
            volume=data.get("volume", 1.0),
            brightness=data.get("brightness", 1.0),
            contrast=data.get("contrast", 1.0),
            saturation=data.get("saturation", 1.0),
            volume_points=[VolumePoint.from_dict(p) for p in data.get("volume_points", [])],
            transition_out=TransitionInfo.from_dict(data["transition_out"])
            if "transition_out" in data
            else None,
        )


@dataclass(slots=True)
class VideoClipTrack:
    """Ordered collection of video clips defining the output timeline.

    Clips are stored in playback order. The output timeline is the
    sequential concatenation of all clips. Each clip references a
    region of the single source video via source_in_ms / source_out_ms.

    내부적으로 접두사 합(prefix sum) 캐시를 유지하여
    clip_at_timeline(), clip_timeline_start() 등을 O(log n)에 수행.
    """

    clips: list[VideoClip] = field(default_factory=list)
    locked: bool = False
    muted: bool = False
    hidden: bool = False

    def _build_prefix(self) -> list[int]:
        """접두사 합 배열을 구축한다. O(n).

        _prefix[i] = clips[0..i-1]의 누적 timeline 시작 offset.
        _prefix[-1] = output_duration_ms.

        외부에서 clip 속성(transition_out, speed 등)을 직접 수정할 수 있으므로
        캐시 대신 매번 재계산. n이 작으므로(보통 <100) 비용 무시 가능.
        """
        offsets: list[int] = []
        offset = 0
        for i, clip in enumerate(self.clips):
            offsets.append(offset)
            offset += clip.duration_ms
            if clip.transition_out and i < len(self.clips) - 1:
                offset -= clip.transition_out.duration_ms
        offsets.append(offset)
        return offsets

    @classmethod
    def from_full_video(cls, duration_ms: int, source_path: str | None = None) -> VideoClipTrack:
        """Create a track with one clip spanning the full video."""
        track = cls()
        if duration_ms > 0:
            track.clips = [VideoClip(0, duration_ms, source_path=source_path)]
        return track

    @property
    def output_duration_ms(self) -> int:
        """Total output timeline length (sum of durations minus transitions). O(1) 캐시."""
        prefix = self._build_prefix()
        return prefix[-1] if prefix else 0

    # -------------------------------------------------------- Time mapping

    def timeline_to_source(self, timeline_ms: int) -> int | None:
        """Convert output-timeline position to source-video position.

        접두사 합 + 이진 탐색으로 O(log n).
        Returns None if timeline_ms is beyond end of all clips.
        """
        if not self.clips:
            return None
        if timeline_ms < 0:
            return self.clips[0].source_in_ms
        result = self.clip_at_timeline(timeline_ms)
        if result is None:
            return None
        idx, clip = result
        prefix = self._build_prefix()
        local_timeline = timeline_ms - prefix[idx]
        return clip.source_in_ms + int(local_timeline * clip.speed)

    def source_to_timeline(self, source_ms: int, source_path=_NO_SOURCE_FILTER) -> int | None:
        """Convert source-video position to output-timeline position.

        접두사 합 캐시를 사용하여 offset 재계산 방지.
        Returns timeline position within the first clip containing source_ms,
        or None if source_ms is not in any clip (deleted region).

        *source_path* controls filtering:
        - ``_NO_SOURCE_FILTER`` (default): consider all clips (backward compat).
        - ``None``: only clips with ``source_path is None`` (primary video).
        - ``"path.mp4"``: only clips with that exact source_path.
        """
        prefix = self._build_prefix()
        last_match_clip: VideoClip | None = None
        last_match_offset: int = 0
        for i, clip in enumerate(self.clips):
            if source_path is not _NO_SOURCE_FILTER and clip.source_path != source_path:
                continue
            offset = prefix[i]
            if clip.source_in_ms <= source_ms < clip.source_out_ms:
                local_source = source_ms - clip.source_in_ms
                return offset + int(local_source / clip.speed)
            last_match_clip = clip
            last_match_offset = offset
        # 마지막 매칭 클립의 끝과 정확히 일치
        if last_match_clip is not None and source_ms == last_match_clip.source_out_ms:
            return last_match_offset + last_match_clip.duration_ms
        # 전체 클립 끝 Fallback
        if source_path is _NO_SOURCE_FILTER and self.clips and source_ms == self.clips[-1].source_out_ms:
            return prefix[-1]
        return None

    def clip_at_timeline(self, timeline_ms: int) -> tuple[int, VideoClip] | None:
        """Find clip at given timeline position (ms).

        접두사 합 + 이진 탐색(CLRS Ch.2.3)으로 O(log n).
        """
        if not self.clips:
            return None
        prefix = self._build_prefix()
        # bisect_right: prefix[i] <= timeline_ms 인 가장 큰 i 를 찾음
        idx = bisect.bisect_right(prefix, timeline_ms) - 1
        if idx < 0:
            idx = 0
        if idx >= len(self.clips):
            return None
        # 범위 확인
        if prefix[idx] <= timeline_ms < prefix[idx + 1]:
            return idx, self.clips[idx]
        return None

    def clip_timeline_start(self, index: int) -> int:
        """Return timeline start position (ms) for clip at index. O(1) 캐시."""
        prefix = self._build_prefix()
        if 0 <= index < len(prefix) - 1:
            return prefix[index]
        return 0

    def clip_boundaries_ms(self) -> list[int]:
        """Return list of start timestamps (ms) for each clip on the timeline. O(1) 캐시."""
        prefix = self._build_prefix()
        # 마지막 원소(output_duration)는 제외
        return prefix[:-1] if len(prefix) > 1 else list(prefix)

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
        prefix = self._build_prefix()
        local_offset = timeline_ms - prefix[idx]

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
        removed = self.clips.pop(index)
        return removed

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
