from pathlib import Path

from src.models.subtitle import SubtitleTrack
from src.ui.dialogs.export_dialog import ExportDialog


def test_export_dialog_worker_status_updates_label(qtbot):
    dialog = ExportDialog(Path("video.mp4"), SubtitleTrack(), video_has_audio=False)
    qtbot.addWidget(dialog)

    dialog._on_worker_status("GPU export failed, retrying with software encoder...")
    assert "retrying with software encoder" in dialog._status_label.text().lower()
