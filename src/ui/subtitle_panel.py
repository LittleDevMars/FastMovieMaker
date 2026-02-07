"""Subtitle list panel using QTableWidget with inline editing and search."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QShortcut, QKeySequence
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

from src.ui.search_bar import SearchBar

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
    style_edit_requested = Signal(int)  # segment index

    def __init__(self, parent=None):
        super().__init__(parent)
        self._track: SubtitleTrack | None = None
        self._editing = False  # guard to ignore cellChanged during rebuild
        self._search_results = []  # indexes of matched segments
        self._current_result = -1  # current highlighted result index

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header with subtitle count
        self._header_label = QLabel("Subtitles")
        self._header_label.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(self._header_label)

        # Search bar (initially hidden)
        self._search_bar = SearchBar(self)
        self._search_bar.search_changed.connect(self._on_search)
        self._search_bar.next_result.connect(self._on_next_result)
        self._search_bar.previous_result.connect(self._on_previous_result)
        layout.addWidget(self._search_bar)

        # Subtitle table
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

        # Search shortcuts
        self._setup_shortcuts()

    # --------------------------------------------------------------- Public

    def set_track(self, track: SubtitleTrack | None) -> None:
        self._track = track
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the table from the current track data."""
        # Remember current search text
        search_visible = self._search_bar.isVisible()
        if search_visible:
            search_text = self._search_bar._search_edit.text()
            case_sensitive = self._search_bar._case_checkbox.isChecked()
        else:
            search_text = ""
            case_sensitive = False

        # Rebuild table
        self._rebuild_table()

        # Restore search if active
        if search_visible and search_text:
            self._on_search(search_text, case_sensitive)

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

    # --------------------------------------------------------------- Search

    def _setup_shortcuts(self) -> None:
        """Setup keyboard shortcuts for search."""
        # Ctrl+F - show search bar
        search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        search_shortcut.activated.connect(self._show_search_bar)

        # F3 - find next
        next_shortcut = QShortcut(QKeySequence("F3"), self)
        next_shortcut.activated.connect(self._on_next_result)

        # Shift+F3 - find previous
        prev_shortcut = QShortcut(QKeySequence("Shift+F3"), self)
        prev_shortcut.activated.connect(self._on_previous_result)

        # Escape - hide search bar
        esc_shortcut = QShortcut(QKeySequence("Escape"), self)
        esc_shortcut.activated.connect(self._hide_search_bar)

    def _show_search_bar(self) -> None:
        """Show the search bar and focus it."""
        self._search_bar.set_focus()

    def _hide_search_bar(self) -> None:
        """Hide the search bar and clear search."""
        self._search_bar.close_search()
        self._clear_search_results()

    def _on_search(self, text: str, case_sensitive: bool) -> None:
        """Perform search and highlight results."""
        self._clear_search_results()

        if not text or not self._track:
            return

        # Find matching segments
        for i, seg in enumerate(self._track):
            if self._text_matches(seg.text, text, case_sensitive):
                self._search_results.append(i)

        # Highlight the table rows
        self._highlight_search_results()

        # Update result counter
        self._search_bar.update_result_count(len(self._search_results))

        # Go to first result if any
        if self._search_results:
            self._goto_result(0)

    def _text_matches(self, text: str, search: str, case_sensitive: bool) -> bool:
        """Check if text matches search criteria."""
        if not case_sensitive:
            return search.lower() in text.lower()
        return search in text

    def _highlight_search_results(self) -> None:
        """Highlight rows that match search criteria."""
        for row in range(self._table.rowCount()):
            # Reset background
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item:
                    item.setBackground(QColor(0, 0, 0, 0))  # Transparent

        # Highlight matches
        highlight_color = QColor(100, 150, 240, 50)  # Light blue with alpha
        for idx in self._search_results:
            for col in range(self._table.columnCount()):
                item = self._table.item(idx, col)
                if item:
                    item.setBackground(highlight_color)

    def _clear_search_results(self) -> None:
        """Clear search results and highlighting."""
        self._search_results = []
        self._current_result = -1

        # Clear all row highlighting
        for row in range(self._table.rowCount()):
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item:
                    item.setBackground(QColor(0, 0, 0, 0))  # Transparent

    def _goto_result(self, index: int) -> None:
        """Go to a specific search result."""
        if not self._search_results:
            return

        # Wrap around if out of bounds
        if index < 0:
            index = len(self._search_results) - 1
        elif index >= len(self._search_results):
            index = 0

        self._current_result = index
        row = self._search_results[index]

        # Select and scroll to row
        self._table.selectRow(row)
        self._table.scrollToItem(self._table.item(row, 0))

        # Seek to this subtitle
        self.seek_requested.emit(self._track[row].start_ms)

        # Update result counter with current position
        self._search_bar.update_result_count(len(self._search_results), self._current_result)

    def _on_next_result(self) -> None:
        """Go to the next search result."""
        if self._current_result >= 0 and self._search_results:
            self._goto_result(self._current_result + 1)

    def _on_previous_result(self) -> None:
        """Go to the previous search result."""
        if self._current_result >= 0 and self._search_results:
            self._goto_result(self._current_result - 1)

    # --------------------------------------------------------------- Context Menu

    def _on_context_menu(self, pos) -> None:
        row = self._table.rowAt(pos.y())
        menu = QMenu(self)

        add_action = menu.addAction("Add Subtitle Here")
        delete_action = None
        style_action = None
        if self._track and 0 <= row < len(self._track):
            delete_action = menu.addAction("Delete Subtitle")
            menu.addSeparator()
            style_action = menu.addAction("Edit Style...")

        # Add search option to context menu
        menu.addSeparator()
        search_action = menu.addAction("Find in Subtitles...")
        search_action.triggered.connect(self._show_search_bar)

        action = menu.exec(self._table.viewport().mapToGlobal(pos))
        if action is not None and action == style_action:
            self.style_edit_requested.emit(row)
        elif action == add_action:
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
