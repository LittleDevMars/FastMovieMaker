"""Timeline waveform service for asynchronous waveform generation and caching."""

from __future__ import annotations

import collections
from pathlib import Path
from typing import Optional, Dict

from PySide6.QtCore import QObject, QThread, Signal, Slot

from src.services.waveform_service import WaveformData
from src.workers.waveform_worker import WaveformWorker


class TimelineWaveformService(QObject):
    """Manages async waveform generation and caching per source file.
    
    This service ensures that each source video's waveform is computed only once
    and is available to all clips referencing that source.
    """

    # (source_path, waveform_data)
    waveform_ready = Signal(str, object)
    status_updated = Signal(str, str)  # (source_path, status_text)

    # 최대 캐시 항목 수 — 각 WaveformData가 수 MB일 수 있으므로 제한
    _MAX_CACHE_SIZE = 20

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        # OrderedDict으로 LRU 구현 (HPP Ch.4 — 해시 테이블 + 순서 유지)
        self._cache: collections.OrderedDict[str, WaveformData] = collections.OrderedDict()
        self._workers: Dict[str, WaveformWorker] = {}
        self._threads: Dict[str, QThread] = {}

    def get_waveform(self, source_path: str | None) -> Optional[WaveformData]:
        """Get waveform data if available, else return None.

        LRU: 접근 시 move_to_end로 최근 사용 순서 갱신.
        Note: This does NOT start generation. Use request_waveform for that.
        """
        path_str = source_path or ""
        data = self._cache.get(path_str)
        if data is not None:
            self._cache.move_to_end(path_str)
        return data

    def request_waveform(self, source_path: str | None) -> None:
        """Request waveform generation for a source path if not already cached or started."""
        path_str = source_path or ""
        if not path_str:
             return

        # 1. Check Cache
        if path_str in self._cache:
            return

        # 2. Check if already working
        if path_str in self._workers:
            return

        # 3. Start Worker
        video_path = Path(path_str)
        if not video_path.exists():
            return

        worker = WaveformWorker(video_path)
        thread = QThread()
        worker.moveToThread(thread)

        worker.status_update.connect(lambda msg, p=path_str: self.status_updated.emit(p, msg))
        worker.finished.connect(lambda data, p=path_str: self._on_worker_finished(p, data))
        worker.error.connect(lambda msg, p=path_str: self._on_worker_error(p, msg))
        
        thread.started.connect(worker.run)
        # Proper cleanup
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        # We don't delete worker immediately because we might need it? 
        # Actually finished/error should trigger deletion.
        thread.finished.connect(lambda p=path_str: self._cleanup_worker(p))

        self._workers[path_str] = worker
        self._threads[path_str] = thread
        thread.start()

    def _on_worker_finished(self, source_path: str, data: WaveformData) -> None:
        self._cache[source_path] = data
        self._cache.move_to_end(source_path)
        # LRU eviction: 가장 오래 사용하지 않은 항목 제거
        while len(self._cache) > self._MAX_CACHE_SIZE:
            self._cache.popitem(last=False)
        self.waveform_ready.emit(source_path, data)

    def _on_worker_error(self, source_path: str, message: str) -> None:
        print(f"Waveform error for {source_path}: {message}")

    def _cleanup_worker(self, source_path: str) -> None:
        if source_path in self._workers:
            del self._workers[source_path]
        if source_path in self._threads:
            del self._threads[source_path]

    def cancel_all(self) -> None:
        """Cancel all running waveform computations."""
        for worker in self._workers.values():
            worker.cancel()
        for thread in self._threads.values():
            thread.quit()
            thread.wait()
        self._workers.clear()
        self._threads.clear()
