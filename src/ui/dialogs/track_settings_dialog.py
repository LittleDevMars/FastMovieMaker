"""TrackSettingsDialog — 비디오 트랙 블렌드 모드 및 크로마키 설정 다이얼로그."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from src.utils.i18n import tr

_BLEND_MODES = ["normal", "screen", "multiply", "lighten", "darken", "chroma_key"]
_BLEND_LABELS = {
    "normal": "Normal",
    "screen": "Screen",
    "multiply": "Multiply",
    "lighten": "Lighten",
    "darken": "Darken",
    "chroma_key": "Chroma Key",
}


class TrackSettingsDialog(QDialog):
    """비디오 트랙 블렌드 모드 + 크로마키 설정 다이얼로그."""

    def __init__(
        self,
        blend_mode: str,
        chroma_color: str,
        chroma_similarity: float,
        chroma_blend: float,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Track Settings"))
        self.setMinimumWidth(340)

        self._chroma_color = chroma_color

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        # 블렌드 모드 콤보박스
        self._blend_combo = QComboBox()
        for bm in _BLEND_MODES:
            self._blend_combo.addItem(tr(_BLEND_LABELS[bm]), bm)
        idx = _BLEND_MODES.index(blend_mode) if blend_mode in _BLEND_MODES else 0
        self._blend_combo.setCurrentIndex(idx)
        form.addRow(tr("Blend Mode"), self._blend_combo)

        # 크로마키 섹션 (동적으로 숨김/표시)
        self._chroma_widget = QWidget()
        chroma_form = QFormLayout(self._chroma_widget)
        chroma_form.setContentsMargins(0, 0, 0, 0)

        # 키 컬러 버튼
        color_row = QHBoxLayout()
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(80, 24)
        self._update_color_btn()
        self._color_btn.clicked.connect(self._pick_color)
        color_row.addWidget(self._color_btn)
        color_row.addStretch()
        chroma_form.addRow(tr("Key Color"), color_row)

        # Similarity
        self._similarity_spin = QDoubleSpinBox()
        self._similarity_spin.setRange(0.01, 1.0)
        self._similarity_spin.setSingleStep(0.01)
        self._similarity_spin.setDecimals(2)
        self._similarity_spin.setValue(chroma_similarity)
        chroma_form.addRow(tr("Similarity"), self._similarity_spin)

        # Blend amount
        self._blend_spin = QDoubleSpinBox()
        self._blend_spin.setRange(0.0, 1.0)
        self._blend_spin.setSingleStep(0.01)
        self._blend_spin.setDecimals(2)
        self._blend_spin.setValue(chroma_blend)
        chroma_form.addRow(tr("Blend Amount"), self._blend_spin)

        layout.addWidget(self._chroma_widget)

        # OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._blend_combo.currentIndexChanged.connect(self._on_blend_changed)
        self._on_blend_changed()

    def _on_blend_changed(self) -> None:
        is_chroma = self._blend_combo.currentData() == "chroma_key"
        self._chroma_widget.setVisible(is_chroma)
        self.adjustSize()

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._chroma_color), self, tr("Key Color"))
        if color.isValid():
            self._chroma_color = color.name().upper()
            self._update_color_btn()

    def _update_color_btn(self) -> None:
        self._color_btn.setStyleSheet(
            f"background-color: {self._chroma_color}; border: 1px solid #555;"
        )
        self._color_btn.setText(self._chroma_color)

    # ── 프로퍼티 ──────────────────────────────────────────────────────

    @property
    def blend_mode(self) -> str:
        return self._blend_combo.currentData()

    @property
    def chroma_color(self) -> str:
        return self._chroma_color

    @property
    def chroma_similarity(self) -> float:
        return self._similarity_spin.value()

    @property
    def chroma_blend(self) -> float:
        return self._blend_spin.value()
