"""Tests for TTSDialog default provider behavior."""

from __future__ import annotations

from src.ui.dialogs import tts_dialog as tts_dialog_module
from src.utils.config import TTSEngine


class _FakeSettingsManager:
    def __init__(self, provider_id: str):
        self._provider_id = provider_id

    def get_tts_default_provider(self) -> str:
        return self._provider_id

    def get_elevenlabs_api_key(self) -> str:
        return ""


def test_tts_dialog_uses_preferred_provider_as_default(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(
        tts_dialog_module,
        "SettingsManager",
        lambda: _FakeSettingsManager(TTSEngine.ELEVENLABS),
    )
    dialog = tts_dialog_module.TTSDialog(video_audio_path=None, parent=None)
    qtbot.addWidget(dialog)
    assert dialog._engine_combo.currentData() == TTSEngine.ELEVENLABS


def test_tts_dialog_engine_is_still_user_changeable(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(
        tts_dialog_module,
        "SettingsManager",
        lambda: _FakeSettingsManager(TTSEngine.ELEVENLABS),
    )
    dialog = tts_dialog_module.TTSDialog(video_audio_path=None, parent=None)
    qtbot.addWidget(dialog)

    idx = dialog._engine_combo.findData(TTSEngine.EDGE_TTS)
    dialog._engine_combo.setCurrentIndex(idx)
    assert dialog._engine_combo.currentData() == TTSEngine.EDGE_TTS
