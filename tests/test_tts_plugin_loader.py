from __future__ import annotations

from pathlib import Path

from src.services.tts_plugin_loader import load_tts_plugin_providers
from src.utils.config import TTSEngine


def _write_plugin(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_loader_loads_valid_plugin_provider(tmp_path) -> None:
    plugin_path = tmp_path / "valid_plugin.py"
    _write_plugin(
        plugin_path,
        """
from pathlib import Path

class DemoProvider:
    provider_id = "demo_provider"
    display_name = "Demo Provider"
    def requires_api_key(self): return False
    def list_voices(self, language): return [("Demo", "demo_voice")]
    def synthesize(self, text, voice, speed, output_path, *, language=None): return None
    async def generate_segments(self, segments, voice, speed, output_dir, on_progress=None): return []

def register_tts_providers():
    return [DemoProvider()]
""".strip(),
    )
    providers, errors = load_tts_plugin_providers([str(plugin_path)])
    assert "demo_provider" in providers
    assert errors == []


def test_loader_handles_missing_register_function(tmp_path) -> None:
    plugin_path = tmp_path / "missing_register.py"
    _write_plugin(plugin_path, "VALUE = 1\n")
    providers, errors = load_tts_plugin_providers([str(plugin_path)])
    assert providers == {}
    assert errors
    assert "register_tts_providers" in errors[0]


def test_loader_handles_register_exception(tmp_path) -> None:
    plugin_path = tmp_path / "raising_plugin.py"
    _write_plugin(
        plugin_path,
        """
def register_tts_providers():
    raise RuntimeError("boom")
""".strip(),
    )
    providers, errors = load_tts_plugin_providers([str(plugin_path)])
    assert providers == {}
    assert errors
    assert "boom" in errors[0]


def test_loader_ignores_invalid_provider_object(tmp_path) -> None:
    plugin_path = tmp_path / "invalid_provider.py"
    _write_plugin(
        plugin_path,
        """
def register_tts_providers():
    return [object()]
""".strip(),
    )
    providers, errors = load_tts_plugin_providers([str(plugin_path)])
    assert providers == {}
    assert errors
    assert "invalid provider object" in errors[0]


def test_loader_ignores_reserved_provider_id_collision(tmp_path) -> None:
    plugin_path = tmp_path / "collision_provider.py"
    _write_plugin(
        plugin_path,
        f"""
class CollisionProvider:
    provider_id = "{TTSEngine.EDGE_TTS}"
    display_name = "Collision"
    def requires_api_key(self): return False
    def list_voices(self, language): return []
    def synthesize(self, text, voice, speed, output_path, *, language=None): return None
    async def generate_segments(self, segments, voice, speed, output_dir, on_progress=None): return []

def register_tts_providers():
    return [CollisionProvider()]
""".strip(),
    )
    providers, errors = load_tts_plugin_providers(
        [str(plugin_path)],
        reserved_provider_ids={TTSEngine.EDGE_TTS, TTSEngine.ELEVENLABS},
    )
    assert providers == {}
    assert errors
    assert "conflicts with builtin provider" in errors[0]
