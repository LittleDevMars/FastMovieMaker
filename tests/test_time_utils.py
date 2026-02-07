"""Tests for time utilities."""

import pytest

from src.utils.time_utils import (
    ms_to_display,
    ms_to_srt_time,
    seconds_to_ms,
    ms_to_frame,
    frame_to_ms,
    snap_to_frame,
    ms_to_timecode_frames,
    timecode_frames_to_ms,
    parse_flexible_timecode,
)


class TestMsToDisplay:
    def test_zero(self):
        assert ms_to_display(0) == "00:00.000"

    def test_normal(self):
        assert ms_to_display(83456) == "01:23.456"

    def test_negative_clamps(self):
        assert ms_to_display(-100) == "00:00.000"

    def test_large_value(self):
        # 5 minutes exactly
        assert ms_to_display(300000) == "05:00.000"


class TestMsToSrtTime:
    def test_zero(self):
        assert ms_to_srt_time(0) == "00:00:00,000"

    def test_normal(self):
        assert ms_to_srt_time(3723456) == "01:02:03,456"

    def test_negative(self):
        assert ms_to_srt_time(-5) == "00:00:00,000"


class TestSecondsToMs:
    def test_integer(self):
        assert seconds_to_ms(5.0) == 5000

    def test_fractional(self):
        assert seconds_to_ms(1.5) == 1500

    def test_rounding(self):
        assert seconds_to_ms(1.9999) == 2000


class TestFrameConversion:
    """Test frame number conversion functions."""

    def test_ms_to_frame_30fps(self):
        assert ms_to_frame(0, 30) == 0
        assert ms_to_frame(1000, 30) == 30  # 1 second = 30 frames
        assert ms_to_frame(33, 30) == 1
        assert ms_to_frame(500, 30) == 15
        assert ms_to_frame(2000, 30) == 60  # 2 seconds

    def test_ms_to_frame_24fps(self):
        assert ms_to_frame(0, 24) == 0
        assert ms_to_frame(1000, 24) == 24  # 1 second = 24 frames
        assert ms_to_frame(42, 24) == 1
        assert ms_to_frame(500, 24) == 12

    def test_ms_to_frame_60fps(self):
        assert ms_to_frame(0, 60) == 0
        assert ms_to_frame(1000, 60) == 60  # 1 second = 60 frames
        assert ms_to_frame(17, 60) == 1
        assert ms_to_frame(500, 60) == 30

    def test_frame_to_ms_30fps(self):
        assert frame_to_ms(0, 30) == 0
        assert frame_to_ms(30, 30) == 1000  # 30 frames = 1 second
        assert frame_to_ms(15, 30) == 500
        assert frame_to_ms(60, 30) == 2000

    def test_frame_to_ms_24fps(self):
        assert frame_to_ms(0, 24) == 0
        assert frame_to_ms(24, 24) == 1000
        assert frame_to_ms(12, 24) == 500

    def test_frame_to_ms_60fps(self):
        assert frame_to_ms(0, 60) == 0
        assert frame_to_ms(60, 60) == 1000
        assert frame_to_ms(30, 60) == 500

    def test_roundtrip_conversion(self):
        """Test that frame → ms → frame conversion is consistent."""
        for fps in [24, 25, 30, 60, 120]:
            for frame in [0, 1, 10, 100, 1000]:
                ms = frame_to_ms(frame, fps)
                frame_back = ms_to_frame(ms, fps)
                assert frame_back == frame, f"Failed at {frame} frames, {fps} fps"

    def test_snap_to_frame_30fps(self):
        assert snap_to_frame(0, 30) == 0
        assert snap_to_frame(33, 30) == 33  # Exact frame boundary
        assert snap_to_frame(40, 30) == 33  # Closer to frame 1
        assert snap_to_frame(50, 30) == 67  # Closer to frame 2
        assert snap_to_frame(1000, 30) == 1000  # Exact second

    def test_snap_to_frame_different_fps(self):
        # Test snapping at various FPS rates
        for fps in [24, 25, 30, 60]:
            # Exact frame boundaries should not change
            for frame in range(10):
                ms = frame_to_ms(frame, fps)
                snapped = snap_to_frame(ms, fps)
                assert snapped == ms

    def test_snap_to_frame_rounding(self):
        """Test that snapping rounds to nearest frame."""
        fps = 30
        frame_duration = frame_to_ms(1, fps)  # ~33ms

        # Test midpoint (should round to nearest)
        midpoint = frame_duration // 2
        snapped = snap_to_frame(midpoint, fps)
        # Should snap to 0 or frame_duration, both acceptable
        assert snapped == 0 or snapped == frame_duration


