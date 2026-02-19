"""Dialog for adjusting clip playback speed."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from src.utils.i18n import tr


class SpeedDialog(QDialog):
    """슬라이더 + 프리셋 버튼으로 클립 속도를 조절하는 다이얼로그."""

    _PRESETS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 4.0]
    # QSlider는 정수만 지원: 25 ~ 400 (value / 100 = speed)
    _SLIDER_MIN = 25
    _SLIDER_MAX = 400

    def __init__(
        self,
        parent=None,
        current_speed: float = 1.0,
        clip_duration_ms: int = 0,
    ):
        super().__init__(parent)
        self.setWindowTitle(tr("Change Clip Speed"))
        self.setMinimumWidth(380)

        self._clip_duration_ms = clip_duration_ms
        self._speed = current_speed

        self._build_ui()
        self._update_display(current_speed)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # --- 속도 슬라이더 ---
        slider_group = QGroupBox(tr("Speed"))
        slider_layout = QVBoxLayout(slider_group)

        self._speed_label = QLabel("1.00x", alignment=Qt.AlignmentFlag.AlignCenter)
        self._speed_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        slider_layout.addWidget(self._speed_label)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(self._SLIDER_MIN, self._SLIDER_MAX)
        self._slider.setValue(int(self._speed * 100))
        self._slider.setTickInterval(25)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._slider.valueChanged.connect(self._on_slider_changed)
        slider_layout.addWidget(self._slider)

        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("0.25x"))
        range_row.addStretch()
        range_row.addWidget(QLabel("4.00x"))
        slider_layout.addLayout(range_row)

        layout.addWidget(slider_group)

        # --- 프리셋 버튼 ---
        preset_group = QGroupBox(tr("Presets"))
        preset_layout = QHBoxLayout(preset_group)
        preset_layout.setSpacing(4)

        for val in self._PRESETS:
            btn = QPushButton(f"{val}x")
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _, v=val: self._set_speed(v))
            preset_layout.addWidget(btn)

        layout.addWidget(preset_group)

        # --- 길이 미리보기 ---
        self._duration_label = QLabel()
        self._duration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._duration_label.setStyleSheet("color: #aaa;")
        layout.addWidget(self._duration_label)

        # --- 버튼 ---
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_slider_changed(self, value: int) -> None:
        speed = value / 100.0
        self._update_display(speed)

    def _set_speed(self, speed: float) -> None:
        self._slider.setValue(int(speed * 100))

    def _update_display(self, speed: float) -> None:
        self._speed = speed
        self._speed_label.setText(f"{speed:.2f}x")

        if self._clip_duration_ms > 0:
            new_dur_ms = int(self._clip_duration_ms / speed)
            orig_s = self._clip_duration_ms / 1000
            new_s = new_dur_ms / 1000
            self._duration_label.setText(
                tr("Duration") + f": {orig_s:.1f}s → {new_s:.1f}s"
            )
        else:
            self._duration_label.setText("")

    def get_speed(self) -> float:
        """선택된 속도 값 반환 (0.25 ~ 4.0)."""
        return round(self._speed, 2)
