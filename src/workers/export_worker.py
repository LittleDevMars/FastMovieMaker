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
        video_tracks: list | None = None,
        text_overlays: list | None = None,
        codec: str = "h264",
        preset: str = "medium",
        crf: int = 23,
        scale_width: int = 0,
        scale_height: int = 0,
        use_gpu: bool = False,
        mix_with_original_audio: bool = False,
        video_volume: float = 1.0,
        audio_volume: float = 1.0,
    ):
        super().__init__()
        self._video_path = video_path
        self._track = track
        self._output_path = output_path
        self._audio_path = audio_path
        self._overlay_path = overlay_path
        self._image_overlays = image_overlays
        self._video_tracks = video_tracks
        self._text_overlays = text_overlays
        self._codec = codec
        self._preset = preset
        self._crf = crf
        self._scale_width = scale_width
        self._scale_height = scale_height
        self._use_gpu = use_gpu
        self._mix_with_original_audio = mix_with_original_audio
        self._video_volume = video_volume
        self._audio_volume = audio_volume

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
                video_tracks=self._video_tracks,
                text_overlays=self._text_overlays,
                codec=self._codec,
                preset=self._preset,
                crf=self._crf,
                scale_width=self._scale_width,
                scale_height=self._scale_height,
                mix_with_original_audio=self._mix_with_original_audio,
                video_volume=self._video_volume,
                audio_volume=self._audio_volume,
            )
            self.finished.emit(str(self._output_path))
        except Exception as e:
            self.error.emit(str(e))
