"""TTS 타이밍 검증 다이얼로그.

활성 트랙의 TTS 오디오를 Whisper로 재전사하고, 원본 자막의
타이밍을 자동 보정한다.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from src.models.subtitle import SubtitleTrack
from src.utils.i18n import tr
from src.workers.tts_verify_worker import TtsVerifyWorker


class TtsVerifyDialog(QDialog):
    """Whisper 역방향 검증 다이얼로그."""

    def __init__(self, track: SubtitleTrack, parent=None) -> None:
        """
        Args:
            track:  검증할 자막 트랙 (audio_path != "" 전제).
            parent: 부모 위젯.
        """
        super().__init__(parent)
        self.setWindowTitle(tr("TTS Timing Verification"))
        self.setMinimumWidth(420)
        self.setModal(True)

        self._track = track
        self._corrections: list = []
        self._thread: QThread | None = None
        self._worker: TtsVerifyWorker | None = None

        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 안내 텍스트
        hint = QLabel(tr(
            "활성 트랙의 TTS 오디오를 Whisper로 재전사합니다.\n"
            "원본 자막의 타이밍이 실제 발화에 맞게 자동 보정됩니다."
        ))
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 모델 선택
        model_row_layout = QVBoxLayout()
        model_label = QLabel(tr("Whisper Model:"))
        model_row_layout.addWidget(model_label)

        self._model_combo = QComboBox()
        self._model_combo.addItems(["tiny", "base", "small"])
        self._model_combo.setCurrentText("base")
        model_row_layout.addWidget(self._model_combo)
        layout.addLayout(model_row_layout)

        # 진행률 바
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 3)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        # 상태 레이블
        self._status_label = QLabel("")
        self._status_label.setVisible(False)
        layout.addWidget(self._status_label)

        # 결과 레이블
        self._result_label = QLabel("")
        self._result_label.setVisible(False)
        layout.addWidget(self._result_label)

        # 버튼
        self._start_btn = QPushButton(tr("Start Verification"))
        self._start_btn.clicked.connect(self._on_start)
        layout.addWidget(self._start_btn)

        self._apply_btn = QPushButton(tr("Apply Corrections"))
        self._apply_btn.setVisible(False)
        self._apply_btn.clicked.connect(self._on_apply)
        layout.addWidget(self._apply_btn)

        self._cancel_btn = QPushButton(tr("Cancel"))
        self._cancel_btn.clicked.connect(self._on_cancel)
        layout.addWidget(self._cancel_btn)

    # ------------------------------------------------------------------ Slots

    def _on_start(self) -> None:
        audio_path = Path(self._track.audio_path)
        if not audio_path.exists():
            QMessageBox.warning(
                self,
                tr("Audio File Not Found"),
                f"{tr('TTS audio file not found')}:\n{audio_path}",
            )
            return

        model_name = self._model_combo.currentText()

        # UI 전환
        self._start_btn.setEnabled(False)
        self._model_combo.setEnabled(False)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)
        self._status_label.setVisible(True)
        self._result_label.setVisible(False)
        self._apply_btn.setVisible(False)

        # 워커 시작
        self._thread = QThread(self)
        self._worker = TtsVerifyWorker(
            audio_path=audio_path,
            original_track=self._track,
            model_name=model_name,
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.status_update.connect(self._on_status)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._cleanup_thread)
        self._worker.error.connect(self._on_error)
        self._worker.error.connect(self._cleanup_thread)

        self._thread.start()

    def _on_status(self, msg: str) -> None:
        self._status_label.setText(msg)

    def _on_progress(self, current: int, total: int) -> None:
        self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(current)

    def _on_finished(self, corrections: list) -> None:
        self._corrections = corrections
        n = len(corrections)
        if n > 0:
            self._result_label.setText(tr("%d segments corrected") % n)
            self._apply_btn.setVisible(True)
        else:
            self._result_label.setText(tr("No corrections found"))
        self._result_label.setVisible(True)
        self._cancel_btn.setText(tr("Close"))

    def _on_error(self, msg: str) -> None:
        self._status_label.setText("")
        QMessageBox.critical(self, tr("Verification Error"), msg)
        self._start_btn.setEnabled(True)
        self._model_combo.setEnabled(True)

    def _on_apply(self) -> None:
        self.accept()

    def _on_cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
        self._cleanup_thread()
        self.reject()

    def _cleanup_thread(self) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(5000)
        self._thread = None
        self._worker = None

    # ------------------------------------------------------------------ Public

    def get_corrections(self) -> list:
        """Apply 버튼으로 닫힌 경우 보정 목록을 반환한다."""
        return self._corrections

    def closeEvent(self, event) -> None:
        self._on_cancel()
        super().closeEvent(event)
