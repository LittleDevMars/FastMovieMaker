"""Batch video export dialog - export to multiple resolutions/formats."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.models.export_preset import (
    BatchExportJob,
    DEFAULT_PRESETS,
    ExportPreset,
)
from src.models.subtitle import SubtitleTrack
from src.utils.i18n import tr
from src.workers.batch_export_worker import BatchExportWorker


class BatchExportDialog(QDialog):
    """Dialog for batch exporting video to multiple presets."""

    def __init__(
        self,
        video_path: Path,
        track: SubtitleTrack,
        parent=None,
        video_has_audio: bool = False,
        overlay_path: Path | None = None,
        image_overlays: list | None = None,
        text_overlays: list | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(tr("Batch Export"))
        self.setMinimumSize(650, 550)
        self.setModal(True)

        self._video_path = video_path
        self._track = track
        self._video_has_audio = video_has_audio
        self._overlay_path = overlay_path
        self._image_overlays = image_overlays
        self._text_overlays = text_overlays
        self._thread: QThread | None = None
        self._worker: BatchExportWorker | None = None
        self._temp_audio_path: Path | None = None
        self._jobs: list[BatchExportJob] = []
        self._output_dir: Path | None = None

        self._has_tts = any(seg.audio_file for seg in track.segments)

        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # --- Preset selection group ---
        preset_group = QGroupBox(tr("Export Presets"))
        preset_layout = QVBoxLayout(preset_group)

        add_row = QHBoxLayout()
        self._preset_combo = QComboBox()
        for p in DEFAULT_PRESETS:
            self._preset_combo.addItem(p.name, p)
        add_row.addWidget(self._preset_combo, 1)

        self._add_btn = QPushButton(tr("Add"))
        self._add_btn.clicked.connect(self._on_add_preset)
        add_row.addWidget(self._add_btn)
        preset_layout.addLayout(add_row)

        # Preset table
        self._preset_table = QTableWidget(0, 4)
        self._preset_table.setHorizontalHeaderLabels(
            [tr("Preset"), tr("Resolution"), tr("Format"), tr("Status")]
        )
        header = self._preset_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._preset_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._preset_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._preset_table.setMinimumHeight(150)
        preset_layout.addWidget(self._preset_table)

        remove_row = QHBoxLayout()
        remove_row.addStretch()
        self._remove_btn = QPushButton(tr("Remove Selected"))
        self._remove_btn.clicked.connect(self._on_remove_preset)
        remove_row.addWidget(self._remove_btn)
        preset_layout.addLayout(remove_row)

        layout.addWidget(preset_group)

        # --- Audio options group ---
        self._options_group = QGroupBox(tr("Audio Options"))
        options_layout = QVBoxLayout(self._options_group)

        self._tts_checkbox = QCheckBox(tr("Include TTS audio"))
        self._tts_checkbox.setChecked(self._has_tts)
        self._tts_checkbox.setEnabled(self._has_tts)
        self._tts_checkbox.toggled.connect(self._on_tts_toggled)
        options_layout.addWidget(self._tts_checkbox)

        if not self._has_tts:
            hint = QLabel(tr("(No TTS audio in this track)"))
            hint.setStyleSheet("color: gray; font-size: 11px;")
            options_layout.addWidget(hint)

        bg_row = QHBoxLayout()
        bg_row.addWidget(QLabel(tr("Background volume:")))
        self._bg_slider = QSlider(Qt.Orientation.Horizontal)
        self._bg_slider.setRange(0, 100)
        self._bg_slider.setValue(50)
        self._bg_slider.setEnabled(self._has_tts)
        bg_row.addWidget(self._bg_slider)
        self._bg_label = QLabel("50%")
        self._bg_label.setMinimumWidth(40)
        bg_row.addWidget(self._bg_label)
        self._bg_slider.valueChanged.connect(lambda v: self._bg_label.setText(f"{v}%"))
        options_layout.addLayout(bg_row)

        tts_row = QHBoxLayout()
        tts_row.addWidget(QLabel(tr("TTS volume:")))
        self._tts_slider = QSlider(Qt.Orientation.Horizontal)
        self._tts_slider.setRange(0, 200)
        self._tts_slider.setValue(100)
        self._tts_slider.setEnabled(self._has_tts)
        tts_row.addWidget(self._tts_slider)
        self._tts_label = QLabel("100%")
        self._tts_label.setMinimumWidth(40)
        tts_row.addWidget(self._tts_label)
        self._tts_slider.valueChanged.connect(lambda v: self._tts_label.setText(f"{v}%"))
        options_layout.addLayout(tts_row)

        self._seg_vol_checkbox = QCheckBox(tr("Apply per-segment volumes"))
        self._seg_vol_checkbox.setChecked(True)
        self._seg_vol_checkbox.setEnabled(self._has_tts)
        options_layout.addWidget(self._seg_vol_checkbox)

        layout.addWidget(self._options_group)

        # --- Progress section (hidden initially) ---
        self._progress_group = QGroupBox(tr("Batch Progress"))
        progress_layout = QVBoxLayout(self._progress_group)

        self._current_job_label = QLabel(tr("Preparing..."))
        progress_layout.addWidget(self._current_job_label)

        job_row = QHBoxLayout()
        job_row.addWidget(QLabel(tr("Current:")))
        self._job_progress = QProgressBar()
        self._job_progress.setRange(0, 100)
        job_row.addWidget(self._job_progress)
        progress_layout.addLayout(job_row)

        overall_row = QHBoxLayout()
        overall_row.addWidget(QLabel(tr("Overall:")))
        self._overall_progress = QProgressBar()
        self._overall_progress.setRange(0, 100)
        overall_row.addWidget(self._overall_progress)
        progress_layout.addLayout(overall_row)

        self._progress_group.setVisible(False)
        layout.addWidget(self._progress_group)

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        self._export_btn = QPushButton(tr("Export All..."))
        self._export_btn.clicked.connect(self._ask_output_dir_and_start)
        btn_layout.addWidget(self._export_btn)

        self._cancel_btn = QPushButton(tr("Cancel"))
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self._cancel_btn)

        layout.addLayout(btn_layout)

        # Pre-populate with 1080p and 720p
        self._add_preset_to_table(DEFAULT_PRESETS[1])
        self._add_preset_to_table(DEFAULT_PRESETS[2])

    # ------------------------------------------------------------------ Presets

    def _on_add_preset(self) -> None:
        preset = self._preset_combo.currentData()
        if preset:
            self._add_preset_to_table(preset)

    def _add_preset_to_table(self, preset: ExportPreset) -> None:
        row = self._preset_table.rowCount()
        self._preset_table.insertRow(row)

        name_item = QTableWidgetItem(preset.name)
        name_item.setData(Qt.ItemDataRole.UserRole, preset)
        self._preset_table.setItem(row, 0, name_item)
        self._preset_table.setItem(row, 1, QTableWidgetItem(preset.resolution_label))
        self._preset_table.setItem(
            row, 2, QTableWidgetItem(f".{preset.container} / {preset.codec}")
        )
        self._preset_table.setItem(row, 3, QTableWidgetItem(tr("Pending")))

    def _on_remove_preset(self) -> None:
        rows = self._preset_table.selectionModel().selectedRows()
        for index in sorted(rows, reverse=True):
            self._preset_table.removeRow(index.row())

    def _on_tts_toggled(self, checked: bool) -> None:
        self._bg_slider.setEnabled(checked)
        self._tts_slider.setEnabled(checked)
        self._seg_vol_checkbox.setEnabled(checked)

    # ------------------------------------------------------------------ Export

    def _ask_output_dir_and_start(self) -> None:
        if self._preset_table.rowCount() == 0:
            QMessageBox.warning(self, tr("No Presets"), tr("Add at least one export preset."))
            return

        dir_path = QFileDialog.getExistingDirectory(
            self, tr("Select Output Directory"), str(self._video_path.parent)
        )
        if not dir_path:
            return

        self._output_dir = Path(dir_path)

        # Build job list
        self._jobs = []
        base_name = self._video_path.stem
        for row in range(self._preset_table.rowCount()):
            preset = self._preset_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            output_name = f"{base_name}{preset.suffix}{preset.file_extension}"
            output_path = str(self._output_dir / output_name)
            self._jobs.append(BatchExportJob(preset=preset, output_path=output_path))

        # Check for overwrites
        existing = [j for j in self._jobs if Path(j.output_path).exists()]
        if existing:
            names = "\n".join(Path(j.output_path).name for j in existing)
            reply = QMessageBox.question(
                self,
                tr("Overwrite?"),
                f"{tr('These files already exist')}:\n{names}\n\n{tr('Overwrite?')}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Transition to progress phase
        self._options_group.setEnabled(False)
        self._export_btn.setVisible(False)
        self._remove_btn.setEnabled(False)
        self._add_btn.setEnabled(False)
        self._progress_group.setVisible(True)

        self._start_batch_export()

    def _start_batch_export(self) -> None:
        audio_path = None

        # Prepare TTS audio ONCE for all jobs
        if self._tts_checkbox.isChecked() and self._has_tts:
            self._current_job_label.setText(tr("Preparing TTS audio..."))
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            try:
                audio_path = self._prepare_tts_audio()
            except Exception as e:
                QMessageBox.critical(
                    self,
                    tr("Audio Preparation Error"),
                    f"{tr('Failed to prepare TTS audio')}:\n{e}\n\n"
                    f"{tr('Exporting without TTS audio.')}",
                )
                audio_path = None

        self._current_job_label.setText(tr("Starting batch export..."))

        self._thread = QThread()
        self._worker = BatchExportWorker(
            self._video_path,
            self._track,
            self._jobs,
            audio_path=audio_path,
            overlay_path=self._overlay_path,
            image_overlays=self._image_overlays,
            text_overlays=self._text_overlays,
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.job_started.connect(self._on_job_started)
        self._worker.job_progress.connect(self._on_job_progress)
        self._worker.job_finished.connect(self._on_job_finished)
        self._worker.job_error.connect(self._on_job_error)
        self._worker.all_finished.connect(self._on_all_finished)
        self._worker.all_finished.connect(self._cleanup_thread)

        self._thread.start()

    def _prepare_tts_audio(self) -> Path | None:
        from src.services.audio_regenerator import AudioRegenerator

        bg_volume = self._bg_slider.value() / 100.0
        tts_volume = self._tts_slider.value() / 100.0
        apply_seg_vol = self._seg_vol_checkbox.isChecked()

        temp_dir = Path(tempfile.mkdtemp(prefix="batch_export_audio_"))
        output_audio = temp_dir / f"batch_tts_{uuid.uuid4().hex[:8]}.mp3"

        video_audio_path = None
        if self._video_has_audio:
            video_audio_path = self._video_path

        regenerated_path, _ = AudioRegenerator.regenerate_track_audio(
            track=self._track,
            output_path=output_audio,
            video_audio_path=video_audio_path,
            bg_volume=bg_volume,
            tts_volume=tts_volume,
            apply_segment_volumes=apply_seg_vol,
        )

        self._temp_audio_path = regenerated_path
        return regenerated_path

    # ------------------------------------------------------------------ Callbacks

    def _on_job_started(self, index: int, preset_name: str) -> None:
        self._current_job_label.setText(
            f"Exporting {index + 1}/{len(self._jobs)}: {preset_name}"
        )
        self._job_progress.setValue(0)
        self._preset_table.setItem(index, 3, QTableWidgetItem(tr("Exporting...")))
        self._preset_table.scrollToItem(self._preset_table.item(index, 0))

    def _on_job_progress(self, index: int, total_sec: float, current_sec: float) -> None:
        if total_sec > 0:
            pct = min(100, int(current_sec / total_sec * 100))
            self._job_progress.setValue(pct)
            completed_before = index
            overall_pct = int(
                (completed_before + pct / 100.0) / len(self._jobs) * 100
            )
            self._overall_progress.setValue(min(100, overall_pct))

    def _on_job_finished(self, index: int, output_path: str) -> None:
        self._preset_table.setItem(index, 3, QTableWidgetItem(tr("Completed")))

    def _on_job_error(self, index: int, message: str) -> None:
        item = QTableWidgetItem(tr("Failed"))
        item.setToolTip(message)
        self._preset_table.setItem(index, 3, item)

    def _on_all_finished(self, total: int, succeeded: int, failed: int) -> None:
        self._overall_progress.setValue(100)
        self._job_progress.setValue(100)

        skipped = total - succeeded - failed
        summary_parts = [f"{succeeded} succeeded"]
        if failed > 0:
            summary_parts.append(f"{failed} failed")
        if skipped > 0:
            summary_parts.append(f"{skipped} skipped")
        summary = ", ".join(summary_parts)

        self._current_job_label.setText(f"{tr('Batch export complete')}: {summary}")
        self._cancel_btn.setText(tr("Close"))
        self._cleanup_temp_audio()

        if failed == 0:
            QMessageBox.information(
                self,
                tr("Batch Export Complete"),
                f"{tr('All exports completed successfully')} ({succeeded}).\n\n"
                f"{tr('Output directory')}:\n{self._output_dir}",
            )
        else:
            error_details = []
            for job in self._jobs:
                if job.status == "failed":
                    error_details.append(
                        f"  {job.preset.name}: {job.error_message[:100]}"
                    )
            QMessageBox.warning(
                self,
                tr("Batch Export Complete"),
                f"{summary}\n\n{tr('Failed exports')}:\n" + "\n".join(error_details),
            )

        self.accept()

    def _on_cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
        self._cleanup_thread()
        self._cleanup_temp_audio()
        self.reject()

    def _cleanup_thread(self) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(5000)
        self._thread = None
        self._worker = None

    def _cleanup_temp_audio(self) -> None:
        if self._temp_audio_path:
            parent = self._temp_audio_path.parent
            if parent.name.startswith("batch_export_audio_"):
                shutil.rmtree(parent, ignore_errors=True)
            elif self._temp_audio_path.exists():
                self._temp_audio_path.unlink(missing_ok=True)
            self._temp_audio_path = None

    def closeEvent(self, event) -> None:
        self._on_cancel()
        super().closeEvent(event)
