"""Built-in TTS providers and lookup helpers."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from src.services.elevenlabs_tts_service import ElevenLabsTTSService
from src.services.settings_manager import SettingsManager
from src.services.tts_plugin_loader import load_tts_plugin_providers
from src.services.tts_provider import TTSProvider, validate_tts_request
from src.services.tts_service import AudioSegment
from src.services.tts_service import TTSService
from src.utils.config import ELEVENLABS_DEFAULT_VOICES, TTS_VOICES, TTSEngine


class EdgeTTSProvider:
    provider_id = TTSEngine.EDGE_TTS
    display_name = "Edge-TTS (Free)"

    def requires_api_key(self) -> bool:
        return False

    def list_voices(self, language: str | None) -> list[tuple[str, str]]:
        labels: list[tuple[str, str]] = []
        languages = [language] if language else list(TTS_VOICES.keys())
        for lang in languages:
            if lang not in TTS_VOICES:
                continue
            voices = TTS_VOICES[lang]
            for gender in ["Female", "Male"]:
                for voice_name in voices.get(gender, []):
                    display = voice_name.split("-")[-1]
                    display = display.replace("Neural", "").replace("Multilingual", "")
                    labels.append((f"{display} ({gender})", voice_name))
        return labels

    def synthesize(
        self,
        text: str,
        voice: str,
        speed: float,
        output_path: Path,
        *,
        language: str | None = None,
    ) -> None:
        validate_tts_request(voice=voice, speed=speed)
        rate = TTSService.format_rate(speed)
        asyncio.run(
            TTSService.generate_speech(
                text=text,
                voice=voice,
                rate=rate,
                output_path=output_path,
            )
        )

    async def generate_segments(
        self,
        segments: list[tuple[str, int]],
        voice: str,
        speed: float,
        output_dir: Path,
        on_progress=None,
    ) -> list[AudioSegment]:
        validate_tts_request(voice=voice, speed=speed, segments=segments)
        rate = TTSService.format_rate(speed)
        return await TTSService.generate_segments(
            segments=segments,
            voice=voice,
            rate=rate,
            output_dir=output_dir,
            on_progress=on_progress,
            timeout=30.0,
        )


class ElevenLabsProvider:
    provider_id = TTSEngine.ELEVENLABS
    display_name = "ElevenLabs (Premium)"

    def requires_api_key(self) -> bool:
        return True

    def list_voices(self, language: str | None) -> list[tuple[str, str]]:
        return [(label, voice_id) for label, voice_id in ELEVENLABS_DEFAULT_VOICES.items()]

    def synthesize(
        self,
        text: str,
        voice: str,
        speed: float,
        output_path: Path,
        *,
        language: str | None = None,
    ) -> None:
        validate_tts_request(voice=voice, speed=speed)
        api_key = SettingsManager().get_elevenlabs_api_key()
        service = ElevenLabsTTSService(api_key)
        service.generate_speech(
            text=text,
            voice_id=voice,
            speed=speed,
            output_path=output_path,
        )

    async def generate_segments(
        self,
        segments: list[tuple[str, int]],
        voice: str,
        speed: float,
        output_dir: Path,
        on_progress=None,
    ) -> list[AudioSegment]:
        validate_tts_request(voice=voice, speed=speed, segments=segments)
        api_key = SettingsManager().get_elevenlabs_api_key()
        service = ElevenLabsTTSService(api_key)
        return await asyncio.to_thread(
            service.generate_segments,
            segments=segments,
            voice_id=voice,
            speed=speed,
            output_dir=output_dir,
            on_progress=on_progress,
            timeout=60.0,
        )


_BUILTIN_PROVIDERS: dict[str, TTSProvider] = {
    TTSEngine.EDGE_TTS: EdgeTTSProvider(),
    TTSEngine.ELEVENLABS: ElevenLabsProvider(),
}
_ALL_PROVIDERS: dict[str, TTSProvider] = dict(_BUILTIN_PROVIDERS)
_PROVIDER_LOAD_ERRORS: list[str] = []


def _collect_plugin_paths() -> list[str]:
    configured_paths = SettingsManager().get_tts_plugin_paths()
    env_raw = os.getenv("FMM_TTS_PLUGIN_PATHS", "")
    env_paths = [p.strip() for p in env_raw.split(os.pathsep) if p.strip()]
    merged = configured_paths + env_paths

    deduped: list[str] = []
    seen: set[str] = set()
    for raw_path in merged:
        normalized = str(Path(raw_path).expanduser())
        if normalized in seen:
            continue
        seen.add(normalized)
        if Path(normalized).is_file():
            deduped.append(normalized)
    return deduped


def get_builtin_providers() -> dict[str, TTSProvider]:
    """Return built-in TTS providers keyed by provider_id."""
    return dict(_BUILTIN_PROVIDERS)


def get_all_providers() -> dict[str, TTSProvider]:
    """Return all registered providers (builtin + plugins)."""
    return dict(_ALL_PROVIDERS)


def get_provider_load_errors() -> list[str]:
    """Return plugin loading errors collected during last reload."""
    return list(_PROVIDER_LOAD_ERRORS)


def reload_provider_registry() -> None:
    """Reload provider registry from builtins + configured plugin paths."""
    global _ALL_PROVIDERS, _PROVIDER_LOAD_ERRORS
    _ALL_PROVIDERS = dict(_BUILTIN_PROVIDERS)
    _PROVIDER_LOAD_ERRORS = []

    plugin_paths = _collect_plugin_paths()
    plugin_providers, plugin_errors = load_tts_plugin_providers(
        plugin_paths,
        reserved_provider_ids=set(_BUILTIN_PROVIDERS.keys()),
    )
    _ALL_PROVIDERS.update(plugin_providers)
    _PROVIDER_LOAD_ERRORS.extend(plugin_errors)


def get_provider(provider_id: str) -> TTSProvider | None:
    """Return a provider instance by id."""
    return _ALL_PROVIDERS.get(provider_id)


reload_provider_registry()
