"""Preferences dialog for application settings."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.services.settings_manager import SettingsManager
from src.services.translator import ISO_639_1_CODES


class PreferencesDialog(QDialog):
    """Dialog for editing application preferences."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumSize(600, 500)

        self._settings = SettingsManager()
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Tab widget
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # Create tabs
        self._tabs.addTab(self._create_general_tab(), "General")
        self._tabs.addTab(self._create_editing_tab(), "Editing")
        self._tabs.addTab(self._create_advanced_tab(), "Advanced")
        self._tabs.addTab(self._create_api_keys_tab(), "API Keys")

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._save_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _create_general_tab(self) -> QWidget:
        """Create the General settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Autosave group
        autosave_group = QGroupBox("Autosave")
        autosave_layout = QFormLayout(autosave_group)

        self._autosave_interval = QSpinBox()
        self._autosave_interval.setRange(10, 300)
        self._autosave_interval.setSuffix(" seconds")
        autosave_layout.addRow("Save Interval:", self._autosave_interval)

        self._autosave_idle = QSpinBox()
        self._autosave_idle.setRange(1, 60)
        self._autosave_idle.setSuffix(" seconds")
        autosave_layout.addRow("Idle Timeout:", self._autosave_idle)

        layout.addWidget(autosave_group)

        # Recent files group
        recent_group = QGroupBox("Recent Files")
        recent_layout = QFormLayout(recent_group)

        self._recent_max = QSpinBox()
        self._recent_max.setRange(5, 20)
        self._recent_max.setSuffix(" files")
        recent_layout.addRow("Maximum Recent Files:", self._recent_max)

        layout.addWidget(recent_group)

        # Language group
        lang_group = QGroupBox("Default Language")
        lang_layout = QFormLayout(lang_group)

        self._default_lang = QComboBox()
        self._default_lang.addItems(sorted(ISO_639_1_CODES.keys()))
        lang_layout.addRow("New Project Language:", self._default_lang)

        layout.addWidget(lang_group)

        # UI group
        ui_group = QGroupBox("User Interface")
        ui_layout = QFormLayout(ui_group)

        self._theme = QComboBox()
        self._theme.addItems(["dark", "light"])
        ui_layout.addRow("Theme:", self._theme)

        info_label = QLabel("Note: Theme changes require restart")
        info_label.setStyleSheet("color: gray; font-style: italic;")
        ui_layout.addRow("", info_label)

        layout.addWidget(ui_group)

        layout.addStretch()
        return widget

    def _create_editing_tab(self) -> QWidget:
        """Create the Editing settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Subtitle defaults group
        subtitle_group = QGroupBox("Subtitle Defaults")
        subtitle_layout = QFormLayout(subtitle_group)

        self._default_duration = QSpinBox()
        self._default_duration.setRange(500, 10000)
        self._default_duration.setSuffix(" ms")
        subtitle_layout.addRow("Default Duration:", self._default_duration)

        layout.addWidget(subtitle_group)

        # Timeline group
        timeline_group = QGroupBox("Timeline")
        timeline_layout = QFormLayout(timeline_group)

        self._snap_tolerance = QSpinBox()
        self._snap_tolerance.setRange(5, 50)
        self._snap_tolerance.setSuffix(" pixels")
        timeline_layout.addRow("Snap Tolerance:", self._snap_tolerance)

        self._frame_fps = QSpinBox()
        self._frame_fps.setRange(10, 120)
        self._frame_fps.setSuffix(" fps")
        timeline_layout.addRow("Frame Seek FPS:", self._frame_fps)

        layout.addWidget(timeline_group)

        layout.addStretch()
        return widget

    def _create_advanced_tab(self) -> QWidget:
        """Create the Advanced settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # FFmpeg group
        ffmpeg_group = QGroupBox("FFmpeg")
        ffmpeg_layout = QVBoxLayout(ffmpeg_group)

        ffmpeg_path_layout = QHBoxLayout()
        self._ffmpeg_path = QLineEdit()
        self._ffmpeg_path.setPlaceholderText("Auto-detect")
        ffmpeg_path_layout.addWidget(QLabel("FFmpeg Path:"))
        ffmpeg_path_layout.addWidget(self._ffmpeg_path)

        browse_ffmpeg = QPushButton("Browse...")
        browse_ffmpeg.clicked.connect(self._browse_ffmpeg)
        ffmpeg_path_layout.addWidget(browse_ffmpeg)

        ffmpeg_layout.addLayout(ffmpeg_path_layout)
        layout.addWidget(ffmpeg_group)

        # Whisper group
        whisper_group = QGroupBox("Whisper")
        whisper_layout = QVBoxLayout(whisper_group)

        whisper_cache_layout = QHBoxLayout()
        self._whisper_cache = QLineEdit()
        self._whisper_cache.setPlaceholderText("Default cache directory")
        whisper_cache_layout.addWidget(QLabel("Model Cache:"))
        whisper_cache_layout.addWidget(self._whisper_cache)

        browse_cache = QPushButton("Browse...")
        browse_cache.clicked.connect(self._browse_whisper_cache)
        whisper_cache_layout.addWidget(browse_cache)

        whisper_layout.addLayout(whisper_cache_layout)
        layout.addWidget(whisper_group)

        layout.addStretch()
        return widget

    def _create_api_keys_tab(self) -> QWidget:
        """Create the API Keys tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # DeepL group
        deepl_group = QGroupBox("DeepL Translation")
        deepl_layout = QVBoxLayout(deepl_group)

        deepl_info = QLabel(
            "Get your free API key at: https://www.deepl.com/pro-api"
        )
        deepl_info.setOpenExternalLinks(True)
        deepl_info.setStyleSheet("color: gray; font-style: italic;")
        deepl_layout.addWidget(deepl_info)

        self._deepl_key = QLineEdit()
        self._deepl_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._deepl_key.setPlaceholderText("Enter DeepL API key...")
        deepl_layout.addWidget(self._deepl_key)

        layout.addWidget(deepl_group)

        # OpenAI group
        openai_group = QGroupBox("OpenAI (GPT-4o-mini)")
        openai_layout = QVBoxLayout(openai_group)

        openai_info = QLabel(
            "Get your API key at: https://platform.openai.com/api-keys"
        )
        openai_info.setOpenExternalLinks(True)
        openai_info.setStyleSheet("color: gray; font-style: italic;")
        openai_layout.addWidget(openai_info)

        self._openai_key = QLineEdit()
        self._openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._openai_key.setPlaceholderText("Enter OpenAI API key...")
        openai_layout.addWidget(self._openai_key)

        layout.addWidget(openai_group)

        # ElevenLabs group
        elevenlabs_group = QGroupBox("ElevenLabs (Text-to-Speech)")
        elevenlabs_layout = QVBoxLayout(elevenlabs_group)

        elevenlabs_info = QLabel(
            "Get your API key at: https://elevenlabs.io/app/settings/api-keys"
        )
        elevenlabs_info.setOpenExternalLinks(True)
        elevenlabs_info.setStyleSheet("color: gray; font-style: italic;")
        elevenlabs_layout.addWidget(elevenlabs_info)

        self._elevenlabs_key = QLineEdit()
        self._elevenlabs_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._elevenlabs_key.setPlaceholderText("Enter ElevenLabs API key...")
        elevenlabs_layout.addWidget(self._elevenlabs_key)

        layout.addWidget(elevenlabs_group)

        # Info label
        info_label = QLabel(
            "Note: API keys are stored securely in your system settings.\n"
            "Google Translate does not require an API key.\n"
            "Edge-TTS is free and does not require an API key."
        )
        info_label.setStyleSheet("color: gray; font-style: italic; margin-top: 20px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addStretch()
        return widget

    def _load_settings(self):
        """Load current settings into UI."""
        # General
        self._autosave_interval.setValue(self._settings.get_autosave_interval())
        self._autosave_idle.setValue(self._settings.get_autosave_idle_timeout())
        self._recent_max.setValue(self._settings.get_recent_files_max())
        self._default_lang.setCurrentText(self._settings.get_default_language())
        self._theme.setCurrentText(self._settings.get_theme())

        # Editing
        self._default_duration.setValue(self._settings.get_default_subtitle_duration())
        self._snap_tolerance.setValue(self._settings.get_snap_tolerance())
        self._frame_fps.setValue(self._settings.get_frame_seek_fps())

        # Advanced
        ffmpeg_path = self._settings.get_ffmpeg_path()
        self._ffmpeg_path.setText(ffmpeg_path or "")

        whisper_cache = self._settings.get_whisper_cache_dir()
        self._whisper_cache.setText(whisper_cache or "")

        # API Keys
        self._deepl_key.setText(self._settings.get_deepl_api_key())
        self._openai_key.setText(self._settings.get_openai_api_key())
        self._elevenlabs_key.setText(self._settings.get_elevenlabs_api_key())

    def _save_and_accept(self):
        """Save settings and close dialog."""
        # General
        self._settings.set_autosave_interval(self._autosave_interval.value())
        self._settings.set_autosave_idle_timeout(self._autosave_idle.value())
        self._settings.set_recent_files_max(self._recent_max.value())
        self._settings.set_default_language(self._default_lang.currentText())
        self._settings.set_theme(self._theme.currentText())

        # Editing
        self._settings.set_default_subtitle_duration(self._default_duration.value())
        self._settings.set_snap_tolerance(self._snap_tolerance.value())
        self._settings.set_frame_seek_fps(self._frame_fps.value())

        # Advanced
        ffmpeg_path = self._ffmpeg_path.text().strip()
        self._settings.set_ffmpeg_path(ffmpeg_path if ffmpeg_path else None)

        whisper_cache = self._whisper_cache.text().strip()
        self._settings.set_whisper_cache_dir(whisper_cache if whisper_cache else None)

        # API Keys
        self._settings.set_deepl_api_key(self._deepl_key.text().strip())
        self._settings.set_openai_api_key(self._openai_key.text().strip())
        self._settings.set_elevenlabs_api_key(self._elevenlabs_key.text().strip())

        # Sync to disk
        self._settings.sync()

        self.accept()

    def _browse_ffmpeg(self):
        """Browse for FFmpeg executable."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select FFmpeg Executable", str(Path.home())
        )
        if file_path:
            self._ffmpeg_path.setText(file_path)

    def _browse_whisper_cache(self):
        """Browse for Whisper cache directory."""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Whisper Cache Directory", str(Path.home())
        )
        if dir_path:
            self._whisper_cache.setText(dir_path)
