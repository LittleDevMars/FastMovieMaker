"""Preferences dialog for application settings."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.services.settings_manager import SettingsManager, _SHORTCUT_DEFAULTS
from src.services.translator import ISO_639_1_CODES
from src.utils.i18n import tr

# 단축키 탭에 표시될 (action_key, display_name) 목록
_SHORTCUT_ACTIONS: list[tuple[str, str]] = [
    ("play_pause",        "Play / Pause"),
    ("seek_back",         "Seek Back 5s"),
    ("seek_forward",      "Seek Forward 5s"),
    ("seek_back_frame",   "Seek Back 1 Frame"),
    ("seek_forward_frame", "Seek Forward 1 Frame"),
    ("delete",            "Delete Selected"),
    ("split_clip",        "Split Clip"),
    ("zoom_in",           "Timeline Zoom In"),
    ("zoom_out",          "Timeline Zoom Out"),
    ("zoom_fit",          "Timeline Zoom Fit"),
    ("snap_toggle",       "Toggle Snap"),
    ("copy_clip",         "Copy Clip"),
    ("paste_clip",        "Paste Clip"),
]


class PreferencesDialog(QDialog):
    """Dialog for editing application preferences."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Preferences"))
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
        self._tabs.addTab(self._create_general_tab(), tr("General"))
        self._tabs.addTab(self._create_editing_tab(), tr("Editing"))
        self._tabs.addTab(self._create_advanced_tab(), tr("Advanced"))
        self._tabs.addTab(self._create_api_keys_tab(), tr("API Keys"))
        self._tabs.addTab(self._create_shortcuts_tab(), tr("Shortcuts"))

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
        autosave_group = QGroupBox(tr("Autosave"))
        autosave_layout = QFormLayout(autosave_group)

        self._autosave_interval = QSpinBox()
        self._autosave_interval.setRange(10, 300)
        self._autosave_interval.setSuffix(f" {tr('seconds')}")
        autosave_layout.addRow(tr("Save Interval:"), self._autosave_interval)

        self._autosave_idle = QSpinBox()
        self._autosave_idle.setRange(1, 60)
        self._autosave_idle.setSuffix(f" {tr('seconds')}")
        autosave_layout.addRow(tr("Idle Timeout:"), self._autosave_idle)

        layout.addWidget(autosave_group)

        # Recent files group
        recent_group = QGroupBox(tr("Recent Files"))
        recent_layout = QFormLayout(recent_group)

        self._recent_max = QSpinBox()
        self._recent_max.setRange(5, 20)
        self._recent_max.setSuffix(f" {tr('files')}")
        recent_layout.addRow(tr("Maximum Recent Files:"), self._recent_max)

        layout.addWidget(recent_group)

        # Language group
        lang_group = QGroupBox(tr("Default Language"))
        lang_layout = QFormLayout(lang_group)

        self._default_lang = QComboBox()
        self._default_lang.addItems(sorted(ISO_639_1_CODES.keys()))
        lang_layout.addRow(tr("New Project Language:"), self._default_lang)

        layout.addWidget(lang_group)

        # UI group
        ui_group = QGroupBox(tr("User Interface"))
        ui_layout = QFormLayout(ui_group)

        self._theme = QComboBox()
        self._theme.addItems(["dark", "light"])
        ui_layout.addRow(tr("Theme:"), self._theme)

        # UI Language selector
        self._ui_language = QComboBox()
        self._ui_language.addItem("English", "en")
        self._ui_language.addItem("한국어", "ko")
        ui_layout.addRow(tr("Language:"), self._ui_language)

        info_label = QLabel(tr("Note: Language and theme changes require restart"))
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
        subtitle_group = QGroupBox(tr("Subtitle Defaults"))
        subtitle_layout = QFormLayout(subtitle_group)

        self._default_duration = QSpinBox()
        self._default_duration.setRange(500, 10000)
        self._default_duration.setSuffix(" ms")
        subtitle_layout.addRow(tr("Default Duration:"), self._default_duration)

        layout.addWidget(subtitle_group)

        # Timeline group
        timeline_group = QGroupBox(tr("Timeline"))
        timeline_layout = QFormLayout(timeline_group)

        self._snap_tolerance = QSpinBox()
        self._snap_tolerance.setRange(5, 50)
        self._snap_tolerance.setSuffix(f" {tr('pixels')}")
        timeline_layout.addRow(tr("Snap Tolerance:"), self._snap_tolerance)

        self._frame_fps = QSpinBox()
        self._frame_fps.setRange(10, 120)
        self._frame_fps.setSuffix(" fps")
        timeline_layout.addRow(tr("Frame Seek FPS:"), self._frame_fps)

        # Audio speed settings
        self._audio_pitch_shift = QCheckBox(tr("Audio speed changes pitch"))
        timeline_layout.addRow(tr("Audio Speed:"), self._audio_pitch_shift)

        self._frame_quality = QComboBox()
        self._frame_quality.addItem(tr("Low"), 10)
        self._frame_quality.addItem(tr("Medium"), 5)
        self._frame_quality.addItem(tr("High"), 2)
        timeline_layout.addRow(tr("Frame Cache Quality:"), self._frame_quality)

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
        self._ffmpeg_path.setPlaceholderText(tr("Auto-detect"))
        ffmpeg_path_layout.addWidget(QLabel(tr("FFmpeg Path:")))
        ffmpeg_path_layout.addWidget(self._ffmpeg_path)

        browse_ffmpeg = QPushButton(tr("Browse..."))
        browse_ffmpeg.clicked.connect(self._browse_ffmpeg)
        ffmpeg_path_layout.addWidget(browse_ffmpeg)

        ffmpeg_layout.addLayout(ffmpeg_path_layout)
        layout.addWidget(ffmpeg_group)

        # Whisper group
        whisper_group = QGroupBox("Whisper")
        whisper_layout = QVBoxLayout(whisper_group)

        whisper_cache_layout = QHBoxLayout()
        self._whisper_cache = QLineEdit()
        self._whisper_cache.setPlaceholderText(tr("Default cache directory"))
        whisper_cache_layout.addWidget(QLabel(tr("Model Cache:")))
        whisper_cache_layout.addWidget(self._whisper_cache)

        browse_cache = QPushButton(tr("Browse..."))
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
        deepl_group = QGroupBox(tr("DeepL Translation"))
        deepl_layout = QVBoxLayout(deepl_group)

        deepl_info = QLabel(
            f"{tr('Get your free API key at')}: https://www.deepl.com/pro-api"
        )
        deepl_info.setOpenExternalLinks(True)
        deepl_info.setStyleSheet("color: gray; font-style: italic;")
        deepl_layout.addWidget(deepl_info)

        self._deepl_key = QLineEdit()
        self._deepl_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._deepl_key.setPlaceholderText(tr("Enter DeepL API key..."))
        deepl_layout.addWidget(self._deepl_key)

        layout.addWidget(deepl_group)

        # OpenAI group
        openai_group = QGroupBox("OpenAI (GPT-4o-mini)")
        openai_layout = QVBoxLayout(openai_group)

        openai_info = QLabel(
            f"{tr('Get your API key at')}: https://platform.openai.com/api-keys"
        )
        openai_info.setOpenExternalLinks(True)
        openai_info.setStyleSheet("color: gray; font-style: italic;")
        openai_layout.addWidget(openai_info)

        self._openai_key = QLineEdit()
        self._openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._openai_key.setPlaceholderText(tr("Enter OpenAI API key..."))
        openai_layout.addWidget(self._openai_key)

        layout.addWidget(openai_group)

        # ElevenLabs group
        elevenlabs_group = QGroupBox("ElevenLabs (Text-to-Speech)")
        elevenlabs_layout = QVBoxLayout(elevenlabs_group)

        elevenlabs_info = QLabel(
            f"{tr('Get your API key at')}: https://elevenlabs.io/app/settings/api-keys"
        )
        elevenlabs_info.setOpenExternalLinks(True)
        elevenlabs_info.setStyleSheet("color: gray; font-style: italic;")
        elevenlabs_layout.addWidget(elevenlabs_info)

        self._elevenlabs_key = QLineEdit()
        self._elevenlabs_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._elevenlabs_key.setPlaceholderText(tr("Enter ElevenLabs API key..."))
        elevenlabs_layout.addWidget(self._elevenlabs_key)

        layout.addWidget(elevenlabs_group)

        # Info label
        info_label = QLabel(
            tr("Note: API keys are stored securely in your system settings.") + "\n"
            + tr("Google Translate does not require an API key.") + "\n"
            + tr("Edge-TTS is free and does not require an API key.")
        )
        info_label.setStyleSheet("color: gray; font-style: italic; margin-top: 20px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addStretch()
        return widget

    def _create_shortcuts_tab(self) -> QWidget:
        """단축키 커스터마이징 탭을 생성한다."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self._shortcuts_table = QTableWidget(len(_SHORTCUT_ACTIONS), 2)
        self._shortcuts_table.setHorizontalHeaderLabels(
            [tr("Action"), tr("Shortcut")]
        )
        self._shortcuts_table.horizontalHeader().setStretchLastSection(True)
        self._shortcuts_table.verticalHeader().setVisible(False)
        self._shortcuts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self._key_edits: list[QKeySequenceEdit] = []
        for row, (action, label) in enumerate(_SHORTCUT_ACTIONS):
            item = QTableWidgetItem(label)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._shortcuts_table.setItem(row, 0, item)
            edit = QKeySequenceEdit()
            self._shortcuts_table.setCellWidget(row, 1, edit)
            self._key_edits.append(edit)

        layout.addWidget(self._shortcuts_table)

        reset_btn = QPushButton(tr("Reset All Shortcuts"))
        reset_btn.clicked.connect(self._reset_all_shortcuts)
        layout.addWidget(reset_btn)

        self._load_shortcuts()
        return widget

    def _load_shortcuts(self) -> None:
        """SettingsManager에서 단축키를 읽어 QKeySequenceEdit에 적용한다."""
        for row, (action, _) in enumerate(_SHORTCUT_ACTIONS):
            key = self._settings.get_shortcut(action)
            self._key_edits[row].setKeySequence(QKeySequence(key))

    def _save_shortcuts(self) -> None:
        """QKeySequenceEdit 값을 SettingsManager에 저장한다."""
        for row, (action, _) in enumerate(_SHORTCUT_ACTIONS):
            seq = self._key_edits[row].keySequence()
            self._settings.set_shortcut(action, seq.toString())

    def _reset_all_shortcuts(self) -> None:
        """모든 단축키를 기본값으로 초기화한다."""
        for row, (action, _) in enumerate(_SHORTCUT_ACTIONS):
            default = _SHORTCUT_DEFAULTS.get(action, "")
            self._key_edits[row].setKeySequence(QKeySequence(default))

    def _load_settings(self):
        """Load current settings into UI."""
        # General
        self._autosave_interval.setValue(self._settings.get_autosave_interval())
        self._autosave_idle.setValue(self._settings.get_autosave_idle_timeout())
        self._recent_max.setValue(self._settings.get_recent_files_max())
        self._default_lang.setCurrentText(self._settings.get_default_language())
        self._theme.setCurrentText(self._settings.get_theme())

        # UI Language
        current_lang = self._settings.get_ui_language()
        lang_index = self._ui_language.findData(current_lang)
        if lang_index >= 0:
            self._ui_language.setCurrentIndex(lang_index)

        # Editing
        self._default_duration.setValue(self._settings.get_default_subtitle_duration())
        self._snap_tolerance.setValue(self._settings.get_snap_tolerance())
        self._frame_fps.setValue(self._settings.get_frame_seek_fps())
        self._audio_pitch_shift.setChecked(self._settings.get_audio_speed_pitch_shift())

        quality = self._settings.get_frame_cache_quality()
        idx = self._frame_quality.findData(quality)
        if idx >= 0:
            self._frame_quality.setCurrentIndex(idx)

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
        self._settings.set_ui_language(self._ui_language.currentData())

        # Editing
        self._settings.set_default_subtitle_duration(self._default_duration.value())
        self._settings.set_snap_tolerance(self._snap_tolerance.value())
        self._settings.set_frame_seek_fps(self._frame_fps.value())
        self._settings.set_audio_speed_pitch_shift(self._audio_pitch_shift.isChecked())
        self._settings.set_frame_cache_quality(self._frame_quality.currentData())

        # Advanced
        ffmpeg_path = self._ffmpeg_path.text().strip()
        self._settings.set_ffmpeg_path(ffmpeg_path if ffmpeg_path else None)

        whisper_cache = self._whisper_cache.text().strip()
        self._settings.set_whisper_cache_dir(whisper_cache if whisper_cache else None)

        # API Keys
        self._settings.set_deepl_api_key(self._deepl_key.text().strip())
        self._settings.set_openai_api_key(self._openai_key.text().strip())
        self._settings.set_elevenlabs_api_key(self._elevenlabs_key.text().strip())

        # Shortcuts
        self._save_shortcuts()

        # Sync to disk
        self._settings.sync()

        self.accept()

    def _browse_ffmpeg(self):
        """Browse for FFmpeg executable."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, tr("Select FFmpeg Executable"), str(Path.home())
        )
        if file_path:
            self._ffmpeg_path.setText(file_path)

    def _browse_whisper_cache(self):
        """Browse for Whisper cache directory."""
        dir_path = QFileDialog.getExistingDirectory(
            self, tr("Select Whisper Cache Directory"), str(Path.home())
        )
        if dir_path:
            self._whisper_cache.setText(dir_path)
