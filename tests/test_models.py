"""Tests for data models."""

from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.models.project import ProjectState
from src.models.style import SubtitleStyle


class TestSubtitleSegment:
    def test_duration(self):
        seg = SubtitleSegment(start_ms=1000, end_ms=3500, text="Hello")
        assert seg.duration_ms == 2500

    def test_text(self):
        seg = SubtitleSegment(start_ms=0, end_ms=1000, text="Test text")
        assert seg.text == "Test text"

    def test_style_default_none(self):
        seg = SubtitleSegment(start_ms=0, end_ms=1000, text="test")
        assert seg.style is None

    def test_style_assignment(self):
        style = SubtitleStyle(font_size=24, font_color="#FF0000")
        seg = SubtitleSegment(start_ms=0, end_ms=1000, text="test", style=style)
        assert seg.style.font_size == 24
        assert seg.style.font_color == "#FF0000"


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

    def test_name_field(self):
        track = SubtitleTrack(name="Korean")
        assert track.name == "Korean"

    def test_name_default_empty(self):
        track = SubtitleTrack()
        assert track.name == ""


class TestSubtitleStyle:
    def test_defaults(self):
        style = SubtitleStyle()
        assert style.font_family == "Arial"
        assert style.font_size == 18
        assert style.font_bold is True
        assert style.font_italic is False
        assert style.font_color == "#FFFFFF"
        assert style.outline_color == "#000000"
        assert style.outline_width == 1
        assert style.bg_color == ""
        assert style.position == "bottom-center"
        assert style.margin_bottom == 40

    def test_copy(self):
        style = SubtitleStyle(font_size=24, font_color="#FF0000")
        copy = style.copy()
        assert copy.font_size == 24
        assert copy.font_color == "#FF0000"
        # Modify copy should not affect original
        copy.font_size = 30
        assert style.font_size == 24

    def test_custom_values(self):
        style = SubtitleStyle(
            font_family="Helvetica",
            font_size=24,
            font_bold=False,
            font_italic=True,
            font_color="#FFCC00",
            outline_color="#333333",
            outline_width=3,
            bg_color="#000000",
            position="top-center",
            margin_bottom=20,
        )
        assert style.font_family == "Helvetica"
        assert style.position == "top-center"
        assert style.outline_width == 3


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

    def test_default_style(self):
        state = ProjectState()
        assert isinstance(state.default_style, SubtitleStyle)
        assert state.default_style.font_size == 18

    def test_subtitle_track_property(self):
        state = ProjectState()
        track = SubtitleTrack(name="Test")
        track.add_segment(SubtitleSegment(0, 1000, "hello"))
        state.subtitle_track = track
        assert state.subtitle_track.name == "Test"
        assert len(state.subtitle_track) == 1

    def test_multitrack(self):
        state = ProjectState()
        assert len(state.subtitle_tracks) == 1
        assert state.active_track_index == 0

        # Add another track
        track2 = SubtitleTrack(name="English")
        track2.add_segment(SubtitleSegment(0, 1000, "hello"))
        state.subtitle_tracks.append(track2)
        state.active_track_index = 1
        assert state.subtitle_track.name == "English"
        assert len(state.subtitle_track) == 1

    def test_reset_clears_tracks(self):
        state = ProjectState()
        state.subtitle_tracks.append(SubtitleTrack(name="Extra"))
        state.active_track_index = 1
        state.reset()
        assert len(state.subtitle_tracks) == 1
        assert state.active_track_index == 0
