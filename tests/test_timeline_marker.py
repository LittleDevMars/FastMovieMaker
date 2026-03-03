"""TimelineMarker 모델 + AddMarker/RemoveMarker/RenameMarker 커맨드 단위 테스트."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.models.timeline_marker import TimelineMarker
from src.models.project import ProjectState


# ── TimelineMarker 모델 ──────────────────────────────────────────────────────

class TestTimelineMarker:
    def test_marker_default_values(self):
        m = TimelineMarker(ms=1000)
        assert m.name == ""
        assert m.color == "yellow"

    def test_marker_to_dict_omits_defaults(self):
        m = TimelineMarker(ms=500)
        d = m.to_dict()
        assert d == {"ms": 500}

    def test_marker_to_dict_includes_non_defaults(self):
        m = TimelineMarker(ms=2000, name="Scene A", color="red")
        d = m.to_dict()
        assert d["ms"] == 2000
        assert d["name"] == "Scene A"
        assert d["color"] == "red"

    def test_marker_from_dict_restores(self):
        original = {"ms": 3000, "name": "Scene B", "color": "blue"}
        m = TimelineMarker.from_dict(original)
        assert m.ms == 3000
        assert m.name == "Scene B"
        assert m.color == "blue"

    def test_marker_from_dict_defaults(self):
        m = TimelineMarker.from_dict({"ms": 100})
        assert m.name == ""
        assert m.color == "yellow"


# ── AddMarkerCommand ──────────────────────────────────────────────────────────

class TestAddMarkerCommand:
    def _make_project(self):
        return ProjectState()

    def test_add_marker_command_redo(self):
        from src.ui.commands import AddMarkerCommand
        project = self._make_project()
        marker = TimelineMarker(ms=1000, name="A")
        cmd = AddMarkerCommand(project, marker)
        cmd.redo()
        assert len(project.markers) == 1
        assert project.markers[0] is marker

    def test_add_marker_command_undo(self):
        from src.ui.commands import AddMarkerCommand
        project = self._make_project()
        marker = TimelineMarker(ms=1000, name="A")
        cmd = AddMarkerCommand(project, marker)
        cmd.redo()
        cmd.undo()
        assert len(project.markers) == 0

    def test_add_marker_sorted_by_ms(self):
        from src.ui.commands import AddMarkerCommand
        project = self._make_project()
        m1 = TimelineMarker(ms=3000)
        m2 = TimelineMarker(ms=1000)
        m3 = TimelineMarker(ms=2000)
        for m in [m1, m2, m3]:
            cmd = AddMarkerCommand(project, m)
            cmd.redo()
        assert [m.ms for m in project.markers] == [1000, 2000, 3000]


# ── RemoveMarkerCommand ───────────────────────────────────────────────────────

class TestRemoveMarkerCommand:
    def test_remove_marker_command_redo(self):
        from src.ui.commands import RemoveMarkerCommand
        project = ProjectState()
        marker = TimelineMarker(ms=500)
        project.markers.append(marker)
        cmd = RemoveMarkerCommand(project, marker)
        cmd.redo()
        assert len(project.markers) == 0

    def test_remove_marker_command_undo(self):
        from src.ui.commands import RemoveMarkerCommand
        project = ProjectState()
        marker = TimelineMarker(ms=500)
        project.markers.append(marker)
        cmd = RemoveMarkerCommand(project, marker)
        cmd.redo()
        cmd.undo()
        assert len(project.markers) == 1
        assert project.markers[0] is marker


# ── RenameMarkerCommand ───────────────────────────────────────────────────────

class TestRenameMarkerCommand:
    def test_rename_marker_command(self):
        from src.ui.commands import RenameMarkerCommand
        marker = TimelineMarker(ms=1000, name="old")
        cmd = RenameMarkerCommand(marker, "old", "new")
        cmd.redo()
        assert marker.name == "new"
        cmd.undo()
        assert marker.name == "old"


# ── Project I/O 라운드트립 ─────────────────────────────────────────────────────

class TestProjectIORoundTripMarkers:
    def test_project_io_round_trip_markers(self):
        from src.services.project_io import save_project, load_project, PROJECT_VERSION

        assert PROJECT_VERSION == 11, "PROJECT_VERSION이 11이어야 합니다"

        project = ProjectState()
        project.markers = [
            TimelineMarker(ms=1000, name="Intro", color="red"),
            TimelineMarker(ms=5000),
        ]

        with tempfile.NamedTemporaryFile(suffix=".fmm.json", delete=False) as f:
            path = Path(f.name)

        try:
            save_project(project, path)
            loaded = load_project(path)
        finally:
            path.unlink(missing_ok=True)

        assert len(loaded.markers) == 2
        assert loaded.markers[0].ms == 1000
        assert loaded.markers[0].name == "Intro"
        assert loaded.markers[0].color == "red"
        assert loaded.markers[1].ms == 5000
        assert loaded.markers[1].name == ""
        assert loaded.markers[1].color == "yellow"
