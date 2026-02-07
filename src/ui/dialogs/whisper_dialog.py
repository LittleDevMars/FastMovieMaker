"""Whisper settings and progress dialog."""

from pathlib import Path

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from src.models.subtitle import SubtitleTrack
from src.utils.config import WHISPER_DEFAULT_LANGUAGE, WHISPER_DEFAULT_MODEL, WHISPER_MODELS
from src.workers.whisper_worker import WhisperWorker


class WhisperDialog(QDialog):
    """Dialog for configuring and running Whisper transcription."""

    def __init__(self, video_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate Subtitles (Whisper)")
        self.setMinimumWidth(420)
        self.setModal(True)

        self._video_path = video_path
        self._result_track: SubtitleTrack | None = None
        self._thread: QThread | None = None
        self._worker: WhisperWorker | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Model selector
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Model:"))
        self._model_combo = QComboBox()
        self._model_combo.addItems(WHISPER_MODELS)
        self._model_combo.setCurrentText(WHISPER_DEFAULT_MODEL)
        model_layout.addWidget(self._model_combo, 1)
        layout.addLayout(model_layout)

        # Language selector
        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("Language:"))
        self._lang_combo = QComboBox()
        self._lang_combo.setEditable(True)
        self._lang_combo.addItems(["ko", "en", "ja", "zh", "auto"])
        self._lang_combo.setCurrentText(WHISPER_DEFAULT_LANGUAGE)
        lang_layout.addWidget(self._lang_combo, 1)
        layout.addLayout(lang_layout)

        # Status
        self._status_label = QLabel("Ready")
        layout.addWidget(self._status_label)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # indeterminate initially
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        # Buttons
        btn_layout = QHBoxLayout()
        self._start_btn = QPushButton("Start")
        self._start_btn.setDefault(True)
        self._start_btn.clicked.connect(self._on_start)
        btn_layout.addWidget(self._start_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self._cancel_btn)
        layout.addLayout(btn_layout)

    def _on_start(self) -> None:
        self._start_btn.setEnabled(False)
        self._model_combo.setEnabled(False)
        self._lang_combo.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)  # indeterminate

        model_name = self._model_combo.currentText()
        language = self._lang_combo.currentText()

        # Worker + Thread setup
        self._thread = QThread()
        self._worker = WhisperWorker(self._video_path, model_name, language)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.status_update.connect(self._on_status)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._cleanup_thread)
        self._worker.error.connect(self._cleanup_thread)

        self._thread.start()

    def _on_cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
        self._cleanup_thread()
        self.reject()

    def _on_status(self, message: str) -> None:
        self._status_label.setText(message)

    def _on_progress(self, current: int, total: int) -> None:
        if total > 0:
            self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(current)

    def _on_finished(self, track: SubtitleTrack) -> None:
        self._result_track = track
        self.accept()

    def _on_error(self, message: str) -> None:
        self._status_label.setText(f"Error: {message}")
        self._progress_bar.setVisible(False)
        self._start_btn.setEnabled(True)
        self._model_combo.setEnabled(True)
        self._lang_combo.setEnabled(True)

    def _cleanup_thread(self) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(5000)
        self._thread = None
        self._worker = None

    def result_track(self) -> SubtitleTrack | None:
        return self._result_track

    def closeEvent(self, event) -> None:
        self._on_cancel()
        super().closeEvent(event)
