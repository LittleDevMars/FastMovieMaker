"""Tests for ImageOverlay model, ImageOverlayTrack, and project serialization."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from src.models.image_overlay import ImageOverlay, ImageOverlayTrack


class TestImageOverlay:
    def test_default_fields(self):
        ov = ImageOverlay(start_ms=1000, end_ms=6000, image_path="/tmp/pip.png")
        assert ov.x_percent == 70.0
        assert ov.y_percent == 10.0
        assert ov.scale_percent == 25.0
        assert ov.opacity == 1.0

    def test_duration_ms(self):
        ov = ImageOverlay(start_ms=2000, end_ms=7000, image_path="/tmp/pip.png")
        assert ov.duration_ms == 5000

    def test_file_name(self):
        ov = ImageOverlay(start_ms=0, end_ms=1000, image_path="/some/dir/image.png")
        assert ov.file_name == "image.png"

    def test_to_dict(self):
        ov = ImageOverlay(
            start_ms=500, end_ms=3000, image_path="/tmp/test.png",
            x_percent=50.0, y_percent=20.0, scale_percent=30.0, opacity=0.8,
        )
        d = ov.to_dict()
        assert d["start_ms"] == 500
        assert d["end_ms"] == 3000
        assert d["image_path"] == "/tmp/test.png"
        assert d["x_percent"] == 50.0
        assert d["y_percent"] == 20.0
        assert d["scale_percent"] == 30.0
        assert d["opacity"] == 0.8

    def test_from_dict(self):
        d = {
            "start_ms": 100, "end_ms": 5100, "image_path": "/tmp/img.png",
            "x_percent": 10.0, "y_percent": 80.0, "scale_percent": 15.0, "opacity": 0.5,
        }
        ov = ImageOverlay.from_dict(d)
        assert ov.start_ms == 100
        assert ov.end_ms == 5100
        assert ov.x_percent == 10.0
        assert ov.y_percent == 80.0
        assert ov.scale_percent == 15.0
        assert ov.opacity == 0.5

    def test_from_dict_defaults(self):
        d = {"start_ms": 0, "end_ms": 1000, "image_path": "/tmp/min.png"}
        ov = ImageOverlay.from_dict(d)
        assert ov.x_percent == 70.0
        assert ov.y_percent == 10.0
        assert ov.scale_percent == 25.0
        assert ov.opacity == 1.0

    def test_roundtrip(self):
        original = ImageOverlay(
            start_ms=1000, end_ms=8000, image_path="/tmp/round.png",
            x_percent=33.3, y_percent=44.4, scale_percent=55.5, opacity=0.75,
        )
        restored = ImageOverlay.from_dict(original.to_dict())
        assert restored.start_ms == original.start_ms
        assert restored.end_ms == original.end_ms
        assert restored.image_path == original.image_path
        assert restored.x_percent == original.x_percent
        assert restored.y_percent == original.y_percent
        assert restored.scale_percent == original.scale_percent
        assert restored.opacity == original.opacity


class TestImageOverlayTrack:
    def test_empty_track(self):
        track = ImageOverlayTrack()
        assert len(track) == 0
        assert track.overlays_at(0) == []

    def test_add_overlay_sorts(self):
        track = ImageOverlayTrack()
        track.add_overlay(ImageOverlay(5000, 10000, "/tmp/b.png"))
        track.add_overlay(ImageOverlay(1000, 3000, "/tmp/a.png"))
        assert track[0].start_ms == 1000
        assert track[1].start_ms == 5000

    def test_remove_overlay(self):
        track = ImageOverlayTrack()
        track.add_overlay(ImageOverlay(0, 1000, "/tmp/a.png"))
        track.add_overlay(ImageOverlay(2000, 3000, "/tmp/b.png"))
        assert len(track) == 2
        track.remove_overlay(0)
        assert len(track) == 1
        assert track[0].start_ms == 2000

    def test_remove_out_of_range(self):
        track = ImageOverlayTrack()
        track.add_overlay(ImageOverlay(0, 1000, "/tmp/a.png"))
        track.remove_overlay(5)  # out of range, should not crash
        assert len(track) == 1

    def test_overlays_at(self):
        track = ImageOverlayTrack()
        track.add_overlay(ImageOverlay(0, 5000, "/tmp/a.png"))
        track.add_overlay(ImageOverlay(3000, 8000, "/tmp/b.png"))
        track.add_overlay(ImageOverlay(10000, 15000, "/tmp/c.png"))

        # At 4000ms: a and b are active
        active = track.overlays_at(4000)
        assert len(active) == 2

        # At 6000ms: only b is active
        active = track.overlays_at(6000)
        assert len(active) == 1
        assert active[0].image_path == "/tmp/b.png"

        # At 12000ms: only c is active
        active = track.overlays_at(12000)
        assert len(active) == 1
        assert active[0].image_path == "/tmp/c.png"

        # At 20000ms: nothing active
        assert track.overlays_at(20000) == []

    def test_overlays_at_boundary(self):
        track = ImageOverlayTrack()
        track.add_overlay(ImageOverlay(1000, 2000, "/tmp/a.png"))
        # start_ms is inclusive
        assert len(track.overlays_at(1000)) == 1
        # end_ms is exclusive
        assert len(track.overlays_at(2000)) == 0

    def test_iter(self):
        track = ImageOverlayTrack()
        track.add_overlay(ImageOverlay(0, 1000, "/tmp/a.png"))
        track.add_overlay(ImageOverlay(2000, 3000, "/tmp/b.png"))
        paths = [ov.image_path for ov in track]
        assert paths == ["/tmp/a.png", "/tmp/b.png"]


class TestProjectSerialization:
    def test_project_has_image_overlay_track(self):
        from src.models.project import ProjectState
        p = ProjectState()
        assert hasattr(p, "image_overlay_track")
        assert isinstance(p.image_overlay_track, ImageOverlayTrack)
        assert len(p.image_overlay_track) == 0

    def test_project_reset_clears_overlays(self):
        from src.models.project import ProjectState
        p = ProjectState()
        p.image_overlay_track.add_overlay(
            ImageOverlay(0, 5000, "/tmp/test.png")
        )
        assert len(p.image_overlay_track) == 1
        p.reset()
        assert len(p.image_overlay_track) == 0

    def test_project_io_roundtrip(self, tmp_path):
        from src.models.project import ProjectState
        from src.services.project_io import save_project, load_project

        p = ProjectState()
        p.video_path = Path("/tmp/video.mp4")
        p.image_overlay_track.add_overlay(
            ImageOverlay(1000, 6000, "/tmp/pip1.png", x_percent=10.0, opacity=0.9)
        )
        p.image_overlay_track.add_overlay(
            ImageOverlay(8000, 12000, "/tmp/pip2.png", scale_percent=50.0)
        )

        save_path = tmp_path / "test_project.fmm.json"
        save_project(p, save_path)

        loaded = load_project(save_path)
        assert len(loaded.image_overlay_track) == 2
        ov1 = loaded.image_overlay_track[0]
        assert ov1.start_ms == 1000
        assert ov1.end_ms == 6000
        assert ov1.image_path == "/tmp/pip1.png"
        assert ov1.x_percent == 10.0
        assert ov1.opacity == 0.9

        ov2 = loaded.image_overlay_track[1]
        assert ov2.start_ms == 8000
        assert ov2.scale_percent == 50.0

    def test_load_project_without_image_overlays(self, tmp_path):
        """Loading an older project without image_overlays key should not fail."""
        data = {
            "version": 1,
            "video_path": "/tmp/video.mp4",
            "tracks": [],
        }
        save_path = tmp_path / "old_project.fmm.json"
        save_path.write_text(json.dumps(data), encoding="utf-8")

        from src.services.project_io import load_project
        loaded = load_project(save_path)
        assert len(loaded.image_overlay_track) == 0


class TestExportSignatures:
    def test_export_video_image_overlays_param(self):
        from src.services.video_exporter import export_video
        sig = inspect.signature(export_video)
        assert "image_overlays" in sig.parameters

    def test_export_worker_image_overlays_param(self):
        from src.workers.export_worker import ExportWorker
        sig = inspect.signature(ExportWorker.__init__)
        assert "image_overlays" in sig.parameters
