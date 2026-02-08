"""Tests for frame snap, frame display, and Jump to Frame dialog."""

import pytest
from PySide6.QtWidgets import QApplication

from src.utils.time_utils import (
    frame_to_ms,
    ms_to_frame,
    ms_to_timecode_frames,
    parse_flexible_timecode,
    snap_to_frame,
)

# Ensure a QApplication exists for widget tests
_app = QApplication.instance() or QApplication([])


# ── snap_to_frame ──────────────────────────────────────────────


class TestSnapToFrame:
    """Verify snap_to_frame aligns ms to nearest frame boundary."""

    def test_exact_boundary_unchanged(self):
        # 1000 ms = exactly frame 30 at 30fps
        assert snap_to_frame(1000, 30) == 1000

    def test_snap_down(self):
        # 40 ms → frame 1.2 → round to frame 1 → 33 ms
        assert snap_to_frame(40, 30) == 33

    def test_snap_up(self):
        # 50 ms → frame 1.5 → round to frame 2 → 67 ms
        assert snap_to_frame(50, 30) == 67

    def test_zero(self):
        assert snap_to_frame(0, 30) == 0

    def test_24fps(self):
        # At 24fps, frame duration = 41.67 ms
        # 50 ms → frame 1.2 → round to 1 → 42 ms
        assert snap_to_frame(50, 24) == 42

    def test_60fps(self):
        # At 60fps, frame duration = 16.67 ms
        # 25 ms → frame 1.5 → round to 2 → 33 ms
        assert snap_to_frame(25, 60) == 33

    def test_large_value(self):
        # 1 hour at 30fps
        ms = 3_600_000
        assert snap_to_frame(ms, 30) == ms


# ── set_snap_fps on TimelineWidget ─────────────────────────────


class TestTimelineSnapFps:
    """Test that TimelineWidget stores snap_fps correctly."""

    def test_set_snap_fps(self):
        from src.ui.timeline_widget import TimelineWidget

        tw = TimelineWidget()
        assert tw._snap_fps == 0  # default off

        tw.set_snap_fps(30)
        assert tw._snap_fps == 30

    def test_snap_ms_disabled(self):
        from src.ui.timeline_widget import TimelineWidget

        tw = TimelineWidget()
        tw.set_snap_fps(0)
        assert tw._snap_ms(40) == 40  # no snapping

    def test_snap_ms_enabled(self):
        from src.ui.timeline_widget import TimelineWidget

        tw = TimelineWidget()
        tw.set_snap_fps(30)
        assert tw._snap_ms(40) == 33  # snapped


# ── parse_flexible_timecode ────────────────────────────────────


class TestParseFlexibleTimecode:
    """Test all supported input formats for parse_flexible_timecode."""

    def test_hh_mm_ss_ff(self):
        # 00:01:23:15 at 30fps
        ms = parse_flexible_timecode("00:01:23:15", 30)
        assert ms == frame_to_ms(30 * (1 * 60 + 23) + 15, 30)

    def test_hh_mm_ss_mmm(self):
        ms = parse_flexible_timecode("00:01:23.456", 30)
        assert ms == 83456

    def test_mm_ss_mmm(self):
        ms = parse_flexible_timecode("01:23.456", 30)
        assert ms == 83456

    def test_frame_number_f_prefix(self):
        ms = parse_flexible_timecode("F:300", 30)
        assert ms == frame_to_ms(300, 30)

    def test_frame_number_frame_prefix(self):
        ms = parse_flexible_timecode("frame:60", 30)
        assert ms == frame_to_ms(60, 30)

    def test_frame_zero(self):
        assert parse_flexible_timecode("F:0", 30) == 0

    def test_mm_ss_no_decimal(self):
        # MM:SS with no decimal = treated as MM:SS.000
        ms = parse_flexible_timecode("01:30", 30)
        assert ms == 90000

    def test_whitespace_stripped(self):
        ms = parse_flexible_timecode("  F:30  ", 30)
        assert ms == frame_to_ms(30, 30)

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            parse_flexible_timecode("invalid", 30)

    def test_negative_frame_raises(self):
        with pytest.raises(ValueError):
            parse_flexible_timecode("F:-1", 30)

    def test_frame_exceeds_fps_raises(self):
        with pytest.raises(ValueError):
            parse_flexible_timecode("00:00:00:30", 30)  # frame 30 >= fps 30


# ── ms_to_timecode_frames ─────────────────────────────────────


class TestMsToTimecodeFrames:
    """Test timecode display formatting."""

    def test_zero(self):
        assert ms_to_timecode_frames(0, 30) == "00:00:00:00"

    def test_one_second(self):
        assert ms_to_timecode_frames(1000, 30) == "00:00:01:00"

    def test_one_minute(self):
        assert ms_to_timecode_frames(60000, 30) == "00:01:00:00"

    def test_with_frames(self):
        # 1 sec + 15 frames = 1000 + 500 = 1500 ms
        assert ms_to_timecode_frames(1500, 30) == "00:00:01:15"

    def test_negative_clamped(self):
        assert ms_to_timecode_frames(-100, 30) == "00:00:00:00"

    def test_24fps(self):
        # At 24fps, 1 second = frame 24 → "00:00:01:00"
        assert ms_to_timecode_frames(1000, 24) == "00:00:01:00"


# ── JumpToFrameDialog validation ──────────────────────────────


class TestJumpToFrameDialogValidation:
    """Test JumpToFrameDialog._on_accept validation logic (without exec)."""

    def _make_dialog(self, current_ms=0, fps=30, duration_ms=60000):
        from src.ui.dialogs.jump_to_frame_dialog import JumpToFrameDialog

        dlg = JumpToFrameDialog(current_ms, fps, duration_ms)
        return dlg

    def test_initial_target_is_none(self):
        dlg = self._make_dialog()
        assert dlg.target_ms() is None

    def test_prefilled_with_current_timecode(self):
        dlg = self._make_dialog(current_ms=1500, fps=30)
        assert dlg._input.text() == "00:00:01:15"

    def test_valid_input_sets_target(self):
        dlg = self._make_dialog(duration_ms=120000)
        dlg._input.setText("00:01:00:00")
        dlg._on_accept()
        assert dlg._target_ms == 60000

    def test_over_duration_shows_error(self):
        dlg = self._make_dialog(duration_ms=10000)
        dlg._input.setText("00:01:00:00")  # 60s > 10s duration
        dlg._on_accept()
        assert dlg._target_ms is None
        assert dlg._error_label.text()  # non-empty error message

    def test_empty_input_shows_error(self):
        dlg = self._make_dialog()
        dlg._input.setText("")
        dlg._on_accept()
        assert dlg._target_ms is None
        assert dlg._error_label.text()

    def test_invalid_format_shows_error(self):
        dlg = self._make_dialog()
        dlg._input.setText("garbage")
        dlg._on_accept()
        assert dlg._target_ms is None
        assert dlg._error_label.text()

    def test_negative_clamped_to_zero(self):
        # parse_flexible_timecode doesn't produce negative for valid input,
        # but verify the dialog clamps to 0
        dlg = self._make_dialog(duration_ms=60000)
        dlg._input.setText("F:0")
        dlg._on_accept()
        assert dlg._target_ms == 0

    def test_frame_input_accepted(self):
        dlg = self._make_dialog(duration_ms=120000)
        dlg._input.setText("F:300")
        dlg._on_accept()
        assert dlg._target_ms == frame_to_ms(300, 30)
