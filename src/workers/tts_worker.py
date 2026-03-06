"""Background worker for TTS (Text-to-Speech) generation."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

from src.models.subtitle import SubtitleTrack, SubtitleSegment
from src.services.tts_provider import (
    TTSRequestError,
    TTSRequestErrorCode,
    exception_to_tts_error_text,
    validate_tts_request,
)
from src.services.tts_provider_registry import get_provider
from src.services.text_splitter import TextSplitter, SplitStrategy
from src.services.audio_merger import AudioMerger
from src.utils.config import TTSEngine


class TTSWorker(QObject):
    """Runs TTS generation in a background thread.

    Signals:
        status_update(str): Status message for UI display.
        progress(int, int): (current, total) segment progress.
        finished(SubtitleTrack, str): Emitted with (subtitle track, audio path) on success.
        error(str): Emitted with error message on failure.
    """

    status_update = Signal(str)
    progress = Signal(int, int)
    finished = Signal(SubtitleTrack, str)  # (track, audio_path)
    error = Signal(str)

    def __init__(
        self,
        script: str,
        voice: str,
        strategy: SplitStrategy,
        speed: float,
        language: str = "ko",
        video_audio_path: Optional[Path] = None,
        bg_volume: float = 0.5,
        tts_volume: float = 1.0,
        engine: str = TTSEngine.EDGE_TTS,
    ):
        """
        Initialize TTS worker.

        Args:
            script: Text script to convert to speech
            voice: TTS voice name or ElevenLabs voice_id
            speed: Preferred normalized speed multiplier (e.g., 1.0)
            strategy: Text splitting strategy
            language: Language code (e.g., "ko", "en")
            video_audio_path: Optional path to video audio for mixing
            bg_volume: Background audio volume (0.0-1.0)
            tts_volume: TTS audio volume (0.0-1.0)
            engine: TTS engine to use (TTSEngine.EDGE_TTS or TTSEngine.ELEVENLABS)
        """
        super().__init__()
        self._script = script
        self._voice = voice
        self._speed = float(speed)
        self._strategy = strategy
        self._language = language
        self._video_audio_path = video_audio_path
        self._bg_volume = bg_volume
        self._tts_volume = tts_volume
        self._engine = engine
        self._cancelled = False

    def cancel(self) -> None:
        """Cancel the TTS generation."""
        self._cancelled = True

    def run(self) -> None:
        """Execute the full TTS pipeline."""
        try:
            asyncio.run(self._run_async())
        except Exception as e:
            if not self._cancelled:
                self.error.emit(exception_to_tts_error_text(e))

    async def _run_async(self) -> None:
        """Async TTS generation pipeline."""
        temp_dir = None
        tts_audio_path = None

        try:
            # Step 1: Split script into segments
            self.status_update.emit("Splitting script into segments...")
            splitter = TextSplitter()
            text_segments = splitter.split(self._script, self._strategy)

            if not text_segments:
                raise TTSRequestError(TTSRequestErrorCode.EMPTY_SCRIPT, "script is empty")

            if self._cancelled:
                return

            total_segments = len(text_segments)
            self.status_update.emit(f"Generating speech for {total_segments} segments...")

            # Step 2: Create temporary directory for audio files
            temp_dir = Path(tempfile.mkdtemp(prefix="tts_"))

            # Step 3: Generate TTS audio for each segment
            def on_progress(current: int, total: int):
                self.progress.emit(current, total)

            segments_data = [(seg.text, seg.index) for seg in text_segments]
            validate_tts_request(
                voice=self._voice,
                speed=self._speed,
                segments=segments_data,
            )
            provider = get_provider(self._engine)
            if provider is None:
                raise TTSRequestError(
                    TTSRequestErrorCode.PROVIDER_UNAVAILABLE,
                    f"provider_id={self._engine}",
                )
            audio_segments = await provider.generate_segments(
                segments=segments_data,
                voice=self._voice,
                speed=self._speed,
                output_dir=temp_dir,
                on_progress=on_progress,
            )

            if self._cancelled:
                return

            # Step 4: Merge all TTS audio segments
            self.status_update.emit("Merging audio segments...")
            tts_audio_path = temp_dir / "tts_merged.mp3"

            audio_files = [seg.audio_path for seg in audio_segments]
            AudioMerger.merge_audio_files(
                audio_files=audio_files,
                output_path=tts_audio_path,
                add_silence_ms=0  # No silence between segments
            )

            if self._cancelled:
                return

            # Step 5: Mix with video audio if provided
            final_audio_path = tts_audio_path
            if self._video_audio_path and self._video_audio_path.exists():
                self.status_update.emit("Mixing TTS with background audio...")
                mixed_audio_path = temp_dir / "mixed_audio.mp3"

                AudioMerger.mix_audio_tracks(
                    track1_path=self._video_audio_path,
                    track2_path=tts_audio_path,
                    output_path=mixed_audio_path,
                    track1_volume=self._bg_volume,
                    track2_volume=self._tts_volume
                )

                final_audio_path = mixed_audio_path

            if self._cancelled:
                return

            # Step 6: Create subtitle track with accurate timing
            self.status_update.emit("Creating subtitle track...")
            track = SubtitleTrack()
            current_time_ms = 0

            # Prepare persistent storage for audio segments
            from src.utils.config import APP_NAME
            user_data_dir = Path.home() / f".{APP_NAME.lower()}"
            user_data_dir.mkdir(parents=True, exist_ok=True)

            import shutil
            import uuid
            session_id = uuid.uuid4().hex[:8]

            for i, audio_seg in enumerate(audio_segments):
                duration_ms = int(audio_seg.duration_sec * 1000)

                # Copy individual segment audio to persistent location
                persistent_segment_audio = user_data_dir / f"tts_seg_{session_id}_{i:04d}.mp3"
                shutil.copy2(audio_seg.audio_path, persistent_segment_audio)

                segment = SubtitleSegment(
                    start_ms=current_time_ms,
                    end_ms=current_time_ms + duration_ms,
                    text=audio_seg.text,
                    audio_file=str(persistent_segment_audio)  # Store individual audio file path
                )

                track.add_segment(segment)
                current_time_ms += duration_ms

            # Step 7: Copy merged audio to a persistent location
            persistent_audio = user_data_dir / f"tts_audio_{session_id}.mp3"
            shutil.copy2(final_audio_path, persistent_audio)

            if not self._cancelled:
                self.status_update.emit("TTS generation complete!")
                self.finished.emit(track, str(persistent_audio))

        except Exception as e:
            if not self._cancelled:
                self.error.emit(exception_to_tts_error_text(e))

        finally:
            # Cleanup temporary directory
            if temp_dir and temp_dir.exists():
                import shutil
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass  # Best effort cleanup
