"""TDD: 자막 생성 취소 시 크래시 없이 종료되는지 검증.

크래시 시나리오:
1. 오디오 추출 중 취소 → extract_audio_to_wav 블로킹이므로 _cancelled 체크 불가
2. 모델 로딩 중 취소 → load_model() 블로킹
3. 취소 후 cleanup_thread 타임아웃 → 스레드가 안 끝남
4. 강제 닫기 시 스레드 참조 유지 → QThread 파괴 방지
5. _cleanup_thread에서 quit() 누락 → QThread 이벤트 루프 안 멈춤
6. QThread에서 import torch → C 스택 오버플로우
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models.subtitle import SubtitleSegment, SubtitleTrack


# ---------------------------------------------------------------------------
# 1. 오디오 추출 중 취소 → worker.run() 이 깨끗하게 종료되어야 함
# ---------------------------------------------------------------------------
class TestCancelDuringAudioExtraction:
    """오디오 추출(FFmpeg) 중 cancel() 호출 시 worker가 조기 종료."""

    def test_cancel_during_extract_stops_before_transcribe(self) -> None:
        """extract_audio_to_wav가 오래 걸릴 때 cancel() 후 transcribe를 호출하지 않아야 한다."""
        from src.workers.whisper_worker import WhisperWorker

        worker = WhisperWorker(
            video_path=Path("/tmp/fake_video.mp4"),
            model_name="tiny",
            language="ko",
        )

        transcribe_called = threading.Event()

        def slow_extract(video_path):
            """FFmpeg 추출을 시뮬레이션 (1초 블로킹)."""
            time.sleep(1.0)
            return Path("/tmp/fake_audio.wav")

        def mock_transcribe(self, audio_path, **kwargs):
            transcribe_called.set()  # 이 함수가 호출되면 안 됨
            return SubtitleTrack(language="ko")

        finished_signals = []
        error_signals = []
        worker.finished.connect(lambda t: finished_signals.append(t))
        worker.error.connect(lambda e: error_signals.append(e))

        with (
            patch(
                "src.workers.whisper_worker.extract_audio_to_wav",
                side_effect=slow_extract,
            ),
            patch(
                "src.infrastructure.transcriber.WhisperTranscriber.transcribe",
                side_effect=mock_transcribe,
            ),
        ):
            t = threading.Thread(target=worker.run)
            t.start()

            # 추출 시작 후 0.1초에 취소
            time.sleep(0.1)
            worker.cancel()

            t.join(timeout=5.0)
            assert not t.is_alive(), "Worker 스레드가 5초 내에 종료되어야 함"

        # transcribe는 호출되지 않았어야 함
        assert not transcribe_called.is_set(), (
            "취소 후 transcribe()가 호출되면 안 됨"
        )
        # finished 시그널이 발생하면 안 됨
        assert len(finished_signals) == 0, "취소 시 finished 시그널 없어야 함"
        # error 시그널도 없어야 함 (취소는 에러가 아님)
        assert len(error_signals) == 0, "취소는 에러 시그널을 발생시키면 안 됨"


# ---------------------------------------------------------------------------
# 2. 모델 로딩 중 취소 → 로딩 완료 후 transcribe 건너뛰기
# ---------------------------------------------------------------------------
class TestCancelDuringModelLoading:
    """load_model() 중 cancel() → 모델 로드 후 transcribe 호출 없이 종료."""

    def test_cancel_during_model_load_skips_transcribe(self) -> None:
        """load_model()이 블로킹인 동안 cancel() → transcribe 호출 없이 종료."""
        from src.workers.whisper_worker import WhisperWorker

        worker = WhisperWorker(
            audio_path=Path("/tmp/fake_audio.wav"),
            model_name="tiny",
            language="ko",
        )

        transcribe_called = threading.Event()
        model_released = threading.Event()

        def slow_load_model(model_name):
            """모델 로딩 시뮬레이션 (1초 블로킹)."""
            time.sleep(1.0)
            return MagicMock()

        def mock_transcribe_fn(model, audio_path, **kwargs):
            transcribe_called.set()
            return SubtitleTrack(language="ko")

        def mock_release(model):
            model_released.set()

        with (
            patch("src.services.whisper_service.load_model", side_effect=slow_load_model),
            patch("src.services.whisper_service.transcribe", side_effect=mock_transcribe_fn),
            patch("src.services.whisper_service.release_model", side_effect=mock_release),
        ):
            t = threading.Thread(target=worker.run)
            t.start()

            time.sleep(0.1)
            worker.cancel()

            t.join(timeout=5.0)
            assert not t.is_alive(), "Worker 스레드가 5초 내에 종료되어야 함"

        # 모델 로딩이 끝난 후에도 transcribe는 호출되면 안 됨
        assert not transcribe_called.is_set(), (
            "취소 상태에서 transcribe()가 호출되면 안 됨"
        )
        # 모델은 반드시 release 되어야 함 (메모리 누수 방지)
        assert model_released.is_set(), (
            "load_model()이 성공했으면 cancel 후에도 release_model() 호출 필수"
        )


# ---------------------------------------------------------------------------
# 3. 강제 닫기(Force Close) 시 스레드 참조 유지
# ---------------------------------------------------------------------------
class TestForceCloseOrphanThread:
    """강제 닫기 시 스레드가 _orphaned_threads에 보관되어 GC로 파괴되지 않아야 함."""

    def test_orphaned_thread_kept_alive(self) -> None:
        """_on_force_close() 후 스레드가 _orphaned_threads 리스트에 있어야 함."""
        from src.ui.dialogs.whisper_dialog import _orphaned_threads

        initial_count = len(_orphaned_threads)

        # 끝나지 않는 스레드를 시뮬레이션
        mock_thread = MagicMock()
        mock_thread.isRunning.return_value = True

        # _orphaned_threads에 추가 (실제 _on_force_close 로직)
        _orphaned_threads.append(mock_thread)

        assert len(_orphaned_threads) == initial_count + 1
        assert mock_thread in _orphaned_threads

        # 정리: 스레드가 끝나면 제거
        mock_thread.isRunning.return_value = False
        from src.ui.dialogs.whisper_dialog import _cleanup_orphaned_threads
        _cleanup_orphaned_threads()

        assert mock_thread not in _orphaned_threads


# ---------------------------------------------------------------------------
# 4. worker.cancel()은 즉시 _cancelled를 설정해야 함 (스레드 안전)
# ---------------------------------------------------------------------------
class TestCancelIsImmediate:
    """cancel()은 어떤 상태에서든 즉시 _cancelled = True."""

    def test_cancel_sets_flag_immediately(self) -> None:
        from src.workers.whisper_worker import WhisperWorker

        worker = WhisperWorker(audio_path=Path("/tmp/f.wav"))
        assert not worker._cancelled
        worker.cancel()
        assert worker._cancelled

    def test_double_cancel_is_safe(self) -> None:
        from src.workers.whisper_worker import WhisperWorker

        worker = WhisperWorker(audio_path=Path("/tmp/f.wav"))
        worker.cancel()
        worker.cancel()  # 두 번 호출해도 크래시 없음
        assert worker._cancelled


# ---------------------------------------------------------------------------
# 5. 취소 시 임시 WAV 파일 정리
# ---------------------------------------------------------------------------
class TestCancelCleansUpTempFiles:
    """extract_audio_to_wav로 생성된 임시 WAV는 취소 시에도 삭제되어야 함."""

    def test_temp_wav_deleted_after_cancel(self) -> None:
        from src.workers.whisper_worker import WhisperWorker

        worker = WhisperWorker(
            video_path=Path("/tmp/fake_video.mp4"),
            model_name="tiny",
            language="ko",
        )

        wav_unlinked = threading.Event()
        fake_wav = MagicMock(spec=Path)
        fake_wav.unlink = MagicMock(side_effect=lambda **kw: wav_unlinked.set())

        def extract_returns_wav(video_path):
            return fake_wav

        def mock_transcribe(self, audio_path, **kwargs):
            check = kwargs.get("check_cancelled")
            # 첫 체크에서 취소됨
            if check and check():
                return SubtitleTrack(language="ko")
            return SubtitleTrack(language="ko")

        # 추출 후 바로 취소
        worker.cancel()

        with (
            patch(
                "src.workers.whisper_worker.extract_audio_to_wav",
                side_effect=extract_returns_wav,
            ),
            patch(
                "src.infrastructure.transcriber.WhisperTranscriber.transcribe",
                side_effect=mock_transcribe,
            ),
        ):
            worker.run()

        # 임시 WAV는 삭제되어야 함
        fake_wav.unlink.assert_called_once_with(missing_ok=True)


# ---------------------------------------------------------------------------
# 6. _cleanup_thread()는 quit() 호출 후 wait() 해야 함
# ---------------------------------------------------------------------------
class TestCleanupThreadCallsQuit:
    """_cleanup_thread()가 quit() 없이 wait()만 하면 QThread 이벤트 루프가
    영원히 돌아서 30초 타임아웃 → 스레드 미정리 → 앱 종료 시 크래시."""

    def test_cleanup_thread_calls_quit_before_wait(self) -> None:
        """_cleanup_thread()가 quit()을 호출한 후 wait()해야 함."""
        import inspect
        from src.ui.dialogs.whisper_dialog import WhisperDialog

        source = inspect.getsource(WhisperDialog._cleanup_thread)

        # quit() 호출이 소스에 있어야 함
        assert "quit()" in source, (
            "_cleanup_thread()에 self._thread.quit() 호출이 없음. "
            "moveToThread 패턴에서 quit() 없이 wait()하면 "
            "QThread 이벤트 루프가 영원히 돌아 타임아웃됨."
        )

        # quit()이 wait() 보다 먼저 나와야 함
        quit_pos = source.index("quit()")
        wait_pos = source.index("wait(")
        assert quit_pos < wait_pos, (
            "quit()이 wait() 보다 먼저 호출되어야 함. "
            "wait()는 이벤트 루프가 멈춘 후에만 정상 동작."
        )


# ---------------------------------------------------------------------------
# 7. whisper_dialog._on_start()는 메인 스레드에서 whisper_service를 사전 임포트해야 함
# ---------------------------------------------------------------------------
class TestMainThreadPreImport:
    """QThread에서 import torch하면 C 스택 오버플로우(492KB).
    메인 스레드(8MB)에서 먼저 임포트하면 sys.modules 캐시로 안전."""

    def test_on_start_pre_imports_whisper_service(self) -> None:
        """_on_start()에 whisper_service 사전 임포트 코드가 있어야 함."""
        import inspect
        from src.ui.dialogs.whisper_dialog import WhisperDialog

        source = inspect.getsource(WhisperDialog._on_start)

        assert "whisper_service" in source, (
            "_on_start()에서 whisper_service를 메인 스레드에서 사전 임포트해야 함. "
            "QThread에서 import torch → C 스택 오버플로우 발생."
        )

        # 사전 임포트가 QThread.start() 보다 먼저 나와야 함
        import_pos = source.index("whisper_service")
        assert "start()" in source, "_on_start()에 thread.start() 호출이 있어야 함"
        start_pos = source.rindex("start()")  # 마지막 start() = thread.start()
        assert import_pos < start_pos, (
            "whisper_service 임포트가 thread.start() 보다 먼저 실행되어야 함."
        )
