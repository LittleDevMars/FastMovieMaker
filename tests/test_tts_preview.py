"""Tests for TTS preview functionality."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import QMediaPlayer

from src.ui.dialogs.tts_dialog import TTSDialog, TTSPreviewWorker
from src.utils.config import TTSEngine


class TestTTSPreviewWorker:
    """Test TTSPreviewWorker logic."""

    @patch("src.ui.dialogs.tts_dialog.TTSService.generate_speech")
    def test_worker_run_edge_tts(self, mock_generate):
        """Test worker runs Edge-TTS generation."""
        worker = TTSPreviewWorker(
            engine=TTSEngine.EDGE_TTS,
            text="Hello",
            voice="en-US-GuyNeural",
            rate="+0%",
        )

        # Capture signal
        results = []
        worker.finished.connect(results.append)

        worker.run()

        assert len(results) == 1
        assert "tts_preview_" in results[0]
        assert results[0].endswith(".mp3")
        mock_generate.assert_called_once()

    @patch("src.services.elevenlabs_tts_service.ElevenLabsTTSService.generate_speech")
    def test_worker_run_elevenlabs(self, mock_generate):
        """Test worker runs ElevenLabs generation."""
        worker = TTSPreviewWorker(
            engine=TTSEngine.ELEVENLABS,
            text="Hello",
            voice="voice_id",
            rate="1.0",
            api_key="test_key",
        )

        results = []
        worker.finished.connect(results.append)

        worker.run()

        assert len(results) == 1
        mock_generate.assert_called_once()


class TestTTSDialogPreview:
    """Test TTSDialog preview UI interaction."""

    @pytest.fixture
    def dialog(self, qtbot):
        dialog = TTSDialog(video_audio_path=None, parent=None)
        qtbot.addWidget(dialog)
        return dialog

    def test_preview_button_starts_worker(self, dialog, qtbot):
        """Test clicking preview button starts the worker."""
        dialog._script_edit.setPlainText("Test script")
        
        with patch("src.ui.dialogs.tts_dialog.TTSPreviewWorker") as MockWorker:
            mock_instance = MockWorker.return_value
            mock_instance.finished = MagicMock()
            mock_instance.error = MagicMock()
            
            qtbot.mouseClick(dialog._preview_btn, Qt.MouseButton.LeftButton)
            
            # Worker should be created and started
            MockWorker.assert_called_once()
            # Button should be disabled during generation
            assert not dialog._preview_btn.isEnabled()
            assert "Generating" in dialog._status_label.text()

    def test_preview_ready_plays_audio(self, dialog, qtbot):
        """Test that when preview is ready, audio plays."""
        # Mock player
        dialog._player = MagicMock()
        dialog._player.playbackState.return_value = QMediaPlayer.PlaybackState.StoppedState
        
        # Simulate worker finished
        fake_path = "/tmp/preview.mp3"
        dialog._on_preview_ready(fake_path)
        
        # Check UI update
        assert dialog._preview_btn.isEnabled()
        assert dialog._preview_btn.text() == "Stop Preview"
        assert "Playing" in dialog._status_label.text()
        
        # Check player call
        dialog._player.setSource.assert_called_with(QUrl.fromLocalFile(fake_path))
        dialog._player.play.assert_called_once()