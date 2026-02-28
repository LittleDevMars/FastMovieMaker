"""Unit tests for SceneDetectionService — 파싱·필터링 로직 (Qt/FFmpeg 의존 없음)."""

from __future__ import annotations

import pytest

from src.services.scene_detection_service import SceneDetectionService


class TestParseScdetOutput:
    def test_parse_scdet_pts_time_format(self):
        stderr = "lavfi.scd.time=2.040000\npts_time:2.040 score:45.2\n"
        result = SceneDetectionService._parse_scdet_output(stderr)
        assert result == [2040]

    def test_parse_scdet_at_time_format(self):
        stderr = "[Parsed_scdet_0 @ 0x...] @time:2.040 score:45.2\n"
        result = SceneDetectionService._parse_scdet_output(stderr)
        assert result == [2040]

    def test_parse_scdet_empty_output(self):
        result = SceneDetectionService._parse_scdet_output("")
        assert result == []

    def test_parse_scdet_multiple_scenes(self):
        stderr = (
            "pts_time:2.040 score:55.1\n"
            "pts_time:5.120 score:60.3\n"
            "pts_time:8.640 score:70.0\n"
        )
        result = SceneDetectionService._parse_scdet_output(stderr)
        assert result == [2040, 5120, 8640]

    def test_parse_scdet_dedup(self):
        # 같은 타임스탬프가 두 번 등장하는 경우 중복 제거
        stderr = "pts_time:3.000 score:50.0\npts_time:3.000 score:51.0\n"
        result = SceneDetectionService._parse_scdet_output(stderr)
        assert result == [3000]

    def test_parse_scdet_fractional_ms(self):
        # int(float*1000) 변환: 소수점 truncation 동작 확인
        stderr = "pts_time:1.500 score:50.0\n"
        result = SceneDetectionService._parse_scdet_output(stderr)
        assert result == [1500]


class TestApplyMinGap:
    def test_apply_min_gap_filters_close(self):
        boundaries = [1000, 1300, 2000, 2200, 3000]
        result = SceneDetectionService._apply_min_gap(boundaries, min_gap_ms=500)
        assert result == [1000, 2000, 3000]

    def test_apply_min_gap_empty(self):
        result = SceneDetectionService._apply_min_gap([], min_gap_ms=500)
        assert result == []

    def test_apply_min_gap_single(self):
        result = SceneDetectionService._apply_min_gap([1500], min_gap_ms=500)
        assert result == [1500]

    def test_apply_min_gap_all_pass(self):
        boundaries = [0, 1000, 2000, 3000]
        result = SceneDetectionService._apply_min_gap(boundaries, min_gap_ms=500)
        assert result == [0, 1000, 2000, 3000]

    def test_apply_min_gap_exact_boundary(self):
        # 정확히 min_gap_ms와 같은 간격은 통과
        boundaries = [0, 500, 1000]
        result = SceneDetectionService._apply_min_gap(boundaries, min_gap_ms=500)
        assert result == [0, 500, 1000]


class TestI18n:
    def test_scene_detect_i18n_ko(self):
        from src.utils.lang.ko import STRINGS
        assert "Detect Scenes..." in STRINGS
        assert STRINGS["Detect Scenes..."] == "장면 감지..."

    def test_scene_detect_i18n_keys_present(self):
        from src.utils.lang.ko import STRINGS
        required = [
            "Detect Scenes",
            "Sensitivity",
            "Min gap between scenes",
            "Detected Scenes",
            "Apply Splits",
        ]
        for key in required:
            assert key in STRINGS, f"i18n 키 누락: {key!r}"
