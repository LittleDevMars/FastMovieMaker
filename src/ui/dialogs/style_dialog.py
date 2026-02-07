"""Subtitle style editing dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from src.models.style import SubtitleStyle

_POSITIONS = [
    ("Bottom Center", "bottom-center"),
    ("Top Center", "top-center"),
    ("Bottom Left", "bottom-left"),
    ("Bottom Right", "bottom-right"),
]


class StyleDialog(QDialog):
    """Dialog for editing a SubtitleStyle."""

    def __init__(self, style: SubtitleStyle, parent=None, title: str = "Edit Style"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self._style = style.copy()

        layout = QVBoxLayout(self)

        # Font group
        font_group = QGroupBox("Font")
        font_layout = QFormLayout(font_group)

        self._font_combo = QFontComboBox()
        self._font_combo.setCurrentFont(QFont(self._style.font_family))
        self._font_combo.currentFontChanged.connect(self._update_preview)
        font_layout.addRow("Family:", self._font_combo)

        self._size_spin = QSpinBox()
        self._size_spin.setRange(8, 72)
        self._size_spin.setValue(self._style.font_size)
        self._size_spin.valueChanged.connect(self._update_preview)
        font_layout.addRow("Size:", self._size_spin)

        style_row = QHBoxLayout()
        self._bold_check = QCheckBox("Bold")
        self._bold_check.setChecked(self._style.font_bold)
        self._bold_check.toggled.connect(self._update_preview)
        style_row.addWidget(self._bold_check)
        self._italic_check = QCheckBox("Italic")
        self._italic_check.setChecked(self._style.font_italic)
        self._italic_check.toggled.connect(self._update_preview)
        style_row.addWidget(self._italic_check)
        font_layout.addRow("Style:", style_row)

        layout.addWidget(font_group)

        # Colors group
        color_group = QGroupBox("Colors")
        color_layout = QFormLayout(color_group)

        self._font_color_btn = self._make_color_button(self._style.font_color)
        self._font_color_btn.clicked.connect(lambda: self._pick_color(self._font_color_btn))
        color_layout.addRow("Text Color:", self._font_color_btn)

        self._outline_color_btn = self._make_color_button(self._style.outline_color)
        self._outline_color_btn.clicked.connect(lambda: self._pick_color(self._outline_color_btn))
        color_layout.addRow("Outline Color:", self._outline_color_btn)

        self._outline_width_spin = QSpinBox()
        self._outline_width_spin.setRange(0, 10)
        self._outline_width_spin.setValue(self._style.outline_width)
        self._outline_width_spin.valueChanged.connect(self._update_preview)
        color_layout.addRow("Outline Width:", self._outline_width_spin)

        self._bg_color_btn = self._make_color_button(self._style.bg_color or "#00000000")
        self._bg_color_btn.clicked.connect(lambda: self._pick_color(self._bg_color_btn))
        color_layout.addRow("Background:", self._bg_color_btn)

        layout.addWidget(color_group)

        # Position group
        pos_group = QGroupBox("Position")
        pos_layout = QFormLayout(pos_group)

        self._position_combo = QComboBox()
        for label, value in _POSITIONS:
            self._position_combo.addItem(label, value)
        current_idx = next(
            (i for i, (_, v) in enumerate(_POSITIONS) if v == self._style.position), 0
        )
        self._position_combo.setCurrentIndex(current_idx)
        self._position_combo.currentIndexChanged.connect(self._update_preview)
        pos_layout.addRow("Position:", self._position_combo)

        self._margin_spin = QSpinBox()
        self._margin_spin.setRange(0, 200)
        self._margin_spin.setValue(self._style.margin_bottom)
        self._margin_spin.valueChanged.connect(self._update_preview)
        pos_layout.addRow("Margin:", self._margin_spin)

        layout.addWidget(pos_group)

        # Preview
        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumHeight(60)
        self._preview_label.setStyleSheet("background-color: #333; border: 1px solid #555; padding: 10px;")
        layout.addWidget(self._preview_label)
        self._update_preview()

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_style(self) -> SubtitleStyle:
        """Return the edited style after dialog is accepted."""
        self._style.font_family = self._font_combo.currentFont().family()
        self._style.font_size = self._size_spin.value()
        self._style.font_bold = self._bold_check.isChecked()
        self._style.font_italic = self._italic_check.isChecked()
        self._style.font_color = self._font_color_btn.property("color_hex")
        self._style.outline_color = self._outline_color_btn.property("color_hex")
        self._style.outline_width = self._outline_width_spin.value()
        bg = self._bg_color_btn.property("color_hex")
        self._style.bg_color = "" if bg in ("#00000000", "#000000", None) else bg
        self._style.position = self._position_combo.currentData()
        self._style.margin_bottom = self._margin_spin.value()
        return self._style

    def _make_color_button(self, hex_color: str) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(60, 24)
        btn.setProperty("color_hex", hex_color)
        self._set_button_color(btn, hex_color)
        return btn

    def _set_button_color(self, btn: QPushButton, hex_color: str) -> None:
        btn.setProperty("color_hex", hex_color)
        btn.setStyleSheet(f"background-color: {hex_color}; border: 1px solid #888;")

    def _pick_color(self, btn: QPushButton) -> None:
        current = QColor(btn.property("color_hex"))
        color = QColorDialog.getColor(current, self, "Select Color")
        if color.isValid():
            self._set_button_color(btn, color.name())
            self._update_preview()

    def _update_preview(self) -> None:
        family = self._font_combo.currentFont().family()
        size = self._size_spin.value()
        bold = "bold" if self._bold_check.isChecked() else "normal"
        italic = "italic" if self._italic_check.isChecked() else "normal"
        color = self._font_color_btn.property("color_hex") or "#FFFFFF"

        self._preview_label.setStyleSheet(
            f"background-color: #333; border: 1px solid #555; padding: 10px;"
            f"font-family: '{family}'; font-size: {size}px;"
            f"font-weight: {bold}; font-style: {italic};"
            f"color: {color};"
        )
        self._preview_label.setText("Sample Subtitle Text")
