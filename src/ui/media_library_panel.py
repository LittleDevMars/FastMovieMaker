"""Media library browser panel with thumbnail grid."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QCursor, QDrag, QFont, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QApplication,
)

from src.models.media_item import MediaItem
from src.utils.i18n import tr
from src.services.media_library_service import MediaLibraryService
from src.utils.config import MEDIA_FILTER, VIDEO_EXTENSIONS


class _ThumbnailWidget(QWidget):
    """Single thumbnail card in the media grid."""

    clicked = Signal(str)
    double_clicked = Signal(str)
    context_menu_requested = Signal(str, object)  # item_id, QPoint

    THUMB_SIZE = 140

    def __init__(self, item: MediaItem, owner: MediaLibraryPanel, parent=None):
        super().__init__(parent)
        self._item = item
        self._owner = owner
        self._selected = False
        self.setFixedSize(self.THUMB_SIZE + 10, self.THUMB_SIZE + 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Thumbnail image
        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(self.THUMB_SIZE, self.THUMB_SIZE - 20)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setStyleSheet(
            "background-color: #2a2a2a; border: 1px solid #444; border-radius: 4px;"
        )

        pixmap = self._load_thumbnail()
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                self.THUMB_SIZE, self.THUMB_SIZE - 20,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._thumb_label.setPixmap(scaled)
        else:
            self._thumb_label.setText("No Preview")
            self._thumb_label.setStyleSheet(
                self._thumb_label.styleSheet()
                + "color: #888; font-size: 10px;"
            )

        layout.addWidget(self._thumb_label)

        # File name label
        name_label = QLabel(item.file_name)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setStyleSheet("color: #ccc; font-size: 10px;")
        name_label.setMaximumWidth(self.THUMB_SIZE)
        name_label.setWordWrap(False)
        layout.addWidget(name_label)

    def set_selected(self, selected: bool) -> None:
        """Toggle visual selection state."""
        self._selected = selected
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._selected:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Tinted background
        painter.fillRect(self.rect(), QColor(0, 188, 212, 25))
        # Border
        pen = QPen(QColor("#00bcd4"), 2)
        painter.setPen(pen)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)

        # Proxy badge
        if self._item.is_proxy_generating:
            painter.setBrush(QColor(255, 165, 0))  # Orange background
            painter.setPen(Qt.PenStyle.NoPen)
            # Top-right corner
            rect = QRectF(self.THUMB_SIZE - 75, 4, 71, 14)
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(QColor("black"))
            painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            progress = getattr(self._item, "proxy_progress", 0)
            text = f"Gen: {progress}%" if progress > 0 else tr("Generating...")
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

        elif getattr(self._item, "has_proxy", False):
            painter.setBrush(QColor(0, 180, 0))    # Green background
            painter.setPen(Qt.PenStyle.NoPen)
            # Top-right corner of thumbnail
            rect = QRectF(self.THUMB_SIZE - 42, 4, 38, 14)
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(QColor("white"))
            painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "PROXY")

        painter.end()

    def _load_thumbnail(self) -> QPixmap | None:
        if self._item.thumbnail_path and Path(self._item.thumbnail_path).exists():
            return QPixmap(self._item.thumbnail_path)
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not hasattr(self, '_drag_start_pos') or self._drag_start_pos is None:
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < 20:
            return
            
        # Ensure current item is selected if not already (unless Ctrl is held)
        if self._item.item_id not in self._owner.get_selected_ids():
             self._owner.select_single(self._item.item_id)

        # Start drag
        drag = QDrag(self)
        mime = QMimeData()
        
        urls = []
        for item_id in self._owner.get_selected_ids():
            item = self._owner.get_item(item_id)
            if item:
                urls.append(QUrl.fromLocalFile(item.file_path))
        
        mime.setUrls(urls)
        mime.setData("application/x-fmm-media-type", self._item.media_type.encode())
        drag.setMimeData(mime)
        # Use thumbnail as drag pixmap
        thumb_pix = self._thumb_label.pixmap()
        if thumb_pix and not thumb_pix.isNull():
            scaled = thumb_pix.scaled(80, 60, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            drag.setPixmap(scaled)
            drag.setHotSpot(QPoint(scaled.width() // 2, scaled.height() // 2))
        drag.exec(Qt.DropAction.CopyAction)
        self._drag_start_pos = None

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = None
            self.clicked.emit(self._item.item_id)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self._item.item_id)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        self.context_menu_requested.emit(self._item.item_id, event.globalPos())


class MediaLibraryPanel(QWidget):
    """Side panel for browsing and managing media files."""

    video_open_requested = Signal(str)
    image_selected = Signal(str)
    image_insert_to_timeline = Signal(str)  # file_path
    subtitle_imported = Signal(str)  # file_path
    proxy_generation_requested = Signal(str)  # file_path
    proxy_generation_cancelled = Signal(str)  # file_path

    GRID_COLUMNS = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._service = MediaLibraryService()
        self._filter: str | None = None  # None = all, "video", "image"
        self._selected_ids: set[str] = set()
        self._thumb_widgets: dict[str, _ThumbnailWidget] = {}
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Import button
        import_btn = QPushButton(tr("+ Import from PC"))
        import_btn.setStyleSheet(
            "QPushButton { background-color: #00bcd4; color: white; "
            "border: none; border-radius: 4px; padding: 8px; font-weight: bold; }"
            "QPushButton:hover { background-color: #00acc1; }"
        )
        import_btn.clicked.connect(self._on_import)
        layout.addWidget(import_btn)

        # Filter tabs
        filter_row = QHBoxLayout()
        filter_row.setSpacing(2)
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)

        for label, filter_val in [(tr("All"), None), (tr("Images"), "image"), (tr("Videos"), "video")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(
                "QPushButton { border: 1px solid #555; border-radius: 3px; "
                "padding: 4px 10px; color: #ccc; background: #333; }"
                "QPushButton:checked { background: #00bcd4; color: white; border-color: #00bcd4; }"
            )
            btn.setProperty("filter_val", filter_val)
            btn.clicked.connect(lambda checked, fv=filter_val: self._on_filter_changed(fv))
            self._filter_group.addButton(btn)
            filter_row.addWidget(btn)
            if filter_val is None:
                btn.setChecked(True)

        layout.addLayout(filter_row)

        # Scroll area for thumbnails
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setStyleSheet("QScrollArea { border: none; background: #1e1e1e; }")

        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(4, 4, 4, 4)
        self._grid_layout.setSpacing(6)
        self._grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self._scroll.setWidget(self._grid_container)
        layout.addWidget(self._scroll, 1)

        # Bottom row: item count + clear all button
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        self._count_label = QLabel(f"{tr('My Media')} (0)")
        self._count_label.setStyleSheet("color: #999; font-size: 11px; padding: 2px;")
        bottom_row.addWidget(self._count_label)
        bottom_row.addStretch()

        clear_btn = QPushButton(tr("Clear All"))
        clear_btn.setStyleSheet(
            "QPushButton { background: #444; color: #ccc; border: 1px solid #555; "
            "border-radius: 3px; padding: 3px 8px; font-size: 11px; }"
            "QPushButton:hover { background: #c0392b; color: white; border-color: #e74c3c; }"
        )
        clear_btn.clicked.connect(self._on_clear_all)
        bottom_row.addWidget(clear_btn)
        layout.addLayout(bottom_row)

    # ------------------------------------------------------------------ Actions

    def _on_import(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("Import Media Files"), "", MEDIA_FILTER
        )
        if not files:
            return

        for file_path in files:
            path = Path(file_path)
            if path.suffix.lower() in {".srt", ".smi"}:
                self.subtitle_imported.emit(str(path))
            else:
                self._service.add_item(file_path)

        self._refresh()

    def _on_filter_changed(self, filter_val: str | None) -> None:
        self._filter = filter_val
        self._refresh()

    def _on_item_clicked(self, item_id: str) -> None:
        modifiers = QApplication.keyboardModifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            # Toggle selection
            if item_id in self._selected_ids:
                self._selected_ids.remove(item_id)
                if item_id in self._thumb_widgets:
                    self._thumb_widgets[item_id].set_selected(False)
            else:
                self._selected_ids.add(item_id)
                if item_id in self._thumb_widgets:
                    self._thumb_widgets[item_id].set_selected(True)
        else:
            # Single selection
            self.select_single(item_id)

        item = self._service.get_item(item_id)
        if item and item.media_type == "image":
            self.image_selected.emit(item.file_path)

    def select_single(self, item_id: str) -> None:
        """Select a single item and deselect others."""
        for old_id in list(self._selected_ids):
            if old_id in self._thumb_widgets:
                self._thumb_widgets[old_id].set_selected(False)
        self._selected_ids.clear()
        self._selected_ids.add(item_id)
        if item_id in self._thumb_widgets:
            self._thumb_widgets[item_id].set_selected(True)
            
    def get_selected_ids(self) -> set[str]:
        return self._selected_ids

    def get_item(self, item_id: str) -> MediaItem | None:
        return self._service.get_item(item_id)

    def _on_item_double_clicked(self, item_id: str) -> None:
        item = self._service.get_item(item_id)
        if not item:
            return
        if item.media_type == "video":
            self.video_open_requested.emit(item.file_path)
        elif item.media_type == "image":
            self.image_insert_to_timeline.emit(item.file_path)

    def _on_context_menu(self, item_id: str, pos) -> None:
        item = self._service.get_item(item_id)
        if not item:
            return

        menu = QMenu(self)

        if item.media_type == "video":
            open_action = menu.addAction(tr("Open Video"))
            open_action.triggered.connect(
                lambda checked=False, path=item.file_path: self.video_open_requested.emit(path)
            )
            
            if getattr(item, "is_proxy_generating", False):
                cancel_proxy_action = menu.addAction(tr("Cancel Proxy Generation"))
                cancel_proxy_action.triggered.connect(
                    lambda checked=False, path=item.file_path: self.proxy_generation_cancelled.emit(path)
                )
            else:
                proxy_action = menu.addAction(tr("Generate Proxy"))
                proxy_action.triggered.connect(
                    lambda checked=False, path=item.file_path: self.proxy_generation_requested.emit(path)
                )
            menu.addSeparator()

        if item.media_type == "image":
            insert_action = menu.addAction(tr("Insert to Timeline"))
            insert_action.triggered.connect(
                lambda: self.image_insert_to_timeline.emit(item.file_path)
            )
            menu.addSeparator()

        fav_text = tr("Unfavorite") if item.favorite else tr("Favorite")
        fav_action = menu.addAction(fav_text)
        fav_action.triggered.connect(lambda: self._toggle_favorite(item_id))

        menu.addSeparator()

        remove_action = menu.addAction(tr("Remove from Library"))
        remove_action.triggered.connect(lambda: self._remove_item(item_id))

        menu.exec(pos)

    def _toggle_favorite(self, item_id: str) -> None:
        self._service.toggle_favorite(item_id)
        self._refresh()

    def _remove_item(self, item_id: str) -> None:
        self._service.remove_item(item_id)
        self._refresh()

    def _on_clear_all(self) -> None:
        items = self._service.list_items()
        if not items:
            return
        reply = QMessageBox.question(
            self, tr("Clear All"),
            f"{len(items)} {tr('items will be removed from the media library. Continue?')}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._service.clear_all()
            self._refresh()

    # ------------------------------------------------------------------ Refresh

    def _refresh(self) -> None:
        """Rebuild the thumbnail grid."""
        # Clear existing widgets
        while self._grid_layout.count():
            child = self._grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self._thumb_widgets.clear()
        items = self._service.list_items(media_type=self._filter)

        # Favorites section
        favorites = [item for item in items if item.favorite]
        non_favorites = [item for item in items if not item.favorite]

        row = 0
        if favorites:
            fav_label = QLabel(f"{tr('Favorites')} ({len(favorites)})")
            fav_label.setStyleSheet("color: #00bcd4; font-size: 12px; font-weight: bold;")
            self._grid_layout.addWidget(fav_label, row, 0, 1, self.GRID_COLUMNS)
            row += 1
            row = self._add_items_to_grid(favorites, row)

        # All items section
        section_label = QLabel(f"{tr('My Media')} ({len(items)})")
        section_label.setStyleSheet("color: #999; font-size: 12px; font-weight: bold;")
        self._grid_layout.addWidget(section_label, row, 0, 1, self.GRID_COLUMNS)
        row += 1
        self._add_items_to_grid(non_favorites, row)

        self._count_label.setText(f"{tr('My Media')} ({len(items)})")

    def _add_items_to_grid(self, items: list[MediaItem], start_row: int) -> int:
        row = start_row
        col = 0
        for item in items:
            thumb = _ThumbnailWidget(item, self)
            thumb.clicked.connect(self._on_item_clicked)
            thumb.double_clicked.connect(self._on_item_double_clicked)
            thumb.context_menu_requested.connect(self._on_context_menu)
            self._thumb_widgets[item.item_id] = thumb
            if item.item_id in self._selected_ids:
                thumb.set_selected(True)
            self._grid_layout.addWidget(thumb, row, col)
            col += 1
            if col >= self.GRID_COLUMNS:
                col = 0
                row += 1
        if col > 0:
            row += 1
        return row

    def on_proxy_ready(self, source_path: str) -> None:
        """Handle proxy generation finished signal."""
        abs_path = str(Path(source_path).resolve())
        for item in self._service.list_items():
            if item.file_path == abs_path:
                item.has_proxy = True
                item.is_proxy_generating = False
                if item.item_id in self._thumb_widgets:
                    self._thumb_widgets[item.item_id].update()
                break

    def on_proxy_progress(self, source_path: str, progress: int) -> None:
        """Handle proxy generation progress signal."""
        abs_path = str(Path(source_path).resolve())
        for item in self._service.list_items():
            if item.file_path == abs_path:
                item.is_proxy_generating = True
                item.proxy_progress = progress
                if item.item_id in self._thumb_widgets:
                    self._thumb_widgets[item.item_id].update()
                break

    def on_proxy_failed(self, source_path: str) -> None:
        """Handle proxy generation failed/cancelled signal."""
        abs_path = str(Path(source_path).resolve())
        for item in self._service.list_items():
            if item.file_path == abs_path:
                item.is_proxy_generating = False
                item.proxy_progress = 0
                if item.item_id in self._thumb_widgets:
                    self._thumb_widgets[item.item_id].update()
                break

    def on_proxy_started(self, source_path: str) -> None:
        """Handle proxy generation started signal."""
        abs_path = str(Path(source_path).resolve())
        for item in self._service.list_items():
            if item.file_path == abs_path:
                item.is_proxy_generating = True
                item.proxy_progress = 0
                if item.item_id in self._thumb_widgets:
                    self._thumb_widgets[item.item_id].update()
                break

    def check_proxies(self) -> None:
        """Check for existing proxies for all items."""
        from src.services.proxy_service import ProxyService
        proxy_svc = ProxyService()
        for item in self._service.list_items():
            if item.media_type == "video":
                item.has_proxy = proxy_svc.has_proxy(item.file_path)
        self._refresh()
