"""Background worker for scene detection using FFmpeg scdet filter."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from src.services.scene_detection_service import SceneDetectionService


class SceneDetectWorker(QObject):
    """FFmpeg scdet 장면 감지를 백그라운드 스레드에서 실행하는 워커.

    Signals:
        finished(list): 장면 경계 ms 목록으로 완료 시 발행.
        error(str): 오류 메시지로 실패 시 발행.
    """

    finished = Signal(list)
    error = Signal(str)

    def __init__(self, video_path: str, threshold: float, min_gap_ms: int):
        super().__init__()
        self._video_path = video_path
        self._threshold = threshold
        self._min_gap_ms = min_gap_ms
        self._cancelled = False

    def cancel(self) -> None:
        """취소 플래그 설정. run()이 종료된 후에 효력 발생."""
        self._cancelled = True

    def run(self) -> None:
        """장면 감지 실행. QThread.started 시그널에 연결해 사용."""
        try:
            boundaries = SceneDetectionService.detect_scenes(
                self._video_path,
                threshold=self._threshold,
                min_gap_ms=self._min_gap_ms,
            )
            if not self._cancelled:
                self.finished.emit(boundaries)
        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))
