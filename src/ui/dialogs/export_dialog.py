"""Video export progress dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from src.models.subtitle import SubtitleTrack
from src.workers.export_worker import ExportWorker


class ExportDialog(QDialog):
    """Dialog that shows export progress."""

    def __init__(self, video_path: Path, track: SubtitleTrack, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Video")
        self.setMinimumWidth(400)
        self.setModal(True)

        self._video_path = video_path
        self._track = track
        self._thread: QThread | None = None
        self._worker: ExportWorker | None = None

        self._build_ui()
        self._ask_output_and_start()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._status_label = QLabel("Preparing export...")
        layout.addWidget(self._status_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        layout.addWidget(self._progress_bar)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._on_cancel)
        layout.addWidget(self._cancel_btn)

    def _ask_output_and_start(self) -> None:
        default_name = self._video_path.stem + "_subtitled.mp4"
        default_dir = str(self._video_path.parent / default_name)
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Video As", default_dir,
            "MP4 Files (*.mp4);;All Files (*)",
        )
        if not path:
            # User cancelled file dialog, close this dialog too
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.reject)
            return

        self._output_path = Path(path)
        self._start_export()

    def _start_export(self) -> None:
        self._status_label.setText("Exporting video with subtitles...")

        self._thread = QThread()
        self._worker = ExportWorker(self._video_path, self._track, self._output_path)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._cleanup_thread)
        self._worker.error.connect(self._cleanup_thread)

        self._thread.start()

    def _on_progress(self, total_sec: float, current_sec: float) -> None:
        if total_sec > 0:
            pct = min(100, int(current_sec / total_sec * 100))
            self._progress_bar.setValue(pct)
            self._status_label.setText(
                f"Exporting: {current_sec:.1f}s / {total_sec:.1f}s ({pct}%)"
            )

    def _on_finished(self, output_path: str) -> None:
        self._progress_bar.setValue(100)
        self._status_label.setText("Export complete!")
        self._cancel_btn.setText("Close")
        QMessageBox.information(self, "Export Complete", f"Video exported to:\n{output_path}")
        self.accept()

    def _on_error(self, message: str) -> None:
        self._status_label.setText(f"Error: {message}")
        self._cancel_btn.setText("Close")
        QMessageBox.critical(self, "Export Error", message)

    def _on_cancel(self) -> None:
        self._cleanup_thread()
        self.reject()

    def _cleanup_thread(self) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(5000)
        self._thread = None
        self._worker = None

    def closeEvent(self, event) -> None:
        self._on_cancel()
        super().closeEvent(event)
