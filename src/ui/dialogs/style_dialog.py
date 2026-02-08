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
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from src.models.style import SubtitleStyle
from src.services.style_preset_manager import StylePresetManager
from src.utils.i18n import tr

_POSITIONS = [
    ("Bottom Center", "bottom-center"),
    ("Top Center", "top-center"),
    ("Bottom Left", "bottom-left"),
    ("Bottom Right", "bottom-right"),
]


class StyleDialog(QDialog):
    """Dialog for editing a SubtitleStyle."""

    def __init__(self, style: SubtitleStyle, parent=None, title: str = None):
        super().__init__(parent)
        self.setWindowTitle(title if title else tr("Edit Style"))
        self.setMinimumWidth(500)
        self._style = style.copy()
        self._preset_manager = StylePresetManager()

        # Create default presets if none exist
        if not self._preset_manager.list_presets():
            self._preset_manager.create_default_presets()

        layout = QHBoxLayout(self)

        # Left side: Preset list
        left_layout = QVBoxLayout()

        preset_label = QLabel(tr("Presets"))
        preset_label.setStyleSheet("font-weight: bold;")
        left_layout.addWidget(preset_label)

        self._preset_list = QListWidget()
        self._preset_list.setMaximumWidth(150)
        self._preset_list.itemClicked.connect(self._load_preset_from_list)
        left_layout.addWidget(self._preset_list)

        # Preset buttons
        preset_btn_layout = QVBoxLayout()

        self._save_preset_btn = QPushButton(tr("Save..."))
        self._save_preset_btn.clicked.connect(self._save_preset)
        preset_btn_layout.addWidget(self._save_preset_btn)

        self._rename_preset_btn = QPushButton(tr("Rename..."))
        self._rename_preset_btn.clicked.connect(self._rename_preset)
        preset_btn_layout.addWidget(self._rename_preset_btn)

        self._delete_preset_btn = QPushButton(tr("Delete"))
        self._delete_preset_btn.clicked.connect(self._delete_preset)
        preset_btn_layout.addWidget(self._delete_preset_btn)

        preset_btn_layout.addStretch()
        left_layout.addLayout(preset_btn_layout)

        layout.addLayout(left_layout)

        # Right side: Style editor
        right_layout = QVBoxLayout()

        # Refresh preset list
        self._refresh_preset_list()

        # Font group
        font_group = QGroupBox(tr("Font"))
        font_layout = QFormLayout(font_group)

        self._font_combo = QFontComboBox()
        self._font_combo.setCurrentFont(QFont(self._style.font_family))
        self._font_combo.currentFontChanged.connect(self._update_preview)
        font_layout.addRow(tr("Family:"), self._font_combo)

        self._size_spin = QSpinBox()
        self._size_spin.setRange(8, 72)
        self._size_spin.setValue(self._style.font_size)
        self._size_spin.valueChanged.connect(self._update_preview)
        font_layout.addRow(tr("Size:"), self._size_spin)

        style_row = QHBoxLayout()
        self._bold_check = QCheckBox(tr("Bold"))
        self._bold_check.setChecked(self._style.font_bold)
        self._bold_check.toggled.connect(self._update_preview)
        style_row.addWidget(self._bold_check)
        self._italic_check = QCheckBox(tr("Italic"))
        self._italic_check.setChecked(self._style.font_italic)
        self._italic_check.toggled.connect(self._update_preview)
        style_row.addWidget(self._italic_check)
        font_layout.addRow(tr("Style:"), style_row)

        right_layout.addWidget(font_group)

        # Colors group
        color_group = QGroupBox(tr("Colors"))
        color_layout = QFormLayout(color_group)

        self._font_color_btn = self._make_color_button(self._style.font_color)
        self._font_color_btn.clicked.connect(lambda: self._pick_color(self._font_color_btn))
        color_layout.addRow(tr("Text Color:"), self._font_color_btn)

        self._outline_color_btn = self._make_color_button(self._style.outline_color)
        self._outline_color_btn.clicked.connect(lambda: self._pick_color(self._outline_color_btn))
        color_layout.addRow(tr("Outline Color:"), self._outline_color_btn)

        self._outline_width_spin = QSpinBox()
        self._outline_width_spin.setRange(0, 10)
        self._outline_width_spin.setValue(self._style.outline_width)
        self._outline_width_spin.valueChanged.connect(self._update_preview)
        color_layout.addRow(tr("Outline Width:"), self._outline_width_spin)

        self._bg_color_btn = self._make_color_button(self._style.bg_color or "#00000000")
        self._bg_color_btn.clicked.connect(lambda: self._pick_color(self._bg_color_btn))
        color_layout.addRow(tr("Background:"), self._bg_color_btn)

        right_layout.addWidget(color_group)

        # Position group
        pos_group = QGroupBox(tr("Position"))
        pos_layout = QFormLayout(pos_group)

        self._position_combo = QComboBox()
        for label, value in _POSITIONS:
            self._position_combo.addItem(tr(label), value)
        current_idx = next(
            (i for i, (_, v) in enumerate(_POSITIONS) if v == self._style.position), 0
        )
        self._position_combo.setCurrentIndex(current_idx)
        self._position_combo.currentIndexChanged.connect(self._update_preview)
        pos_layout.addRow(tr("Position:"), self._position_combo)

        self._margin_spin = QSpinBox()
        self._margin_spin.setRange(0, 200)
        self._margin_spin.setValue(self._style.margin_bottom)
        self._margin_spin.valueChanged.connect(self._update_preview)
        pos_layout.addRow(tr("Margin:"), self._margin_spin)

        right_layout.addWidget(pos_group)

        # Preview
        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumHeight(60)
        self._preview_label.setStyleSheet("background-color: #333; border: 1px solid #555; padding: 10px;")
        right_layout.addWidget(self._preview_label)
        self._update_preview()

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        right_layout.addWidget(buttons)

        layout.addLayout(right_layout)

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
        color = QColorDialog.getColor(current, self, tr("Select Color"))
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
        self._preview_label.setText(tr("Sample Subtitle Text"))

    def _refresh_preset_list(self) -> None:
        """Refresh the preset list widget."""
        self._preset_list.clear()
        for preset_name in self._preset_manager.list_presets():
            self._preset_list.addItem(preset_name)

    def _get_current_style_from_ui(self) -> SubtitleStyle:
        """Get the current style from UI controls."""
        return SubtitleStyle(
            font_family=self._font_combo.currentFont().family(),
            font_size=self._size_spin.value(),
            font_bold=self._bold_check.isChecked(),
            font_italic=self._italic_check.isChecked(),
            font_color=self._font_color_btn.property("color_hex"),
            outline_color=self._outline_color_btn.property("color_hex"),
            outline_width=self._outline_width_spin.value(),
            bg_color=self._bg_color_btn.property("color_hex") if self._bg_color_btn.property("color_hex") not in ("#00000000", "#000000", None) else "",
            position=self._position_combo.currentData(),
            margin_bottom=self._margin_spin.value(),
        )

    def _apply_style_to_ui(self, style: SubtitleStyle) -> None:
        """Apply a style to the UI controls."""
        self._font_combo.setCurrentFont(QFont(style.font_family))
        self._size_spin.setValue(style.font_size)
        self._bold_check.setChecked(style.font_bold)
        self._italic_check.setChecked(style.font_italic)
        self._set_button_color(self._font_color_btn, style.font_color)
        self._set_button_color(self._outline_color_btn, style.outline_color)
        self._outline_width_spin.setValue(style.outline_width)
        self._set_button_color(self._bg_color_btn, style.bg_color or "#00000000")

        # Set position
        for i, (_, value) in enumerate(_POSITIONS):
            if value == style.position:
                self._position_combo.setCurrentIndex(i)
                break

        self._margin_spin.setValue(style.margin_bottom)
        self._update_preview()

    def _save_preset(self) -> None:
        """Save current style as a preset."""
        name, ok = QInputDialog.getText(
            self,
            tr("Save Preset"),
            tr("Enter preset name:"),
        )

        if not ok or not name.strip():
            return

        name = name.strip()

        # Check if preset already exists
        if self._preset_manager.preset_exists(name):
            reply = QMessageBox.question(
                self,
                tr("Overwrite Preset"),
                f"{tr('Preset')} '{name}' {tr('already exists. Overwrite?')}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Save the current style
        current_style = self._get_current_style_from_ui()
        self._preset_manager.save_preset(name, current_style)
        self._refresh_preset_list()

        QMessageBox.information(
            self,
            tr("Preset Saved"),
            f"{tr('Preset')} '{name}' {tr('has been saved successfully.')}",
        )

    def _load_preset_from_list(self) -> None:
        """Load the selected preset from the list."""
        item = self._preset_list.currentItem()
        if not item:
            return

        preset_name = item.text()
        style = self._preset_manager.load_preset(preset_name)

        if style:
            self._apply_style_to_ui(style)
        else:
            QMessageBox.warning(
                self,
                tr("Load Failed"),
                f"{tr('Could not load preset')} '{preset_name}'.",
            )

    def _rename_preset(self) -> None:
        """Rename the selected preset."""
        item = self._preset_list.currentItem()
        if not item:
            QMessageBox.information(
                self,
                tr("No Selection"),
                tr("Please select a preset to rename."),
            )
            return

        old_name = item.text()

        new_name, ok = QInputDialog.getText(
            self,
            tr("Rename Preset"),
            f"{tr('Enter new name for')} '{old_name}':",
            text=old_name,
        )

        if not ok or not new_name.strip():
            return

        new_name = new_name.strip()

        if new_name == old_name:
            return

        if self._preset_manager.preset_exists(new_name):
            QMessageBox.warning(
                self,
                tr("Name Conflict"),
                f"{tr('Preset')} '{new_name}' {tr('already exists. Please choose a different name.')}",
            )
            return

        if self._preset_manager.rename_preset(old_name, new_name):
            self._refresh_preset_list()
            QMessageBox.information(
                self,
                tr("Preset Renamed"),
                f"{tr('Preset renamed from')} '{old_name}' {tr('to')} '{new_name}'.",
            )
        else:
            QMessageBox.warning(
                self,
                tr("Rename Failed"),
                f"{tr('Could not rename preset')} '{old_name}'.",
            )

    def _delete_preset(self) -> None:
        """Delete the selected preset."""
        item = self._preset_list.currentItem()
        if not item:
            QMessageBox.information(
                self,
                tr("No Selection"),
                tr("Please select a preset to delete."),
            )
            return

        preset_name = item.text()

        reply = QMessageBox.question(
            self,
            tr("Delete Preset"),
            f"{tr('Are you sure you want to delete preset')} '{preset_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._preset_manager.delete_preset(preset_name)
            self._refresh_preset_list()
            QMessageBox.information(
                self,
                tr("Preset Deleted"),
                f"{tr('Preset')} '{preset_name}' {tr('has been deleted.')}",
            )
