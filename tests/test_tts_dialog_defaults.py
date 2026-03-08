"""Tests for TTSDialog default provider behavior."""

from __future__ import annotations

from types import SimpleNamespace

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


def test_tts_dialog_includes_plugin_provider_from_registry(qtbot, monkeypatch) -> None:
    providers = {
        TTSEngine.EDGE_TTS: SimpleNamespace(
            provider_id=TTSEngine.EDGE_TTS,
            display_name="Edge-TTS (Free)",
            list_voices=lambda language: [("Edge Voice", "edge_voice")],
        ),
        "plugin.demo": SimpleNamespace(
            provider_id="plugin.demo",
            display_name="Plugin Demo",
            list_voices=lambda language: [("Plugin Voice", "plugin_voice")],
        ),
    }

    monkeypatch.setattr(
        tts_dialog_module,
        "SettingsManager",
        lambda: _FakeSettingsManager("plugin.demo"),
    )
    monkeypatch.setattr(tts_dialog_module, "get_all_providers", lambda: providers)
    monkeypatch.setattr(tts_dialog_module, "get_provider", lambda provider_id: providers.get(provider_id))

    dialog = tts_dialog_module.TTSDialog(video_audio_path=None, parent=None)
    qtbot.addWidget(dialog)

    assert dialog._engine_combo.findData("plugin.demo") >= 0
    assert dialog._engine_combo.currentData() == "plugin.demo"
