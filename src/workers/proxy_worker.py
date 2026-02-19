"""Worker for generating proxy media in a background thread."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from src.services.proxy_service import generate_proxy, get_proxy_path


class ProxyWorker(QObject):
    """Worker to run proxy generation."""

    progress = Signal(int)
    finished = Signal(str)  # proxy_path or empty string if failed/cancelled
    error = Signal(str)

    def __init__(self, source_path: str):
        super().__init__()
        self._source_path = source_path
        self._is_cancelled = False

    def run(self) -> None:
        """Run the proxy generation."""
        try:
            src = Path(self._source_path)
            dst = get_proxy_path(src)

            success = generate_proxy(
                src,
                dst,
                on_progress=self.progress.emit,
                cancel_check=self.check_cancelled
            )

            if self._is_cancelled:
                self.finished.emit("")
            elif success:
                self.finished.emit(str(dst))
            else:
                self.error.emit(f"Proxy generation failed for {self._source_path}")
                self.finished.emit("")

        except Exception as e:
            if not self._is_cancelled:
                self.error.emit(str(e))
            self.finished.emit("")

    def cancel(self) -> None:
        """Request cancellation."""
        self._is_cancelled = True

    def check_cancelled(self) -> bool:
        """Check if cancellation was requested."""
        return self._is_cancelled