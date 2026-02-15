"""자막 생성(Whisper) 취소 동작 검증.

- transcribe()에서 check_cancelled 시 중단되는지
- WhisperWorker.cancel() 호출 시 run()이 정상 종료되는지
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.services.whisper_service import transcribe
from src.utils.time_utils import seconds_to_ms


class TestTranscribeCancel:
    """transcribe()가 check_cancelled 시 루프를 빠져나오는지 검증."""

    def test_check_cancelled_breaks_loop(self) -> None:
        """check_cancelled가 True를 반환하면 즉시 중단하고 지금까지의 트랙을 반환."""
        # fake segment (faster_whisper Segment-like)
        class FakeSeg:
            def __init__(self, start: float, end: float, text: str):
                self.start = start
                self.end = end
                self.text = text

        call_count = 0

        def check_after_two() -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 2

        def fake_iterator():
            for i in range(10):
                yield FakeSeg(i * 1.0, (i + 1) * 1.0, f"segment {i}")

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (fake_iterator(), MagicMock())

        track = transcribe(
            mock_model,
            Path("/tmp/fake.wav"),
            language="ko",
            check_cancelled=check_after_two,
        )

        assert len(track.segments) == 1
        assert track.segments[0].text == "segment 0"
        assert call_count == 2

    def test_check_cancelled_none_runs_full(self) -> None:
        """check_cancelled가 None이면 전체 이터레이션."""
        class FakeSeg:
            def __init__(self, start: float, end: float, text: str):
                self.start = start
                self.end = end
                self.text = text

        def fake_iterator():
            for i in range(3):
                yield FakeSeg(i * 1.0, (i + 1) * 1.0, f"seg{i}")

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (fake_iterator(), MagicMock())

        track = transcribe(
            mock_model,
            Path("/tmp/fake.wav"),
            language="ko",
            check_cancelled=None,
        )

        assert len(track.segments) == 3


class TestWhisperWorkerCancel:
    """WhisperWorker.cancel() 호출 시 run()이 종료되는지 검증 (목 사용)."""

    def test_worker_run_exits_after_cancel(self) -> None:
        """run() 내부에서 transcribe가 check_cancelled로 중단되면 run()이 정상 반환."""
        from src.workers.whisper_worker import WhisperWorker

        wav_path = Path("/tmp/test_whisper_cancel_fake.wav")
        worker = WhisperWorker(audio_path=wav_path, model_name="tiny", language="ko")

        yield_count = [0]

        def mock_transcribe(
            self,
            audio_path,
            *,
            language=None,
            model_name=None,
            on_progress=None,
            on_segment=None,
            check_cancelled=None,
        ):
            from src.models.subtitle import SubtitleSegment
            track = SubtitleTrack(language=language or "ko")
            for i in range(20):
                yield_count[0] += 1
                if check_cancelled and check_cancelled():
                    break
                seg = type("Seg", (), {"start": i * 1.0, "end": (i + 1) * 1.0, "text": f"s{i}"})()
                track.add_segment(SubtitleSegment(
                    start_ms=int(seg.start * 1000),
                    end_ms=int(seg.end * 1000),
                    text=seg.text,
                ))
                if on_segment:
                    on_segment(track.segments[-1])
                time.sleep(0.05)
            return track

        with patch("src.workers.whisper_worker.extract_audio_to_wav", return_value=wav_path):
            with patch(
                "src.infrastructure.transcriber.WhisperTranscriber.transcribe",
                side_effect=mock_transcribe,
            ):
                result = [None]
                err = [None]

                def run_in_thread():
                    try:
                        worker.run()
                        result[0] = "done"
                    except Exception as e:
                        err[0] = e

                t = threading.Thread(target=run_in_thread)
                t.start()
                time.sleep(0.2)
                worker.cancel()
                t.join(timeout=5.0)
                assert t.is_alive() is False, "Worker thread should exit after cancel"
                assert result[0] == "done", f"run() should finish normally, err={err[0]}"
                assert yield_count[0] <= 5, "Should have stopped soon after cancel (few yields)"
