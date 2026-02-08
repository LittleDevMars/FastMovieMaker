"""자막 검색용 검색 바 위젯."""

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
    """자막 필터링용 검색 바.

    기능:
    - 대소문자 구분 옵션 있는 텍스트 검색
    - 실시간 필터링
    - 다음/이전 결과 이동 버튼
    """

    # (검색어, 대소문자 구분 여부)
    search_changed = Signal(str, bool)  # text, case_sensitive
    next_result = Signal()
    previous_result = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        """검색 아이콘, 입력창, 대소문자 체크, 결과 수, 이전/다음 버튼 구성."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 검색 아이콘
        search_label = QLabel("🔍")
        layout.addWidget(search_label)

        # 검색 입력
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search subtitles (Ctrl+F)")
        self._search_edit.setClearButtonEnabled(True)
        layout.addWidget(self._search_edit, 1)  # 스트레치

        # 대소문자 구분
        self._case_checkbox = QCheckBox("Match case")
        layout.addWidget(self._case_checkbox)

        # 결과 개수 표시
        self._results_label = QLabel("0 results")
        self._results_label.setMinimumWidth(70)
        layout.addWidget(self._results_label)

        # 이전/다음 결과 버튼
        self._prev_button = QToolButton()
        self._prev_button.setText("▲")
        self._prev_button.setToolTip("Previous (Shift+F3)")
        layout.addWidget(self._prev_button)

        self._next_button = QToolButton()
        self._next_button.setText("▼")
        self._next_button.setToolTip("Next (F3)")
        layout.addWidget(self._next_button)

        # 처음에는 숨김 (Ctrl+F로 표시)
        self.setVisible(False)

    def _connect_signals(self):
        """검색어/체크박스 변경 시 search_changed, 버튼 클릭 시 next/prev 시그널 연결."""
        self._search_edit.textChanged.connect(self._on_search_text_changed)
        self._case_checkbox.toggled.connect(self._on_search_text_changed)
        self._next_button.clicked.connect(self.next_result)
        self._prev_button.clicked.connect(self.previous_result)

    def _on_search_text_changed(self):
        """검색어 또는 대소문자 구분 옵션 변경 시 시그널 발생."""
        text = self._search_edit.text().strip()
        case_sensitive = self._case_checkbox.isChecked()
        self.search_changed.emit(text, case_sensitive)

    def set_focus(self):
        """검색 바를 보이게 하고 입력창에 포커스, 전체 선택."""
        self.setVisible(True)
        self._search_edit.setFocus()
        self._search_edit.selectAll()

    def close_search(self):
        """검색어 지우고 검색 바 숨김."""
        self._search_edit.clear()
        self.setVisible(False)

    def update_result_count(self, count: int, current: int = -1):
        """결과 개수/현재 인덱스 표시 갱신. current >= 0이면 'N of M' 형식."""
        if count == 0:
            self._results_label.setText("No results")
        elif current >= 0:
            self._results_label.setText(f"{current + 1} of {count}")
        else:
            self._results_label.setText(f"{count} results")

        self._next_button.setEnabled(count > 0)
        self._prev_button.setEnabled(count > 0)
