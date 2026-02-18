"""TTS (Text-to-Speech) settings and progress dialog."""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QThread, QUrl, Qt, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
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
from src.utils.i18n import tr
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


class TTSPreviewWorker(QObject):
    """Worker for generating a short TTS preview."""

    finished = Signal(str)  # audio_path
    error = Signal(str)

    def __init__(self, engine: str, text: str, voice: str, rate: str, api_key: str = ""):
        super().__init__()
        self._engine = engine
        self._text = text
        self._voice = voice
        self._rate = rate
        self._api_key = api_key

    def run(self) -> None:
        try:
            temp_dir = Path(tempfile.gettempdir())
            output_path = temp_dir / f"tts_preview_{uuid.uuid4().hex}.mp3"

            if self._engine == TTSEngine.ELEVENLABS:
                from src.services.elevenlabs_tts_service import ElevenLabsTTSService
                service = ElevenLabsTTSService(self._api_key)
                speed = 1.0
                try:
                    speed = float(self._rate)
                except ValueError:
                    pass
                service.generate_speech(
                    text=self._text,
                    voice_id=self._voice,
                    speed=speed,
                    output_path=output_path
                )
            else:
                # Edge-TTS requires asyncio
                asyncio.run(TTSService.generate_speech(
                    text=self._text,
                    voice=self._voice,
                    rate=self._rate,
                    output_path=output_path
                ))

            self.finished.emit(str(output_path))
        except Exception as e:
            self.error.emit(str(e))


