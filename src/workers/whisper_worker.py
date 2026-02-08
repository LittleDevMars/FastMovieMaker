"""Background worker for Whisper transcription."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from src.models.subtitle import SubtitleTrack
from src.services.audio_extractor import extract_audio_to_wav
from src.services.whisper_service import load_model, release_model, transcribe


class WhisperWorker(QObject):
    """Runs faster-whisper transcription in a background thread.

    Signals:
        status_update(str): Status message for UI display.
        progress(int, int): (current, total) segment progress.
        finished(SubtitleTrack): Emitted with result on success.
        error(str): Emitted with error message on failure.
    """

    status_update = Signal(str)
    progress = Signal(int, int)
    finished = Signal(SubtitleTrack)
    error = Signal(str)

    def __init__(self, video_path: Path, model_name: str, language: str):
        super().__init__()
        self._video_path = video_path
        self._model_name = model_name
        self._language = language
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        """Execute the full transcription pipeline."""
        wav_path: Path | None = None
        model = None
        try:
            # Step 1: Extract audio
            self.status_update.emit("Extracting audio from video...")
            wav_path = extract_audio_to_wav(self._video_path)

            if self._cancelled:
                return

            # Step 2: Load model
            self.status_update.emit(f"Loading faster-whisper '{self._model_name}' model...")
            model = load_model(self._model_name)

            if self._cancelled:
                return

            # Step 3: Transcribe
            self.status_update.emit("Transcribing audio (faster-whisper)...")
            track = transcribe(
                model,
                wav_path,
                language=self._language,
                on_progress=lambda cur, total: self.progress.emit(cur, total),
            )

            if not self._cancelled:
                self.finished.emit(track)

        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))

        finally:
            # Cleanup
            if model is not None:
                release_model(model)
            if wav_path is not None:
                try:
                    wav_path.unlink(missing_ok=True)
                except OSError:
                    pass
