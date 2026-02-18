"""Dialog for editing video transition settings."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from src.services.transition_service import TransitionService
from src.utils.i18n import tr


class TransitionDialog(QDialog):
    """Dialog to select transition type and duration."""

    def __init__(
        self,
        parent=None,
        initial_type: str = "fade",
        initial_duration: int = 1000,
        outgoing_clip=None,
        incoming_clip=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(tr("Transition Settings"))
        self.resize(400, 250)

        self._type = initial_type
        self._duration = initial_duration
        self._outgoing_clip = outgoing_clip
        self._incoming_clip = incoming_clip

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Clip Info
        info_group = QGroupBox(tr("Transition Info"))
        info_layout = QHBoxLayout(info_group)

        out_name = "Clip A"
        if self._outgoing_clip and self._outgoing_clip.source_path:
            out_name = Path(self._outgoing_clip.source_path).name

        in_name = "Clip B"
        if self._incoming_clip and self._incoming_clip.source_path:
            in_name = Path(self._incoming_clip.source_path).name
        elif self._incoming_clip is None:
            in_name = tr("(End of Track)")

        info_label = QLabel(f"{out_name} ➔ {in_name}")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet("font-weight: bold; color: #ccc;")
        info_layout.addWidget(info_label)
        layout.addWidget(info_group)

        # Settings Form
        form_layout = QVBoxLayout()
        form_layout.setSpacing(10)

        # Type
        type_label = QLabel(tr("Transition Type:"))
        self._type_combo = QComboBox()
        transitions = TransitionService.get_available_transitions()
        for t in transitions:
            self._type_combo.addItem(t, t)

        idx = self._type_combo.findData(self._type)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)

        form_layout.addWidget(type_label)
        form_layout.addWidget(self._type_combo)

        # Duration
        dur_label = QLabel(tr("Duration (ms):"))
        self._dur_spin = QSpinBox()
        self._dur_spin.setRange(100, 5000)  # 0.1s to 5s
        self._dur_spin.setSingleStep(100)
        self._dur_spin.setValue(self._duration)
        self._dur_spin.setSuffix(" ms")

        form_layout.addWidget(dur_label)
        form_layout.addWidget(self._dur_spin)

        layout.addLayout(form_layout)
        layout.addStretch()

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> tuple[str, int]:
        """Return (transition_type, duration_ms)."""
        return self._type_combo.currentData(), self._dur_spin.value()