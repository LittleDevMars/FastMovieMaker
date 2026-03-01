"""슬라이더 기반 컬러 보정 다이얼로그."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QDialogButtonBox, QGroupBox, QPushButton,
)
from src.utils.i18n import tr


class ColorCorrectionDialog(QDialog):
    """Brightness / Contrast / Saturation 슬라이더 다이얼로그."""

    def __init__(
        self,
        parent=None,
        initial_brightness: float = 1.0,
        initial_contrast: float = 1.0,
        initial_saturation: float = 1.0,
    ):
        super().__init__(parent)
        self.setWindowTitle(tr("Color Correction"))
        self.setMinimumWidth(380)
        self._build_ui(initial_brightness, initial_contrast, initial_saturation)

    def _make_slider_row(
        self, label: str, lo: int, hi: int, val: int, scale: float
    ) -> tuple[QHBoxLayout, QSlider]:
        """슬라이더 + 현재값 라벨 한 행 생성."""
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setFixedWidth(80)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(val)
        val_lbl = QLabel(f"{val / scale:.2f}")
        val_lbl.setFixedWidth(40)
        slider.valueChanged.connect(lambda v: val_lbl.setText(f"{v / scale:.2f}"))
        row.addWidget(lbl)
        row.addWidget(slider)
        row.addWidget(val_lbl)
        return row, slider

    def _build_ui(self, br: float, ct: float, sat: float) -> None:
        layout = QVBoxLayout(self)
        group = QGroupBox(tr("Visual Filters"))
        g_layout = QVBoxLayout(group)

        # Brightness: 0.5~2.0 → 슬라이더 50~200
        row, self._br_slider = self._make_slider_row(
            tr("Brightness"), 50, 200, int(br * 100), 100.0
        )
        g_layout.addLayout(row)

        # Contrast: 0.5~2.0 → 슬라이더 50~200
        row, self._ct_slider = self._make_slider_row(
            tr("Contrast"), 50, 200, int(ct * 100), 100.0
        )
        g_layout.addLayout(row)

        # Saturation: 0.0~3.0 → 슬라이더 0~300
        row, self._sat_slider = self._make_slider_row(
            tr("Saturation"), 0, 300, int(sat * 100), 100.0
        )
        g_layout.addLayout(row)

        layout.addWidget(group)

        reset_btn = QPushButton(tr("Reset to Default"))
        reset_btn.clicked.connect(self._on_reset)
        layout.addWidget(reset_btn)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_reset(self) -> None:
        self._br_slider.setValue(100)   # 1.0
        self._ct_slider.setValue(100)   # 1.0
        self._sat_slider.setValue(100)  # 1.0

    def get_values(self) -> dict[str, float]:
        return {
            "brightness": self._br_slider.value() / 100.0,
            "contrast":   self._ct_slider.value() / 100.0,
            "saturation": self._sat_slider.value() / 100.0,
        }
