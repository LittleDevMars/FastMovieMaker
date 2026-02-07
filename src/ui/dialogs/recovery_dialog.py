"""Recovery dialog for crashed sessions."""

import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class RecoveryDialog(QDialog):
    """Dialog to recover from crashed session or autosave files."""

    def __init__(self, recovery_files=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Recovery Files Found")
        self.setMinimumSize(550, 350)

        self._selected_file = None
        self._recovery_files = recovery_files or []

        self._build_ui()
        self._populate_list()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header_label = QLabel(
            "FastMovieMaker was not closed properly or autosaved files were found. "
            "Would you like to recover your work?"
        )
        header_label.setWordWrap(True)
        layout.addWidget(header_label)

        # Files list
        self._file_list = QListWidget()
        self._file_list.setAlternatingRowColors(True)
        self._file_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._file_list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._file_list)

        # File details
        self._details_label = QLabel()
        layout.addWidget(self._details_label)

        # Buttons
        button_layout = QHBoxLayout()

        self._restore_button = QPushButton("Restore Selected")
        self._restore_button.clicked.connect(self.accept)
        self._restore_button.setEnabled(False)

        discard_button = QPushButton("Discard All")
        discard_button.clicked.connect(self._on_discard_all)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        button_layout.addWidget(self._restore_button)
        button_layout.addWidget(discard_button)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)

    def _populate_list(self):
        """Fill the list with recovery files."""
        self._file_list.clear()

        # Sort by modification time (newest first)
        sorted_files = sorted(
            self._recovery_files,
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        for file_path in sorted_files:
            item = QListWidgetItem(str(file_path.name))
            item.setData(Qt.ItemDataRole.UserRole, file_path)

            # Add timestamp as subtext
            mtime = file_path.stat().st_mtime
            dt = datetime.fromtimestamp(mtime)
            item.setToolTip(f"Last modified: {dt.strftime('%Y-%m-%d %H:%M:%S')}")

            self._file_list.addItem(item)

        if sorted_files:
            self._file_list.setCurrentRow(0)

    def _on_selection_changed(self):
        """Update UI when selected file changes."""
        items = self._file_list.selectedItems()
        if not items:
            self._restore_button.setEnabled(False)
            self._details_label.setText("")
            self._selected_file = None
            return

        # Get selected file
        item = items[0]
        path = item.data(Qt.ItemDataRole.UserRole)
        self._selected_file = path

        # Show details
        mtime = path.stat().st_mtime
        dt = datetime.fromtimestamp(mtime)
        file_time = dt.strftime("%Y-%m-%d %H:%M:%S")
        file_size = path.stat().st_size / 1024  # KB

        self._details_label.setText(
            f"<b>Selected file:</b> {path.name}<br>"
            f"<b>Last modified:</b> {file_time}<br>"
            f"<b>Size:</b> {file_size:.1f} KB"
        )

        self._restore_button.setEnabled(True)

    def _on_discard_all(self):
        """Discard all recovery files."""
        result = QMessageBox.question(
            self,
            "Confirm Discard",
            "Are you sure you want to discard all recovery files?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if result == QMessageBox.StandardButton.Yes:
            self.done(2)  # Custom code for "discard all"

    def get_selected_file(self) -> Path:
        """Return the selected recovery file."""
        return self._selected_file