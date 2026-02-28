"""GPT 대본 자동 생성 다이얼로그."""

from __future__ import annotations

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from src.services.settings_manager import SettingsManager
from src.utils.i18n import tr
from src.workers.gpt_script_worker import GptScriptWorker


class GptScriptDialog(QDialog):
    """주제·스타일·길이 설정으로 GPT 대본을 생성하고 편집하는 다이얼로그.

    dlg.exec() == QDialog.Accepted 이면 dlg.get_script()로 결과 텍스트 획득.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Generate Script with AI"))
        self.setMinimumSize(540, 480)
        self.setModal(True)

        self._thread: QThread | None = None
        self._worker: GptScriptWorker | None = None

        self._build_ui()

    # ── UI 구성 ─────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 주제 입력
        topic_group = QGroupBox(tr("Topic / Context:"))
        topic_layout = QVBoxLayout()
        self._topic_edit = QPlainTextEdit()
        self._topic_edit.setPlaceholderText(
            "예: 인공지능의 역사를 쉽게 설명해줘\n"
            "Ex: Explain the history of AI in simple terms"
        )
        self._topic_edit.setFixedHeight(80)
        topic_layout.addWidget(self._topic_edit)
        topic_group.setLayout(topic_layout)
        layout.addWidget(topic_group)

        # 스타일·길이·언어 설정
        settings_group = QGroupBox(tr("Settings"))
        settings_layout = QFormLayout()

        self._style_combo = QComboBox()
        self._style_combo.addItem(tr("Informative"), "informative")
        self._style_combo.addItem(tr("Casual"),      "casual")
        self._style_combo.addItem(tr("Persuasive"),  "persuasive")
        self._style_combo.addItem(tr("Humorous"),    "humorous")
        settings_layout.addRow(tr("Style:"), self._style_combo)

        self._length_combo = QComboBox()
        self._length_combo.addItem(tr("Short (~300 chars)"),  "short")
        self._length_combo.addItem(tr("Medium (~700 chars)"), "medium")
        self._length_combo.addItem(tr("Long (~1500 chars)"),  "long")
        self._length_combo.setCurrentIndex(1)  # medium 기본값
        settings_layout.addRow(tr("Length:"), self._length_combo)

        self._lang_combo = QComboBox()
        self._lang_combo.addItem("Korean", "ko")
        self._lang_combo.addItem("English", "en")
        settings_layout.addRow(tr("Language:"), self._lang_combo)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Generate 버튼 + 진행바
        gen_row = QHBoxLayout()
        self._generate_btn = QPushButton(tr("Generate"))
        self._generate_btn.clicked.connect(self._on_generate)
        gen_row.addWidget(self._generate_btn)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # indeterminate
        self._progress_bar.setVisible(False)
        gen_row.addWidget(self._progress_bar, stretch=1)
        layout.addLayout(gen_row)

        # 결과 편집
        result_group = QGroupBox(tr("Generated Script:"))
        result_layout = QVBoxLayout()
        self._result_edit = QPlainTextEdit()
        self._result_edit.setEnabled(False)
        self._result_edit.setMinimumHeight(160)
        result_layout.addWidget(self._result_edit)
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)

        # 버튼 박스
        self._button_box = QDialogButtonBox()
        self._use_btn = self._button_box.addButton(
            tr("Use This Script"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._use_btn.setEnabled(False)
        cancel_btn = self._button_box.addButton(
            tr("Cancel"), QDialogButtonBox.ButtonRole.RejectRole
        )
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self._on_cancel)
        layout.addWidget(self._button_box)

    # ── 슬롯 ────────────────────────────────────────────────────────────────

    def _on_generate(self) -> None:
        topic = self._topic_edit.toPlainText().strip()
        if not topic:
            QMessageBox.warning(
                self,
                tr("Warning"),
                tr("Please enter a topic or context to generate a script."),
            )
            return

        api_key = SettingsManager().get_openai_api_key()
        if not api_key:
            QMessageBox.warning(
                self,
                tr("API Key Required"),
                tr("OpenAI API key is not set.\nSet it in Edit > Preferences > API Keys."),
            )
            return

        style    = self._style_combo.currentData()
        length   = self._length_combo.currentData()
        language = self._lang_combo.currentData()

        # UI 비활성화
        self._generate_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._result_edit.setEnabled(False)
        self._use_btn.setEnabled(False)

        # 워커 시작
        self._thread = QThread()
        self._worker = GptScriptWorker(topic, style, length, language, api_key)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._cleanup_thread)
        self._worker.error.connect(self._cleanup_thread)

        self._thread.start()

    def _on_finished(self, script: str) -> None:
        self._result_edit.setPlainText(script)
        self._result_edit.setEnabled(True)
        self._use_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        self._generate_btn.setEnabled(True)

    def _on_error(self, message: str) -> None:
        self._progress_bar.setVisible(False)
        self._generate_btn.setEnabled(True)
        QMessageBox.critical(
            self,
            tr("Error"),
            f"{tr('Failed to generate script')}:\n\n{message}",
        )

    def _on_cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
        self._cleanup_thread()
        self.reject()

    def _cleanup_thread(self) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(5000)
        self._thread = None
        self._worker = None

    # ── 공개 API ────────────────────────────────────────────────────────────

    def get_script(self) -> str:
        """Accept 후 생성된 스크립트 텍스트 반환."""
        return self._result_edit.toPlainText()

    def closeEvent(self, event) -> None:
        self._on_cancel()
        super().closeEvent(event)
