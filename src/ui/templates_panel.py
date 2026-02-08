"""Template browser panel with thumbnail grid for overlay templates."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.models.overlay_template import OverlayTemplate
from src.services.template_service import TemplateService


class _TemplateThumbnail(QWidget):
    """Single thumbnail card in the template grid."""

    clicked = Signal(str)  # template_id

    THUMB_SIZE = 140

    def __init__(self, template: OverlayTemplate, parent=None):
        super().__init__(parent)
        self._template = template
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

        # Template name label
        name_label = QLabel(template.name)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setStyleSheet("color: #ccc; font-size: 10px;")
        name_label.setMaximumWidth(self.THUMB_SIZE)
        name_label.setWordWrap(False)
        layout.addWidget(name_label)

    def _load_thumbnail(self) -> QPixmap | None:
        if self._template.thumbnail_path and Path(self._template.thumbnail_path).exists():
            return QPixmap(self._template.thumbnail_path)
        if self._template.image_path and Path(self._template.image_path).exists():
            return QPixmap(self._template.image_path)
        return None

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        if selected:
            self.setStyleSheet("border: 2px solid #00bcd4; border-radius: 6px;")
        else:
            self.setStyleSheet("")

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._template.template_id)
        super().mouseReleaseEvent(event)


class TemplatesPanel(QWidget):
    """Side panel for browsing and applying overlay templates."""

    template_applied = Signal(object)   # OverlayTemplate
    template_cleared = Signal()

    GRID_COLUMNS = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._service = TemplateService()
        self._aspect_filter: str | None = None    # None = all
        self._source_filter: str = "builtin"      # "builtin" or "user"
        self._selected_id: str | None = None
        self._thumbnails: list[_TemplateThumbnail] = []
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Source filter tabs
        source_row = QHBoxLayout()
        source_row.setSpacing(2)
        self._source_group = QButtonGroup(self)
        self._source_group.setExclusive(True)

        for label, val in [("기본 템플릿", "builtin"), ("내 템플릿", "user")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(
                "QPushButton { border: 1px solid #555; border-radius: 3px; "
                "padding: 4px 10px; color: #ccc; background: #333; }"
                "QPushButton:checked { background: #00bcd4; color: white; border-color: #00bcd4; }"
            )
            btn.setProperty("source_val", val)
            btn.clicked.connect(lambda checked, v=val: self._on_source_changed(v))
            self._source_group.addButton(btn)
            source_row.addWidget(btn)
            if val == "builtin":
                btn.setChecked(True)

        layout.addLayout(source_row)

        # Aspect ratio filter tabs
        aspect_row = QHBoxLayout()
        aspect_row.setSpacing(2)
        self._aspect_group = QButtonGroup(self)
        self._aspect_group.setExclusive(True)

        for label, val in [("전체", None), ("16:9", "16:9"), ("9:16", "9:16")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(
                "QPushButton { border: 1px solid #555; border-radius: 3px; "
                "padding: 4px 8px; color: #ccc; background: #333; font-size: 11px; }"
                "QPushButton:checked { background: #555; color: white; border-color: #777; }"
            )
            btn.setProperty("aspect_val", val)
            btn.clicked.connect(lambda checked, v=val: self._on_aspect_changed(v))
            self._aspect_group.addButton(btn)
            aspect_row.addWidget(btn)
            if val is None:
                btn.setChecked(True)

        layout.addLayout(aspect_row)

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

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        apply_btn = QPushButton("적용하기")
        apply_btn.setStyleSheet(
            "QPushButton { background-color: #00bcd4; color: white; "
            "border: none; border-radius: 4px; padding: 8px; font-weight: bold; }"
            "QPushButton:hover { background-color: #00acc1; }"
        )
        apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(apply_btn)

        clear_btn = QPushButton("해제")
        clear_btn.setStyleSheet(
            "QPushButton { background-color: #555; color: white; "
            "border: none; border-radius: 4px; padding: 8px; }"
            "QPushButton:hover { background-color: #666; }"
        )
        clear_btn.clicked.connect(self._on_clear)
        btn_row.addWidget(clear_btn)

        layout.addLayout(btn_row)

        # Import button (for user templates)
        self._import_btn = QPushButton("+ 이미지 추가")
        self._import_btn.setStyleSheet(
            "QPushButton { background-color: #333; color: #ccc; "
            "border: 1px solid #555; border-radius: 4px; padding: 6px; }"
            "QPushButton:hover { background-color: #444; }"
        )
        self._import_btn.clicked.connect(self._on_import)
        self._import_btn.setVisible(False)  # Only show for user templates
        layout.addWidget(self._import_btn)

        # Count label
        self._count_label = QLabel("Templates (0)")
        self._count_label.setStyleSheet("color: #999; font-size: 11px; padding: 2px;")
        layout.addWidget(self._count_label)

    # ------------------------------------------------------------------ Actions

    def _on_source_changed(self, source: str) -> None:
        self._source_filter = source
        self._selected_id = None
        self._import_btn.setVisible(source == "user")
        self._refresh()

    def _on_aspect_changed(self, aspect: str | None) -> None:
        self._aspect_filter = aspect
        self._selected_id = None
        self._refresh()

    def _on_thumbnail_clicked(self, template_id: str) -> None:
        self._selected_id = template_id
        for thumb in self._thumbnails:
            thumb.set_selected(thumb._template.template_id == template_id)

    def _on_apply(self) -> None:
        if not self._selected_id:
            return
        template = self._service.get_template(self._selected_id)
        if template:
            self.template_applied.emit(template)

    def _on_clear(self) -> None:
        self._selected_id = None
        for thumb in self._thumbnails:
            thumb.set_selected(False)
        self.template_cleared.emit()

    def _on_import(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "오버레이 이미지 선택", "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)"
        )
        if not files:
            return

        for file_path in files:
            self._service.add_user_template(
                image_path=file_path,
                name=Path(file_path).stem,
                aspect_ratio="16:9",
            )

        self._refresh()

    # ------------------------------------------------------------------ Refresh

    def _refresh(self) -> None:
        """Rebuild the thumbnail grid."""
        # Clear existing widgets
        self._thumbnails.clear()
        while self._grid_layout.count():
            child = self._grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Get templates based on filters
        builtin_only = self._source_filter == "builtin"
        user_only = self._source_filter == "user"
        templates = self._service.list_templates(
            aspect_ratio=self._aspect_filter,
            builtin_only=builtin_only,
            user_only=user_only,
        )

        row = 0
        col = 0
        for template in templates:
            thumb = _TemplateThumbnail(template)
            thumb.clicked.connect(self._on_thumbnail_clicked)
            if template.template_id == self._selected_id:
                thumb.set_selected(True)
            self._thumbnails.append(thumb)
            self._grid_layout.addWidget(thumb, row, col)
            col += 1
            if col >= self.GRID_COLUMNS:
                col = 0
                row += 1

        self._count_label.setText(f"Templates ({len(templates)})")
