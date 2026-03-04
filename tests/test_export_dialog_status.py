from pathlib import Path

from unittest.mock import patch

from src.models.subtitle import SubtitleTrack
from src.ui.dialogs.export_dialog import ExportDialog


def test_export_dialog_worker_status_updates_label(qtbot):
    dialog = ExportDialog(Path("video.mp4"), SubtitleTrack(), video_has_audio=False)
    qtbot.addWidget(dialog)

    dialog._on_worker_status("GPU export failed, retrying with software encoder...")
    assert "retrying with software encoder" in dialog._status_label.text().lower()


@patch(
    "src.ui.dialogs.export_dialog.get_hw_info",
    return_value={
        "platform": "darwin",
        "recommended": "h264_videotoolbox",
        "candidates": ["h264_videotoolbox", "libx264"],
        "unavailable_reasons": {},
    },
)
def test_export_dialog_shows_planned_encoder_label(mock_hw_info, qtbot):
    dialog = ExportDialog(Path("video.mp4"), SubtitleTrack(), video_has_audio=False)
    qtbot.addWidget(dialog)
    assert "h264_videotoolbox" in dialog._encoder_label.text().lower()


@patch(
    "src.ui.dialogs.export_dialog.get_hw_info",
    return_value={
        "platform": "darwin",
        "recommended": "libx264",
        "candidates": ["libx264"],
        "unavailable_reasons": {"videotoolbox": "encoder help probe failed"},
    },
)
def test_export_dialog_gpu_tooltip_contains_unavailable_reason(mock_hw_info, qtbot):
    dialog = ExportDialog(Path("video.mp4"), SubtitleTrack(), video_has_audio=False)
    qtbot.addWidget(dialog)
    assert not dialog._gpu_checkbox.isEnabled()
    tooltip = dialog._gpu_checkbox.toolTip().lower()
    assert "videotoolbox" in tooltip
