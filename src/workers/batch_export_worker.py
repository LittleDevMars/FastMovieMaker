"""Background worker for batch video export."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from src.models.export_preset import BatchExportJob
from src.models.subtitle import SubtitleTrack
from src.services.video_exporter import export_video


class BatchExportWorker(QObject):
    """Runs multiple export jobs sequentially in a background thread."""

    job_started = Signal(int, str)
    job_progress = Signal(int, float, float)
    job_finished = Signal(int, str)
    job_error = Signal(int, str)
    all_finished = Signal(int, int, int)

    def __init__(
        self,
        video_path: Path,
        track: SubtitleTrack,
        jobs: list[BatchExportJob],
        audio_path: Path | None = None,
    ):
        super().__init__()
        self._video_path = video_path
        self._track = track
        self._jobs = jobs
        self._audio_path = audio_path
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        succeeded = 0
        failed = 0

        for i, job in enumerate(self._jobs):
            if self._cancelled:
                job.status = "skipped"
                continue

            job.status = "running"
            self.job_started.emit(i, job.preset.name)

            try:
                export_video(
                    self._video_path,
                    self._track,
                    Path(job.output_path),
                    on_progress=lambda total, cur, idx=i: self.job_progress.emit(idx, total, cur),
                    audio_path=self._audio_path,
                    scale_width=job.preset.width,
                    scale_height=job.preset.height,
                    codec=job.preset.codec,
                )
                job.status = "completed"
                succeeded += 1
                self.job_finished.emit(i, job.output_path)
            except Exception as e:
                job.status = "failed"
                job.error_message = str(e)
                failed += 1
                self.job_error.emit(i, str(e))

        self.all_finished.emit(len(self._jobs), succeeded, failed)
