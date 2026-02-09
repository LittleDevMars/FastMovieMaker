"""Unit tests for VideoClip and VideoClipTrack models."""

import pytest

from src.models.video_clip import VideoClip, VideoClipTrack


# ------------------------------------------------------------------ VideoClip


class TestVideoClip:
    def test_duration(self):
        clip = VideoClip(1000, 5000)
        assert clip.duration_ms == 4000

    def test_to_dict(self):
        clip = VideoClip(100, 200)
        d = clip.to_dict()
        assert d == {"source_in_ms": 100, "source_out_ms": 200}

    def test_to_dict_with_source_path(self):
        clip = VideoClip(100, 200, source_path="C:/videos/extra.mp4")
        d = clip.to_dict()
        assert d["source_path"] == "C:/videos/extra.mp4"

    def test_from_dict(self):
        clip = VideoClip.from_dict({"source_in_ms": 500, "source_out_ms": 1500})
        assert clip.source_in_ms == 500
        assert clip.source_out_ms == 1500
        assert clip.source_path is None

    def test_from_dict_with_source_path(self):
        clip = VideoClip.from_dict({
            "source_in_ms": 500, "source_out_ms": 1500,
            "source_path": "D:/clip2.mp4",
        })
        assert clip.source_path == "D:/clip2.mp4"

    def test_roundtrip(self):
        original = VideoClip(1234, 5678)
        restored = VideoClip.from_dict(original.to_dict())
        assert restored.source_in_ms == original.source_in_ms
        assert restored.source_out_ms == original.source_out_ms

    def test_roundtrip_with_source_path(self):
        original = VideoClip(1234, 5678, source_path="extra.mp4")
        restored = VideoClip.from_dict(original.to_dict())
        assert restored.source_path == original.source_path


# ------------------------------------------------------------------ VideoClipTrack


