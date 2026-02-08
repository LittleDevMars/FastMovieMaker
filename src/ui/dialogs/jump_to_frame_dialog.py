"""Jump to Frame / Timecode dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from src.utils.time_utils import ms_to_timecode_frames, parse_flexible_timecode


class JumpToFrameDialog(QDialog):
    """Dialog for jumping to a specific frame or timecode position."""

    def __init__(
        self,
        current_ms: int,
        fps: int,
        duration_ms: int,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Jump to Frame")
        self.setFixedWidth(400)

        self._fps = fps
        self._duration_ms = duration_ms
        self._target_ms: int | None = None

        layout = QVBoxLayout(self)

        # Current position info
        current_tc = ms_to_timecode_frames(current_ms, fps)
        info = QLabel(f"현재 위치: {current_tc}  (FPS: {fps})")
        info.setStyleSheet("color: gray;")
        layout.addWidget(info)

        # Input field
        self._input = QLineEdit()
        self._input.setText(current_tc)
        self._input.selectAll()
        self._input.setPlaceholderText("00:00:00:00")
        layout.addWidget(self._input)

        # Format help
        help_text = QLabel(
            "지원 형식:\n"
            "  HH:MM:SS:FF  (프레임)  예: 00:01:23:15\n"
            "  HH:MM:SS.mmm (밀리초)  예: 00:01:23.456\n"
            "  MM:SS.mmm              예: 01:23.456\n"
            f"  F:숫자 또는 frame:숫자   예: F:300"
        )
        help_text.setStyleSheet("color: gray; font-size: 11px;")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        # Error label
        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: red;")
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._input.returnPressed.connect(self._on_accept)

    def _on_accept(self) -> None:
        text = self._input.text().strip()
        if not text:
            self._show_error("값을 입력하세요.")
            return

        try:
            ms = parse_flexible_timecode(text, self._fps)
        except ValueError as e:
            self._show_error(str(e))
            return

        if ms < 0:
            ms = 0
        if ms > self._duration_ms:
            self._show_error(
                f"범위를 초과했습니다. 최대: {ms_to_timecode_frames(self._duration_ms, self._fps)}"
            )
            return

        self._target_ms = ms
        self.accept()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(True)

    def target_ms(self) -> int | None:
        """Return parsed target position in ms, or None if cancelled."""
        return self._target_ms
