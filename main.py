"""FastMovieMaker application entry point."""

import sys

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

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
