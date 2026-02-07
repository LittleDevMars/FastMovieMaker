"""Tests for project I/O (save/load with v1/v2 format)."""

import json
import tempfile
from pathlib import Path

import pytest

from src.models.project import ProjectState
from src.models.style import SubtitleStyle
from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.services.project_io import load_project, save_project


@pytest.fixture
def sample_project():
    project = ProjectState()
    project.video_path = Path("/fake/video.mp4")
    project.duration_ms = 10000
    project.default_style = SubtitleStyle(font_size=24, font_color="#FFCC00")
    track = SubtitleTrack(name="Korean", language="ko")
    track.add_segment(SubtitleSegment(0, 2000, "안녕하세요"))
    track.add_segment(SubtitleSegment(3000, 5000, "반갑습니다"))
    project.subtitle_track = track
    return project


class TestSaveLoadV2:
    def test_roundtrip(self, sample_project, tmp_path):
        path = tmp_path / "test.fmm.json"
        save_project(sample_project, path)
        loaded = load_project(path)

        assert loaded.video_path == sample_project.video_path
        assert loaded.duration_ms == 10000
        assert loaded.default_style.font_size == 24
        assert loaded.default_style.font_color == "#FFCC00"
        assert len(loaded.subtitle_track) == 2
        assert loaded.subtitle_track[0].text == "안녕하세요"
        assert loaded.subtitle_track.name == "Korean"
        assert loaded.subtitle_track.language == "ko"

    def test_version_2(self, sample_project, tmp_path):
        path = tmp_path / "test.fmm.json"
        save_project(sample_project, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] == 2
        assert "tracks" in data
        assert "default_style" in data

    def test_multitrack_roundtrip(self, tmp_path):
        project = ProjectState()
        project.video_path = Path("/fake/video.mp4")
        project.duration_ms = 10000

        track1 = SubtitleTrack(name="Korean", language="ko")
        track1.add_segment(SubtitleSegment(0, 2000, "안녕"))
        track2 = SubtitleTrack(name="English", language="en")
        track2.add_segment(SubtitleSegment(0, 2000, "hello"))

        project.subtitle_tracks = [track1, track2]
        project.active_track_index = 1

        path = tmp_path / "test.fmm.json"
        save_project(project, path)
        loaded = load_project(path)

        assert len(loaded.subtitle_tracks) == 2
        assert loaded.active_track_index == 1
        assert loaded.subtitle_tracks[0].name == "Korean"
        assert loaded.subtitle_tracks[1].name == "English"
        assert loaded.subtitle_track[0].text == "hello"

    def test_segment_style_roundtrip(self, tmp_path):
        project = ProjectState()
        project.video_path = Path("/fake/video.mp4")
        style = SubtitleStyle(font_size=30, font_color="#FF0000")
        seg = SubtitleSegment(0, 1000, "styled", style=style)
        track = SubtitleTrack(name="Default")
        track.add_segment(seg)
        project.subtitle_track = track

        path = tmp_path / "test.fmm.json"
        save_project(project, path)
        loaded = load_project(path)

        loaded_seg = loaded.subtitle_track[0]
        assert loaded_seg.style is not None
        assert loaded_seg.style.font_size == 30
        assert loaded_seg.style.font_color == "#FF0000"


class TestV1Migration:
    def test_load_v1_format(self, tmp_path):
        v1_data = {
            "version": 1,
            "video_path": "/fake/video.mp4",
            "duration_ms": 5000,
            "segments": [
                {"start_ms": 0, "end_ms": 2000, "text": "hello"},
                {"start_ms": 3000, "end_ms": 5000, "text": "world"},
            ],
            "language": "en",
        }
        path = tmp_path / "v1.fmm.json"
        path.write_text(json.dumps(v1_data), encoding="utf-8")

        loaded = load_project(path)
        assert loaded.video_path == Path("/fake/video.mp4")
        assert loaded.duration_ms == 5000
        assert len(loaded.subtitle_track) == 2
        assert loaded.subtitle_track[0].text == "hello"
        assert loaded.subtitle_track.language == "en"
        assert loaded.subtitle_track.name == "Default"
        # Default style should be applied
        assert loaded.default_style.font_size == 18