class TTSDialog(QDialog):
    """Dialog for configuring and running TTS generation."""

    def __init__(
        self,
        video_audio_path: Optional[Path] = None,
        parent=None,
        segment_mode: bool = False,
        initial_text: str = "",
        initial_voice: str | None = None,
        initial_speed: float | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(tr("Generate Speech (TTS)"))
        self.setMinimumSize(600, 500)
        self.setModal(True)

        self._video_audio_path = video_audio_path
        self._segment_mode = segment_mode
        self._initial_text = initial_text
        self._initial_voice = initial_voice
        self._initial_speed = initial_speed
        self._result_track: SubtitleTrack | None = None
        self._result_audio_path: str | None = None
        self._thread: QThread | None = None
        self._worker: TTSWorker | None = None

        # Preview components
        self._preview_thread: QThread | None = None
        self._preview_worker: TTSPreviewWorker | None = None
        self._audio_output = QAudioOutput()
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio_output)
        self._player.playbackStateChanged.connect(self._on_player_state_changed)

        self._build_ui()
        
        if self._segment_mode:
            self.setWindowTitle(tr("Edit Segment TTS"))
            self._apply_segment_settings()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Script input
        script_group = QGroupBox(tr("Script"))
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
        if self._segment_mode:
            self._script_edit.setReadOnly(True)
        layout.addWidget(script_group)

        # Settings group
        settings_group = QGroupBox(tr("Settings"))
        settings_layout = QFormLayout()

        # Engine selector
        self._engine_combo = QComboBox()
        self._engine_combo.addItem(tr("Edge-TTS (Free)"), TTSEngine.EDGE_TTS)
        self._engine_combo.addItem(tr("ElevenLabs (Premium)"), TTSEngine.ELEVENLABS)
        self._engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        settings_layout.addRow(tr("Engine:"), self._engine_combo)

        # Language selector
        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["Korean", "English"])
        self._lang_combo.setCurrentText("Korean")
        self._lang_combo.currentTextChanged.connect(self._on_language_changed)
        settings_layout.addRow(tr("Language:"), self._lang_combo)

        # Voice selector
        self._voice_combo = QComboBox()
        self._populate_voices("Korean")
        settings_layout.addRow(tr("Voice:"), self._voice_combo)

        # Speed
        self._speed_spin = QDoubleSpinBox()
        self._speed_spin.setRange(0.5, 2.0)
        self._speed_spin.setSingleStep(0.1)
        self._speed_spin.setValue(TTS_DEFAULT_SPEED)
        self._speed_spin.setSuffix("x")
        settings_layout.addRow(tr("Speed:"), self._speed_spin)

        # Split strategy
        self._strategy_combo = QComboBox()
        self._strategy_combo.addItem(tr("Sentence (. ! ?)"), SplitStrategy.SENTENCE)
        self._strategy_combo.addItem(tr("Newline"), SplitStrategy.NEWLINE)
        self._strategy_combo.addItem(tr("Fixed Length (50 chars)"), SplitStrategy.FIXED_LENGTH)
        if not self._segment_mode:
            settings_layout.addRow(tr("Split by:"), self._strategy_combo)
        else:
            self._strategy_combo.setEnabled(False)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Volume controls (if mixing with video audio)
        if self._video_audio_path:
            volume_group = QGroupBox(tr("Volume Mix"))
            volume_layout = QFormLayout()

            self._bg_volume_spin = QDoubleSpinBox()
            self._bg_volume_spin.setRange(0.0, 1.0)
            self._bg_volume_spin.setSingleStep(0.1)
            self._bg_volume_spin.setValue(0.5)
            self._bg_volume_spin.setPrefix("Background: ")
            volume_layout.addRow(tr("BG Audio:"), self._bg_volume_spin)

            self._tts_volume_spin = QDoubleSpinBox()
            self._tts_volume_spin.setRange(0.0, 1.0)
            self._tts_volume_spin.setSingleStep(0.1)
            self._tts_volume_spin.setValue(1.0)
            self._tts_volume_spin.setPrefix("TTS: ")
            volume_layout.addRow(tr("TTS Audio:"), self._tts_volume_spin)

            volume_group.setLayout(volume_layout)
            layout.addWidget(volume_group)
        else:
            self._bg_volume_spin = None
            self._tts_volume_spin = None

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
        self._preview_btn = QPushButton(tr("Preview"))
        self._preview_btn.clicked.connect(self._on_preview)
        btn_layout.addWidget(self._preview_btn)

        self._generate_btn = QPushButton(tr("Generate"))
        self._generate_btn.setDefault(True)
        self._generate_btn.clicked.connect(self._on_generate)
        btn_layout.addWidget(self._generate_btn)

        self._cancel_btn = QPushButton(tr("Cancel"))
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self._cancel_btn)
        layout.addLayout(btn_layout)

    def _apply_segment_settings(self) -> None:
        """Apply initial settings for segment mode."""
        self._script_edit.setPlainText(self._initial_text)
        if self._initial_speed:
            self._speed_spin.setValue(self._initial_speed)
        if self._initial_voice:
            idx = self._voice_combo.findData(self._initial_voice)
            if idx >= 0:
                self._voice_combo.setCurrentIndex(idx)

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

    def _on_preview(self) -> None:
        """Handle preview button click."""
        # If playing, stop
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.stop()
            self._preview_btn.setText(tr("Preview"))
            self._status_label.setText(tr("Ready"))
            return

        # If generating, cancel
        if self._preview_thread is not None:
            self._cancel_preview_generation()
            return

        # Prepare text (limit to 100 chars for preview)
        script = self._script_edit.toPlainText().strip()
        if not script:
            QMessageBox.warning(self, tr("Empty Script"), tr("Please enter a script to generate speech."))
            return
        
        preview_text = script[:100]
        if len(script) > 100:
            # Try to cut at the last space to avoid cutting words
            last_space = preview_text.rfind(' ')
            if last_space > 0:
                preview_text = preview_text[:last_space]

        engine = self._engine_combo.currentData()
        api_key = ""

        # Validate API key for ElevenLabs
        if engine == TTSEngine.ELEVENLABS:
            api_key = SettingsManager().get_elevenlabs_api_key()
            if not api_key:
                QMessageBox.warning(
                    self,
                    tr("API Key Required"),
                    tr("ElevenLabs requires an API key.") + "\n\n"
                    + tr("Set it in Edit > Preferences > API Keys."),
                )
                return

        # Get settings
        voice_data = self._voice_combo.currentData()
        speed = self._speed_spin.value()
        
        if engine == TTSEngine.ELEVENLABS:
            rate = str(speed)
        else:
            rate = TTSService.format_rate(speed)

        # UI update
        self._preview_btn.setText(tr("Stop Preview"))
        self._status_label.setText(tr("Generating preview..."))

        # Start worker
        self._preview_thread = QThread()
        self._preview_worker = TTSPreviewWorker(engine, preview_text, voice_data, rate, api_key)
        self._preview_worker.moveToThread(self._preview_thread)
        
        self._preview_thread.started.connect(self._preview_worker.run)
        self._preview_worker.finished.connect(self._on_preview_ready)
        self._preview_worker.error.connect(self._on_preview_error)
        self._preview_worker.finished.connect(self._cleanup_preview_thread)
        self._preview_worker.error.connect(self._cleanup_preview_thread)
        
        self._preview_thread.start()

    def _cancel_preview_generation(self) -> None:
        """Cancel the ongoing preview generation."""
        if self._preview_thread:
            if self._preview_worker:
                try:
                    self._preview_worker.finished.disconnect(self._on_preview_ready)
                    self._preview_worker.error.disconnect(self._on_preview_error)
                    self._preview_worker.finished.disconnect(self._cleanup_preview_thread)
                    self._preview_worker.error.disconnect(self._cleanup_preview_thread)
                except RuntimeError:
                    pass
            self._preview_thread.quit()
            # We don't wait here to avoid UI freeze. The thread will exit when run() returns.
        
        self._preview_thread = None
        self._preview_worker = None
        
        self._preview_btn.setText(tr("Preview"))
        self._status_label.setText(tr("Ready"))

    def _on_preview_ready(self, audio_path: str) -> None:
        self._status_label.setText(tr("Playing preview..."))
        self._player.setSource(QUrl.fromLocalFile(audio_path))
        self._player.play()

    def _on_preview_error(self, message: str) -> None:
        self._preview_btn.setText(tr("Preview"))
        self._status_label.setText(f"{tr('Preview failed')}: {message}")

    def _on_generate(self) -> None:  # In segment mode, this acts as "Apply"
        """Start TTS generation."""
        script = self._script_edit.toPlainText().strip()
        if not script:
            QMessageBox.warning(
                self,
                tr("Empty Script"),
                tr("Please enter a script to generate speech.")
            )
            return

        engine = self._engine_combo.currentData()

        # Validate API key for ElevenLabs
        if engine == TTSEngine.ELEVENLABS:
            api_key = SettingsManager().get_elevenlabs_api_key()
            if not api_key:
                QMessageBox.warning(
                    self,
                    tr("API Key Required"),
                    tr("ElevenLabs requires an API key.") + "\n\n"
                    + tr("Set it in Edit > Preferences > API Keys."),
                )
                return

        # Disable controls
        self._preview_btn.setEnabled(False)
        self._generate_btn.setEnabled(False)
        self._script_edit.setEnabled(False)
        self._engine_combo.setEnabled(False)
        self._lang_combo.setEnabled(False)
        self._voice_combo.setEnabled(False)
        self._speed_spin.setEnabled(False)
        if not self._segment_mode:
            self._strategy_combo.setEnabled(False)
        if self._bg_volume_spin:
            self._bg_volume_spin.setEnabled(False)
        if self._tts_volume_spin:
            self._tts_volume_spin.setEnabled(False)

        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)  # indeterminate

        # Get settings
        voice_data = self._voice_combo.currentData()
        self._final_speed = self._speed_spin.value()
        strategy = self._strategy_combo.currentData()
        language = self._lang_combo.currentText().lower()[:2]  # "Korean" -> "ko"

        # Rate format differs by engine
        if engine == TTSEngine.ELEVENLABS:
            rate = str(speed)
        else:
            rate = TTSService.format_rate(self._final_speed)

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
        self._preview_btn.setEnabled(True)
        self._generate_btn.setEnabled(True)
        self._script_edit.setEnabled(True)
        self._engine_combo.setEnabled(True)
        self._voice_combo.setEnabled(True)
        self._speed_spin.setEnabled(True)
        if not self._segment_mode:
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
            tr("TTS Generation Failed"),
            f"{tr('Failed to generate speech')}:\n\n{message}"
        )

    def _cleanup_thread(self) -> None:
        """Clean up worker thread."""
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(5000)
        self._thread = None
        self._worker = None

    def _cleanup_preview_thread(self) -> None:
        if self._preview_thread and self._preview_thread.isRunning():
            self._preview_thread.quit()
            self._preview_thread.wait(2000)
        self._preview_thread = None
        self._preview_worker = None

    def _on_player_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.StoppedState:
            if self._preview_thread is None:  # Only reset if not generating
                self._preview_btn.setText(tr("Preview"))
            if self._status_label.text() == tr("Playing preview..."):
                self._status_label.setText(tr("Ready"))
            self._preview_btn.setEnabled(True)

    def result_track(self) -> SubtitleTrack | None:
        """Get the generated subtitle track."""
        return self._result_track

    def result_audio_path(self) -> str | None:
        """Get the path to the generated audio file."""
        return self._result_audio_path

    def get_segment_settings(self) -> tuple[str, float]:
        """Return (voice, speed) for segment mode."""
        # If generation succeeded, return the settings used
        if hasattr(self, '_final_voice') and hasattr(self, '_final_speed'):
            return self._final_voice, self._final_speed
        # Fallback to current UI values
        return self._voice_combo.currentData(), self._speed_spin.value()

    def closeEvent(self, event) -> None:
        """Handle dialog close."""
        self._player.stop()
        self._cleanup_preview_thread()
        self._on_cancel()
        super().closeEvent(event)
