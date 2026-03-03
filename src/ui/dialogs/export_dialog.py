"""Video export progress dialog with TTS audio integration."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from src.models.export_preset import DEFAULT_PRESETS, ExportPreset
from src.models.subtitle import SubtitleTrack
from src.services.export_preset_manager import ExportPresetManager
from src.utils.i18n import tr
from src.workers.export_worker import ExportWorker
from src.utils.hw_accel import get_hw_info


class _ThumbSignals(QObject):
    """QRunnable은 시그널 미지원 → 별도 QObject로 분리."""
    thumb_ready = Signal(str)  # 임시 JPEG 경로


class _ThumbWorker(QRunnable):
    """별도 스레드에서 FFmpeg로 첫 프레임을 추출한다."""

    def __init__(self, video_path: Path) -> None:
        super().__init__()
        self.signals = _ThumbSignals()
        self._video_path = video_path

    def run(self) -> None:
        try:
            from src.utils.config import find_ffmpeg
            ffmpeg = find_ffmpeg()
            if not ffmpeg:
                return
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            tmp.close()
            subprocess.run(
                [ffmpeg, "-ss", "0", "-i", str(self._video_path),
                 "-vframes", "1", "-f", "image2", "-y", tmp.name],
                capture_output=True, timeout=15,
            )
            self.signals.thumb_ready.emit(tmp.name)
        except Exception:
            pass


class ExportDialog(QDialog):
    """Dialog that shows export options and progress."""

    def __init__(
        self,
        video_path: Path,
        track: SubtitleTrack,
        parent=None,
        video_has_audio: bool = False,
        overlay_path: Path | None = None,
        overlay_template=None,
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
        self._overlay_template = overlay_template
        self._image_overlays = image_overlays
        self._video_tracks = video_tracks
        self._text_overlays = text_overlays
        self._thread: QThread | None = None
        self._worker: ExportWorker | None = None
        self._temp_audio_path: Path | None = None
        self._thumb_tmp_path: str | None = None
        self._preset_manager = ExportPresetManager()

        # Check if track has TTS audio segments
        self._has_tts = any(seg.audio_file for seg in track.segments)

        # Probe video metadata (synchronous, fast)
        self._video_info = None
        if video_path and video_path.exists():
            try:
                from src.services.video_probe import probe_video
                self._video_info = probe_video(video_path)
            except Exception:
                pass

        self._build_ui()
        self._show_options()

        # 썸네일 비동기 추출 시작
        if video_path and video_path.exists():
            worker = _ThumbWorker(video_path)
            worker.signals.thumb_ready.connect(self._on_thumbnail_ready)
            QThreadPool.globalInstance().start(worker)

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # --- Source Preview panel ---
        layout.addWidget(self._build_preview_panel())

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

        # Mix with original audio checkbox
        self._mix_audio_checkbox = QCheckBox(tr("Mix with original audio"))
        self._mix_audio_checkbox.setChecked(self._video_has_audio)
        self._mix_audio_checkbox.setEnabled(self._has_tts and self._video_has_audio)
        self._mix_audio_checkbox.toggled.connect(self._on_mix_audio_toggled)
        options_layout.addWidget(self._mix_audio_checkbox)

        # Background volume slider
        bg_row = QHBoxLayout()
        bg_row.addWidget(QLabel(tr("Background volume:")))
        self._bg_slider = QSlider(Qt.Orientation.Horizontal)
        self._bg_slider.setRange(0, 100)
        self._bg_slider.setValue(50)
        self._bg_slider.setEnabled(self._has_tts and self._video_has_audio)
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

        # --- BGM Ducking group ---
        self._ducking_group = QGroupBox(tr("BGM Ducking"))
        ducking_layout = QVBoxLayout(self._ducking_group)

        self._ducking_checkbox = QCheckBox(tr("Enable Auto-Ducking"))
        self._ducking_checkbox.setChecked(False)
        self._ducking_checkbox.setEnabled(self._has_tts and self._video_has_audio)
        self._ducking_checkbox.toggled.connect(self._on_ducking_toggled)
        ducking_layout.addWidget(self._ducking_checkbox)

        duck_row = QHBoxLayout()
        duck_row.addWidget(QLabel(tr("Duck Level:")))
        self._duck_slider = QSlider(Qt.Orientation.Horizontal)
        self._duck_slider.setRange(0, 100)
        self._duck_slider.setValue(30)
        self._duck_slider.setEnabled(False)
        duck_row.addWidget(self._duck_slider)
        self._duck_label = QLabel("30%")
        self._duck_label.setMinimumWidth(40)
        duck_row.addWidget(self._duck_label)
        self._duck_slider.valueChanged.connect(lambda v: self._duck_label.setText(f"{v}%"))
        ducking_layout.addLayout(duck_row)

        layout.addWidget(self._ducking_group)

        # --- Video options group ---
        self._video_group = QGroupBox(tr("Video Options"))
        video_layout = QVBoxLayout(self._video_group)

        # ── 프리셋 툴바 행 ──
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel(tr("Export Preset:")))
        self._export_preset_combo = QComboBox()
        self._export_preset_combo.setMinimumWidth(180)
        self._populate_export_preset_combo()
        self._export_preset_combo.currentIndexChanged.connect(self._on_export_preset_selected)
        preset_row.addWidget(self._export_preset_combo)

        self._save_preset_btn = QPushButton(tr("Save Preset..."))
        self._save_preset_btn.clicked.connect(self._on_save_export_preset)
        preset_row.addWidget(self._save_preset_btn)

        self._delete_preset_btn = QPushButton(tr("Delete Preset"))
        self._delete_preset_btn.clicked.connect(self._on_delete_export_preset)
        preset_row.addWidget(self._delete_preset_btn)
        video_layout.addLayout(preset_row)

        # ── Audio Bitrate 행 ──
        ab_row = QHBoxLayout()
        ab_row.addWidget(QLabel(tr("Audio Bitrate:")))
        self._audio_bitrate_combo = QComboBox()
        for br in ["96k", "128k", "192k", "320k"]:
            self._audio_bitrate_combo.addItem(br, br)
        self._audio_bitrate_combo.setCurrentIndex(2)  # 192k 기본
        ab_row.addWidget(self._audio_bitrate_combo)
        ab_row.addStretch()
        video_layout.addLayout(ab_row)

        # ── Container 행 ──
        container_row = QHBoxLayout()
        container_row.addWidget(QLabel(tr("Container:")))
        self._container_combo = QComboBox()
        self._container_combo.addItem("MP4", "mp4")
        self._container_combo.addItem("MKV", "mkv")
        self._container_combo.addItem("WebM", "webm")
        self._container_combo.currentIndexChanged.connect(self._update_output_info)
        container_row.addWidget(self._container_combo)
        container_row.addStretch()
        video_layout.addLayout(container_row)

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
        self._res_combo.addItem("1080p 16:9 (1920×1080)", (1920, 1080))
        self._res_combo.addItem("720p 16:9 (1280×720)", (1280, 720))
        self._res_combo.addItem("1080p 9:16 (1080×1920)", (1080, 1920))
        self._res_combo.addItem("720p 9:16 (720×1280)", (720, 1280))
        self._res_combo.addItem("1:1 (1080×1080)", (1080, 1080))
        # Auto-select based on overlay template aspect ratio
        template_ar = self._overlay_template.aspect_ratio if self._overlay_template else None
        if template_ar == "9:16":
            self._res_combo.setCurrentIndex(3)  # 1080×1920
        elif template_ar == "16:9":
            self._res_combo.setCurrentIndex(1)  # 1920×1080
        elif template_ar == "1:1":
            self._res_combo.setCurrentIndex(5)  # 1080×1080
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

        # 코덱/해상도/CRF 변경 시 출력 정보 실시간 갱신
        self._codec_combo.currentIndexChanged.connect(self._update_output_info)
        self._res_combo.currentIndexChanged.connect(self._update_output_info)
        self._crf_slider.valueChanged.connect(self._update_output_info)
        self._update_output_info()

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

    def _build_preview_panel(self) -> QGroupBox:
        """소스 미리보기 패널 — 썸네일 + 소스/출력 정보."""
        group = QGroupBox(tr("Source Preview"))
        h = QHBoxLayout(group)

        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(200, 112)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setStyleSheet("background: #333; color: #888;")
        self._thumb_label.setText("...")
        h.addWidget(self._thumb_label)

        info_layout = QVBoxLayout()
        self._source_info_label = QLabel(f"{tr('Resolution')}: —")
        self._output_info_label = QLabel(f"{tr('Output')}: —")
        info_layout.addWidget(self._source_info_label)
        info_layout.addWidget(self._output_info_label)
        info_layout.addStretch()
        h.addLayout(info_layout)

        # 소스 정보 즉시 표시 (video_info가 있으면)
        self._update_source_info()
        return group

    def _update_source_info(self) -> None:
        """소스 해상도/길이 라벨을 갱신한다."""
        if not self._video_info:
            return
        vi = self._video_info
        if vi.width and vi.height:
            total_sec = vi.duration_ms / 1000
            m, s = divmod(int(total_sec), 60)
            h, m = divmod(m, 60)
            dur_str = f"{h:02d}:{m:02d}:{s:02d}"
            self._source_info_label.setText(
                f"Source: {vi.width}×{vi.height}  {dur_str}"
            )

    def _update_output_info(self) -> None:
        """출력 해상도/예상 크기/코덱 라벨을 갱신한다."""
        codec_txt = self._codec_combo.currentText()
        res_data = self._res_combo.currentData()
        crf = self._crf_slider.value()

        # 출력 해상도 결정
        if res_data and res_data != (0, 0):
            out_w, out_h = res_data
        elif self._video_info and self._video_info.width:
            out_w, out_h = self._video_info.width, self._video_info.height
        else:
            out_w, out_h = 1920, 1080

        # CRF 기반 비트레이트 추정 (H.264 1080p 기준 ~4000kbps, CRF 낮을수록 품질↑)
        base_kbps = 4000  # H.264 1080p at CRF 23
        if "HEVC" in codec_txt or "hevc" in codec_txt.lower():
            base_kbps = 2000
        # CRF 차이에 따른 보정 (±6 CRF ≈ ×2 bitrate)
        crf_factor = 2 ** ((23 - crf) / 6)
        # 해상도 비율 보정 (1080p = 2073600px 기준)
        pixel_ratio = (out_w * out_h) / 2_073_600
        bitrate_kbps = int(base_kbps * crf_factor * pixel_ratio)

        # 예상 파일 크기 (MB)
        if self._video_info and self._video_info.duration_ms:
            dur_sec = self._video_info.duration_ms / 1000
            size_mb = dur_sec * bitrate_kbps / 8 / 1024
            size_str = f"~{size_mb:.0f} MB"
        else:
            size_str = "—"

        self._output_info_label.setText(
            f"Output: {out_w}×{out_h}  {size_str}  {codec_txt}"
        )

    def _on_thumbnail_ready(self, path: str) -> None:
        """썸네일 추출 완료 콜백 — QPixmap을 라벨에 표시한다."""
        self._thumb_tmp_path = path
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                200, 112,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._thumb_label.setPixmap(scaled)
            self._thumb_label.setText("")

    def _show_options(self) -> None:
        """Show the options UI phase."""
        self._options_group.setVisible(True)
        self._ducking_group.setVisible(True)
        self._video_group.setVisible(True)
        self._options_group.setEnabled(True)
        self._ducking_group.setEnabled(True)
        self._video_group.setEnabled(True)
        self._progress_section.setVisible(False)
        self._export_btn.setVisible(True)

    def _on_tts_toggled(self, checked: bool) -> None:
        mix_ok = checked and self._video_has_audio
        self._mix_audio_checkbox.setEnabled(mix_ok)
        self._bg_slider.setEnabled(mix_ok and self._mix_audio_checkbox.isChecked())
        self._tts_slider.setEnabled(checked)
        self._seg_vol_checkbox.setEnabled(checked)
        self._ducking_checkbox.setEnabled(mix_ok)
        if not mix_ok:
            self._ducking_checkbox.setChecked(False)

    def _on_mix_audio_toggled(self, checked: bool) -> None:
        self._bg_slider.setEnabled(checked)
        self._ducking_checkbox.setEnabled(checked and self._has_tts)
        if not checked:
            self._ducking_checkbox.setChecked(False)

    def _on_ducking_toggled(self, checked: bool) -> None:
        self._duck_slider.setEnabled(checked)

    # ------------------------------------------------------------------ Export

    def _ask_output_and_start(self) -> None:
        container = self._container_combo.currentData() or "mp4"
        filter_map = {
            "mp4": "MP4 Files (*.mp4);;All Files (*)",
            "mkv": "MKV Files (*.mkv);;All Files (*)",
            "webm": "WebM Files (*.webm);;All Files (*)",
        }
        file_filter = filter_map.get(container, "Video Files (*.mp4 *.mkv *.webm);;All Files (*)")
        default_name = self._video_path.stem + f"_subtitled.{container}"
        default_dir = str(self._video_path.parent / default_name)
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Save Video As"), default_dir,
            file_filter,
        )
        if not path:
            return

        self._output_path = Path(path)

        # Transition to progress phase
        self._options_group.setEnabled(False)
        self._ducking_group.setEnabled(False)
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
            mix_with_original_audio=self._mix_audio_checkbox.isChecked(),
            video_volume=self._bg_slider.value() / 100.0,
            audio_volume=self._tts_slider.value() / 100.0,
            audio_bitrate=self._audio_bitrate_combo.currentText(),
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
        ducking_enabled = self._ducking_checkbox.isChecked()
        duck_level = self._duck_slider.value() / 100.0

        # Create temp output for the mixed audio
        temp_dir = Path(tempfile.mkdtemp(prefix="export_audio_"))
        output_audio = temp_dir / f"export_tts_{uuid.uuid4().hex[:8]}.mp3"

        # Determine background audio source
        # We let VideoExporter handle the mixing via mix_with_original_audio param
        video_audio_path = None

        regenerated_path, _ = AudioRegenerator.regenerate_track_audio(
            track=self._track,
            output_path=output_audio,
            video_audio_path=video_audio_path,
            bg_volume=bg_volume,
            tts_volume=tts_volume,
            apply_segment_volumes=apply_seg_vol,
            ducking_enabled=ducking_enabled,
            duck_level=duck_level,
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

    # ------------------------------------------------------------------ Preset helpers

    def _populate_export_preset_combo(self) -> None:
        """기본 프리셋 + 사용자 프리셋으로 콤보박스를 채운다."""
        self._export_preset_combo.blockSignals(True)
        self._export_preset_combo.clear()

        # 기본 프리셋
        for p in DEFAULT_PRESETS:
            self._export_preset_combo.addItem(p.name, ("default", p))

        # 사용자 프리셋이 있으면 구분선 + 사용자 프리셋 추가 (단일 QSettings 읽기)
        user_presets = self._preset_manager.get_all_presets()
        if user_presets:
            self._export_preset_combo.insertSeparator(len(DEFAULT_PRESETS))
            for name, preset in user_presets.items():
                self._export_preset_combo.addItem(name, ("user", preset))

        self._export_preset_combo.blockSignals(False)

    def _on_export_preset_selected(self, index: int) -> None:
        """프리셋 선택 시 UI 값을 프리셋 내용으로 세팅한다."""
        data = self._export_preset_combo.itemData(index)
        if not data:
            return
        _, preset = data

        # 여러 위젯의 signal을 일괄 차단하여 _update_output_info 중복 호출 방지
        for w in (self._codec_combo, self._res_combo, self._crf_slider,
                  self._preset_combo, self._audio_bitrate_combo, self._container_combo):
            w.blockSignals(True)

        # 코덱
        codec_map = {"h264": "H.264", "hevc": "HEVC"}
        codec_text = codec_map.get(preset.codec, "H.264")
        idx = self._codec_combo.findText(codec_text)
        if idx >= 0:
            self._codec_combo.setCurrentIndex(idx)

        # 해상도
        res_found = False
        for i in range(self._res_combo.count()):
            if self._res_combo.itemData(i) == (preset.width, preset.height):
                self._res_combo.setCurrentIndex(i)
                res_found = True
                break
        if not res_found:
            self._res_combo.setCurrentIndex(0)  # Original

        # CRF
        self._crf_slider.setValue(preset.crf)

        # Speed preset
        speed_map = {"fast": 0, "medium": 1, "slow": 2}
        self._preset_combo.setCurrentIndex(speed_map.get(preset.speed_preset, 1))

        # 오디오 비트레이트
        ab_idx = self._audio_bitrate_combo.findData(preset.audio_bitrate)
        if ab_idx >= 0:
            self._audio_bitrate_combo.setCurrentIndex(ab_idx)

        # 컨테이너
        container_idx = self._container_combo.findData(preset.container)
        if container_idx >= 0:
            self._container_combo.setCurrentIndex(container_idx)

        for w in (self._codec_combo, self._res_combo, self._crf_slider,
                  self._preset_combo, self._audio_bitrate_combo, self._container_combo):
            w.blockSignals(False)

        self._update_output_info()

    def _on_save_export_preset(self) -> None:
        """현재 UI 설정을 이름으로 사용자 프리셋에 저장한다."""
        name, ok = QInputDialog.getText(
            self,
            tr("Save Preset..."),
            tr("Preset name:"),
        )
        if not ok or not name.strip():
            return
        name = name.strip()

        # 기본 프리셋 이름으로 저장 금지
        default_names = {p.name for p in DEFAULT_PRESETS}
        if name in default_names:
            QMessageBox.warning(
                self, tr("Save Preset..."),
                tr("Cannot save over built-in preset"),
            )
            return

        codec_text = self._codec_combo.currentText()
        codec = "hevc" if "HEVC" in codec_text else "h264"
        w, h = self._res_combo.currentData() or (0, 0)
        speed_key = self._presets[self._preset_combo.currentIndex()][1]
        audio_bitrate = self._audio_bitrate_combo.currentData() or "192k"
        container = self._container_combo.currentData() or "mp4"

        preset = ExportPreset(
            name=name,
            width=w,
            height=h,
            codec=codec,
            container=container,
            audio_bitrate=audio_bitrate,
            crf=self._crf_slider.value(),
            speed_preset=speed_key,
        )
        self._preset_manager.save_preset(name, preset)
        self._populate_export_preset_combo()
        QMessageBox.information(self, tr("Save Preset..."), tr("Export preset saved"))

    def _on_delete_export_preset(self) -> None:
        """선택된 프리셋을 삭제한다. 기본 프리셋은 삭제 불가."""
        data = self._export_preset_combo.currentData()
        if not data:
            return
        kind, preset = data
        if kind == "default":
            QMessageBox.warning(
                self, tr("Delete Preset"),
                tr("Cannot delete built-in preset"),
            )
            return
        self._preset_manager.delete_preset(preset.name)
        self._populate_export_preset_combo()

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
        # 썸네일 임시 파일 정리
        if self._thumb_tmp_path:
            try:
                Path(self._thumb_tmp_path).unlink(missing_ok=True)
            except Exception:
                pass
        super().closeEvent(event)
