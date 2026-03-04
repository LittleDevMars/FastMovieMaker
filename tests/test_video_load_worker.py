"""Tests for VideoLoadWorker conversion decision logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


@patch("src.workers.video_load_worker.get_ffmpeg_runner")
def test_get_conversion_reason_apv_on_linux(mock_get_runner, monkeypatch):
    from src.workers.video_load_worker import VideoLoadWorker

    monkeypatch.setattr("src.workers.video_load_worker.sys.platform", "linux")
    runner = MagicMock()
    runner.is_available.return_value = True
    runner.run_ffprobe.return_value = MagicMock(stdout="apv\n")
    mock_get_runner.return_value = runner

    worker = VideoLoadWorker(Path("/tmp/sample.mp4"))
    assert worker._get_conversion_reason(Path("/tmp/sample.mp4")) == "apv"


@patch("src.workers.video_load_worker.get_ffmpeg_runner")
def test_get_conversion_reason_non_apv_no_convert_on_linux(mock_get_runner, monkeypatch):
    from src.workers.video_load_worker import VideoLoadWorker

    monkeypatch.setattr("src.workers.video_load_worker.sys.platform", "linux")
    runner = MagicMock()
    runner.is_available.return_value = True
    runner.run_ffprobe.return_value = MagicMock(stdout="h264\n")
    mock_get_runner.return_value = runner

    worker = VideoLoadWorker(Path("/tmp/sample.mp4"))
    assert worker._get_conversion_reason(Path("/tmp/sample.mp4")) is None


@patch("src.workers.video_load_worker.get_ffmpeg_runner")
def test_get_conversion_reason_container_on_macos(mock_get_runner, monkeypatch):
    from src.workers.video_load_worker import VideoLoadWorker

    monkeypatch.setattr("src.workers.video_load_worker.sys.platform", "darwin")
    runner = MagicMock()
    runner.is_available.return_value = True
    runner.run_ffprobe.return_value = MagicMock(stdout="h264\n")
    mock_get_runner.return_value = runner

    worker = VideoLoadWorker(Path("/tmp/sample.mkv"))
    assert worker._get_conversion_reason(Path("/tmp/sample.mkv")) == "container"


@patch("src.workers.video_load_worker.AudioMerger.has_audio_stream", return_value=True)
@patch("src.workers.video_load_worker.VideoLoadWorker._convert_to_mp4")
@patch("src.workers.video_load_worker.get_ffmpeg_runner")
def test_run_converts_when_apv_detected(mock_get_runner, mock_convert, mock_has_audio, monkeypatch):
    from src.workers.video_load_worker import VideoLoadWorker

    monkeypatch.setattr("src.workers.video_load_worker.sys.platform", "linux")
    runner = MagicMock()
    runner.is_available.return_value = True
    runner.run_ffprobe.return_value = MagicMock(stdout="apv\n")
    mock_get_runner.return_value = runner

    converted = Path("/tmp/converted.mp4")
    mock_convert.return_value = converted

    worker = VideoLoadWorker(Path("/tmp/source.mp4"))
    payload: list[tuple[Path, bool, Path]] = []
    worker.finished.connect(lambda path, has_audio, source: payload.append((path, has_audio, source)))

    worker.run()

    assert mock_convert.called
    assert payload == [(converted, True, Path("/tmp/source.mp4"))]


@patch("src.workers.video_load_worker.get_ffmpeg_runner")
@patch("src.workers.video_load_worker.tempfile.mktemp")
def test_convert_to_mp4_uses_remux_first(mock_mktemp, mock_get_runner, tmp_path):
    from src.workers.video_load_worker import VideoLoadWorker

    out_path = tmp_path / "fmm_remux.mp4"
    out_path.touch()
    mock_mktemp.return_value = str(out_path)

    runner = MagicMock()
    runner.is_available.return_value = True
    runner.run.return_value = MagicMock(returncode=0)
    mock_get_runner.return_value = runner

    worker = VideoLoadWorker(Path("/tmp/source.mkv"))
    result = worker._convert_to_mp4(Path("/tmp/source.mkv"))

    assert result == out_path
    first_args = runner.run.call_args_list[0][0][0]
    assert "-c:v" in first_args
    assert first_args[first_args.index("-c:v") + 1] == "copy"


@patch("src.workers.video_load_worker.get_hw_encoder", return_value=("h264_nvenc", ["-preset", "p4"]))
@patch("src.workers.video_load_worker.get_ffmpeg_runner")
@patch("src.workers.video_load_worker.tempfile.mktemp")
def test_convert_to_mp4_falls_back_to_sw_after_hw_failure(
    mock_mktemp, mock_get_runner, mock_get_hw, tmp_path
):
    from src.workers.video_load_worker import VideoLoadWorker

    out_path = tmp_path / "fmm_fallback.mp4"
    out_path.touch()
    mock_mktemp.return_value = str(out_path)

    runner = MagicMock()
    runner.is_available.return_value = True
    runner.run.side_effect = [
        MagicMock(returncode=1),  # remux fail
        MagicMock(returncode=1),  # hw fail
        MagicMock(returncode=0),  # sw success
    ]
    mock_get_runner.return_value = runner

    worker = VideoLoadWorker(Path("/tmp/source.webm"))
    result = worker._convert_to_mp4(Path("/tmp/source.webm"))

    assert result == out_path
    assert runner.run.call_count == 3

    hw_args = runner.run.call_args_list[1][0][0]
    sw_args = runner.run.call_args_list[2][0][0]
    assert hw_args[hw_args.index("-c:v") + 1] == "h264_nvenc"
    assert sw_args[sw_args.index("-c:v") + 1] == "libx264"
    assert "fast" in sw_args