class TestVideoClipTrack:
    def test_from_full_video(self):
        track = VideoClipTrack.from_full_video(10000)
        assert len(track) == 1
        assert track[0].source_in_ms == 0
        assert track[0].source_out_ms == 10000
        assert track.output_duration_ms == 10000

    def test_from_full_video_zero(self):
        track = VideoClipTrack.from_full_video(0)
        assert len(track) == 0
        assert track.output_duration_ms == 0

    def test_output_duration(self):
        track = VideoClipTrack(clips=[
            VideoClip(0, 5000),
            VideoClip(8000, 15000),
        ])
        assert track.output_duration_ms == 5000 + 7000  # 12000

    # ---- Time mapping ----

    def test_timeline_to_source_single_clip(self):
        track = VideoClipTrack.from_full_video(10000)
        assert track.timeline_to_source(0) == 0
        assert track.timeline_to_source(5000) == 5000
        assert track.timeline_to_source(9999) == 9999
        assert track.timeline_to_source(10000) is None  # beyond end

    def test_timeline_to_source_multi_clip(self):
        track = VideoClipTrack(clips=[
            VideoClip(0, 5000),       # output 0-5000
            VideoClip(8000, 15000),   # output 5000-12000
        ])
        # In first clip
        assert track.timeline_to_source(0) == 0
        assert track.timeline_to_source(3000) == 3000
        assert track.timeline_to_source(4999) == 4999
        # In second clip
        assert track.timeline_to_source(5000) == 8000
        assert track.timeline_to_source(7000) == 10000
        assert track.timeline_to_source(11999) == 14999
        # Beyond end
        assert track.timeline_to_source(12000) is None

    def test_timeline_to_source_negative(self):
        track = VideoClipTrack.from_full_video(10000)
        assert track.timeline_to_source(-100) == 0

    def test_source_to_timeline_single_clip(self):
        track = VideoClipTrack.from_full_video(10000)
        assert track.source_to_timeline(0) == 0
        assert track.source_to_timeline(5000) == 5000
        assert track.source_to_timeline(10000) == 10000  # exact end

    def test_source_to_timeline_multi_clip(self):
        track = VideoClipTrack(clips=[
            VideoClip(0, 5000),       # output 0-5000
            VideoClip(8000, 15000),   # output 5000-12000
        ])
        # In first clip
        assert track.source_to_timeline(0) == 0
        assert track.source_to_timeline(3000) == 3000
        # In deleted region (5000-8000)
        assert track.source_to_timeline(6000) is None
        # In second clip
        assert track.source_to_timeline(8000) == 5000
        assert track.source_to_timeline(10000) == 7000
        assert track.source_to_timeline(15000) == 12000  # exact end

    def test_clip_at_timeline(self):
        track = VideoClipTrack(clips=[
            VideoClip(0, 5000),
            VideoClip(8000, 15000),
        ])
        result = track.clip_at_timeline(3000)
        assert result is not None
        assert result[0] == 0
        assert result[1].source_in_ms == 0

        result = track.clip_at_timeline(7000)
        assert result is not None
        assert result[0] == 1
        assert result[1].source_in_ms == 8000

        assert track.clip_at_timeline(12000) is None

    def test_clip_timeline_start(self):
        track = VideoClipTrack(clips=[
            VideoClip(0, 5000),
            VideoClip(8000, 15000),
        ])
        assert track.clip_timeline_start(0) == 0
        assert track.clip_timeline_start(1) == 5000

    def test_clip_boundaries(self):
        track = VideoClipTrack(clips=[
            VideoClip(0, 5000),
            VideoClip(8000, 15000),
        ])
        assert track.clip_boundaries_ms() == [0, 5000, 12000]

    def test_next_clip_source_in(self):
        track = VideoClipTrack(clips=[
            VideoClip(0, 5000),
            VideoClip(8000, 15000),
        ])
        assert track.next_clip_source_in(6000) == 8000
        assert track.next_clip_source_in(14000) is None
        assert track.next_clip_source_in(-1) == 0

    # ---- Split ----

    def test_split_at_timeline(self):
        track = VideoClipTrack.from_full_video(10000)
        assert track.split_at_timeline(5000) is True
        assert len(track) == 2
        assert track[0].source_in_ms == 0
        assert track[0].source_out_ms == 5000
        assert track[1].source_in_ms == 5000
        assert track[1].source_out_ms == 10000

    def test_split_preserves_output_duration(self):
        track = VideoClipTrack.from_full_video(10000)
        track.split_at_timeline(3000)
        assert track.output_duration_ms == 10000

    def test_split_multi_clip(self):
        track = VideoClipTrack(clips=[
            VideoClip(0, 5000),
            VideoClip(8000, 15000),
        ])
        # Split second clip at output ms 7000 (= 2000 into second clip = source 10000)
        assert track.split_at_timeline(7000) is True
        assert len(track) == 3
        assert track[0] == VideoClip(0, 5000)
        assert track[1] == VideoClip(8000, 10000)
        assert track[2] == VideoClip(10000, 15000)
        assert track.output_duration_ms == 12000

    def test_split_too_close_to_start(self):
        track = VideoClipTrack.from_full_video(10000)
        assert track.split_at_timeline(50) is False  # < 100ms
        assert len(track) == 1

    def test_split_too_close_to_end(self):
        track = VideoClipTrack.from_full_video(10000)
        assert track.split_at_timeline(9950) is False  # < 100ms from end
        assert len(track) == 1

    def test_split_beyond_end(self):
        track = VideoClipTrack.from_full_video(10000)
        assert track.split_at_timeline(15000) is False

    # ---- Remove ----

    def test_remove_clip(self):
        track = VideoClipTrack(clips=[
            VideoClip(0, 5000),
            VideoClip(5000, 10000),
        ])
        removed = track.remove_clip(0)
        assert removed is not None
        assert removed.source_in_ms == 0
        assert removed.source_out_ms == 5000
        assert len(track) == 1
        assert track.output_duration_ms == 5000

    def test_remove_last_clip_fails(self):
        track = VideoClipTrack.from_full_video(10000)
        removed = track.remove_clip(0)
        assert removed is None
        assert len(track) == 1

    def test_remove_out_of_range(self):
        track = VideoClipTrack.from_full_video(10000)
        assert track.remove_clip(-1) is None
        assert track.remove_clip(5) is None

    # ---- Trim ----

    def test_trim_left(self):
        track = VideoClipTrack.from_full_video(10000)
        track.trim_clip_left(0, 2000)
        assert track[0].source_in_ms == 2000
        assert track[0].source_out_ms == 10000
        assert track.output_duration_ms == 8000

    def test_trim_left_clamp(self):
        track = VideoClipTrack.from_full_video(10000)
        track.trim_clip_left(0, 9950)  # would leave < 100ms
        assert track[0].source_in_ms == 9900  # clamped to out - 100
        assert track[0].duration_ms == 100

    def test_trim_right(self):
        track = VideoClipTrack.from_full_video(10000)
        track.trim_clip_right(0, 7000)
        assert track[0].source_out_ms == 7000
        assert track.output_duration_ms == 7000

    def test_trim_right_clamp(self):
        track = VideoClipTrack.from_full_video(10000)
        track.trim_clip_right(0, 50)  # would leave < 100ms
        assert track[0].source_out_ms == 100  # clamped to in + 100
        assert track[0].duration_ms == 100

    # ---- is_full_video ----

    def test_is_full_video_true(self):
        track = VideoClipTrack.from_full_video(10000)
        assert track.is_full_video(10000) is True

    def test_is_full_video_false_multi(self):
        track = VideoClipTrack(clips=[
            VideoClip(0, 5000),
            VideoClip(5000, 10000),
        ])
        assert track.is_full_video(10000) is False

    def test_is_full_video_false_trimmed(self):
        track = VideoClipTrack(clips=[VideoClip(500, 10000)])
        assert track.is_full_video(10000) is False

    # ---- Iteration ----

    # ---- Multi-source ----

    def test_split_preserves_source_path(self):
        track = VideoClipTrack(clips=[
            VideoClip(0, 10000, source_path="extra.mp4"),
        ])
        track.split_at_timeline(5000)
        assert len(track) == 2
        assert track[0].source_path == "extra.mp4"
        assert track[1].source_path == "extra.mp4"

    def test_has_multiple_sources_false(self):
        track = VideoClipTrack(clips=[
            VideoClip(0, 5000),
            VideoClip(5000, 10000),
        ])
        assert track.has_multiple_sources() is False

    def test_has_multiple_sources_true(self):
        track = VideoClipTrack(clips=[
            VideoClip(0, 5000),
            VideoClip(0, 3000, source_path="extra.mp4"),
        ])
        assert track.has_multiple_sources() is True

    def test_unique_source_paths(self):
        track = VideoClipTrack(clips=[
            VideoClip(0, 5000),
            VideoClip(0, 3000, source_path="a.mp4"),
            VideoClip(0, 2000, source_path="b.mp4"),
            VideoClip(3000, 6000, source_path="a.mp4"),
        ])
        paths = track.unique_source_paths()
        assert set(paths) == {"a.mp4", "b.mp4"}

    def test_source_to_timeline_multi_source(self):
        """source_to_timeline with source_path filter only considers matching clips."""
        track = VideoClipTrack(clips=[
            VideoClip(0, 5000),                              # timeline 0-5000
            VideoClip(0, 3000, source_path="extra.mp4"),     # timeline 5000-8000
            VideoClip(5000, 10000),                          # timeline 8000-13000
        ])
        # source_ms=1000 in extra.mp4 → timeline 6000
        assert track.source_to_timeline(1000, source_path="extra.mp4") == 6000
        # source_ms=1000 in primary (None) → first matching clip → timeline 1000
        assert track.source_to_timeline(1000, source_path=None) == 1000
        # Without filter → first clip match
        assert track.source_to_timeline(1000) == 1000

    def test_from_full_video_with_source_path(self):
        track = VideoClipTrack.from_full_video(5000, source_path="input.mp4")
        assert len(track) == 1
        assert track[0].source_path == "input.mp4"

    # ---- Iteration ----

    def test_len_iter_getitem(self):
        track = VideoClipTrack(clips=[
            VideoClip(0, 5000),
            VideoClip(8000, 15000),
        ])
        assert len(track) == 2
        assert list(track)[0].source_in_ms == 0
        assert track[1].source_in_ms == 8000
