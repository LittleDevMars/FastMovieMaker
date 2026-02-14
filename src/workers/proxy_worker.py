"""Background worker for asynchronous proxy media generation."""

from __future__ import annotations

import logging
from pathlib import Path
from PySide6.QtCore import QObject, Signal

from src.services import proxy_service

logger = logging.getLogger(__name__)

class ProxyWorker(QObject):
    """Handles proxy generation in a background thread.

    Signals:
        progress(str): Status message for UI display.
        finished(Path, Path): Emitted on success with (source_path, proxy_path).
        error(str): Emitted with error message on failure.
    """

    progress = Signal(str)
    finished = Signal(object, object)  # source_path (Path), proxy_path (Path)
    error = Signal(str)

    def __init__(self, source_path: Path, project_path: Path | None = None):
        super().__init__()
        self._source_path = source_path
        self._project_path = project_path
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        """Execute proxy generation logic."""
        try:
            if self._cancelled:
                return

            self.progress.emit(f"준비 중: {self._source_path.name}")
            
            proxy_path = proxy_service.get_proxy_path(self._source_path, self._project_path)
            
            if proxy_service.is_proxy_valid(self._source_path, proxy_path):
                self.progress.emit("기존 프록시 사용 가능")
                self.finished.emit(self._source_path, proxy_path)
                return

            self.progress.emit(f"프록시 생성 중 (720p): {self._source_path.name}")
            
            success = proxy_service.generate_proxy(self._source_path, proxy_path)
            
            if self._cancelled:
                if proxy_path.exists():
                    proxy_path.unlink(missing_ok=True)
                return

            if success:
                self.progress.emit("프록시 생성 완료")
                self.finished.emit(self._source_path, proxy_path)
            else:
                self.error.emit(f"프록시 생성 실패: {self._source_path.name}")

        except Exception as e:
            logger.exception(f"Error in ProxyWorker: {e}")
            if not self._cancelled:
                self.error.emit(str(e))
