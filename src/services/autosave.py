"""Automatic saving and recovery system."""

import json
import os
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QObject, QSettings, QTimer, Signal, Slot

from src.models.project import ProjectState
from src.services.project_io import save_project, load_project


class AutoSaveManager(QObject):
    """Manages automatic saving of projects and recovery of crashed sessions.

    Features:
    - Automatic saving on timer (default: every 30 seconds)
    - Automatic saving after edits (default: 5 seconds idle)
    - Crash recovery from autosave files
    - Recent projects list management
    """

    recovery_available = Signal(Path)  # Emitted when a recoverable file is found
    save_completed = Signal(Path)      # Emitted when autosave completes

    def __init__(self, parent: QObject = None):
        super().__init__(parent)

        # Autosave directory
        self._base_dir = Path.home() / ".fastmoviemaker"
        self._autosave_dir = self._base_dir / "autosave"
        self._autosave_dir.mkdir(parents=True, exist_ok=True)

        # Settings
        self._settings = QSettings()
        self._autosave_interval = self._settings.value("autosave/interval", 30, int)  # seconds
        self._idle_timeout = self._settings.value("autosave/idle_timeout", 5, int)    # seconds
        self._max_recent = self._settings.value("recent/max_files", 10, int)

        # State
        self._project: Optional[ProjectState] = None
        self._edited = False
        self._last_save_time = 0
        self._active_file_path: Optional[Path] = None

        # Timers
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer)
        self._timer.start(self._autosave_interval * 1000)

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._on_idle_timeout)

    def set_project(self, project: ProjectState) -> None:
        """Set the current project to be autosaved."""
        self._project = project

    def set_active_file(self, path: Optional[Path]) -> None:
        """Set the current project file path."""
        if path:
            self._active_file_path = path
            self._add_recent_file(path)

    def notify_edit(self) -> None:
        """Called whenever the project is edited."""
        self._edited = True
        self._idle_timer.start(self._idle_timeout * 1000)

    def save_now(self) -> None:
        """Force an immediate autosave."""
        if self._project:
            self._do_autosave()

    def set_autosave_interval(self, seconds: int) -> None:
        """Change the autosave interval."""
        self._autosave_interval = seconds
        self._settings.setValue("autosave/interval", seconds)
        self._timer.start(seconds * 1000)

    def set_idle_timeout(self, seconds: int) -> None:
        """Change the idle timeout before autosaving after edits."""
        self._idle_timeout = seconds
        self._settings.setValue("autosave/idle_timeout", seconds)

    def check_for_recovery(self) -> Optional[Path]:
        """Check for recovery files on startup.

        Returns:
            Path to the most recent recovery file, or None if none exist.
        """
        recovery_files = list(self._autosave_dir.glob("*.fmm.json"))
        if not recovery_files:
            return None

        # Find most recent autosave file
        recovery_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return recovery_files[0]

    def load_recovery(self, path: Path) -> ProjectState:
        """Load a project from a recovery file."""
        return load_project(path)

    def cleanup_recovery_files(self) -> None:
        """Clean up autosave files after successful recovery or discard."""
        for path in self._autosave_dir.glob("*.fmm.json"):
            try:
                path.unlink()
            except (PermissionError, OSError):
                pass  # Ignore errors during cleanup

    def get_recent_files(self) -> List[Path]:
        """Get the list of recent project files."""
        recent = self._settings.value("recent/files", [])
        if recent:
            return [Path(p) for p in recent if Path(p).is_file()]
        return []

    def clear_recent_files(self) -> None:
        """Clear the recent files list."""
        self._settings.setValue("recent/files", [])

    def _add_recent_file(self, path: Path) -> None:
        """Add a file to the recent files list."""
        recent_files = self.get_recent_files()

        # Remove if already exists (to move to top)
        str_path = str(path)
        recent_files = [p for p in recent_files if str(p) != str_path]

        # Add to front
        recent_files.insert(0, path)

        # Limit to max items
        if len(recent_files) > self._max_recent:
            recent_files = recent_files[:self._max_recent]

        # Save
        self._settings.setValue("recent/files", [str(p) for p in recent_files])

    def _do_autosave(self) -> None:
        """Perform the actual autosave."""
        if not self._project:
            return

        # Use current project name if saved, or timestamp if unsaved
        timestamp = int(time.time())
        if self._active_file_path:
            name = f"{self._active_file_path.stem}_autosave_{timestamp}.fmm.json"
        else:
            name = f"autosave_{timestamp}.fmm.json"

        save_path = self._autosave_dir / name
        save_project(self._project, save_path)
        self._last_save_time = timestamp
        self._edited = False
        self.save_completed.emit(save_path)

    @Slot()
    def _on_timer(self) -> None:
        """Called when the periodic timer fires."""
        if self._project:
            self._do_autosave()

    @Slot()
    def _on_idle_timeout(self) -> None:
        """Called when the idle timer fires (edits, then no activity)."""
        if self._edited and self._project:
            self._do_autosave()