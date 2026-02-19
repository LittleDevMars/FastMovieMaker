"""Tests for DuckingService.build_volume_expr()."""

import pytest

from src.models.subtitle import SubtitleSegment
from src.services.ducking_service import DuckingService


def _make_seg(start_ms: int, end_ms: int, has_audio: bool = True) -> SubtitleSegment:
    return SubtitleSegment(
        start_ms=start_ms,
        end_ms=end_ms,
        text="test",
        audio_file="/tmp/test.mp3" if has_audio else None,
    )


class TestDuckingServiceNoSegments:
    def test_empty_list_returns_base_volume(self):
        result = DuckingService.build_volume_expr([], base_volume=0.8, duck_volume=0.3)
        assert result == "0.8"

    def test_all_segments_without_audio_returns_base_volume(self):
        segs = [_make_seg(0, 2000, has_audio=False), _make_seg(3000, 5000, has_audio=False)]
        result = DuckingService.build_volume_expr(segs, base_volume=0.5, duck_volume=0.2)
        assert result == "0.5"


class TestDuckingServiceSingleSegment:
    def test_single_segment_produces_between_expr(self):
        segs = [_make_seg(500, 2000)]
        result = DuckingService.build_volume_expr(segs, base_volume=0.8, duck_volume=0.3)
        assert "between(t,0.500,2.000)" in result
        assert "0.300" in result
        assert "0.800" in result

    def test_if_gt_wrapper_present(self):
        segs = [_make_seg(1000, 3000)]
        result = DuckingService.build_volume_expr(segs, base_volume=1.0, duck_volume=0.25)
        assert result.startswith("if(gt(")
        assert result.endswith(")")

    def test_single_segment_timing_accuracy(self):
        segs = [_make_seg(1500, 4500)]
        result = DuckingService.build_volume_expr(segs, base_volume=0.6, duck_volume=0.15)
        assert "between(t,1.500,4.500)" in result


class TestDuckingServiceMultipleSegments:
    def test_two_segments_joined_with_plus(self):
        segs = [_make_seg(500, 2000), _make_seg(3000, 5500)]
        result = DuckingService.build_volume_expr(segs, base_volume=0.8, duck_volume=0.3)
        assert "between(t,0.500,2.000)+between(t,3.000,5.500)" in result

    def test_mixed_audio_segments_only_active_included(self):
        segs = [
            _make_seg(0, 1000, has_audio=True),
            _make_seg(2000, 3000, has_audio=False),  # excluded
            _make_seg(4000, 5000, has_audio=True),
        ]
        result = DuckingService.build_volume_expr(segs, base_volume=0.7, duck_volume=0.2)
        assert "between(t,0.000,1.000)" in result
        assert "between(t,4.000,5.000)" in result
        # Segment without audio should not create a between expression at 2.000/3.000
        assert "between(t,2.000,3.000)" not in result

    def test_three_segments_correct_count(self):
        segs = [_make_seg(i * 2000, i * 2000 + 1000) for i in range(3)]
        result = DuckingService.build_volume_expr(segs, base_volume=1.0, duck_volume=0.3)
        assert result.count("between") == 3