class TestTimecodeFrames:
    """Test HH:MM:SS:FF timecode format."""

    def test_ms_to_timecode_frames_zero(self):
        assert ms_to_timecode_frames(0, 30) == "00:00:00:00"

    def test_ms_to_timecode_frames_simple(self):
        assert ms_to_timecode_frames(1000, 30) == "00:00:01:00"  # 1 second
        assert ms_to_timecode_frames(1033, 30) == "00:00:01:01"  # 1 second + 1 frame

    def test_ms_to_timecode_frames_complex(self):
        # 1 minute, 23 seconds, 15 frames at 30fps
        # = (1*60 + 23)*30 + 15 = 2505 frames
        # = 2505 * 1000 / 30 = 83500ms
        assert ms_to_timecode_frames(83500, 30) == "00:01:23:15"

    def test_ms_to_timecode_frames_with_hours(self):
        # 1 hour = 3600 seconds = 3600000ms
        assert ms_to_timecode_frames(3600000, 30) == "01:00:00:00"
        # 1 hour, 2 minutes, 3 seconds, 4 frames
        ms = 3723000 + frame_to_ms(4, 30)
        assert ms_to_timecode_frames(ms, 30) == "01:02:03:04"

    def test_ms_to_timecode_frames_different_fps(self):
        # 1 second at different FPS
        assert ms_to_timecode_frames(1000, 24) == "00:00:01:00"
        assert ms_to_timecode_frames(1000, 25) == "00:00:01:00"
        assert ms_to_timecode_frames(1000, 60) == "00:00:01:00"

    def test_ms_to_timecode_frames_negative_clamps(self):
        assert ms_to_timecode_frames(-1000, 30) == "00:00:00:00"

    def test_timecode_frames_to_ms_zero(self):
        assert timecode_frames_to_ms("00:00:00:00", 30) == 0

    def test_timecode_frames_to_ms_simple(self):
        assert timecode_frames_to_ms("00:00:01:00", 30) == 1000
        assert timecode_frames_to_ms("00:00:01:15", 30) == 1500

    def test_timecode_frames_to_ms_complex(self):
        # 1 minute, 23 seconds, 15 frames at 30fps
        assert timecode_frames_to_ms("00:01:23:15", 30) == 83500

    def test_timecode_frames_to_ms_with_hours(self):
        assert timecode_frames_to_ms("01:00:00:00", 30) == 3600000
        assert timecode_frames_to_ms("01:02:03:04", 30) == 3723000 + frame_to_ms(4, 30)

    def test_timecode_frames_to_ms_invalid_format(self):
        with pytest.raises(ValueError, match="Expected HH:MM:SS:FF"):
            timecode_frames_to_ms("01:23.456", 30)
        with pytest.raises(ValueError, match="Expected HH:MM:SS:FF"):
            timecode_frames_to_ms("00:01:23", 30)

    def test_timecode_frames_to_ms_invalid_numbers(self):
        with pytest.raises(ValueError):
            timecode_frames_to_ms("00:00:00:abc", 30)

    def test_timecode_frames_to_ms_frame_exceeds_fps(self):
        with pytest.raises(ValueError, match="exceeds FPS"):
            timecode_frames_to_ms("00:00:00:30", 30)  # Frame 30 at 30fps
        with pytest.raises(ValueError, match="exceeds FPS"):
            timecode_frames_to_ms("00:00:00:60", 30)  # Frame 60 at 30fps

    def test_timecode_frames_roundtrip(self):
        """Test that ms → timecode → ms conversion is consistent."""
        for fps in [24, 30, 60]:
            for ms in [0, 1000, 5000, 83500, 3600000]:
                # Snap to frame boundary first
                ms_snapped = snap_to_frame(ms, fps)
                timecode = ms_to_timecode_frames(ms_snapped, fps)
                ms_back = timecode_frames_to_ms(timecode, fps)
                assert ms_back == ms_snapped


