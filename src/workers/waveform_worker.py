"""Background worker for waveform peak computation."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from src.services.audio_extractor import extract_audio_to_wav
from src.services.waveform_service import compute_peaks_from_wav


class WaveformWorker(QObject):
    """Extracts audio and computes waveform peaks in a background thread.

    Signals:
        status_update(str): Status message for UI display.
        finished(object): Emitted with WaveformData on success.
        error(str): Emitted with error message on failure.
    """

    status_update = Signal(str)
    finished = Signal(object)  # WaveformData
    error = Signal(str)

    def __init__(self, video_path: Path):
        super().__init__()
        self._video_path = video_path
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        """Execute audio extraction + peak computation."""
        wav_path: Path | None = None
        try:
            self.status_update.emit("Extracting audio for waveform...")
            wav_path = extract_audio_to_wav(self._video_path)

            if self._cancelled:
                return

            self.status_update.emit("Computing waveform peaks...")
            waveform_data = compute_peaks_from_wav(wav_path)

            if not self._cancelled:
                self.status_update.emit("Waveform ready")
                self.finished.emit(waveform_data)

        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))

        finally:
            if wav_path is not None:
                try:
                    wav_path.unlink(missing_ok=True)
                except OSError:
                    pass
