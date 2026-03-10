"""Project sync service for manual pull/conflict-check/push workflows."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Protocol

from src.services.settings_manager import SettingsManager


class SyncBackendType(str, Enum):
    """Supported sync backend types."""

    FILESYSTEM = "filesystem"
    GIT = "git"


class SyncPolicy(str, Enum):
    """Conflict handling policy."""

    AUTO = "auto"
    USE_LOCAL = "use_local"
    USE_REMOTE = "use_remote"


class SyncResultCode(str, Enum):
    """Structured sync result code."""

    SUCCESS = "success"
    NO_CHANGES = "no_changes"
    CONFLICT = "conflict"
    ERROR = "error"


@dataclass(slots=True)
class SyncFileInfo:
    """Sync summary info for a file snapshot."""

    path: str
    size_bytes: int
    modified_at: str
    sha256: str


class ProjectSyncBackend(Protocol):
    """Backend contract for project sync sources."""

    def fetch(self, file_key: str) -> bytes | None:
        """Fetch payload by file key. Return None when missing."""

    def store(self, file_key: str, payload: bytes) -> None:
        """Store payload by file key."""

    def describe(self, file_key: str) -> SyncFileInfo | None:
        """Return file summary info for file key."""


@dataclass(slots=True)
class SyncResult:
    """Project sync result payload."""

    code: SyncResultCode
    message: str
    file_key: str
    detail: str = ""
    local_info: SyncFileInfo | None = None
    remote_info: SyncFileInfo | None = None
    conflict_reason: str | None = None


class FileSystemSyncBackend:
    """Filesystem-based sync backend rooted at a local directory."""

    def __init__(self, root_path: Path) -> None:
        self._root_path = root_path

    def fetch(self, file_key: str) -> bytes | None:
        path = self._target_path(file_key)
        if not path.is_file():
            return None
        return path.read_bytes()

    def store(self, file_key: str, payload: bytes) -> None:
        if not self._root_path.is_dir():
            raise RuntimeError("Project sync folder is unavailable.")
        path = self._target_path(file_key)
        path.write_bytes(payload)

    def describe(self, file_key: str) -> SyncFileInfo | None:
        path = self._target_path(file_key)
        if not path.is_file():
            return None
        payload = path.read_bytes()
        return _file_info(path, _hash_bytes(payload))

    def _target_path(self, file_key: str) -> Path:
        return self._root_path / Path(file_key).name


class GitSyncBackend:
    """Git working-tree sync backend.

    This backend stores sync files under `.fmm_sync_store/` in a local git repo.
    It does not push/pull remotes in this phase.
    """

    def __init__(self, repo_path: Path, store_dir: str = ".fmm_sync_store") -> None:
        self._repo_path = repo_path
        self._store_dir = store_dir

    def fetch(self, file_key: str) -> bytes | None:
        self._validate_repo()
        path = self._target_path(file_key)
        if not path.is_file():
            return None
        return path.read_bytes()

    def store(self, file_key: str, payload: bytes) -> None:
        self._validate_repo()
        path = self._target_path(file_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        rel_path = path.relative_to(self._repo_path)
        cmd = ["git", "-C", str(self._repo_path), "add", str(rel_path)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
        except OSError as exc:
            raise RuntimeError("Git is not available.") from exc
        if proc.returncode != 0:
            raise RuntimeError("Failed to stage sync file in git repository.")

    def describe(self, file_key: str) -> SyncFileInfo | None:
        self._validate_repo()
        path = self._target_path(file_key)
        if not path.is_file():
            return None
        payload = path.read_bytes()
        return _file_info(path, _hash_bytes(payload))

    def _target_path(self, file_key: str) -> Path:
        return self._repo_path / self._store_dir / Path(file_key).name

    def _validate_repo(self) -> None:
        if not self._repo_path.is_dir():
            raise RuntimeError("Git sync repository is unavailable.")
        cmd = ["git", "-C", str(self._repo_path), "rev-parse", "--is-inside-work-tree"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
        except OSError as exc:
            raise RuntimeError("Git is not available.") from exc
        if proc.returncode != 0:
            raise RuntimeError("Git sync repository is invalid.")


class ProjectSyncService:
    """Sync a local project file with a configured backend target."""

    def __init__(self, settings: SettingsManager | None = None) -> None:
        self._settings = settings or SettingsManager()

    def sync(
        self,
        project_path: Path,
        sync_root: Path | None = None,
        policy: SyncPolicy = SyncPolicy.AUTO,
        backend: ProjectSyncBackend | None = None,
    ) -> SyncResult:
        file_key = project_path.name
        if not file_key:
            return SyncResult(SyncResultCode.ERROR, "Invalid project file path.", file_key)
        if not project_path.is_file():
            return SyncResult(SyncResultCode.ERROR, "Project file does not exist.", file_key)

        backend_obj, backend_error = self._resolve_backend(sync_root, backend)
        if backend_obj is None:
            return SyncResult(SyncResultCode.ERROR, backend_error or "Sync backend is unavailable.", file_key)

        state_map = self._settings.get_project_sync_state()
        last_hash = self._last_hash_for(state_map, file_key)

        try:
            local_bytes = project_path.read_bytes()
        except Exception as exc:
            return SyncResult(
                SyncResultCode.ERROR,
                "Failed to read local project file.",
                file_key,
                str(exc),
            )
        local_hash = _hash_bytes(local_bytes)
        local_info = _file_info(project_path, local_hash)

        remote_bytes = b""
        remote_hash = ""
        remote_info: SyncFileInfo | None = None
        try:
            maybe_remote = backend_obj.fetch(file_key)
            if maybe_remote is not None:
                remote_bytes = maybe_remote
                remote_hash = _hash_bytes(remote_bytes)
                remote_info = backend_obj.describe(file_key)
        except Exception as exc:
            return SyncResult(
                SyncResultCode.ERROR,
                "Failed to read synced project file.",
                file_key,
                str(exc),
                local_info=local_info,
            )
        remote_exists = remote_hash != ""

        # Already synced.
        if remote_exists and local_hash == remote_hash:
            self._store_last_hash(state_map, file_key, local_hash)
            return SyncResult(
                SyncResultCode.NO_CHANGES,
                "Project is already up to date.",
                file_key,
                local_info=local_info,
                remote_info=remote_info,
            )

        # No remote copy yet -> push local.
        if not remote_exists:
            return self._push(
                project_path,
                backend_obj,
                state_map,
                file_key,
                local_info=local_info,
                payload=local_bytes,
            )

        # Known last sync state can disambiguate pull/push automatically.
        if last_hash and local_hash == last_hash and remote_hash != last_hash:
            return self._pull(
                project_path,
                backend_obj,
                remote_bytes,
                state_map,
                file_key,
                remote_hash,
                local_info=local_info,
                remote_info=remote_info,
            )
        if last_hash and remote_hash == last_hash and local_hash != last_hash:
            return self._push(
                project_path,
                backend_obj,
                state_map,
                file_key,
                local_info=local_info,
                payload=local_bytes,
            )

        # Conflict (first sync mismatch or both sides changed since last sync).
        if policy == SyncPolicy.USE_LOCAL:
            return self._push(
                project_path,
                backend_obj,
                state_map,
                file_key,
                local_info=local_info,
                payload=local_bytes,
            )
        if policy == SyncPolicy.USE_REMOTE:
            return self._pull(
                project_path,
                backend_obj,
                remote_bytes,
                state_map,
                file_key,
                remote_hash,
                local_info=local_info,
                remote_info=remote_info,
            )
        return SyncResult(
            SyncResultCode.CONFLICT,
            "Both local and synced versions changed.",
            file_key,
            local_info=local_info,
            remote_info=remote_info,
            conflict_reason="local_and_remote_changed",
        )

    def _push(
        self,
        project_path: Path,
        backend: ProjectSyncBackend,
        state_map: dict[str, dict[str, str]],
        file_key: str,
        local_info: SyncFileInfo | None = None,
        payload: bytes | None = None,
    ) -> SyncResult:
        try:
            local_bytes = payload if payload is not None else project_path.read_bytes()
            backend.store(file_key, local_bytes)
        except Exception as exc:
            return SyncResult(
                SyncResultCode.ERROR,
                "Failed to sync local file to sync folder.",
                file_key,
                str(exc),
                local_info=local_info,
            )
        local_hash = _hash_bytes(local_bytes)
        self._store_last_hash(state_map, file_key, local_hash)
        if local_info is None:
            local_info = _file_info(project_path, local_hash)
        try:
            remote_info = backend.describe(file_key)
        except Exception as exc:
            return SyncResult(
                SyncResultCode.ERROR,
                "Failed to read synced project file.",
                file_key,
                str(exc),
                local_info=local_info,
            )
        return SyncResult(
            SyncResultCode.SUCCESS,
            "Project sync completed.",
            file_key,
            local_info=local_info,
            remote_info=remote_info,
        )

    def _pull(
        self,
        project_path: Path,
        backend: ProjectSyncBackend,
        remote_bytes: bytes,
        state_map: dict[str, dict[str, str]],
        file_key: str,
        remote_hash: str,
        local_info: SyncFileInfo | None = None,
        remote_info: SyncFileInfo | None = None,
    ) -> SyncResult:
        try:
            project_path.write_bytes(remote_bytes)
        except Exception as exc:
            return SyncResult(
                SyncResultCode.ERROR,
                "Failed to apply synced file to local project.",
                file_key,
                str(exc),
                local_info=local_info,
                remote_info=remote_info,
            )
        self._store_last_hash(state_map, file_key, remote_hash)
        if remote_info is None:
            try:
                remote_info = backend.describe(file_key)
            except Exception as exc:
                return SyncResult(
                    SyncResultCode.ERROR,
                    "Failed to read synced project file.",
                    file_key,
                    str(exc),
                    local_info=local_info,
                )
        local_after = _file_info(project_path, remote_hash)
        return SyncResult(
            SyncResultCode.SUCCESS,
            "Project sync completed.",
            file_key,
            local_info=local_after,
            remote_info=remote_info,
        )

    def _resolve_backend(
        self,
        sync_root: Path | None,
        backend: ProjectSyncBackend | None,
    ) -> tuple[ProjectSyncBackend | None, str | None]:
        if backend is not None:
            return backend, None
        if sync_root is not None:
            if not sync_root.is_dir():
                return None, "Sync root is unavailable."
            return FileSystemSyncBackend(sync_root), None

        backend_type = str(self._settings.get_project_sync_backend()).strip().lower()
        if backend_type == SyncBackendType.GIT.value:
            repo_path = self._settings.get_project_sync_git_repo_path()
            if not repo_path:
                return None, "Git sync repository is not configured."
            repo_root = Path(repo_path)
            if not repo_root.is_dir():
                return None, "Git sync repository is unavailable."
            return GitSyncBackend(repo_root), None

        root = self._settings.get_project_sync_root_path()
        if not root:
            return None, "Project sync folder is not configured. Set it in Preferences."
        root_path = Path(root)
        if not root_path.is_dir():
            return None, "Project sync folder is unavailable."
        return FileSystemSyncBackend(root_path), None

    @staticmethod
    def _last_hash_for(state_map: dict[str, dict[str, str]], file_key: str) -> str:
        raw = state_map.get(file_key, {}).get("last_hash", "")
        return str(raw).strip()

    def _store_last_hash(
        self,
        state_map: dict[str, dict[str, str]],
        file_key: str,
        last_hash: str,
    ) -> None:
        state_map[file_key] = {
            "last_hash": last_hash,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._settings.set_project_sync_state(state_map)


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_info(path: Path, sha256: str) -> SyncFileInfo:
    try:
        stat = path.stat()
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
        size_bytes = int(stat.st_size)
    except Exception:
        modified_at = ""
        size_bytes = 0
    return SyncFileInfo(
        path=str(path),
        size_bytes=size_bytes,
        modified_at=modified_at,
        sha256=sha256,
    )
