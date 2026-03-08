"""Project sync service for manual pull/conflict-check/push workflows."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from src.services.settings_manager import SettingsManager


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


class ProjectSyncService:
    """Sync a local project file with a local-folder backend target."""

    def __init__(self, settings: SettingsManager | None = None) -> None:
        self._settings = settings or SettingsManager()

    def sync(
        self,
        project_path: Path,
        sync_root: Path,
        policy: SyncPolicy = SyncPolicy.AUTO,
    ) -> SyncResult:
        file_key = project_path.name
        if not file_key:
            return SyncResult(SyncResultCode.ERROR, "Invalid project file path.", file_key)
        if not project_path.is_file():
            return SyncResult(SyncResultCode.ERROR, "Project file does not exist.", file_key)
        if not sync_root or not sync_root.is_dir():
            return SyncResult(SyncResultCode.ERROR, "Sync root is unavailable.", file_key)

        remote_path = sync_root / file_key
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

        remote_exists = remote_path.is_file()
        remote_bytes = b""
        remote_hash = ""
        remote_info: SyncFileInfo | None = None
        if remote_exists:
            try:
                remote_bytes = remote_path.read_bytes()
            except Exception as exc:
                return SyncResult(
                    SyncResultCode.ERROR,
                    "Failed to read synced project file.",
                    file_key,
                    str(exc),
                    local_info=local_info,
                )
            remote_hash = _hash_bytes(remote_bytes)
            remote_info = _file_info(remote_path, remote_hash)

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
            return self._push(project_path, remote_path, state_map, file_key, local_info=local_info)

        # Known last sync state can disambiguate pull/push automatically.
        if last_hash and local_hash == last_hash and remote_hash != last_hash:
            return self._pull(
                project_path,
                remote_path,
                remote_bytes,
                state_map,
                file_key,
                remote_hash,
                local_info=local_info,
                remote_info=remote_info,
            )
        if last_hash and remote_hash == last_hash and local_hash != last_hash:
            return self._push(project_path, remote_path, state_map, file_key, local_info=local_info)

        # Conflict (first sync mismatch or both sides changed since last sync).
        if policy == SyncPolicy.USE_LOCAL:
            return self._push(project_path, remote_path, state_map, file_key, local_info=local_info)
        if policy == SyncPolicy.USE_REMOTE:
            return self._pull(
                project_path,
                remote_path,
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
        remote_path: Path,
        state_map: dict[str, dict[str, str]],
        file_key: str,
        local_info: SyncFileInfo | None = None,
    ) -> SyncResult:
        try:
            local_bytes = project_path.read_bytes()
            remote_path.write_bytes(local_bytes)
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
        remote_info = _file_info(remote_path, local_hash)
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
        remote_path: Path,
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
            remote_info = _file_info(remote_path, remote_hash)
        local_after = _file_info(project_path, remote_hash)
        return SyncResult(
            SyncResultCode.SUCCESS,
            "Project sync completed.",
            file_key,
            local_info=local_after,
            remote_info=remote_info,
        )

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
