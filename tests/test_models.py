"""Tests for data models."""

from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.models.project import ProjectState


class TestSubtitleSegment:
    def test_duration(self):
        seg = SubtitleSegment(start_ms=1000, end_ms=3500, text="Hello")
        assert seg.duration_ms == 2500

    def test_text(self):
        seg = SubtitleSegment(start_ms=0, end_ms=1000, text="Test text")
        assert seg.text == "Test text"


class TestSubtitleTrack:
    def test_empty(self):
        track = SubtitleTrack()
        assert len(track) == 0
        assert track.segment_at(500) is None

    def test_add_and_sort(self):
        track = SubtitleTrack()
        track.add_segment(SubtitleSegment(5000, 8000, "second"))
        track.add_segment(SubtitleSegment(1000, 4000, "first"))
        assert track[0].text == "first"
        assert track[1].text == "second"

    def test_segment_at(self):
        track = SubtitleTrack()
        track.add_segment(SubtitleSegment(1000, 4000, "hello"))
        track.add_segment(SubtitleSegment(5000, 8000, "world"))

        assert track.segment_at(0) is None
        assert track.segment_at(1000).text == "hello"
        assert track.segment_at(3999).text == "hello"
        assert track.segment_at(4000) is None
        assert track.segment_at(5000).text == "world"

    def test_clear(self):
        track = SubtitleTrack()
        track.add_segment(SubtitleSegment(0, 1000, "x"))
        track.clear()
        assert len(track) == 0

    def test_iteration(self):
        track = SubtitleTrack()
        track.add_segment(SubtitleSegment(0, 1000, "a"))
        track.add_segment(SubtitleSegment(1000, 2000, "b"))
        texts = [seg.text for seg in track]
        assert texts == ["a", "b"]


class TestProjectState:
    def test_initial(self):
        state = ProjectState()
        assert not state.has_video
        assert not state.has_subtitles

    def test_reset(self):
        state = ProjectState()
        state.video_path = "test.mp4"
        state.duration_ms = 5000
        state.reset()
        assert state.video_path is None
        assert state.duration_ms == 0
