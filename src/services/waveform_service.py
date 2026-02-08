"""Waveform peak computation service (pure Python, no Qt dependency)."""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class WaveformData:
    """Pre-computed waveform peak data at 1-peak-per-millisecond resolution."""

    peaks_pos: np.ndarray  # max amplitude per ms, shape (duration_ms,), float32, [0, 1]
    peaks_neg: np.ndarray  # min amplitude per ms, shape (duration_ms,), float32, [-1, 0]
    duration_ms: int
    sample_rate: int


def compute_peaks_from_wav(wav_path: Path) -> WaveformData:
    """Load a WAV file and compute per-millisecond min/max peaks.

    Args:
        wav_path: Path to a 16-bit or 32-bit PCM mono WAV file.

    Returns:
        WaveformData with normalized peaks in [-1, 1].
    """
    with wave.open(str(wav_path), "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frame_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw_data = wf.readframes(n_frames)

    # Convert raw bytes to numpy array
    if sample_width == 2:
        samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)
        max_val = 32768.0
    elif sample_width == 4:
        samples = np.frombuffer(raw_data, dtype=np.int32).astype(np.float32)
        max_val = 2147483648.0
    else:
        raise ValueError(f"Unsupported sample width: {sample_width}")

    # If multi-channel, take first channel only
    if n_channels > 1:
        samples = samples[::n_channels]

    # Normalize to [-1.0, 1.0]
    samples /= max_val

    # Calculate dimensions
    samples_per_ms = frame_rate / 1000.0
    duration_ms = int(len(samples) / samples_per_ms)

    if duration_ms <= 0:
        return WaveformData(
            peaks_pos=np.zeros(0, dtype=np.float32),
            peaks_neg=np.zeros(0, dtype=np.float32),
            duration_ms=0,
            sample_rate=frame_rate,
        )

    # Vectorized peak computation using reshape
    samples_per_ms_int = int(np.ceil(samples_per_ms))
    padded_len = duration_ms * samples_per_ms_int
    padded = np.zeros(padded_len, dtype=np.float32)
    copy_len = min(len(samples), padded_len)
    padded[:copy_len] = samples[:copy_len]

    reshaped = padded.reshape(duration_ms, samples_per_ms_int)
    peaks_pos = np.max(reshaped, axis=1).astype(np.float32)
    peaks_neg = np.min(reshaped, axis=1).astype(np.float32)

    return WaveformData(
        peaks_pos=peaks_pos,
        peaks_neg=peaks_neg,
        duration_ms=duration_ms,
        sample_rate=frame_rate,
    )
