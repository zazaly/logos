"""Helpers for loading Qt Designer .ui files."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QWidget

GUI_DIR = Path(__file__).resolve().parent.parent / "gui"


def load_ui(name: str, parent: QWidget | None = None) -> QWidget:
    """Load a QWidget-based .ui file from the repository gui folder."""
    path = GUI_DIR / name
    ui_file = QFile(str(path))
    if not ui_file.open(QFile.ReadOnly):
        raise RuntimeError(f"Unable to open UI file: {path}")
    try:
        widget = QUiLoader().load(ui_file, parent)
    finally:
        ui_file.close()
    if widget is None:
        raise RuntimeError(f"Unable to load UI file: {path}")
    return widget
