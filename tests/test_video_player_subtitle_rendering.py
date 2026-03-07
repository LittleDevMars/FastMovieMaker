"""Regression tests for subtitle rendering cache behavior in VideoPlayerWidget."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from src.models.style import SubtitleStyle
from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.ui.video_player_widget import VideoPlayerWidget


_app = QApplication.instance() or QApplication([])


class _FakePlayer(QObject):
    positionChanged = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._pos = 0
        self._output = None

    def setVideoOutput(self, output) -> None:
        self._output = output

    def position(self) -> int:
        return self._pos

    def set_position(self, ms: int) -> None:
        self._pos = ms
        self.positionChanged.emit(ms)


def test_subtitle_updates_when_style_changes_with_same_text(qtbot) -> None:
    player = _FakePlayer()
    widget = VideoPlayerWidget(player)
    qtbot.addWidget(widget)

    style_a = SubtitleStyle(font_size=18)
    style_b = SubtitleStyle(font_size=30)
    track = SubtitleTrack()
    seg = SubtitleSegment(0, 1000, "same-text", style=style_a)
    track.add_segment(seg)
    widget.set_subtitle_track(track)

    widget._update_subtitle(100)
    assert widget._subtitle_item.font().pointSize() == 18

    seg.style = style_b
    widget._update_subtitle(100)
    assert widget._subtitle_item.font().pointSize() == 30


def test_subtitle_does_not_reapply_style_when_text_and_style_unchanged(qtbot, monkeypatch) -> None:
    player = _FakePlayer()
    widget = VideoPlayerWidget(player)
    qtbot.addWidget(widget)

    calls = {"count": 0}
    orig = widget._apply_style

    def _spy(style):
        calls["count"] += 1
        return orig(style)

    monkeypatch.setattr(widget, "_apply_style", _spy)

    track = SubtitleTrack()
    seg = SubtitleSegment(0, 1000, "stable", style=SubtitleStyle(font_size=20))
    track.add_segment(seg)
    widget.set_subtitle_track(track)

    widget._update_subtitle(100)
    widget._update_subtitle(100)

    assert calls["count"] == 1
