"""Regression tests for project I/O compression stability."""

from __future__ import annotations

import gzip
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from src.models.project import ProjectState
from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.services.autosave import AutoSaveManager
from src.services.project_io import load_project, save_project


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_project_io.py"


def _load_bench_module():
    spec = importlib.util.spec_from_file_location("benchmark_project_io", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def _build_large_project(count: int = 2000) -> ProjectState:
    project = ProjectState()
    project.video_path = Path("/tmp/large_source.mp4")
    project.duration_ms = count * 120
    track = SubtitleTrack(name="Large", language="ko")
    for i in range(count):
        start_ms = i * 120
        track.add_segment(SubtitleSegment(start_ms, start_ms + 100, f"segment-{i}-payload"))
    project.subtitle_track = track
    return project


def test_large_project_roundtrip_and_compression_ratio(tmp_path: Path) -> None:
    project = _build_large_project()
    path = tmp_path / "large.fmm.json"

    save_project(project, path)
    raw = path.read_bytes()
    assert raw[:2] == b"\x1f\x8b"

    plain = gzip.decompress(raw)
    ratio = len(raw) / len(plain)
    assert ratio < 1.0

    loaded = load_project(path)
    assert len(loaded.subtitle_track) == 2000
    assert loaded.subtitle_track[1999].text == "segment-1999-payload"


def test_plain_json_backward_compatible_for_large_project(tmp_path: Path) -> None:
    project = _build_large_project(1500)
    gzip_path = tmp_path / "gzip.fmm.json"
    plain_path = tmp_path / "plain.fmm.json"

    save_project(project, gzip_path)
    raw = gzip_path.read_bytes()
    plain_path.write_bytes(gzip.decompress(raw))

    loaded = load_project(plain_path)
    assert len(loaded.subtitle_track) == 1500
    assert loaded.subtitle_track[0].text == "segment-0-payload"


def test_autosave_recovery_reads_compressed_file(tmp_path: Path, monkeypatch, qtbot) -> None:
    monkeypatch.setattr("src.services.autosave.Path.home", lambda: tmp_path)

    class _FakeSettings:
        def __init__(self):
            self._store = {}

        def value(self, key, default=None, value_type=None):
            return self._store.get(key, default)

        def setValue(self, key, value):
            self._store[key] = value

    monkeypatch.setattr("src.services.autosave.QSettings", _FakeSettings)

    manager = AutoSaveManager()
    manager._timer.stop()
    manager._idle_timer.stop()

    project = _build_large_project(300)
    manager.set_project(project)
    manager.save_now()

    recovery = manager.check_for_recovery()
    assert recovery is not None
    assert recovery.exists()
    assert recovery.read_bytes()[:2] == b"\x1f\x8b"

    restored = manager.load_recovery(recovery)
    assert len(restored.subtitle_track) == 300
    assert restored.subtitle_track[0].text == "segment-0-payload"


def test_benchmark_script_reports_expected_metrics() -> None:
    mod = _load_bench_module()
    metrics = mod.run_benchmark(segment_count=200, iterations=2, text_length=32)
    assert metrics["save_ms_avg"] > 0
    assert metrics["load_ms_avg"] > 0
    assert 0 < metrics["compression_ratio_avg"] < 1

    lines = mod.format_report(metrics)
    assert lines[0] == "PROJECT_IO_BENCHMARK"
    assert any(line.startswith("compression_ratio_avg:") for line in lines)
