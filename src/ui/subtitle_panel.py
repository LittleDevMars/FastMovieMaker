"""Subtitle list panel using QTableWidget with inline editing."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QLineEdit,
    QMenu,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QLabel,
)

from src.models.subtitle import SubtitleTrack
from src.utils.time_utils import ms_to_display, display_to_ms


class _TimeEditDialog(QDialog):
    """Small dialog to edit start / end times."""

    def __init__(self, start_ms: int, end_ms: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Time")
        layout = QFormLayout(self)
        self._start_edit = QLineEdit(ms_to_display(start_ms))
        self._end_edit = QLineEdit(ms_to_display(end_ms))
        layout.addRow("Start (MM:SS.mmm):", self._start_edit)
        layout.addRow("End (MM:SS.mmm):", self._end_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> tuple[int, int]:
        return display_to_ms(self._start_edit.text()), display_to_ms(self._end_edit.text())


class SubtitlePanel(QWidget):
    """Panel showing subtitle segments in a table with editing support."""

    seek_requested = Signal(int)  # ms
    text_edited = Signal(int, str)  # (segment index, new text)
    time_edited = Signal(int, int, int)  # (segment index, start_ms, end_ms)
    segment_add_requested = Signal(int, int)  # (start_ms, end_ms)
    segment_delete_requested = Signal(int)  # segment index

    def __init__(self, parent=None):
        super().__init__(parent)
        self._track: SubtitleTrack | None = None
        self._editing = False  # guard to ignore cellChanged during rebuild

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._header_label = QLabel("Subtitles")
        self._header_label.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(self._header_label)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["#", "Start", "End", "Text"])
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self._table.cellClicked.connect(self._on_cell_clicked)
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self._table.cellChanged.connect(self._on_cell_changed)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._table)

    # --------------------------------------------------------------- Public

    def set_track(self, track: SubtitleTrack | None) -> None:
        self._track = track
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the table from the current track data."""
        self._rebuild_table()

    # --------------------------------------------------------------- Build

    def _rebuild_table(self) -> None:
        self._editing = True
        self._table.setRowCount(0)
        if not self._track:
            self._header_label.setText("Subtitles")
            self._editing = False
            return

        self._header_label.setText(f"Subtitles ({len(self._track)})")
        for i, seg in enumerate(self._track):
            row = self._table.rowCount()
            self._table.insertRow(row)

            num_item = QTableWidgetItem(str(i + 1))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            num_item.setFlags(num_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 0, num_item)

            start_item = QTableWidgetItem(ms_to_display(seg.start_ms))
            start_item.setFlags(start_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 1, start_item)

            end_item = QTableWidgetItem(ms_to_display(seg.end_ms))
            end_item.setFlags(end_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 2, end_item)

            text_item = QTableWidgetItem(seg.text)
            self._table.setItem(row, 3, text_item)

        self._editing = False

    # --------------------------------------------------------------- Slots

    def _on_cell_clicked(self, row: int, _col: int) -> None:
        if self._track and 0 <= row < len(self._track):
            self.seek_requested.emit(self._track[row].start_ms)

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        if not self._track or row < 0 or row >= len(self._track):
            return

        if col == 3:
            # Enable inline editing for the text column
            item = self._table.item(row, 3)
            if item:
                self._table.editItem(item)
        elif col in (1, 2):
            # Open time edit dialog
            seg = self._track[row]
            dlg = _TimeEditDialog(seg.start_ms, seg.end_ms, self)
            if dlg.exec():
                try:
                    start, end = dlg.values()
                    if end > start:
                        self.time_edited.emit(row, start, end)
                except (ValueError, IndexError):
                    QMessageBox.warning(self, "Invalid Time", "Could not parse time values.")

    def _on_cell_changed(self, row: int, col: int) -> None:
        if self._editing or col != 3:
            return
        if not self._track or row < 0 or row >= len(self._track):
            return
        item = self._table.item(row, 3)
        if item:
            new_text = item.text().strip()
            if new_text and new_text != self._track[row].text:
                self.text_edited.emit(row, new_text)

    def _on_context_menu(self, pos) -> None:
        row = self._table.rowAt(pos.y())
        menu = QMenu(self)

        add_action = menu.addAction("Add Subtitle Here")
        delete_action = None
        if self._track and 0 <= row < len(self._track):
            delete_action = menu.addAction("Delete Subtitle")

        action = menu.exec(self._table.viewport().mapToGlobal(pos))
        if action == add_action:
            # Insert at the clicked row position or at end
            if self._track and 0 <= row < len(self._track):
                seg = self._track[row]
                # Place new segment after this one
                start = seg.end_ms
                end = start + 2000
            else:
                # Add at the end
                if self._track and len(self._track) > 0:
                    last = self._track[-1]
                    start = last.end_ms
                else:
                    start = 0
                end = start + 2000
            self.segment_add_requested.emit(start, end)
        elif action is not None and action == delete_action:
            self.segment_delete_requested.emit(row)
