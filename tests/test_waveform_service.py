"""Tests for waveform peak computation."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from src.services.waveform_service import WaveformData, compute_peaks_from_wav


def _create_test_wav(
    path: Path,
    duration_ms: int = 1000,
    frequency: float = 440.0,
    sample_rate: int = 16000,
) -> None:
    """Create a test WAV file with a sine wave."""
    n_samples = int(sample_rate * duration_ms / 1000)
    t = np.arange(n_samples) / sample_rate
    samples = (np.sin(2 * np.pi * frequency * t) * 32767).astype(np.int16)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())


class TestWaveformData:
    def test_dataclass_fields(self):
        data = WaveformData(
            peaks_pos=np.array([0.5], dtype=np.float32),
            peaks_neg=np.array([-0.5], dtype=np.float32),
            duration_ms=1,
            sample_rate=16000,
        )
        assert data.duration_ms == 1
        assert data.sample_rate == 16000
        assert len(data.peaks_pos) == 1
        assert len(data.peaks_neg) == 1


class TestComputePeaks:
    def test_basic_sine_wave(self, tmp_path):
        wav_path = tmp_path / "sine.wav"
        _create_test_wav(wav_path, duration_ms=100)
        result = compute_peaks_from_wav(wav_path)

        assert isinstance(result, WaveformData)
        assert result.duration_ms == 100
        assert len(result.peaks_pos) == 100
        assert len(result.peaks_neg) == 100
        assert result.sample_rate == 16000

    def test_peaks_amplitude(self, tmp_path):
        wav_path = tmp_path / "sine.wav"
        _create_test_wav(wav_path, duration_ms=500, frequency=440.0)
        result = compute_peaks_from_wav(wav_path)

        # Sine wave peaks should be near +1 and -1
        assert np.max(result.peaks_pos) > 0.9
        assert np.min(result.peaks_neg) < -0.9

    def test_peaks_normalized_range(self, tmp_path):
        wav_path = tmp_path / "sine.wav"
        _create_test_wav(wav_path, duration_ms=200)
        result = compute_peaks_from_wav(wav_path)

        # All values should be within [-1, 1]
        assert np.all(result.peaks_pos >= -1.0)
        assert np.all(result.peaks_pos <= 1.0)
        assert np.all(result.peaks_neg >= -1.0)
        assert np.all(result.peaks_neg <= 1.0)
        # peaks_pos >= peaks_neg always
        assert np.all(result.peaks_pos >= result.peaks_neg)

    def test_silence(self, tmp_path):
        wav_path = tmp_path / "silent.wav"
        n_samples = 16000  # 1 second at 16kHz
        samples = np.zeros(n_samples, dtype=np.int16)

        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(samples.tobytes())

        result = compute_peaks_from_wav(wav_path)
        assert result.duration_ms == 1000
        assert np.max(np.abs(result.peaks_pos)) == 0.0
        assert np.max(np.abs(result.peaks_neg)) == 0.0

    def test_empty_wav(self, tmp_path):
        wav_path = tmp_path / "empty.wav"
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"")

        result = compute_peaks_from_wav(wav_path)
        assert result.duration_ms == 0
        assert len(result.peaks_pos) == 0
        assert len(result.peaks_neg) == 0

    def test_different_sample_rate(self, tmp_path):
        wav_path = tmp_path / "44k.wav"
        _create_test_wav(wav_path, duration_ms=100, sample_rate=44100)
        result = compute_peaks_from_wav(wav_path)

        assert result.duration_ms == 100
        assert result.sample_rate == 44100
        assert len(result.peaks_pos) == 100

    def test_long_duration(self, tmp_path):
        """Test with 5-second audio to verify vectorized computation."""
        wav_path = tmp_path / "long.wav"
        _create_test_wav(wav_path, duration_ms=5000)
        result = compute_peaks_from_wav(wav_path)

        assert result.duration_ms == 5000
        assert len(result.peaks_pos) == 5000
        assert len(result.peaks_neg) == 5000
