"""Verification tests for recent bug fixes."""

from unittest.mock import MagicMock, patch
from pathlib import Path

from src.models.video_clip import VideoClipTrack
from src.services.proxy_service import ProxyService
from src.ui.controllers.clip_controller import ClipController
from src.ui.controllers.app_context import AppContext


def test_video_clip_track_has_name_attribute():
    """Verify VideoClipTrack has 'name' attribute to fix AttributeError during save."""
    track = VideoClipTrack()
    assert hasattr(track, "name")
    assert track.name == ""
    
    # Test roundtrip with dict (used in save/load)
    data = track.to_dict()
    assert "name" in data
    
    restored = VideoClipTrack.from_dict(data)
    assert restored.name == ""


def test_proxy_service_importable():
    """Verify ProxyService class exists and can be instantiated."""
    service = ProxyService()
    assert service is not None
    # Check if create_worker method exists
    assert hasattr(service, "create_worker")


@patch("src.ui.controllers.clip_controller.probe_video")
def test_add_video_to_timeline_logic(mock_probe):
    """Verify add_video_to_timeline logic handles v_idx correctly."""
    # Setup mock context
    ctx = MagicMock(spec=AppContext)
    ctx.project = MagicMock()
    ctx.project.video_tracks = []  # Start with no tracks
    ctx.current_track_index = 0
    ctx.timeline = MagicMock()
    ctx.timeline.is_ripple_mode.return_value = False
    
    # Mock probe result
    mock_info = MagicMock()
    mock_info.duration_ms = 10000
    mock_probe.return_value = mock_info
    
    ctrl = ClipController(ctx)
    
    # Execute method that previously failed with NameError: name 'v_idx' is not defined
    # This simulates dropping a file
    ctrl.add_video_to_timeline(Path("test.mp4"), 0)
    
    # Verify a track was created (since list was empty)
    assert len(ctx.project.video_tracks) == 1
    # Verify command was pushed (means logic completed successfully)
    ctx.undo_stack.push.assert_called()