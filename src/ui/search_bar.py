"""Search bar widget for filtering subtitles."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QWidget,
)


class SearchBar(QWidget):
    """Search bar for filtering subtitles.

    Features:
    - Text search with case sensitivity option
    - Time range filtering
    - Real-time filtering
    - Navigation (next/prev) buttons
    """

    search_changed = Signal(str, bool)  # text, case_sensitive
    next_result = Signal()
    previous_result = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Search icon
        search_label = QLabel("🔍")
        layout.addWidget(search_label)

        # Search input
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search subtitles (Ctrl+F)")
        self._search_edit.setClearButtonEnabled(True)
        layout.addWidget(self._search_edit, 1)  # Stretch factor

        # Case sensitivity
        self._case_checkbox = QCheckBox("Match case")
        layout.addWidget(self._case_checkbox)

        # Result count
        self._results_label = QLabel("0 results")
        self._results_label.setMinimumWidth(70)
        layout.addWidget(self._results_label)

        # Navigation buttons
        self._prev_button = QToolButton()
        self._prev_button.setText("▲")
        self._prev_button.setToolTip("Previous (Shift+F3)")
        layout.addWidget(self._prev_button)

        self._next_button = QToolButton()
        self._next_button.setText("▼")
        self._next_button.setToolTip("Next (F3)")
        layout.addWidget(self._next_button)

        # Initially hidden
        self.setVisible(False)

    def _connect_signals(self):
        self._search_edit.textChanged.connect(self._on_search_text_changed)
        self._case_checkbox.toggled.connect(self._on_search_text_changed)
        self._next_button.clicked.connect(self.next_result)
        self._prev_button.clicked.connect(self.previous_result)

    def _on_search_text_changed(self):
        """Emit signal when search text or case sensitivity changes."""
        text = self._search_edit.text().strip()
        case_sensitive = self._case_checkbox.isChecked()
        self.search_changed.emit(text, case_sensitive)

    def set_focus(self):
        """Give focus to the search input."""
        self.setVisible(True)
        self._search_edit.setFocus()
        self._search_edit.selectAll()

    def close_search(self):
        """Clear and hide search bar."""
        self._search_edit.clear()
        self.setVisible(False)

    def update_result_count(self, count: int, current: int = -1):
        """Update the result count display."""
        if count == 0:
            self._results_label.setText("No results")
        elif current >= 0:
            self._results_label.setText(f"{current + 1} of {count}")
        else:
            self._results_label.setText(f"{count} results")

        self._next_button.setEnabled(count > 0)
        self._prev_button.setEnabled(count > 0)