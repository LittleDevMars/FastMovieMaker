"""TrackHeaderPanel 단위 테스트 — Qt 최소 의존."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from src.models.audio import AudioTrack
from src.models.image_overlay import ImageOverlayTrack
from src.models.project import ProjectState
from src.models.subtitle import SubtitleTrack
from src.models.text_overlay import TextOverlayTrack
from src.models.video_clip import VideoClipTrack
from src.ui.track_header_panel import TrackHeaderPanel

# QApplication 인스턴스 보장
_app = QApplication.instance() or QApplication([])


# ── 헬퍼 ──────────────────────────────────────────────────────────────

def _make_timeline_mock(
    video_track_y_base: int = 16,
    sub_y: int = 66,
    audio_y: int = 104,
    img_y: int = 142,
    text_y: int = 186,
    bgm_base_y: int = 230,
) -> MagicMock:
    """TimelineWidget 인스턴스를 모방하는 Mock 반환."""
    m = MagicMock()
    m._video_track_y.side_effect = lambda i: video_track_y_base + i * 36
    m._subtitle_track_y.return_value = sub_y
    m._audio_track_y.return_value = audio_y
    m._img_overlay_base_y.return_value = img_y
    m._text_overlay_base_y.return_value = text_y
    m._bgm_track_base_y.return_value = bgm_base_y
    m._bgm_track_y.side_effect = lambda i: bgm_base_y + i * 38
    return m


def _make_project(num_video: int = 1, num_bgm: int = 1) -> ProjectState:
    """기본 ProjectState 생성."""
    p = ProjectState()
    p.video_tracks = [VideoClipTrack(name=f"V{i}") for i in range(num_video)]
    p.bgm_tracks = [AudioTrack(name=f"BGM{i}") for i in range(num_bgm)]
    return p


def _make_panel(project: ProjectState | None = None,
                num_video: int = 1) -> TrackHeaderPanel:
    """ProjectState와 mock timeline이 연결된 패널 반환."""
    timeline = _make_timeline_mock()
    panel = TrackHeaderPanel(timeline=timeline)
    proj = project or _make_project(num_video=num_video)
    panel.set_project(proj)
    return panel


# ── 클래스 상수 존재 확인 (Bug 1 검증) ───────────────────────────────

class TestClassConstants:
    """Bug 1: 필수 클래스 상수가 정의되어 있는지 확인."""

    def test_bgm_h_defined(self):
        assert hasattr(TrackHeaderPanel, "_BGM_H")
        assert isinstance(TrackHeaderPanel._BGM_H, int)

    def test_track_gap_defined(self):
        assert hasattr(TrackHeaderPanel, "_TRACK_GAP")
        assert isinstance(TrackHeaderPanel._TRACK_GAP, int)

    def test_img_row_h_defined(self):
        assert hasattr(TrackHeaderPanel, "_IMG_ROW_H")
        assert isinstance(TrackHeaderPanel._IMG_ROW_H, int)

    def test_text_row_h_defined(self):
        assert hasattr(TrackHeaderPanel, "_TEXT_ROW_H")
        assert isinstance(TrackHeaderPanel._TEXT_ROW_H, int)

    def test_constant_values(self):
        assert TrackHeaderPanel._BGM_H == 34
        assert TrackHeaderPanel._TRACK_GAP == 4
        assert TrackHeaderPanel._IMG_ROW_H == 40
        assert TrackHeaderPanel._TEXT_ROW_H == 28


# ── _get_tracks_layout 반환값 검증 ───────────────────────────────────

class TestGetTracksLayout:
    """_get_tracks_layout() 반환 구조 및 내용 검증."""

    def test_returns_empty_without_project(self):
        panel = TrackHeaderPanel(timeline=_make_timeline_mock())
        assert panel._get_tracks_layout() == []

    def test_returns_empty_without_timeline(self):
        panel = TrackHeaderPanel(timeline=None)
        panel.set_project(_make_project())
        assert panel._get_tracks_layout() == []

    def test_basic_tracks_present(self):
        panel = _make_panel(num_video=1)
        tracks = panel._get_tracks_layout()
        types = [t["track_type"] for t in tracks]
        assert "video" in types
        assert "subtitle" in types
        assert "audio" in types
        assert "overlay" in types
        assert "text" in types
        assert "bgm" in types

    def test_video_track_count_matches(self):
        panel = _make_panel(num_video=3)
        tracks = panel._get_tracks_layout()
        video_tracks = [t for t in tracks if t["track_type"] == "video"]
        assert len(video_tracks) == 3

    def test_bgm_track_count_matches(self):
        proj = _make_project(num_bgm=2)
        panel = _make_panel(project=proj)
        tracks = panel._get_tracks_layout()
        bgm_tracks = [t for t in tracks if t["track_type"] == "bgm"]
        assert len(bgm_tracks) == 2

    def test_video_track_has_required_keys(self):
        panel = _make_panel(num_video=1)
        tracks = panel._get_tracks_layout()
        vt = next(t for t in tracks if t["track_type"] == "video")
        for key in ("y", "h", "name", "controls", "track_type", "index"):
            assert key in vt, f"Missing key: {key}"

    def test_bgm_track_has_index_key(self):
        panel = _make_panel()
        tracks = panel._get_tracks_layout()
        bt = next(t for t in tracks if t["track_type"] == "bgm")
        assert "index" in bt

    def test_overlay_h_uses_class_constant(self):
        """Bug 2 검증: timeline._IMG_ROW_H 대신 클래스 상수 사용."""
        timeline = _make_timeline_mock(img_y=100, text_y=100)  # next_y == y → h=_IMG_ROW_H
        panel = TrackHeaderPanel(timeline=timeline)
        panel.set_project(_make_project())
        tracks = panel._get_tracks_layout()
        ot = next(t for t in tracks if t["track_type"] == "overlay")
        # h = max(_IMG_ROW_H, next_y - y - _TRACK_GAP) = max(40, 0-4) = 40
        assert ot["h"] == TrackHeaderPanel._IMG_ROW_H

    def test_no_attribute_error_raised(self):
        """Bug 1 & 2 통합: AttributeError 없이 실행 완료."""
        panel = _make_panel(num_video=2)
        try:
            result = panel._get_tracks_layout()
        except AttributeError as e:
            pytest.fail(f"AttributeError: {e}")
        assert len(result) > 0


# ── _get_track_state 검증 (Bug 4) ────────────────────────────────────

class TestGetTrackState:
    """_get_track_state() 반환값 정확성 확인."""

    def _make_panel_with_project(self) -> tuple[TrackHeaderPanel, ProjectState]:
        proj = _make_project()
        panel = _make_panel(project=proj)
        return panel, proj

    def test_video_state_reflects_model(self):
        panel, proj = self._make_panel_with_project()
        proj.video_tracks[0].muted = True
        proj.video_tracks[0].locked = False
        proj.video_tracks[0].hidden = True
        info = {"track_type": "video", "index": 0}
        locked, muted, hidden = panel._get_track_state(info)
        assert muted is True
        assert locked is False
        assert hidden is True

    def test_subtitle_state_reflects_model(self):
        panel, proj = self._make_panel_with_project()
        proj.subtitle_track.muted = True
        info = {"track_type": "subtitle"}
        _, muted, _ = panel._get_track_state(info)
        assert muted is True

    def test_audio_state_reflects_subtitle_track(self):
        """Bug 4: audio 타입이 subtitle_track에서 상태를 읽는지 확인."""
        panel, proj = self._make_panel_with_project()
        proj.subtitle_track.muted = True
        info = {"track_type": "audio"}
        _, muted, _ = panel._get_track_state(info)
        assert muted is True

    def test_audio_state_none_subtitle_track(self):
        """Bug 4: subtitle_track이 None이면 (False, False, False) 반환."""
        panel, proj = self._make_panel_with_project()
        # active_track_index를 범위 밖으로 → subtitle_track이 None을 반환하지 않음
        # 대신 project 자체를 None subtitle_track을 갖도록 mock
        mock_proj = MagicMock()
        mock_proj.subtitle_track = None
        mock_proj.video_tracks = proj.video_tracks
        mock_proj.bgm_tracks = proj.bgm_tracks
        panel.set_project(mock_proj)
        info = {"track_type": "audio"}
        result = panel._get_track_state(info)
        assert result == (False, False, False)

    def test_bgm_state_reflects_model(self):
        proj = _make_project(num_bgm=1)
        proj.bgm_tracks[0].muted = True
        proj.bgm_tracks[0].locked = True
        panel = _make_panel(project=proj)
        info = {"track_type": "bgm", "index": 0}
        locked, muted, hidden = panel._get_track_state(info)
        assert locked is True
        assert muted is True
        assert hidden is False  # AudioTrack has no hidden field

    def test_overlay_state_uses_getattr(self):
        proj = _make_project()
        proj.image_overlay_track.locked = True
        proj.image_overlay_track.hidden = True
        panel = _make_panel(project=proj)
        info = {"track_type": "overlay"}
        locked, muted, hidden = panel._get_track_state(info)
        assert locked is True
        assert muted is False
        assert hidden is True


# ── _toggle_state 동작 검증 ──────────────────────────────────────────

class TestToggleState:
    """_toggle_state()가 모델 값을 토글하고 signal을 emit하는지 확인."""

    def test_toggle_video_muted(self):
        proj = _make_project()
        proj.video_tracks[0].muted = False
        panel = _make_panel(project=proj)
        signal_called = []
        panel.state_changed.connect(lambda: signal_called.append(True))

        panel._toggle_state({"track_type": "video", "index": 0}, "muted")
        assert proj.video_tracks[0].muted is True
        assert len(signal_called) == 1

    def test_toggle_video_muted_twice_restores(self):
        proj = _make_project()
        proj.video_tracks[0].muted = False
        panel = _make_panel(project=proj)
        panel._toggle_state({"track_type": "video", "index": 0}, "muted")
        panel._toggle_state({"track_type": "video", "index": 0}, "muted")
        assert proj.video_tracks[0].muted is False

    def test_toggle_subtitle_locked(self):
        proj = _make_project()
        proj.subtitle_track.locked = False
        panel = _make_panel(project=proj)
        panel._toggle_state({"track_type": "subtitle"}, "locked")
        assert proj.subtitle_track.locked is True

    def test_toggle_bgm_muted(self):
        proj = _make_project(num_bgm=1)
        proj.bgm_tracks[0].muted = False
        panel = _make_panel(project=proj)
        panel._toggle_state({"track_type": "bgm", "index": 0}, "muted")
        assert proj.bgm_tracks[0].muted is True

    def test_no_project_does_nothing(self):
        panel = TrackHeaderPanel(timeline=_make_timeline_mock())
        # should not raise
        panel._toggle_state({"track_type": "video", "index": 0}, "muted")


# ── 버튼 히트 테스트 (mousePressEvent 보조) ──────────────────────────

class TestButtonHitDetection:
    """L/M/V 버튼 위치 계산이 _get_tracks_layout과 일치하는지 확인."""

    def test_ctrl_x_start_offset(self):
        """버튼 X 시작점은 width - 80."""
        panel = _make_panel()
        expected_ctrl_x = panel.width() - 80
        # TrackHeaderPanel.setFixedWidth(120) → width=120 → ctrl_x=40
        assert expected_ctrl_x == 40

    def test_video_track_has_LMH_controls(self):
        panel = _make_panel(num_video=1)
        tracks = panel._get_tracks_layout()
        vt = next(t for t in tracks if t["track_type"] == "video")
        assert "L" in vt["controls"]
        assert "M" in vt["controls"]
        assert "H" in vt["controls"]

    def test_bgm_track_has_LM_controls(self):
        panel = _make_panel()
        tracks = panel._get_tracks_layout()
        bt = next(t for t in tracks if t["track_type"] == "bgm")
        assert "L" in bt["controls"]
        assert "M" in bt["controls"]
        assert "H" not in bt["controls"]

    def test_overlay_track_has_LH_controls(self):
        panel = _make_panel()
        tracks = panel._get_tracks_layout()
        ot = next(t for t in tracks if t["track_type"] == "overlay")
        assert "L" in ot["controls"]
        assert "H" in ot["controls"]
        assert "M" not in ot["controls"]
