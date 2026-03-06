"""Tests for provider-based routing in TTSWorker."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.text_splitter import SplitStrategy, TextSegment
from src.services.tts_provider import TTSRequestErrorCode
from src.workers.tts_worker import TTSWorker


def test_worker_uses_provider_generate_segments(tmp_path) -> None:
    worker = TTSWorker(
        script="hello world",
        voice="en-US-GuyNeural",
        strategy=SplitStrategy.SENTENCE,
        speed=1.1,
    )
    provider = MagicMock()
    errors: list[str] = []
    finished_calls: list[tuple] = []
    worker.error.connect(errors.append)
    worker.finished.connect(lambda track, audio_path: finished_calls.append((track, audio_path)))

    async def _generate_segments(segments, voice, speed, output_dir, on_progress=None):
        seg_path = output_dir / "segment_0000.mp3"
        seg_path.write_bytes(b"")
        return [SimpleNamespace(text="hello world", audio_path=seg_path, duration_sec=1.0)]

    provider.generate_segments = AsyncMock(side_effect=_generate_segments)

    def _merge(audio_files, output_path, add_silence_ms=0):
        output_path.write_bytes(b"")

    def _copy2(src, dst):
        Path(dst).write_bytes(Path(src).read_bytes())

    with (
        patch("src.workers.tts_worker.get_provider", return_value=provider),
        patch("src.workers.tts_worker.TextSplitter.split", return_value=[TextSegment("hello world", 0)]),
        patch("src.workers.tts_worker.AudioMerger.merge_audio_files", side_effect=_merge),
        patch("src.workers.tts_worker.Path.home", return_value=tmp_path),
        patch("shutil.copy2", side_effect=_copy2),
    ):
        worker.run()

    assert not errors
    assert len(finished_calls) == 1
    provider.generate_segments.assert_awaited_once()


def test_worker_emits_error_for_unknown_provider() -> None:
    worker = TTSWorker(
        script="hello",
        voice="en-US-GuyNeural",
        strategy=SplitStrategy.SENTENCE,
        speed=1.0,
        engine="unknown-provider",
    )
    errors: list[str] = []
    worker.error.connect(errors.append)
    with patch("src.workers.tts_worker.get_provider", return_value=None):
        worker.run()
    assert errors
    assert errors[0].startswith("TTS_ERROR::")
    assert f"TTS_ERROR::{TTSRequestErrorCode.PROVIDER_UNAVAILABLE.value}::" in errors[0]


def test_worker_emits_error_for_invalid_speed() -> None:
    worker = TTSWorker(
        script="hello",
        voice="en-US-GuyNeural",
        strategy=SplitStrategy.SENTENCE,
        speed=0.0,
    )
    errors: list[str] = []
    provider = MagicMock()
    provider.generate_segments = AsyncMock(return_value=[])
    worker.error.connect(errors.append)
    with (
        patch("src.workers.tts_worker.get_provider", return_value=provider),
        patch("src.workers.tts_worker.TextSplitter.split", return_value=[TextSegment("hello", 0)]),
    ):
        worker.run()
    assert errors
    assert f"TTS_ERROR::{TTSRequestErrorCode.INVALID_SPEED.value}::" in errors[0]


def test_worker_emits_error_for_empty_voice() -> None:
    worker = TTSWorker(
        script="hello",
        voice="",
        strategy=SplitStrategy.SENTENCE,
        speed=1.0,
    )
    errors: list[str] = []
    provider = MagicMock()
    provider.generate_segments = AsyncMock(return_value=[])
    worker.error.connect(errors.append)
    with (
        patch("src.workers.tts_worker.get_provider", return_value=provider),
        patch("src.workers.tts_worker.TextSplitter.split", return_value=[TextSegment("hello", 0)]),
    ):
        worker.run()
    assert errors
    assert f"TTS_ERROR::{TTSRequestErrorCode.VOICE_REQUIRED.value}::" in errors[0]


def test_worker_emits_error_for_empty_segments() -> None:
    worker = TTSWorker(
        script="hello",
        voice="en-US-GuyNeural",
        strategy=SplitStrategy.SENTENCE,
        speed=1.0,
    )
    errors: list[str] = []
    worker.error.connect(errors.append)
    with patch("src.workers.tts_worker.TextSplitter.split", return_value=[]):
        worker.run()
    assert errors
    assert f"TTS_ERROR::{TTSRequestErrorCode.EMPTY_SCRIPT.value}::" in errors[0]
