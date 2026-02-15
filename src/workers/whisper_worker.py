"""Background worker for Whisper transcription."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from src.infrastructure.transcriber import WhisperTranscriber
from src.models.subtitle import SubtitleTrack
from src.services.audio_extractor import extract_audio_to_wav


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
    segment_ready = Signal(object)  # Signal(SubtitleSegment) but avoiding circular import issues in signal def
    finished = Signal(SubtitleTrack)
    error = Signal(str)

    def __init__(self, video_path: Path | None = None, audio_path: Path | None = None, model_name: str = "base", language: str = "ko"):
        super().__init__()
        self._video_path = video_path
        self._audio_path = audio_path
        self._model_name = model_name
        self._language = language
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        """Execute the full transcription pipeline."""
        wav_path: Path | None = None
        should_cleanup_wav = False
        try:
            # Step 1: Extract audio (skip if audio_path provided)
            if self._audio_path:
                wav_path = self._audio_path
                should_cleanup_wav = False
            else:
                self.status_update.emit("Extracting audio from video...")
                wav_path = extract_audio_to_wav(self._video_path)
                should_cleanup_wav = True

            if self._cancelled:
                return

            # Step 2 & 3: Transcribe (ITranscriber가 모델 로드/해제 포함)
            self.status_update.emit("Transcribing audio (faster-whisper)...")
            transcriber = WhisperTranscriber()
            track = transcriber.transcribe(
                wav_path,
                language=self._language,
                model_name=self._model_name,
                on_progress=lambda cur, total: self.progress.emit(cur, total),
                on_segment=lambda seg: self.segment_ready.emit(seg),
                check_cancelled=lambda: self._cancelled,
            )

            if not self._cancelled:
                self.finished.emit(track)

        except Exception as e:
            if not self._cancelled:
                import traceback
                tb = traceback.format_exc()
                # 디버그용: 콘솔에도 전체 traceback 출력
                print(f"[WhisperWorker ERROR]\n{tb}", flush=True)
                self.error.emit(str(e))

        finally:
            # Only delete temp WAV if we created it
            if should_cleanup_wav and wav_path is not None:
                try:
                    wav_path.unlink(missing_ok=True)
                except OSError:
                    pass
