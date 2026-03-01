"""tests/test_clip_color_label.py — 클립 컬러 레이블 단위 테스트."""

import pytest

from src.models.video_clip import VideoClip
from src.ui.commands import EditColorLabelCommand


# ── VideoClip 기본값 ───────────────────────────────────────────────────────────


def test_default_color_label():
    """VideoClip 기본 color_label은 'none'이다."""
    clip = VideoClip(source_in_ms=0, source_out_ms=5000)
    assert clip.color_label == "none"


# ── EditColorLabelCommand ─────────────────────────────────────────────────────


def test_edit_color_label_redo():
    """EditColorLabelCommand.redo()는 새 label을 설정한다."""
    clip = VideoClip(source_in_ms=0, source_out_ms=5000)
    cmd = EditColorLabelCommand(clip, "none", "red")
    cmd.redo()
    assert clip.color_label == "red"


def test_edit_color_label_undo():
    """EditColorLabelCommand.undo()는 이전 label로 복원한다."""
    clip = VideoClip(source_in_ms=0, source_out_ms=5000)
    cmd = EditColorLabelCommand(clip, "none", "blue")
    cmd.redo()
    cmd.undo()
    assert clip.color_label == "none"


# ── 직렬화 ───────────────────────────────────────────────────────────────────


def test_to_dict_omits_none():
    """color_label='none'이면 to_dict() 결과에 키가 없다."""
    clip = VideoClip(source_in_ms=0, source_out_ms=3000)
    d = clip.to_dict()
    assert "color_label" not in d


def test_to_dict_includes_label():
    """color_label이 'none'이 아니면 to_dict()에 포함된다."""
    clip = VideoClip(source_in_ms=0, source_out_ms=3000, color_label="green")
    d = clip.to_dict()
    assert d["color_label"] == "green"


def test_from_dict_defaults_none():
    """dict에 color_label 키가 없으면 from_dict()는 'none'을 반환한다."""
    clip = VideoClip.from_dict({"source_in_ms": 0, "source_out_ms": 3000})
    assert clip.color_label == "none"


def test_from_dict_restores_label():
    """dict에 color_label이 있으면 from_dict()가 올바르게 복원한다."""
    clip = VideoClip.from_dict({"source_in_ms": 0, "source_out_ms": 3000, "color_label": "purple"})
    assert clip.color_label == "purple"
