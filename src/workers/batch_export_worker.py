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
        overlay_path: Path | None = None,
        image_overlays: list | None = None,
        text_overlays: list | None = None,
        mix_with_original_audio: bool = False,
        video_volume: float = 1.0,
        audio_volume: float = 1.0,
    ):
        super().__init__()
        self._video_path = video_path
        self._track = track
        self._jobs = jobs
        self._audio_path = audio_path
        self._overlay_path = overlay_path
        self._image_overlays = image_overlays
        self._text_overlays = text_overlays
        self._mix_with_original_audio = mix_with_original_audio
        self._video_volume = video_volume
        self._audio_volume = audio_volume
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
                    overlay_path=self._overlay_path,
                    image_overlays=self._image_overlays,
                    text_overlays=self._text_overlays,
                    mix_with_original_audio=self._mix_with_original_audio,
                    video_volume=self._video_volume,
                    audio_volume=self._audio_volume,
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
