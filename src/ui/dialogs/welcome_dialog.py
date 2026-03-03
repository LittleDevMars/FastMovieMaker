"""웰컴 다이얼로그 및 템플릿 선택 다이얼로그.

- WelcomeDialog: 앱 시작 시 최근 파일 + 템플릿 + 빠른 시작 제공.
- TemplatePickerDialog: "New from Template…" 메뉴에서 사용.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from src.models.project_template import ProjectTemplate
from src.services.template_manager import TemplateManager
from src.utils.i18n import tr


class WelcomeDialog(QDialog):
    """앱 시작 시 표시되는 웰컴 다이얼로그."""

    RESULT_OPEN_FILE = 2   # "Open Project…" 버튼 결과 코드
    RESULT_NEW_EMPTY = 3   # "New Empty Project" 버튼 결과 코드

    def __init__(
        self,
        recent_files: List[Path],
        template_manager: Optional[TemplateManager] = None,
        parent=None,
    ) -> None:
        """
        Args:
            recent_files:     최근 열었던 프로젝트 파일 목록.
            template_manager: 템플릿 관리자. None 이면 기본 인스턴스 생성.
            parent:           부모 위젯.
        """
        super().__init__(parent)
        self.setWindowTitle(tr("Welcome to FastMovieMaker"))
        self.setMinimumSize(560, 420)
        self.setModal(True)

        self._template_mgr = template_manager or TemplateManager()
        self._recent_files = recent_files[:5]

        # 결과 저장
        self._selected_recent: Optional[Path] = None
        self._selected_template: Optional[ProjectTemplate] = None

        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── 제목 ──
        title = QLabel("<h2>FastMovieMaker</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # ── 최근 파일 + 템플릿 (가로 배치) ──
        mid_row = QHBoxLayout()

        # 최근 파일
        recent_group = QGroupBox(tr("Recent Projects"))
        recent_layout = QVBoxLayout(recent_group)

        self._recent_list = QListWidget()
        self._recent_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._recent_list.setMinimumHeight(140)
        if self._recent_files:
            for p in self._recent_files:
                item = QListWidgetItem(p.name)
                item.setToolTip(str(p))
                item.setData(Qt.ItemDataRole.UserRole, p)
                self._recent_list.addItem(item)
            self._recent_list.itemDoubleClicked.connect(self._on_recent_double_click)
        else:
            placeholder = QListWidgetItem(tr("No recent projects"))
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._recent_list.addItem(placeholder)
        recent_layout.addWidget(self._recent_list)

        open_recent_btn = QPushButton(tr("Open Selected"))
        open_recent_btn.clicked.connect(self._on_open_recent)
        recent_layout.addWidget(open_recent_btn)
        mid_row.addWidget(recent_group, 1)

        # 템플릿
        tmpl_group = QGroupBox(tr("New from Template"))
        tmpl_layout = QVBoxLayout(tmpl_group)

        for tmpl in self._template_mgr.get_builtin_templates():
            btn = QPushButton(f"{tmpl.display_name}\n{tmpl.aspect_label}")
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            btn.setProperty("template_obj", tmpl)
            btn.clicked.connect(self._on_template_clicked)
            tmpl_layout.addWidget(btn)

        mid_row.addWidget(tmpl_group, 1)
        layout.addLayout(mid_row)

        # ── 하단 버튼 ──
        btn_row = QHBoxLayout()

        open_file_btn = QPushButton(tr("Open Project\u2026"))
        open_file_btn.clicked.connect(self._on_open_file)
        btn_row.addWidget(open_file_btn)

        new_btn = QPushButton(tr("New Empty Project"))
        new_btn.clicked.connect(self._on_new_empty)
        btn_row.addWidget(new_btn)

        btn_row.addStretch()

        skip_btn = QPushButton(tr("Skip"))
        skip_btn.clicked.connect(self.reject)
        btn_row.addWidget(skip_btn)

        layout.addLayout(btn_row)

    # ------------------------------------------------------------------ Slots

    def _on_recent_double_click(self, item: QListWidgetItem) -> None:
        path: Path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self._selected_recent = path
            self.accept()

    def _on_open_recent(self) -> None:
        current = self._recent_list.currentItem()
        if current:
            path: Path = current.data(Qt.ItemDataRole.UserRole)
            if path:
                self._selected_recent = path
                self.accept()

    def _on_template_clicked(self) -> None:
        tmpl = self.sender().property("template_obj")
        if tmpl:
            self._selected_template = tmpl
            self.accept()

    def _on_open_file(self) -> None:
        self._selected_recent = None
        self._selected_template = None
        self.done(WelcomeDialog.RESULT_OPEN_FILE)

    def _on_new_empty(self) -> None:
        self.done(WelcomeDialog.RESULT_NEW_EMPTY)

    # ------------------------------------------------------------------ Public

    def selected_recent(self) -> Optional[Path]:
        """선택된 최근 파일 경로를 반환한다 (없으면 None)."""
        return self._selected_recent

    def selected_template(self) -> Optional[ProjectTemplate]:
        """선택된 템플릿을 반환한다 (없으면 None)."""
        return self._selected_template


class TemplatePickerDialog(QDialog):
    """New from Template… 메뉴 전용 템플릿 선택 다이얼로그."""

    def __init__(
        self,
        template_manager: Optional[TemplateManager] = None,
        parent=None,
    ) -> None:
        """
        Args:
            template_manager: 템플릿 관리자.
            parent:           부모 위젯.
        """
        super().__init__(parent)
        self.setWindowTitle(tr("New from Template"))
        self.setMinimumSize(380, 300)
        self.setModal(True)

        self._template_mgr = template_manager or TemplateManager()
        self._selected: Optional[ProjectTemplate] = None

        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(QLabel(tr("Select a template to create a new project:")))

        self._list = QListWidget()
        self._list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        for tmpl in self._template_mgr.get_all_templates():
            item = QListWidgetItem(
                f"{tmpl.display_name}  —  {tmpl.aspect_label}\n{tmpl.description}"
            )
            item.setData(Qt.ItemDataRole.UserRole, tmpl)
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)
        self._list.itemDoubleClicked.connect(self._on_create)
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        create_btn = QPushButton(tr("Create"))
        create_btn.clicked.connect(self._on_create)
        btn_row.addWidget(create_btn)

        cancel_btn = QPushButton(tr("Cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------ Slots

    def _on_create(self, *_) -> None:
        current = self._list.currentItem()
        if current:
            self._selected = current.data(Qt.ItemDataRole.UserRole)
            self.accept()

    # ------------------------------------------------------------------ Public

    def selected_template(self) -> Optional[ProjectTemplate]:
        """선택된 템플릿을 반환한다 (없으면 None)."""
        return self._selected
