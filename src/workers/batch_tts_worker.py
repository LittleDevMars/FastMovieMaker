"""배치 TTS 생성 백그라운드 워커.

여러 .txt 파일을 한 번에 TTS 변환하여 .mp3 + .srt 쌍을 출력한다.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, Signal

from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.services.audio_merger import AudioMerger
from src.services.subtitle_exporter import export_srt
from src.services.text_splitter import SplitStrategy, TextSplitter
from src.services.tts_service import TTSService


@dataclass(slots=True)
class BatchTtsJob:
    """배치 TTS 단일 작업 정보."""

    txt_path: Path
    output_dir: Path


@dataclass(slots=True)
class BatchTtsResult:
    """배치 TTS 단일 작업 결과."""

    job: BatchTtsJob
    audio_path: Optional[str] = None   # 성공 시 mp3 경로
    srt_path: Optional[str] = None     # 성공 시 srt 경로
    error: Optional[str] = None        # 실패 시 에러 메시지

    @property
    def success(self) -> bool:
        return self.error is None and self.audio_path is not None


class BatchTtsWorker(QObject):
    """여러 .txt 파일을 순차적으로 TTS 변환한다.

    Signals:
        job_started(int):                  작업 인덱스.
        job_finished(int, object):         (인덱스, BatchTtsResult).
        progress(int, int, int, int):      (job_idx, job_total, seg_cur, seg_total).
        all_finished(list):                list[BatchTtsResult].
        error(str):                        치명적 오류 메시지.
    """

    job_started = Signal(int)
    job_finished = Signal(int, object)   # (index, BatchTtsResult)
    progress = Signal(int, int, int, int)  # (job_idx, job_total, seg_cur, seg_total)
    all_finished = Signal(list)
    error = Signal(str)

    def __init__(
        self,
        jobs: List[BatchTtsJob],
        voice: str = "ko-KR-SunHiNeural",
        rate: str = "+0%",
        strategy: SplitStrategy = SplitStrategy.SENTENCE,
    ) -> None:
        """
        Args:
            jobs:     처리할 작업 목록.
            voice:    TTS 음성 이름.
            rate:     음성 속도 (edge-tts 형식, e.g. "+0%").
            strategy: 텍스트 분할 전략.
        """
        super().__init__()
        self._jobs = jobs
        self._voice = voice
        self._rate = rate
        self._strategy = strategy
        self._cancelled = False

    def cancel(self) -> None:
        """처리 취소 요청."""
        self._cancelled = True

    def run(self) -> None:
        """모든 작업을 순차적으로 처리한다."""
        try:
            asyncio.run(self._run_async())
        except Exception as exc:
            if not self._cancelled:
                self.error.emit(f"배치 TTS 실패: {exc}")

    async def _run_async(self) -> None:
        results: List[BatchTtsResult] = []
        total_jobs = len(self._jobs)

        for job_idx, job in enumerate(self._jobs):
            if self._cancelled:
                break

            self.job_started.emit(job_idx)
            result = await self._process_job(job_idx, total_jobs, job)
            results.append(result)
            self.job_finished.emit(job_idx, result)

        self.all_finished.emit(results)

    async def _process_job(
        self,
        job_idx: int,
        total_jobs: int,
        job: BatchTtsJob,
    ) -> BatchTtsResult:
        """단일 .txt 파일을 처리한다."""
        temp_dir: Optional[Path] = None
        try:
            # 텍스트 읽기
            text = job.txt_path.read_text(encoding="utf-8")
            if not text.strip():
                return BatchTtsResult(job=job, error="파일이 비어 있습니다.")

            # 텍스트 분할
            splitter = TextSplitter()
            text_segments = splitter.split(text, self._strategy)
            if not text_segments:
                return BatchTtsResult(job=job, error="분할된 세그먼트가 없습니다.")

            total_segs = len(text_segments)
            temp_dir = Path(tempfile.mkdtemp(prefix="batch_tts_"))

            # TTS 생성
            def on_seg_progress(cur: int, tot: int) -> None:
                self.progress.emit(job_idx, total_jobs, cur, tot)

            self.progress.emit(job_idx, total_jobs, 0, total_segs)

            segments_data = [(seg.text, seg.index) for seg in text_segments]
            audio_segments = await TTSService.generate_segments(
                segments=segments_data,
                voice=self._voice,
                rate=self._rate,
                output_dir=temp_dir,
                on_progress=on_seg_progress,
            )

            if self._cancelled:
                return BatchTtsResult(job=job, error="취소됨")

            # 오디오 병합
            merged_path = temp_dir / "merged.mp3"
            AudioMerger.merge_audio_files(
                audio_files=[seg.audio_path for seg in audio_segments],
                output_path=merged_path,
                add_silence_ms=0,
            )

            # 영구 저장
            job.output_dir.mkdir(parents=True, exist_ok=True)
            stem = job.txt_path.stem
            session_id = uuid.uuid4().hex[:8]
            final_mp3 = job.output_dir / f"{stem}_{session_id}.mp3"
            shutil.copy2(merged_path, final_mp3)

            # SRT 생성
            track = SubtitleTrack()
            current_ms = 0
            for audio_seg in audio_segments:
                dur_ms = int(audio_seg.duration_sec * 1000)
                track.add_segment(
                    SubtitleSegment(
                        start_ms=current_ms,
                        end_ms=current_ms + dur_ms,
                        text=audio_seg.text,
                    )
                )
                current_ms += dur_ms

            srt_path = job.output_dir / f"{stem}_{session_id}.srt"
            export_srt(track, srt_path)

            return BatchTtsResult(
                job=job,
                audio_path=str(final_mp3),
                srt_path=str(srt_path),
            )

        except Exception as exc:
            return BatchTtsResult(job=job, error=str(exc))

        finally:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
