"""Dialog for individual video clip audio volume adjustment."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QSlider, QSpinBox, QDialogButtonBox
)
from src.utils.i18n import tr

class ClipVolumeDialog(QDialog):
    """Dialog with a slider and spinbox to adjust clip volume (0-200%)."""

    def __init__(self, parent=None, initial_volume: float = 1.0):
        super().__init__(parent)
        self.setWindowTitle(tr("Clip Volume"))
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)

        info_label = QLabel(tr("Adjust audio gain for this clip:"))
        layout.addWidget(info_label)

        controls_layout = QHBoxLayout()
        
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 200)
        self.slider.setValue(int(initial_volume * 100))
        
        self.spin = QSpinBox()
        self.spin.setRange(0, 200)
        self.spin.setSuffix("%")
        self.spin.setValue(int(initial_volume * 100))

        # Sync slider and spinbox
        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self.slider.setValue)

        controls_layout.addWidget(self.slider)
        controls_layout.addWidget(self.spin)
        layout.addLayout(controls_layout)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_volume(self) -> float:
        """Return volume as a float multiplier (0.0 to 2.0)."""
        return self.spin.value() / 100.0
