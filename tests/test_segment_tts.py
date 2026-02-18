"""Tests for per-segment TTS settings functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt

from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.services.project_io import _dict_to_segment, _segment_to_dict
from src.ui.commands import EditSegmentTTSCommand
from src.ui.dialogs.tts_dialog import TTSDialog


class TestSegmentTTSModel:
    """Test SubtitleSegment model updates for TTS settings."""

    def test_segment_fields_defaults(self):
        seg = SubtitleSegment(0, 1000, "Test")
        assert seg.voice is None
        assert seg.speed is None

    def test_segment_fields_init(self):
        seg = SubtitleSegment(0, 1000, "Test", voice="ko-KR-SunHiNeural", speed=1.2)
        assert seg.voice == "ko-KR-SunHiNeural"
        assert seg.speed == 1.2

    def test_segment_serialization(self):
        seg = SubtitleSegment(0, 1000, "Test", voice="voice_id", speed=0.8)
        d = _segment_to_dict(seg)
        assert d["voice"] == "voice_id"
        assert d["speed"] == 0.8

        restored = _dict_to_segment(d)
        assert restored.voice == "voice_id"
        assert restored.speed == 0.8


class TestEditSegmentTTSCommand:
    """Test Undo/Redo for segment TTS settings."""

    def test_redo_undo(self):
        track = SubtitleTrack()
        seg = SubtitleSegment(0, 1000, "Test", audio_file="old.mp3", voice="old_voice", speed=1.0)
        track.add_segment(seg)

        cmd = EditSegmentTTSCommand(
            track, 0, seg,
            new_audio_file="new.mp3",
            new_voice="new_voice",
            new_speed=1.5
        )

        # Redo
        cmd.redo()
        assert seg.audio_file == "new.mp3"
        assert seg.voice == "new_voice"
        assert seg.speed == 1.5

        # Undo
        cmd.undo()
        assert seg.audio_file == "old.mp3"
        assert seg.voice == "old_voice"
        assert seg.speed == 1.0


class TestTTSDialogSegmentMode:
    """Test TTSDialog in segment editing mode."""

    def test_init_segment_mode(self, qtbot):
        dialog = TTSDialog(
            segment_mode=True,
            initial_text="Segment Text",
            initial_voice="ko-KR-InJoonNeural",
            initial_speed=1.2,
            parent=None
        )
        qtbot.addWidget(dialog)

        # Check UI state
        assert dialog.windowTitle() == "Edit Segment TTS"
        assert dialog._script_edit.toPlainText() == "Segment Text"
        assert dialog._script_edit.isReadOnly()
        assert dialog._speed_spin.value() == 1.2
        
        # Strategy combo should be disabled in segment mode
        assert not dialog._strategy_combo.isEnabled()

    def test_get_segment_settings(self, qtbot):
        dialog = TTSDialog(segment_mode=True, parent=None)
        qtbot.addWidget(dialog)

        # Simulate user change
        dialog._speed_spin.setValue(1.5)
        # Mock voice selection (add item first to ensure it exists)
        dialog._voice_combo.addItem("Test Voice", "test_voice_id")
        idx = dialog._voice_combo.findData("test_voice_id")
        dialog._voice_combo.setCurrentIndex(idx)

        voice, speed = dialog.get_segment_settings()
        assert voice == "test_voice_id"
        assert speed == 1.5

    def test_generate_button_behavior_in_segment_mode(self, qtbot):
        """In segment mode, Generate button should trigger worker with script."""
        dialog = TTSDialog(segment_mode=True, initial_text="Hello", parent=None)
        qtbot.addWidget(dialog)

        with patch("src.ui.dialogs.tts_dialog.TTSWorker") as MockWorker:
            mock_worker_instance = MockWorker.return_value
            
            qtbot.mouseClick(dialog._generate_btn, Qt.MouseButton.LeftButton)
            
            MockWorker.assert_called_once()
            call_kwargs = MockWorker.call_args[1]
            assert call_kwargs["script"] == "Hello"


class TestSubtitleControllerSegmentTTS:
    """Test controller integration."""

    def test_on_edit_segment_tts_opens_dialog_and_pushes_command(self):
        from src.ui.controllers.subtitle_controller import SubtitleController
        from src.ui.controllers.app_context import AppContext

        ctx = MagicMock(spec=AppContext)
        ctx.project = MagicMock()
        ctx.project.has_subtitles = True
        track = SubtitleTrack()
        seg = SubtitleSegment(0, 1000, "Test")
        track.add_segment(seg)
        ctx.project.subtitle_track = track
        ctx.window = MagicMock()
        ctx.undo_stack = MagicMock()

        ctrl = SubtitleController(ctx)

        with patch("src.ui.dialogs.tts_dialog.TTSDialog") as MockDialog:
            mock_dlg = MockDialog.return_value
            mock_dlg.exec.return_value = 1  # Accepted

            # Mock result from dialog
            mock_result_track = SubtitleTrack()
            mock_result_track.add_segment(SubtitleSegment(0, 1000, "Test", audio_file="/tmp/out.mp3"))
            mock_dlg.result_track.return_value = mock_result_track
            mock_dlg.get_segment_settings.return_value = ("voice_id", 1.5)

            ctrl.on_edit_segment_tts(0)

            # Verify dialog init args
            MockDialog.assert_called_once()
            call_kwargs = MockDialog.call_args[1]
            assert call_kwargs["segment_mode"] is True
            assert call_kwargs["initial_text"] == "Test"

            # Verify command pushed
            ctx.undo_stack.push.assert_called_once()
            # Check if pushed object is EditSegmentTTSCommand
            cmd = ctx.undo_stack.push.call_args[0][0]
            assert isinstance(cmd, EditSegmentTTSCommand)