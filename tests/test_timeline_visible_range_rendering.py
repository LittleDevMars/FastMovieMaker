"""Tests for visible-range rendering in TimelinePainter."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from src.models.subtitle import SubtitleSegment
from src.ui.timeline_painter import TimelinePainter


_app = QApplication.instance() or QApplication([])


class _TrackSpy:
    def __init__(self, segments: list[SubtitleSegment], visible: tuple[int, int]):
        self._segments = segments
        self._visible = visible
        self.accessed: list[int] = []
        self.visible_args: tuple[int, int] | None = None

    def __bool__(self) -> bool:
        return True

    def __getitem__(self, index: int) -> SubtitleSegment:
        self.accessed.append(index)
        return self._segments[index]

    def visible_range_indices(self, start_ms: int, end_ms: int) -> tuple[int, int]:
        self.visible_args = (start_ms, end_ms)
        return self._visible


@dataclass
class _TwStub:
    _track: _TrackSpy
    _selected_index: int = -1
    _visible_start_ms: int = 1000

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
