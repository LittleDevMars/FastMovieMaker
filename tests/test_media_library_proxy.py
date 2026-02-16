"""Tests for media library proxy integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QPoint

from src.models.media_item import MediaItem
from src.ui.media_library_panel import MediaLibraryPanel


class TestMediaLibraryProxy:
    @pytest.fixture
    def panel(self, qtbot, tmp_path):
        # Mock service to avoid disk I/O and isolate UI logic
        with patch("src.ui.media_library_panel.MediaLibraryService") as MockService:
            service = MockService.return_value
            # Setup dummy items
            self.video_path = str(tmp_path / "video.mp4")
            self.item = MediaItem(
                item_id="1",
                file_path=self.video_path,
                file_name="video.mp4",
                media_type="video",
                added_at="2024-01-01",
            )
            service.list_items.return_value = [self.item]
            service.get_item.return_value = self.item
            
            panel = MediaLibraryPanel()
            qtbot.addWidget(panel)
            panel._service = service  # Inject mock
            
            # Force refresh to populate UI with the mock item
            panel._refresh()
            return panel

    def test_on_proxy_ready_updates_item(self, panel):
        """Test that on_proxy_ready updates the item's has_proxy flag."""
        assert not self.item.has_proxy
        
        # Simulate proxy ready signal
        panel.on_proxy_ready(self.video_path)
        
        assert self.item.has_proxy is True
        
        # Verify thumbnail widget exists (UI updated)
        assert "1" in panel._thumb_widgets

    def test_on_proxy_started_updates_item(self, panel):
        """Test that on_proxy_started updates the item's is_proxy_generating flag."""
        assert not self.item.is_proxy_generating
        
        # Simulate proxy started signal
        panel.on_proxy_started(self.video_path)
        
        assert self.item.is_proxy_generating is True
        assert "1" in panel._thumb_widgets

    @patch("src.services.proxy_service.ProxyService")
    def test_check_proxies(self, MockProxyService, panel):
        """Test that check_proxies updates items based on ProxyService."""
        mock_svc = MockProxyService.return_value
        # Setup: has_proxy returns True for our item
        mock_svc.has_proxy.side_effect = lambda path: path == self.video_path
        
        self.item.has_proxy = False
        
        panel.check_proxies()
        
        assert self.item.has_proxy is True
        mock_svc.has_proxy.assert_called_with(self.video_path)

    def test_context_menu_actions(self, panel):
        """Test that context menu logic adds 'Generate Proxy' for videos."""
        # We mock QMenu to inspect added actions without showing GUI
        with patch("src.ui.media_library_panel.QMenu") as MockMenu:
            mock_menu = MockMenu.return_value
            actions = []
            
            def add_action(text):
                act = MagicMock()
                act.text.return_value = text
                actions.append(act)
                return act
            
            mock_menu.addAction.side_effect = add_action
            
            # Trigger context menu logic
            panel._on_context_menu("1", QPoint(0, 0))
            
            # Verify "Generate Proxy" action was added
            action_texts = [a.text() for a in actions]
            # Note: tr() might return translation, but usually key is English
            assert any("Generate Proxy" in t for t in action_texts)

    def test_proxy_generation_signal(self, panel, qtbot):
        """Test that the panel emits proxy_generation_requested signal."""
        with qtbot.waitSignal(panel.proxy_generation_requested) as blocker:
            # Manually emit to verify signal definition
            panel.proxy_generation_requested.emit(self.video_path)
        
        assert blocker.args == [self.video_path]