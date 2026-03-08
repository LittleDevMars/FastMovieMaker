"""UI tests for default TTS provider preference."""

from __future__ import annotations

from types import SimpleNamespace

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
            "tts_plugin_paths": [],
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
    monkeypatch.setattr(
        pref_module,
        "get_all_providers",
        lambda: {
            TTSEngine.EDGE_TTS: SimpleNamespace(
                provider_id=TTSEngine.EDGE_TTS,
                display_name="Edge-TTS (Free)",
            ),
            TTSEngine.ELEVENLABS: SimpleNamespace(
                provider_id=TTSEngine.ELEVENLABS,
                display_name="ElevenLabs (Premium)",
            ),
        },
    )
    monkeypatch.setattr(pref_module, "reload_provider_registry", lambda: None)
    monkeypatch.setattr(pref_module, "get_provider_load_errors", lambda: [])

    dialog = pref_module.PreferencesDialog()
    qtbot.addWidget(dialog)
    idx = dialog._tts_provider.findData(TTSEngine.ELEVENLABS)
    dialog._tts_provider.setCurrentIndex(idx)
    dialog._save_and_accept()

    assert shared_settings.get_tts_default_provider() == TTSEngine.ELEVENLABS

    dialog2 = pref_module.PreferencesDialog()
    qtbot.addWidget(dialog2)
    assert dialog2._tts_provider.currentData() == TTSEngine.ELEVENLABS


def test_preferences_add_plugin_path_avoids_duplicates(qtbot, monkeypatch) -> None:
    shared_settings = _FakeSettingsManager()
    monkeypatch.setattr(pref_module, "SettingsManager", lambda: shared_settings)
    monkeypatch.setattr(
        pref_module,
        "get_all_providers",
        lambda: {
            TTSEngine.EDGE_TTS: SimpleNamespace(
                provider_id=TTSEngine.EDGE_TTS,
                display_name="Edge-TTS (Free)",
            ),
            TTSEngine.ELEVENLABS: SimpleNamespace(
                provider_id=TTSEngine.ELEVENLABS,
                display_name="ElevenLabs (Premium)",
            ),
        },
    )
    monkeypatch.setattr(pref_module, "reload_provider_registry", lambda: None)
    monkeypatch.setattr(pref_module, "get_provider_load_errors", lambda: [])

    selected_path = "/tmp/fmm_plugin.py"
    monkeypatch.setattr(
        pref_module.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (selected_path, "Python Files (*.py)"),
    )

    dialog = pref_module.PreferencesDialog()
    qtbot.addWidget(dialog)
    dialog._add_tts_plugin_path()
    dialog._add_tts_plugin_path()

    assert dialog._tts_plugin_paths.count() == 1
    assert dialog._tts_plugin_paths.item(0).text() == selected_path


def test_preferences_save_plugin_paths_reload_and_error_status(qtbot, monkeypatch) -> None:
    shared_settings = _FakeSettingsManager()
    monkeypatch.setattr(pref_module, "SettingsManager", lambda: shared_settings)
    monkeypatch.setattr(
        pref_module,
        "get_all_providers",
        lambda: {
            TTSEngine.EDGE_TTS: SimpleNamespace(
                provider_id=TTSEngine.EDGE_TTS,
                display_name="Edge-TTS (Free)",
            ),
            "plugin.demo": SimpleNamespace(
                provider_id="plugin.demo",
                display_name="Plugin Demo",
            ),
        },
    )

    called = {"reload": 0}

    def _reload() -> None:
        called["reload"] += 1

    monkeypatch.setattr(pref_module, "reload_provider_registry", _reload)
    monkeypatch.setattr(
        pref_module,
        "get_provider_load_errors",
        lambda: ["/tmp/fmm_plugin.py: register_tts_providers() is missing"],
    )

    dialog = pref_module.PreferencesDialog()
    qtbot.addWidget(dialog)
    dialog._tts_plugin_paths.addItem("/tmp/fmm_plugin.py")
    dialog._save_and_accept()

    assert shared_settings.get_tts_plugin_paths() == ["/tmp/fmm_plugin.py"]
    assert called["reload"] == 1
    assert "register_tts_providers() is missing" in dialog._tts_plugin_status.text()


def test_preferences_includes_plugin_provider_in_default_combo(qtbot, monkeypatch) -> None:
    shared_settings = _FakeSettingsManager()
    shared_settings.set_tts_default_provider("plugin.demo")
    monkeypatch.setattr(pref_module, "SettingsManager", lambda: shared_settings)
    monkeypatch.setattr(
        pref_module,
        "get_all_providers",
        lambda: {
            TTSEngine.EDGE_TTS: SimpleNamespace(
                provider_id=TTSEngine.EDGE_TTS,
                display_name="Edge-TTS (Free)",
            ),
            "plugin.demo": SimpleNamespace(
                provider_id="plugin.demo",
                display_name="Plugin Demo",
            ),
        },
    )
    monkeypatch.setattr(pref_module, "reload_provider_registry", lambda: None)
    monkeypatch.setattr(pref_module, "get_provider_load_errors", lambda: [])

    dialog = pref_module.PreferencesDialog()
    qtbot.addWidget(dialog)

    assert dialog._tts_provider.findData("plugin.demo") >= 0
    assert dialog._tts_provider.currentData() == "plugin.demo"
