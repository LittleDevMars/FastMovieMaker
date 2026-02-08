"""Waveform peak computation service (pure Python, no Qt dependency).

Processes audio in chunks to keep memory usage low for long videos.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

# 1초 분량씩 청크로 읽기 (메모리 ~128KB per chunk at 48kHz/16bit)
_CHUNK_SECONDS = 1


@dataclass
class WaveformData:
    """Pre-computed waveform peak data at 1-peak-per-millisecond resolution."""

    peaks_pos: np.ndarray  # max amplitude per ms, shape (duration_ms,), float32, [0, 1]
    peaks_neg: np.ndarray  # min amplitude per ms, shape (duration_ms,), float32, [-1, 0]
    duration_ms: int
    sample_rate: int


def compute_peaks_from_wav(
    wav_path: Path,
    on_progress: Callable[[int, int], None] | None = None,
) -> WaveformData:
    """Load a WAV file in chunks and compute per-millisecond min/max peaks.

    Memory-efficient: only one chunk (~1 second) of audio is in memory at a time,
    regardless of total file duration.

    Args:
        wav_path: Path to a 16-bit or 32-bit PCM mono/stereo WAV file.
        on_progress: Optional callback(processed_ms, total_ms) for progress.

    Returns:
        WaveformData with normalized peaks in [-1, 1].
    """
    with wave.open(str(wav_path), "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frame_rate = wf.getframerate()
        n_frames = wf.getnframes()

        if sample_width == 2:
            dtype = np.int16
            max_val = 32768.0
        elif sample_width == 4:
            dtype = np.int32
            max_val = 2147483648.0
        else:
            raise ValueError(f"Unsupported sample width: {sample_width}")

        samples_per_ms = frame_rate / 1000.0
        total_duration_ms = int(n_frames / samples_per_ms)

        if total_duration_ms <= 0:
            return WaveformData(
                peaks_pos=np.zeros(0, dtype=np.float32),
                peaks_neg=np.zeros(0, dtype=np.float32),
                duration_ms=0,
                sample_rate=frame_rate,
            )

        # 결과 배열 미리 할당
        peaks_pos = np.zeros(total_duration_ms, dtype=np.float32)
        peaks_neg = np.zeros(total_duration_ms, dtype=np.float32)

        chunk_frames = int(frame_rate * _CHUNK_SECONDS)
        samples_per_ms_int = int(np.ceil(samples_per_ms))
        ms_written = 0
        frames_read = 0

        # 이전 청크에서 남은 샘플(ms 경계에 걸친 부분)
        leftover = np.zeros(0, dtype=np.float32)

        while frames_read < n_frames:
            read_count = min(chunk_frames, n_frames - frames_read)
            raw = wf.readframes(read_count)
            frames_read += read_count

            chunk = np.frombuffer(raw, dtype=dtype).astype(np.float32)
            if n_channels > 1:
                chunk = chunk[::n_channels]
            chunk /= max_val

            # 이전 남은 샘플과 합치기
            if len(leftover) > 0:
                chunk = np.concatenate([leftover, chunk])

            # 이 청크에서 완전한 ms 수 계산
            chunk_ms = int(len(chunk) / samples_per_ms)
            usable_samples = chunk_ms * samples_per_ms_int

            if chunk_ms > 0 and ms_written + chunk_ms <= total_duration_ms:
                padded = np.zeros(chunk_ms * samples_per_ms_int, dtype=np.float32)
                copy_len = min(int(chunk_ms * samples_per_ms), len(chunk))
                padded[:copy_len] = chunk[:copy_len]

                reshaped = padded.reshape(chunk_ms, samples_per_ms_int)
                peaks_pos[ms_written:ms_written + chunk_ms] = np.max(reshaped, axis=1)
                peaks_neg[ms_written:ms_written + chunk_ms] = np.min(reshaped, axis=1)
                ms_written += chunk_ms

                # 남은 샘플 보관 (다음 청크와 합칠 것)
                used_samples = int(chunk_ms * samples_per_ms)
                leftover = chunk[used_samples:] if used_samples < len(chunk) else np.zeros(0, dtype=np.float32)
            else:
                leftover = chunk

            if on_progress and total_duration_ms > 0:
                on_progress(ms_written, total_duration_ms)

        # 마지막 남은 샘플 처리
        if len(leftover) > 0 and ms_written < total_duration_ms:
            remaining_ms = min(int(len(leftover) / samples_per_ms), total_duration_ms - ms_written)
            if remaining_ms > 0:
                padded = np.zeros(remaining_ms * samples_per_ms_int, dtype=np.float32)
                copy_len = min(len(leftover), len(padded))
                padded[:copy_len] = leftover[:copy_len]
                reshaped = padded.reshape(remaining_ms, samples_per_ms_int)
                peaks_pos[ms_written:ms_written + remaining_ms] = np.max(reshaped, axis=1)
                peaks_neg[ms_written:ms_written + remaining_ms] = np.min(reshaped, axis=1)
                ms_written += remaining_ms

    # 실제 쓴 만큼만 잘라서 반환
    return WaveformData(
        peaks_pos=peaks_pos[:ms_written],
        peaks_neg=peaks_neg[:ms_written],
        duration_ms=ms_written,
        sample_rate=frame_rate,
    )
