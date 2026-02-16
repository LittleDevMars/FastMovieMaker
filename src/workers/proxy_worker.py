"""Worker for generating proxy media in background."""

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from src.services.proxy_service import generate_proxy, get_proxy_path


class ProxyWorker(QObject):
    """Generates a proxy file for a video."""

    finished = Signal(str)  # proxy_path
    progress = Signal(int)  # percentage
    error = Signal(str)     # error message

    def __init__(self, source_path: str):
        super().__init__()
        self._source_path = Path(source_path)

    def run(self) -> None:
        proxy_path = get_proxy_path(self._source_path)
        success = generate_proxy(
            self._source_path, 
            proxy_path, 
            on_progress=self.progress.emit,
            cancel_check=lambda: self._cancelled
        )
        if success:
            self.finished.emit(str(proxy_path))
        else:
            self.error.emit(f"Proxy generation failed for {self._source_path.name}")
            self.finished.emit("")