"""Background worker for video export."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from src.models.subtitle import SubtitleTrack
from src.services.video_exporter import export_video


class ExportWorker(QObject):
    """Runs video export in a background thread.

    Signals:
        progress(float, float): (total_sec, current_sec)
        finished(str): output path on success
        error(str): error message on failure
    """

    progress = Signal(float, float)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, video_path: Path, track: SubtitleTrack, output_path: Path):
        super().__init__()
        self._video_path = video_path
        self._track = track
        self._output_path = output_path

    def run(self) -> None:
        try:
            export_video(
                self._video_path,
                self._track,
                self._output_path,
                on_progress=lambda total, cur: self.progress.emit(total, cur),
            )
            self.finished.emit(str(self._output_path))
        except Exception as e:
            self.error.emit(str(e))
