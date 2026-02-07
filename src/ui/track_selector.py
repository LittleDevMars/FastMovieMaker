"""Track selector widget for managing multiple subtitle tracks."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QPushButton,
    QWidget,
)


class TrackSelector(QWidget):
    """Widget to select, add, remove, and rename subtitle tracks."""

    track_changed = Signal(int)  # new track index
    track_added = Signal(str)  # new track name
    track_removed = Signal(int)  # track index to remove
    track_renamed = Signal(int, str)  # (track index, new name)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._combo = QComboBox()
        self._combo.setMinimumWidth(120)
        self._combo.currentIndexChanged.connect(self._on_index_changed)
        layout.addWidget(self._combo, 1)

        self._add_btn = QPushButton("+")
        self._add_btn.setFixedWidth(30)
        self._add_btn.setToolTip("Add new track")
        self._add_btn.clicked.connect(self._on_add)
        layout.addWidget(self._add_btn)

        self._remove_btn = QPushButton("-")
        self._remove_btn.setFixedWidth(30)
        self._remove_btn.setToolTip("Remove current track")
        self._remove_btn.clicked.connect(self._on_remove)
        layout.addWidget(self._remove_btn)

        self._rename_btn = QPushButton("Aa")
        self._rename_btn.setFixedWidth(30)
        self._rename_btn.setToolTip("Rename current track")
        self._rename_btn.clicked.connect(self._on_rename)
        layout.addWidget(self._rename_btn)

    def set_tracks(self, names: list[str], active_index: int = 0) -> None:
        """Update the combo box with given track names."""
        self._updating = True
        self._combo.clear()
        for name in names:
            self._combo.addItem(name)
        if 0 <= active_index < len(names):
            self._combo.setCurrentIndex(active_index)
        self._updating = False

    def _on_index_changed(self, index: int) -> None:
        if not self._updating and index >= 0:
            self.track_changed.emit(index)

    def _on_add(self) -> None:
        name, ok = QInputDialog.getText(self, "New Track", "Track name:")
        if ok and name.strip():
            self.track_added.emit(name.strip())

    def _on_remove(self) -> None:
        index = self._combo.currentIndex()
        if index >= 0:
            self.track_removed.emit(index)

    def _on_rename(self) -> None:
        index = self._combo.currentIndex()
        if index >= 0:
            current_name = self._combo.currentText()
            name, ok = QInputDialog.getText(self, "Rename Track", "New name:", text=current_name)
            if ok and name.strip():
                self.track_renamed.emit(index, name.strip())
