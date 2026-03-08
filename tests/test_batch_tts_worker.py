"""tests/test_batch_tts_worker.py — BatchTtsWorker + 데이터 구조 단위 테스트."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.tts_provider import TTSRequestErrorCode
from src.workers.batch_tts_worker import BatchTtsJob, BatchTtsResult, BatchTtsWorker
from src.services.text_splitter import SplitStrategy


# ─────────────────────── BatchTtsJob ───────────────────────

class TestBatchTtsJobFields:
    def test_batch_tts_job_fields(self):
        job = BatchTtsJob(
            txt_path=Path("/tmp/test.txt"),
            output_dir=Path("/tmp/out"),
        )
        assert job.txt_path == Path("/tmp/test.txt")
        assert job.output_dir == Path("/tmp/out")


# ─────────────────────── BatchTtsResult ───────────────────────

class TestBatchTtsResultFields:
    def test_batch_tts_result_success(self):
        job = BatchTtsJob(Path("/tmp/a.txt"), Path("/tmp/out"))
        result = BatchTtsResult(
            job=job,
            audio_path="/tmp/out/a.mp3",
            srt_path="/tmp/out/a.srt",
        )
        assert result.success is True
        assert result.error is None

    def test_batch_tts_result_failure(self):
        job = BatchTtsJob(Path("/tmp/a.txt"), Path("/tmp/out"))
        result = BatchTtsResult(job=job, error="연결 오류")
        assert result.success is False
        assert result.audio_path is None
        assert result.srt_path is None

    def test_batch_tts_result_default_none(self):
        job = BatchTtsJob(Path("/tmp/a.txt"), Path("/tmp/out"))
        result = BatchTtsResult(job=job)
        assert result.success is False  # audio_path is None


# ─────────────────────── BatchTtsWorker ───────────────────────

def _make_worker(
    jobs: list[BatchTtsJob],
    voice: str = "ko-KR-SunHiNeural",
    speed: float = 1.0,
    engine: str = "edge_tts",
) -> BatchTtsWorker:
    return BatchTtsWorker(jobs=jobs, voice=voice, speed=speed, engine=engine)


class TestBatchTtsWorkerSignals:
    def test_worker_emits_job_finished(self, tmp_path):
        """job_finished 시그널이 각 작업마다 발송된다 (Mock TTSService)."""
        txt = tmp_path / "hello.txt"
        txt.write_text("안녕하세요. 반갑습니다.", encoding="utf-8")

        job = BatchTtsJob(txt_path=txt, output_dir=tmp_path)
        worker = _make_worker([job])

        finished_calls: list = []
        worker.job_finished.connect(lambda idx, r: finished_calls.append((idx, r)))

        # AudioSegment mock
        from src.services.tts_service import AudioSegment as TtsAudioSeg
        mock_audio_seg = MagicMock(spec=TtsAudioSeg)
        mock_audio_seg.audio_path = tmp_path / "seg0.mp3"
        mock_audio_seg.duration_sec = 1.0
        mock_audio_seg.text = "안녕하세요."
        # 실제 파일 생성 (AudioMerger.merge_audio_files 가 파일을 요구함)
        (tmp_path / "seg0.mp3").write_bytes(b"")

        with (
            patch("src.workers.batch_tts_worker.get_provider") as mock_get_provider,
            patch(
                "src.workers.batch_tts_worker.AudioMerger.merge_audio_files"
            ) as mock_merge,
        ):
            provider = MagicMock()
            provider.generate_segments = AsyncMock(return_value=[mock_audio_seg])
            mock_get_provider.return_value = provider
            # merge_audio_files 가 output_path 파일을 만든 것처럼 처리
            def _merge(audio_files, output_path, add_silence_ms=0):
                output_path.write_bytes(b"")
            mock_merge.side_effect = _merge

            worker.run()

        assert len(finished_calls) == 1
        idx, result = finished_calls[0]
        assert idx == 0
        provider.generate_segments.assert_awaited_once()

    def test_worker_emits_error_for_unknown_provider(self, tmp_path):
        txt = tmp_path / "hello.txt"
        txt.write_text("안녕하세요.", encoding="utf-8")
        job = BatchTtsJob(txt_path=txt, output_dir=tmp_path)
        worker = _make_worker([job], engine="unknown-provider")

        all_results: list = []
        worker.all_finished.connect(lambda r: all_results.extend(r))

        with patch("src.workers.batch_tts_worker.get_provider", return_value=None):
            worker.run()

        assert len(all_results) == 1
        assert all_results[0].success is False
        assert f"TTS_ERROR::{TTSRequestErrorCode.PROVIDER_UNAVAILABLE.value}::" in (all_results[0].error or "")

    def test_worker_provider_exception_is_reported(self, tmp_path):
        txt = tmp_path / "hello.txt"
        txt.write_text("안녕하세요.", encoding="utf-8")
        job = BatchTtsJob(txt_path=txt, output_dir=tmp_path)
        worker = _make_worker([job])

        all_results: list = []
        worker.all_finished.connect(lambda r: all_results.extend(r))

        provider = MagicMock()
        provider.generate_segments = AsyncMock(side_effect=RuntimeError("provider boom"))

        with patch("src.workers.batch_tts_worker.get_provider", return_value=provider):
            worker.run()

        assert len(all_results) == 1
        assert all_results[0].success is False
        assert "provider boom" in (all_results[0].error or "")

    def test_worker_emits_all_finished(self, tmp_path):
        """all_finished 시그널이 한 번 발송된다."""
        txt1 = tmp_path / "a.txt"
        txt1.write_text("안녕.", encoding="utf-8")
        txt2 = tmp_path / "b.txt"
        txt2.write_text("반가워.", encoding="utf-8")

        jobs = [
            BatchTtsJob(txt_path=txt1, output_dir=tmp_path),
            BatchTtsJob(txt_path=txt2, output_dir=tmp_path),
        ]
        worker = _make_worker(jobs)

        all_finished_calls: list = []
        worker.all_finished.connect(lambda r: all_finished_calls.append(r))

        from src.services.tts_service import AudioSegment as TtsAudioSeg

        def _fake_seg(text: str, idx: int, p: Path) -> MagicMock:
            seg = MagicMock(spec=TtsAudioSeg)
            seg_path = p / f"seg_{idx}.mp3"
            seg_path.write_bytes(b"")
            seg.audio_path = seg_path
            seg.duration_sec = 0.5
            seg.text = text
            return seg

        call_count = [0]

        async def _gen_segments(segments, voice, speed, output_dir, on_progress=None, **kw):
            res = [_fake_seg(t, i, tmp_path) for i, (t, _) in enumerate(segments)]
            call_count[0] += 1
            return res

        provider = MagicMock()
        provider.generate_segments = AsyncMock(side_effect=_gen_segments)

        with (
            patch("src.workers.batch_tts_worker.get_provider", return_value=provider),
            patch(
                "src.workers.batch_tts_worker.AudioMerger.merge_audio_files",
                side_effect=lambda audio_files, output_path, **kw: output_path.write_bytes(b""),
            ),
        ):
            worker.run()

        assert len(all_finished_calls) == 1
        assert len(all_finished_calls[0]) == 2

    def test_worker_cancel_mid_batch(self, tmp_path):
        """cancel() 호출 후 이후 작업은 처리하지 않는다."""
        txt_files = []
        for i in range(3):
            t = tmp_path / f"f{i}.txt"
            t.write_text("test", encoding="utf-8")
            txt_files.append(t)

        jobs = [BatchTtsJob(t, tmp_path) for t in txt_files]
        worker = _make_worker(jobs)

        started_indices: list[int] = []
        worker.job_started.connect(started_indices.append)

        from src.services.tts_service import AudioSegment as TtsAudioSeg

        call_count = [0]

        async def _gen_segments(segments, voice, speed, output_dir, on_progress=None, **kw):
            # 첫 번째 작업 처리 후 취소
            if call_count[0] == 0:
                worker.cancel()
            call_count[0] += 1
            seg = MagicMock(spec=TtsAudioSeg)
            p = tmp_path / f"seg_{call_count[0]}.mp3"
            p.write_bytes(b"")
            seg.audio_path = p
            seg.duration_sec = 0.5
            seg.text = "test"
            return [seg]

        with (
            patch("src.workers.batch_tts_worker.get_provider") as mock_get_provider,
            patch(
                "src.workers.batch_tts_worker.AudioMerger.merge_audio_files",
                side_effect=lambda audio_files, output_path, **kw: output_path.write_bytes(b""),
            ),
        ):
            provider = MagicMock()
            provider.generate_segments = AsyncMock(side_effect=_gen_segments)
            mock_get_provider.return_value = provider
            worker.run()

        # 취소 후에는 1개 이하만 처리됨
        assert len(started_indices) <= 2

    def test_worker_handles_empty_file(self, tmp_path):
        """빈 .txt 파일은 error 필드가 설정된 결과를 반환한다."""
        txt = tmp_path / "empty.txt"
        txt.write_text("", encoding="utf-8")

        job = BatchTtsJob(txt_path=txt, output_dir=tmp_path)
        worker = _make_worker([job])

        all_results: list = []
        worker.all_finished.connect(lambda r: all_results.extend(r))
        worker.run()

        assert len(all_results) == 1
        assert all_results[0].error is not None
        assert f"TTS_ERROR::{TTSRequestErrorCode.EMPTY_SCRIPT.value}::" in (all_results[0].error or "")

    def test_worker_handles_empty_segments(self, tmp_path):
        txt = tmp_path / "empty_segments.txt"
        txt.write_text("non-empty", encoding="utf-8")

        job = BatchTtsJob(txt_path=txt, output_dir=tmp_path)
        worker = _make_worker([job])

        all_results: list = []
        worker.all_finished.connect(lambda r: all_results.extend(r))
        with patch("src.workers.batch_tts_worker.TextSplitter.split", return_value=[]):
            worker.run()

        assert len(all_results) == 1
        assert all_results[0].success is False
        assert f"TTS_ERROR::{TTSRequestErrorCode.EMPTY_SEGMENTS.value}::" in (all_results[0].error or "")

    def test_worker_handles_invalid_speed(self, tmp_path):
        txt = tmp_path / "invalid_speed.txt"
        txt.write_text("hello", encoding="utf-8")
        job = BatchTtsJob(txt_path=txt, output_dir=tmp_path)
        worker = _make_worker([job], speed=9.9)

        all_results: list = []
        worker.all_finished.connect(lambda r: all_results.extend(r))

        provider = MagicMock()
        provider.generate_segments = AsyncMock(return_value=[])
        with patch("src.workers.batch_tts_worker.get_provider", return_value=provider):
            worker.run()

        assert len(all_results) == 1
        assert all_results[0].success is False
        assert f"TTS_ERROR::{TTSRequestErrorCode.INVALID_SPEED.value}::" in (all_results[0].error or "")

    def test_worker_handles_empty_voice(self, tmp_path):
        txt = tmp_path / "empty_voice.txt"
        txt.write_text("hello", encoding="utf-8")
        job = BatchTtsJob(txt_path=txt, output_dir=tmp_path)
        worker = _make_worker([job], voice="")

        all_results: list = []
        worker.all_finished.connect(lambda r: all_results.extend(r))

        provider = MagicMock()
        provider.generate_segments = AsyncMock(return_value=[])
        with patch("src.workers.batch_tts_worker.get_provider", return_value=provider):
            worker.run()

        assert len(all_results) == 1
        assert all_results[0].success is False
        assert f"TTS_ERROR::{TTSRequestErrorCode.VOICE_REQUIRED.value}::" in (all_results[0].error or "")

    def test_worker_saves_mp3_and_srt(self, tmp_path):
        """성공 시 .mp3 와 .srt 경로가 결과에 포함된다."""
        txt = tmp_path / "test.txt"
        txt.write_text("안녕하세요.", encoding="utf-8")

        job = BatchTtsJob(txt_path=txt, output_dir=tmp_path)
        worker = _make_worker([job])

        all_results: list = []
        worker.all_finished.connect(lambda r: all_results.extend(r))

        from src.services.tts_service import AudioSegment as TtsAudioSeg
        mock_seg = MagicMock(spec=TtsAudioSeg)
        seg_path = tmp_path / "seg0.mp3"
        seg_path.write_bytes(b"")
        mock_seg.audio_path = seg_path
        mock_seg.duration_sec = 1.0
        mock_seg.text = "안녕하세요."

        with (
            patch("src.workers.batch_tts_worker.get_provider") as mock_get_provider,
            patch(
                "src.workers.batch_tts_worker.AudioMerger.merge_audio_files",
                side_effect=lambda audio_files, output_path, **kw: output_path.write_bytes(b""),
            ),
        ):
            provider = MagicMock()
            provider.generate_segments = AsyncMock(return_value=[mock_seg])
            mock_get_provider.return_value = provider
            worker.run()

        assert len(all_results) == 1
        r = all_results[0]
        assert r.audio_path is not None
        assert r.srt_path is not None
        assert r.audio_path.endswith(".mp3")
        assert r.srt_path.endswith(".srt")

    def test_worker_progress_per_segment(self, tmp_path):
        """세그먼트별로 progress 시그널이 발송된다."""
        txt = tmp_path / "t.txt"
        txt.write_text("첫 번째. 두 번째. 세 번째.", encoding="utf-8")

        job = BatchTtsJob(txt_path=txt, output_dir=tmp_path)
        worker = _make_worker([job])

        progress_calls: list[tuple] = []
        worker.progress.connect(lambda ji, jt, sc, st: progress_calls.append((ji, jt, sc, st)))

        from src.services.tts_service import AudioSegment as TtsAudioSeg

        call_step = [0]

        async def _gen_segments(segments, voice, speed, output_dir, on_progress=None, **kw):
            segs = []
            for i, (t, idx) in enumerate(segments):
                p = tmp_path / f"seg_{call_step[0]}_{i}.mp3"
                p.write_bytes(b"")
                seg = MagicMock(spec=TtsAudioSeg)
                seg.audio_path = p
                seg.duration_sec = 0.5
                seg.text = t
                if on_progress:
                    on_progress(i + 1, len(segments))
                segs.append(seg)
            call_step[0] += 1
            return segs

        with (
            patch("src.workers.batch_tts_worker.get_provider") as mock_get_provider,
            patch(
                "src.workers.batch_tts_worker.AudioMerger.merge_audio_files",
                side_effect=lambda audio_files, output_path, **kw: output_path.write_bytes(b""),
            ),
        ):
            provider = MagicMock()
            provider.generate_segments = AsyncMock(side_effect=_gen_segments)
            mock_get_provider.return_value = provider
            worker.run()

        # progress 시그널이 최소 1번 이상 발송됨
        assert len(progress_calls) >= 1

    def test_worker_one_file_failure_continues(self, tmp_path):
        """한 파일이 실패해도 나머지 작업은 계속 처리된다."""
        txt_good = tmp_path / "good.txt"
        txt_good.write_text("안녕하세요.", encoding="utf-8")
        txt_bad = tmp_path / "bad.txt"
        txt_bad.write_text("실패할 파일", encoding="utf-8")

        jobs = [
            BatchTtsJob(txt_path=txt_good, output_dir=tmp_path),
            BatchTtsJob(txt_path=txt_bad, output_dir=tmp_path),
        ]
        worker = _make_worker(jobs)

        all_results: list = []
        worker.all_finished.connect(lambda r: all_results.extend(r))

        from src.services.tts_service import AudioSegment as TtsAudioSeg

        call_count = [0]

        async def _gen_or_fail(segments, voice, speed, output_dir, on_progress=None, **kw):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("의도적 실패")
            seg = MagicMock(spec=TtsAudioSeg)
            p = tmp_path / f"seg_{call_count[0]}.mp3"
            p.write_bytes(b"")
            seg.audio_path = p
            seg.duration_sec = 0.5
            seg.text = "안녕하세요."
            return [seg]

        with (
            patch("src.workers.batch_tts_worker.get_provider") as mock_get_provider,
            patch(
                "src.workers.batch_tts_worker.AudioMerger.merge_audio_files",
                side_effect=lambda audio_files, output_path, **kw: output_path.write_bytes(b""),
            ),
        ):
            provider = MagicMock()
            provider.generate_segments = AsyncMock(side_effect=_gen_or_fail)
            mock_get_provider.return_value = provider
            worker.run()

        assert len(all_results) == 2
        assert all_results[0].success is True
        assert all_results[1].success is False


# ─────────────────────── i18n ───────────────────────

class TestBatchTtsI18nKeys:
    def test_batch_tts_i18n_keys(self):
        """P2b i18n 키가 ko.py에 존재한다."""
        from src.utils.lang.ko import STRINGS

        required_keys = [
            "Batch TTS\u2026",
            "Batch TTS Generation",
            "Add Files",
            "Output Folder:",
            "Browse\u2026",
            "Start Batch TTS",
            "Batch TTS complete",
            "No voice available for selected provider.",
            "Selected provider is unavailable.",
        ]
        for key in required_keys:
            assert key in STRINGS, f"Missing i18n key: {key!r}"
