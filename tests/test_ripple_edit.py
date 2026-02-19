"""Tests for RippleEditService and DeleteClipCommand BGM/text ripple."""

from __future__ import annotations

import pytest

from src.models.audio import AudioClip, AudioTrack
from src.models.image_overlay import ImageOverlay, ImageOverlayTrack
from src.models.project import ProjectState
from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.models.text_overlay import TextOverlay, TextOverlayTrack
from src.models.video_clip import VideoClip, VideoClipTrack
from src.services.ripple_edit_service import RippleEditService


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_segment(start: int, end: int) -> SubtitleSegment:
    return SubtitleSegment(start_ms=start, end_ms=end, text="x")


def _make_bgm_clip(start: int, dur: int = 2000) -> AudioClip:
    clip = AudioClip(source_path="bgm.mp3", duration_ms=dur)
    clip.start_ms = start
    return clip


def _make_text_overlay(start: int, end: int) -> TextOverlay:
    return TextOverlay(start_ms=start, end_ms=end, text="overlay")


def _make_project_with_bgm_and_text() -> ProjectState:
    """프로젝트: 자막 1개, BGM 클립 3개, 텍스트 오버레이 2개."""
    project = ProjectState()

    # 자막
    track = project.subtitle_tracks[0]
    track.segments = [
        _make_segment(0, 1000),
        _make_segment(5000, 6000),  # ripple_start_ms=3000 이후
        _make_segment(8000, 9000),  # 이후
    ]

    # BGM
    bgm_track = project.bgm_tracks[0]
    bgm_track.clips = [
        _make_bgm_clip(1000),   # 이전 → 이동 안 함
        _make_bgm_clip(3000),   # 경계 → 이동
        _make_bgm_clip(7000),   # 이후 → 이동
    ]

    # 텍스트 오버레이
    tt = TextOverlayTrack()
    tt.overlays = [
        _make_text_overlay(2000, 2500),   # 이전 → 이동 안 함
        _make_text_overlay(4000, 5000),   # 이후 → 이동
    ]
    project.text_overlay_track = tt

    return project


# ── RippleEditService ─────────────────────────────────────────────────────────

class TestRippleEditService:
    def test_push_subtitles(self):
        project = ProjectState()
        track = project.subtitle_tracks[0]
        track.segments = [
            _make_segment(0, 1000),
            _make_segment(3000, 4000),
            _make_segment(5000, 6000),
        ]
        count = RippleEditService.apply_ripple(project, ripple_start_ms=2000, delta_ms=1000)
        assert project.subtitle_tracks[0].segments[0].start_ms == 0   # 불변
        assert project.subtitle_tracks[0].segments[1].start_ms == 4000  # 이동
        assert project.subtitle_tracks[0].segments[2].start_ms == 6000  # 이동
        assert count == 2

    def test_pull_subtitles(self):
        project = ProjectState()
        track = project.subtitle_tracks[0]
        track.segments = [_make_segment(5000, 6000)]
        RippleEditService.apply_ripple(project, ripple_start_ms=3000, delta_ms=-2000)
        assert track.segments[0].start_ms == 3000

    def test_push_bgm_clips(self):
        project = _make_project_with_bgm_and_text()
        RippleEditService.apply_ripple(project, ripple_start_ms=3000, delta_ms=2000)
        clips = project.bgm_tracks[0].clips
        assert clips[0].start_ms == 1000   # 이전: 불변
        assert clips[1].start_ms == 5000   # 3000 → 5000
        assert clips[2].start_ms == 9000   # 7000 → 9000

    def test_push_text_overlays(self):
        project = _make_project_with_bgm_and_text()
        RippleEditService.apply_ripple(project, ripple_start_ms=3000, delta_ms=1000)
        overlays = project.text_overlay_track.overlays
        assert overlays[0].start_ms == 2000   # 이전: 불변
        assert overlays[1].start_ms == 5000   # 4000 → 5000

    def test_zero_delta_returns_zero(self):
        project = ProjectState()
        count = RippleEditService.apply_ripple(project, ripple_start_ms=0, delta_ms=0)
        assert count == 0

    def test_locked_track_skipped(self):
        project = _make_project_with_bgm_and_text()
        project.bgm_tracks[0].locked = True
        RippleEditService.apply_ripple(project, ripple_start_ms=0, delta_ms=1000)
        # locked이므로 변경 없음
        assert project.bgm_tracks[0].clips[0].start_ms == 1000


