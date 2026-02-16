"""실제 faster-whisper 모델을 사용한 통합 테스트.

- chunk_length=10 인자가 에러 없이 동작하는지
- 취소 플래그 설정 시 transcribe 루프가 실제로 빠져나오는지
- _on_start 중복 호출 방지 가드 동작 확인
"""

from __future__ import annotations

import tempfile
import threading
import time
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


class TestChunkLengthCompatibility:
    """chunk_length=10이 설치된 faster-whisper에서 에러 없이 동작하는지 검증."""

    def test_chunk_length_accepted_by_transcribe(self) -> None:
        """WhisperModel.transcribe()가 chunk_length를 인자로 받을 수 있는지."""
        import inspect
        from faster_whisper import WhisperModel
        sig = inspect.signature(WhisperModel.transcribe)
        assert "chunk_length" in sig.parameters, (
            f"설치된 faster-whisper({__import__('faster_whisper').__version__})에 "
            "chunk_length 인자가 없음"
        )

    def test_batch_size_not_in_whisper_model(self) -> None:
        """WhisperModel.transcribe()에 batch_size가 없는지 확인 (있으면 넘겨도 되지만 현재 코드는 안 넘김)."""
        import inspect
        from faster_whisper import WhisperModel
        sig = inspect.signature(WhisperModel.transcribe)
        # batch_size가 있든 없든 우리 코드는 넘기지 않으므로, 이건 정보 확인용
        has_batch_size = "batch_size" in sig.parameters
        print(f"  WhisperModel.transcribe() has batch_size: {has_batch_size}")

    def test_transcribe_with_real_model_and_silence(self) -> None:
        """실제 tiny 모델 + 3초 무음 WAV로 transcribe 호출 (chunk_length=10 포함)."""
        from faster_whisper import WhisperModel

        # 3초 무음 WAV 생성
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = Path(f.name)
        sr = 16000
        duration_sec = 3
        samples = np.zeros(sr * duration_sec, dtype=np.int16)
        with wave.open(str(wav_path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(samples.tobytes())

        model = None
        try:
            model = WhisperModel("tiny", device="cpu", compute_type="int8")
            # chunk_length=10 포함 호출 — TypeError 나면 테스트 실패
            segments_iter, info = model.transcribe(
                str(wav_path),
                language="ko",
                vad_filter=True,
                chunk_length=10,
            )
            # 이터레이터 소비 (무음이라 세그먼트 0~1개)
            segments = list(segments_iter)
            assert isinstance(segments, list)
            print(f"  segments: {len(segments)}, duration: {info.duration:.1f}s")
        finally:
            wav_path.unlink(missing_ok=True)
            if model is not None:
                del model


class TestCancelWithRealModel:
    """실제 모델로 취소가 동작하는지 검증."""

    def test_cancel_stops_transcription(self) -> None:
        """취소 플래그 설정 시 세그먼트 루프가 즉시 중단되는지."""
        from faster_whisper import WhisperModel
        from src.services.whisper_service import transcribe

        # 5초 사인파 WAV 생성 (무음이면 VAD가 전부 건너뛰므로 약간의 소리 필요)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = Path(f.name)
        sr = 16000
        duration_sec = 5
        t = np.linspace(0, duration_sec, sr * duration_sec, dtype=np.float32)
        samples = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)
        with wave.open(str(wav_path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(samples.tobytes())

        model = None
        try:
            model = WhisperModel("tiny", device="cpu", compute_type="int8")
            cancelled = [False]
            segment_count = [0]

            def on_seg(seg):
                segment_count[0] += 1
                # 첫 세그먼트 받자마자 취소
                cancelled[0] = True

            track = transcribe(
                model,
                wav_path,
                language="ko",
                on_segment=on_seg,
                check_cancelled=lambda: cancelled[0],
            )
            # 취소됐으므로 세그먼트 수가 매우 적어야 함 (1개)
            assert len(track.segments) <= 1, (
                f"취소 후 세그먼트가 {len(track.segments)}개 — 취소가 제대로 반영되지 않음"
            )
            print(f"  cancelled after {len(track.segments)} segment(s) ✓")
        finally:
            if model:
                del model
            wav_path.unlink(missing_ok=True)


class TestOnStartGuard:
    """_on_start 중복 호출 방지 가드 — 코드 레벨 확인 (Qt 없이)."""

    def test_on_start_has_guard_in_source(self) -> None:
        """_on_start 메서드 소스에 isRunning 가드가 있는지 확인."""
        import inspect
        from src.ui.dialogs.whisper_dialog import WhisperDialog
        source = inspect.getsource(WhisperDialog._on_start)
        assert "isRunning" in source, "_on_start에 isRunning 가드가 없음"
        assert "return" in source.split("isRunning")[1][:50], "_on_start에 isRunning 후 return이 없음"
        print("  _on_start guard exists in source ✓")
