"""Lightweight dictionary-based i18n for FastMovieMaker."""

from __future__ import annotations

_current_strings: dict[str, str] = {}
_current_lang: str = "en"


def init_language(lang_code: str = "en") -> None:
    """Load language strings. Call once at app startup before UI creation."""
    global _current_strings, _current_lang
    _current_lang = lang_code
    if lang_code == "ko":
        from src.utils.lang.ko import STRINGS
        _current_strings = STRINGS
    elif lang_code == "en":
        _current_strings = {}
    else:
        try:
            import importlib
            mod = importlib.import_module(f"src.utils.lang.{lang_code}")
            _current_strings = mod.STRINGS
        except (ImportError, AttributeError):
            _current_strings = {}


def tr(key: str) -> str:
    """Translate *key* to the current language. Returns *key* unchanged if no translation."""
    return _current_strings.get(key, key)


def current_language() -> str:
    """Return the active language code (e.g. 'en', 'ko')."""
    return _current_lang
