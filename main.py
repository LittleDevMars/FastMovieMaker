"""FastMovieMaker application entry point."""

import os
import sys

# Use Windows Media Foundation backend (Qt's bundled FFmpeg backend has issues)
os.environ.setdefault("QT_MEDIA_BACKEND", "windows")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from src.utils.config import APP_NAME, ORG_NAME
from src.ui.main_window import MainWindow


def main() -> None:
    QApplication.setOrganizationName(ORG_NAME)
    QApplication.setApplicationName(APP_NAME)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    # Allow opening a video via command-line argument
    if len(sys.argv) > 1:
        from pathlib import Path
        video_path = Path(sys.argv[1])
        if video_path.is_file():
            window._load_video(video_path)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
