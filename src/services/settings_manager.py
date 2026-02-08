"""Settings manager for application preferences."""

from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QSettings


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