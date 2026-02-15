"""자막 생성(Whisper) 예외 시나리오 테스트.

- 존재하지 않는 오디오 파일 → error 시그널
- 오디오 추출 실패(비디오 없음/FFmpeg 실패) → error 시그널
- transcribe 단계에서 예외 → error 시그널

Qt GUI(qapp) 없이 모킹으로 검증해 샌드박스/헤드리스에서도 동작.
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import patch

import pytest


class TestWhisperWorkerExceptionScenarios:
    """WhisperWorker가 예외 발생 시 error 시그널을 emit하는지 검증."""

    def test_worker_emits_error_when_audio_file_missing(self) -> None:
        """존재하지 않는 오디오 파일로 transcribe 시도 시 예외 → error 시그널 emit."""
        from src.workers.whisper_worker import WhisperWorker

        worker = WhisperWorker(
            audio_path=Path("/nonexistent_audio_12345.wav"),
            model_name="tiny",
            language="ko",
        )
        errors = []

        def on_error(msg: str) -> None:
            errors.append(msg)

        worker.error.connect(on_error)

        # QCoreApplication으로 시그널 전달 (GUI 없이, macOS 크래시 회피)
        from PySide6.QtCore import QCoreApplication
        app = QCoreApplication.instance() or QCoreApplication([])

        # transcribe 단계에서 FileNotFoundError 나도록 mock (실제 모델 로드 없이 빠르게)
        with patch(
            "src.workers.whisper_worker.WhisperTranscriber",
        ) as MockTranscriber:
            mock_instance = MockTranscriber.return_value
            mock_instance.transcribe.side_effect = FileNotFoundError("No such file: /nonexistent_audio_12345.wav")

            def run_worker() -> None:
                worker.run()

            t = threading.Thread(target=run_worker)
            t.start()
            t.join(timeout=5.0)
            for _ in range(20):
                app.processEvents()
        assert len(errors) == 1, f"error 시그널 1회 emit. errors={errors}"
        assert "nonexistent" in errors[0] or "No such" in errors[0] or "file" in errors[0].lower()

    def test_worker_emits_error_when_video_extraction_fails(self) -> None:
        """extract_audio_to_wav가 실패(RuntimeError) 시 error 시그널 emit."""
        from src.workers.whisper_worker import WhisperWorker

        worker = WhisperWorker(
            video_path=Path("/some/video.mp4"),
            model_name="tiny",
            language="ko",
        )
        errors = []

        def on_error(msg: str) -> None:
            errors.append(msg)

        worker.error.connect(on_error)

        from PySide6.QtCore import QCoreApplication
        app = QCoreApplication.instance() or QCoreApplication([])

        with patch(
            "src.workers.whisper_worker.extract_audio_to_wav",
            side_effect=RuntimeError("FFmpeg failed:\nNo such file"),
        ):
            def run_worker() -> None:
                worker.run()

            t = threading.Thread(target=run_worker)
            t.start()
            t.join(timeout=5.0)
            for _ in range(10):
                app.processEvents()
        assert len(errors) == 1, f"error 시그널 1회만 emit. errors={errors}"
        assert "FFmpeg" in errors[0] or "failed" in errors[0].lower()

    def test_worker_emits_error_when_transcribe_raises(self) -> None:
        """transcribe 단계에서 예외 발생 시 error 시그널 emit."""
        from src.workers.whisper_worker import WhisperWorker

        worker = WhisperWorker(
            audio_path=Path("/tmp/fake.wav"),  # 존재하지 않아도 mock으로 transcribe까지 감
            model_name="tiny",
            language="ko",
        )
        errors = []

        def on_error(msg: str) -> None:
            errors.append(msg)

        worker.error.connect(on_error)

        from PySide6.QtCore import QCoreApplication
        app = QCoreApplication.instance() or QCoreApplication([])

        with patch("src.workers.whisper_worker.extract_audio_to_wav", return_value=Path("/tmp/fake.wav")):
            with patch(
                "src.workers.whisper_worker.WhisperTranscriber",
            ) as MockTranscriber:
                mock_instance = MockTranscriber.return_value
                mock_instance.transcribe.side_effect = ValueError("Parser stack overflowed - Python source too complex")

                def run_worker() -> None:
                    worker.run()

                t = threading.Thread(target=run_worker)
                t.start()
                t.join(timeout=5.0)
                for _ in range(10):
                    app.processEvents()
        assert len(errors) == 1, f"error 시그널 1회만 emit. errors={errors}"
        assert "Parser" in errors[0] or "complex" in errors[0] or "ValueError" in errors[0]
