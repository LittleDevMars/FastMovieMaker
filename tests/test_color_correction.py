"""컬러 보정 기능 단위 테스트 (Qt 불필요)."""

import pytest
from unittest.mock import patch, MagicMock

from src.models.video_clip import VideoClip
from src.utils.lang.ko import STRINGS


# ── ColorCorrectionDialog 테스트 (headless) ──────────────────────────────────

class TestColorCorrectionDialog:
    """Qt 위젯 없이 다이얼로그 로직만 검증."""

    def _make_dialog(self, br=1.0, ct=1.0, sat=1.0):
        """QApplication 없이 다이얼로그 객체 생성."""
        from src.ui.dialogs.color_correction_dialog import ColorCorrectionDialog
        with patch("src.ui.dialogs.color_correction_dialog.QDialog.__init__", return_value=None), \
             patch("src.ui.dialogs.color_correction_dialog.QVBoxLayout"), \
             patch("src.ui.dialogs.color_correction_dialog.QGroupBox"), \
             patch("src.ui.dialogs.color_correction_dialog.QPushButton"), \
             patch("src.ui.dialogs.color_correction_dialog.QDialogButtonBox"), \
             patch("src.ui.dialogs.color_correction_dialog.QLabel"), \
             patch("src.ui.dialogs.color_correction_dialog.QHBoxLayout"):

            # QSlider를 모킹하여 슬라이더 값 추적
            mock_slider_cls = MagicMock()
            br_slider = MagicMock()
            ct_slider = MagicMock()
            sat_slider = MagicMock()
            br_slider.value.return_value = int(br * 100)
            ct_slider.value.return_value = int(ct * 100)
            sat_slider.value.return_value = int(sat * 100)
            mock_slider_cls.side_effect = [br_slider, ct_slider, sat_slider]

            with patch("src.ui.dialogs.color_correction_dialog.QSlider", mock_slider_cls):
                dlg = ColorCorrectionDialog.__new__(ColorCorrectionDialog)
                dlg._br_slider = br_slider
                dlg._ct_slider = ct_slider
                dlg._sat_slider = sat_slider
        return dlg

    def test_default_values(self):
        dlg = self._make_dialog(1.0, 1.0, 1.0)
        vals = dlg.get_values()
        assert vals["brightness"] == pytest.approx(1.0)
        assert vals["contrast"] == pytest.approx(1.0)
        assert vals["saturation"] == pytest.approx(1.0)

    def test_get_values_bright(self):
        dlg = self._make_dialog(1.5, 1.0, 1.0)
        assert dlg.get_values()["brightness"] == pytest.approx(1.5)

    def test_get_values_contrast(self):
        dlg = self._make_dialog(1.0, 0.8, 1.0)
        assert dlg.get_values()["contrast"] == pytest.approx(0.8)

    def test_get_values_saturation(self):
        dlg = self._make_dialog(1.0, 1.0, 2.0)
        assert dlg.get_values()["saturation"] == pytest.approx(2.0)

    def test_reset_values(self):
        dlg = self._make_dialog(1.5, 0.8, 2.0)
        # _on_reset 호출 시 setValue(100)가 불려야 함
        dlg._on_reset()
        dlg._br_slider.setValue.assert_called_with(100)
        dlg._ct_slider.setValue.assert_called_with(100)
        dlg._sat_slider.setValue.assert_called_with(100)


# ── FFmpeg eq 필터 테스트 ──────────────────────────────────────────────────────

class TestEqFilter:
    """_build_concat_filter 의 eq 필터 삽입 여부 확인."""

    def _run_filter(self, clip: VideoClip) -> list[str]:
        """concat 필터 파트 리스트 반환."""
        from src.services.video_exporter import _build_concat_filter
        parts, _, _ = _build_concat_filter([clip])
        return parts

    def test_eq_filter_built(self):
        clip = VideoClip(0, 1000, "test.mp4")
        clip.brightness = 1.5
        clip.contrast = 0.8
        clip.saturation = 0.5
        parts = self._run_filter(clip)
        full = ";".join(parts)
        assert "eq=brightness=" in full

    def test_eq_filter_default_skipped(self):
        clip = VideoClip(0, 1000, "test.mp4")
        # 기본값: brightness=1.0, contrast=1.0, saturation=1.0
        parts = self._run_filter(clip)
        full = ";".join(parts)
        assert "eq=" not in full


# ── i18n 키 존재 확인 ──────────────────────────────────────────────────────────

class TestI18nKeys:
    def test_i18n_keys_present(self):
        assert "Color Correction" in STRINGS
        assert "Reset to Default" in STRINGS
        assert "Brightness" in STRINGS
        assert "Contrast" in STRINGS
        assert "Saturation" in STRINGS
