"""Timeline thumbnail service for asynchronous filmstrip generation."""

from __future__ import annotations

import collections
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtGui import QImage

from src.utils.ffmpeg_utils import find_ffmpeg


class ThumbnailRunnable(QRunnable):
    """Worker to extract a single thumbnail using FFmpeg."""

    class Signals(QObject):
        # (source_path, timestamp_ms, image)
        result = Signal(str, int, QImage)

    def __init__(self, source_path: str, timestamp_ms: int, height: int):
        super().__init__()
        self.source_path = source_path
        self.timestamp_ms = timestamp_ms
        self.height = height
        self.signals = self.Signals()

    def run(self) -> None:
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            return

        # Double-SS for fast seeking
        target_sec = self.timestamp_ms / 1000.0
        input_seek = max(0.0, target_sec - 1.0)
        output_seek = target_sec - input_seek

        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NO_WINDOW

        # Output dimensions: keep aspect ratio, fixed height
        scale_filter = f"scale=-1:{self.height}"

        cmd = [
            ffmpeg,
            "-ss", f"{input_seek:.3f}",
            "-i", self.source_path,
            "-ss", f"{output_seek:.3f}",
            "-vf", scale_filter,
            "-frames:v", "1",
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "-q:v", "5",  # Reasonable quality
            "-",
        ]

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
                timeout=5,
            )
            if proc.returncode == 0 and proc.stdout:
                image = QImage.fromData(proc.stdout)
                if not image.isNull():
                    self.signals.result.emit(self.source_path, self.timestamp_ms, image)
        except Exception:
            pass


class TimelineThumbnailService(QObject):
    """Manages async thumbnail generation and caching."""

    thumbnail_ready = Signal(str, int, QImage)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._cache = collections.OrderedDict()
        self._cache_size = 200  # Max number of thumbnails to keep
        self._pending_requests = set()  # (source_path, timestamp_ms)

        self._thread_pool = QThreadPool()
        # Limit concurrent FFmpeg processes to avoid system lag
        self._thread_pool.setMaxThreadCount(3)

    @Slot(str, int, int)
    def request_thumbnail(self, source_path: str, timestamp_ms: int, height: int) -> Optional[QImage]:
        """Request a thumbnail. Returns image if cached, else returns None and starts worker."""
        key = (source_path, timestamp_ms)

        # 1. Check Cache
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]

        # 2. Check Pending
        if key in self._pending_requests:
            return None

        # 3. Start Worker
        self._pending_requests.add(key)
        
        worker = ThumbnailRunnable(source_path, timestamp_ms, height)
        # Connect signal using a lambda or partial to capture context if needed,
        # but here we can just execute a method on the service.
        # However, QRunnable signals can't directly connect to QObject slots safely across threads 
        # without proper handling. The QRunnable.Signals(QObject) pattern helps.
        worker.signals.result.connect(self._on_thumbnail_ready)
        self._thread_pool.start(worker)

        return None

    @Slot(str, int, QImage)
    def _on_thumbnail_ready(self, source_path: str, timestamp_ms: int, image: QImage) -> None:
        key = (source_path, timestamp_ms)
        if key in self._pending_requests:
            self._pending_requests.remove(key)

        # Add to cache
        self._cache[key] = image
        self._cache.move_to_end(key)

        # Evict if full
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

        self.thumbnail_ready.emit(source_path, timestamp_ms, image)

    def clear_cache(self) -> None:
        self._cache.clear()
        self._pending_requests.clear()
        # Note: We don't cancel running tasks easily with QThreadPool, but that's acceptable.

    def cancel_all_requests(self) -> None:
        self._pending_requests.clear()
        # QThreadPool.clear() removes queued tasks that haven't started yet
        self._thread_pool.clear()
