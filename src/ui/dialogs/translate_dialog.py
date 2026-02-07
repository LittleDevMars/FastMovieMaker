"""Translation dialog for subtitle tracks."""

import time
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.models.subtitle import SubtitleTrack
from src.services.settings_manager import SettingsManager
from src.services.translator import TranslationEngine, TranslatorService


class TranslateDialog(QDialog):
    """Dialog for translating subtitle tracks using various engines."""

    def __init__(
        self,
        track: SubtitleTrack,
        available_langs: List[str],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Translate Subtitles")
        self.setMinimumSize(500, 400)

        self._track = track
        self._available_langs = available_langs
        self._source_lang = track.language or "Korean"  # Default to Korean if not set
        self._translator = TranslatorService(self)
        self._translator.progress.connect(self._on_progress)
        self._translator.error.connect(self._on_error)
        self._settings = SettingsManager()

        # Result
        self._result_track = None
        self._translation_complete = False

        self._build_ui()
        self._load_api_keys()
        self._update_ui_state()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Language selection
        lang_group = QGroupBox("Languages")
        lang_layout = QFormLayout(lang_group)

        self._source_combo = QComboBox()
        self._source_combo.addItems(self._available_langs)
        self._source_combo.setCurrentText(self._source_lang)
        lang_layout.addRow("Source Language:", self._source_combo)

        self._target_combo = QComboBox()
        self._target_combo.addItems(self._available_langs)
        # Default target language is English if source is not English
        default_target = "English" if self._source_lang != "English" else "Korean"
        self._target_combo.setCurrentText(default_target)
        lang_layout.addRow("Target Language:", self._target_combo)

        layout.addWidget(lang_group)

        # Translation engine
        engine_group = QGroupBox("Translation Engine")
        engine_layout = QFormLayout(engine_group)

        self._engine_combo = QComboBox()
        self._engine_combo.addItem("DeepL API", TranslationEngine.DEEPL)
        self._engine_combo.addItem("GPT-4o-mini", TranslationEngine.GPT)
        self._engine_combo.addItem("Google Translate", TranslationEngine.GOOGLE)
        engine_layout.addRow("Engine:", self._engine_combo)

        # API key for selected engine
        self._api_key_layout = QHBoxLayout()
        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setPlaceholderText("Enter API key...")
        self._api_key_layout.addWidget(self._api_key_edit)

        self._save_key_btn = QPushButton("Save Key")
        self._save_key_btn.clicked.connect(self._save_api_key)
        self._api_key_layout.addWidget(self._save_key_btn)

        engine_layout.addRow("API Key:", self._api_key_layout)
        self._engine_combo.currentIndexChanged.connect(self._on_engine_changed)

        layout.addWidget(engine_group)

        # Track options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        self._new_track_radio = QRadioButton("Create new track")
        self._new_track_radio.setChecked(True)
        self._replace_radio = QRadioButton("Replace current track")
        options_layout.addWidget(self._new_track_radio)
        options_layout.addWidget(self._replace_radio)

        layout.addWidget(options_group)

        # Progress
        progress_group = QGroupBox("Translation Progress")
        progress_layout = QVBoxLayout(progress_group)

        self._progress_bar = QProgressBar()
        self._progress_bar.setValue(0)
        progress_layout.addWidget(self._progress_bar)

        self._status_label = QLabel("Ready to translate")
        progress_layout.addWidget(self._status_label)

        layout.addWidget(progress_group)

        # Preview
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)

        self._preview_text = QTextEdit()
        self._preview_text.setReadOnly(True)
        self._preview_text.setFont(QFont("Courier", 11))
        self._preview_text.setPlaceholderText("Translation preview will appear here...")
        preview_layout.addWidget(self._preview_text)

        layout.addWidget(preview_group)

        # Buttons
        self._button_box = QDialogButtonBox()
        self._translate_btn = self._button_box.addButton(
            "Translate", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._cancel_btn = self._button_box.addButton(
            "Cancel", QDialogButtonBox.ButtonRole.RejectRole
        )
        self._button_box.accepted.connect(self._on_translate)
        self._button_box.rejected.connect(self._on_cancel)
        layout.addWidget(self._button_box)

    def _load_api_keys(self):
        """Load saved API keys from settings."""
        # Load DeepL API key
        deepl_key = self._settings.get_deepl_api_key()
        self._translator.set_api_key(TranslationEngine.DEEPL, deepl_key)

        # Load OpenAI API key
        gpt_key = self._settings.get_openai_api_key()
        self._translator.set_api_key(TranslationEngine.GPT, gpt_key)

        # Update the UI with the current engine's key
        self._on_engine_changed()

    def _save_api_key(self):
        """Save the API key to settings."""
        key = self._api_key_edit.text().strip()
        if not key:
            return

        engine = self._engine_combo.currentData()
        self._translator.set_api_key(engine, key)

        # Save to settings
        if engine == TranslationEngine.DEEPL:
            self._settings.set_deepl_api_key(key)
        elif engine == TranslationEngine.GPT:
            self._settings.set_openai_api_key(key)

        self._settings.sync()
        QMessageBox.information(self, "API Key Saved", "API key has been saved.")

    def _on_engine_changed(self):
        """Update the API key field when engine changes."""
        engine = self._engine_combo.currentData()

        # Update API key field
        key = self._translator.get_api_key(engine)
        self._api_key_edit.setText(key)

        # Show/hide API key fields based on engine
        needs_api = engine != TranslationEngine.GOOGLE
        self._api_key_edit.setVisible(needs_api)
        self._save_key_btn.setVisible(needs_api)

    def _update_ui_state(self, translating: bool = False):
        """Update UI state based on translation progress."""
        self._source_combo.setEnabled(not translating)
        self._target_combo.setEnabled(not translating)
        self._engine_combo.setEnabled(not translating)
        self._api_key_edit.setEnabled(not translating)
        self._save_key_btn.setEnabled(not translating)
        self._new_track_radio.setEnabled(not translating)
        self._replace_radio.setEnabled(not translating)

        if translating:
            self._translate_btn.setText("Cancel Translation")
            self._translate_btn.clicked.disconnect()
            self._translate_btn.clicked.connect(self._on_cancel_translation)
            self._cancel_btn.setEnabled(False)
        else:
            self._translate_btn.setText("Translate")
            try:
                self._translate_btn.clicked.disconnect()
            except:
                pass
            self._translate_btn.clicked.connect(self._on_translate)
            self._cancel_btn.setEnabled(True)

    def _on_translate(self):
        """Start the translation process."""
        source_lang = self._source_combo.currentText()
        target_lang = self._target_combo.currentText()

        if source_lang == target_lang:
            QMessageBox.warning(
                self, "Invalid Language Selection",
                "Source and target languages must be different."
            )
            return

        engine = self._engine_combo.currentData()

        # Check if API key is needed and provided
        if engine != TranslationEngine.GOOGLE:
            key = self._translator.get_api_key(engine)
            if not key:
                QMessageBox.warning(
                    self, "API Key Required",
                    f"Please enter an API key for {self._engine_combo.currentText()}."
                )
                self._api_key_edit.setFocus()
                return

        # Update UI
        self._update_ui_state(True)
        self._progress_bar.setValue(0)
        self._status_label.setText(f"Translating from {source_lang} to {target_lang}...")

        # Start translation in background
        self._translation_complete = False
        self._result_track = self._translator.translate_track(
            self._track, source_lang, target_lang, engine, self._on_progress
        )

    def _on_progress(self, current: int, total: int):
        """Update progress bar and status label."""
        percent = int(current * 100 / max(1, total))
        self._progress_bar.setValue(percent)

        if current >= total:
            self._status_label.setText("Translation completed!")
            self._translation_complete = True

            # Update UI
            self._update_ui_state(False)

            # Update preview with sample
            self._update_preview()

            # If successful, enable OK button to accept the dialog
            if self._result_track:
                self._translate_btn.setText("Apply Translation")
                self._translate_btn.clicked.disconnect()
                self._translate_btn.clicked.connect(self.accept)

    def _update_preview(self):
        """Show a preview of the translated subtitles."""
        if not self._result_track or len(self._result_track) == 0:
            return

        # Show at most 5 samples
        preview = "Translation Preview:\n\n"

        for i, seg in enumerate(self._result_track):
            if i >= 5:
                preview += "...\n"
                break

            preview += f"{i+1}. {seg.text}\n"

        self._preview_text.setText(preview)

    def _on_cancel_translation(self):
        """Cancel the ongoing translation."""
        self._translator.cancel_translation()
        self._status_label.setText("Translation canceled.")
        self._update_ui_state(False)

    def _on_cancel(self):
        """Cancel the dialog."""
        if self._translation_complete:
            result = QMessageBox.question(
                self,
                "Discard Translation",
                "Translation is complete. Are you sure you want to discard it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if result == QMessageBox.StandardButton.No:
                return

        self.reject()

    def _on_error(self, error_msg: str):
        """Handle translation error."""
        QMessageBox.critical(self, "Translation Error", error_msg)
        self._status_label.setText(f"Error: {error_msg}")
        self._update_ui_state(False)

    def get_result_track(self) -> Optional[SubtitleTrack]:
        """Get the translated subtitle track."""
        return self._result_track

    def is_new_track(self) -> bool:
        """Check if the translation should be added as a new track."""
        return self._new_track_radio.isChecked()