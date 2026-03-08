"""Settings manager for application preferences."""

import json
import os
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QSettings

from src.utils.config import TTSEngine

# 커스터마이징 가능한 단축키 기본값
_SHORTCUT_DEFAULTS: dict[str, str] = {
    "play_pause":        "Space",
    "seek_back":         "Left",
    "seek_forward":      "Right",
    "seek_back_frame":   "Shift+Left",
    "seek_forward_frame": "Shift+Right",
    "delete":            "Delete",
    "split_clip":        "Ctrl+B",
    "zoom_in":           "Ctrl+=",
    "zoom_out":          "Ctrl+-",
    "zoom_fit":          "Ctrl+0",
    "snap_toggle":       "S",
    "copy_clip":         "Ctrl+C",
    "paste_clip":        "Ctrl+V",
}


class SettingsManager:
    """Wrapper around QSettings for type-safe preference management."""

    def __init__(self):
        self._settings = QSettings()

    # ---------------------------------------------------- General Settings

    def get_autosave_interval(self) -> int:
        """Get the autosave interval in seconds (default: 30)."""
        return self._settings.value("autosave/interval", 30, int)

    def set_autosave_interval(self, seconds: int) -> None:
        """Set the autosave interval in seconds."""
        self._settings.setValue("autosave/interval", seconds)

    def get_autosave_idle_timeout(self) -> int:
        """Get the idle timeout after edits in seconds (default: 5)."""
        return self._settings.value("autosave/idle_timeout", 5, int)

    def set_autosave_idle_timeout(self, seconds: int) -> None:
        """Set the idle timeout after edits in seconds."""
        self._settings.setValue("autosave/idle_timeout", seconds)

    def get_recent_files_max(self) -> int:
        """Get the maximum number of recent files to remember (default: 10)."""
        return self._settings.value("recent/max_files", 10, int)

    def set_recent_files_max(self, count: int) -> None:
        """Set the maximum number of recent files to remember."""
        self._settings.setValue("recent/max_files", count)

    def get_default_language(self) -> str:
        """Get the default language for new projects (default: Korean)."""
        return self._settings.value("general/default_language", "Korean", str)

    def set_default_language(self, language: str) -> None:
        """Set the default language for new projects."""
        self._settings.setValue("general/default_language", language)

    # ---------------------------------------------------- Editing Settings

    def get_default_subtitle_duration(self) -> int:
        """Get the default duration for new subtitles in ms (default: 2000)."""
        return self._settings.value("editing/default_duration", 2000, int)

    def set_default_subtitle_duration(self, ms: int) -> None:
        """Set the default duration for new subtitles in ms."""
        self._settings.setValue("editing/default_duration", ms)

    def get_snap_tolerance(self) -> int:
        """Get the snap tolerance in pixels (default: 10)."""
        return self._settings.value("editing/snap_tolerance", 10, int)

    def set_snap_tolerance(self, pixels: int) -> None:
        """Set the snap tolerance in pixels."""
        self._settings.setValue("editing/snap_tolerance", pixels)

    def get_frame_seek_fps(self) -> int:
        """Get the FPS for frame-by-frame seeking (default: 30)."""
        return self._settings.value("editing/frame_fps", 30, int)

    def set_frame_seek_fps(self, fps: int) -> None:
        """Set the FPS for frame-by-frame seeking."""
        self._settings.setValue("editing/frame_fps", fps)

    def get_audio_speed_pitch_shift(self) -> bool:
        """Get whether audio speed changes should also shift pitch (default: False)."""
        return self._settings.value("editing/audio_speed_pitch_shift", False, bool)

    def set_audio_speed_pitch_shift(self, shift_pitch: bool) -> None:
        """Set whether audio speed changes should also shift pitch."""
        self._settings.setValue("editing/audio_speed_pitch_shift", shift_pitch)

    def get_frame_cache_quality(self) -> int:
        """Get the JPEG quality for frame cache (1-31, lower is better, default: 5)."""
        return self._settings.value("editing/frame_cache_quality", 5, int)

    def set_frame_cache_quality(self, quality: int) -> None:
        """Set the JPEG quality for frame cache."""
        self._settings.setValue("editing/frame_cache_quality", quality)

    # ---------------------------------------------------- Advanced Settings

    def get_ffmpeg_path(self) -> Optional[str]:
        """Get the custom FFmpeg path (None for auto-detect)."""
        path = self._settings.value("advanced/ffmpeg_path", "", str)
        return path if path else None

    def set_ffmpeg_path(self, path: Optional[str]) -> None:
        """Set the custom FFmpeg path (None for auto-detect)."""
        self._settings.setValue("advanced/ffmpeg_path", path or "")

    def get_whisper_cache_dir(self) -> Optional[str]:
        """Get the Whisper model cache directory (None for default)."""
        path = self._settings.value("advanced/whisper_cache", "", str)
        return path if path else None

    def set_whisper_cache_dir(self, path: Optional[str]) -> None:
        """Set the Whisper model cache directory (None for default)."""
        self._settings.setValue("advanced/whisper_cache", path or "")

    # ---------------------------------------------------- API Keys

    def get_deepl_api_key(self) -> str:
        """Get the DeepL API key."""
        return self._settings.value("api_keys/deepl", "", str)

    def set_deepl_api_key(self, key: str) -> None:
        """Set the DeepL API key."""
        self._settings.setValue("api_keys/deepl", key)

    def get_openai_api_key(self) -> str:
        """Get the OpenAI API key."""
        return self._settings.value("api_keys/openai", "", str)

    def set_openai_api_key(self, key: str) -> None:
        """Set the OpenAI API key."""
        self._settings.setValue("api_keys/openai", key)

    def get_elevenlabs_api_key(self) -> str:
        """Get the ElevenLabs API key."""
        return self._settings.value("api_keys/elevenlabs", "", str)

    def set_elevenlabs_api_key(self, key: str) -> None:
        """Set the ElevenLabs API key."""
        self._settings.setValue("api_keys/elevenlabs", key)

    # ---------------------------------------------------- UI Settings

    def get_theme(self) -> str:
        """Get the UI theme (default: dark)."""
        return self._settings.value("ui/theme", "dark", str)

    def set_theme(self, theme: str) -> None:
        """Set the UI theme."""
        self._settings.setValue("ui/theme", theme)

    def get_ui_language(self) -> str:
        """Get the UI language code (default: ko)."""
        return self._settings.value("ui/language", "ko", str)

    def set_ui_language(self, lang: str) -> None:
        """Set the UI language code ('en', 'ko', etc.)."""
        self._settings.setValue("ui/language", lang)

    # ---------------------------------------------------- General Methods

    def reset_to_defaults(self) -> None:
        """Reset all settings to default values."""
        self._settings.clear()

    def sync(self) -> None:
        """Force synchronization of settings to disk."""
        self._settings.sync()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value by key."""
        return self._settings.value(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a setting value by key."""
        self._settings.setValue(key, value)

    # ---------------------------------------------------- TTS Settings

    def get_tts_default_provider(self) -> str:
        """Get default TTS provider id (default: edge_tts)."""
        value = self._settings.value("tts/default_provider", TTSEngine.EDGE_TTS, str)
        if not str(value).strip():
            return TTSEngine.EDGE_TTS
        return str(value)

    def set_tts_default_provider(self, provider_id: str) -> None:
        """Set default TTS provider id."""
        if not str(provider_id).strip():
            provider_id = TTSEngine.EDGE_TTS
        self._settings.setValue("tts/default_provider", str(provider_id))

    def get_tts_plugin_paths(self) -> list[str]:
        """Get configured TTS plugin file paths."""
        raw_value = self._settings.value("tts/plugin_paths", [])
        return self._normalize_path_list(raw_value)

    def set_tts_plugin_paths(self, paths: list[str]) -> None:
        """Set configured TTS plugin file paths."""
        normalized = self._normalize_path_list(paths)
        self._settings.setValue("tts/plugin_paths", normalized)

    # ---------------------------------------------------- Project Sync Settings

    def get_project_sync_root_path(self) -> Optional[str]:
        """Get project sync root folder path."""
        path = self._settings.value("project_sync/root_path", "", str)
        token = str(path).strip()
        return token if token else None

    def set_project_sync_root_path(self, path: Optional[str]) -> None:
        """Set project sync root folder path."""
        token = str(path).strip() if path is not None else ""
        self._settings.setValue("project_sync/root_path", token)

    def get_project_sync_state(self) -> dict[str, dict[str, str]]:
        """Get per-project sync state map."""
        raw_value = self._settings.value("project_sync/state", "{}", str)
        if isinstance(raw_value, dict):
            return self._normalize_sync_state(raw_value)
        try:
            parsed = json.loads(str(raw_value))
        except Exception:
            return {}
        return self._normalize_sync_state(parsed)

    def set_project_sync_state(self, state: dict[str, dict[str, str]]) -> None:
        """Set per-project sync state map."""
        normalized = self._normalize_sync_state(state)
        payload = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
        self._settings.setValue("project_sync/state", payload)

    # ---------------------------------------------------- Shortcut Settings

    def get_shortcut(self, action: str) -> str:
        """Get the key sequence string for the given action (falls back to default)."""
        return self._settings.value(
            f"shortcuts/{action}", _SHORTCUT_DEFAULTS.get(action, ""), str
        )

    def set_shortcut(self, action: str, key: str) -> None:
        """Persist the key sequence string for the given action."""
        self._settings.setValue(f"shortcuts/{action}", key)

    @staticmethod
    def _normalize_path_list(value: Any) -> list[str]:
        if isinstance(value, str):
            tokens = value.split(os.pathsep) if os.pathsep in value else [value]
            return [token.strip() for token in tokens if token and token.strip()]
        if isinstance(value, (list, tuple, set)):
            seen: set[str] = set()
            out: list[str] = []
            for item in value:
                token = str(item).strip()
                if not token or token in seen:
                    continue
                seen.add(token)
                out.append(token)
            return out
        return []

    @staticmethod
    def _normalize_sync_state(value: Any) -> dict[str, dict[str, str]]:
        if not isinstance(value, dict):
            return {}
        out: dict[str, dict[str, str]] = {}
        for raw_key, raw_entry in value.items():
            key = str(raw_key).strip()
            if not key or not isinstance(raw_entry, dict):
                continue
            last_hash = str(raw_entry.get("last_hash", "")).strip()
            updated_at = str(raw_entry.get("updated_at", "")).strip()
            out[key] = {
                "last_hash": last_hash,
                "updated_at": updated_at,
            }
        return out
