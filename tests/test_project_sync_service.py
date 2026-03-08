"""Unit tests for local-folder project sync service."""

from __future__ import annotations

from pathlib import Path

from src.services.project_sync_service import (
    ProjectSyncService,
    SyncPolicy,
    SyncResultCode,
)


class _FakeSettings:
    def __init__(self) -> None:
        self.state: dict[str, dict[str, str]] = {}

    def get_project_sync_state(self) -> dict[str, dict[str, str]]:
        return dict(self.state)

    def set_project_sync_state(self, state: dict[str, dict[str, str]]) -> None:
        self.state = dict(state)


def test_sync_push_and_no_changes(tmp_path: Path) -> None:
    local = tmp_path / "sample.fmm.json"
    local.write_text('{"a":1}', encoding="utf-8")
    sync_root = tmp_path / "sync"
    sync_root.mkdir()
    settings = _FakeSettings()
    svc = ProjectSyncService(settings=settings)  # type: ignore[arg-type]

    first = svc.sync(local, sync_root)
    assert first.code == SyncResultCode.SUCCESS
    assert first.local_info is not None
    assert first.remote_info is not None
    assert (sync_root / "sample.fmm.json").read_text(encoding="utf-8") == '{"a":1}'

    second = svc.sync(local, sync_root)
    assert second.code == SyncResultCode.NO_CHANGES
    assert second.local_info is not None
    assert second.remote_info is not None


def test_sync_pull_when_remote_changed_and_local_unchanged(tmp_path: Path) -> None:
    local = tmp_path / "sample.fmm.json"
    local.write_text('{"base":1}', encoding="utf-8")
    sync_root = tmp_path / "sync"
    sync_root.mkdir()
    settings = _FakeSettings()
    svc = ProjectSyncService(settings=settings)  # type: ignore[arg-type]

    assert svc.sync(local, sync_root).code == SyncResultCode.SUCCESS
    (sync_root / "sample.fmm.json").write_text('{"remote":2}', encoding="utf-8")

    result = svc.sync(local, sync_root)
    assert result.code == SyncResultCode.SUCCESS
    assert result.local_info is not None
    assert result.remote_info is not None
    assert local.read_text(encoding="utf-8") == '{"remote":2}'


def test_sync_push_when_local_changed_and_remote_unchanged(tmp_path: Path) -> None:
    local = tmp_path / "sample.fmm.json"
    local.write_text('{"base":1}', encoding="utf-8")
    sync_root = tmp_path / "sync"
    sync_root.mkdir()
    settings = _FakeSettings()
    svc = ProjectSyncService(settings=settings)  # type: ignore[arg-type]

    assert svc.sync(local, sync_root).code == SyncResultCode.SUCCESS
    local.write_text('{"local":3}', encoding="utf-8")

    result = svc.sync(local, sync_root)
    assert result.code == SyncResultCode.SUCCESS
    assert result.local_info is not None
    assert result.remote_info is not None
    assert (sync_root / "sample.fmm.json").read_text(encoding="utf-8") == '{"local":3}'


def test_sync_conflict_and_manual_resolution(tmp_path: Path) -> None:
    local = tmp_path / "sample.fmm.json"
    local.write_text('{"base":1}', encoding="utf-8")
    sync_root = tmp_path / "sync"
    sync_root.mkdir()
    settings = _FakeSettings()
    svc = ProjectSyncService(settings=settings)  # type: ignore[arg-type]

    assert svc.sync(local, sync_root).code == SyncResultCode.SUCCESS
    local.write_text('{"local":4}', encoding="utf-8")
    (sync_root / "sample.fmm.json").write_text('{"remote":5}', encoding="utf-8")

    conflict = svc.sync(local, sync_root)
    assert conflict.code == SyncResultCode.CONFLICT
    assert conflict.local_info is not None
    assert conflict.remote_info is not None
    assert conflict.conflict_reason == "local_and_remote_changed"

    use_remote = svc.sync(local, sync_root, policy=SyncPolicy.USE_REMOTE)
    assert use_remote.code == SyncResultCode.SUCCESS
    assert use_remote.local_info is not None
    assert use_remote.remote_info is not None
    assert local.read_text(encoding="utf-8") == '{"remote":5}'

    local.write_text('{"local":6}', encoding="utf-8")
    (sync_root / "sample.fmm.json").write_text('{"remote":7}', encoding="utf-8")
    conflict2 = svc.sync(local, sync_root)
    assert conflict2.code == SyncResultCode.CONFLICT
    assert conflict2.local_info is not None
    assert conflict2.remote_info is not None
    use_local = svc.sync(local, sync_root, policy=SyncPolicy.USE_LOCAL)
    assert use_local.code == SyncResultCode.SUCCESS
    assert use_local.local_info is not None
    assert use_local.remote_info is not None
    assert (sync_root / "sample.fmm.json").read_text(encoding="utf-8") == '{"local":6}'


def test_sync_fails_for_missing_project_or_invalid_root(tmp_path: Path) -> None:
    settings = _FakeSettings()
    svc = ProjectSyncService(settings=settings)  # type: ignore[arg-type]
    missing_project = tmp_path / "missing.fmm.json"
    root = tmp_path / "sync"
    root.mkdir()

    missing_result = svc.sync(missing_project, root)
    assert missing_result.code == SyncResultCode.ERROR

    local = tmp_path / "sample.fmm.json"
    local.write_text("{}", encoding="utf-8")
    invalid_root = tmp_path / "not_exists"
    invalid_root_result = svc.sync(local, invalid_root)
    assert invalid_root_result.code == SyncResultCode.ERROR
    assert invalid_root_result.local_info is None
