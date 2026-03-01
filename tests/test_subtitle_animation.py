"""자막 애니메이션 기능 단위 테스트 (Qt 의존 없음)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.models.subtitle_animation import SubtitleAnimation
from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.services.subtitle_exporter import (
    _build_animation_tag,
    _generate_typewriter_events,
)
from src.services.project_io import save_project, load_project
from src.models.project import ProjectState


# ── 1. SubtitleAnimation 기본값 ──────────────────────────────────────────────

def test_default_values():
    anim = SubtitleAnimation()
    assert anim.in_effect == "none"
    assert anim.out_effect == "none"
    assert anim.in_duration_ms == 300
    assert anim.out_duration_ms == 300
    assert anim.slide_offset_px == 60


# ── 2. copy() 독립성 ─────────────────────────────────────────────────────────

def test_copy_independence():
    original = SubtitleAnimation(in_effect="fade", in_duration_ms=500)
    copied = original.copy()
    copied.in_effect = "slide_up"
    copied.in_duration_ms = 200
    assert original.in_effect == "fade"
    assert original.in_duration_ms == 500


# ── 3. fade in 태그 ──────────────────────────────────────────────────────────

def test_fade_in_tag():
    anim = SubtitleAnimation(in_effect="fade", out_effect="none",
                             in_duration_ms=300, out_duration_ms=300)
    tag = _build_animation_tag(anim, 0, 3000, None, 1920, 1080)
    assert "\\fad(300,0)" in tag


# ── 4. fade in + fade out 태그 ───────────────────────────────────────────────

def test_fade_in_out_tag():
    anim = SubtitleAnimation(in_effect="fade", out_effect="fade",
                             in_duration_ms=300, out_duration_ms=200)
    tag = _build_animation_tag(anim, 0, 3000, None, 1920, 1080)
    assert "\\fad(300,200)" in tag


# ── 5. none 효과 → 태그 없음 ─────────────────────────────────────────────────

def test_none_effect_no_tag():
    anim = SubtitleAnimation(in_effect="none", out_effect="none")
    tag = _build_animation_tag(anim, 0, 3000, None, 1920, 1080)
    assert tag == ""


# ── 6. slide_up 태그 ─────────────────────────────────────────────────────────

def test_slide_up_tag():
    anim = SubtitleAnimation(in_effect="slide_up", out_effect="none",
                             in_duration_ms=400, slide_offset_px=60)
    tag = _build_animation_tag(anim, 0, 3000, None, 1920, 1080)
    # slide_up: start_y = ay + offset (아래에서 위로)
    assert "\\move(" in tag
    # 기본 bottom 위치: y = 1080 - 40 = 1040, start_y = 1040 + 60 = 1100
    assert "1100" in tag
    assert "1040" in tag


# ── 7. slide_down 태그 ───────────────────────────────────────────────────────

def test_slide_down_tag():
    anim = SubtitleAnimation(in_effect="slide_down", out_effect="none",
                             in_duration_ms=400, slide_offset_px=60)
    tag = _build_animation_tag(anim, 0, 3000, None, 1920, 1080)
    assert "\\move(" in tag
    # slide_down: start_y = ay - offset (위에서 아래로)
    # ay = 1040, start_y = 1040 - 60 = 980
    assert "980" in tag
    assert "1040" in tag


# ── 8. typewriter 이벤트 개수 ────────────────────────────────────────────────

def test_typewriter_event_count():
    anim = SubtitleAnimation(in_effect="typewriter", out_effect="none",
                             in_duration_ms=500)
    seg = SubtitleSegment(start_ms=0, end_ms=3000, text="hello", animation=anim)
    events = _generate_typewriter_events(seg, "Default", None, anim, 1920, 1080)
    assert len(events) == 5  # "hello" = 5글자


# ── 9. typewriter 누적 텍스트 ────────────────────────────────────────────────

def test_typewriter_cumulative_text():
    anim = SubtitleAnimation(in_effect="typewriter", out_effect="none",
                             in_duration_ms=500)
    seg = SubtitleSegment(start_ms=0, end_ms=3000, text="hi", animation=anim)
    events = _generate_typewriter_events(seg, "Default", None, anim, 1920, 1080)
    assert events[0].endswith("h")
    assert events[1].endswith("hi")


# ── 10. project_io 직렬화 → 역직렬화 동등성 ─────────────────────────────────

def test_project_io_round_trip(tmp_path):
    project = ProjectState()
    anim = SubtitleAnimation(in_effect="fade", out_effect="fade",
                             in_duration_ms=400, out_duration_ms=200, slide_offset_px=80)
    seg = SubtitleSegment(start_ms=0, end_ms=3000, text="Test", animation=anim)
    project.subtitle_tracks[0].add_segment(seg)

    path = tmp_path / "test.fmm.json"
    save_project(project, path)
    loaded = load_project(path)

    loaded_seg = loaded.subtitle_tracks[0][0]
    assert loaded_seg.animation is not None
    a = loaded_seg.animation
    assert a.in_effect == "fade"
    assert a.out_effect == "fade"
    assert a.in_duration_ms == 400
    assert a.out_duration_ms == 200
    assert a.slide_offset_px == 80
