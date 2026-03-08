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


def test_tts_default_provider_non_builtin_roundtrip() -> None:
    mgr = _make_manager()
    mgr.set_tts_default_provider("plugin.provider")
    assert mgr.get_tts_default_provider() == "plugin.provider"
    mgr._settings.setValue("tts/default_provider", "plugin.provider")
    assert mgr.get_tts_default_provider() == "plugin.provider"


def test_tts_default_provider_empty_fallback_to_edge() -> None:
    mgr = _make_manager()
    mgr.set_tts_default_provider("")
    assert mgr.get_tts_default_provider() == TTSEngine.EDGE_TTS
    mgr._settings.setValue("tts/default_provider", "")
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


def test_project_sync_root_roundtrip() -> None:
    mgr = _make_manager()
    assert mgr.get_project_sync_root_path() is None
    mgr.set_project_sync_root_path("/tmp/fmm_sync")
    assert mgr.get_project_sync_root_path() == "/tmp/fmm_sync"
    mgr.set_project_sync_root_path("")
    assert mgr.get_project_sync_root_path() is None


def test_project_sync_state_roundtrip_and_normalize() -> None:
    mgr = _make_manager()
    state = {
        "demo.fmm.json": {
            "last_hash": "abc123",
            "updated_at": "2026-03-08T00:00:00+00:00",
        }
    }
    mgr.set_project_sync_state(state)
    assert mgr.get_project_sync_state() == state

    mgr._settings.setValue(
        "project_sync/state",
        '{"demo.fmm.json":{"last_hash":"h1","updated_at":"u1"},"":{"last_hash":"x"}}',
    )
    assert mgr.get_project_sync_state() == {
        "demo.fmm.json": {
            "last_hash": "h1",
            "updated_at": "u1",
        }
    }

    mgr._settings.setValue("project_sync/state", "not-json")
    assert mgr.get_project_sync_state() == {}
