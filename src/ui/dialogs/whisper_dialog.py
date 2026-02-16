"""Whisper settings and progress dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from src.models.subtitle import SubtitleTrack
from src.utils.config import WHISPER_DEFAULT_LANGUAGE, WHISPER_DEFAULT_MODEL, WHISPER_MODELS
from src.utils.i18n import tr
from src.workers.whisper_worker import WhisperWorker

# 강제 닫기 시 스레드가 백그라운드에서 끝날 때까지 참조를 유지 (파괴 방지)
_orphaned_threads: list[QThread] = []


def _cleanup_orphaned_threads() -> None:
    """이미 끝난 고아 스레드 참조 해제."""
    _orphaned_threads[:] = [t for t in _orphaned_threads if t.isRunning()]


class WhisperDialog(QDialog):
    """Dialog for configuring and running Whisper transcription."""

    progress = Signal(int, int)
    finished = Signal(SubtitleTrack)
    error = Signal(str)
    segment_ready = Signal(object)  # Forwarded from worker

    def __init__(self, video_path: Path | None = None, audio_path: Path | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Generate Subtitles (Whisper)"))
        self.setMinimumWidth(420)
        # 비모달: 변환 중 메인 창의 자막/타임라인 실시간 미리보기가 보이도록
        self.setWindowModality(Qt.WindowModality.NonModal)

        if not video_path and not audio_path:
            raise ValueError("Either video_path or audio_path must be provided")

        self._video_path = video_path
        self._audio_path = audio_path
        self._result_track: SubtitleTrack | None = None
        self._thread: QThread | None = None
        self._worker: WhisperWorker | None = None
        self._segment_count = 0
        self._cancelling = False

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Model selector
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel(tr("Model:")))
        self._model_combo = QComboBox()
        self._model_combo.addItems(WHISPER_MODELS)
        self._model_combo.setCurrentText(WHISPER_DEFAULT_MODEL)
        model_layout.addWidget(self._model_combo, 1)
        layout.addLayout(model_layout)

        # Language selector
        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel(tr("Language:")))
        self._lang_combo = QComboBox()
        self._lang_combo.setEditable(True)
        self._lang_combo.addItems(["ko", "en", "ja", "zh", "auto"])
        self._lang_combo.setCurrentText(WHISPER_DEFAULT_LANGUAGE)
        lang_layout.addWidget(self._lang_combo, 1)
        layout.addLayout(lang_layout)

        # Status
        self._status_label = QLabel(tr("Ready"))
        layout.addWidget(self._status_label)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # indeterminate initially
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        # Buttons
        btn_layout = QHBoxLayout()
        self._start_btn = QPushButton(tr("Start"))
        self._start_btn.setDefault(True)
        self._start_btn.clicked.connect(self._on_start)
        btn_layout.addWidget(self._start_btn)

        self._cancel_btn = QPushButton(tr("Cancel"))
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self._cancel_btn)

        # 강제 닫기 버튼 (취소가 안 먹을 때 표시됨)
        self._force_close_btn = QPushButton(tr("Force Close"))
        self._force_close_btn.setStyleSheet("QPushButton { color: #ff6666; }")
        self._force_close_btn.clicked.connect(self._on_force_close)
        self._force_close_btn.setVisible(False)
        btn_layout.addWidget(self._force_close_btn)

        layout.addLayout(btn_layout)

    def _on_start(self) -> None:
        # 이미 스레드가 돌고 있으면 무시 (더블클릭/연타 방지)
        if self._thread is not None and self._thread.isRunning():
            return
        self._start_btn.setEnabled(False)
        self._model_combo.setEnabled(False)
        self._lang_combo.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)
        self._segment_count = 0

        model_name = self._model_combo.currentText()
        language = self._lang_combo.currentText()

        # 메인 스레드에서 torch/faster_whisper 사전 임포트 (필수)
        # QThread C 스택(~512KB)에서 import torch 시 스택 오버플로우 발생하므로
        # 메인 스레드(8MB)에서 먼저 로드 → sys.modules 캐시로 QThread는 재임포트 불필요
        self._status_label.setText(tr("Loading model modules..."))
        QApplication.processEvents()
        try:
            import src.services.whisper_service  # noqa: F401
        except Exception as e:
            self._on_error(f"Module load failed: {e}")
            return

        # Worker + Thread setup
        self._thread = QThread()
        self._worker = WhisperWorker(
            video_path=self._video_path,
            audio_path=self._audio_path,
            model_name=model_name,
            language=language,
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.status_update.connect(self._on_status)
        self._worker.progress.connect(self._on_progress)
        self._worker.segment_ready.connect(self._on_segment_ready)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._cleanup_thread)
        self._worker.error.connect(self._cleanup_thread)

        self._thread.start()

    # ---- Cancel ----

    def _on_cancel(self) -> None:
        """취소 버튼: worker에 취소 신호 후 즉시 다이얼로그 닫기.

        faster_whisper(ctranslate2)는 C 레벨 연산이라 Python에서 즉시 중단 불가.
        스레드는 백그라운드에서 다음 세그먼트 경계(약 5초 단위)에서 자연 종료된다.
        """
        if not self._worker or not self._thread:
            self.reject()
            return
        if self._cancelling:
            return
        self._cancelling = True
        self._worker.cancel()
        # 즉시 다이얼로그 닫기 (스레드는 백그라운드에서 곧 종료됨)
        self._on_force_close()

    def _show_force_close_if_needed(self) -> None:
        """취소 후 5초가 지나도 스레드가 안 끝났으면 강제 닫기 버튼 활성화."""
        if self._cancelling and self._thread and self._thread.isRunning():
            self._force_close_btn.setVisible(True)
            self._status_label.setText(
                tr("Cancelling...") + " " + tr("(Force Close available)")
            )

    def _on_force_close(self) -> None:
        """스레드를 백그라운드에 남기고 다이얼로그만 즉시 닫기."""
        self._disconnect_all_signals()
        # 스레드 참조를 모듈 레벨에 보관 → 스레드가 끝날 때까지 파괴 방지
        if self._thread and self._thread.isRunning():
            _orphaned_threads.append(self._thread)
            # 고아 스레드가 끝나면 자동 정리
            self._thread.finished.connect(_cleanup_orphaned_threads)
        self._thread = None
        self._worker = None
        self._cancelling = False
        try:
            self.segment_ready.disconnect()
        except RuntimeError:
            pass
        self.reject()

    def _disconnect_all_signals(self) -> None:
        """워커·스레드의 모든 시그널 연결 해제 (강제 닫기 전)."""
        if self._worker:
            for sig in [
                self._worker.status_update,
                self._worker.progress,
                self._worker.segment_ready,
                self._worker.finished,
                self._worker.error,
            ]:
                try:
                    sig.disconnect()
                except (TypeError, RuntimeError):
                    pass
        if self._thread:
            try:
                self._thread.started.disconnect()
            except (TypeError, RuntimeError):
                pass
            try:
                self._thread.finished.disconnect()
            except (TypeError, RuntimeError):
                pass

    # ---- Slots ----

    def _on_status(self, message: str) -> None:
        self._status_label.setText(message)

    def _on_segment_ready(self, segment) -> None:
        """실시간 미리보기: 메인 창으로 전달하고 세그먼트 수 갱신."""
        self._segment_count += 1
        self._status_label.setText(
            f"{tr('Transcribing audio (faster-whisper)...')} — {tr('Segments')}: {self._segment_count}"
        )
        self.segment_ready.emit(segment)

    def _on_progress(self, current: int, total: int) -> None:
        if total > 0:
            self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(current)
        else:
            self._progress_bar.setValue(current)
            self._progress_bar.setMaximum(0)

    def _on_finished(self, track: SubtitleTrack) -> None:
        self._result_track = track
        self.accept()

    def _on_error(self, message: str) -> None:
        self._status_label.setText(f"Error: {message}")
        self._progress_bar.setVisible(False)
        self._start_btn.setEnabled(True)
        self._model_combo.setEnabled(True)
        self._lang_combo.setEnabled(True)

    def _on_cancel_thread_finished(self) -> None:
        """취소 후 스레드가 끝났을 때 호출. 정리 후 다이얼로그 닫기."""
        self._cleanup_thread()
        try:
            self.segment_ready.disconnect()
        except RuntimeError:
            pass
        self._cancelling = False
        self.reject()

    def _cleanup_thread(self) -> None:
        """스레드 이벤트 루프 종료 후 참조 해제.

        moveToThread 패턴에서 worker.run() 반환 후에도 QThread 이벤트 루프는
        계속 돌기 때문에 quit()으로 먼저 멈춰야 wait()가 정상 동작한다.
        """
        if self._thread is None:
            return
        if self._thread.isRunning():
            self._thread.quit()       # 이벤트 루프 종료 요청
            self._thread.wait(10000)   # 최대 10초 대기
        if not self._thread.isRunning():
            self._thread = None
            self._worker = None

    def result_track(self) -> SubtitleTrack | None:
        return self._result_track

    def closeEvent(self, event) -> None:
        if self._cancelling:
            # 이미 취소 중 — 강제 닫기로 처리
            self._on_force_close()
            event.accept()
        elif self._thread and self._thread.isRunning():
            self._on_cancel()
            event.ignore()
        else:
            super().closeEvent(event)
