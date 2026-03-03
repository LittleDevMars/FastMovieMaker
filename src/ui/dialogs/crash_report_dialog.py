"""크래시 리포트 다이얼로그.

미처리 예외 발생 시 스택 트레이스를 표시하고
사용자가 클립보드에 복사하거나 로그 폴더를 열 수 있다.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
)

from src.utils.i18n import tr


class CrashReportDialog(QDialog):
    """예외 스택 트레이스를 표시하는 크래시 리포트 다이얼로그."""

    def __init__(
        self,
        exc_type: str,
        exc_message: str,
        traceback_text: str,
        crash_log_path: Optional[Path] = None,
        parent=None,
    ) -> None:
        """
        Args:
            exc_type:        예외 클래스 이름.
            exc_message:     예외 메시지.
            traceback_text:  전체 스택 트레이스 문자열.
            crash_log_path:  저장된 크래시 로그 파일 경로 (없으면 None).
            parent:          부모 위젯.
        """
        super().__init__(parent)
        self.setWindowTitle(tr("Application Error"))
        self.setMinimumSize(600, 420)

        self._traceback_text = traceback_text
        self._crash_log_path = crash_log_path

        self._build_ui(exc_type, exc_message, traceback_text)

    # ------------------------------------------------------------------ UI

    def _build_ui(self, exc_type: str, exc_message: str, traceback_text: str) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 오류 요약
        summary = QLabel(
            f"<b>{tr('An unexpected error occurred:')}</b><br>"
            f"<code>{exc_type}: {exc_message}</code>"
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        # 스택 트레이스 (읽기 전용, 모노스페이스)
        self._trace_edit = QTextEdit()
        self._trace_edit.setReadOnly(True)
        self._trace_edit.setPlainText(traceback_text)
        mono = QFont("Courier New" if sys.platform == "win32" else "Menlo")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self._trace_edit.setFont(mono)
        self._trace_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self._trace_edit)

        # 로그 파일 안내
        if self._crash_log_path:
            path_label = QLabel(
                f"{tr('Crash log saved to:')}<br>"
                f"<small><code>{self._crash_log_path}</code></small>"
            )
            path_label.setWordWrap(True)
            layout.addWidget(path_label)

        # 버튼 행
        btn_row = QHBoxLayout()

        copy_btn = QPushButton(tr("Copy to Clipboard"))
        copy_btn.clicked.connect(self._on_copy)
        btn_row.addWidget(copy_btn)

        if self._crash_log_path:
            open_btn = QPushButton(tr("Open Log Folder"))
            open_btn.clicked.connect(self._on_open_log_folder)
            btn_row.addWidget(open_btn)

        btn_row.addStretch()

        close_btn = QPushButton(tr("Close"))
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    # ------------------------------------------------------------------ Slots

    def _on_copy(self) -> None:
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self._traceback_text)

    def _on_open_log_folder(self) -> None:
        if not self._crash_log_path:
            return
        folder = self._crash_log_path.parent
        if not folder.exists():
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        elif sys.platform == "win32":
            os.startfile(str(folder))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(folder)])
