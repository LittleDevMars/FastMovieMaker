"""Video export progress dialog with TTS audio integration."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from src.models.subtitle import SubtitleTrack
from src.utils.i18n import tr
from src.workers.export_worker import ExportWorker
from src.utils.hw_accel import get_hw_info


class ExportDialog(QDialog):
    """Dialog that shows export options and progress."""

    def __init__(
        self,
        video_path: Path,
        track: SubtitleTrack,
        parent=None,
        video_has_audio: bool = False,
        overlay_path: Path | None = None,
        image_overlays: list | None = None,
        video_tracks: list | None = None,
        text_overlays: list | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(tr("Export Video"))
        self.setMinimumWidth(450)
        self.setModal(True)

        self._video_path = video_path
        self._track = track
        self._video_has_audio = video_has_audio
        self._overlay_path = overlay_path
        self._image_overlays = image_overlays
        self._video_tracks = video_tracks
        self._text_overlays = text_overlays
        self._thread: QThread | None = None
        self._worker: ExportWorker | None = None
        self._temp_audio_path: Path | None = None

        # Check if track has TTS audio segments
        self._has_tts = any(seg.audio_file for seg in track.segments)

        self._build_ui()
        self._show_options()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # --- Audio options group ---
        self._options_group = QGroupBox(tr("Audio Options"))
        options_layout = QVBoxLayout(self._options_group)

        # TTS include checkbox
        self._tts_checkbox = QCheckBox(tr("Include TTS audio"))
        self._tts_checkbox.setChecked(self._has_tts)
        self._tts_checkbox.setEnabled(self._has_tts)
        self._tts_checkbox.toggled.connect(self._on_tts_toggled)
        options_layout.addWidget(self._tts_checkbox)

        if not self._has_tts:
            hint = QLabel(tr("(No TTS audio in this track)"))
            hint.setStyleSheet("color: gray; font-size: 11px;")
            options_layout.addWidget(hint)

        # Background volume slider
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

        # TTS volume slider
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

        # Segment volume checkbox
        self._seg_vol_checkbox = QCheckBox(tr("Apply per-segment volumes"))
        self._seg_vol_checkbox.setChecked(True)
        self._seg_vol_checkbox.setEnabled(self._has_tts)
        options_layout.addWidget(self._seg_vol_checkbox)

        layout.addWidget(self._options_group)

        # --- Video options group ---
        self._video_group = QGroupBox(tr("Video Options"))
        video_layout = QVBoxLayout(self._video_group)

        # Codec & Preset row
        row1 = QHBoxLayout()
        row1.addWidget(QLabel(tr("Codec:")))
        self._codec_combo = QComboBox()
        self._codec_combo.addItems(["H.264", "HEVC"])
        row1.addWidget(self._codec_combo)

        row1.addWidget(QLabel(tr("Preset:")))
        self._preset_combo = QComboBox()
        # Map user-friendly names to ffmpeg presets
        # (Display Name, ffmpeg value)
        self._presets = [
            (tr("Fast (Lower Quality)"), "fast"),
            (tr("Balanced"), "medium"),
            (tr("High Quality (Slow)"), "slow"),
        ]
        for name, _ in self._presets:
            self._preset_combo.addItem(name)
        self._preset_combo.setCurrentIndex(1)  # Default to Balanced
        row1.addWidget(self._preset_combo)
        video_layout.addLayout(row1)

        # Resolution & CRF row
        row2 = QHBoxLayout()
        row2.addWidget(QLabel(tr("Resolution:")))
        self._res_combo = QComboBox()
        self._res_combo.addItem(tr("Original"), (0, 0))
        self._res_combo.addItem("1080p (1920x1080)", (1920, 1080))
        self._res_combo.addItem("720p (1280x720)", (1280, 720))
        row2.addWidget(self._res_combo)

        row2.addWidget(QLabel(tr("Quality (CRF):")))
        self._crf_slider = QSlider(Qt.Orientation.Horizontal)
        self._crf_slider.setRange(0, 51)
        self._crf_slider.setValue(23)
        self._crf_slider.setInvertedAppearance(True)  # Lower is better
        row2.addWidget(self._crf_slider)

        self._crf_label = QLabel("23")
        self._crf_label.setMinimumWidth(30)
        row2.addWidget(self._crf_label)
        self._crf_slider.valueChanged.connect(lambda v: self._crf_label.setText(str(v)))

        video_layout.addLayout(row2)

        # Helper text for CRF
        crf_hint = QLabel(tr("Lower CRF = Better Quality (Larger File)"))
        crf_hint.setStyleSheet("color: gray; font-size: 11px;")
        crf_hint.setAlignment(Qt.AlignmentFlag.AlignRight)
        video_layout.addWidget(crf_hint)

        # GPU Acceleration
        self._gpu_checkbox = QCheckBox(tr("Use Hardware Acceleration (GPU)"))
        hw_info = get_hw_info()
        has_hw = hw_info.get("recommended") is not None and hw_info.get("recommended") != "software"
        self._gpu_checkbox.setChecked(has_hw)
        if has_hw:
            self._gpu_checkbox.setToolTip(tr("Hardware acceleration is available on this system."))
        else:
            self._gpu_checkbox.setEnabled(False)
            self._gpu_checkbox.setToolTip(tr("No hardware encoder detected."))
        
        video_layout.addWidget(self._gpu_checkbox)

        layout.addWidget(self._video_group)

        # --- Progress section (hidden initially) ---
        self._progress_section = QGroupBox(tr("Export Progress"))
        progress_layout = QVBoxLayout(self._progress_section)

        self._status_label = QLabel(tr("Preparing export..."))
        progress_layout.addWidget(self._status_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        progress_layout.addWidget(self._progress_bar)

        self._progress_section.setVisible(False)
        layout.addWidget(self._progress_section)

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        self._export_btn = QPushButton(tr("Export..."))
        self._export_btn.clicked.connect(self._ask_output_and_start)
        btn_layout.addWidget(self._export_btn)

        self._cancel_btn = QPushButton(tr("Cancel"))
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self._cancel_btn)

        layout.addLayout(btn_layout)

    def _show_options(self) -> None:
        """Show the options UI phase."""
        self._options_group.setVisible(True)
        self._video_group.setVisible(True)
        self._options_group.setEnabled(True)
        self._video_group.setEnabled(True)
        self._progress_section.setVisible(False)
        self._export_btn.setVisible(True)

    def _on_tts_toggled(self, checked: bool) -> None:
        self._bg_slider.setEnabled(checked)
        self._tts_slider.setEnabled(checked)
        self._seg_vol_checkbox.setEnabled(checked)

    # ------------------------------------------------------------------ Export

    def _ask_output_and_start(self) -> None:
        default_name = self._video_path.stem + "_subtitled.mp4"
        default_dir = str(self._video_path.parent / default_name)
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Save Video As"), default_dir,
            "MP4 Files (*.mp4);;All Files (*)",
        )
        if not path:
            return

        self._output_path = Path(path)

        # Transition to progress phase
        self._options_group.setEnabled(False)
        self._video_group.setEnabled(False)
        self._export_btn.setVisible(False)
        self._progress_section.setVisible(True)

        self._start_export()

    def _start_export(self) -> None:
        audio_path = None

        if self._tts_checkbox.isChecked() and self._has_tts:
            # Prepare TTS audio
            self._status_label.setText(tr("Preparing TTS audio..."))
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()

            try:
                audio_path = self._prepare_tts_audio()
            except Exception as e:
                QMessageBox.critical(
                    self, tr("Audio Preparation Error"),
                    f"{tr('Failed to prepare TTS audio')}:\n{e}\n\n"
                    f"{tr('Exporting without TTS audio.')}"
                )
                audio_path = None

        self._status_label.setText(tr("Exporting video with subtitles..."))

        # Gather video options
        codec = self._codec_combo.currentText().lower().replace(".", "")
        preset = self._presets[self._preset_combo.currentIndex()][1]
        crf = self._crf_slider.value()
        w, h = self._res_combo.currentData()

        self._thread = QThread()
        self._worker = ExportWorker(
            self._video_path,
            self._track,
            self._output_path,
            audio_path=audio_path,
            overlay_path=self._overlay_path,
            image_overlays=self._image_overlays,
            video_tracks=self._video_tracks,
            text_overlays=self._text_overlays,
            codec=codec,
            preset=preset,
            crf=crf,
            scale_width=w,
            scale_height=h,
            use_gpu=self._gpu_checkbox.isChecked(),
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._cleanup_thread)
        self._worker.error.connect(self._cleanup_thread)

        self._thread.start()

    def _prepare_tts_audio(self) -> Path | None:
        """Regenerate TTS audio with current settings and return the path."""
        from src.services.audio_regenerator import AudioRegenerator

        bg_volume = self._bg_slider.value() / 100.0
        tts_volume = self._tts_slider.value() / 100.0
        apply_seg_vol = self._seg_vol_checkbox.isChecked()

        # Create temp output for the mixed audio
        temp_dir = Path(tempfile.mkdtemp(prefix="export_audio_"))
        output_audio = temp_dir / f"export_tts_{uuid.uuid4().hex[:8]}.mp3"

        # Determine background audio source
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

    def _on_progress(self, total_sec: float, current_sec: float) -> None:
        if total_sec > 0:
            pct = min(100, int(current_sec / total_sec * 100))
            self._progress_bar.setValue(pct)
            self._status_label.setText(
                f"Exporting: {current_sec:.1f}s / {total_sec:.1f}s ({pct}%)"
            )

    def _on_finished(self, output_path: str) -> None:
        self._progress_bar.setValue(100)
        self._status_label.setText(tr("Export complete!"))
        self._cancel_btn.setText(tr("Close"))
        self._cleanup_temp_audio()
        QMessageBox.information(self, tr("Export Complete"), f"{tr('Video exported to')}:\n{output_path}")
        self.accept()

    def _on_error(self, message: str) -> None:
        self._status_label.setText(f"{tr('Error')}: {message}")
        self._cancel_btn.setText(tr("Close"))
        self._cleanup_temp_audio()
        QMessageBox.critical(self, tr("Export Error"), message)

    def _on_cancel(self) -> None:
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
        """Remove temporary audio file and its parent directory."""
        if self._temp_audio_path:
            parent = self._temp_audio_path.parent
            if parent.name.startswith("export_audio_"):
                shutil.rmtree(parent, ignore_errors=True)
            elif self._temp_audio_path.exists():
                self._temp_audio_path.unlink(missing_ok=True)
            self._temp_audio_path = None

    def closeEvent(self, event) -> None:
        self._on_cancel()
        super().closeEvent(event)
