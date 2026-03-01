"""자막 애니메이션 편집 다이얼로그."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
)
from PySide6.QtCore import Qt

from src.models.subtitle_animation import SubtitleAnimation
from src.utils.i18n import tr


class AnimationDialog(QDialog):
    """자막 진입·퇴출 애니메이션을 설정하는 다이얼로그."""

    _IN_EFFECTS = [
        ("none", tr("None")),
        ("fade", tr("Fade In")),
        ("slide_up", tr("Slide Up")),
        ("slide_down", tr("Slide Down")),
        ("typewriter", tr("Typewriter")),
    ]
    _OUT_EFFECTS = [
        ("none", tr("None")),
        ("fade", tr("Fade Out")),
    ]

    def __init__(self, parent=None, initial: SubtitleAnimation | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Subtitle Animation"))
        self.setMinimumWidth(360)
        self._init = initial.copy() if initial else SubtitleAnimation()
        self._build_ui()
        self._load_values(self._init)

    # ---------------------------------------------------------------- UI build

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Entry Effect 그룹
        entry_group = QGroupBox(tr("Entry Effect"))
        entry_form = QFormLayout(entry_group)

        self._in_combo = QComboBox()
        for key, label in self._IN_EFFECTS:
            self._in_combo.addItem(label, key)
        entry_form.addRow(tr("Effect"), self._in_combo)

        self._in_slider, self._in_label = self._make_slider()
        in_row = QHBoxLayout()
        in_row.addWidget(self._in_slider)
        in_row.addWidget(self._in_label)
        entry_form.addRow(tr("Duration"), in_row)

        layout.addWidget(entry_group)

        # Exit Effect 그룹
        exit_group = QGroupBox(tr("Exit Effect"))
        exit_form = QFormLayout(exit_group)

        self._out_combo = QComboBox()
        for key, label in self._OUT_EFFECTS:
            self._out_combo.addItem(label, key)
        exit_form.addRow(tr("Effect"), self._out_combo)

        self._out_slider, self._out_label = self._make_slider()
        out_row = QHBoxLayout()
        out_row.addWidget(self._out_slider)
        out_row.addWidget(self._out_label)
        exit_form.addRow(tr("Duration"), out_row)

        layout.addWidget(exit_group)

        # Reset 버튼
        reset_btn = QPushButton(tr("Reset to Default"))
        reset_btn.clicked.connect(self._on_reset)
        layout.addWidget(reset_btn)

        # OK / Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # 시그널 연결
        self._in_combo.currentIndexChanged.connect(self._on_in_effect_changed)
        self._out_combo.currentIndexChanged.connect(self._on_out_effect_changed)
        self._in_slider.valueChanged.connect(lambda v: self._in_label.setText(f"{v} ms"))
        self._out_slider.valueChanged.connect(lambda v: self._out_label.setText(f"{v} ms"))

    def _make_slider(self) -> tuple[QSlider, QLabel]:
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(100)
        slider.setMaximum(2000)
        slider.setSingleStep(50)
        slider.setPageStep(100)
        label = QLabel("300 ms")
        label.setFixedWidth(60)
        return slider, label

    # ---------------------------------------------------------------- Load/Save

    def _load_values(self, anim: SubtitleAnimation) -> None:
        # in_effect 콤보
        for i, (key, _) in enumerate(self._IN_EFFECTS):
            if key == anim.in_effect:
                self._in_combo.setCurrentIndex(i)
                break
        self._in_slider.setValue(anim.in_duration_ms)
        self._in_label.setText(f"{anim.in_duration_ms} ms")

        # out_effect 콤보
        for i, (key, _) in enumerate(self._OUT_EFFECTS):
            if key == anim.out_effect:
                self._out_combo.setCurrentIndex(i)
                break
        self._out_slider.setValue(anim.out_duration_ms)
        self._out_label.setText(f"{anim.out_duration_ms} ms")

        self._on_in_effect_changed()
        self._on_out_effect_changed()

    def get_values(self) -> SubtitleAnimation:
        """다이얼로그 설정값을 SubtitleAnimation으로 반환."""
        in_key = self._in_combo.currentData()
        out_key = self._out_combo.currentData()
        return SubtitleAnimation(
            in_effect=in_key,
            out_effect=out_key,
            in_duration_ms=self._in_slider.value(),
            out_duration_ms=self._out_slider.value(),
            slide_offset_px=self._init.slide_offset_px,
        )

    # ---------------------------------------------------------------- Slots

    def _on_in_effect_changed(self) -> None:
        key = self._in_combo.currentData()
        # "none"이면 duration 비활성화
        enabled = key != "none"
        self._in_slider.setEnabled(enabled)
        self._in_label.setEnabled(enabled)

    def _on_out_effect_changed(self) -> None:
        key = self._out_combo.currentData()
        enabled = key != "none"
        self._out_slider.setEnabled(enabled)
        self._out_label.setEnabled(enabled)

    def _on_reset(self) -> None:
        """모든 값을 기본값으로 초기화."""
        self._load_values(SubtitleAnimation())
