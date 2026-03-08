"""Tests for TTS provider registry (builtin + plugin providers)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.services.tts_provider import TTSRequestError, TTSRequestErrorCode
from src.services import tts_provider_registry as registry
from src.utils.config import TTSEngine


class _FakeSettingsManager:
    def __init__(self, plugin_paths: list[str] | None = None):
        self._plugin_paths = plugin_paths or []

    def get_tts_plugin_paths(self) -> list[str]:
        return list(self._plugin_paths)

    def get_elevenlabs_api_key(self) -> str:
        return ""


def _write_valid_plugin(path: Path, provider_id: str = "plugin_demo") -> None:
    path.write_text(
        f"""
class DemoProvider:
    provider_id = "{provider_id}"
    display_name = "Demo"
    def requires_api_key(self): return False
    def list_voices(self, language): return [("Demo", "demo_voice")]
    def synthesize(self, text, voice, speed, output_path, *, language=None): return None
    async def generate_segments(self, segments, voice, speed, output_dir, on_progress=None): return []

def register_tts_providers():
    return [DemoProvider()]
""".strip(),
        encoding="utf-8",
    )


def test_builtin_providers_include_edge_and_elevenlabs(monkeypatch) -> None:
    monkeypatch.setattr(registry, "SettingsManager", lambda: _FakeSettingsManager([]))
    monkeypatch.delenv("FMM_TTS_PLUGIN_PATHS", raising=False)
    registry.reload_provider_registry()

    providers = registry.get_builtin_providers()
    assert TTSEngine.EDGE_TTS in providers
    assert TTSEngine.ELEVENLABS in providers
    assert providers[TTSEngine.EDGE_TTS].provider_id == TTSEngine.EDGE_TTS
    assert providers[TTSEngine.ELEVENLABS].provider_id == TTSEngine.ELEVENLABS


def test_get_provider_unknown_returns_none(monkeypatch) -> None:
    monkeypatch.setattr(registry, "SettingsManager", lambda: _FakeSettingsManager([]))
    monkeypatch.delenv("FMM_TTS_PLUGIN_PATHS", raising=False)
    registry.reload_provider_registry()
    assert registry.get_provider("unknown_provider") is None


def test_provider_api_key_requirements(monkeypatch) -> None:
    monkeypatch.setattr(registry, "SettingsManager", lambda: _FakeSettingsManager([]))
    monkeypatch.delenv("FMM_TTS_PLUGIN_PATHS", raising=False)
    registry.reload_provider_registry()

    edge = registry.get_provider(TTSEngine.EDGE_TTS)
    elevenlabs = registry.get_provider(TTSEngine.ELEVENLABS)
    assert edge is not None and not edge.requires_api_key()
    assert elevenlabs is not None and elevenlabs.requires_api_key()


def test_registry_loads_plugin_provider(monkeypatch, tmp_path) -> None:
    plugin_path = tmp_path / "plugin_demo.py"
    _write_valid_plugin(plugin_path, provider_id="plugin_demo")

    monkeypatch.setattr(
        registry,
        "SettingsManager",
        lambda: _FakeSettingsManager([str(plugin_path)]),
    )
    monkeypatch.delenv("FMM_TTS_PLUGIN_PATHS", raising=False)
    registry.reload_provider_registry()

    provider = registry.get_provider("plugin_demo")
    assert provider is not None
    assert provider.provider_id == "plugin_demo"
    assert registry.get_provider_load_errors() == []


def test_registry_reloads_after_env_plugin_change(monkeypatch, tmp_path) -> None:
    plugin_path = tmp_path / "env_plugin.py"
    _write_valid_plugin(plugin_path, provider_id="env_provider")

    monkeypatch.setattr(registry, "SettingsManager", lambda: _FakeSettingsManager([]))
    monkeypatch.delenv("FMM_TTS_PLUGIN_PATHS", raising=False)
    registry.reload_provider_registry()
    assert registry.get_provider("env_provider") is None

    monkeypatch.setenv("FMM_TTS_PLUGIN_PATHS", str(plugin_path))
    registry.reload_provider_registry()
    assert registry.get_provider("env_provider") is not None


def test_registry_collects_plugin_load_errors(monkeypatch, tmp_path) -> None:
    bad_plugin = tmp_path / "bad_plugin.py"
    bad_plugin.write_text("VALUE = 1\n", encoding="utf-8")

    monkeypatch.setattr(
        registry,
        "SettingsManager",
        lambda: _FakeSettingsManager([str(bad_plugin)]),
    )
    monkeypatch.delenv("FMM_TTS_PLUGIN_PATHS", raising=False)
    registry.reload_provider_registry()

    assert registry.get_provider(TTSEngine.EDGE_TTS) is not None
    errors = registry.get_provider_load_errors()
    assert errors
    assert "register_tts_providers" in errors[0]


@patch("src.services.tts_provider_registry.TTSService.generate_segments", new_callable=AsyncMock)
def test_edge_provider_generate_segments_delegates(mock_generate_segments, monkeypatch) -> None:
    monkeypatch.setattr(registry, "SettingsManager", lambda: _FakeSettingsManager([]))
    monkeypatch.delenv("FMM_TTS_PLUGIN_PATHS", raising=False)
    registry.reload_provider_registry()

    edge = registry.get_provider(TTSEngine.EDGE_TTS)
    assert edge is not None
    mock_generate_segments.return_value = []
    result = asyncio.run(
        edge.generate_segments(
            segments=[("hello", 0)],
            voice="en-US-GuyNeural",
            speed=1.0,
            output_dir=Path("/tmp"),
        )
    )
    assert result == []
    mock_generate_segments.assert_called_once()


@patch("src.services.tts_provider_registry.ElevenLabsTTSService.generate_segments")
def test_elevenlabs_provider_generate_segments_delegates(mock_generate_segments, monkeypatch) -> None:
    monkeypatch.setattr(registry, "SettingsManager", lambda: _FakeSettingsManager([]))
    monkeypatch.delenv("FMM_TTS_PLUGIN_PATHS", raising=False)
    registry.reload_provider_registry()

    elevenlabs = registry.get_provider(TTSEngine.ELEVENLABS)
    assert elevenlabs is not None
    mock_generate_segments.return_value = []
    result = asyncio.run(
        elevenlabs.generate_segments(
            segments=[("hello", 0)],
            voice="voice_id",
            speed=1.0,
            output_dir=Path("/tmp"),
        )
    )
    assert result == []
    mock_generate_segments.assert_called_once()


def test_edge_provider_generate_segments_validates_speed(monkeypatch) -> None:
    monkeypatch.setattr(registry, "SettingsManager", lambda: _FakeSettingsManager([]))
    monkeypatch.delenv("FMM_TTS_PLUGIN_PATHS", raising=False)
    registry.reload_provider_registry()

    edge = registry.get_provider(TTSEngine.EDGE_TTS)
    assert edge is not None
    try:
        asyncio.run(
            edge.generate_segments(
                segments=[("hello", 0)],
                voice="en-US-GuyNeural",
                speed=0.0,
                output_dir=Path("/tmp"),
            )
        )
    except TTSRequestError as exc:
        assert exc.code == TTSRequestErrorCode.INVALID_SPEED
    else:
        raise AssertionError("Expected TTSRequestError for invalid speed")


def test_edge_provider_generate_segments_validates_voice(monkeypatch) -> None:
    monkeypatch.setattr(registry, "SettingsManager", lambda: _FakeSettingsManager([]))
    monkeypatch.delenv("FMM_TTS_PLUGIN_PATHS", raising=False)
    registry.reload_provider_registry()

    edge = registry.get_provider(TTSEngine.EDGE_TTS)
    assert edge is not None
    try:
        asyncio.run(
            edge.generate_segments(
                segments=[("hello", 0)],
                voice="",
                speed=1.0,
                output_dir=Path("/tmp"),
            )
        )
    except TTSRequestError as exc:
        assert exc.code == TTSRequestErrorCode.VOICE_REQUIRED
    else:
        raise AssertionError("Expected TTSRequestError for empty voice")
