"""Video player widget using QGraphicsView + QGraphicsVideoItem with subtitle overlay."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QSizeF, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPen, QPixmap, QResizeEvent, QWheelEvent
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)

from src.models.image_overlay import ImageOverlayTrack
from src.models.style import SubtitleStyle
from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.models.overlay_template import OverlayTemplate
from src.models.text_overlay import TextOverlayTrack


class VideoPlayerWidget(QGraphicsView):
    """Displays video with subtitle text overlay."""

    # Emitted when user drags/scales a PIP overlay: (index, x%, y%, scale%)
    pip_position_changed = Signal(int, float, float, float)
    # Emitted when user drags a text overlay: (index, x%, y%)
    text_overlay_position_changed = Signal(int, float, float)

    def __init__(self, player: QMediaPlayer, parent=None):
        super().__init__(parent)
        self._player = player
        self._subtitle_track: SubtitleTrack | None = None
        self._current_subtitle_text = ""
        self._default_style = SubtitleStyle()
        self._current_template: OverlayTemplate | None = None
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

        self._video_locked = False
        self._video_hidden = False


        # Cached frame preview layer (Z=1: above video, below overlays)
        self._frame_preview_item = QGraphicsPixmapItem()
        self._frame_preview_item.setZValue(1)
        self._frame_preview_item.setVisible(False)
        self._scene.addItem(self._frame_preview_item)

        # Overlay template layer (between video and subtitle)
        self._overlay_item = QGraphicsPixmapItem()
        self._overlay_item.setZValue(5)
        self._overlay_item.setVisible(False)
        self._scene.addItem(self._overlay_item)
        self._overlay_path: str | None = None

        # PIP image overlays (zValue=7, between template=5 and subtitle=10)
        self._image_overlay_track: ImageOverlayTrack | None = None
        self._pip_items: dict[int, QGraphicsPixmapItem] = {}
        self._pip_active_indices: set[int] = set()

        # Text overlays (zValue=8, between PIP=7 and subtitle=10)
        self._text_overlay_track: TextOverlayTrack | None = None
        self._text_overlay_items: dict[int, QGraphicsTextItem] = {}
        self._text_overlay_active_indices: set[int] = set()

        # PIP selection and dragging
        self._selected_pip_index: int = -1
        self._pip_drag_active = False
        self._pip_drag_start_pos = None

        # Text selection and dragging
        self._selected_text_index: int = -1
        self._text_drag_active = False
        self._text_drag_start_pos = None

        self._selection_border: QGraphicsRectItem | None = None

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
        self._update_image_overlays(position_ms)
        self._update_text_overlays(position_ms)

    def _update_subtitle(self, position_ms: int) -> None:
        if not self._subtitle_track or self._subtitle_track.hidden:
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

    def _get_safe_area(self, scene_rect: QRectF) -> QRectF:
        """Calculate the safe area for subtitles based on current template aspect ratio."""
        if not self._current_template or self._current_template.aspect_ratio not in ("9:16", "4:5", "1:1"):
            return scene_rect

        # Calculate bounding box for the target aspect ratio, centered in scene
        vw = scene_rect.width()
        vh = scene_rect.height()
        
        target_ratio = 9/16  # Default fallback for constrained ratios
        if self._current_template.aspect_ratio == "9:16":
            target_ratio = 9/16
        elif self._current_template.aspect_ratio == "4:5":
            target_ratio = 4/5
        elif self._current_template.aspect_ratio == "1:1":
            target_ratio = 1/1

        # Check if we are limited by height or width
        # scene usually matches video aspect (e.g. 16:9). 
        # A 9:16 box inside 16:9 is limited by height.
        
        # Try full height
        box_h = vh
        box_w = box_h * target_ratio
        
        if box_w > vw:
            # Limited by width
            box_w = vw
            box_h = box_w / target_ratio
            
        x = (vw - box_w) / 2
        y = (vh - box_h) / 2
        
        return QRectF(x, y, box_w, box_h)

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
        
        # Calculate safe area (9:16 support)
        safe_rect = self._get_safe_area(scene_rect)

        # Auto word-wrap: limit text width to 90% of safe area width
        max_text_width = safe_rect.width() * 0.9
        self._subtitle_item.setTextWidth(max_text_width)

        text_width = self._subtitle_item.boundingRect().width()
        text_height = self._subtitle_item.boundingRect().height()

        # Horizontal positioning
        position = style.position
        if position.endswith("center"):
            # Center the text horizontally within safe area
            x = safe_rect.left() + (safe_rect.width() - text_width) / 2
        elif position.endswith("left"):
            x = safe_rect.left() + 20
        elif position.endswith("right"):
            x = safe_rect.right() - text_width - 20
        else:
            # Default to center
            x = safe_rect.left() + (safe_rect.width() - text_width) / 2

        # Vertical positioning
        if position.startswith("top"):
            y = safe_rect.top() + style.margin_bottom
        else:
            y = safe_rect.bottom() - text_height - style.margin_bottom

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

    def set_overlay(self, template: OverlayTemplate | None = None, image_path: str | None = None, opacity: float = 1.0) -> None:
        """Set or update the overlay template image on top of the video."""
        # Support legacy call with just image_path
        if template is None and image_path:
            # Create a dummy template wrapper if only path provided
            from src.models.overlay_template import OverlayTemplate
            template = OverlayTemplate(
                template_id="temp", name="temp", image_path=image_path,
                thumbnail_path="", category="frame", aspect_ratio="16:9", opacity=opacity
            )

        self._current_template = template

        if template and template.image_path and Path(template.image_path).exists():
            self._overlay_path = template.image_path
            pixmap = QPixmap(template.image_path)
            view_size = self.viewport().size()
            scaled = pixmap.scaled(
                view_size.width(), view_size.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._overlay_item.setPixmap(scaled)
            self._overlay_item.setOpacity(template.opacity)
            self._overlay_item.setVisible(True)
            # Center the overlay
            x = (view_size.width() - scaled.width()) / 2
            y = (view_size.height() - scaled.height()) / 2
            self._overlay_item.setPos(x, y)
        else:
            self._overlay_path = None
            self._overlay_item.setVisible(False)
        
        # Re-position subtitles based on new template aspect ratio
        self._position_subtitle()

    def clear_overlay(self) -> None:
        """Remove the overlay template."""
        self._overlay_path = None
        self._current_template = None
        self._overlay_item.setVisible(False)
        self._position_subtitle()

    # -------------------------------------------------------- PIP Image Overlays

    def set_image_overlay_track(self, track: ImageOverlayTrack | None) -> None:
        """Set the image overlay track for PIP display."""
        self._image_overlay_track = track
        # Clear existing PIP items
        for item in self._pip_items.values():
            self._scene.removeItem(item)
        self._pip_items.clear()
        self._pip_active_indices.clear()
        self._selected_pip_index = -1
        if self._selection_border:
            self._selection_border.setVisible(False)
        # Immediately render overlays at current position
        try:
            self._update_image_overlays(self._player.position())
        except RuntimeError:
            pass

    def _update_image_overlays(self, position_ms: int) -> None:
        """Show/hide PIP image overlays based on playhead position."""
        if not self._image_overlay_track or self._image_overlay_track.hidden:
            # Hide all
            for item in self._pip_items.values():
                item.setVisible(False)
            self._pip_active_indices.clear()
            return

        active = self._image_overlay_track.overlays_at(position_ms)
        active_indices = set()
        for ov in active:
            idx = self._image_overlay_track.overlays.index(ov)
            active_indices.add(idx)

            if idx not in self._pip_items:
                pip = QGraphicsPixmapItem()
                pip.setZValue(7)
                self._scene.addItem(pip)
                self._pip_items[idx] = pip

            pip = self._pip_items[idx]
            if idx not in self._pip_active_indices:
                # Newly activated: load and position
                pixmap = QPixmap(ov.image_path)
                if pixmap.isNull():
                    pip.setVisible(False)
                    continue
                view_w = self.viewport().width()
                view_h = self.viewport().height()
                target_w = max(1, int(view_w * ov.scale_percent / 100))
                scaled = pixmap.scaledToWidth(target_w, Qt.TransformationMode.SmoothTransformation)
                pip.setPixmap(scaled)
                pip.setOpacity(ov.opacity)
                pip.setPos(view_w * ov.x_percent / 100, view_h * ov.y_percent / 100)
                pip.setVisible(True)

        # Hide deactivated overlays
        for idx in self._pip_active_indices - active_indices:
            if idx in self._pip_items:
                self._pip_items[idx].setVisible(False)

        self._pip_active_indices = active_indices

        # Update selection border if selected PIP is visible
        if self._selected_pip_index >= 0:
            self._update_selection_border()

    # -------------------------------------------------------- Text Overlays

    def set_text_overlay_track(self, track: TextOverlayTrack | None) -> None:
        """Set the text overlay track for display."""
        self._text_overlay_track = track
        # Clear existing text overlay items
        for item in self._text_overlay_items.values():
            self._scene.removeItem(item)
        self._text_overlay_items.clear()
        self._text_overlay_active_indices.clear()
        # Immediately render overlays at current position
        if self._player:
            try:
                self._update_text_overlays(self._player.position())
            except RuntimeError:
                # Player may have been deleted
                pass

    def _update_text_overlays(self, position_ms: int) -> None:
        """Show/hide text overlays based on playhead position."""
        if not self._text_overlay_track:
            # Hide all
            for item in self._text_overlay_items.values():
                item.setVisible(False)
            self._text_overlay_active_indices.clear()
            return

        active = self._text_overlay_track.overlays_at(position_ms)
        active_indices = set()

        for overlay in active:
            idx = self._text_overlay_track.overlays.index(overlay)
            active_indices.add(idx)

            # Create text item if not exists
            if idx not in self._text_overlay_items:
                text_item = QGraphicsTextItem()
                text_item.setZValue(8)  # Above PIP overlays (7), below subtitle (10)
                # Enable selection and movement
                text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
                text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
                text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
                self._scene.addItem(text_item)
                self._text_overlay_items[idx] = text_item

            text_item = self._text_overlay_items[idx]

            # Apply latest content and style
            text_item.setPlainText(overlay.text)
            style = overlay.style if overlay.style else self._default_style
            font = QFont(style.font_family, style.font_size)
            font.setBold(style.font_bold)
            font.setItalic(style.font_italic)
            text_item.setFont(font)
            text_item.setDefaultTextColor(QColor(style.font_color))
            text_item.setOpacity(overlay.opacity)

            if idx not in self._text_overlay_active_indices:
                # Newly activated: apply position based on percentage and alignment
                view_w = self.viewport().width()
                view_h = self.viewport().height()
                x_px = view_w * overlay.x_percent / 100
                y_px = view_h * overlay.y_percent / 100
                
                # Adjust for alignment
                rect = text_item.boundingRect()
                w = rect.width()
                h = rect.height()
                
                off_x = 0
                if overlay.alignment == "center":
                    off_x = -w / 2
                elif overlay.alignment == "right":
                    off_x = -w
                    
                off_y = 0
                if overlay.v_alignment == "middle":
                    off_y = -h / 2
                elif overlay.v_alignment == "bottom":
                    off_y = -h
                    
                text_item.setPos(x_px + off_x, y_px + off_y)
                text_item.setVisible(True)

        # Hide deactivated overlays
        for idx in self._text_overlay_active_indices - active_indices:
            if idx in self._text_overlay_items:
                self._text_overlay_items[idx].setVisible(False)

        self._text_overlay_active_indices = active_indices
        
        # Update selection border if selected text is affected
        if self._selected_text_index >= 0:
            self._update_selection_border()

    # -------------------------------------------------------- Overlay Utilities

    def _fit_overlay(self) -> None:
        """Resize the overlay to match the current view size."""
        if not self._overlay_path or not self._overlay_item.isVisible():
            return
        pixmap = QPixmap(self._overlay_path)
        if pixmap.isNull():
            return
        view_size = self.viewport().size()
        scaled = pixmap.scaled(
            view_size.width(), view_size.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._overlay_item.setPixmap(scaled)
        x = (view_size.width() - scaled.width()) / 2
        y = (view_size.height() - scaled.height()) / 2
        self._overlay_item.setPos(x, y)

    def show_cached_frame(self, pixmap: QPixmap) -> None:
        """Show a cached frame thumbnail, covering the video area."""
        if pixmap.isNull():
            return
        view_size = self.viewport().size()
        scaled = pixmap.scaled(
            view_size.width(), view_size.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._frame_preview_item.setPixmap(scaled)
        x = (view_size.width() - scaled.width()) / 2
        y = (view_size.height() - scaled.height()) / 2
        self._frame_preview_item.setPos(x, y)
        self._frame_preview_item.setVisible(True)

    def hide_cached_frame(self) -> None:
        """Hide the cached frame preview, showing live video again."""
        self._frame_preview_item.setVisible(False)

    def _fit_video(self) -> None:
        view_size = self.viewport().size()
        self._video_item.setSize(QSizeF(view_size.width(), view_size.height()))
        self._scene.setSceneRect(0, 0, view_size.width(), view_size.height())
        self._fit_overlay()
        self._position_subtitle()
        # Re-fit cached frame preview if visible
        if self._frame_preview_item.isVisible():
            pixmap = self._frame_preview_item.pixmap()
            if pixmap and not pixmap.isNull():
                self.show_cached_frame(pixmap)

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

    # ------------------------------------------------- PIP Selection / Dragging

    def select_pip(self, index: int) -> None:
        """Select a PIP overlay by index (or -1 to deselect)."""
        self._selected_pip_index = index
        self._selected_text_index = -1
        self._update_selection_border()

    def select_text(self, index: int) -> None:
        """Select a text overlay by index (or -1 to deselect)."""
        self._selected_text_index = index
        self._selected_pip_index = -1
        self._update_selection_border()

    def _pip_item_at_pos(self, view_pos) -> int:
        """Return the PIP item index at view position, or -1."""
        scene_pos = self.mapToScene(view_pos)
        items = self._scene.items(scene_pos)
        for item in items:
            for idx, pip in self._pip_items.items():
                if item is pip and pip.isVisible():
                    return idx
        return -1

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # 1. Check PIP items
            idx = self._pip_item_at_pos(event.pos())
            if idx >= 0:
                self._selected_pip_index = idx
                self._selected_text_index = -1
                self._pip_drag_active = True
                self._pip_drag_start_pos = self.mapToScene(event.pos())
                self._update_selection_border()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return

            # 2. Check Text items
            idx = self._text_item_at_pos(event.pos())
            if idx >= 0:
                self._selected_text_index = idx
                self._selected_pip_index = -1
                self._text_drag_active = True
                self._text_drag_start_pos = self.mapToScene(event.pos())
                self._update_selection_border()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return

            # Click elsewhere → deselect all
            if (self._selected_pip_index >= 0 or self._selected_text_index >= 0) and not self._edit_mode:
                self._selected_pip_index = -1
                self._selected_text_index = -1
                self._update_selection_border()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        scene_pos = self.mapToScene(event.pos())

        # Move PIP
        if self._pip_drag_active and self._selected_pip_index >= 0:
            pip = self._pip_items.get(self._selected_pip_index)
            if pip and self._pip_drag_start_pos is not None:
                delta = scene_pos - self._pip_drag_start_pos
                pip.setPos(pip.pos() + delta)
                self._pip_drag_start_pos = scene_pos
                self._update_selection_border()
            event.accept()
            return

        # Move Text
        if self._text_drag_active and self._selected_text_index >= 0:
            text_item = self._text_overlay_items.get(self._selected_text_index)
            if text_item and self._text_drag_start_pos is not None:
                delta = scene_pos - self._text_drag_start_pos
                text_item.setPos(text_item.pos() + delta)
                self._text_drag_start_pos = scene_pos
                self._update_selection_border()
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._pip_drag_active:
                self._pip_drag_active = False
                self._pip_drag_start_pos = None
                self.setCursor(Qt.CursorShape.ArrowCursor)
                self._emit_pip_position()
                event.accept()
                return
            elif self._text_drag_active:
                self._text_drag_active = False
                self._text_drag_start_pos = None
                self.setCursor(Qt.CursorShape.ArrowCursor)
                self._emit_text_position()
                event.accept()
                return

        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._selected_pip_index >= 0:
            pip = self._pip_items.get(self._selected_pip_index)
            track = self._image_overlay_track
            if pip and pip.isVisible() and track and 0 <= self._selected_pip_index < len(track):
                ov = track[self._selected_pip_index]
                delta = event.angleDelta().y()
                step = 2.0 if delta > 0 else -2.0
                new_scale = max(5.0, min(200.0, ov.scale_percent + step))
                if new_scale != ov.scale_percent:
                    ov.scale_percent = new_scale
                    # Re-render at new scale
                    pixmap = QPixmap(ov.image_path)
                    if not pixmap.isNull():
                        view_w = self.viewport().width()
                        target_w = max(1, int(view_w * new_scale / 100))
                        scaled = pixmap.scaledToWidth(target_w, Qt.TransformationMode.SmoothTransformation)
                        pip.setPixmap(scaled)
                    self._update_selection_border()
                    self._emit_pip_position()
                event.accept()
                return
        super().wheelEvent(event)

    def _emit_pip_position(self) -> None:
        """Convert current PIP pixel position to percentages and emit signal."""
        idx = self._selected_pip_index
        pip = self._pip_items.get(idx)
        track = self._image_overlay_track
        if pip is None or track is None or idx < 0 or idx >= len(track):
            return
        view_w = self.viewport().width()
        view_h = self.viewport().height()
        if view_w <= 0 or view_h <= 0:
            return
        x_pct = pip.pos().x() / view_w * 100.0
        y_pct = pip.pos().y() / view_h * 100.0
        scale_pct = track[idx].scale_percent
        self.pip_position_changed.emit(idx, x_pct, y_pct, scale_pct)

    def _emit_text_position(self) -> None:
        """Convert current text pixel position to percentages and emit signal."""
        idx = self._selected_text_index
        item = self._text_overlay_items.get(idx)
        track = self._text_overlay_track
        if item is None or track is None or idx < 0 or idx >= len(track.overlays):
            return
            
        ov = track.overlays[idx]
        view_w = self.viewport().width()
        view_h = self.viewport().height()
        if view_w <= 0 or view_h <= 0:
            return
            
        # Get anchor point from top-left position + alignment offset
        rect = item.boundingRect()
        w = rect.width()
        h = rect.height()
        
        pos_x = item.pos().x()
        pos_y = item.pos().y()
        
        anchor_x = pos_x
        if ov.alignment == "center":
            anchor_x = pos_x + w / 2
        elif ov.alignment == "right":
            anchor_x = pos_x + w
            
        anchor_y = pos_y
        if ov.v_alignment == "middle":
            anchor_y = pos_y + h / 2
        elif ov.v_alignment == "bottom":
            anchor_y = pos_y + h
            
        x_pct = anchor_x / view_w * 100.0
        y_pct = anchor_y / view_h * 100.0
        self.text_overlay_position_changed.emit(idx, x_pct, y_pct)

    def _update_selection_border(self) -> None:
        """Show/hide/reposition the selection border."""
        target_item = None
        if self._selected_pip_index >= 0:
            target_item = self._pip_items.get(self._selected_pip_index)
        elif self._selected_text_index >= 0:
            target_item = self._text_overlay_items.get(self._selected_text_index)

        if target_item is None or not target_item.isVisible():
            if self._selection_border:
                self._selection_border.setVisible(False)
            return

        if self._selection_border is None:
            self._selection_border = QGraphicsRectItem()
            self._selection_border.setZValue(9) # Above all overlays
            self._selection_border.setPen(QPen(QColor(0, 188, 212), 2, Qt.PenStyle.DashLine))
            self._selection_border.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self._scene.addItem(self._selection_border)

        rect = target_item.boundingRect()
        self._selection_border.setRect(rect.adjusted(-3, -3, 3, 3))
        self._selection_border.setPos(target_item.pos())
        self._selection_border.setVisible(True)

    def _text_item_at_pos(self, pos) -> int:
        """Find index of text overlay item at current viewport position."""
        scene_pos = self.mapToScene(pos)
        items = self.scene().items(scene_pos)
        for item in items:
            if isinstance(item, QGraphicsTextItem) and item != self._subtitle_item:
                for idx, text_item in self._text_overlay_items.items():
                    if text_item == item:
                        return idx
        return -1

    def _pip_item_at_pos(self, pos) -> int:
        """Find index of PIP image item at current viewport position."""
        scene_pos = self.mapToScene(pos)
        items = self.scene().items(scene_pos)
        for item in items:
             if isinstance(item, QGraphicsPixmapItem) and item != self._overlay_item and item != self._frame_preview_item:
                 for idx, pip_item in self._pip_items.items():
                     if pip_item == item:
                         return idx
        return -1

    def set_video_hidden(self, hidden: bool) -> None:
        """Set visibility of the main video track."""
        self._video_hidden = hidden
        self._video_item.setVisible(not hidden)
        if hidden:
            self.hide_cached_frame()

