"""장면 감지 설정 및 결과 선택 다이얼로그."""

from __future__ import annotations

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

from src.utils.i18n import tr
from src.workers.scene_detect_worker import SceneDetectWorker


def _ms_to_timecode(ms: int) -> str:
    """ms → 'mm:ss.zzz' 포맷."""
    total_s, rem_ms = divmod(ms, 1000)
    m, s = divmod(total_s, 60)
    return f"{m:02d}:{s:02d}.{rem_ms:03d}"


class SceneDetectDialog(QDialog):
    """FFmpeg scdet 기반 장면 감지 + 분할 대상 선택 다이얼로그."""

    def __init__(self, parent, video_path: str):
        super().__init__(parent)
        self._video_path = video_path
        self._boundaries: list[int] = []
        self._thread: QThread | None = None
        self._worker: SceneDetectWorker | None = None

        self.setWindowTitle(tr("Detect Scenes"))
        self.setMinimumWidth(420)
        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ── Sensitivity ──
        layout.addWidget(QLabel(tr("Sensitivity")))
        sens_row = QHBoxLayout()
        sens_row.addWidget(QLabel(tr("Low")))
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 100)
        self._slider.setValue(40)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._slider.setTickInterval(10)
        sens_row.addWidget(self._slider)
        sens_row.addWidget(QLabel(tr("High")))
        self._sens_label = QLabel("40")
        self._sens_label.setMinimumWidth(30)
        sens_row.addWidget(self._sens_label)
        layout.addLayout(sens_row)
        self._slider.valueChanged.connect(lambda v: self._sens_label.setText(str(v)))

        # ── Min gap ──
        gap_row = QHBoxLayout()
        gap_row.addWidget(QLabel(tr("Min gap between scenes")))
        self._gap_spin = QSpinBox()
        self._gap_spin.setRange(100, 5000)
        self._gap_spin.setValue(500)
        self._gap_spin.setSuffix(" ms")
        gap_row.addWidget(self._gap_spin)
        gap_row.addStretch()
        layout.addLayout(gap_row)

        # ── Detect button + progress ──
        detect_row = QHBoxLayout()
        self._detect_btn = QPushButton(tr("Detect Scenes"))
        self._detect_btn.clicked.connect(self._on_detect)
        detect_row.addWidget(self._detect_btn)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.hide()
        detect_row.addWidget(self._progress)
        layout.addLayout(detect_row)

        # ── Result list ──
        self._result_label = QLabel(tr("Detected Scenes"))
        layout.addWidget(self._result_label)
        self._list = QListWidget()
        self._list.itemChanged.connect(self._update_apply_button)
        layout.addWidget(self._list)

        # ── Select All / Deselect All ──
        sel_row = QHBoxLayout()
        select_all_btn = QPushButton(tr("Select All"))
        select_all_btn.clicked.connect(self._select_all)
        sel_row.addWidget(select_all_btn)
        deselect_all_btn = QPushButton(tr("Deselect All"))
        deselect_all_btn.clicked.connect(self._deselect_all)
        sel_row.addWidget(deselect_all_btn)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # ── Dialog buttons ──
        self._btn_box = QDialogButtonBox()
        self._apply_btn = self._btn_box.addButton(
            tr("Apply Splits (0)"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._apply_btn.setEnabled(False)
        cancel_btn = self._btn_box.addButton(QDialogButtonBox.StandardButton.Cancel)
        self._btn_box.accepted.connect(self.accept)
        self._btn_box.rejected.connect(self._on_cancel)
        layout.addWidget(self._btn_box)

    # ---------------------------------------------------------------- Logic

    def _on_detect(self) -> None:
        self._detect_btn.setEnabled(False)
        self._progress.show()
        self._list.clear()
        self._boundaries = []
        self._update_apply_button()

        threshold = float(self._slider.value())
        min_gap = self._gap_spin.value()

        self._worker = SceneDetectWorker(self._video_path, threshold, min_gap)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _cleanup_thread(self) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
        self._detect_btn.setEnabled(True)
        self._progress.hide()

    def _on_finished(self, boundaries: list[int]) -> None:
        self._boundaries = boundaries
        self._list.blockSignals(True)
        self._list.clear()
        for ms in boundaries:
            item = QListWidgetItem(_ms_to_timecode(ms))
            item.setData(Qt.ItemDataRole.UserRole, ms)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._list.addItem(item)
        self._list.blockSignals(False)
        n = len(boundaries)
        self._result_label.setText(f"{tr('Detected Scenes')} ({n} {tr('found')})")
        self._update_apply_button()

    def _on_error(self, msg: str) -> None:
        QMessageBox.critical(self, tr("Error"), msg)

    def _on_cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
        self.reject()

    def _select_all(self) -> None:
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.CheckState.Checked)
        self._list.blockSignals(False)
        self._update_apply_button()

    def _deselect_all(self) -> None:
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self._list.blockSignals(False)
        self._update_apply_button()

    def _update_apply_button(self) -> None:
        n = len(self.get_selected_boundaries())
        self._apply_btn.setText(f"{tr('Apply Splits')} ({n})")
        self._apply_btn.setEnabled(n > 0)

    # ----------------------------------------------------------------- API

    def get_selected_boundaries(self) -> list[int]:
        """체크된 장면 경계 ms 목록 반환."""
        result = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result
