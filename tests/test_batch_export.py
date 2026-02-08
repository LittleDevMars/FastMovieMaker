"""Tests for batch export feature."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from src.models.export_preset import (
    BatchExportJob,
    DEFAULT_PRESETS,
    ExportPreset,
)
from src.models.subtitle import SubtitleSegment, SubtitleTrack


class TestExportPreset:
    def test_resolution_label(self):
        p = ExportPreset("Test", 1920, 1080, "h264", "mp4")
        assert p.resolution_label == "1920x1080"

    def test_original_resolution_label(self):
        p = ExportPreset("Original", 0, 0, "h264", "mp4")
        assert p.resolution_label == "Original"

    def test_file_extension(self):
        p = ExportPreset("Test", 1920, 1080, "h264", "mp4")
        assert p.file_extension == ".mp4"

    def test_file_extension_mkv(self):
        p = ExportPreset("Test", 1920, 1080, "hevc", "mkv")
        assert p.file_extension == ".mkv"

    def test_default_presets_not_empty(self):
        assert len(DEFAULT_PRESETS) >= 5

    def test_default_presets_have_unique_suffixes(self):
        suffixes = [p.suffix for p in DEFAULT_PRESETS]
        assert len(suffixes) == len(set(suffixes))


class TestBatchExportJob:
    def test_default_status(self):
        preset = ExportPreset("Test", 1920, 1080, "h264", "mp4")
        job = BatchExportJob(preset=preset, output_path="/tmp/out.mp4")
        assert job.status == "pending"
        assert job.error_message == ""
        assert job.progress_pct == 0

    def test_status_transitions(self):
        preset = ExportPreset("Test", 1920, 1080, "h264", "mp4")
        job = BatchExportJob(preset=preset, output_path="/tmp/out.mp4")
        job.status = "running"
        assert job.status == "running"
        job.status = "completed"
        assert job.status == "completed"

    def test_error_message(self):
        preset = ExportPreset("Test", 1920, 1080, "h264", "mp4")
        job = BatchExportJob(preset=preset, output_path="/tmp/out.mp4")
        job.status = "failed"
        job.error_message = "FFmpeg not found"
        assert job.error_message == "FFmpeg not found"


class TestExportVideoScaling:
    def test_accepts_scale_params(self):
        from src.services.video_exporter import export_video

        sig = inspect.signature(export_video)
        assert "scale_width" in sig.parameters
        assert "scale_height" in sig.parameters
        assert "codec" in sig.parameters

    def test_scale_defaults_to_zero(self):
        from src.services.video_exporter import export_video

        sig = inspect.signature(export_video)
        assert sig.parameters["scale_width"].default == 0
        assert sig.parameters["scale_height"].default == 0

    def test_codec_defaults_to_h264(self):
        from src.services.video_exporter import export_video

        sig = inspect.signature(export_video)
        assert sig.parameters["codec"].default == "h264"


class TestBatchExportWorkerSignature:
    def test_worker_stores_jobs(self):
        from src.workers.batch_export_worker import BatchExportWorker

        preset = ExportPreset("Test", 1920, 1080, "h264", "mp4")
        jobs = [BatchExportJob(preset=preset, output_path="/tmp/out.mp4")]
        track = SubtitleTrack(segments=[])

        worker = BatchExportWorker(
            Path("/tmp/test.mp4"),
            track,
            jobs,
            audio_path=Path("/tmp/audio.mp3"),
        )
        assert len(worker._jobs) == 1
        assert worker._audio_path == Path("/tmp/audio.mp3")

    def test_cancel_flag(self):
        from src.workers.batch_export_worker import BatchExportWorker

        track = SubtitleTrack(segments=[])
        worker = BatchExportWorker(Path("/tmp/test.mp4"), track, [])
        assert worker._cancelled is False
        worker.cancel()
        assert worker._cancelled is True

    def test_worker_stores_video_path(self):
        from src.workers.batch_export_worker import BatchExportWorker

        track = SubtitleTrack(segments=[])
        worker = BatchExportWorker(Path("/tmp/test.mp4"), track, [])
        assert worker._video_path == Path("/tmp/test.mp4")
