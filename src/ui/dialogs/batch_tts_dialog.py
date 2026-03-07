"""배치 TTS 생성 다이얼로그.

여러 .txt 파일을 한 번에 TTS 변환하여 .mp3 + .srt 쌍으로 출력한다.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.services.settings_manager import SettingsManager
from src.services.text_splitter import SplitStrategy
from src.services.tts_error_presenter import to_user_message
from src.services.tts_provider_registry import get_all_providers, get_provider
from src.utils.i18n import tr
from src.workers.batch_tts_worker import BatchTtsJob, BatchTtsResult, BatchTtsWorker

_EDGE_PROVIDER_ID = "edge_tts"

_STRATEGY_OPTIONS = [
    (SplitStrategy.SENTENCE, "문장 단위"),
    (SplitStrategy.NEWLINE, "줄바꿈 단위"),
    (SplitStrategy.FIXED_LENGTH, "고정 길이"),
]


class BatchTtsDialog(QDialog):
    """배치 TTS 생성 다이얼로그."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Batch TTS Generation"))
        self.setMinimumSize(680, 580)
        self.setModal(True)

        self._thread: QThread | None = None
        self._worker: BatchTtsWorker | None = None
        self._results: list[BatchTtsResult] = []
        self._provider_available = True

        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ── 파일 그룹 ──
        file_group = QGroupBox(tr("Input Files"))
        file_layout = QVBoxLayout(file_group)

        self._file_list = QListWidget()
        self._file_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._file_list.setMinimumHeight(120)
        file_layout.addWidget(self._file_list)

        file_btn_row = QHBoxLayout()
        add_files_btn = QPushButton(tr("Add Files"))
        add_files_btn.clicked.connect(self._on_add_files)
        file_btn_row.addWidget(add_files_btn)

        remove_btn = QPushButton(tr("Remove"))
        remove_btn.clicked.connect(self._on_remove_files)
        file_btn_row.addWidget(remove_btn)
        file_btn_row.addStretch()
        file_layout.addLayout(file_btn_row)
        layout.addWidget(file_group)

        # ── 설정 그룹 ──
        settings_group = QGroupBox(tr("Settings"))
        settings_layout = QVBoxLayout(settings_group)

        # 출력 폴더
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel(tr("Output Folder:")))
        self._output_edit = QLineEdit()
        self._output_edit.setPlaceholderText(tr("Select output folder..."))
        out_row.addWidget(self._output_edit, 1)
        browse_btn = QPushButton(tr("Browse\u2026"))
        browse_btn.clicked.connect(self._on_browse_output)
        out_row.addWidget(browse_btn)
        settings_layout.addLayout(out_row)

        # 엔진
        engine_row = QHBoxLayout()
        engine_row.addWidget(QLabel(tr("Engine:")))
        self._engine_combo = QComboBox()
        self._populate_engine_options()
        self._engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        engine_row.addWidget(self._engine_combo, 1)
        settings_layout.addLayout(engine_row)

        # 음성
        voice_row = QHBoxLayout()
        voice_row.addWidget(QLabel(tr("Voice:")))
        self._voice_combo = QComboBox()
        voice_row.addWidget(self._voice_combo, 1)
        settings_layout.addLayout(voice_row)
        self._voice_state_label = QLabel("")
        settings_layout.addWidget(self._voice_state_label)

        # 속도 슬라이더 (0.5x ~ 2.0x, step 0.1)
        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel(tr("Speed:")))
        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setRange(5, 20)   # 0.5 ~ 2.0 (×10)
        self._speed_slider.setValue(10)       # 1.0x
        self._speed_slider.setTickInterval(5)
        speed_row.addWidget(self._speed_slider, 1)
        self._speed_label = QLabel("1.0x")
        self._speed_label.setMinimumWidth(40)
        self._speed_slider.valueChanged.connect(
            lambda v: self._speed_label.setText(f"{v / 10:.1f}x")
        )
        speed_row.addWidget(self._speed_label)
        settings_layout.addLayout(speed_row)

        # 분할 전략
        strategy_row = QHBoxLayout()
        strategy_row.addWidget(QLabel(tr("Split Strategy:")))
        self._strategy_combo = QComboBox()
        for strategy, label in _STRATEGY_OPTIONS:
            self._strategy_combo.addItem(label, strategy)
        strategy_row.addWidget(self._strategy_combo, 1)
        settings_layout.addLayout(strategy_row)

        layout.addWidget(settings_group)

        # ── 진행 그룹 ──
        self._progress_group = QGroupBox(tr("Progress"))
        progress_layout = QVBoxLayout(self._progress_group)

        self._current_file_label = QLabel("-")
        progress_layout.addWidget(self._current_file_label)

        file_pb_row = QHBoxLayout()
        file_pb_row.addWidget(QLabel(tr("Current file:")))
        self._file_progress = QProgressBar()
        self._file_progress.setRange(0, 100)
        file_pb_row.addWidget(self._file_progress)
        progress_layout.addLayout(file_pb_row)

        overall_pb_row = QHBoxLayout()
        overall_pb_row.addWidget(QLabel(tr("Overall:")))
        self._overall_progress = QProgressBar()
        self._overall_progress.setRange(0, 100)
        overall_pb_row.addWidget(self._overall_progress)
        progress_layout.addLayout(overall_pb_row)

        self._progress_group.setVisible(False)
        layout.addWidget(self._progress_group)

        # ── 결과 테이블 ──
        self._result_table = QTableWidget(0, 3)
        self._result_table.setHorizontalHeaderLabels(
            [tr("File"), tr("Status"), tr("Output Path")]
        )
        hdr = self._result_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._result_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._result_table.setVisible(False)
        layout.addWidget(self._result_table)

        # ── 버튼 ──
        btn_row = QHBoxLayout()
        self._start_btn = QPushButton(tr("Start Batch TTS"))
        self._start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(self._start_btn)

        self._cancel_btn = QPushButton(tr("Cancel"))
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self._cancel_btn)
        layout.addLayout(btn_row)

        # Preferences 기반 기본 엔진 적용 후 음성 로드
        default_provider = SettingsManager().get_tts_default_provider()
        idx = self._engine_combo.findData(default_provider)
        if idx < 0:
            idx = self._engine_combo.findData(_EDGE_PROVIDER_ID)
        if idx >= 0:
            self._engine_combo.setCurrentIndex(idx)
        elif self._engine_combo.count() > 0:
            self._engine_combo.setCurrentIndex(0)
        self._on_engine_changed(self._engine_combo.currentIndex())

    # ------------------------------------------------------------------ Slots

    def _populate_engine_options(self) -> None:
        self._engine_combo.clear()
        for provider in get_all_providers().values():
            self._engine_combo.addItem(provider.display_name, provider.provider_id)

    def _on_engine_changed(self, _index: int) -> None:
        engine = self._engine_combo.currentData()
        self._voice_combo.clear()

        provider = get_provider(engine)
        if provider is None:
            self._provider_available = False
            self._voice_state_label.setText(tr("Selected provider is unavailable."))
            self._start_btn.setEnabled(False)
            return

        self._provider_available = True
        for label, voice_id in provider.list_voices(None):
            self._voice_combo.addItem(label, voice_id)
        if self._voice_combo.count() == 0:
            self._voice_state_label.setText(tr("No voice available for selected provider."))
            self._start_btn.setEnabled(False)
            return

        self._voice_combo.setCurrentIndex(0)
        self._voice_state_label.setText("")
        self._start_btn.setEnabled(True)

    def _on_add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("Select Text Files"), "", "Text files (*.txt)"
        )
        for p in paths:
            if not any(
                self._file_list.item(i).text() == p
                for i in range(self._file_list.count())
            ):
                self._file_list.addItem(p)

    def _on_remove_files(self) -> None:
        for item in self._file_list.selectedItems():
            self._file_list.takeItem(self._file_list.row(item))

    def _on_browse_output(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(
            self, tr("Select Output Directory"), ""
        )
        if dir_path:
            self._output_edit.setText(dir_path)

    def _on_start(self) -> None:
        # 유효성 검사
        if self._file_list.count() == 0:
            QMessageBox.warning(
                self, tr("No Input Files"), tr("Add at least one .txt file.")
            )
            return

        output_dir_text = self._output_edit.text().strip()
        if not output_dir_text:
            QMessageBox.warning(
                self, tr("No Output Folder"), tr("Select an output folder.")
            )
            return

        output_dir = Path(output_dir_text)
        engine = self._engine_combo.currentData()

        if not self._provider_available or get_provider(engine) is None:
            QMessageBox.warning(
                self,
                tr("TTS Generation Failed"),
                tr("Failed to generate speech") + f":\n\n{tr('Selected provider is unavailable.')}",
            )
            return

        provider = get_provider(engine)
        requires_api_key = callable(getattr(provider, "requires_api_key", None)) and bool(provider.requires_api_key())
        if requires_api_key:
            api_key = SettingsManager().get_elevenlabs_api_key()
            if not api_key:
                QMessageBox.warning(
                    self,
                    tr("API Key Required"),
                    tr("Selected provider requires an API key.") + "\n\n"
                    + tr("Set it in Edit > Preferences > API Keys."),
                )
                return

        # 작업 목록 생성
        jobs: list[BatchTtsJob] = []
        for i in range(self._file_list.count()):
            txt_path = Path(self._file_list.item(i).text())
            jobs.append(BatchTtsJob(txt_path=txt_path, output_dir=output_dir))

        # 결과 테이블 초기화
        self._result_table.setRowCount(len(jobs))
        for i, job in enumerate(jobs):
            self._result_table.setItem(i, 0, QTableWidgetItem(job.txt_path.name))
            self._result_table.setItem(i, 1, QTableWidgetItem(tr("Pending")))
            self._result_table.setItem(i, 2, QTableWidgetItem(""))
        self._result_table.setVisible(True)

        # 설정 수집
        voice_id: str = self._voice_combo.currentData()
        if not voice_id:
            QMessageBox.warning(
                self,
                tr("TTS Generation Failed"),
                tr("Failed to generate speech") + f":\n\n{tr('No voice available for selected provider.')}",
            )
            return
        speed = self._speed_slider.value() / 10.0
        strategy: SplitStrategy = self._strategy_combo.currentData()

        # UI 전환
        self._start_btn.setEnabled(False)
        self._progress_group.setVisible(True)
        self._overall_progress.setValue(0)
        self._file_progress.setValue(0)

        # 워커 시작
        self._thread = QThread(self)
        self._worker = BatchTtsWorker(
            jobs=jobs,
            voice=voice_id,
            speed=speed,
            engine=engine,
            strategy=strategy,
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.job_started.connect(self._on_job_started)
        self._worker.job_finished.connect(self._on_job_finished)
        self._worker.progress.connect(self._on_progress)
        self._worker.all_finished.connect(self._on_all_finished)
        self._worker.all_finished.connect(self._cleanup_thread)
        self._worker.error.connect(self._on_worker_error)
        self._worker.error.connect(self._cleanup_thread)

        self._total_jobs = len(jobs)
        self._thread.start()

    def _on_job_started(self, idx: int) -> None:
        if idx < self._result_table.rowCount():
            self._result_table.setItem(idx, 1, QTableWidgetItem(tr("Exporting...")))
            name = self._result_table.item(idx, 0).text() if self._result_table.item(idx, 0) else ""
            self._current_file_label.setText(f"{idx + 1}/{self._total_jobs}: {name}")
        self._file_progress.setValue(0)

    def _on_job_finished(self, idx: int, result: object) -> None:
        result: BatchTtsResult = result  # type annotation hint
        if idx < self._result_table.rowCount():
            if result.success:
                self._result_table.setItem(idx, 1, QTableWidgetItem(tr("Completed")))
                self._result_table.setItem(
                    idx, 2, QTableWidgetItem(result.audio_path or "")
                )
            else:
                item = QTableWidgetItem(tr("Failed"))
                item.setToolTip(result.error or "")
                self._result_table.setItem(idx, 1, item)
        overall_pct = int((idx + 1) / self._total_jobs * 100)
        self._overall_progress.setValue(min(100, overall_pct))

    def _on_progress(
        self, job_idx: int, job_total: int, seg_cur: int, seg_total: int
    ) -> None:
        if seg_total > 0:
            self._file_progress.setValue(int(seg_cur / seg_total * 100))

    def _on_all_finished(self, results: list) -> None:
        self._results = results
        self._overall_progress.setValue(100)
        self._file_progress.setValue(100)
        self._current_file_label.setText(tr("Batch TTS complete"))
        self._start_btn.setEnabled(True)
        self._cancel_btn.setText(tr("Close"))

        succeeded = sum(1 for r in results if r.success)
        failed = len(results) - succeeded
        if failed == 0:
            QMessageBox.information(
                self,
                tr("Batch TTS complete"),
                tr("All %d files converted successfully.") % succeeded,
            )
        else:
            QMessageBox.warning(
                self,
                tr("Batch TTS complete"),
                tr("%d succeeded, %d failed.") % (succeeded, failed),
            )

    def _on_worker_error(self, msg: str) -> None:
        self._current_file_label.setText(msg)
        QMessageBox.critical(self, tr("Batch TTS Error"), to_user_message(msg))
        self._start_btn.setEnabled(True)

    def _on_cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
        self._cleanup_thread()
        self.reject()

    def _cleanup_thread(self) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(5000)
        self._thread = None
        self._worker = None

    def closeEvent(self, event) -> None:
        self._on_cancel()
        super().closeEvent(event)
