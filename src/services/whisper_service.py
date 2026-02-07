"""Whisper transcription service (no Qt dependency)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import torch
import whisper

from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.utils.time_utils import seconds_to_ms


def load_model(model_name: str) -> whisper.Whisper:
    """Load a Whisper model onto GPU if available."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return whisper.load_model(model_name, device=device)


def transcribe(
    model: whisper.Whisper,
    audio_path: Path,
    language: str = "ko",
    on_progress: Callable[[int, int], None] | None = None,
) -> SubtitleTrack:
    """Transcribe audio file and return a SubtitleTrack.

    Args:
        model: Loaded Whisper model.
        audio_path: Path to 16kHz WAV file.
        language: Language code.
        on_progress: Callback(current_segment, total_segments) for progress.

    Returns:
        SubtitleTrack with transcribed segments.
    """
    result = model.transcribe(
        str(audio_path),
        language=language,
        verbose=False,
    )

    segments = result.get("segments", [])
    total = len(segments)

    track = SubtitleTrack(language=language)
    for i, seg in enumerate(segments):
        track.add_segment(SubtitleSegment(
            start_ms=seconds_to_ms(seg["start"]),
            end_ms=seconds_to_ms(seg["end"]),
            text=seg["text"].strip(),
        ))
        if on_progress:
            on_progress(i + 1, total)

    return track


def release_model(model: whisper.Whisper) -> None:
    """Release model and free GPU memory."""
    del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
