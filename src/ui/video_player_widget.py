"""Video player widget using QGraphicsView + QGraphicsVideoItem with subtitle overlay."""

from __future__ import annotations

from PySide6.QtCore import Qt, QSizeF
from PySide6.QtGui import QColor, QFont, QResizeEvent
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)

from src.models.style import SubtitleStyle
from src.models.subtitle import SubtitleSegment, SubtitleTrack


class VideoPlayerWidget(QGraphicsView):
    """Displays video with subtitle text overlay."""

    def __init__(self, player: QMediaPlayer, parent=None):
        super().__init__(parent)
        self._player = player
        self._subtitle_track: SubtitleTrack | None = None
        self._current_subtitle_text = ""
        self._default_style = SubtitleStyle()
        self.setMinimumSize(640, 360)

        # Scene setup
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("background-color: black; border: none;")

        # Video item
        self._video_item = QGraphicsVideoItem()
        self._scene.addItem(self._video_item)
        self._player.setVideoOutput(self._video_item)
        self._video_item.nativeSizeChanged.connect(self._on_native_size_changed)

        # Subtitle overlay
        self._subtitle_item = QGraphicsTextItem()
        self._subtitle_item.setZValue(10)
        self._subtitle_item.setVisible(False)
        self._scene.addItem(self._subtitle_item)

        # Subtitle position editing
        self._edit_mode = False
        self._subtitle_item.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIsMovable, False)
        self._subtitle_item.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        # Install event filter to track subtitle movement
        self._subtitle_item.installEventFilter(self)

        # Apply default style
        self._apply_style(self._default_style)

        # Connect player position to subtitle update
        self._player.positionChanged.connect(self._on_position_changed)

    def set_default_style(self, style: SubtitleStyle) -> None:
        """Set the default style used when a segment has no per-segment style."""
        self._default_style = style
        # Re-render current subtitle with new style
        self._current_subtitle_text = ""  # force re-render
        self._update_subtitle(self._player.position())

    def set_subtitle_track(self, track: SubtitleTrack | None) -> None:
        self._subtitle_track = track
        # Force update by clearing cache
        self._current_subtitle_text = ""
        try:
            self._update_subtitle(self._player.position())
        except RuntimeError:
            # Player might be deleted during app shutdown
            pass

    def _get_effective_style(self, segment: SubtitleSegment) -> SubtitleStyle:
        """Return the segment's style if set, otherwise the default style."""
        return segment.style if segment.style is not None else self._default_style

    def _on_position_changed(self, position_ms: int) -> None:
        self._update_subtitle(position_ms)

    def _update_subtitle(self, position_ms: int) -> None:
        if not self._subtitle_track:
            self._subtitle_item.setVisible(False)
            self._current_subtitle_text = ""
            return

        seg = self._subtitle_track.segment_at(position_ms)
        if seg:
            style = self._get_effective_style(seg)
            if seg.text != self._current_subtitle_text:
                self._current_subtitle_text = seg.text
                self._apply_style(style)
                self._subtitle_item.setPlainText(seg.text)
                self._position_subtitle(style)
            self._subtitle_item.setVisible(True)
        else:
            self._subtitle_item.setVisible(False)
            self._current_subtitle_text = ""

    def _apply_style(self, style: SubtitleStyle) -> None:
        """Apply visual style to the subtitle text item."""
        weight = QFont.Weight.Bold if style.font_bold else QFont.Weight.Normal
        font = QFont(style.font_family, style.font_size, weight)
        font.setItalic(style.font_italic)
        self._subtitle_item.setFont(font)
        self._subtitle_item.setDefaultTextColor(QColor(style.font_color))

        # Outline effect via drop shadow
        if style.outline_width > 0 and style.outline_color:
            effect = QGraphicsDropShadowEffect()
            effect.setBlurRadius(style.outline_width * 3)
            effect.setOffset(0, 0)
            effect.setColor(QColor(style.outline_color))
            self._subtitle_item.setGraphicsEffect(effect)
        else:
            self._subtitle_item.setGraphicsEffect(None)

    def _position_subtitle(self, style: SubtitleStyle | None = None) -> None:
        """Position subtitle according to style settings."""
        if style is None:
            style = self._default_style

        # Use custom position if set
        if style.custom_x is not None and style.custom_y is not None:
            self._subtitle_item.setPos(style.custom_x, style.custom_y)
            self._update_edit_border()
            return

        view_rect = self.viewport().rect()
        scene_rect = self.mapToScene(view_rect).boundingRect()
        text_width = self._subtitle_item.boundingRect().width()
        text_height = self._subtitle_item.boundingRect().height()

        # Horizontal positioning
        position = style.position
        if position.endswith("center"):
            x = scene_rect.center().x() - text_width / 2
        elif position.endswith("left"):
            x = scene_rect.left() + 20
        elif position.endswith("right"):
            x = scene_rect.right() - text_width - 20
        else:
            x = scene_rect.center().x() - text_width / 2

        # Vertical positioning
        if position.startswith("top"):
            y = scene_rect.top() + style.margin_bottom
        else:
            y = scene_rect.bottom() - text_height - style.margin_bottom

        self._subtitle_item.setPos(x, y)
        self._update_edit_border()

    def _update_edit_border(self) -> None:
        """Update edit mode border position to match subtitle."""
        if hasattr(self, '_edit_border') and self._edit_border.isVisible():
            rect = self._subtitle_item.boundingRect()
            pos = self._subtitle_item.pos()
            border_rect = rect.adjusted(-10, -10, 10, 10)
            self._edit_border.setRect(border_rect)
            self._edit_border.setPos(pos)

    def _on_native_size_changed(self, size: QSizeF) -> None:
        self._fit_video()

    def _fit_video(self) -> None:
        view_size = self.viewport().size()
        self._video_item.setSize(QSizeF(view_size.width(), view_size.height()))
        self._scene.setSceneRect(0, 0, view_size.width(), view_size.height())
        self._position_subtitle()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit_video()

    def set_subtitle_edit_mode(self, enabled: bool) -> None:
        """Enable/disable subtitle position editing mode."""
        self._edit_mode = enabled
        self._subtitle_item.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIsMovable, enabled)

        # Visual feedback: change cursor and add border
        if enabled:
            self._subtitle_item.setCursor(Qt.CursorShape.OpenHandCursor)
            # Add visual border to indicate edit mode
            from PySide6.QtWidgets import QGraphicsRectItem
            from PySide6.QtGui import QPen, QBrush
            if not hasattr(self, '_edit_border'):
                self._edit_border = QGraphicsRectItem()
                self._edit_border.setZValue(9)  # Just below subtitle
                self._scene.addItem(self._edit_border)

            # Update border position and style
            rect = self._subtitle_item.boundingRect()
            pos = self._subtitle_item.pos()
            border_rect = rect.adjusted(-10, -10, 10, 10)
            self._edit_border.setRect(border_rect)
            self._edit_border.setPos(pos)
            self._edit_border.setPen(QPen(QColor(255, 165, 0), 3, Qt.PenStyle.DashLine))  # Orange dashed border
            self._edit_border.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self._edit_border.setVisible(True)
        else:
            self._subtitle_item.setCursor(Qt.CursorShape.ArrowCursor)
            # Hide border when not in edit mode
            if hasattr(self, '_edit_border'):
                self._edit_border.setVisible(False)

    def get_subtitle_position(self) -> tuple[int, int] | None:
        """Get current subtitle position (x, y) in scene coordinates."""
        if not self._subtitle_item.isVisible():
            return None
        pos = self._subtitle_item.pos()
        return (int(pos.x()), int(pos.y()))

    def is_edit_mode(self) -> bool:
        """Check if subtitle edit mode is enabled."""
        return self._edit_mode

    def eventFilter(self, obj, event):
        """Filter events to track subtitle item position changes."""
        from PySide6.QtCore import QEvent
        # Check if _subtitle_item exists first (may not be initialized yet)
        if hasattr(self, '_subtitle_item') and obj == self._subtitle_item and event.type() == QEvent.Type.GraphicsSceneMouseMove:
            # Update border position while dragging
            if self._edit_mode:
                self._update_edit_border()
        return super().eventFilter(obj, event)
