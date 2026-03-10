from __future__ import annotations

from src.services.tts_error_presenter import to_user_message
from src.services.tts_provider import TTSRequestErrorCode, serialize_tts_error


def _tr_identity(text: str) -> str:
    return text


def test_presenter_maps_provider_unavailable() -> None:
    error = serialize_tts_error(TTSRequestErrorCode.PROVIDER_UNAVAILABLE, "provider missing")
    assert to_user_message(error, tr_fn=_tr_identity) == "Selected provider is unavailable."


def test_presenter_maps_voice_required() -> None:
    error = serialize_tts_error(TTSRequestErrorCode.VOICE_REQUIRED, "voice required")
    assert to_user_message(error, tr_fn=_tr_identity) == "No voice available for selected provider."


def test_presenter_maps_invalid_speed() -> None:
    error = serialize_tts_error(TTSRequestErrorCode.INVALID_SPEED, "speed out of range")
    assert to_user_message(error, tr_fn=_tr_identity) == "Invalid TTS speed."


def test_presenter_maps_empty_script_and_segments() -> None:
    empty_script = serialize_tts_error(TTSRequestErrorCode.EMPTY_SCRIPT, "empty script")
    empty_segments = serialize_tts_error(TTSRequestErrorCode.EMPTY_SEGMENTS, "empty segments")
    expected = "Please enter a script to generate speech."
    assert to_user_message(empty_script, tr_fn=_tr_identity) == expected
    assert to_user_message(empty_segments, tr_fn=_tr_identity) == expected


def test_presenter_falls_back_to_invalid_message_for_unknown() -> None:
    assert to_user_message("random error text", tr_fn=_tr_identity) == "TTS request is invalid."
