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
        assert data["version"] == 4
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


class TestAudioTimeline:
    """Tests for audio timeline save/load."""

    def test_audio_timeline_roundtrip(self, tmp_path):
        """Test saving and loading audio timeline information."""
        project = ProjectState()
        project.video_path = Path("/fake/video.mp4")
        project.duration_ms = 30000

        track = SubtitleTrack(
            name="TTS Track",
            audio_path="/tmp/tts_audio.mp3",
            audio_start_ms=1000,
            audio_duration_ms=25000,
        )
        track.add_segment(SubtitleSegment(1000, 3000, "First"))
        track.add_segment(SubtitleSegment(3000, 5000, "Second"))

        project.subtitle_track = track

        path = tmp_path / "test_audio.fmm.json"
        save_project(project, path)
        loaded = load_project(path)

        assert loaded.subtitle_track.audio_path == "/tmp/tts_audio.mp3"
        assert loaded.subtitle_track.audio_start_ms == 1000
        assert loaded.subtitle_track.audio_duration_ms == 25000

    def test_audio_timeline_json_structure(self, tmp_path):
        """Test JSON structure includes audio timeline fields."""
        project = ProjectState()
        track = SubtitleTrack(
            name="Test",
            audio_path="/tmp/audio.mp3",
            audio_start_ms=500,
            audio_duration_ms=10000,
        )
        project.subtitle_track = track

        path = tmp_path / "test.fmm.json"
        save_project(project, path)

        data = json.loads(path.read_text(encoding="utf-8"))
        track_data = data["tracks"][0]

        assert "audio_path" in track_data
        assert "audio_start_ms" in track_data
        assert "audio_duration_ms" in track_data
        assert track_data["audio_path"] == "/tmp/audio.mp3"
        assert track_data["audio_start_ms"] == 500
        assert track_data["audio_duration_ms"] == 10000

    def test_audio_timeline_multitrack(self, tmp_path):
        """Test audio timeline with multiple tracks."""
        project = ProjectState()
        project.duration_ms = 50000

        # Track 1: TTS with audio
        track1 = SubtitleTrack(
            name="TTS Korean",
            audio_path="/tmp/korean.mp3",
            audio_start_ms=0,
            audio_duration_ms=20000,
        )
        track1.add_segment(SubtitleSegment(0, 5000, "안녕하세요"))

        # Track 2: No audio
        track2 = SubtitleTrack(name="English")
        track2.add_segment(SubtitleSegment(0, 5000, "Hello"))

        # Track 3: TTS with different timing
        track3 = SubtitleTrack(
            name="TTS English",
            audio_path="/tmp/english.mp3",
            audio_start_ms=5000,
            audio_duration_ms=15000,
        )
        track3.add_segment(SubtitleSegment(5000, 10000, "Welcome"))

        project.subtitle_tracks = [track1, track2, track3]
        project.active_track_index = 0

        path = tmp_path / "test_multi.fmm.json"
        save_project(project, path)
        loaded = load_project(path)

        assert len(loaded.subtitle_tracks) == 3

        # Check track 1
        assert loaded.subtitle_tracks[0].audio_path == "/tmp/korean.mp3"
        assert loaded.subtitle_tracks[0].audio_start_ms == 0
        assert loaded.subtitle_tracks[0].audio_duration_ms == 20000

        # Check track 2 (no audio)
        assert loaded.subtitle_tracks[1].audio_path == ""
        assert loaded.subtitle_tracks[1].audio_start_ms == 0
        assert loaded.subtitle_tracks[1].audio_duration_ms == 0

        # Check track 3
        assert loaded.subtitle_tracks[2].audio_path == "/tmp/english.mp3"
        assert loaded.subtitle_tracks[2].audio_start_ms == 5000
        assert loaded.subtitle_tracks[2].audio_duration_ms == 15000

    def test_audio_timeline_backward_compatibility(self, tmp_path):
        """Test loading old projects without audio timeline fields."""
        # Create a v2 project without audio timeline fields
        old_data = {
            "version": 2,
            "video_path": "/fake/video.mp4",
            "duration_ms": 10000,
            "default_style": {"font_size": 18, "font_color": "#FFFFFF"},
            "active_track_index": 0,
            "tracks": [
                {
                    "name": "Old Track",
                    "language": "ko",
                    "audio_path": "",
                    # audio_start_ms and audio_duration_ms missing
                    "segments": [
                        {"start_ms": 0, "end_ms": 2000, "text": "test"}
                    ],
                }
            ],
        }

        path = tmp_path / "old.fmm.json"
        path.write_text(json.dumps(old_data), encoding="utf-8")

        loaded = load_project(path)
        assert loaded.subtitle_track.audio_start_ms == 0  # Default value
        assert loaded.subtitle_track.audio_duration_ms == 0  # Default value


