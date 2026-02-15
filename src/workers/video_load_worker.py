"""Background worker for video loading and conversion."""

from __future__ import annotations

import sys
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QThread

from src.infrastructure.ffmpeg_runner import get_ffmpeg_runner
from src.services.audio_merger import AudioMerger


class VideoLoadWorker(QObject):
    """Handles video file preparation (conversion if needed) in a background thread.

    Signals:
        progress(str): Status message for UI display.
        finished(Path, bool, Path): Emitted on success with (playback_path, has_audio, source_path).
        error(str): Emitted with error message on failure.
    """

    progress = Signal(str)
    finished = Signal(object, bool, object)  # playback_path (Path), has_audio (bool), source_path (Path)
    error = Signal(str)

    # Formats that macOS AVFoundation cannot play natively
    _NEEDS_CONVERT = {".mkv", ".avi", ".flv", ".wmv", ".webm"}

    def __init__(self, source_path: Path):
        super().__init__()
        self._source_path = source_path
        self._cancelled = False
        self._temp_path: Path | None = None

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        """Execute video preparation logic."""
        try:
            playback_path = self._source_path
            
            # 1. Check if conversion is needed
            if sys.platform == "darwin" and self._source_path.suffix.lower() in self._NEEDS_CONVERT:
                self.progress.emit(f"Converting {self._source_path.name} to MP4...")
                converted = self._convert_to_mp4(self._source_path)
                
                if self._cancelled:
                    if converted and converted.is_file():
                        converted.unlink(missing_ok=True)
                    return

                if converted:
                    playback_path = converted
                    self._temp_path = converted
                else:
                    self.error.emit(f"Could not convert {self._source_path.suffix} to MP4 for playback.")
                    return

            # 2. Check for audio stream
            self.progress.emit("Checking audio stream...")
            has_audio = False
            try:
                has_audio = AudioMerger.has_audio_stream(self._source_path)
            except Exception:
                has_audio = False

            if self._cancelled:
                return

            self.finished.emit(playback_path, has_audio, self._source_path)

        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))
                # Cleanup temp file if error occurred
                if self._temp_path is not None and self._temp_path.is_file():
                    self._temp_path.unlink(missing_ok=True)

    def _convert_to_mp4(self, source: Path) -> Path | None:
        """Convert a non-MP4 video to a temp MP4 file using FFmpeg."""
        runner = get_ffmpeg_runner()
        if not runner.is_available():
            return None

        tmp = Path(tempfile.mktemp(suffix=".mp4", prefix="fmm_"))

        args = [
            "-i", str(source),
            "-map", "0:v:0",
            "-map", "0:a:0?",
            "-c:v", "copy",
            "-c:a", "aac",
            "-ac", "2",
            "-b:a", "192k",
            "-strict", "experimental",
            "-y",
            str(tmp),
        ]

        try:
            result = runner.run(
                args,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )

            if result.returncode == 0 and tmp.is_file():
                return tmp

            if self._cancelled:
                return None

            self.progress.emit(f"Copy failed, re-encoding {source.name}...")

            args_reencode = [
                "-i", str(source),
                "-map", "0:v:0",
                "-map", "0:a:0?",
                "-c:v", "libx264", "-preset", "fast",
                "-c:a", "aac",
                "-ac", "2",
                "-b:a", "192k",
                "-strict", "experimental",
                "-y",
                str(tmp),
            ]

            result2 = runner.run(
                args_reencode,
                encoding="utf-8",
                errors="replace",
                timeout=600,
            )
            
            if result2.returncode == 0 and tmp.is_file():
                return tmp
            
            return None

        except subprocess.TimeoutExpired:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            return None
        except Exception:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise
