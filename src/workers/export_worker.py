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

    def __init__(
        self,
        video_path: Path,
        track: SubtitleTrack,
        output_path: Path,
        audio_path: Path | None = None,
        overlay_path: Path | None = None,
        image_overlays: list | None = None,
        video_clips=None,
    ):
        super().__init__()
        self._video_path = video_path
        self._track = track
        self._output_path = output_path
        self._audio_path = audio_path
        self._overlay_path = overlay_path
        self._image_overlays = image_overlays
        self._video_clips = video_clips

    def run(self) -> None:
        try:
            export_video(
                self._video_path,
                self._track,
                self._output_path,
                on_progress=lambda total, cur: self.progress.emit(total, cur),
                audio_path=self._audio_path,
                overlay_path=self._overlay_path,
                image_overlays=self._image_overlays,
                video_clips=self._video_clips,
            )
            self.finished.emit(str(self._output_path))
        except Exception as e:
            self.error.emit(str(e))
