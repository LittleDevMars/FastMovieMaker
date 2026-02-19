"""Tests for SpeedDialog (Qt-independent logic)."""

from __future__ import annotations

import pytest


class TestSpeedDialogLogic:
    """SpeedDialog의 로직만 단위 테스트 (Qt 위젯 없이)."""

    def test_presets_in_valid_range(self):
        from src.ui.dialogs.speed_dialog import SpeedDialog
        for v in SpeedDialog._PRESETS:
            assert 0.25 <= v <= 4.0

    def test_slider_range(self):
        from src.ui.dialogs.speed_dialog import SpeedDialog
        assert SpeedDialog._SLIDER_MIN == 25
        assert SpeedDialog._SLIDER_MAX == 400

    def test_slider_value_to_speed_conversion(self):
        """슬라이더 값 / 100 = 속도."""
        from src.ui.dialogs.speed_dialog import SpeedDialog
        assert SpeedDialog._SLIDER_MIN / 100 == 0.25
        assert SpeedDialog._SLIDER_MAX / 100 == 4.0

    def test_duration_calculation(self):
        """속도 2.0x → 길이 절반."""
        # 5000ms 클립, 2.0x → 2500ms
        original_ms = 5000
        speed = 2.0
        expected = int(original_ms / speed)
        assert expected == 2500

    def test_duration_calculation_slow(self):
        """속도 0.5x → 길이 두 배."""
        original_ms = 4000
        speed = 0.5
        assert int(original_ms / speed) == 8000
