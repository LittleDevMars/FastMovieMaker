"""Tests for per-segment volume feature."""

import json
from pathlib import Path

import pytest

from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.models.project import ProjectState
from src.services.project_io import load_project, save_project


class TestSubtitleSegmentVolume:
    def test_default_volume(self):
        seg = SubtitleSegment(start_ms=0, end_ms=1000, text="hello")
        assert seg.volume == 1.0

    def test_custom_volume(self):
        seg = SubtitleSegment(start_ms=0, end_ms=1000, text="hello", volume=0.5)
        assert seg.volume == 0.5

    def test_volume_max(self):
        seg = SubtitleSegment(start_ms=0, end_ms=1000, text="loud", volume=2.0)
        assert seg.volume == 2.0

    def test_volume_zero(self):
        seg = SubtitleSegment(start_ms=0, end_ms=1000, text="muted", volume=0.0)
        assert seg.volume == 0.0


class TestVolumeProjectIO:
    def test_volume_save_load_roundtrip(self, tmp_path):
        project = ProjectState()
        project.video_path = Path("/fake/video.mp4")
        track = SubtitleTrack(name="Test")
        track.add_segment(SubtitleSegment(0, 1000, "normal"))
        track.add_segment(SubtitleSegment(1000, 2000, "quiet", volume=0.5))
        track.add_segment(SubtitleSegment(2000, 3000, "loud", volume=1.5))
        project.subtitle_track = track

        path = tmp_path / "test.fmm.json"
        save_project(project, path)
        loaded = load_project(path)

        assert loaded.subtitle_track[0].volume == 1.0
        assert loaded.subtitle_track[1].volume == 0.5
        assert loaded.subtitle_track[2].volume == 1.5

    def test_volume_default_not_saved(self, tmp_path):
        """Volume=1.0 should not appear in JSON to save space."""
        project = ProjectState()
        project.video_path = Path("/fake/video.mp4")
        track = SubtitleTrack(name="Test")
        track.add_segment(SubtitleSegment(0, 1000, "normal"))
        project.subtitle_track = track

        path = tmp_path / "test.fmm.json"
        save_project(project, path)

        data = json.loads(path.read_text(encoding="utf-8"))
        seg_data = data["tracks"][0]["segments"][0]
        assert "volume" not in seg_data

    def test_volume_non_default_saved(self, tmp_path):
        """Non-default volume should appear in JSON."""
        project = ProjectState()
        project.video_path = Path("/fake/video.mp4")
        track = SubtitleTrack(name="Test")
        track.add_segment(SubtitleSegment(0, 1000, "quiet", volume=0.7))
        project.subtitle_track = track

        path = tmp_path / "test.fmm.json"
        save_project(project, path)

        data = json.loads(path.read_text(encoding="utf-8"))
        seg_data = data["tracks"][0]["segments"][0]
        assert seg_data["volume"] == 0.7

    def test_backward_compatibility_no_volume(self, tmp_path):
        """Old project files without volume field should load with default 1.0."""
        old_data = {
            "version": 2,
            "video_path": "/fake/video.mp4",
            "duration_ms": 5000,
            "default_style": {"font_size": 18},
            "active_track_index": 0,
            "tracks": [{
                "name": "Old",
                "language": "",
                "audio_path": "",
                "audio_start_ms": 0,
                "audio_duration_ms": 0,
                "segments": [
                    {"start_ms": 0, "end_ms": 1000, "text": "old segment"}
                ],
            }],
        }
        path = tmp_path / "old.fmm.json"
        path.write_text(json.dumps(old_data), encoding="utf-8")

        loaded = load_project(path)
        assert loaded.subtitle_track[0].volume == 1.0


class TestEditVolumeCommand:
    def test_undo_redo(self):
        from src.ui.commands import EditVolumeCommand

        track = SubtitleTrack()
        track.add_segment(SubtitleSegment(0, 1000, "test", volume=1.0))

        cmd = EditVolumeCommand(track, 0, 1.0, 0.5)
        cmd.redo()
        assert track[0].volume == 0.5

        cmd.undo()
        assert track[0].volume == 1.0

    def test_bounds_check(self):
        from src.ui.commands import EditVolumeCommand

        track = SubtitleTrack()
        track.add_segment(SubtitleSegment(0, 1000, "test"))

        # Out-of-bounds index should not crash
        cmd = EditVolumeCommand(track, 5, 1.0, 0.5)
        cmd.redo()  # Should not raise
        cmd.undo()  # Should not raise
