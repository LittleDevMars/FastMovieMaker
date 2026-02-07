"""Video player widget using QGraphicsView + QGraphicsVideoItem with subtitle overlay."""

from __future__ import annotations

from PySide6.QtCore import Qt, QSizeF
from PySide6.QtGui import QColor, QFont, QResizeEvent
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)

from src.models.subtitle import SubtitleTrack
from src.utils.config import SUBTITLE_FONT_SIZE, SUBTITLE_OVERLAY_MARGIN_BOTTOM


class VideoPlayerWidget(QGraphicsView):
    """Displays video with subtitle text overlay."""

    def __init__(self, player: QMediaPlayer, parent=None):
        super().__init__(parent)
        self._player = player
        self._subtitle_track: SubtitleTrack | None = None
        self._current_subtitle_text = ""

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
        font = QFont("Arial", SUBTITLE_FONT_SIZE, QFont.Weight.Bold)
        self._subtitle_item.setFont(font)
        self._subtitle_item.setDefaultTextColor(QColor("white"))
        self._subtitle_item.setZValue(10)
        self._subtitle_item.setVisible(False)
        self._scene.addItem(self._subtitle_item)

        # Connect player position to subtitle update
        self._player.positionChanged.connect(self._on_position_changed)

    def set_subtitle_track(self, track: SubtitleTrack | None) -> None:
        self._subtitle_track = track
        self._update_subtitle(self._player.position())

    def _on_position_changed(self, position_ms: int) -> None:
        self._update_subtitle(position_ms)

    def _update_subtitle(self, position_ms: int) -> None:
        if not self._subtitle_track:
            self._subtitle_item.setVisible(False)
            self._current_subtitle_text = ""
            return

        seg = self._subtitle_track.segment_at(position_ms)
        if seg:
            if seg.text != self._current_subtitle_text:
                self._current_subtitle_text = seg.text
                self._subtitle_item.setPlainText(seg.text)
                self._position_subtitle()
            self._subtitle_item.setVisible(True)
        else:
            self._subtitle_item.setVisible(False)
            self._current_subtitle_text = ""

    def _position_subtitle(self) -> None:
        """Center subtitle at the bottom of the video area."""
        view_rect = self.viewport().rect()
        scene_rect = self.mapToScene(view_rect).boundingRect()
        text_width = self._subtitle_item.boundingRect().width()
        text_height = self._subtitle_item.boundingRect().height()
        x = scene_rect.center().x() - text_width / 2
        y = scene_rect.bottom() - text_height - SUBTITLE_OVERLAY_MARGIN_BOTTOM
        self._subtitle_item.setPos(x, y)

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
