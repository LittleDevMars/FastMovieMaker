"""TTS 타이밍 검증 백그라운드 워커.

TTS 오디오를 Whisper로 재전사한 뒤, TtsVerifier로 보정 목록을 생성한다.
QObject + moveToThread 패턴을 사용한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtCore import QObject, Signal

from src.models.subtitle import SubtitleTrack
from src.services.tts_verifier import CorrectionResult, TtsVerifier


class TtsVerifyWorker(QObject):
    """Whisper 재전사 + 타이밍 비교를 백그라운드에서 실행한다.

    Signals:
        status_update(str):       상태 메시지.
        progress(int, int):       (현재 단계, 전체 단계).
        finished(list):           list[CorrectionResult] — 보정 목록.
        error(str):               오류 메시지.
    """

    status_update = Signal(str)
    progress = Signal(int, int)
    finished = Signal(list)   # list[CorrectionResult]
    error = Signal(str)

    def __init__(
        self,
        audio_path: Path,
        original_track: SubtitleTrack,
        model_name: str = "base",
        language: str = "ko",
    ) -> None:
        """
        Args:
            audio_path:     검증할 TTS 병합 오디오 경로 (.mp3 / .wav).
            original_track: 보정 대상 원본 자막 트랙.
            model_name:     Whisper 모델 이름 (tiny/base/small).
            language:       전사 언어 코드.
        """
        super().__init__()
        self._audio_path = Path(audio_path)
        self._original_track = original_track
        self._model_name = model_name
        self._language = language
        self._cancelled = False

    def cancel(self) -> None:
        """작업 취소 요청."""
        self._cancelled = True

    def run(self) -> None:
        """Whisper 전사 → TtsVerifier 보정 순으로 실행."""
        try:
            # 단계 1: 오디오 파일 확인
            self.status_update.emit("오디오 파일 확인 중...")
            self.progress.emit(0, 3)

            if not self._audio_path.exists():
                self.error.emit(f"오디오 파일을 찾을 수 없습니다: {self._audio_path}")
                return

            if self._cancelled:
                return

            # 단계 2: Whisper 전사
            self.status_update.emit(f"Whisper ({self._model_name}) 전사 중...")
            self.progress.emit(1, 3)

            from src.infrastructure.transcriber import WhisperTranscriber

            transcriber = WhisperTranscriber()
            whisper_track: SubtitleTrack = transcriber.transcribe(
                self._audio_path,
                language=self._language,
                model_name=self._model_name,
                check_cancelled=lambda: self._cancelled,
            )

            if self._cancelled:
                return

            # 단계 3: 타이밍 비교 및 보정 목록 생성
            self.status_update.emit("타이밍 비교 중...")
            self.progress.emit(2, 3)

            corrections: List[CorrectionResult] = TtsVerifier.verify_and_align(
                self._original_track, whisper_track
            )

            self.progress.emit(3, 3)
            self.status_update.emit("검증 완료")
            self.finished.emit(corrections)

        except Exception as exc:
            if not self._cancelled:
                self.error.emit(f"TTS 타이밍 검증 실패: {exc}")
