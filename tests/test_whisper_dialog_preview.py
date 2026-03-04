from pathlib import Path

from src.models.subtitle import SubtitleSegment
from src.ui.dialogs.whisper_dialog import WhisperDialog


def test_segment_ready_updates_live_preview(qtbot):
    dialog = WhisperDialog(audio_path=Path("/tmp/fake.wav"))
    qtbot.addWidget(dialog)

    seg = SubtitleSegment(start_ms=0, end_ms=1000, text="hello preview")
    dialog._on_segment_ready(seg)

    assert dialog._segment_count == 1
    assert dialog._preview_text.toPlainText() == "hello preview"


def test_live_preview_keeps_last_8_lines(qtbot):
    dialog = WhisperDialog(audio_path=Path("/tmp/fake.wav"))
    qtbot.addWidget(dialog)

    for i in range(10):
        dialog._on_segment_ready(SubtitleSegment(start_ms=i, end_ms=i + 1, text=f"line {i}"))

    lines = dialog._preview_text.toPlainText().splitlines()
    assert len(lines) == 8
    assert lines[0] == "line 2"
    assert lines[-1] == "line 9"
