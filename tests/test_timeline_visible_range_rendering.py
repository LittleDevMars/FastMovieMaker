"""Tests for visible-range rendering in TimelinePainter."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from src.models.style import SubtitleStyle
from src.models.subtitle import SubtitleSegment
from src.ui.timeline_painter import TimelinePainter


_app = QApplication.instance() or QApplication([])


class _TrackSpy:
    def __init__(self, segments: list[SubtitleSegment], visible: tuple[int, int]):
        self._segments = segments
        self._visible = visible
        self.accessed: list[int] = []
        self.visible_args: tuple[int, int] | None = None
        self.visible_call_count: int = 0
        self.hidden: bool = False

    def __bool__(self) -> bool:
        return True

    def __getitem__(self, index: int) -> SubtitleSegment:
        self.accessed.append(index)
        return self._segments[index]

    def visible_range_indices(self, start_ms: int, end_ms: int) -> tuple[int, int]:
        self.visible_args = (start_ms, end_ms)
        self.visible_call_count += 1
        return self._visible


@dataclass
class _TwStub:
    _track: _TrackSpy
    _selected_index: int = -1
    _selected_overlay_index: int = -1
    _selected_clip_index: int = -1
    _selected_clip_track_index: int = -1
    _selected_clips: set[tuple[int, int]] | None = None
    _visible_start_ms: int = 1000
    _project: object | None = None
    _image_overlay_track: object | None = None
    _clip_track: object | None = None
    _has_video: bool = False
    _waveform_data: object | None = None

    def __post_init__(self) -> None:
        if self._selected_clips is None:
            self._selected_clips = set()

    def _visible_range_ms(self) -> int:
        return 2000

    def _subtitle_track_y(self) -> int:
        return 20

    def _audio_track_y(self) -> int:
        return 70

    def _ms_to_x(self, ms: int) -> float:
        return float(ms - self._visible_start_ms)

    def width(self) -> int:
        return 400


def test_draw_segments_uses_visible_range_indices() -> None:
    segments = [
        SubtitleSegment(0, 500, "off-left"),
        SubtitleSegment(1100, 1300, "one"),
        SubtitleSegment(1400, 1700, "two"),
        SubtitleSegment(4000, 4500, "off-right"),
    ]
    track = _TrackSpy(segments, (1, 3))
    tw = _TwStub(_track=track)
    painter_obj = TimelinePainter(tw)  # type: ignore[arg-type]

    img = QImage(500, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    painter_obj._draw_segments(painter, 200)
    painter.end()

    assert track.visible_args == (1000, 3000)
    assert track.accessed == [1, 2]


def test_draw_audio_track_uses_visible_range_indices() -> None:
    segments = [
        SubtitleSegment(0, 500, "off-left", audio_file="a.mp3"),
        SubtitleSegment(1100, 1300, "one", audio_file="b.mp3"),
        SubtitleSegment(1400, 1700, "two", audio_file="c.mp3"),
        SubtitleSegment(4000, 4500, "off-right", audio_file="d.mp3"),
    ]
    track = _TrackSpy(segments, (1, 3))
    tw = _TwStub(_track=track)
    painter_obj = TimelinePainter(tw)  # type: ignore[arg-type]

    img = QImage(500, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    painter_obj._draw_audio_track(painter, 200)
    painter.end()

    assert track.visible_args == (1000, 3000)
    assert track.accessed == [1, 2]


def test_draw_paths_reuse_visible_window_cache_in_same_viewport() -> None:
    segments = [
        SubtitleSegment(1100, 1300, "one", audio_file="b.mp3"),
        SubtitleSegment(1400, 1700, "two", audio_file="c.mp3"),
    ]
    track = _TrackSpy(segments, (0, 2))
    tw = _TwStub(_track=track)
    painter_obj = TimelinePainter(tw)  # type: ignore[arg-type]

    img = QImage(500, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    painter_obj._draw_audio_track(painter, 200)
    painter_obj._draw_segments(painter, 200)
    painter.end()

    assert track.visible_call_count == 1


def test_static_cache_key_changes_when_visible_segment_text_or_style_changes() -> None:
    segments = [
        SubtitleSegment(1100, 1300, "one"),
        SubtitleSegment(1400, 1700, "two"),
    ]
    track = _TrackSpy(segments, (0, 2))
    tw = _TwStub(_track=track)
    painter_obj = TimelinePainter(tw)  # type: ignore[arg-type]

    key_before = painter_obj._build_static_cache_key(400, 120, 2000)
    segments[0].text = "changed"
    key_after_text = painter_obj._build_static_cache_key(400, 120, 2000)
    assert key_before != key_after_text

    segments[0].style = SubtitleStyle(font_size=22)
    key_after_style = painter_obj._build_static_cache_key(400, 120, 2000)
    assert key_after_text != key_after_style


def test_static_cache_key_changes_when_selection_or_zoom_changes() -> None:
    segments = [SubtitleSegment(1100, 1300, "one")]
    track = _TrackSpy(segments, (0, 1))
    tw = _TwStub(_track=track)
    painter_obj = TimelinePainter(tw)  # type: ignore[arg-type]

    key_before = painter_obj._build_static_cache_key(400, 120, 2000)
    tw._selected_index = 0
    key_selected = painter_obj._build_static_cache_key(400, 120, 2000)
    assert key_before != key_selected

    tw._visible_start_ms = 1200
    key_zoom = painter_obj._build_static_cache_key(400, 120, 1800)
    assert key_selected != key_zoom


def test_static_cache_key_stable_when_inputs_unchanged() -> None:
    segments = [SubtitleSegment(1100, 1300, "one")]
    track = _TrackSpy(segments, (0, 1))
    tw = _TwStub(_track=track)
    painter_obj = TimelinePainter(tw)  # type: ignore[arg-type]

    key1 = painter_obj._build_static_cache_key(400, 120, 2000)
    key2 = painter_obj._build_static_cache_key(400, 120, 2000)
    assert key1 == key2


def test_large_segment_set_uses_visible_window_only() -> None:
    segments = [SubtitleSegment(i * 10, i * 10 + 8, f"s{i}") for i in range(5000)]
    track = _TrackSpy(segments, (2500, 2510))
    tw = _TwStub(_track=track)
    painter_obj = TimelinePainter(tw)  # type: ignore[arg-type]

    img = QImage(500, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    painter_obj._draw_segments(painter, 200)
    painter.end()

    assert len(track.accessed) == 10
    assert track.accessed[0] == 2500
    assert track.accessed[-1] == 2509
