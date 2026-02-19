"""Controller 단위 테스트. AppContext mock으로 Qt 부담 최소화."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.ui.controllers.app_context import AppContext


class TestAppContext:
    """AppContext 속성/편의 메서드 검증 (Qt 불필요)."""

    def test_init_defaults(self) -> None:
        ctx = AppContext()
        assert ctx.current_clip_index == 0
        assert ctx.current_track_index == 0
        assert ctx.current_playback_source is None
        assert ctx.pending_seek_ms is None
        assert ctx.play_intent is False
        assert ctx.use_proxies is False
        assert ctx.proxy_map == {}

    def test_status_bar_returns_window_statusBar(self) -> None:
        ctx = AppContext()
        mock_bar = MagicMock()
        ctx.window = MagicMock()
        ctx.window.statusBar.return_value = mock_bar
        assert ctx.status_bar() is mock_bar
        ctx.window.statusBar.assert_called_once()

    def test_active_track_empty_tracks(self) -> None:
        ctx = AppContext()
        ctx.project = MagicMock()
        ctx.project.active_track_index = 0
        ctx.project.subtitle_tracks = []
        assert ctx.active_track() is None

    def test_active_track_valid_index(self) -> None:
        ctx = AppContext()
        track = MagicMock()
        ctx.project = MagicMock()
        ctx.project.active_track_index = 0
        ctx.project.subtitle_tracks = [track]
        assert ctx.active_track() is track

    def test_active_track_out_of_range(self) -> None:
        ctx = AppContext()
        ctx.project = MagicMock()
        ctx.project.active_track_index = 2
        ctx.project.subtitle_tracks = [MagicMock(), MagicMock()]
        assert ctx.active_track() is None


class TestPlaybackControllerWithMockContext:
    """PlaybackController 동작 검증 (mock AppContext, Qt 의존 최소)."""

    def test_on_stop_all_calls_player_stop_and_clears_intent(self) -> None:
        from src.ui.controllers.playback_controller import PlaybackController

        ctx = MagicMock(spec=AppContext)
        ctx.player = MagicMock()
        ctx.tts_player = MagicMock()
        ctx.play_intent = True

        ctrl = PlaybackController(ctx)
        ctrl.on_stop_all()

        ctx.player.stop.assert_called_once()
        ctx.tts_player.stop.assert_called_once()
        assert ctx.play_intent is False

    def test_seek_relative_clamps_and_sets_position(self) -> None:
        from src.ui.controllers.playback_controller import PlaybackController

        ctx = MagicMock(spec=AppContext)
        ctx.player = MagicMock()
        ctx.player.position.return_value = 5000  # 5 sec
        ctx.tts_player = MagicMock()
        ctx.project = MagicMock()
        ctx.timeline = MagicMock()
        ctx.project.video_clip_track = None

        ctrl = PlaybackController(ctx)
        ctrl.seek_relative(3000)

        ctx.player.setPosition.assert_called_once()
        call_arg = ctx.player.setPosition.call_args[0][0]
        assert call_arg == 8000

    def test_seek_relative_does_not_go_negative(self) -> None:
        from src.ui.controllers.playback_controller import PlaybackController

        ctx = MagicMock(spec=AppContext)
        ctx.player = MagicMock()
        ctx.player.position.return_value = 2000
        ctx.tts_player = MagicMock()
        ctx.project = MagicMock()
        ctx.timeline = MagicMock()
        ctx.project.video_clip_track = None

        ctrl = PlaybackController(ctx)
        ctrl.seek_relative(-10000)

        ctx.player.setPosition.assert_called_once_with(0)


class TestMediaController:
    """MediaController 동작 검증."""

    def test_on_proxy_finished_shows_message(self) -> None:
        from src.ui.controllers.media_controller import MediaController

        ctx = MagicMock(spec=AppContext)
        ctx.proxy_map = {}
        ctx.status_bar.return_value = MagicMock()
        ctx.window = None  # QObject requires None or real QObject as parent
        ctx.use_proxies = False  # instance attr not in class spec

        ctrl = MediaController(ctx)
        ctrl._on_proxy_finished("/path/to/video.mp4", "/path/to/proxy.mp4")

        assert ctx.proxy_map["/path/to/video.mp4"] == "/path/to/proxy.mp4"
        ctx.status_bar().showMessage.assert_called_once()
        args = ctx.status_bar().showMessage.call_args[0]
        assert "video.mp4" in args[0]

    def test_cancel_all_proxies(self) -> None:
        """Test that cancel_all_proxies stops all running workers."""
        from src.ui.controllers.media_controller import MediaController

        ctx = MagicMock(spec=AppContext)
        ctx.window = None  # QObject requires None or real QObject as parent
        ctrl = MediaController(ctx)

        # Mock workers
        mock_thread1 = MagicMock()
        mock_worker1 = MagicMock()
        mock_thread2 = MagicMock()
        mock_worker2 = MagicMock()

        mock_thread1.isRunning.return_value = True
        mock_thread2.isRunning.return_value = True

        ctrl._proxy_workers["video1.mp4"] = (mock_thread1, mock_worker1)
        ctrl._proxy_workers["video2.mp4"] = (mock_thread2, mock_worker2)

        ctrl.cancel_all_proxies()

        mock_worker1.cancel.assert_called_once()
        mock_worker2.cancel.assert_called_once()
        mock_thread1.quit.assert_called_once()
        mock_thread2.quit.assert_called_once()
        assert len(ctrl._proxy_workers) == 0
