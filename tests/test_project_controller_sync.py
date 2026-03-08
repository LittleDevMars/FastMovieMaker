"""ProjectController sync action tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.services.project_sync_service import (
    SyncFileInfo,
    SyncPolicy,
    SyncResult,
    SyncResultCode,
)
from src.ui.controllers.project_controller import ProjectController
from src.utils.i18n import tr


class _FakeSettingsManager:
    def __init__(self, root_path: str | None) -> None:
        self._root_path = root_path

    def get_project_sync_root_path(self) -> str | None:
        return self._root_path


def _make_context(project_path: Path | None) -> SimpleNamespace:
    status_bar = MagicMock()
    window = MagicMock()
    return SimpleNamespace(
        current_project_path=project_path,
        project=MagicMock(),
        window=window,
        status_bar=lambda: status_bar,
    )


def test_sync_project_blocks_without_open_project(monkeypatch) -> None:
    ctx = _make_context(None)
    ctrl = ProjectController(ctx)  # type: ignore[arg-type]

    warning = MagicMock()
    monkeypatch.setattr("src.ui.controllers.project_controller.QMessageBox.warning", warning)

    ctrl.on_sync_project()

    warning.assert_called_once()


def test_sync_project_blocks_without_sync_root(tmp_path: Path, monkeypatch) -> None:
    project_path = tmp_path / "sample.fmm.json"
    project_path.write_text("{}", encoding="utf-8")
    ctx = _make_context(project_path)
    ctrl = ProjectController(ctx)  # type: ignore[arg-type]

    monkeypatch.setattr("src.ui.controllers.project_controller.SettingsManager", lambda: _FakeSettingsManager(None))
    monkeypatch.setattr("src.services.project_io.save_project", lambda project, path: None)
    warning = MagicMock()
    monkeypatch.setattr("src.ui.controllers.project_controller.QMessageBox.warning", warning)

    ctrl.on_sync_project()

    warning.assert_called_once()


def test_sync_project_success_updates_status_bar(tmp_path: Path, monkeypatch) -> None:
    project_path = tmp_path / "sample.fmm.json"
    project_path.write_text("{}", encoding="utf-8")
    sync_root = tmp_path / "sync"
    sync_root.mkdir()
    ctx = _make_context(project_path)
    ctrl = ProjectController(ctx)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "src.ui.controllers.project_controller.SettingsManager",
        lambda: _FakeSettingsManager(str(sync_root)),
    )
    monkeypatch.setattr("src.services.project_io.save_project", lambda project, path: None)

    class _FakeSyncService:
        def __init__(self, settings=None) -> None:
            pass

        def sync(self, project_path, sync_root, policy=SyncPolicy.AUTO):
            return SyncResult(SyncResultCode.SUCCESS, "Project sync completed.", project_path.name)

    monkeypatch.setattr("src.ui.controllers.project_controller.ProjectSyncService", _FakeSyncService)

    ctrl.on_sync_project()

    ctx.status_bar().showMessage.assert_called()


def test_sync_project_conflict_use_remote_reloads_project(tmp_path: Path, monkeypatch) -> None:
    project_path = tmp_path / "sample.fmm.json"
    project_path.write_text("{}", encoding="utf-8")
    sync_root = tmp_path / "sync"
    sync_root.mkdir()
    ctx = _make_context(project_path)
    ctrl = ProjectController(ctx)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "src.ui.controllers.project_controller.SettingsManager",
        lambda: _FakeSettingsManager(str(sync_root)),
    )
    monkeypatch.setattr("src.services.project_io.save_project", lambda project, path: None)

    class _FakeSyncService:
        def __init__(self, settings=None) -> None:
            self.calls = 0

        def sync(self, project_path, sync_root, policy=SyncPolicy.AUTO):
            self.calls += 1
            if self.calls == 1:
                return SyncResult(SyncResultCode.CONFLICT, "conflict", project_path.name)
            return SyncResult(SyncResultCode.SUCCESS, "Project sync completed.", project_path.name)

    monkeypatch.setattr("src.ui.controllers.project_controller.ProjectSyncService", _FakeSyncService)
    monkeypatch.setattr(ctrl, "_prompt_sync_conflict", lambda _result: SyncPolicy.USE_REMOTE)
    on_load_project = MagicMock()
    monkeypatch.setattr(ctrl, "on_load_project", on_load_project)

    ctrl.on_sync_project()

    on_load_project.assert_called_once_with(path=project_path)
    assert ctx.status_bar().showMessage.call_args[0][0] == tr("Project synced using remote version.")


def test_sync_project_conflict_cancel_keeps_state(tmp_path: Path, monkeypatch) -> None:
    project_path = tmp_path / "sample.fmm.json"
    project_path.write_text("{}", encoding="utf-8")
    sync_root = tmp_path / "sync"
    sync_root.mkdir()
    ctx = _make_context(project_path)
    ctrl = ProjectController(ctx)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "src.ui.controllers.project_controller.SettingsManager",
        lambda: _FakeSettingsManager(str(sync_root)),
    )
    monkeypatch.setattr("src.services.project_io.save_project", lambda project, path: None)

    class _FakeSyncService:
        def __init__(self, settings=None) -> None:
            pass

        def sync(self, project_path, sync_root, policy=SyncPolicy.AUTO):
            return SyncResult(SyncResultCode.CONFLICT, "conflict", project_path.name)

    monkeypatch.setattr("src.ui.controllers.project_controller.ProjectSyncService", _FakeSyncService)
    monkeypatch.setattr(ctrl, "_prompt_sync_conflict", lambda _result: None)

    ctrl.on_sync_project()

    ctx.status_bar().showMessage.assert_called()


def test_sync_project_reports_error_when_save_before_sync_fails(tmp_path: Path, monkeypatch) -> None:
    project_path = tmp_path / "sample.fmm.json"
    project_path.write_text("{}", encoding="utf-8")
    ctx = _make_context(project_path)
    ctrl = ProjectController(ctx)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "src.ui.controllers.project_controller.SettingsManager",
        lambda: _FakeSettingsManager(str(tmp_path)),
    )

    def _fail_save(project, path):
        raise RuntimeError("save failed")

    monkeypatch.setattr("src.services.project_io.save_project", _fail_save)
    critical = MagicMock()
    monkeypatch.setattr("src.ui.controllers.project_controller.QMessageBox.critical", critical)

    ctrl.on_sync_project()

    critical.assert_called_once()


def test_conflict_summary_contains_local_and_remote_fields() -> None:
    ctx = _make_context(Path("/tmp/sample.fmm.json"))
    ctrl = ProjectController(ctx)  # type: ignore[arg-type]
    result = SyncResult(
        code=SyncResultCode.CONFLICT,
        message="Both local and synced versions changed.",
        file_key="sample.fmm.json",
        local_info=SyncFileInfo(
            path="/tmp/sample.fmm.json",
            size_bytes=120,
            modified_at="2026-03-08T10:00:00+00:00",
            sha256="abcdef1234567890",
        ),
        remote_info=SyncFileInfo(
            path="/tmp/sync/sample.fmm.json",
            size_bytes=140,
            modified_at="2026-03-08T10:02:00+00:00",
            sha256="0123456789abcdef",
        ),
        conflict_reason="local_and_remote_changed",
    )

    summary = ctrl._build_conflict_summary(result)

    assert tr("Local") in summary
    assert tr("Remote") in summary
    assert "abcdef12" in summary
    assert "01234567" in summary
    assert tr("Local and remote changed since last sync.") in summary
