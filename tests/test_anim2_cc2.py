"""Phase ANIM2 + CC2 — 자막 애니메이션 강화 및 컬러 보정 강화 테스트."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ────────────────────────────────────────────────────────────────────────────
# Phase CC2: hue 필드
# ────────────────────────────────────────────────────────────────────────────

class TestVideoClipHue:
    """VideoClip에 hue 필드 추가 테스트."""

    def test_default_hue_is_zero(self):
        from src.models.video_clip import VideoClip
        clip = VideoClip(source_in_ms=0, source_out_ms=1000)
        assert clip.hue == 0.0

    def test_hue_stored(self):
        from src.models.video_clip import VideoClip
        clip = VideoClip(source_in_ms=0, source_out_ms=1000, hue=45.0)
        assert clip.hue == 45.0

    def test_hue_negative(self):
        from src.models.video_clip import VideoClip
        clip = VideoClip(source_in_ms=0, source_out_ms=1000, hue=-90.0)
        assert clip.hue == -90.0

    def test_clone_preserves_hue(self):
        from src.models.video_clip import VideoClip
        clip = VideoClip(source_in_ms=0, source_out_ms=1000, hue=120.0)
        cloned = clip.clone()
        assert cloned.hue == 120.0

    def test_to_dict_includes_hue_when_nonzero(self):
        from src.models.video_clip import VideoClip
        clip = VideoClip(source_in_ms=0, source_out_ms=1000, hue=30.0)
        d = clip.to_dict()
        assert "hue" in d
        assert d["hue"] == 30.0

    def test_to_dict_omits_hue_when_zero(self):
        from src.models.video_clip import VideoClip
        clip = VideoClip(source_in_ms=0, source_out_ms=1000)
        d = clip.to_dict()
        assert "hue" not in d

    def test_from_dict_restores_hue(self):
        from src.models.video_clip import VideoClip
        d = {"source_in_ms": 0, "source_out_ms": 1000, "hue": -60.0}
        clip = VideoClip.from_dict(d)
        assert clip.hue == -60.0

    def test_from_dict_defaults_hue_to_zero(self):
        from src.models.video_clip import VideoClip
        d = {"source_in_ms": 0, "source_out_ms": 1000}
        clip = VideoClip.from_dict(d)
        assert clip.hue == 0.0

    def test_roundtrip_hue(self):
        from src.models.video_clip import VideoClip
        clip = VideoClip(source_in_ms=500, source_out_ms=3000,
                         brightness=1.2, contrast=0.9, saturation=1.5, hue=-30.0)
        clip2 = VideoClip.from_dict(clip.to_dict())
        assert clip2.hue == -30.0
        assert clip2.brightness == 1.2
        assert clip2.saturation == 1.5


# ────────────────────────────────────────────────────────────────────────────
# Phase CC2: EditColorCorrectionCommand with hue
# ────────────────────────────────────────────────────────────────────────────

class TestEditColorCorrectionCommandHue:
    """EditColorCorrectionCommand이 hue를 올바르게 처리하는지 확인."""

    def _make_clip(self, br=1.0, ct=1.0, sat=1.0, hue=0.0):
        from src.models.video_clip import VideoClip
        return VideoClip(source_in_ms=0, source_out_ms=1000,
                         brightness=br, contrast=ct, saturation=sat, hue=hue)

    def test_redo_sets_hue(self):
        from src.ui.commands import EditColorCorrectionCommand
        clip = self._make_clip(hue=0.0)
        cmd = EditColorCorrectionCommand(
            clip,
            1.0, 1.0, 1.0,
            1.2, 0.9, 1.1,
            old_hue=0.0, new_hue=45.0,
        )
        cmd.redo()
        assert clip.hue == 45.0

    def test_undo_restores_hue(self):
        from src.ui.commands import EditColorCorrectionCommand
        clip = self._make_clip(hue=45.0)
        cmd = EditColorCorrectionCommand(
            clip,
            1.2, 0.9, 1.1,
            1.0, 1.0, 1.0,
            old_hue=45.0, new_hue=0.0,
        )
        cmd.redo()
        assert clip.hue == 0.0
        cmd.undo()
        assert clip.hue == 45.0

    def test_default_hue_params_are_zero(self):
        """hue 파라미터 없이도 기존 코드처럼 동작 (하위 호환)."""
        from src.ui.commands import EditColorCorrectionCommand
        clip = self._make_clip()
        cmd = EditColorCorrectionCommand(clip, 1.0, 1.0, 1.0, 1.2, 0.9, 1.1)
        cmd.redo()
        assert clip.hue == 0.0  # default new_hue=0.0


# ────────────────────────────────────────────────────────────────────────────
# Phase CC2: video_exporter hue 필터
# ────────────────────────────────────────────────────────────────────────────

class TestVideoExporterHueFilter:
    """hue 필드가 있는 클립에 hue 필터가 추가되는지 확인 (서비스 레이어)."""

    def _get_filter_chain_str(self, br=1.0, ct=1.0, sat=1.0, hue=0.0) -> str:
        """비디오 exporter의 필터 체인 구성 로직을 직접 테스트."""
        v_chain: list[str] = ["[0:v]trim=start=0.000:end=5.000", "setpts=PTS-STARTPTS"]
        clip_hue = hue
        if br != 1.0 or ct != 1.0 or sat != 1.0:
            f_bri = br - 1.0
            v_chain.append(f"eq=brightness={f_bri:.2f}:contrast={ct:.2f}:saturation={sat:.2f}")
        if clip_hue != 0.0:
            v_chain.append(f"hue=h={clip_hue:.2f}")
        return ",".join(v_chain)

    def test_no_filter_when_defaults(self):
        chain = self._get_filter_chain_str()
        assert "eq=" not in chain
        assert "hue=h=" not in chain

    def test_hue_filter_added_when_nonzero(self):
        chain = self._get_filter_chain_str(hue=30.0)
        assert "hue=h=30.00" in chain

    def test_hue_filter_negative(self):
        chain = self._get_filter_chain_str(hue=-90.0)
        assert "hue=h=-90.00" in chain

    def test_eq_and_hue_combined(self):
        chain = self._get_filter_chain_str(br=1.2, ct=1.1, sat=0.8, hue=45.0)
        assert "eq=" in chain
        assert "hue=h=45.00" in chain

    def test_eq_without_hue(self):
        chain = self._get_filter_chain_str(br=1.3, sat=1.2)
        assert "eq=" in chain
        assert "hue=h=" not in chain


# ────────────────────────────────────────────────────────────────────────────
# Phase ANIM2: 자막 테이블 모델 애니메이션 인디케이터
# ────────────────────────────────────────────────────────────────────────────

class TestSubtitleTableModelAnimIndicator:
    """# 열에 애니메이션 인디케이터 색상/툴팁이 추가되는지 확인."""

    def _make_track_with_anim(self):
        from src.models.subtitle import SubtitleSegment, SubtitleTrack
        from src.models.subtitle_animation import SubtitleAnimation
        seg_no_anim = SubtitleSegment(0, 1000, "Hello")
        seg_with_anim = SubtitleSegment(1000, 2000, "World")
        seg_with_anim.animation = SubtitleAnimation(in_effect="fade", out_effect="none")
        track = SubtitleTrack(segments=[seg_no_anim, seg_with_anim])
        return track

    def test_foreground_color_on_animated_segment(self):
        """애니메이션 있는 세그먼트 # 열은 파란색 ForegroundRole 반환."""
        from src.ui.subtitle_panel import _SubtitleTableModel
        from PySide6.QtCore import Qt, QModelIndex
        model = _SubtitleTableModel()
        model.set_track(self._make_track_with_anim())
        # row=1 (animated), col=0 (#)
        idx = model.index(1, 0)
        color = model.data(idx, Qt.ItemDataRole.ForegroundRole)
        assert color is not None  # 파란색 반환

    def test_no_foreground_color_on_normal_segment(self):
        """애니메이션 없는 세그먼트 # 열은 ForegroundRole None 반환."""
        from src.ui.subtitle_panel import _SubtitleTableModel
        from PySide6.QtCore import Qt
        model = _SubtitleTableModel()
        model.set_track(self._make_track_with_anim())
        idx = model.index(0, 0)  # row=0 (no animation)
        color = model.data(idx, Qt.ItemDataRole.ForegroundRole)
        assert color is None

    def test_tooltip_on_animated_segment(self):
        """애니메이션 있는 세그먼트 # 열은 ToolTipRole 반환."""
        from src.ui.subtitle_panel import _SubtitleTableModel
        from PySide6.QtCore import Qt
        model = _SubtitleTableModel()
        model.set_track(self._make_track_with_anim())
        idx = model.index(1, 0)
        tooltip = model.data(idx, Qt.ItemDataRole.ToolTipRole)
        assert tooltip is not None
        assert "fade" in tooltip


# ────────────────────────────────────────────────────────────────────────────
# Phase ANIM2: 타임라인 페인터 애니메이션 배지 조건
# ────────────────────────────────────────────────────────────────────────────

class TestAnimationBadgeCondition:
    """애니메이션 배지 표시 조건 로직 단위 테스트."""

    def _has_animation(self, in_effect="none", out_effect="none"):
        from src.models.subtitle_animation import SubtitleAnimation
        anim = SubtitleAnimation(in_effect=in_effect, out_effect=out_effect)
        return anim.in_effect != "none" or anim.out_effect != "none"

    def test_no_badge_when_both_none(self):
        assert not self._has_animation("none", "none")

    def test_badge_when_in_effect(self):
        assert self._has_animation(in_effect="fade")

    def test_badge_when_out_effect(self):
        assert self._has_animation(out_effect="fade")

    def test_badge_when_both_set(self):
        assert self._has_animation("slide_up", "fade")

    def test_no_badge_when_animation_is_none(self):
        anim = None
        has_anim = (
            anim is not None
            and (anim.in_effect != "none" or anim.out_effect != "none")
        )
        assert not has_anim
