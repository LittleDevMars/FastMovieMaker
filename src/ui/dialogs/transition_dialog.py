"""Dialog for configuring video transition effects."""

import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import QThread, Signal, QUrl, Qt
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QComboBox,
    QSpinBox,
    QDialogButtonBox,
    QPushButton,
    QLabel,
    QProgressBar,
)
from src.utils.i18n import tr
from src.utils.config import find_ffmpeg


class PreviewWorker(QThread):
    """Background worker to generate transition preview using FFmpeg."""
    
    finished = Signal(str)  # output_path
    error = Signal(str)

    def __init__(self, clip_out, clip_in, trans_type, trans_dur_ms):
        super().__init__()
        self.clip_out = clip_out
        self.clip_in = clip_in
        self.trans_type = trans_type
        self.trans_dur_ms = trans_dur_ms
        self._temp_file = None

    def run(self):
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            self.error.emit("FFmpeg not found")
            return

        if not self.clip_out.source_path or not self.clip_in.source_path:
            self.error.emit("Missing source video")
            return

        try:
            # Create temp file
            self._temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            output_path = self._temp_file.name
            self._temp_file.close()

            # Preview settings: 2 seconds of each clip
            # Note: We ignore speed for preview simplicity, showing raw source transition
            preview_dur = 2.0
            trans_dur_sec = self.trans_dur_ms / 1000.0
            
            # Calculate trim points (source time)
            # Clip A: take last 'preview_dur' seconds
            out_end = self.clip_out.source_out_ms / 1000.0
            out_start = max(self.clip_out.source_in_ms / 1000.0, out_end - preview_dur)
            actual_dur_a = out_end - out_start

            # Clip B: take first 'preview_dur' seconds
            in_start = self.clip_in.source_in_ms / 1000.0
            in_end = min(self.clip_in.source_out_ms / 1000.0, in_start + preview_dur)
            
            # xfade offset = duration of first clip - transition duration
            offset = actual_dur_a - trans_dur_sec

            # FFmpeg command
            # Scale to 640x360 for fast preview
            cmd = [
                ffmpeg, "-y",
                "-ss", str(out_start), "-t", str(preview_dur), "-i", self.clip_out.source_path,
                "-ss", str(in_start), "-t", str(preview_dur), "-i", self.clip_in.source_path,
                "-filter_complex",
                f"[0:v]scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2,setsar=1[v0];"
                f"[1:v]scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2,setsar=1[v1];"
                f"[v0][v1]xfade=transition={self.trans_type}:duration={trans_dur_sec}:offset={offset}[v]",
                "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast", "-an",
                output_path
            ]
            
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            self.finished.emit(output_path)

        except Exception as e:
            self.error.emit(str(e))


class TransitionDialog(QDialog):
    """Video transition configuration dialog."""

    def __init__(self, parent=None, initial_type: str = "fade", initial_duration: int = 500,
                 outgoing_clip=None, incoming_clip=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Transition Settings"))
        self.resize(400, 450)

        self._outgoing_clip = outgoing_clip
        self._incoming_clip = incoming_clip
        self._preview_worker = None
        self._preview_path = None

        layout = QVBoxLayout(self)
        
        # --- Preview Area ---
        self._video_widget = QVideoWidget()
        self._video_widget.setMinimumHeight(200)
        self._video_widget.setStyleSheet("background-color: black;")
        layout.addWidget(self._video_widget)

        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)
        self._player.setVideoOutput(self._video_widget)
        # Loop preview
        self._player.setLoops(QMediaPlayer.Loops.Infinite)

        preview_layout = QHBoxLayout()
        self._preview_btn = QPushButton(tr("Preview"))
        self._preview_btn.clicked.connect(self._start_preview)
        preview_layout.addWidget(self._preview_btn)
        
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        preview_layout.addWidget(self._progress)
        layout.addLayout(preview_layout)

        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: red")
        layout.addWidget(self._error_label)

        # --- Settings ---
        form = QFormLayout()

        self._type_combo = QComboBox()
        # Common xfade transitions supported by FFmpeg
        transitions = [
            ("fade", tr("Fade")),
            ("wipeleft", tr("Wipe Left")),
            ("wiperight", tr("Wipe Right")),
            ("wipeup", tr("Wipe Up")),
            ("wipedown", tr("Wipe Down")),
            ("slideleft", tr("Slide Left")),
            ("slideright", tr("Slide Right")),
            ("slideup", tr("Slide Up")),
            ("slidedown", tr("Slide Down")),
            ("circlecrop", tr("Circle Crop")),
            ("rectcrop", tr("Rect Crop")),
            ("distance", tr("Distance")),
            ("fadeblack", tr("Fade Black")),
            ("fadewhite", tr("Fade White")),
            ("radial", tr("Radial")),
            ("smoothleft", tr("Smooth Left")),
            ("smoothright", tr("Smooth Right")),
            ("smoothup", tr("Smooth Up")),
            ("smoothdown", tr("Smooth Down")),
            ("pixelize", tr("Pixelize")),
            ("dissolve", tr("Dissolve")),
            ("hblur", tr("Horizontal Blur")),
            ("wipetl", tr("Wipe Top-Left")),
            ("wiper", tr("Wipe Radial")),
        ]
        for t_id, t_name in transitions:
            self._type_combo.addItem(t_name, t_id)
        
        # Set initial selection
        idx = self._type_combo.findData(initial_type)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        else:
            self._type_combo.setCurrentIndex(0)

        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(100, 5000) # 0.1s to 5s
        self._duration_spin.setSingleStep(100)
        self._duration_spin.setSuffix(" ms")
        self._duration_spin.setValue(initial_duration)
        
        # Auto-preview when type changes
        self._type_combo.currentIndexChanged.connect(self._start_preview)

        form.addRow(tr("Type:"), self._type_combo)
        form.addRow(tr("Duration:"), self._duration_spin)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Initial preview if clips are available
        if self._outgoing_clip and self._incoming_clip:
            self._start_preview()
        else:
            self._preview_btn.setEnabled(False)
            self._error_label.setText(tr("Select clips to preview"))

    def _start_preview(self):
        if not self._outgoing_clip or not self._incoming_clip:
            return

        self._preview_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._error_label.setText("")
        self._player.stop()

        trans_type = self._type_combo.currentData()
        trans_dur = self._duration_spin.value()

        self._preview_worker = PreviewWorker(
            self._outgoing_clip, self._incoming_clip, trans_type, trans_dur
        )
        self._preview_worker.finished.connect(self._on_preview_ready)
        self._preview_worker.error.connect(self._on_preview_error)
        self._preview_worker.start()

    def _on_preview_ready(self, path):
        self._preview_path = path
        self._progress.setVisible(False)
        self._preview_btn.setEnabled(True)
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()

    def _on_preview_error(self, msg):
        self._progress.setVisible(False)
        self._preview_btn.setEnabled(True)
        self._error_label.setText(f"Preview failed: {msg}")

    def get_data(self) -> tuple[str, int]:
        """Return (transition_type, duration_ms)."""
        return (
            self._type_combo.currentData(),
            self._duration_spin.value()
        )