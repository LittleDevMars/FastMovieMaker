"""Background worker for frame thumbnail cache extraction."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from src.services.frame_cache_service import FrameCacheService


class FrameCacheWorker(QObject):
    """Extracts frame thumbnails for multiple video sources in background."""

    status_update = Signal(str)
    source_ready = Signal(str)
    progress = Signal(int, int)      # (completed_sources, total_sources)
    finished = Signal(object)        # FrameCacheService
    error = Signal(str)

    def __init__(
        self,
        source_paths: list[str],
        durations: dict[str, int],
        cache_service: FrameCacheService,
    ) -> None:
        super().__init__()
        self._source_paths = source_paths
        self._durations = durations
        self._cache_service = cache_service
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            total = len(self._source_paths)
            for i, source_path in enumerate(self._source_paths):
                if self._cancelled:
                    return

                if self._cache_service.is_cached(source_path):
                    self.source_ready.emit(source_path)
                    self.progress.emit(i + 1, total)
                    continue

                name = Path(source_path).name
                self.status_update.emit(f"Caching frames: {name} ({i + 1}/{total})")

                output_dir = self._cache_service.source_cache_dir(source_path)
                duration = self._durations.get(source_path, 0)

                FrameCacheService.extract_frames(
                    source_path=source_path,
                    output_dir=output_dir,
                    interval_ms=1000,
                    width=640,
                    duration_ms=duration,
                    cancel_check=lambda: self._cancelled,
                )

                if not self._cancelled:
                    self.source_ready.emit(source_path)
                    self.progress.emit(i + 1, total)

            if not self._cancelled:
                self.status_update.emit("Frame cache ready")
                self.finished.emit(self._cache_service)

        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))
