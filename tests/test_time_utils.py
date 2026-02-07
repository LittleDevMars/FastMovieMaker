"""Tests for time utilities."""

from src.utils.time_utils import ms_to_display, ms_to_srt_time, seconds_to_ms


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