class TestVideoClipTrack:
    """Tests for video clip track save/load."""

    def test_clip_track_roundtrip(self, tmp_path):
        from src.models.video_clip import VideoClip, VideoClipTrack
        project = ProjectState()
        project.video_path = Path("/fake/video.mp4")
        project.duration_ms = 30000
        project.video_clip_track = VideoClipTrack(clips=[
            VideoClip(0, 10000),
            VideoClip(15000, 25000),
        ])
        track = SubtitleTrack(name="Default")
        track.add_segment(SubtitleSegment(0, 5000, "hello"))
        project.subtitle_track = track

        path = tmp_path / "test_clips.fmm.json"
        save_project(project, path)
        loaded = load_project(path)

        assert loaded.video_clip_track is not None
        assert len(loaded.video_clip_track.clips) == 2
        assert loaded.video_clip_track.clips[0].source_in_ms == 0
        assert loaded.video_clip_track.clips[0].source_out_ms == 10000
        assert loaded.video_clip_track.clips[1].source_in_ms == 15000
        assert loaded.video_clip_track.clips[1].source_out_ms == 25000
        assert loaded.video_clip_track.output_duration_ms == 20000

    def test_no_clip_track_backward_compat(self, tmp_path):
        """v2 projects without video_clips should load with clip_track=None."""
        old_data = {
            "version": 2,
            "video_path": "/fake/video.mp4",
            "duration_ms": 10000,
            "default_style": {"font_size": 18, "font_color": "#FFFFFF"},
            "active_track_index": 0,
            "tracks": [
                {
                    "name": "Default",
                    "language": "",
                    "audio_path": "",
                    "segments": [],
                }
            ],
        }
        path = tmp_path / "v2.fmm.json"
        path.write_text(json.dumps(old_data), encoding="utf-8")
        loaded = load_project(path)
        assert loaded.video_clip_track is None

    def test_clip_track_json_structure(self, tmp_path):
        from src.models.video_clip import VideoClip, VideoClipTrack
        project = ProjectState()
        project.video_clip_track = VideoClipTrack(clips=[
            VideoClip(1000, 5000),
        ])
        track = SubtitleTrack(name="Default")
        project.subtitle_track = track

        path = tmp_path / "test.fmm.json"
        save_project(project, path)
        data = json.loads(path.read_text(encoding="utf-8"))

        assert data["version"] == 4
        assert "video_clips" in data
        assert len(data["video_clips"]) == 1
        assert data["video_clips"][0]["source_in_ms"] == 1000
        assert data["video_clips"][0]["source_out_ms"] == 5000

    def test_v4_source_path_roundtrip(self, tmp_path):
        """source_path should survive save/load."""
        from src.models.video_clip import VideoClip, VideoClipTrack
        project = ProjectState()
        project.video_clip_track = VideoClipTrack(clips=[
            VideoClip(0, 5000),
            VideoClip(0, 3000, source_path="D:/extra.mp4"),
        ])
        track = SubtitleTrack(name="Default")
        project.subtitle_track = track

        path = tmp_path / "test_v4.fmm.json"
        save_project(project, path)

        loaded = load_project(path)
        assert loaded.video_clip_track is not None
        assert len(loaded.video_clip_track.clips) == 2
        assert loaded.video_clip_track.clips[0].source_path is None
        assert loaded.video_clip_track.clips[1].source_path == "D:/extra.mp4"

    def test_v3_compat_no_source_path(self, tmp_path):
        """v3 project without source_path should load with source_path=None."""
        v3_data = {
            "version": 3,
            "video_path": None,
            "duration_ms": 10000,
            "default_style": {},
            "active_track_index": 0,
            "tracks": [{"name": "Default", "language": "", "segments": []}],
            "image_overlays": [],
            "video_clips": [
                {"source_in_ms": 0, "source_out_ms": 10000},
            ],
        }
        path = tmp_path / "v3_compat.fmm.json"
        path.write_text(json.dumps(v3_data), encoding="utf-8")

        loaded = load_project(path)
        assert loaded.video_clip_track is not None
        assert loaded.video_clip_track.clips[0].source_path is None
