"""UI tests for default TTS provider preference."""

from __future__ import annotations

from src.ui.dialogs import preferences_dialog as pref_module
from src.utils.config import TTSEngine


class _FakeSettingsManager:
    def __init__(self) -> None:
        self._values: dict[str, object] = {
            "autosave_interval": 30,
            "autosave_idle_timeout": 5,
            "recent_files_max": 10,
            "default_language": "Korean",
            "theme": "dark",
            "ui_language": "ko",
            "default_subtitle_duration": 2000,
            "snap_tolerance": 10,
            "frame_seek_fps": 30,
            "audio_speed_pitch_shift": False,
            "frame_cache_quality": 5,
            "ffmpeg_path": None,
            "whisper_cache_dir": None,
            "tts_default_provider": TTSEngine.EDGE_TTS,
            "deepl_api_key": "",
            "openai_api_key": "",
            "elevenlabs_api_key": "",
        }
        self._shortcuts: dict[str, str] = {}

    def get_shortcut(self, action: str) -> str:
        return self._shortcuts.get(action, "")

    def set_shortcut(self, action: str, key: str) -> None:
        self._shortcuts[action] = key

    def sync(self) -> None:
        pass

    def __getattr__(self, name: str):
        if name.startswith("get_"):
            key = name[len("get_"):]
            return lambda: self._values.get(key)
        if name.startswith("set_"):
            key = name[len("set_"):]
            return lambda value: self._values.__setitem__(key, value)
        raise AttributeError(name)


def test_preferences_saves_and_loads_default_tts_provider(qtbot, monkeypatch) -> None:
    shared_settings = _FakeSettingsManager()
    monkeypatch.setattr(pref_module, "SettingsManager", lambda: shared_settings)

    dialog = pref_module.PreferencesDialog()
    qtbot.addWidget(dialog)
    idx = dialog._tts_provider.findData(TTSEngine.ELEVENLABS)
    dialog._tts_provider.setCurrentIndex(idx)
    dialog._save_and_accept()

    assert shared_settings.get_tts_default_provider() == TTSEngine.ELEVENLABS

    dialog2 = pref_module.PreferencesDialog()
    qtbot.addWidget(dialog2)
    assert dialog2._tts_provider.currentData() == TTSEngine.ELEVENLABS
