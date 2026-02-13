"""Dialog for editing text overlay properties."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QDialogButtonBox,
    QGroupBox,
    QFormLayout,
    QColorDialog,
    QFontComboBox,
    QCheckBox,
)

from src.models.style import SubtitleStyle
from src.utils.i18n import tr


class TextOverlayDialog(QDialog):
    """Dialog to edit text overlay content and style."""

    def __init__(self, parent=None, text: str = "", style: SubtitleStyle | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Edit Text Overlay"))
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        self._style = style.copy() if style else SubtitleStyle()

        layout = QVBoxLayout(self)

        # Text content
        text_group = QGroupBox(tr("Text Content"))
        text_layout = QVBoxLayout()
        self._text_edit = QTextEdit()
        self._text_edit.setPlainText(text)
        self._text_edit.setMaximumHeight(100)
        text_layout.addWidget(self._text_edit)
        text_group.setLayout(text_layout)
        layout.addWidget(text_group)

        # Style settings
        style_group = QGroupBox(tr("Text Style"))
        style_layout = QFormLayout()

        # Font family
        self._font_combo = QFontComboBox()
        self._font_combo.setCurrentText(self._style.font_family)
        style_layout.addRow(tr("Font:"), self._font_combo)

        # Font size
        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(8, 200)
        self._font_size_spin.setValue(self._style.font_size)
        style_layout.addRow(tr("Size:"), self._font_size_spin)

        # Font style
        font_style_layout = QHBoxLayout()
        self._bold_check = QCheckBox(tr("Bold"))
        self._bold_check.setChecked(self._style.font_bold)
        self._italic_check = QCheckBox(tr("Italic"))
        self._italic_check.setChecked(self._style.font_italic)
        font_style_layout.addWidget(self._bold_check)
        font_style_layout.addWidget(self._italic_check)
        font_style_layout.addStretch()
        style_layout.addRow(tr("Style:"), font_style_layout)

        # Font color
        font_color_layout = QHBoxLayout()
        self._font_color_label = QLabel()
        self._font_color_label.setFixedSize(40, 20)
        self._font_color_label.setStyleSheet(f"background-color: {self._style.font_color}; border: 1px solid #ccc;")
        self._font_color_btn = QPushButton(tr("Choose..."))
        self._font_color_btn.clicked.connect(self._choose_font_color)
        font_color_layout.addWidget(self._font_color_label)
        font_color_layout.addWidget(self._font_color_btn)
        font_color_layout.addStretch()
        style_layout.addRow(tr("Text Color:"), font_color_layout)

        # Outline color
        outline_color_layout = QHBoxLayout()
        self._outline_color_label = QLabel()
        self._outline_color_label.setFixedSize(40, 20)
        self._outline_color_label.setStyleSheet(f"background-color: {self._style.outline_color}; border: 1px solid #ccc;")
        self._outline_color_btn = QPushButton(tr("Choose..."))
        self._outline_color_btn.clicked.connect(self._choose_outline_color)
        outline_color_layout.addWidget(self._outline_color_label)
        outline_color_layout.addWidget(self._outline_color_btn)
        outline_color_layout.addStretch()
        style_layout.addRow(tr("Outline Color:"), outline_color_layout)

        # Outline width
        self._outline_width_spin = QSpinBox()
        self._outline_width_spin.setRange(0, 10)
        self._outline_width_spin.setValue(self._style.outline_width)
        style_layout.addRow(tr("Outline Width:"), self._outline_width_spin)

        style_group.setLayout(style_layout)
        layout.addWidget(style_group)

        # Position settings
        position_group = QGroupBox(tr("Position (%)"))
        position_layout = QFormLayout()

        self._x_spin = QDoubleSpinBox()
        self._x_spin.setRange(0, 100)
        self._x_spin.setValue(50.0)
        self._x_spin.setSuffix("%")
        position_layout.addRow(tr("X (Horizontal):"), self._x_spin)

        self._y_spin = QDoubleSpinBox()
        self._y_spin.setRange(0, 100)
        self._y_spin.setValue(50.0)
        self._y_spin.setSuffix("%")
        position_layout.addRow(tr("Y (Vertical):"), self._y_spin)

        self._opacity_spin = QDoubleSpinBox()
        self._opacity_spin.setRange(0.0, 1.0)
        self._opacity_spin.setSingleStep(0.1)
        self._opacity_spin.setValue(1.0)
        position_layout.addRow(tr("Opacity:"), self._opacity_spin)

        position_group.setLayout(position_layout)
        layout.addWidget(position_group)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _choose_font_color(self) -> None:
        """Open color picker for font color."""
        color = QColorDialog.getColor(Qt.GlobalColor.white, self, tr("Choose Font Color"))
        if color.isValid():
            self._style.font_color = color.name()
            self._font_color_label.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #ccc;")

    def _choose_outline_color(self) -> None:
        """Open color picker for outline color."""
        color = QColorDialog.getColor(Qt.GlobalColor.black, self, tr("Choose Outline Color"))
        if color.isValid():
            self._style.outline_color = color.name()
            self._outline_color_label.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #ccc;")

    def get_text(self) -> str:
        """Return the edited text."""
        return self._text_edit.toPlainText()

    def get_style(self) -> SubtitleStyle:
        """Return the edited style."""
        self._style.font_family = self._font_combo.currentText()
        self._style.font_size = self._font_size_spin.value()
        self._style.font_bold = self._bold_check.isChecked()
        self._style.font_italic = self._italic_check.isChecked()
        self._style.outline_width = self._outline_width_spin.value()
        return self._style

    def get_position(self) -> tuple[float, float]:
        """Return (x_percent, y_percent)."""
        return (self._x_spin.value(), self._y_spin.value())

    def get_opacity(self) -> float:
        """Return opacity value."""
        return self._opacity_spin.value()

    def set_position(self, x_percent: float, y_percent: float) -> None:
        """Set position values."""
        self._x_spin.setValue(x_percent)
        self._y_spin.setValue(y_percent)

    def set_opacity(self, opacity: float) -> None:
        """Set opacity value."""
        self._opacity_spin.setValue(opacity)
