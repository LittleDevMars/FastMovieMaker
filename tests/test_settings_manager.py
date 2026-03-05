"""SettingsManager tests for TTS provider defaults."""

from __future__ import annotations

from src.services.settings_manager import SettingsManager
from src.utils.config import TTSEngine


class _FakeQSettings:
    def __init__(self):
        self._data: dict[str, str] = {}

    def value(self, key: str, default, type_=None):
        return self._data.get(key, default)

    def setValue(self, key: str, value) -> None:
        self._data[key] = value


def _make_manager() -> SettingsManager:
    mgr = SettingsManager.__new__(SettingsManager)
    mgr._settings = _FakeQSettings()
    return mgr


def test_tts_default_provider_roundtrip() -> None:
    mgr = _make_manager()
    assert mgr.get_tts_default_provider() == TTSEngine.EDGE_TTS
    mgr.set_tts_default_provider(TTSEngine.ELEVENLABS)
    assert mgr.get_tts_default_provider() == TTSEngine.ELEVENLABS


def test_tts_default_provider_invalid_fallback() -> None:
    mgr = _make_manager()
    mgr.set_tts_default_provider("invalid-provider")
    assert mgr.get_tts_default_provider() == TTSEngine.EDGE_TTS
    mgr._settings.setValue("tts/default_provider", "invalid-provider")
    assert mgr.get_tts_default_provider() == TTSEngine.EDGE_TTS


def test_tts_plugin_paths_roundtrip() -> None:
    mgr = _make_manager()
    mgr.set_tts_plugin_paths(["/a/plugin_one.py", "/b/plugin_two.py"])
    assert mgr.get_tts_plugin_paths() == ["/a/plugin_one.py", "/b/plugin_two.py"]


def test_tts_plugin_paths_normalize_invalid_types() -> None:
    mgr = _make_manager()
    mgr._settings.setValue("tts/plugin_paths", 12345)
    assert mgr.get_tts_plugin_paths() == []
    mgr._settings.setValue("tts/plugin_paths", ["/x.py", "", "  ", "/x.py", "/y.py"])
    assert mgr.get_tts_plugin_paths() == ["/x.py", "/y.py"]
