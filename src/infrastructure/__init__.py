"""Infrastructure layer: external dependencies (FFmpeg, Whisper, etc.).

이 계층은 외부 도구/라이브러리를 추상화하여 Application 계층이
구현체에 직접 의존하지 않도록 합니다.
"""

from src.infrastructure.ffmpeg_runner import FFmpegRunner
from src.infrastructure.transcriber import ITranscriber, WhisperTranscriber

__all__ = [
    "FFmpegRunner",
    "ITranscriber",
    "WhisperTranscriber",
]
