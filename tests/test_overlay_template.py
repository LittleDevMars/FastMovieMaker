"""Tests for overlay template model and template service."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.models.overlay_template import OverlayTemplate


class TestOverlayTemplate:
    def test_default_fields(self):
        t = OverlayTemplate(
            template_id="test1",
            name="Test Template",
            image_path="/tmp/test.png",
            thumbnail_path="/tmp/test_thumb.png",
            category="frame",
            aspect_ratio="16:9",
        )
        assert t.opacity == 1.0
        assert t.is_builtin is True

    def test_to_dict(self):
        t = OverlayTemplate(
            template_id="test1",
            name="Test Template",
            image_path="/tmp/test.png",
            thumbnail_path="/tmp/test_thumb.png",
            category="frame",
            aspect_ratio="16:9",
            opacity=0.8,
            is_builtin=False,
        )
        d = t.to_dict()
        assert d["template_id"] == "test1"
        assert d["name"] == "Test Template"
        assert d["category"] == "frame"
        assert d["aspect_ratio"] == "16:9"
        assert d["opacity"] == 0.8
        assert d["is_builtin"] is False

    def test_from_dict(self):
        d = {
            "template_id": "test2",
            "name": "Another Template",
            "image_path": "/tmp/other.png",
            "thumbnail_path": "/tmp/other_thumb.png",
            "category": "watermark",
            "aspect_ratio": "9:16",
            "opacity": 0.5,
            "is_builtin": False,
        }
        t = OverlayTemplate.from_dict(d)
        assert t.template_id == "test2"
        assert t.category == "watermark"
        assert t.aspect_ratio == "9:16"
        assert t.opacity == 0.5
        assert t.is_builtin is False

    def test_from_dict_defaults(self):
        """Missing optional fields should use defaults."""
        d = {
            "template_id": "min",
            "name": "Minimal",
            "image_path": "/tmp/min.png",
        }
        t = OverlayTemplate.from_dict(d)
        assert t.thumbnail_path == ""
        assert t.category == "frame"
        assert t.aspect_ratio == "16:9"
        assert t.opacity == 1.0
        assert t.is_builtin is True

    def test_roundtrip(self):
        original = OverlayTemplate(
            template_id="rt1",
            name="Roundtrip Test",
            image_path="/tmp/rt.png",
            thumbnail_path="/tmp/rt_thumb.png",
            category="lower_third",
            aspect_ratio="9:16",
            opacity=0.75,
            is_builtin=False,
        )
        restored = OverlayTemplate.from_dict(original.to_dict())
        assert restored.template_id == original.template_id
        assert restored.name == original.name
        assert restored.category == original.category
        assert restored.aspect_ratio == original.aspect_ratio
        assert restored.opacity == original.opacity
        assert restored.is_builtin == original.is_builtin


class TestTemplateService:
    def test_list_builtin_templates(self):
        from src.services.template_service import TemplateService

        service = TemplateService()
        templates = service.list_templates(builtin_only=True)
        # Should have 6 built-in templates from manifest.json
        assert len(templates) == 6

    def test_filter_by_aspect_ratio(self):
        from src.services.template_service import TemplateService

        service = TemplateService()
        wide = service.list_templates(aspect_ratio="16:9", builtin_only=True)
        tall = service.list_templates(aspect_ratio="9:16", builtin_only=True)
        assert len(wide) == 3  # youtube_frame, rec_frame, minimal_border
        assert len(tall) == 3  # shorts_frame, channel_badge, recording_vertical

    def test_get_template_by_id(self):
        from src.services.template_service import TemplateService

        service = TemplateService()
        t = service.get_template("youtube_frame")
        assert t is not None
        assert t.name == "YouTube Frame"
        assert t.aspect_ratio == "16:9"

    def test_get_nonexistent_template(self):
        from src.services.template_service import TemplateService

        service = TemplateService()
        t = service.get_template("nonexistent_id_xyz")
        assert t is None

    def test_add_user_template(self, tmp_path):
        from src.services.template_service import TemplateService, _get_user_dir

        service = TemplateService()
        # Create a dummy image
        dummy_img = tmp_path / "custom_overlay.png"
        dummy_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        initial_user_count = len(service.list_templates(user_only=True))
        result = service.add_user_template(
            image_path=dummy_img,
            name="Custom Overlay",
            aspect_ratio="16:9",
            category="watermark",
        )

        assert result is not None
        assert result.name == "Custom Overlay"
        assert result.is_builtin is False

        new_count = len(service.list_templates(user_only=True))
        assert new_count == initial_user_count + 1

        # Cleanup
        service.remove_user_template(result.template_id)

    def test_add_nonexistent_file(self):
        from src.services.template_service import TemplateService

        service = TemplateService()
        result = service.add_user_template(
            image_path="/tmp/nonexistent_overlay_12345.png",
            name="Ghost",
        )
        assert result is None

    def test_remove_user_template(self, tmp_path):
        from src.services.template_service import TemplateService

        service = TemplateService()
        dummy_img = tmp_path / "to_remove.png"
        dummy_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        added = service.add_user_template(image_path=dummy_img, name="To Remove")
        assert added is not None

        removed = service.remove_user_template(added.template_id)
        assert removed is True

        # Should no longer exist
        assert service.get_template(added.template_id) is None

    def test_remove_nonexistent_template(self):
        from src.services.template_service import TemplateService

        service = TemplateService()
        removed = service.remove_user_template("nonexistent_id_xyz")
        assert removed is False

    def test_builtin_template_image_paths_absolute(self):
        from src.services.template_service import TemplateService

        service = TemplateService()
        templates = service.list_templates(builtin_only=True)
        for t in templates:
            assert Path(t.image_path).is_absolute(), f"{t.name} image_path is not absolute"


class TestExportVideoSignature:
    def test_overlay_path_parameter_exists(self):
        """Verify export_video accepts overlay_path parameter."""
        import inspect
        from src.services.video_exporter import export_video

        sig = inspect.signature(export_video)
        assert "overlay_path" in sig.parameters

    def test_export_worker_overlay_path(self):
        """Verify ExportWorker accepts overlay_path parameter."""
        import inspect
        from src.workers.export_worker import ExportWorker

        sig = inspect.signature(ExportWorker.__init__)
        assert "overlay_path" in sig.parameters


class TestManifestJson:
    def test_manifest_exists(self):
        manifest_path = Path(__file__).resolve().parent.parent / "resources" / "templates" / "manifest.json"
        assert manifest_path.exists(), "manifest.json should exist"

    def test_manifest_structure(self):
        manifest_path = Path(__file__).resolve().parent.parent / "resources" / "templates" / "manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "templates" in data
        assert len(data["templates"]) == 6

    def test_manifest_template_fields(self):
        manifest_path = Path(__file__).resolve().parent.parent / "resources" / "templates" / "manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        required_fields = {"template_id", "name", "image_path", "category", "aspect_ratio"}
        for entry in data["templates"]:
            for field in required_fields:
                assert field in entry, f"Missing field '{field}' in template '{entry.get('name', '?')}'"

    def test_template_pngs_exist(self):
        templates_dir = Path(__file__).resolve().parent.parent / "resources" / "templates"
        manifest_path = templates_dir / "manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in data["templates"]:
            img_path = templates_dir / entry["image_path"]
            assert img_path.exists(), f"Template PNG missing: {entry['image_path']}"
