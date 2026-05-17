"""
bru.__main__
============
Entry-point so the package can be run with:

    python -m bru
"""
from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from bru.theme       import apply_windows_98_theme
from bru.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Bulk Rename Utility")
    app.setOrganizationName("BRU")
    app.setApplicationVersion("3.0.0")

    font = QFont("Segoe UI", 10)
    font.setHintingPreference(QFont.PreferFullHinting)
    app.setFont(font)

    apply_windows_98_theme(app)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
