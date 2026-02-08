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

from src.utils.i18n import tr
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
        self.setWindowTitle(tr("Jump to Frame"))
        self.setFixedWidth(400)

        self._fps = fps
        self._duration_ms = duration_ms
        self._target_ms: int | None = None

        layout = QVBoxLayout(self)

        # Current position info
        current_tc = ms_to_timecode_frames(current_ms, fps)
        info = QLabel(f"{tr('Current position')}: {current_tc}  (FPS: {fps})")
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
            f"{tr('Supported formats')}:\n"
            "  HH:MM:SS:FF  (frames)  e.g. 00:01:23:15\n"
            "  HH:MM:SS.mmm (ms)      e.g. 00:01:23.456\n"
            "  MM:SS.mmm              e.g. 01:23.456\n"
            f"  F:number / frame:number  e.g. F:300"
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
            self._show_error(tr("Please enter a value."))
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
                f"{tr('Out of range. Max')}: {ms_to_timecode_frames(self._duration_ms, self._fps)}"
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
