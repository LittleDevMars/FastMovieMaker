"""Custom-painted timeline widget showing subtitle blocks and playhead."""

from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from src.models.subtitle import SubtitleTrack
from src.utils.config import TIMELINE_HEIGHT
from src.utils.time_utils import ms_to_display


class TimelineWidget(QWidget):
    """Timeline bar showing subtitle segments with zoom, scroll, and click-to-seek."""

    seek_requested = Signal(int)  # ms

    # Colors
    _BG_COLOR = QColor(30, 30, 30)
    _RULER_COLOR = QColor(100, 100, 100)
    _RULER_TEXT_COLOR = QColor(170, 170, 170)
    _SEGMENT_COLOR = QColor(60, 140, 220, 180)
    _SEGMENT_BORDER = QColor(80, 170, 255)
    _PLAYHEAD_COLOR = QColor(255, 60, 60)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(TIMELINE_HEIGHT)
        self.setMouseTracking(True)

        self._track: SubtitleTrack | None = None
        self._duration_ms: int = 0
        self._playhead_ms: int = 0

        # Zoom/scroll: visible_start_ms is the left edge, px_per_ms controls zoom
        self._visible_start_ms: float = 0.0
        self._px_per_ms: float = 0.0  # recalculated on paint

        self._dragging = False

    # -------------------------------------------------------- Public API

    def set_track(self, track: SubtitleTrack | None) -> None:
        self._track = track
        self.update()

    def set_duration(self, duration_ms: int) -> None:
        self._duration_ms = duration_ms
        self._visible_start_ms = 0
        self.update()

    def set_playhead(self, position_ms: int) -> None:
        self._playhead_ms = position_ms
        # Auto-scroll: if playhead goes past 80% of visible range, scroll
        visible_range = self._visible_range_ms()
        if visible_range > 0:
            right_edge = self._visible_start_ms + visible_range
            if position_ms > self._visible_start_ms + visible_range * 0.8:
                self._visible_start_ms = position_ms - visible_range * 0.2
            elif position_ms < self._visible_start_ms:
                self._visible_start_ms = max(0, position_ms - visible_range * 0.1)
        self.update()

    # ----------------------------------------------------------- Paint

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()

        # Background
        painter.fillRect(0, 0, w, h, self._BG_COLOR)

        if self._duration_ms <= 0:
            painter.setPen(self._RULER_TEXT_COLOR)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No video loaded")
            painter.end()
            return

        # Calculate visible range
        visible_ms = self._visible_range_ms()
        if visible_ms <= 0:
            visible_ms = self._duration_ms
        self._px_per_ms = w / visible_ms

        # Draw ruler
        self._draw_ruler(painter, w, h, visible_ms)

        # Draw segments
        if self._track:
            self._draw_segments(painter, h)

        # Draw playhead
        self._draw_playhead(painter, h)

        painter.end()

    def _draw_ruler(self, painter: QPainter, w: int, h: int, visible_ms: float) -> None:
        painter.setPen(QPen(self._RULER_COLOR, 1))
        painter.setFont(QFont("Arial", 8))

        # Choose tick interval based on zoom
        tick_ms = self._nice_tick_interval(visible_ms)
        if tick_ms <= 0:
            return

        # First tick at or after visible start
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

        for seg in self._track:
            x1 = self._ms_to_x(seg.start_ms)
            x2 = self._ms_to_x(seg.end_ms)
            if x2 < 0 or x1 > self.width():
                continue  # offscreen

            rect = QRectF(x1, seg_y, max(x2 - x1, 2), seg_h)
            painter.setPen(QPen(self._SEGMENT_BORDER, 1))
            painter.setBrush(QBrush(self._SEGMENT_COLOR))
            painter.drawRoundedRect(rect, 3, 3)

            # Draw text if segment is wide enough
            if rect.width() > 30:
                painter.setPen(QColor("white"))
                painter.setFont(QFont("Arial", 8))
                text_rect = rect.adjusted(4, 2, -4, -2)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                 painter.fontMetrics().elidedText(seg.text, Qt.TextElideMode.ElideRight,
                                                                   int(text_rect.width())))

    def _draw_playhead(self, painter: QPainter, h: int) -> None:
        x = self._ms_to_x(self._playhead_ms)
        if 0 <= x <= self.width():
            painter.setPen(QPen(self._PLAYHEAD_COLOR, 2))
            painter.drawLine(int(x), 0, int(x), h)
            # Triangle at top
            painter.setBrush(QBrush(self._PLAYHEAD_COLOR))
            painter.drawPolygon([
                (int(x) - 5, 0),
                (int(x) + 5, 0),
                (int(x), 7),
            ])

    # ----------------------------------------------------------- Mouse

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._duration_ms > 0:
            self._dragging = True
            self._seek_to_x(event.position().x())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            self._seek_to_x(event.position().x())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._dragging = False

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Zoom with Ctrl+wheel, scroll otherwise."""
        if self._duration_ms <= 0:
            return

        delta = event.angleDelta().y()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Zoom: change visible range
            factor = 0.8 if delta > 0 else 1.25
            mouse_ms = self._x_to_ms(event.position().x())
            old_range = self._visible_range_ms()
            new_range = max(1000, min(self._duration_ms, old_range * factor))
            # Keep mouse position stable
            mouse_frac = event.position().x() / max(self.width(), 1)
            self._visible_start_ms = mouse_ms - new_range * mouse_frac
            self._clamp_visible_start(new_range)
        else:
            # Scroll
            shift = self._visible_range_ms() * 0.1 * (-1 if delta > 0 else 1)
            self._visible_start_ms += shift
            self._clamp_visible_start(self._visible_range_ms())

        self.update()

    # ----------------------------------------------------------- Helpers

    def _visible_range_ms(self) -> float:
        """Current visible time range in ms."""
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
        """Choose a human-friendly tick interval."""
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
