"""Backend contract tests for project sync backends."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.services.project_sync_service import FileSystemSyncBackend, GitSyncBackend


def _git_available() -> bool:
    proc = subprocess.run(["git", "--version"], capture_output=True, text=True)
    return proc.returncode == 0


def test_filesystem_backend_fetch_store_describe(tmp_path: Path) -> None:
    root = tmp_path / "sync"
    root.mkdir()
    backend = FileSystemSyncBackend(root)

    assert backend.fetch("demo.fmm.json") is None

    payload = b'{"name":"demo"}'
    backend.store("demo.fmm.json", payload)

    fetched = backend.fetch("demo.fmm.json")
    assert fetched == payload

    info = backend.describe("demo.fmm.json")
    assert info is not None
    assert info.path.endswith("demo.fmm.json")
    assert info.size_bytes == len(payload)
    assert len(info.sha256) == 64


@pytest.mark.skipif(not _git_available(), reason="git is not available")
def test_git_backend_fetch_store_describe(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True, text=True)

    backend = GitSyncBackend(repo)
    payload = b'{"id":1}'
    backend.store("demo.fmm.json", payload)

    fetched = backend.fetch("demo.fmm.json")
    assert fetched == payload

    info = backend.describe("demo.fmm.json")
    assert info is not None
    assert info.path.endswith(".fmm_sync_store/demo.fmm.json")
    assert info.size_bytes == len(payload)


@pytest.mark.skipif(not _git_available(), reason="git is not available")
def test_git_backend_raises_when_repo_invalid(tmp_path: Path) -> None:
    missing_repo = tmp_path / "missing-repo"
    backend = GitSyncBackend(missing_repo)

    with pytest.raises(RuntimeError, match="Git sync repository is unavailable\\."):
        backend.fetch("demo.fmm.json")

    repo = tmp_path / "not-a-repo"
    repo.mkdir()
    invalid_backend = GitSyncBackend(repo)
    with pytest.raises(RuntimeError, match="Git sync repository is invalid\\."):
        invalid_backend.fetch("demo.fmm.json")


def test_git_backend_stage_error_is_standardized(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    backend = GitSyncBackend(repo)

    class _Result:
        def __init__(self, returncode: int = 0) -> None:
            self.returncode = returncode
            self.stderr = "mock error"

    def _fake_run(cmd, capture_output=True, text=True):  # noqa: ANN001
        if "rev-parse" in cmd:
            return _Result(0)
        if "add" in cmd:
            return _Result(1)
        return _Result(0)

    monkeypatch.setattr("src.services.project_sync_service.subprocess.run", _fake_run)

    with pytest.raises(RuntimeError, match="Failed to stage sync file in git repository\\."):
        backend.store("demo.fmm.json", b"{}")