# ── DeleteClipCommand BGM/Text Ripple ────────────────────────────────────────

class TestDeleteClipCommandBGMRipple:
    def _make_project(self) -> tuple[ProjectState, int, int]:
        """클립 2개(각 5000ms), BGM 클립, 텍스트 오버레이가 있는 프로젝트."""
        project = ProjectState()

        clip_a = VideoClip(source_in_ms=0, source_out_ms=5000)
        clip_b = VideoClip(source_in_ms=0, source_out_ms=5000)
        project.video_tracks[0].clips = [clip_a, clip_b]

        track = project.subtitle_tracks[0]
        track.segments = [_make_segment(6000, 7000)]

        bgm_track = project.bgm_tracks[0]
        bgm_track.clips = [_make_bgm_clip(6000)]

        tt = TextOverlayTrack()
        tt.overlays = [_make_text_overlay(6000, 7000)]
        project.text_overlay_track = tt

        return project, 0, 5000  # clip_start=0, clip_end=5000

    def test_redo_shifts_bgm_after_delete(self):
        from src.ui.commands import DeleteClipCommand
        project, clip_start, clip_end = self._make_project()

        removed = project.video_tracks[0].clips[0]
        cmd = DeleteClipCommand(
            project, 0, 0, removed,
            project.subtitle_tracks[0],
            project.image_overlay_track,
            clip_start_tl=clip_start,
            clip_end_tl=clip_end,
            ripple=True,
        )
        cmd.redo()

        assert project.bgm_tracks[0].clips[0].start_ms == 1000  # 6000 - 5000

    def test_redo_shifts_text_overlay_after_delete(self):
        from src.ui.commands import DeleteClipCommand
        project, clip_start, clip_end = self._make_project()

        removed = project.video_tracks[0].clips[0]
        cmd = DeleteClipCommand(
            project, 0, 0, removed,
            project.subtitle_tracks[0],
            project.image_overlay_track,
            clip_start_tl=clip_start,
            clip_end_tl=clip_end,
            ripple=True,
        )
        cmd.redo()

        assert project.text_overlay_track.overlays[0].start_ms == 1000

    def test_undo_restores_bgm(self):
        from src.ui.commands import DeleteClipCommand
        project, clip_start, clip_end = self._make_project()

        removed = project.video_tracks[0].clips[0]
        cmd = DeleteClipCommand(
            project, 0, 0, removed,
            project.subtitle_tracks[0],
            project.image_overlay_track,
            clip_start_tl=clip_start,
            clip_end_tl=clip_end,
            ripple=True,
        )
        cmd.redo()
        cmd.undo()

        assert project.bgm_tracks[0].clips[0].start_ms == 6000
        assert project.text_overlay_track.overlays[0].start_ms == 6000

    def test_no_ripple_leaves_bgm_unchanged(self):
        from src.ui.commands import DeleteClipCommand
        project, clip_start, clip_end = self._make_project()

        removed = project.video_tracks[0].clips[0]
        cmd = DeleteClipCommand(
            project, 0, 0, removed,
            project.subtitle_tracks[0],
            project.image_overlay_track,
            clip_start_tl=clip_start,
            clip_end_tl=clip_end,
            ripple=False,
        )
        cmd.redo()

        assert project.bgm_tracks[0].clips[0].start_ms == 6000  # 변화 없음
