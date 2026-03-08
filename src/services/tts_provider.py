"""TTS provider interface and shared config types."""

from __future__ import annotations

import math
from enum import Enum
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Protocol

if TYPE_CHECKING:
    from src.services.tts_service import AudioSegment

TTS_SPEED_MIN = 0.1
TTS_SPEED_MAX = 4.0
TTS_ERROR_PREFIX = "TTS_ERROR"


class TTSRequestErrorCode(str, Enum):
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    VOICE_REQUIRED = "VOICE_REQUIRED"
    INVALID_SPEED = "INVALID_SPEED"
    EMPTY_SCRIPT = "EMPTY_SCRIPT"
    EMPTY_SEGMENTS = "EMPTY_SEGMENTS"
    UNKNOWN = "UNKNOWN"


class TTSRequestError(ValueError):
    """Structured TTS request validation/runtime error."""

    def __init__(self, code: TTSRequestErrorCode, detail: str | None = None):
        self.code = code
        self.detail = detail
        super().__init__(self.__str__())

    def __str__(self) -> str:
        if self.detail:
            return f"{self.code.value}: {self.detail}"
        return self.code.value


def serialize_tts_error(code: TTSRequestErrorCode, detail: str | None = None) -> str:
    safe_detail = "" if detail is None else str(detail)
    return f"{TTS_ERROR_PREFIX}::{code.value}::{safe_detail}"


def parse_tts_error(serialized: str) -> tuple[TTSRequestErrorCode, str]:
    text = str(serialized or "")
    if not text.startswith(f"{TTS_ERROR_PREFIX}::"):
        return (TTSRequestErrorCode.UNKNOWN, text)
    parts = text.split("::", 2)
    if len(parts) < 3:
        return (TTSRequestErrorCode.UNKNOWN, text)
    code_name = parts[1].strip()
    detail = parts[2]
    try:
        code = TTSRequestErrorCode(code_name)
    except ValueError:
        code = TTSRequestErrorCode.UNKNOWN
    return (code, detail)


def exception_to_tts_error_text(exc: Exception) -> str:
    if isinstance(exc, TTSRequestError):
        return serialize_tts_error(exc.code, exc.detail)
    return serialize_tts_error(TTSRequestErrorCode.UNKNOWN, str(exc))


def validate_tts_request(
    *,
    voice: str,
    speed: float,
    segments: list[tuple[str, int]] | None = None,
) -> None:
    """Validate shared TTS input contract before provider invocation."""
    if not str(voice).strip():
        raise TTSRequestError(TTSRequestErrorCode.VOICE_REQUIRED, "voice is required")

    speed_value = float(speed)
    if (not math.isfinite(speed_value)) or not (TTS_SPEED_MIN <= speed_value <= TTS_SPEED_MAX):
        raise TTSRequestError(
            TTSRequestErrorCode.INVALID_SPEED,
            f"speed must be between {TTS_SPEED_MIN} and {TTS_SPEED_MAX}",
        )

    if segments is not None and len(segments) == 0:
        raise TTSRequestError(TTSRequestErrorCode.EMPTY_SEGMENTS, "segments must not be empty")


@dataclass(slots=True)
class TTSProviderConfig:
    """Common provider configuration for UI/worker handoff."""

    provider_id: str
    voice: str
    speed: float
    language: str | None = None
    api_key: str | None = None


class TTSProvider(Protocol):
    """Provider contract for text-to-speech engines."""

    provider_id: str
    display_name: str

    def requires_api_key(self) -> bool:
        """Return whether this provider requires an API key."""

    def list_voices(self, language: str | None) -> list[tuple[str, str]]:
        """Return available voices as (label, value) pairs."""

    def synthesize(
        self,
        text: str,
        voice: str,
        speed: float,
        output_path: Path,
        *,
        language: str | None = None,
    ) -> None:
        """Generate speech audio at the given path."""

    async def generate_segments(
        self,
        segments: list[tuple[str, int]],
        voice: str,
        speed: float,
        output_dir: Path,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list["AudioSegment"]:
        """Generate speech audio for multiple segments."""
