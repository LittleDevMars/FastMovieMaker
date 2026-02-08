"""Tests for media library models and service."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.models.media_item import MediaItem
from src.utils.config import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS


class TestMediaItem:
    def test_default_fields(self):
        item = MediaItem(
            item_id="abc123",
            file_path="/tmp/video.mp4",
            file_name="video.mp4",
            media_type="video",
            added_at="2026-01-01T00:00:00",
        )
        assert item.thumbnail_path == ""
        assert item.duration_ms == 0
        assert item.width == 0
        assert item.height == 0
        assert item.file_size == 0
        assert item.favorite is False

    def test_to_dict(self):
        item = MediaItem(
            item_id="abc123",
            file_path="/tmp/video.mp4",
            file_name="video.mp4",
            media_type="video",
            added_at="2026-01-01T00:00:00",
            favorite=True,
        )
        d = item.to_dict()
        assert d["item_id"] == "abc123"
        assert d["media_type"] == "video"
        assert d["favorite"] is True

    def test_from_dict(self):
        d = {
            "item_id": "xyz789",
            "file_path": "/tmp/image.png",
            "file_name": "image.png",
            "media_type": "image",
            "added_at": "2026-01-01T00:00:00",
            "width": 1920,
            "height": 1080,
        }
        item = MediaItem.from_dict(d)
        assert item.item_id == "xyz789"
        assert item.media_type == "image"
        assert item.width == 1920
        assert item.favorite is False  # default

    def test_from_dict_backward_compat(self):
        """Missing optional fields should use defaults."""
        d = {
            "item_id": "old",
            "file_path": "/tmp/old.mp4",
            "file_name": "old.mp4",
            "media_type": "video",
            "added_at": "2025-01-01T00:00:00",
        }
        item = MediaItem.from_dict(d)
        assert item.thumbnail_path == ""
        assert item.duration_ms == 0
        assert item.favorite is False

    def test_roundtrip(self):
        item = MediaItem(
            item_id="rt1",
            file_path="/tmp/test.mp4",
            file_name="test.mp4",
            media_type="video",
            added_at="2026-01-01T00:00:00",
            duration_ms=5000,
            width=1920,
            height=1080,
            file_size=1024000,
            favorite=True,
        )
        restored = MediaItem.from_dict(item.to_dict())
        assert restored.item_id == item.item_id
        assert restored.duration_ms == item.duration_ms
        assert restored.favorite == item.favorite
        assert restored.file_size == item.file_size


class TestMediaLibraryService:
    def test_empty_library(self, tmp_path):
        from src.services.media_library_service import MediaLibraryService

        lib_path = tmp_path / "test_lib.json"
        service = MediaLibraryService(library_path=lib_path)
        assert service.list_items() == []

    def test_add_video_item(self, tmp_path):
        from src.services.media_library_service import MediaLibraryService

        lib_path = tmp_path / "test_lib.json"
        video_file = tmp_path / "sample.mp4"
        video_file.write_bytes(b"\x00" * 100)

        service = MediaLibraryService(library_path=lib_path)
        item = service.add_item(video_file)

        assert item is not None
        assert item.media_type == "video"
        assert item.file_name == "sample.mp4"
        assert item.file_size == 100
        assert len(service.list_items()) == 1

    def test_add_image_item(self, tmp_path):
        from src.services.media_library_service import MediaLibraryService

        lib_path = tmp_path / "test_lib.json"
        img_file = tmp_path / "photo.png"
        img_file.write_bytes(b"\x00" * 50)

        service = MediaLibraryService(library_path=lib_path)
        item = service.add_item(img_file)

        assert item is not None
        assert item.media_type == "image"
        assert item.file_name == "photo.png"

    def test_add_unsupported_format(self, tmp_path):
        from src.services.media_library_service import MediaLibraryService

        lib_path = tmp_path / "test_lib.json"
        txt_file = tmp_path / "readme.txt"
        txt_file.write_text("hello")

        service = MediaLibraryService(library_path=lib_path)
        item = service.add_item(txt_file)
        assert item is None
        assert len(service.list_items()) == 0

    def test_add_nonexistent_file(self, tmp_path):
        from src.services.media_library_service import MediaLibraryService

        lib_path = tmp_path / "test_lib.json"
        service = MediaLibraryService(library_path=lib_path)
        item = service.add_item(tmp_path / "nope.mp4")
        assert item is None

    def test_duplicate_prevention(self, tmp_path):
        from src.services.media_library_service import MediaLibraryService

        lib_path = tmp_path / "test_lib.json"
        video_file = tmp_path / "sample.mp4"
        video_file.write_bytes(b"\x00" * 100)

        service = MediaLibraryService(library_path=lib_path)
        item1 = service.add_item(video_file)
        item2 = service.add_item(video_file)

        assert item1.item_id == item2.item_id
        assert len(service.list_items()) == 1

    def test_remove_item(self, tmp_path):
        from src.services.media_library_service import MediaLibraryService

        lib_path = tmp_path / "test_lib.json"
        video_file = tmp_path / "sample.mp4"
        video_file.write_bytes(b"\x00" * 100)

        service = MediaLibraryService(library_path=lib_path)
        item = service.add_item(video_file)
        assert len(service.list_items()) == 1

        removed = service.remove_item(item.item_id)
        assert removed is True
        assert len(service.list_items()) == 0

    def test_remove_nonexistent(self, tmp_path):
        from src.services.media_library_service import MediaLibraryService

        lib_path = tmp_path / "test_lib.json"
        service = MediaLibraryService(library_path=lib_path)
        assert service.remove_item("nonexistent") is False

    def test_filter_by_type(self, tmp_path):
        from src.services.media_library_service import MediaLibraryService

        lib_path = tmp_path / "test_lib.json"
        (tmp_path / "video.mp4").write_bytes(b"\x00")
        (tmp_path / "image.png").write_bytes(b"\x00")

        service = MediaLibraryService(library_path=lib_path)
        service.add_item(tmp_path / "video.mp4")
        service.add_item(tmp_path / "image.png")

        assert len(service.list_items()) == 2
        assert len(service.list_items(media_type="video")) == 1
        assert len(service.list_items(media_type="image")) == 1

    def test_toggle_favorite(self, tmp_path):
        from src.services.media_library_service import MediaLibraryService

        lib_path = tmp_path / "test_lib.json"
        video_file = tmp_path / "sample.mp4"
        video_file.write_bytes(b"\x00")

        service = MediaLibraryService(library_path=lib_path)
        item = service.add_item(video_file)
        assert item.favorite is False

        new_state = service.toggle_favorite(item.item_id)
        assert new_state is True
        assert service.get_item(item.item_id).favorite is True

        new_state = service.toggle_favorite(item.item_id)
        assert new_state is False

    def test_get_favorites(self, tmp_path):
        from src.services.media_library_service import MediaLibraryService

        lib_path = tmp_path / "test_lib.json"
        (tmp_path / "a.mp4").write_bytes(b"\x00")
        (tmp_path / "b.png").write_bytes(b"\x00")

        service = MediaLibraryService(library_path=lib_path)
        item_a = service.add_item(tmp_path / "a.mp4")
        service.add_item(tmp_path / "b.png")
        service.toggle_favorite(item_a.item_id)

        favs = service.get_favorites()
        assert len(favs) == 1
        assert favs[0].item_id == item_a.item_id

    def test_persistence(self, tmp_path):
        from src.services.media_library_service import MediaLibraryService

        lib_path = tmp_path / "test_lib.json"
        video_file = tmp_path / "sample.mp4"
        video_file.write_bytes(b"\x00" * 100)

        # Add item
        service1 = MediaLibraryService(library_path=lib_path)
        service1.add_item(video_file)
        assert len(service1.list_items()) == 1

        # Reload from disk
        service2 = MediaLibraryService(library_path=lib_path)
        assert len(service2.list_items()) == 1
        assert service2.list_items()[0].file_name == "sample.mp4"

    def test_json_structure(self, tmp_path):
        from src.services.media_library_service import MediaLibraryService

        lib_path = tmp_path / "test_lib.json"
        video_file = tmp_path / "sample.mp4"
        video_file.write_bytes(b"\x00")

        service = MediaLibraryService(library_path=lib_path)
        service.add_item(video_file)

        data = json.loads(lib_path.read_text(encoding="utf-8"))
        assert "items" in data
        assert len(data["items"]) == 1
        assert data["items"][0]["media_type"] == "video"


class TestConfigExtensions:
    def test_image_extensions_exist(self):
        assert len(IMAGE_EXTENSIONS) >= 5
        assert ".png" in IMAGE_EXTENSIONS
        assert ".jpg" in IMAGE_EXTENSIONS

    def test_video_extensions_exist(self):
        assert len(VIDEO_EXTENSIONS) >= 5
        assert ".mp4" in VIDEO_EXTENSIONS
