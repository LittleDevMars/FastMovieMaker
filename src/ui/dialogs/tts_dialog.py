"""TTS (Text-to-Speech) settings and progress dialog."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QMessageBox,
)

from src.models.subtitle import SubtitleTrack
from src.services.settings_manager import SettingsManager
from src.services.text_splitter import SplitStrategy
from src.services.tts_service import TTSService
from src.utils.config import (
    ELEVENLABS_DEFAULT_VOICES,
    TTS_DEFAULT_VOICE,
    TTS_DEFAULT_SPEED,
    TTS_VOICES,
    TTSEngine,
)
from src.workers.tts_worker import TTSWorker


class TTSDialog(QDialog):
    """Dialog for configuring and running TTS generation."""

    def __init__(self, video_audio_path: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate Speech (TTS)")
        self.setMinimumSize(600, 500)
        self.setModal(True)

        self._video_audio_path = video_audio_path
        self._result_track: SubtitleTrack | None = None
        self._result_audio_path: str | None = None
        self._thread: QThread | None = None
        self._worker: TTSWorker | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Script input
        script_group = QGroupBox("Script")
        script_layout = QVBoxLayout()
        self._script_edit = QPlainTextEdit()
        self._script_edit.setPlaceholderText(
            "Enter your script here...\n\n"
            "Example:\n"
            "안녕하세요. FastMovieMaker입니다.\n"
            "TTS 기능을 테스트합니다.\n"
            "음성 생성 확인 부탁드립니다."
        )
        self._script_edit.setMinimumHeight(200)
        script_layout.addWidget(self._script_edit)
        script_group.setLayout(script_layout)
        layout.addWidget(script_group)

        # Settings group
        settings_group = QGroupBox("Settings")
        settings_layout = QFormLayout()

        # Engine selector
        self._engine_combo = QComboBox()
        self._engine_combo.addItem("Edge-TTS (무료)", TTSEngine.EDGE_TTS)
        self._engine_combo.addItem("ElevenLabs (프리미엄)", TTSEngine.ELEVENLABS)
        self._engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        settings_layout.addRow("엔진:", self._engine_combo)

        # Language selector
        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["Korean", "English"])
        self._lang_combo.setCurrentText("Korean")
        self._lang_combo.currentTextChanged.connect(self._on_language_changed)
        settings_layout.addRow("Language:", self._lang_combo)

        # Voice selector
        self._voice_combo = QComboBox()
        self._populate_voices("Korean")
        settings_layout.addRow("Voice:", self._voice_combo)

        # Speed
        self._speed_spin = QDoubleSpinBox()
        self._speed_spin.setRange(0.5, 2.0)
        self._speed_spin.setSingleStep(0.1)
        self._speed_spin.setValue(TTS_DEFAULT_SPEED)
        self._speed_spin.setSuffix("x")
        settings_layout.addRow("Speed:", self._speed_spin)

        # Split strategy
        self._strategy_combo = QComboBox()
        self._strategy_combo.addItem("Sentence (. ! ?)", SplitStrategy.SENTENCE)
        self._strategy_combo.addItem("Newline", SplitStrategy.NEWLINE)
        self._strategy_combo.addItem("Fixed Length (50 chars)", SplitStrategy.FIXED_LENGTH)
        settings_layout.addRow("Split by:", self._strategy_combo)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Volume controls (if mixing with video audio)
        if self._video_audio_path:
            volume_group = QGroupBox("Volume Mix")
            volume_layout = QFormLayout()

            self._bg_volume_spin = QDoubleSpinBox()
            self._bg_volume_spin.setRange(0.0, 1.0)
            self._bg_volume_spin.setSingleStep(0.1)
            self._bg_volume_spin.setValue(0.5)
            self._bg_volume_spin.setPrefix("Background: ")
            volume_layout.addRow("BG Audio:", self._bg_volume_spin)

            self._tts_volume_spin = QDoubleSpinBox()
            self._tts_volume_spin.setRange(0.0, 1.0)
            self._tts_volume_spin.setSingleStep(0.1)
            self._tts_volume_spin.setValue(1.0)
            self._tts_volume_spin.setPrefix("TTS: ")
            volume_layout.addRow("TTS Audio:", self._tts_volume_spin)

            volume_group.setLayout(volume_layout)
            layout.addWidget(volume_group)
        else:
            self._bg_volume_spin = None
            self._tts_volume_spin = None

        # Status
        self._status_label = QLabel("Ready")
        layout.addWidget(self._status_label)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # indeterminate initially
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        # Buttons
        btn_layout = QHBoxLayout()
        self._generate_btn = QPushButton("Generate")
        self._generate_btn.setDefault(True)
        self._generate_btn.clicked.connect(self._on_generate)
        btn_layout.addWidget(self._generate_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self._cancel_btn)
        layout.addLayout(btn_layout)

    def _populate_voices(self, language: str) -> None:
        """Populate voice combo with voices for the selected language."""
        self._voice_combo.clear()

        if language in TTS_VOICES:
            voices = TTS_VOICES[language]
            for gender in ["Female", "Male"]:
                if gender in voices:
                    for voice_name in voices[gender]:
                        # Extract display name (e.g., "ko-KR-SunHiNeural" -> "SunHi")
                        display = voice_name.split("-")[-1].replace("Neural", "").replace("Multilingual", "")
                        self._voice_combo.addItem(f"{display} ({gender})", voice_name)

        # Set default
        default_index = self._voice_combo.findData(TTS_DEFAULT_VOICE)
        if default_index >= 0:
            self._voice_combo.setCurrentIndex(default_index)

    def _on_engine_changed(self, index: int) -> None:
        """Handle TTS engine selection change."""
        engine = self._engine_combo.currentData()
        if engine == TTSEngine.ELEVENLABS:
            self._lang_combo.setEnabled(False)
            self._populate_elevenlabs_voices()
        else:
            self._lang_combo.setEnabled(True)
            self._populate_voices(self._lang_combo.currentText())

    def _populate_elevenlabs_voices(self) -> None:
        """Populate voice combo with ElevenLabs voices."""
        self._voice_combo.clear()
        for display_name, voice_id in ELEVENLABS_DEFAULT_VOICES.items():
            self._voice_combo.addItem(display_name, voice_id)

    def _on_language_changed(self, language: str) -> None:
        """Handle language selection change."""
        self._populate_voices(language)

    def _on_generate(self) -> None:
        """Start TTS generation."""
        script = self._script_edit.toPlainText().strip()
        if not script:
            QMessageBox.warning(
                self,
                "Empty Script",
                "Please enter a script to generate speech."
            )
            return

        engine = self._engine_combo.currentData()

        # Validate API key for ElevenLabs
        if engine == TTSEngine.ELEVENLABS:
            api_key = SettingsManager().get_elevenlabs_api_key()
            if not api_key:
                QMessageBox.warning(
                    self,
                    "API 키 필요",
                    "ElevenLabs를 사용하려면 API 키가 필요합니다.\n\n"
                    "Edit > Preferences > API Keys에서 설정하세요.",
                )
                return

        # Disable controls
        self._generate_btn.setEnabled(False)
        self._script_edit.setEnabled(False)
        self._engine_combo.setEnabled(False)
        self._lang_combo.setEnabled(False)
        self._voice_combo.setEnabled(False)
        self._speed_spin.setEnabled(False)
        self._strategy_combo.setEnabled(False)
        if self._bg_volume_spin:
            self._bg_volume_spin.setEnabled(False)
        if self._tts_volume_spin:
            self._tts_volume_spin.setEnabled(False)

        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)  # indeterminate

        # Get settings
        voice_data = self._voice_combo.currentData()
        speed = self._speed_spin.value()
        strategy = self._strategy_combo.currentData()
        language = self._lang_combo.currentText().lower()[:2]  # "Korean" -> "ko"

        # Rate format differs by engine
        if engine == TTSEngine.ELEVENLABS:
            rate = str(speed)
        else:
            rate = TTSService.format_rate(speed)

        bg_volume = self._bg_volume_spin.value() if self._bg_volume_spin else 0.5
        tts_volume = self._tts_volume_spin.value() if self._tts_volume_spin else 1.0

        # Worker + Thread setup
        self._thread = QThread()
        self._worker = TTSWorker(
            script=script,
            voice=voice_data,
            rate=rate,
            strategy=strategy,
            language=language,
            video_audio_path=self._video_audio_path,
            bg_volume=bg_volume,
            tts_volume=tts_volume,
            engine=engine,
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.status_update.connect(self._on_status)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._cleanup_thread)
        self._worker.error.connect(self._cleanup_thread)

        self._thread.start()

    def _on_cancel(self) -> None:
        """Cancel TTS generation."""
        if self._worker:
            self._worker.cancel()
        self._cleanup_thread()
        self.reject()

    def _on_status(self, message: str) -> None:
        """Update status label."""
        self._status_label.setText(message)

    def _on_progress(self, current: int, total: int) -> None:
        """Update progress bar."""
        if total > 0:
            self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(current)

    def _on_finished(self, track: SubtitleTrack, audio_path: str) -> None:
        """Handle successful completion."""
        self._result_track = track
        self._result_audio_path = audio_path
        self.accept()

    def _on_error(self, message: str) -> None:
        """Handle error."""
        self._status_label.setText(f"Error: {message}")
        self._progress_bar.setVisible(False)

        # Re-enable controls
        self._generate_btn.setEnabled(True)
        self._script_edit.setEnabled(True)
        self._engine_combo.setEnabled(True)
        self._voice_combo.setEnabled(True)
        self._speed_spin.setEnabled(True)
        self._strategy_combo.setEnabled(True)
        # Re-enable language only if edge-tts is selected
        engine = self._engine_combo.currentData()
        self._lang_combo.setEnabled(engine != TTSEngine.ELEVENLABS)
        if self._bg_volume_spin:
            self._bg_volume_spin.setEnabled(True)
        if self._tts_volume_spin:
            self._tts_volume_spin.setEnabled(True)

        QMessageBox.critical(
            self,
            "TTS Generation Failed",
            f"Failed to generate speech:\n\n{message}"
        )

    def _cleanup_thread(self) -> None:
        """Clean up worker thread."""
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(5000)
        self._thread = None
        self._worker = None

    def result_track(self) -> SubtitleTrack | None:
        """Get the generated subtitle track."""
        return self._result_track

    def result_audio_path(self) -> str | None:
        """Get the path to the generated audio file."""
        return self._result_audio_path

    def closeEvent(self, event) -> None:
        """Handle dialog close."""
        self._on_cancel()
        super().closeEvent(event)
