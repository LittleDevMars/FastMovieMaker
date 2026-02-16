"""Tests for proxy generation service and worker."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.services.proxy_service import (
    generate_proxy,
    get_proxy_path,
    is_proxy_valid,
)
from src.workers.proxy_worker import ProxyWorker


class TestProxyService:
    @patch("src.services.proxy_service.get_proxy_dir")
    def test_get_proxy_path(self, mock_get_dir, tmp_path):
        # Mock proxy dir to be inside temp path
        mock_get_dir.return_value = tmp_path / "proxies"
        
        # Test that proxy path is generated correctly based on hash
        video_path = tmp_path / "test_video.mp4"
        # Create dummy file to resolve absolute path
        video_path.touch()
        
        proxy_path = get_proxy_path(video_path)
        
        assert proxy_path.parent == tmp_path / "proxies"
        assert proxy_path.name.startswith("proxy_")
        assert proxy_path.suffix == ".mp4"
        
        # Same path should yield same proxy path
        assert get_proxy_path(video_path) == proxy_path

    def test_is_proxy_valid(self, tmp_path):
        video_path = tmp_path / "source.mp4"
        proxy_path = tmp_path / "proxy.mp4"
        
        video_path.touch()
        
        # Case 1: Proxy doesn't exist
        assert not is_proxy_valid(video_path, proxy_path)
        
        # Case 2: Proxy exists but is older than source
        proxy_path.touch()
        # Set proxy mtime to 10 seconds ago
        old_time = time.time() - 10
        import os
        os.utime(proxy_path, (old_time, old_time))
        # Set source mtime to now
        video_path.touch() 
        
        # Ensure filesystem timestamp resolution is handled
        assert video_path.stat().st_mtime > proxy_path.stat().st_mtime
        assert not is_proxy_valid(video_path, proxy_path)
        
        # Case 3: Proxy is newer than source
        # Set source to old
        os.utime(video_path, (old_time, old_time))
        proxy_path.touch() # Now
        
        assert is_proxy_valid(video_path, proxy_path)

    @patch("src.services.proxy_service.probe_video")
    @patch("src.services.proxy_service.get_ffmpeg_runner")
    def test_generate_proxy_success(self, mock_get_runner, mock_probe, tmp_path):
        video_path = tmp_path / "source.mp4"
        proxy_path = tmp_path / "proxy.mp4"
        video_path.touch()
        
        mock_info = MagicMock()
        mock_info.duration_ms = 10000
        mock_probe.return_value = mock_info
        
        mock_runner = MagicMock()
        mock_runner.is_available.return_value = True
        
        # Mock run_async process
        mock_process = MagicMock()
        mock_process.stdout = iter(["out_time_us=5000000"]) # 50%
        mock_process.stderr = iter([])
        mock_process.returncode = 0
        mock_process.wait.return_value = None
        
        mock_runner.run_async.return_value = mock_process
        mock_get_runner.return_value = mock_runner
        
        progress_cb = MagicMock()
        result = generate_proxy(video_path, proxy_path, on_progress=progress_cb)
        
        assert result is True
        mock_runner.run_async.assert_called_once()
        args = mock_runner.run_async.call_args[0][0]
        assert str(video_path) in args
        assert str(proxy_path) in args
        assert "-progress" in args
        
        # Check progress calls
        progress_cb.assert_any_call(50)
        progress_cb.assert_any_call(100)

    @patch("src.services.proxy_service.get_ffmpeg_runner")
    def test_generate_proxy_cancel(self, mock_get_runner, tmp_path):
        video_path = tmp_path / "source.mp4"
        proxy_path = tmp_path / "proxy.mp4"
        video_path.touch()
        
        mock_runner = MagicMock()
        mock_runner.is_available.return_value = True
        
        mock_process = MagicMock()
        # Simulate output then cancel
        mock_process.stdout = iter(["out_time_us=1000000"])
        mock_process.terminate = MagicMock()
        mock_process.wait.return_value = None
        
        mock_runner.run_async.return_value = mock_process
        mock_get_runner.return_value = mock_runner
        
        # Cancel immediately
        result = generate_proxy(video_path, proxy_path, cancel_check=lambda: True)
        
        assert result is False
        mock_process.terminate.assert_called()

    @patch("src.services.proxy_service.get_ffmpeg_runner")
    def test_generate_proxy_failure(self, mock_get_runner, tmp_path):
        video_path = tmp_path / "source.mp4"
        proxy_path = tmp_path / "proxy.mp4"
        video_path.touch()
        
        mock_runner = MagicMock()
        mock_runner.is_available.return_value = True
        
        mock_process = MagicMock()
        mock_process.stdout = iter([])
        mock_process.returncode = 1
        mock_process.wait.return_value = None
        mock_runner.run_async.return_value = mock_process
        mock_get_runner.return_value = mock_runner
        
        result = generate_proxy(video_path, proxy_path)
        
        assert result is False

    @patch("src.services.proxy_service.get_ffmpeg_runner")
    def test_generate_proxy_exists_skip(self, mock_get_runner, tmp_path):
        video_path = tmp_path / "source.mp4"
        proxy_path = tmp_path / "proxy.mp4"
        video_path.touch()
        proxy_path.touch()
        
        result = generate_proxy(video_path, proxy_path, force=False)
        
        assert result is True
        mock_get_runner.assert_not_called() # Should skip generation

    @patch("src.services.proxy_service.get_ffmpeg_runner")
    def test_generate_proxy_force_overwrite(self, mock_get_runner, tmp_path):
        video_path = tmp_path / "source.mp4"
        proxy_path = tmp_path / "proxy.mp4"
        video_path.touch()
        proxy_path.touch()
        
        mock_runner = MagicMock()
        mock_runner.is_available.return_value = True
        
        mock_process = MagicMock()
        mock_process.stdout = iter([])
        mock_process.returncode = 0
        mock_process.wait.return_value = None
        mock_runner.run_async.return_value = mock_process
        mock_get_runner.return_value = mock_runner
        
        result = generate_proxy(video_path, proxy_path, force=True)
        
        assert result is True
        mock_runner.run_async.assert_called_once()


class TestProxyWorker:
    @patch("src.workers.proxy_worker.generate_proxy")
    @patch("src.workers.proxy_worker.get_proxy_path")
    def test_worker_run_success(self, mock_get_path, mock_generate):
        video_path = Path("source.mp4")
        proxy_path = Path("proxy.mp4")
        
        mock_get_path.return_value = proxy_path
        mock_generate.return_value = True
        
        worker = ProxyWorker(str(video_path))
        
        # Capture signal
        signals = []
        worker.finished.connect(signals.append)
        
        worker.run()
        
        assert len(signals) == 1
        assert signals[0] == str(proxy_path)
        mock_generate.assert_called_once()
        assert "on_progress" in mock_generate.call_args[1]
        assert "cancel_check" in mock_generate.call_args[1]

    @patch("src.workers.proxy_worker.generate_proxy")
    @patch("src.workers.proxy_worker.get_proxy_path")
    def test_worker_run_failure(self, mock_get_path, mock_generate):
        video_path = Path("source.mp4")
        proxy_path = Path("proxy.mp4")
        
        mock_get_path.return_value = proxy_path
        mock_generate.return_value = False
        
        worker = ProxyWorker(str(video_path))
        
        signals = []
        worker.finished.connect(signals.append)
        errors = []
        worker.error.connect(errors.append)
        
        worker.run()
        
        assert len(signals) == 1
        assert signals[0] == "" # Empty string indicates failure
        assert len(errors) == 1
        assert "failed" in errors[0]