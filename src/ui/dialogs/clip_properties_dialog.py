"""Dialog for individual video clip properties (volume & visual filters)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QSlider, QSpinBox, QDialogButtonBox, QGroupBox, QDoubleSpinBox
)
from src.utils.i18n import tr

class ClipPropertiesDialog(QDialog):
    """Dialog to adjust clip volume and visual filters (brightness, contrast, saturation)."""

    def __init__(self, parent=None, initial_volume: float = 1.0, 
                 initial_brightness: float = 1.0, initial_contrast: float = 1.0, 
                 initial_saturation: float = 1.0, initial_speed: float = 1.0):
        super().__init__(parent)
        self.setWindowTitle(tr("Clip Properties"))
        self.setMinimumWidth(350)

        layout = QVBoxLayout(self)

        # 1. Volume Section
        vol_group = QGroupBox(tr("Audio Volume"))
        vol_layout = QVBoxLayout(vol_group)
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 200)
        self.vol_slider.setValue(int(initial_volume * 100))
        self.vol_spin = QSpinBox()
        self.vol_spin.setRange(0, 200)
        self.vol_spin.setSuffix("%")
        self.vol_spin.setValue(int(initial_volume * 100))
        self.vol_slider.valueChanged.connect(self.vol_spin.setValue)
        self.vol_spin.valueChanged.connect(self.vol_slider.setValue)
        h_layout = QHBoxLayout()
        h_layout.addWidget(self.vol_slider)
        h_layout.addWidget(self.vol_spin)
        vol_layout.addLayout(h_layout)
        layout.addWidget(vol_group)

        # 2. Speed Section
        speed_group = QGroupBox(tr("Playback Speed"))
        speed_layout = QVBoxLayout(speed_group)
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.25, 4.0)
        self.speed_spin.setSingleStep(0.1)
        self.speed_spin.setValue(initial_speed)
        self.speed_spin.setSuffix("x")
        speed_layout.addWidget(self.speed_spin)
        layout.addWidget(speed_group)

        # 3. Visual Filters Section
        filter_group = QGroupBox(tr("Visual Filters"))
        filter_layout = QVBoxLayout(filter_group)

        # Brightness
        filter_layout.addWidget(QLabel(tr("Brightness (0.5 to 2.0)")))
        self.bright_spin = QDoubleSpinBox()
        self.bright_spin.setRange(0.5, 2.0)
        self.bright_spin.setSingleStep(0.1)
        self.bright_spin.setValue(initial_brightness)
        filter_layout.addWidget(self.bright_spin)

        # Contrast
        filter_layout.addWidget(QLabel(tr("Contrast (0.5 to 2.0)")))
        self.cont_spin = QDoubleSpinBox()
        self.cont_spin.setRange(0.5, 2.0)
        self.cont_spin.setSingleStep(0.1)
        self.cont_spin.setValue(initial_contrast)
        filter_layout.addWidget(self.cont_spin)

        # Saturation
        filter_layout.addWidget(QLabel(tr("Saturation (0.0 to 3.0)")))
        self.sat_spin = QDoubleSpinBox()
        self.sat_spin.setRange(0.0, 3.0)
        self.sat_spin.setSingleStep(0.1)
        self.sat_spin.setValue(initial_saturation)
        filter_layout.addWidget(self.sat_spin)

        layout.addWidget(filter_group)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_values(self) -> dict[str, float]:
        """Return adjusted values as a dictionary."""
        return {
            "volume": self.vol_spin.value() / 100.0,
            "brightness": self.bright_spin.value(),
            "contrast": self.cont_spin.value(),
            "saturation": self.sat_spin.value(),
            "speed": self.speed_spin.value(),
        }
