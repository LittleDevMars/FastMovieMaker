"""Dialog for selecting and configuring video transition effects."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QSpinBox, QPushButton, QFormLayout
)
from PySide6.QtCore import Qt
from src.utils.i18n import tr

class TransitionDialog(QDialog):
    """Dialog to choose transition type and duration."""

    TRANSITION_TYPES = [
        "fade", "wipeleft", "wiperight", "wipeup", "wipedown",
        "slideleft", "slideright", "slideup", "slidedown",
        "dissolve", "pixelize", "circlecrop", "rectcrop",
        "fadeblack", "fadewhite", "radial"
    ]

    def __init__(self, parent=None, initial_type="fade", initial_duration=500):
        super().__init__(parent)
        self.setWindowTitle(tr("Add Transition"))
        self.setMinimumWidth(300)

        self.layout = QVBoxLayout(self)
        self.form = QFormLayout()

        # Type selection
        self.type_combo = QComboBox()
        self.type_combo.addItems(self.TRANSITION_TYPES)
        if initial_type in self.TRANSITION_TYPES:
            self.type_combo.setCurrentText(initial_type)
        self.form.addRow(tr("Type:"), self.type_combo)

        # Duration selection
        self.dur_spin = QSpinBox()
        self.dur_spin.setRange(100, 5000)
        self.dur_spin.setSingleStep(100)
        self.dur_spin.setSuffix(" ms")
        self.dur_spin.setValue(initial_duration)
        self.form.addRow(tr("Duration:"), self.dur_spin)

        self.layout.addLayout(self.form)

        # Buttons
        self.btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton(tr("OK"))
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton(tr("Cancel"))
        self.cancel_btn.clicked.connect(self.reject)
        
        self.btn_layout.addStretch()
        self.btn_layout.addWidget(self.ok_btn)
        self.btn_layout.addWidget(self.cancel_btn)
        self.layout.addLayout(self.btn_layout)

    def get_data(self) -> tuple[str, int]:
        """Return (type, duration_ms)."""
        return self.type_combo.currentText(), self.dur_spin.value()
