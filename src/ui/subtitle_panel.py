"""Subtitle list panel using QTableView + QAbstractTableModel (virtual rows)."""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMenu,
    QMessageBox,
    QTableView,
    QVBoxLayout,
    QWidget,
    QLabel,
)

from src.ui.search_bar import SearchBar

from src.models.subtitle import SubtitleTrack
from src.utils.i18n import tr
from src.utils.time_utils import ms_to_display, parse_flexible_timecode


# ------------------------------------------------------------------ Model


class _SubtitleTableModel(QAbstractTableModel):
    """Virtual model backed by SubtitleTrack — only provides data for visible rows."""

    HEADERS = [tr("#"), tr("Start"), tr("End"), tr("Text"), tr("Vol")]

    # Signals forwarded to panel
    text_committed = Signal(int, str)      # (row, new_text)
    volume_committed = Signal(int, float)  # (row, new_volume)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._track: SubtitleTrack | None = None
        self._search_rows: set[int] = set()

    def set_track(self, track: SubtitleTrack | None) -> None:
        self.beginResetModel()
        self._track = track
        self._search_rows.clear()
        self.endResetModel()

    def notify_data_changed(self) -> None:
        """Notify that all data may have changed (e.g. after external edit)."""
        self.beginResetModel()
        self.endResetModel()

    def set_search_rows(self, rows: set[int]) -> None:
        self._search_rows = rows
        top_left = self.index(0, 0)
        bot_right = self.index(self.rowCount() - 1, self.columnCount() - 1)
        if top_left.isValid() and bot_right.isValid():
            self.dataChanged.emit(top_left, bot_right)

    # ---- QAbstractTableModel overrides ----

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._track) if self._track else 0

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return 5

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not self._track:
            return None
        row, col = index.row(), index.column()
        if row < 0 or row >= len(self._track):
            return None

        seg = self._track[row]

        if role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.EditRole:
            if col == 0:
                return str(row + 1)
            elif col == 1:
                return ms_to_display(seg.start_ms)
            elif col == 2:
                return ms_to_display(seg.end_ms)
            elif col == 3:
                return seg.text
            elif col == 4:
                return f"{int(seg.volume * 100)}%"

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (0, 4):
                return int(Qt.AlignmentFlag.AlignCenter)

        elif role == Qt.ItemDataRole.BackgroundRole:
            if row in self._search_rows:
                return QColor(100, 150, 240, 50)

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() in (3, 4):
            base |= Qt.ItemFlag.ItemIsEditable
        return base

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if role != Qt.ItemDataRole.EditRole or not self._track:
            return False
        row, col = index.row(), index.column()
        if row < 0 or row >= len(self._track):
            return False

        if col == 3:
            new_text = str(value).strip()
            if new_text and new_text != self._track[row].text:
                self.text_committed.emit(row, new_text)
                self.dataChanged.emit(index, index)
                return True
        elif col == 4:
            raw = str(value).strip().rstrip("%")
            try:
                pct = int(raw)
                volume = max(0.0, min(2.0, pct / 100.0))
                if volume != self._track[row].volume:
                    self.volume_committed.emit(row, volume)
                    self.dataChanged.emit(index, index)
                    return True
            except ValueError:
                pass
        return False


# ------------------------------------------------------------------ Dialog


