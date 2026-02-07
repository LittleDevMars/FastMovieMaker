"""GUI automation tests for TTS dialog using pytest-qt."""

import pytest
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from src.ui.dialogs.tts_dialog import TTSDialog
from src.services.text_splitter import SplitStrategy


@pytest.fixture
def tts_dialog(qtbot):
    """Create a TTS dialog for testing."""
    dialog = TTSDialog(video_audio_path=None, parent=None)
    qtbot.addWidget(dialog)
    return dialog


def test_tts_dialog_opens(tts_dialog, qtbot):
    """Test that TTS dialog opens without errors."""
    assert tts_dialog is not None
    assert tts_dialog.windowTitle() == "Generate Speech (TTS)"


def test_tts_dialog_has_required_widgets(tts_dialog, qtbot):
    """Test that all required widgets are present."""
    # Script input
    assert tts_dialog._script_edit is not None
    assert tts_dialog._script_edit.placeholderText() != ""

    # Language selector
    assert tts_dialog._lang_combo is not None
    assert tts_dialog._lang_combo.count() >= 2  # Korean, English

    # Voice selector
    assert tts_dialog._voice_combo is not None
    assert tts_dialog._voice_combo.count() > 0

    # Speed control
    assert tts_dialog._speed_spin is not None
    assert tts_dialog._speed_spin.minimum() == 0.5
    assert tts_dialog._speed_spin.maximum() == 2.0

    # Strategy selector
    assert tts_dialog._strategy_combo is not None
    assert tts_dialog._strategy_combo.count() == 3  # SENTENCE, NEWLINE, FIXED_LENGTH

    # Buttons
    assert tts_dialog._generate_btn is not None
    assert tts_dialog._cancel_btn is not None

    # Progress bar (hidden initially)
    assert tts_dialog._progress_bar is not None
    assert not tts_dialog._progress_bar.isVisible()


def test_tts_dialog_language_change(tts_dialog, qtbot):
    """Test that changing language updates voice list."""
    # Get initial voice count
    initial_voice = tts_dialog._voice_combo.currentText()

    # Change language
    tts_dialog._lang_combo.setCurrentText("English")
    qtbot.wait(100)  # Wait for signal processing

    # Voice should have changed
    new_voice = tts_dialog._voice_combo.currentText()
    assert new_voice != initial_voice
    assert "Female" in new_voice or "Male" in new_voice


def test_tts_dialog_script_input(tts_dialog, qtbot):
    """Test script input functionality."""
    test_script = "안녕하세요.\n테스트입니다."

    # Set text
    tts_dialog._script_edit.setPlainText(test_script)

    # Verify text was set
    assert tts_dialog._script_edit.toPlainText() == test_script


def test_tts_dialog_empty_script_warning(tts_dialog, qtbot):
    """Test that empty script shows warning."""
    # Clear script
    tts_dialog._script_edit.clear()

    # Mock QMessageBox to prevent actual dialog
    from unittest.mock import patch
    with patch('src.ui.dialogs.tts_dialog.QMessageBox.warning') as mock_warning:
        # Click generate with empty script
        qtbot.mouseClick(tts_dialog._generate_btn, Qt.MouseButton.LeftButton)

        # Should show warning
        assert mock_warning.called
        assert "Empty Script" in str(mock_warning.call_args)


def test_tts_dialog_settings_persistence(tts_dialog, qtbot):
    """Test that settings can be changed and retrieved."""
    # Set speed
    tts_dialog._speed_spin.setValue(1.5)
    assert tts_dialog._speed_spin.value() == 1.5

    # Set strategy
    tts_dialog._strategy_combo.setCurrentIndex(1)  # NEWLINE
    assert tts_dialog._strategy_combo.currentData() == SplitStrategy.NEWLINE


def test_tts_dialog_cancel_button(tts_dialog, qtbot):
    """Test cancel button functionality."""
    # Click cancel
    with qtbot.waitSignal(tts_dialog.rejected, timeout=1000):
        qtbot.mouseClick(tts_dialog._cancel_btn, Qt.MouseButton.LeftButton)


def test_tts_dialog_without_video(qtbot):
    """Test TTS dialog works without video (no volume controls)."""
    dialog = TTSDialog(video_audio_path=None, parent=None)
    qtbot.addWidget(dialog)

    # Volume controls should not exist
    assert dialog._bg_volume_spin is None
    assert dialog._tts_volume_spin is None


def test_tts_dialog_with_video(qtbot):
    """Test TTS dialog with video shows volume controls."""
    # Use a fake path (doesn't need to exist for UI test)
    fake_video = Path("/fake/video.mp4")
    dialog = TTSDialog(video_audio_path=fake_video, parent=None)
    qtbot.addWidget(dialog)

    # Volume controls should exist
    assert dialog._bg_volume_spin is not None
    assert dialog._tts_volume_spin is not None

    # Check default values
    assert dialog._bg_volume_spin.value() == 0.5
    assert dialog._tts_volume_spin.value() == 1.0


@pytest.mark.slow
def test_tts_dialog_generate_button_state(tts_dialog, qtbot):
    """Test that generate button is disabled during generation."""
    # Set valid script
    tts_dialog._script_edit.setPlainText("Test script.")

    # Mock the worker to prevent actual TTS generation
    from unittest.mock import patch, MagicMock

    with patch('src.ui.dialogs.tts_dialog.TTSWorker') as MockWorker:
        # Create mock worker
        mock_worker = MagicMock()
        MockWorker.return_value = mock_worker

        # Click generate
        qtbot.mouseClick(tts_dialog._generate_btn, Qt.MouseButton.LeftButton)
        qtbot.wait(100)

        # Generate button should be disabled
        assert not tts_dialog._generate_btn.isEnabled()

        # Progress bar should be visible
        assert tts_dialog._progress_bar.isVisible()


if __name__ == "__main__":
    # Allow running this test file directly
    pytest.main([__file__, "-v"])
