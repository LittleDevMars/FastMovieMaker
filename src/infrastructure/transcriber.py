"""음성-텍스트 변환(Transcription) 추상화.

ITranscriber 프로토콜로 정의하여 faster-whisper 외 다른 구현체(Rust 등)로
교체 가능하게 함.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

from src.models.subtitle import SubtitleSegment, SubtitleTrack


@runtime_checkable
class ITranscriber(Protocol):
    """음성 파일을 자막 트랙으로 변환하는 인터페이스."""

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str = "ko",
        model_name: str = "base",
        on_progress: Callable[[int, int], None] | None = None,
        on_segment: Callable[[SubtitleSegment], None] | None = None,
        check_cancelled: Callable[[], bool] | None = None,
    ) -> SubtitleTrack:
        """오디오 파일을 자막 트랙으로 변환. 취소 시 부분 결과 반환."""
        ...


class WhisperTranscriber:
    """faster-whisper 기반 ITranscriber 구현체."""

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str = "ko",
        model_name: str = "base",
        on_progress: Callable[[int, int], None] | None = None,
        on_segment: Callable[[SubtitleSegment], None] | None = None,
        check_cancelled: Callable[[], bool] | None = None,
    ) -> SubtitleTrack:
        """faster-whisper로 음성→텍스트 변환."""
        from src.services.whisper_service import (
            load_model,
            release_model,
            transcribe as _transcribe,
        )

        model = None
        try:
            model = load_model(model_name)

            # 모델 로딩(10~30초) 사이 취소되었을 수 있으므로 체크
            if check_cancelled and check_cancelled():
                return SubtitleTrack(language=language)

            return _transcribe(
                model,
                audio_path,
                language=language,
                on_progress=on_progress,
                on_segment=on_segment,
                check_cancelled=check_cancelled,
            )
        finally:
            if model is not None:
                release_model(model)