class _TimeEditDialog(QDialog):
    """Dialog to edit start/end times with flexible timecode format support."""

    def __init__(self, start_ms: int, end_ms: int, fps: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Edit Time"))
        self._fps = fps

        layout = QFormLayout(self)

        self._start_edit = QLineEdit(ms_to_display(start_ms))
        self._end_edit = QLineEdit(ms_to_display(end_ms))
        layout.addRow(tr("Start:"), self._start_edit)
        layout.addRow(tr("End:"), self._end_edit)

        help_text = QLabel(
            f"{tr('Supported formats')}:\n"
            f"• MM:SS.mmm (e.g., 01:23.456)\n"
            f"• HH:MM:SS.mmm (e.g., 00:01:23.456)\n"
            f"• HH:MM:SS:FF (e.g., 00:01:23:15)\n"
            f"• F:123 ({tr('frame number at')} {fps} fps)"
        )
        help_text.setStyleSheet("color: gray; font-size: 10px;")
        help_text.setWordWrap(True)
        layout.addRow("", help_text)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> tuple[int, int]:
        start_ms = parse_flexible_timecode(self._start_edit.text(), self._fps)
        end_ms = parse_flexible_timecode(self._end_edit.text(), self._fps)
        return start_ms, end_ms


# ------------------------------------------------------------------ Panel


class SubtitlePanel(QWidget):
    """Panel showing subtitle segments in a virtual table with editing support."""

    seek_requested = Signal(int)  # ms
    text_edited = Signal(int, str)  # (segment index, new text)
    time_edited = Signal(int, int, int)  # (segment index, start_ms, end_ms)
    volume_edited = Signal(int, float)  # (segment index, new volume 0.0~2.0)
    segment_add_requested = Signal(int, int)  # (start_ms, end_ms)
    segment_delete_requested = Signal(int)  # segment index
    style_edit_requested = Signal(int)  # segment index
    tts_edit_requested = Signal(int)  # segment index
    font_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._track: SubtitleTrack | None = None
        self._search_results: list[int] = []
        self._current_result: int = -1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header_layout = QHBoxLayout()
        self._header_label = QLabel(tr("Subtitles"))
        self._header_label.setStyleSheet("font-weight: bold; padding: 4px;")
        header_layout.addWidget(self._header_label)

        self._font_combo = QFontComboBox(self)
        self._font_combo.currentFontChanged.connect(self._on_font_changed)
        header_layout.addWidget(self._font_combo)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Search bar
        self._search_bar = SearchBar(self)
        self._search_bar.search_changed.connect(self._on_search)
        self._search_bar.next_result.connect(self._on_next_result)
        self._search_bar.previous_result.connect(self._on_previous_result)
        layout.addWidget(self._search_bar)

        # Model + View (virtual rows)
        self._model = _SubtitleTableModel(self)
        self._model.text_committed.connect(self.text_edited)
        self._model.volume_committed.connect(self.volume_edited)

        self._table = QTableView()
        self._table.setModel(self._model)
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
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self._table.clicked.connect(self._on_clicked)
        self._table.doubleClicked.connect(self._on_double_clicked)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._table)

        self._setup_shortcuts()

    # --------------------------------------------------------------- Public

    def set_track(self, track: SubtitleTrack | None, font_family: str = "Arial") -> None:
        self._track = track
        self._model.set_track(track)
        self._update_header()
        self._font_combo.blockSignals(True)
        self._font_combo.setCurrentFont(QFont(font_family))
        self._font_combo.blockSignals(False)
        self._font_combo.setVisible(track is not None)

    def refresh(self, font_family: str = "Arial") -> None:
        """Notify model of external data change and re-apply search."""
        search_visible = self._search_bar.isVisible()
        if search_visible:
            search_text = self._search_bar._search_edit.text()
            case_sensitive = self._search_bar._case_checkbox.isChecked()
        else:
            search_text = ""
            case_sensitive = False

        self._model.notify_data_changed()
        self._update_header()
        self._font_combo.blockSignals(True)
        self._font_combo.setCurrentFont(QFont(font_family))
        self._font_combo.blockSignals(False)
        self._font_combo.setVisible(self._track is not None)

        if search_visible and search_text:
            self._on_search(search_text, case_sensitive)

    # --------------------------------------------------------------- Internal

    def _update_header(self) -> None:
        count = len(self._track) if self._track else 0
        self._header_label.setText(f"{tr('Subtitles')} ({count})" if count else tr("Subtitles"))

    def _on_font_changed(self, font: QFont) -> None:
        if self._track:
            self.font_changed.emit(font.family())
			
	# --------------------------------------------------------------- Slots

    def _on_clicked(self, index: QModelIndex) -> None:
        row = index.row()
        if self._track and 0 <= row < len(self._track):
            self.seek_requested.emit(self._track[row].start_ms)

    def _on_double_clicked(self, index: QModelIndex) -> None:
        row, col = index.row(), index.column()
        if not self._track or row < 0 or row >= len(self._track):
            return

        if col in (3, 4):
            self._table.edit(index)
        elif col in (1, 2):
            seg = self._track[row]
            from src.services.settings_manager import SettingsManager
            settings = SettingsManager()
            fps = settings.get_frame_seek_fps()

            dlg = _TimeEditDialog(seg.start_ms, seg.end_ms, fps, self)
            if dlg.exec():
                try:
                    start, end = dlg.values()
                    if end > start:
                        self.time_edited.emit(row, start, end)
                    else:
                        QMessageBox.warning(
                            self, tr("Invalid Time Range"),
                            tr("End time must be greater than start time.")
                        )
                except ValueError as e:
                    QMessageBox.warning(
                        self, tr("Invalid Timecode"),
                        f"{tr('Could not parse timecode')}: {str(e)}"
                    )

    # --------------------------------------------------------------- Search

    def _setup_shortcuts(self) -> None:
        search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        search_shortcut.activated.connect(self._show_search_bar)

        next_shortcut = QShortcut(QKeySequence("F3"), self)
        next_shortcut.activated.connect(self._on_next_result)

        prev_shortcut = QShortcut(QKeySequence("Shift+F3"), self)
        prev_shortcut.activated.connect(self._on_previous_result)

        esc_shortcut = QShortcut(QKeySequence("Escape"), self)
        esc_shortcut.activated.connect(self._hide_search_bar)

    def _show_search_bar(self) -> None:
        self._search_bar.set_focus()

    def _hide_search_bar(self) -> None:
        self._search_bar.close_search()
        self._clear_search_results()

    def _on_search(self, text: str, case_sensitive: bool) -> None:
        self._clear_search_results()
        if not text or not self._track:
            return

        for i, seg in enumerate(self._track):
            if self._text_matches(seg.text, text, case_sensitive):
                self._search_results.append(i)

        self._model.set_search_rows(set(self._search_results))
        self._search_bar.update_result_count(len(self._search_results))

        if self._search_results:
            self._goto_result(0)

    @staticmethod
    def _text_matches(text: str, search: str, case_sensitive: bool) -> bool:
        if not case_sensitive:
            return search.lower() in text.lower()
        return search in text

    def _clear_search_results(self) -> None:
        self._search_results = []
        self._current_result = -1
        self._model.set_search_rows(set())

    def _goto_result(self, index: int) -> None:
        if not self._search_results:
            return
        if index < 0:
            index = len(self._search_results) - 1
        elif index >= len(self._search_results):
            index = 0

        self._current_result = index
        row = self._search_results[index]

        self._table.selectRow(row)
        self._table.scrollTo(self._model.index(row, 0))

        self.seek_requested.emit(self._track[row].start_ms)
        self._search_bar.update_result_count(len(self._search_results), self._current_result)

    def _on_next_result(self) -> None:
        if self._current_result >= 0 and self._search_results:
            self._goto_result(self._current_result + 1)

    def _on_previous_result(self) -> None:
        if self._current_result >= 0 and self._search_results:
            self._goto_result(self._current_result - 1)

    # --------------------------------------------------------------- Context Menu

    def _on_context_menu(self, pos) -> None:
        index = self._table.indexAt(pos)
        row = index.row() if index.isValid() else -1
        menu = QMenu(self)

        add_action = menu.addAction(tr("Add Subtitle Here"))
        delete_action = None
        style_action = None
        tts_action = None
        if self._track and 0 <= row < len(self._track):
            delete_action = menu.addAction(tr("Delete Subtitle"))
            menu.addSeparator()
            style_action = menu.addAction(tr("Edit Style..."))
            tts_action = menu.addAction(tr("Edit TTS Settings..."))

        menu.addSeparator()
        search_action = menu.addAction(tr("Find in Subtitles..."))
        search_action.triggered.connect(self._show_search_bar)

        action = menu.exec(self._table.viewport().mapToGlobal(pos))
        if action is not None and action == style_action:
            self.style_edit_requested.emit(row)
        elif action is not None and action == tts_action:
            self.tts_edit_requested.emit(row)
        elif action == add_action:
            if self._track and 0 <= row < len(self._track):
                seg = self._track[row]
                start = seg.end_ms
                end = start + 2000
            else:
                if self._track and len(self._track) > 0:
                    last = self._track[-1]
                    start = last.end_ms
                else:
                    start = 0
                end = start + 2000
            self.segment_add_requested.emit(start, end)
        elif action is not None and action == delete_action:
            self.segment_delete_requested.emit(row)
