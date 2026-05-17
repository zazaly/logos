"""
bru.theme
=========
Solarized colour palettes and QSS stylesheet generator.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

SOLARIZED_DARK: dict[str, str] = {
    "BG": "#002b36",
    "BG2": "#073642",
    "BG3": "#0b3c49",
    "BG4": "#145766",
    "FG": "#eee8d5",
    "ACC": "#268bd2",
    "ACC2": "#2aa198",
    "MUT": "#93a1a1",
    "SEL": "#094a5a",
    "BORD": "#1f5f6f",
    "WARN": "#b58900",
    "ERR": "#dc322f",
    "OK": "#859900",
}

SOLARIZED_LIGHT: dict[str, str] = {
    "BG": "#fdf6e3",
    "BG2": "#eee8d5",
    "BG3": "#e6dfcc",
    "BG4": "#d8d0bb",
    "FG": "#586e75",
    "ACC": "#268bd2",
    "ACC2": "#2aa198",
    "MUT": "#657b83",
    "SEL": "#cfe8f6",
    "BORD": "#c2b8a3",
    "WARN": "#b58900",
    "ERR": "#dc322f",
    "OK": "#859900",
}

# Default runtime palette used by widgets that reference COLORS directly.
COLORS: dict[str, str] = dict(SOLARIZED_DARK)


def _build_stylesheet(c: dict[str, str]) -> str:
    return f"""
    QMainWindow, QDialog, QWidget {{
        background:{c['BG']}; color:{c['FG']};
        font-family:'Segoe UI','SF Pro Display','Helvetica Neue',Ubuntu,sans-serif;
        font-size:12px;
    }}
    QMenuBar {{
        background:{c['BG2']}; border-bottom:1px solid {c['BORD']}; padding:2px 4px;
    }}
    QMenuBar::item:selected {{ background:{c['SEL']}; border-radius:4px; }}
    QMenu {{
        background:{c['BG3']}; border:1px solid {c['BORD']};
        border-radius:6px; padding:4px;
    }}
    QMenu::item {{ padding:5px 20px 5px 10px; border-radius:4px; }}
    QMenu::item:selected {{ background:{c['SEL']}; }}
    QMenu::separator {{ height:1px; background:{c['BORD']}; margin:3px 0; }}
    QTreeView, QTableWidget, QListWidget {{
        background:{c['BG2']}; border:1px solid {c['BORD']}; border-radius:6px;
        alternate-background-color:{c['BG3']}; gridline-color:{c['BORD']}; outline:none;
    }}
    QTreeView::item:hover, QTableWidget::item:hover, QListWidget::item:hover {{
        background:{c['BG3']};
    }}
    QTreeView::item:selected, QTableWidget::item:selected, QListWidget::item:selected {{
        background:{c['SEL']};
    }}
    QHeaderView::section {{
        background:{c['BG4']}; color:{c['MUT']}; font-size:10px; font-weight:700;
        letter-spacing:0.08em; padding:5px 8px; border:none;
        border-right:1px solid {c['BORD']}; border-bottom:1px solid {c['BORD']};
    }}
    QGroupBox {{
        background:{c['BG2']}; border:1px solid {c['BORD']}; border-radius:8px;
        margin-top:14px; padding:8px 8px 6px 8px;
        font-size:10px; font-weight:700; color:{c['ACC2']}; letter-spacing:0.1em;
    }}
    QGroupBox::title {{
        subcontrol-origin:margin; subcontrol-position:top left;
        left:10px; top:0px; padding:0 6px; background:{c['BG2']};
    }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background:{c['BG3']}; border:1px solid {c['BORD']}; border-radius:4px;
        padding:3px 7px; color:{c['FG']}; min-height:22px;
        selection-background-color:{c['SEL']};
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border-color:{c['ACC']};
    }}
    QLineEdit[valid="false"] {{
        border-color:{c['ERR']}; background:#3a1c1c;
    }}
    QComboBox::drop-down {{ border:none; width:20px; }}
    QComboBox QAbstractItemView {{
        background:{c['BG3']}; border:1px solid {c['BORD']};
        selection-background-color:{c['SEL']}; border-radius:4px;
    }}
    QCheckBox {{ color:{c['FG']}; spacing:5px; }}
    QCheckBox::indicator {{
        width:14px; height:14px; border:1px solid {c['BORD']};
        border-radius:3px; background:{c['BG3']};
    }}
    QCheckBox::indicator:checked {{ background:{c['ACC']}; border-color:{c['ACC']}; }}
    QPushButton {{
        background:{c['BG3']}; border:1px solid {c['BORD']}; border-radius:5px;
        padding:4px 12px; color:{c['FG']}; min-height:24px;
    }}
    QPushButton:hover  {{ background:{c['SEL']}; border-color:{c['ACC']}; }}
    QPushButton:pressed {{ background:#0f2545; }}
    QPushButton#renameBtn {{
        background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 #2563eb,stop:1 #1d4ed8);
        border:none; border-radius:7px; color:white;
        font-size:13px; font-weight:700; letter-spacing:0.06em;
        padding:10px 36px; min-width:130px;
    }}
    QPushButton#renameBtn:hover {{
        background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 #3b82f6,stop:1 #2563eb);
    }}
    QPushButton#renameBtn:pressed {{ background:#1e40af; }}
    QPushButton#undoBtn {{
        background:{c['BG3']}; border:1px solid {c['BORD']}; border-radius:5px;
        padding:8px 18px; color:{c['WARN']}; font-weight:600;
    }}
    QPushButton#undoBtn:hover {{ border-color:{c['WARN']}; }}
    QPushButton#undoBtn:disabled {{ color:{c['MUT']}; border-color:{c['BG4']}; }}
    QScrollArea {{ border:none; }}
    QScrollBar:vertical {{
        background:{c['BG']}; width:8px; margin:0;
    }}
    QScrollBar::handle:vertical {{
        background:{c['BORD']}; border-radius:4px; min-height:24px;
    }}
    QScrollBar::handle:vertical:hover {{ background:{c['MUT']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
    QScrollBar:horizontal {{
        background:{c['BG']}; height:8px; margin:0;
    }}
    QScrollBar::handle:horizontal {{
        background:{c['BORD']}; border-radius:4px; min-width:24px;
    }}
    QScrollBar::handle:horizontal:hover {{ background:{c['MUT']}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}
    QSplitter::handle:horizontal {{ background:{c['BORD']}; width:4px; }}
    QSplitter::handle:vertical   {{ background:{c['BORD']}; height:4px; }}
    QStatusBar {{
        background:{c['BG2']}; color:{c['MUT']}; font-size:11px;
        border-top:1px solid {c['BORD']};
    }}
    QProgressBar {{
        background:{c['BG3']}; border:1px solid {c['BORD']}; border-radius:4px;
        height:6px; text-align:center; color:transparent;
    }}
    QProgressBar::chunk {{
        background:{c['ACC']}; border-radius:4px;
    }}
    QToolTip {{
        background:{c['BG4']}; color:{c['FG']}; border:1px solid {c['BORD']};
        border-radius:4px; padding:4px 8px; font-size:11px;
    }}
    QTabWidget::pane {{
        background:{c['BG2']}; border:1px solid {c['BORD']}; border-radius:6px;
    }}
    QTabBar::tab {{
        background:{c['BG3']}; color:{c['MUT']}; padding:5px 14px;
        border:1px solid {c['BORD']}; border-bottom:none; border-radius:4px 4px 0 0;
        margin-right:2px;
    }}
    QTabBar::tab:selected {{ background:{c['BG2']}; color:{c['FG']}; border-bottom:none; }}
    QTabBar::tab:hover    {{ color:{c['FG']}; }}
    """


def apply_theme(app: QApplication, palette: dict[str, str]) -> None:
    """Apply a palette + stylesheet to a QApplication instance."""
    COLORS.clear()
    COLORS.update(palette)
    c = COLORS
    pal = QPalette()
    pal.setColor(QPalette.Window,          QColor(c["BG"]))
    pal.setColor(QPalette.WindowText,      QColor(c["FG"]))
    pal.setColor(QPalette.Base,            QColor(c["BG2"]))
    pal.setColor(QPalette.AlternateBase,   QColor(c["BG3"]))
    pal.setColor(QPalette.Text,            QColor(c["FG"]))
    pal.setColor(QPalette.Button,          QColor(c["BG3"]))
    pal.setColor(QPalette.ButtonText,      QColor(c["FG"]))
    pal.setColor(QPalette.Highlight,       QColor(c["SEL"]))
    pal.setColor(QPalette.HighlightedText, QColor(c["FG"]))
    pal.setColor(QPalette.PlaceholderText, QColor(c["MUT"]))
    app.setPalette(pal)
    app.setStyleSheet(_build_stylesheet(c))


def apply_dark_theme(app: QApplication) -> None:
    apply_theme(app, SOLARIZED_DARK)


def apply_light_theme(app: QApplication) -> None:
    apply_theme(app, SOLARIZED_LIGHT)


def apply_windows_98_theme(app: QApplication) -> None:
    """Apply a classic Windows 98 inspired palette/theme."""
    app.setStyle(QStyleFactory.create("Windows"))
    app.setStyleSheet("")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#C0C0C0"))
    pal.setColor(QPalette.WindowText, QColor("#000000"))
    pal.setColor(QPalette.Base, QColor("#FFFFFF"))
    pal.setColor(QPalette.AlternateBase, QColor("#E0E0E0"))
    pal.setColor(QPalette.Text, QColor("#000000"))
    pal.setColor(QPalette.Button, QColor("#C0C0C0"))
    pal.setColor(QPalette.ButtonText, QColor("#000000"))
    pal.setColor(QPalette.Highlight, QColor("#000080"))
    pal.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.PlaceholderText, QColor("#808080"))
    app.setPalette(pal)
    app.setFont(QFont("MS Sans Serif", 9))
    COLORS.clear()
    COLORS.update({
        "BG": "#C0C0C0",
        "BG2": "#D4D0C8",
        "BG3": "#FFFFFF",
        "BG4": "#DFDFDF",
        "FG": "#000000",
        "ACC": "#000080",
        "ACC2": "#000080",
        "MUT": "#606060",
        "SEL": "#000080",
        "BORD": "#808080",
        "WARN": "#7A4B00",
        "ERR": "#A00000",
        "OK": "#008000",
    })
