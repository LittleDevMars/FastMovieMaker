"""Custom-painted timeline widget showing subtitle blocks and playhead."""

from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import Qt, Signal, QPoint, QRectF
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPolygon,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from src.models.subtitle import SubtitleTrack
from src.utils.config import TIMELINE_HEIGHT
from src.utils.time_utils import ms_to_display


class _DragMode(Enum):
    NONE = auto()
    SEEK = auto()
    MOVE = auto()
    RESIZE_LEFT = auto()
    RESIZE_RIGHT = auto()


_EDGE_PX = 6  # pixels from segment edge that trigger resize


class TimelineWidget(QWidget):
    """Timeline bar showing subtitle segments with zoom, scroll, click-to-seek,
    and drag-move / drag-resize of segments."""

    seek_requested = Signal(int)  # ms
    segment_selected = Signal(int)  # segment index
    segment_moved = Signal(int, int, int)  # (index, new_start_ms, new_end_ms)

    # Colors
    _BG_COLOR = QColor(30, 30, 30)
    _RULER_COLOR = QColor(100, 100, 100)
    _RULER_TEXT_COLOR = QColor(170, 170, 170)
    _SEGMENT_COLOR = QColor(60, 140, 220, 180)
    _SEGMENT_BORDER = QColor(80, 170, 255)
    _SELECTED_COLOR = QColor(100, 200, 255, 200)
    _SELECTED_BORDER = QColor(150, 220, 255)
    _PLAYHEAD_COLOR = QColor(255, 60, 60)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(TIMELINE_HEIGHT)
        self.setMouseTracking(True)

        self._track: SubtitleTrack | None = None
        self._duration_ms: int = 0
        self._playhead_ms: int = 0

        # Zoom/scroll
        self._visible_start_ms: float = 0.0
        self._px_per_ms: float = 0.0

        # Selection
        self._selected_index: int = -1

        # Drag state
        self._drag_mode = _DragMode.NONE
        self._drag_seg_index: int = -1
        self._drag_start_x: float = 0.0
        self._drag_orig_start_ms: int = 0
        self._drag_orig_end_ms: int = 0

    # -------------------------------------------------------- Public API

    def set_track(self, track: SubtitleTrack | None) -> None:
        self._track = track
        self._selected_index = -1
        self.update()

    def set_duration(self, duration_ms: int) -> None:
        self._duration_ms = duration_ms
        self._visible_start_ms = 0
        self.update()

    def set_playhead(self, position_ms: int) -> None:
        self._playhead_ms = position_ms
        visible_range = self._visible_range_ms()
        if visible_range > 0:
            if position_ms > self._visible_start_ms + visible_range * 0.8:
                self._visible_start_ms = position_ms - visible_range * 0.2
            elif position_ms < self._visible_start_ms:
                self._visible_start_ms = max(0, position_ms - visible_range * 0.1)
        self.update()

    def refresh(self) -> None:
        """Repaint after external model changes."""
        self.update()

    def select_segment(self, index: int) -> None:
        self._selected_index = index
        self.update()

    # ----------------------------------------------------------- Paint

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()

        painter.fillRect(0, 0, w, h, self._BG_COLOR)

        if self._duration_ms <= 0:
            painter.setPen(self._RULER_TEXT_COLOR)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No video loaded")
            painter.end()
            return

        visible_ms = self._visible_range_ms()
        if visible_ms <= 0:
            visible_ms = self._duration_ms
        self._px_per_ms = w / visible_ms

        self._draw_ruler(painter, w, h, visible_ms)
        if self._track:
            self._draw_segments(painter, h)
        self._draw_playhead(painter, h)
        painter.end()

    def _draw_ruler(self, painter: QPainter, w: int, h: int, visible_ms: float) -> None:
        painter.setPen(QPen(self._RULER_COLOR, 1))
        painter.setFont(QFont("Arial", 8))
        tick_ms = self._nice_tick_interval(visible_ms)
        if tick_ms <= 0:
            return
        start_tick = int(self._visible_start_ms / tick_ms) * tick_ms
        if start_tick < self._visible_start_ms:
            start_tick += tick_ms
        t = start_tick
        while t <= self._visible_start_ms + visible_ms:
            x = self._ms_to_x(t)
            painter.setPen(QPen(self._RULER_COLOR, 1))
            painter.drawLine(int(x), 0, int(x), 14)
            painter.setPen(self._RULER_TEXT_COLOR)
            painter.drawText(int(x) + 3, 12, ms_to_display(int(t)))
            t += tick_ms

    def _draw_segments(self, painter: QPainter, h: int) -> None:
        seg_y = 20
        seg_h = h - 30

        for i, seg in enumerate(self._track):
            x1 = self._ms_to_x(seg.start_ms)
            x2 = self._ms_to_x(seg.end_ms)
            if x2 < 0 or x1 > self.width():
                continue

            rect = QRectF(x1, seg_y, max(x2 - x1, 2), seg_h)

            if i == self._selected_index:
                painter.setPen(QPen(self._SELECTED_BORDER, 2))
                painter.setBrush(QBrush(self._SELECTED_COLOR))
            else:
                painter.setPen(QPen(self._SEGMENT_BORDER, 1))
                painter.setBrush(QBrush(self._SEGMENT_COLOR))
            painter.drawRoundedRect(rect, 3, 3)

            if rect.width() > 30:
                painter.setPen(QColor("white"))
                painter.setFont(QFont("Arial", 8))
                text_rect = rect.adjusted(4, 2, -4, -2)
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    painter.fontMetrics().elidedText(
                        seg.text, Qt.TextElideMode.ElideRight, int(text_rect.width())
                    ),
                )

    def _draw_playhead(self, painter: QPainter, h: int) -> None:
        x = self._ms_to_x(self._playhead_ms)
        if 0 <= x <= self.width():
            painter.setPen(QPen(self._PLAYHEAD_COLOR, 2))
            painter.drawLine(int(x), 0, int(x), h)
            painter.setBrush(QBrush(self._PLAYHEAD_COLOR))
            painter.drawPolygon(QPolygon([
                QPoint(int(x) - 5, 0),
                QPoint(int(x) + 5, 0),
                QPoint(int(x), 7),
            ]))

    # ----------------------------------------------------------- Mouse

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._duration_ms <= 0:
            return

        x = event.position().x()
        y = event.position().y()
        seg_idx, hit = self._hit_test(x, y)

        if hit == "left_edge":
            self._start_drag(_DragMode.RESIZE_LEFT, seg_idx, x)
        elif hit == "right_edge":
            self._start_drag(_DragMode.RESIZE_RIGHT, seg_idx, x)
        elif hit == "body":
            self._selected_index = seg_idx
            self.segment_selected.emit(seg_idx)
            self._start_drag(_DragMode.MOVE, seg_idx, x)
        else:
            self._selected_index = -1
            self._drag_mode = _DragMode.SEEK
            self._seek_to_x(x)

        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        x = event.position().x()
        y = event.position().y()

        if self._drag_mode == _DragMode.SEEK:
            self._seek_to_x(x)
            return

        if self._drag_mode in (_DragMode.MOVE, _DragMode.RESIZE_LEFT, _DragMode.RESIZE_RIGHT):
            self._handle_drag(x)
            return

        # Update cursor based on hover
        seg_idx, hit = self._hit_test(x, y)
        if hit in ("left_edge", "right_edge"):
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        elif hit == "body":
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_mode in (_DragMode.MOVE, _DragMode.RESIZE_LEFT, _DragMode.RESIZE_RIGHT):
            # Emit final position
            if self._track and 0 <= self._drag_seg_index < len(self._track):
                seg = self._track[self._drag_seg_index]
                if seg.start_ms != self._drag_orig_start_ms or seg.end_ms != self._drag_orig_end_ms:
                    self.segment_moved.emit(self._drag_seg_index, seg.start_ms, seg.end_ms)
        self._drag_mode = _DragMode.NONE
        self._drag_seg_index = -1
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._duration_ms <= 0:
            return
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 0.8 if delta > 0 else 1.25
            mouse_ms = self._x_to_ms(event.position().x())
            old_range = self._visible_range_ms()
            new_range = max(1000, min(self._duration_ms, old_range * factor))
            mouse_frac = event.position().x() / max(self.width(), 1)
            self._visible_start_ms = mouse_ms - new_range * mouse_frac
            self._clamp_visible_start(new_range)
        else:
            shift = self._visible_range_ms() * 0.1 * (-1 if delta > 0 else 1)
            self._visible_start_ms += shift
            self._clamp_visible_start(self._visible_range_ms())
        self.update()

    # -------------------------------------------------------- Drag helpers

    def _start_drag(self, mode: _DragMode, seg_idx: int, x: float) -> None:
        self._drag_mode = mode
        self._drag_seg_index = seg_idx
        self._drag_start_x = x
        if self._track and 0 <= seg_idx < len(self._track):
            seg = self._track[seg_idx]
            self._drag_orig_start_ms = seg.start_ms
            self._drag_orig_end_ms = seg.end_ms

    def _handle_drag(self, x: float) -> None:
        if not self._track or self._drag_seg_index < 0 or self._drag_seg_index >= len(self._track):
            return

        dx_ms = int((x - self._drag_start_x) / self._px_per_ms) if self._px_per_ms > 0 else 0
        seg = self._track[self._drag_seg_index]

        if self._drag_mode == _DragMode.MOVE:
            new_start = max(0, self._drag_orig_start_ms + dx_ms)
            duration = self._drag_orig_end_ms - self._drag_orig_start_ms
            if new_start + duration > self._duration_ms:
                new_start = self._duration_ms - duration
            seg.start_ms = new_start
            seg.end_ms = new_start + duration
        elif self._drag_mode == _DragMode.RESIZE_LEFT:
            new_start = max(0, self._drag_orig_start_ms + dx_ms)
            new_start = min(new_start, seg.end_ms - 100)  # min 100ms
            seg.start_ms = new_start
        elif self._drag_mode == _DragMode.RESIZE_RIGHT:
            new_end = max(seg.start_ms + 100, self._drag_orig_end_ms + dx_ms)
            new_end = min(new_end, self._duration_ms)
            seg.end_ms = new_end

        self.update()

    def _hit_test(self, x: float, y: float) -> tuple[int, str]:
        """Return (segment_index, hit_zone) or (-1, '') if nothing hit."""
        if not self._track:
            return -1, ""
        seg_y = 20
        seg_h = self.height() - 30
        if y < seg_y or y > seg_y + seg_h:
            return -1, ""

        for i, seg in enumerate(self._track):
            x1 = self._ms_to_x(seg.start_ms)
            x2 = self._ms_to_x(seg.end_ms)
            if x < x1 - _EDGE_PX or x > x2 + _EDGE_PX:
                continue
            if abs(x - x1) <= _EDGE_PX:
                return i, "left_edge"
            if abs(x - x2) <= _EDGE_PX:
                return i, "right_edge"
            if x1 <= x <= x2:
                return i, "body"
        return -1, ""

    # ----------------------------------------------------------- Helpers

    def _visible_range_ms(self) -> float:
        if self._px_per_ms > 0:
            return self.width() / self._px_per_ms
        return float(self._duration_ms) if self._duration_ms > 0 else 1.0

    def _ms_to_x(self, ms: float) -> float:
        return (ms - self._visible_start_ms) * self._px_per_ms

    def _x_to_ms(self, x: float) -> float:
        if self._px_per_ms <= 0:
            return 0
        return self._visible_start_ms + x / self._px_per_ms

    def _seek_to_x(self, x: float) -> None:
        ms = int(max(0, min(self._duration_ms, self._x_to_ms(x))))
        self.seek_requested.emit(ms)

    def _clamp_visible_start(self, visible_range: float) -> None:
        self._visible_start_ms = max(0, self._visible_start_ms)
        max_start = max(0, self._duration_ms - visible_range)
        self._visible_start_ms = min(self._visible_start_ms, max_start)

    @staticmethod
    def _nice_tick_interval(visible_ms: float) -> int:
        target_ticks = 8
        raw = visible_ms / target_ticks
        candidates = [
            500, 1000, 2000, 5000, 10000, 15000, 30000,
            60000, 120000, 300000, 600000,
        ]
        for c in candidates:
            if c >= raw:
                return c
        return candidates[-1]
