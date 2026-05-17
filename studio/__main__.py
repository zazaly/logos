"""
studio.__main__
============
Entry-point so the package can be run with:

    python -m studio
"""
from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from studio.theme       import apply_windows_xp_theme
from studio.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Bulk Rename Utility")
    app.setOrganizationName("BRU")
    app.setApplicationVersion("3.0.0")

    font = QFont("FiraCode Nerd Font", 10)
    font.setHintingPreference(QFont.PreferFullHinting)
    app.setFont(font)

    apply_windows_xp_theme(app)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
