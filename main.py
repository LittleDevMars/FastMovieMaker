"""FastMovieMaker application entry point."""

import os
import sys
from pathlib import Path

# SIGABRT 등 크래시 시 Python 트레이스백 출력 (원인 분석용)
try:
    import faulthandler
    faulthandler.enable(all_threads=True)
except Exception:
    pass

# Set platform-appropriate media backend
if sys.platform == "darwin":
    os.environ.setdefault("QT_MEDIA_BACKEND", "darwin")
elif sys.platform == "win32":
    os.environ.setdefault("QT_MEDIA_BACKEND", "windows")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QColor, QPalette

from src.utils.config import APP_NAME, ORG_NAME
from src.utils.i18n import init_language
from src.services.settings_manager import SettingsManager
from src.ui.main_window import MainWindow


def _apply_dark_theme(app: QApplication) -> None:
    """Apply a dark color palette using the Fusion style."""
    app.setStyle("Fusion")
    palette = QPalette()

    # Base colors
    palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 45))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(212, 212, 212))
    palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 45))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(50, 50, 50))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(212, 212, 212))
    palette.setColor(QPalette.ColorRole.Text, QColor(212, 212, 212))
    palette.setColor(QPalette.ColorRole.Button, QColor(55, 55, 55))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(212, 212, 212))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))

    # Links
    palette.setColor(QPalette.ColorRole.Link, QColor(80, 160, 255))
    palette.setColor(QPalette.ColorRole.LinkVisited, QColor(130, 100, 200))

    # Highlight
    palette.setColor(QPalette.ColorRole.Highlight, QColor(60, 140, 220))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))

    # Disabled
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(120, 120, 120))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(120, 120, 120))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(120, 120, 120))

    app.setPalette(palette)

    # Load QSS stylesheet
    qss_path = Path(__file__).parent / "src" / "ui" / "styles" / "dark.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))


def main() -> None:
    QApplication.setOrganizationName(ORG_NAME)
    QApplication.setApplicationName(APP_NAME)

    app = QApplication(sys.argv)
    _apply_dark_theme(app)

    # Initialize UI language from settings
    _settings = SettingsManager()
    init_language(_settings.get_ui_language())

    window = MainWindow()
    window.show()

    # 앱 종료 시 전역 QThreadPool 대기 (QRunnable 스레드 파괴 크래시 방지)
    def _on_about_to_quit() -> None:
        QThreadPool.globalInstance().waitForDone(20000)

    app.aboutToQuit.connect(_on_about_to_quit)

    # Allow opening a video via command-line argument
    if len(sys.argv) > 1:
        from pathlib import Path
        video_path = Path(sys.argv[1])
        if video_path.is_file():
            window._load_video(video_path)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
