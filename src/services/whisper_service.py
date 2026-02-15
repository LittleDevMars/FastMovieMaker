"""Whisper transcription service using faster-whisper (CTranslate2, no Qt dependency)."""

from __future__ import annotations

import sys
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
    on_segment: Callable[[SubtitleSegment], None] | None = None,
    check_cancelled: Callable[[], bool] | None = None,
) -> SubtitleTrack:
    """Transcribe audio file and return a SubtitleTrack.

    Args:
        model: Loaded faster-whisper model.
        audio_path: Path to audio file (WAV, MP3, etc.).
        language: Language code.
        on_progress: Callback(current_segment, total_segments) for progress.
        on_segment: Callback(segment) called immediately when a segment is transcribed.
        check_cancelled: Callback returning True if operation should abort.

    Returns:
        SubtitleTrack with transcribed segments. Returns partial track if cancelled.
    """
    # chunk_length=10: 10초 단위 청크로 세그먼트가 자주 나와 취소 체크가 빨라짐
    # (batch_size는 BatchedInferencePipeline 전용이라 WhisperModel에는 넘기지 않음)
    segments_iter, info = model.transcribe(
        str(audio_path),
        language=language,
        vad_filter=True,
        chunk_length=10,
    )

    # faster-whisper returns an iterator
    # We must iterate manually to support cancellation
    track = SubtitleTrack(language=language)
    
    # Note: total segments is unknown with faster-whisper iterator until done.
    # We can pass an incrementing counter to on_progress if total is unknown,
    # or just use 0 as total. The original code gathered list() first which implied waiting.
    # To keep responsiveness, we shouldn't list() it all at once if we want to cancel mid-way.
    
    count = 0
    for seg in segments_iter:
        if check_cancelled and check_cancelled():
            break
            
        new_segment = SubtitleSegment(
            start_ms=seconds_to_ms(seg.start),
            end_ms=seconds_to_ms(seg.end),
            text=seg.text.strip(),
        )
        track.add_segment(new_segment)
        
        if on_segment:
            on_segment(new_segment)

        count += 1
        if on_progress:
            # We don't know total length, so pass 0 or estimate
            on_progress(count, 0)

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
