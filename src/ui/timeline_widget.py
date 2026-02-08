"""Custom-painted timeline widget showing subtitle blocks and playhead."""

from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import Qt, Signal, QPoint, QRectF
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QImage,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPolygon,
    QWheelEvent,
)

import numpy as np
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
    AUDIO_MOVE = auto()
    AUDIO_RESIZE_LEFT = auto()
    AUDIO_RESIZE_RIGHT = auto()
    PLAYHEAD_DRAG = auto()  # Dragging the playhead
    PAN_VIEW = auto()  # Dragging timeline view to scroll


_EDGE_PX = 6  # pixels from segment edge that trigger resize
_PLAYHEAD_HIT_PX = 20  # pixels from playhead that trigger drag (wider for easier clicking)


class TimelineWidget(QWidget):
    """Timeline bar showing subtitle segments with zoom, scroll, click-to-seek,
    and drag-move / drag-resize of segments."""

    seek_requested = Signal(int)  # ms
    segment_selected = Signal(int)  # segment index
    segment_moved = Signal(int, int, int)  # (index, new_start_ms, new_end_ms)
    audio_moved = Signal(int, int)  # (new_start_ms, new_duration_ms)

    # Colors
    _BG_COLOR = QColor(30, 30, 30)
    _RULER_COLOR = QColor(100, 100, 100)
    _RULER_TEXT_COLOR = QColor(170, 170, 170)
    _SEGMENT_COLOR = QColor(60, 140, 220, 180)
    _SEGMENT_BORDER = QColor(80, 170, 255)
    _SELECTED_COLOR = QColor(100, 200, 255, 200)
    _SELECTED_BORDER = QColor(150, 220, 255)
    _PLAYHEAD_COLOR = QColor(255, 60, 60)
    _AUDIO_COLOR = QColor(100, 200, 100, 180)  # TTS audio - green
    _AUDIO_BORDER = QColor(120, 220, 120)
    _AUDIO_SELECTED_COLOR = QColor(150, 255, 150, 200)
    _AUDIO_SELECTED_BORDER = QColor(180, 255, 180)
    _VIDEO_AUDIO_COLOR = QColor(255, 150, 50, 180)  # Video audio - orange
    _VIDEO_AUDIO_BORDER = QColor(255, 180, 80)
    _WAVEFORM_FILL = QColor(255, 150, 50, 100)  # Semi-transparent orange
    _WAVEFORM_EDGE = QColor(255, 180, 80, 180)  # Brighter orange peaks
    _WAVEFORM_CENTER = QColor(255, 150, 50, 40)  # Subtle center line

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(TIMELINE_HEIGHT)
        self.setMouseTracking(True)

        # Set explicit background and border for visibility
        self.setStyleSheet("""
            TimelineWidget {
                background-color: rgb(30, 30, 30);
                border-top: 1px solid rgb(50, 50, 50);
            }
        """)

        self._track: SubtitleTrack | None = None
        self._duration_ms: int = 0
        self._playhead_ms: int = 0

        # Zoom/scroll
        self._visible_start_ms: float = 0.0
        self._px_per_ms: float = 0.0

        # Selection
        self._selected_index: int = -1
        self._audio_selected: bool = False

        # Drag state
        self._drag_mode = _DragMode.NONE
        self._drag_seg_index: int = -1
        self._drag_start_x: float = 0.0
        self._drag_orig_start_ms: int = 0
        self._drag_orig_end_ms: int = 0
        self._drag_orig_audio_start_ms: int = 0
        self._drag_orig_audio_duration_ms: int = 0

        # Waveform data
        self._waveform_data = None  # WaveformData or None
        self._waveform_image_cache: QImage | None = None
        self._waveform_cache_key: tuple | None = None

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
        # Don't update playhead during drag to avoid conflicts
        if self._drag_mode == _DragMode.PLAYHEAD_DRAG:
            return

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

    def set_waveform(self, waveform_data) -> None:
        """Set pre-computed waveform data for display."""
        self._waveform_data = waveform_data
        self._waveform_image_cache = None
        self._waveform_cache_key = None
        self.update()

    def clear_waveform(self) -> None:
        """Remove waveform display."""
        self._waveform_data = None
        self._waveform_image_cache = None
        self._waveform_cache_key = None
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
        self._draw_video_audio(painter, w, h)  # Video audio track (if video loaded)
        if self._track:
            self._draw_audio_track(painter, h)  # TTS audio track
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

    def _draw_video_audio(self, painter: QPainter, w: int, h: int) -> None:
        """Draw video audio waveform or fallback indicator bar."""
        if self._duration_ms <= 0:
            return

        if self._waveform_data is not None and self._waveform_data.duration_ms > 0:
            self._draw_waveform(painter, w)
        else:
            self._draw_video_audio_fallback(painter, w)

    def _draw_waveform(self, painter: QPainter, w: int) -> None:
        """Draw waveform using cached QImage for performance."""
        wf = self._waveform_data
        if wf is None or wf.duration_ms <= 0:
            return

        waveform_y = 120
        waveform_h = 45

        visible_ms = self._visible_range_ms()
        cache_key = (self._visible_start_ms, visible_ms, w)

        if self._waveform_cache_key != cache_key:
            self._waveform_image_cache = self._render_waveform_image(w, waveform_h)
            self._waveform_cache_key = cache_key

        if self._waveform_image_cache is not None:
            painter.drawImage(0, waveform_y, self._waveform_image_cache)

        # Draw label
        label_x = max(5, int(self._ms_to_x(0)) + 5)
        if 0 < label_x < w - 80:
            painter.setPen(QColor(255, 200, 100, 200))
            painter.setFont(QFont("Arial", 8))
            painter.drawText(label_x, waveform_y + 10, "Video Audio")

    def _render_waveform_image(self, w: int, h: int) -> QImage:
        """Render waveform to a QImage for efficient blitting."""
        wf = self._waveform_data
        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor(0, 0, 0, 0))

        center_y = h // 2
        half_h = h / 2.0

        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        fill_color = self._WAVEFORM_FILL
        edge_color = self._WAVEFORM_EDGE

        for px in range(w):
            ms_start = self._x_to_ms(px)
            ms_end = self._x_to_ms(px + 1)
            ms_start_i = max(0, int(ms_start))
            ms_end_i = min(wf.duration_ms, int(ms_end))

            if ms_start_i >= ms_end_i or ms_start_i >= wf.duration_ms:
                continue

            peak_max = float(np.max(wf.peaks_pos[ms_start_i:ms_end_i]))
            peak_min = float(np.min(wf.peaks_neg[ms_start_i:ms_end_i]))

            y_top = center_y - int(peak_max * half_h)
            y_bot = center_y - int(peak_min * half_h)
            if y_bot <= y_top:
                y_bot = y_top + 1

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(fill_color))
            p.drawRect(px, y_top, 1, y_bot - y_top)

            p.setBrush(QBrush(edge_color))
            p.drawRect(px, y_top, 1, 1)
            if y_bot - y_top > 2:
                p.drawRect(px, y_bot - 1, 1, 1)

        # Center line
        p.setPen(QPen(self._WAVEFORM_CENTER, 1))
        p.drawLine(0, center_y, w, center_y)

        p.end()
        return img

    def _draw_video_audio_fallback(self, painter: QPainter, w: int) -> None:
        """Fallback: draw simple bar when waveform data is not available."""
        video_audio_y = 120
        video_audio_h = 45

        x1 = self._ms_to_x(0)
        x2 = self._ms_to_x(self._duration_ms)

        if x2 < 0 or x1 > w:
            return

        rect = QRectF(x1, video_audio_y, max(x2 - x1, 2), video_audio_h)
        painter.setPen(QPen(self._VIDEO_AUDIO_BORDER, 1))
        painter.setBrush(QBrush(self._VIDEO_AUDIO_COLOR))
        painter.drawRoundedRect(rect, 3, 3)

        if x2 - x1 > 100:
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Arial", 9))
            label_rect = QRectF(x1 + 5, video_audio_y, x2 - x1 - 10, video_audio_h)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Loading waveform...")

    def _draw_audio_track(self, painter: QPainter, h: int) -> None:
        """Draw individual audio segments for each subtitle segment."""
        if not self._track:
            return

        audio_y = 75
        audio_h = 40

        # Draw individual audio segments
        for i, seg in enumerate(self._track):
            # Only draw if this segment has audio
            if not seg.audio_file:
                continue

            x1 = self._ms_to_x(seg.start_ms)
            x2 = self._ms_to_x(seg.end_ms)

            if x2 < 0 or x1 > self.width():
                continue

            rect = QRectF(x1, audio_y, max(x2 - x1, 2), audio_h)

            # Highlight selected audio segment
            if i == self._selected_index:
                painter.setPen(QPen(self._AUDIO_SELECTED_BORDER, 2))
                painter.setBrush(QBrush(self._AUDIO_SELECTED_COLOR))
            else:
                painter.setPen(QPen(self._AUDIO_BORDER, 1))
                painter.setBrush(QBrush(self._AUDIO_COLOR))

            painter.drawRoundedRect(rect, 3, 3)

            # Draw label (segment number)
            if rect.width() > 30:
                painter.setPen(QColor("white"))
                painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
                text_rect = rect.adjusted(4, 2, -4, -2)
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
                    f"🔊 {i+1}",
                )

    def _draw_segments(self, painter: QPainter, h: int) -> None:
        seg_y = 20
        seg_h = 50

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
        if self._duration_ms <= 0 or self._px_per_ms <= 0:
            return

        x = event.position().x()
        y = event.position().y()

        # Middle mouse button → Pan view
        if event.button() == Qt.MouseButton.MiddleButton:
            self._drag_mode = _DragMode.PAN_VIEW
            self._drag_start_x = x
            self._drag_start_visible_ms = self._visible_start_ms
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            return

        # Shift + Left click on empty space → Pan view
        if event.button() == Qt.MouseButton.LeftButton:
            modifiers = event.modifiers()

            seg_idx, hit = self._hit_test(x, y)

            # Check if Shift is pressed and clicking on empty space
            if modifiers & Qt.KeyboardModifier.ShiftModifier and hit == "":
                self._drag_mode = _DragMode.PAN_VIEW
                self._drag_start_x = x
                self._drag_start_visible_ms = self._visible_start_ms
                self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
                return

            # Check if clicking on playhead
            if hit == "playhead":
                self._drag_mode = _DragMode.PLAYHEAD_DRAG
                self._seek_to_x(x)
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            # Audio segments now share the same hit zones as subtitle segments (linked movement)
            elif hit == "left_edge":
                self._audio_selected = False
                self._start_drag(_DragMode.RESIZE_LEFT, seg_idx, x)
            elif hit == "right_edge":
                self._audio_selected = False
                self._start_drag(_DragMode.RESIZE_RIGHT, seg_idx, x)
            elif hit == "body":
                self._audio_selected = False
                self._selected_index = seg_idx
                self.segment_selected.emit(seg_idx)
                self._start_drag(_DragMode.MOVE, seg_idx, x)
            else:
                self._audio_selected = False
                self._selected_index = -1
                self._drag_mode = _DragMode.SEEK
                self._seek_to_x(x)

        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        x = event.position().x()
        y = event.position().y()

        # Handle pan view drag
        if self._drag_mode == _DragMode.PAN_VIEW:
            self._handle_pan_view(x)
            return

        # Handle playhead drag
        if self._drag_mode == _DragMode.PLAYHEAD_DRAG:
            self._seek_to_x(x)
            return

        # Handle seek (click and drag anywhere)
        if self._drag_mode == _DragMode.SEEK:
            self._seek_to_x(x)
            return

        if self._drag_mode in (_DragMode.MOVE, _DragMode.RESIZE_LEFT, _DragMode.RESIZE_RIGHT):
            self._handle_drag(x)
            return

        # Update cursor based on hover (including playhead)
        if self._drag_mode == _DragMode.NONE:
            seg_idx, hit = self._hit_test(x, y)
            if hit == "playhead":
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
                return  # Don't process other hit zones
            elif hit in ("left_edge", "right_edge", "audio_left_edge", "audio_right_edge"):
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            elif hit in ("body", "audio_body"):
                self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_mode in (_DragMode.MOVE, _DragMode.RESIZE_LEFT, _DragMode.RESIZE_RIGHT):
            # Emit final position (for both subtitle and linked audio)
            if self._track and 0 <= self._drag_seg_index < len(self._track):
                seg = self._track[self._drag_seg_index]
                if seg.start_ms != self._drag_orig_start_ms or seg.end_ms != self._drag_orig_end_ms:
                    self.segment_moved.emit(self._drag_seg_index, seg.start_ms, seg.end_ms)
        self._drag_mode = _DragMode.NONE
        self._drag_seg_index = -1
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._duration_ms <= 0 or self._px_per_ms <= 0:
            return
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 0.8 if delta > 0 else 1.25
            mouse_ms = self._x_to_ms(event.position().x())
            old_range = self._visible_range_ms()
            new_range = max(1000, min(self._duration_ms, old_range * factor))
            mouse_frac = event.position().x() / max(self.width(), 1)
            # Immediately clamp to prevent negative values
            self._visible_start_ms = max(0, mouse_ms - new_range * mouse_frac)
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

    def _handle_pan_view(self, x: float) -> None:
        """Handle panning the timeline view by dragging."""
        if self._px_per_ms <= 0:
            return

        # Calculate how much to pan based on drag distance
        dx_px = x - self._drag_start_x
        dx_ms = -dx_px / self._px_per_ms  # Negative because dragging right should scroll left

        # Update visible start position
        new_visible_start = self._drag_start_visible_ms + dx_ms
        visible_range = self._visible_range_ms()

        # Clamp to valid range
        new_visible_start = max(0, new_visible_start)
        max_start = max(0, self._duration_ms - visible_range)
        new_visible_start = min(new_visible_start, max_start)

        self._visible_start_ms = new_visible_start
        self.update()

    def _start_audio_drag(self, mode: _DragMode, x: float) -> None:
        """Start dragging audio track."""
        self._drag_mode = mode
        self._drag_start_x = x
        if self._track:
            self._drag_orig_audio_start_ms = self._track.audio_start_ms
            self._drag_orig_audio_duration_ms = self._track.audio_duration_ms

    def _handle_audio_drag(self, x: float) -> None:
        """Handle audio track drag/resize."""
        if not self._track:
            return

        dx_ms = int((x - self._drag_start_x) / self._px_per_ms) if self._px_per_ms > 0 else 0

        if self._drag_mode == _DragMode.AUDIO_MOVE:
            new_start = max(0, self._drag_orig_audio_start_ms + dx_ms)
            if new_start + self._drag_orig_audio_duration_ms > self._duration_ms:
                new_start = self._duration_ms - self._drag_orig_audio_duration_ms
            self._track.audio_start_ms = max(0, new_start)
        elif self._drag_mode == _DragMode.AUDIO_RESIZE_LEFT:
            new_start = max(0, self._drag_orig_audio_start_ms + dx_ms)
            new_start = min(new_start, self._track.audio_start_ms + self._track.audio_duration_ms - 100)
            duration_change = self._track.audio_start_ms - new_start
            self._track.audio_start_ms = new_start
            self._track.audio_duration_ms += duration_change
        elif self._drag_mode == _DragMode.AUDIO_RESIZE_RIGHT:
            new_duration = max(100, self._drag_orig_audio_duration_ms + dx_ms)
            max_duration = self._duration_ms - self._track.audio_start_ms
            self._track.audio_duration_ms = min(new_duration, max_duration)

        self.update()

    def _hit_test(self, x: float, y: float) -> tuple[int, str]:
        """Return (segment_index, hit_zone) or (-1, '') if nothing hit."""
        # Check playhead first (highest priority, wider hit zone for easier dragging)
        playhead_x = self._ms_to_x(self._playhead_ms)
        if abs(x - playhead_x) <= _PLAYHEAD_HIT_PX:
            return -3, "playhead"

        if not self._track:
            return -1, ""

        # Check audio segments (below subtitles) - treat as linked to subtitle segments
        audio_y = 75
        audio_h = 40
        if audio_y <= y <= audio_y + audio_h:
            for i, seg in enumerate(self._track):
                if not seg.audio_file:
                    continue
                x1 = self._ms_to_x(seg.start_ms)
                x2 = self._ms_to_x(seg.end_ms)
                if x < x1 - _EDGE_PX or x > x2 + _EDGE_PX:
                    continue
                # Audio segments use same hit zones as subtitles (linked movement)
                if abs(x - x1) <= _EDGE_PX:
                    return i, "left_edge"
                if abs(x - x2) <= _EDGE_PX:
                    return i, "right_edge"
                if x1 <= x <= x2:
                    return i, "body"

        # Check subtitle segments
        seg_y = 20
        seg_h = 50
        if seg_y <= y <= seg_y + seg_h:
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
            # Return current playhead position instead of 0 to avoid unwanted seeking
            return float(self._playhead_ms)
        return self._visible_start_ms + x / self._px_per_ms

    def _seek_to_x(self, x: float) -> None:
        ms = int(max(0, min(self._duration_ms, self._x_to_ms(x))))
        self._playhead_ms = ms
        self.update()
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
