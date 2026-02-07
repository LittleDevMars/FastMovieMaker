"""Subtitle list panel using QTableWidget."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QLabel,
)

from src.models.subtitle import SubtitleTrack
from src.utils.time_utils import ms_to_display


class SubtitlePanel(QWidget):
    """Panel showing subtitle segments in a table. Click a row to seek."""

    seek_requested = Signal(int)  # ms

    def __init__(self, parent=None):
        super().__init__(parent)
        self._track: SubtitleTrack | None = None

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

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self._table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self._table)

    def set_track(self, track: SubtitleTrack | None) -> None:
        self._track = track
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        self._table.setRowCount(0)
        if not self._track:
            self._header_label.setText("Subtitles")
            return

        self._header_label.setText(f"Subtitles ({len(self._track)})")
        for i, seg in enumerate(self._track):
            row = self._table.rowCount()
            self._table.insertRow(row)

            num_item = QTableWidgetItem(str(i + 1))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 0, num_item)
            self._table.setItem(row, 1, QTableWidgetItem(ms_to_display(seg.start_ms)))
            self._table.setItem(row, 2, QTableWidgetItem(ms_to_display(seg.end_ms)))
            self._table.setItem(row, 3, QTableWidgetItem(seg.text))

    def _on_cell_clicked(self, row: int, _col: int) -> None:
        if self._track and 0 <= row < len(self._track):
            self.seek_requested.emit(self._track[row].start_ms)
