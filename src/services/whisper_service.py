"""Whisper transcription service using faster-whisper (CTranslate2, no Qt dependency)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from faster_whisper import WhisperModel

from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.utils.time_utils import seconds_to_ms


def load_model(model_name: str) -> WhisperModel:
    """Load a faster-whisper model onto GPU if available.

    Uses float16 on CUDA for ~4x speed vs openai-whisper with half VRAM.
    Falls back to int8 on CPU for decent speed without GPU.
    """
    try:
        import torch
        has_cuda = torch.cuda.is_available()
    except ImportError:
        has_cuda = False

    if has_cuda:
        return WhisperModel(model_name, device="cuda", compute_type="float16")
    else:
        return WhisperModel(model_name, device="cpu", compute_type="int8")


def transcribe(
    model: WhisperModel,
    audio_path: Path,
    language: str = "ko",
    on_progress: Callable[[int, int], None] | None = None,
) -> SubtitleTrack:
    """Transcribe audio file and return a SubtitleTrack.

    Args:
        model: Loaded faster-whisper model.
        audio_path: Path to audio file (WAV, MP3, etc.).
        language: Language code.
        on_progress: Callback(current_segment, total_segments) for progress.

    Returns:
        SubtitleTrack with transcribed segments.
    """
    segments_iter, info = model.transcribe(
        str(audio_path),
        language=language,
        vad_filter=True,
    )

    # faster-whisper returns an iterator; collect segments for progress tracking
    segments = list(segments_iter)
    total = len(segments)

    track = SubtitleTrack(language=language)
    for i, seg in enumerate(segments):
        track.add_segment(SubtitleSegment(
            start_ms=seconds_to_ms(seg.start),
            end_ms=seconds_to_ms(seg.end),
            text=seg.text.strip(),
        ))
        if on_progress:
            on_progress(i + 1, total)

    return track


def release_model(model: WhisperModel) -> None:
    """Release model and free GPU memory."""
    del model
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