class TestFlexibleParsing:
    """Test parse_flexible_timecode with various formats."""

    def test_parse_mm_ss_mmm(self):
        """Test MM:SS.mmm format."""
        fps = 30
        assert parse_flexible_timecode("00:00.000", fps) == 0
        assert parse_flexible_timecode("01:23.456", fps) == 83456
        assert parse_flexible_timecode("05:00.000", fps) == 300000

    def test_parse_mm_ss(self):
        """Test MM:SS format (backward compatibility)."""
        fps = 30
        assert parse_flexible_timecode("00:00", fps) == 0
        assert parse_flexible_timecode("01:23", fps) == 83000

    def test_parse_hh_mm_ss_mmm(self):
        """Test HH:MM:SS.mmm format."""
        fps = 30
        assert parse_flexible_timecode("00:00:00.000", fps) == 0
        assert parse_flexible_timecode("00:01:23.456", fps) == 83456
        assert parse_flexible_timecode("01:02:03.456", fps) == 3723456

    def test_parse_hh_mm_ss_ff(self):
        """Test HH:MM:SS:FF format."""
        fps = 30
        assert parse_flexible_timecode("00:00:00:00", fps) == 0
        assert parse_flexible_timecode("00:00:01:00", fps) == 1000
        assert parse_flexible_timecode("00:01:23:15", fps) == 83500

    def test_parse_frame_number_f_prefix(self):
        """Test F:123 format."""
        fps = 30
        assert parse_flexible_timecode("F:0", fps) == 0
        assert parse_flexible_timecode("F:30", fps) == 1000
        assert parse_flexible_timecode("F:60", fps) == 2000
        assert parse_flexible_timecode("f:30", fps) == 1000  # Case insensitive

    def test_parse_frame_number_frame_prefix(self):
        """Test frame:123 format."""
        fps = 30
        assert parse_flexible_timecode("frame:0", fps) == 0
        assert parse_flexible_timecode("frame:30", fps) == 1000
        assert parse_flexible_timecode("Frame:60", fps) == 2000  # Case insensitive

    def test_parse_frame_number_with_spaces(self):
        """Test frame number with spaces."""
        fps = 30
        assert parse_flexible_timecode("F: 30", fps) == 1000
        assert parse_flexible_timecode("frame: 60 ", fps) == 2000

    def test_parse_negative_frame_number(self):
        """Test that negative frame numbers raise error."""
        with pytest.raises(ValueError, match="cannot be negative"):
            parse_flexible_timecode("F:-10", 30)

    def test_parse_invalid_frame_number(self):
        """Test invalid frame number format."""
        with pytest.raises(ValueError):
            parse_flexible_timecode("F:abc", 30)

    def test_parse_invalid_format(self):
        """Test unrecognized formats."""
        with pytest.raises(ValueError, match="Unrecognized timecode format"):
            parse_flexible_timecode("invalid", 30)
        with pytest.raises(ValueError, match="Unrecognized timecode format"):
            parse_flexible_timecode("12345", 30)

    def test_parse_different_fps(self):
        """Test that FPS affects frame-based formats."""
        # Frame 60 at different FPS
        assert parse_flexible_timecode("F:60", 30) == 2000  # 2 seconds at 30fps
        assert parse_flexible_timecode("F:60", 60) == 1000  # 1 second at 60fps
        assert parse_flexible_timecode("F:60", 24) == 2500  # 2.5 seconds at 24fps

    def test_parse_with_whitespace(self):
        """Test that leading/trailing whitespace is handled."""
        fps = 30
        assert parse_flexible_timecode("  01:23.456  ", fps) == 83456
        assert parse_flexible_timecode(" 00:01:23:15 ", fps) == 83500
        assert parse_flexible_timecode("  F:30  ", fps) == 1000
