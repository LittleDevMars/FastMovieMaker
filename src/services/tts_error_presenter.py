"""Common presenter for mapping TTS error codes to user-facing messages."""

from __future__ import annotations

from typing import Callable

from src.services.tts_provider import TTSRequestErrorCode, parse_tts_error
from src.utils.i18n import tr


def to_user_message(error_text: str, tr_fn: Callable[[str], str] = tr) -> str:
    """Convert serialized/internal TTS errors into localized user-facing text."""
    code, _detail = parse_tts_error(error_text)
    if code == TTSRequestErrorCode.PROVIDER_UNAVAILABLE:
        return tr_fn("Selected provider is unavailable.")
    if code == TTSRequestErrorCode.VOICE_REQUIRED:
        return tr_fn("No voice available for selected provider.")
    if code == TTSRequestErrorCode.INVALID_SPEED:
        return tr_fn("Invalid TTS speed.")
    if code in (TTSRequestErrorCode.EMPTY_SCRIPT, TTSRequestErrorCode.EMPTY_SEGMENTS):
        return tr_fn("Please enter a script to generate speech.")
    return tr_fn("TTS request is invalid.")
