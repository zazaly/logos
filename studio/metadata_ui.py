"""
ui.py — Main application window with spreadsheet metadata editor.

Changes in this revision:
  - Row action buttons column: [♻ Update] [🔍 Mirror] [🧮 Auto] per row
  - Title auto-populated from filename (no extension)
  - Status messages moved to a console-style log panel below the table
  - Scrollbars always visible
  - Defragmenter-style file progress strip (one block per file, colour-coded)
  - Repackage output goes to <source>/finished/ alongside sidecars
  - Mirror = copy col-1 value to all other columns on that row
  - Update = visual confirm flash on col-1 cell
  - Auto = read col-1 numeric value, fill remaining cols +1 each
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox, QComboBox, QMessageBox, QProgressBar,
    QDialog, QSpinBox, QFormLayout, QDialogButtonBox, QToolBar,
    QTextEdit, QAbstractItemView, QMenu, QSizePolicy, QScrollArea,
    QFrame, QSplitter
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QColor, QFont, QFontDatabase, QBrush, QPainter, QPen, QTextCursor

from studio.theme import COLORS

from studio.metadata_comicxml import (
    FIELDS, FIELD_TAGS, SECTION_ORDER, DROPDOWN_OPTIONS,
    AUTO_INCREMENT_FIELDS, empty_metadata, write_comicinfo, load_or_init_comicinfo
)
from studio.metadata_archive import (
    scan_folder, get_temp_dir, get_extract_dir, count_pages, SUPPORTED_EXTENSIONS
)
from studio.metadata_worker import ExtractionWorker, RepackageWorker
from studio.metadata_sidecar import generate_cover, generate_metadata_json, generate_csv_report



def _color(name: str, default: str) -> str:
    return COLORS.get(name, default)


# ── Palette ───────────────────────────────────────────────────────────────────

DARK_BG      = _color("BG", "#1e1e2e")
PANEL_BG     = _color("BG2", "#2a2a3e")
HEADER_BG    = _color("BG4", "#313154")
SECTION_BG   = _color("BG", "#1a1a2e")
CELL_BG      = _color("BG2", "#2a2a3e")
CELL_ALT_BG  = _color("BG3", "#242436")
ACCENT       = _color("ACC", "#7c6af7")
ACCENT2      = _color("ACC2", "#a89cf7")
TEXT_MAIN    = _color("FG", "#e0e0f0")
TEXT_DIM     = _color("MUT", "#8888aa")
TEXT_SECTION = _color("FG", "#c0b8ff")
BORDER       = _color("BORD", "#3a3a5a")
SUCCESS      = _color("OK", "#4caf84")
WARNING      = _color("WARN", "#e8a838")
ERROR        = _color("ERR", "#e85555")

# Defragmenter block state colours
BLOCK_IDLE       = "#2a2a4a"
BLOCK_EXTRACTING = "#e8a838"
BLOCK_READY      = "#4caf84"
BLOCK_SAVING     = "#7c6af7"
BLOCK_DONE       = "#2d6a4f"
BLOCK_ERROR      = "#e85555"
BLOCK_REPACK     = "#1d6fa8"

STYLE = f"""
QMainWindow, QWidget {{
    background-color: {DARK_BG};
    color: {TEXT_MAIN};
    font-family: "Inter", "Segoe UI", "SF Pro Display", sans-serif;
    font-size: 13px;
}}
QTableWidget {{
    background-color: {CELL_BG};
    gridline-color: {BORDER};
    border: 1px solid {BORDER};
    border-radius: 4px;
    selection-background-color: {ACCENT};
    selection-color: white;
}}
QTableWidget::item {{
    padding: 3px 6px;
    border: none;
}}
QHeaderView::section {{
    background-color: {HEADER_BG};
    color: {TEXT_MAIN};
    padding: 5px 8px;
    border: 1px solid {BORDER};
    font-weight: bold;
    font-size: 11px;
}}
QPushButton {{
    background-color: {ACCENT};
    color: white;
    border: none;
    border-radius: 5px;
    padding: 6px 16px;
    font-weight: bold;
    font-size: 13px;
    min-width: 90px;
}}
QPushButton:hover {{ background-color: {ACCENT2}; }}
QPushButton:disabled {{
    background-color: {PANEL_BG};
    color: {TEXT_DIM};
    border: 1px solid {BORDER};
}}
QPushButton#secondary {{
    background-color: {PANEL_BG};
    border: 1px solid {BORDER};
    color: {TEXT_MAIN};
    min-width: 80px;
}}
QPushButton#secondary:hover {{ background-color: {HEADER_BG}; }}
QPushButton#row_btn {{
    background-color: transparent;
    border: 1px solid {BORDER};
    color: {TEXT_MAIN};
    border-radius: 3px;
    padding: 3px 8px;
    font-size: 13px;
    min-width: 0px;
    min-height: 0px;
}}
QPushButton#row_btn:hover {{ background-color: {HEADER_BG}; border-color: {ACCENT}; }}
QLineEdit, QComboBox, QSpinBox {{
    background-color: {PANEL_BG};
    color: {TEXT_MAIN};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 3px 6px;
}}
QTextEdit {{
    background-color: #0f0f1a;
    color: #a0ffb0;
    border: 1px solid {BORDER};
    border-radius: 4px;
    font-family: "Consolas", "Cascadia Code", "Fira Code", monospace;
    font-size: 12px;
    padding: 4px;
}}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background-color: {PANEL_BG};
    color: {TEXT_MAIN};
    selection-background-color: {ACCENT};
}}
QLabel {{ color: {TEXT_MAIN}; }}
QLabel#dim {{ color: {TEXT_DIM}; font-size: 11px; }}
QScrollBar:vertical {{
    background: {PANEL_BG};
    width: 12px;
    border-left: 1px solid {BORDER};
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 3px;
    min-height: 24px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: {PANEL_BG};
    height: 12px;
    border-top: 1px solid {BORDER};
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 3px;
    min-width: 24px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{ background: {ACCENT}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QMenu {{
    background-color: {PANEL_BG};
    border: 1px solid {BORDER};
    color: {TEXT_MAIN};
    border-radius: 5px;
    padding: 4px;
}}
QMenu::item {{ padding: 5px 20px; border-radius: 3px; }}
QMenu::item:selected {{ background-color: {ACCENT}; }}
QCheckBox {{ color: {TEXT_MAIN}; }}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background: {PANEL_BG};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}
QToolBar {{
    background-color: {PANEL_BG};
    border-bottom: 1px solid {BORDER};
    spacing: 6px;
    padding: 5px 10px;
}}
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:vertical {{ height: 3px; }}
"""


# ── Defragmenter-style progress strip ────────────────────────────────────────

class DefragStrip(QWidget):
    """
    One coloured block per file. States animate like a disk defragmenter.
    Hover shows filename + state tooltip.
    """

    BLOCK_W = 24
    BLOCK_H = 24
    GAP     = 3

    STATE_STYLES = {
        "idle":       (BLOCK_IDLE,       BORDER,    "Idle"),
        "extracting": (BLOCK_EXTRACTING, WARNING,   "Extracting"),
        "ready":      (BLOCK_READY,      SUCCESS,   "Ready"),
        "saving":     (BLOCK_SAVING,     ACCENT2,   "Saving"),
        "done":       (BLOCK_DONE,       SUCCESS,   "Done"),
        "error":      (BLOCK_ERROR,      ERROR,     "Error"),
        "repacking":  (BLOCK_REPACK,     "#5ab4e8", "Repacking"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: list[str] = []
        self._states: dict[str, str] = {}
        self._extra_tips: dict[str, str] = {}
        self._hover = -1
        self.setMouseTracking(True)
        self.setMinimumHeight(self.BLOCK_H + 10)
        self.setMaximumHeight(self.BLOCK_H + 10)

        # Spinner animation for "extracting" / "repacking"
        self._anim_frame = 0
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(120)

    def _tick(self):
        self._anim_frame = (self._anim_frame + 1) % 8
        if any(s in ("extracting", "repacking", "saving") for s in self._states.values()):
            self.update()

    def set_files(self, filenames: list[str]):
        self._files = filenames
        self._states = {f: "idle" for f in filenames}
        self._extra_tips = {}
        self.setMinimumWidth(
            len(filenames) * (self.BLOCK_W + self.GAP) + self.GAP + 6
        )
        self.update()

    def set_state(self, filename: str, state: str, tip: str = ""):
        if filename in self._states:
            self._states[filename] = state
            if tip:
                self._extra_tips[filename] = tip
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        x = self.GAP + 3
        y = (self.height() - self.BLOCK_H) // 2
        spinner_chars = "▖▘▝▗▚▞░▒"

        for i, fname in enumerate(self._files):
            state = self._states.get(fname, "idle")
            fill, border, _ = self.STATE_STYLES.get(state, self.STATE_STYLES["idle"])

            # Animate active blocks with a slightly pulsing border
            if state in ("extracting", "saving", "repacking"):
                alpha = 180 + int(60 * abs((self._anim_frame - 4) / 4))
                bc = QColor(border)
                bc.setAlpha(alpha)
                border_color = bc
            else:
                border_color = QColor(border)

            if i == self._hover:
                border_color = QColor(ACCENT2)

            painter.setBrush(QColor(fill))
            painter.setPen(QPen(border_color, 1.5))
            painter.drawRoundedRect(x, y, self.BLOCK_W, self.BLOCK_H, 4, 4)

            # Draw a tiny spinner char for active states
            if state in ("extracting", "saving", "repacking"):
                painter.setPen(QPen(QColor("#ffffff"), 1))
                f = painter.font()
                f.setPointSize(8)
                painter.setFont(f)
                ch = spinner_chars[self._anim_frame % len(spinner_chars)]
                painter.drawText(x, y, self.BLOCK_W, self.BLOCK_H,
                                 Qt.AlignCenter, ch)
            elif state == "done":
                painter.setPen(QPen(QColor("#ffffff"), 1))
                f = painter.font()
                f.setPointSize(8)
                painter.setFont(f)
                painter.drawText(x, y, self.BLOCK_W, self.BLOCK_H,
                                 Qt.AlignCenter, "✓")
            elif state == "error":
                painter.setPen(QPen(QColor("#ffffff"), 1))
                f = painter.font()
                f.setPointSize(8)
                painter.setFont(f)
                painter.drawText(x, y, self.BLOCK_W, self.BLOCK_H,
                                 Qt.AlignCenter, "✕")

            x += self.BLOCK_W + self.GAP
        painter.end()

    def mouseMoveEvent(self, event):
        idx = self._idx_at(event.position().x())
        if idx != self._hover:
            self._hover = idx
            self.update()
        if 0 <= idx < len(self._files):
            fname = self._files[idx]
            state = self._states.get(fname, "idle")
            _, _, state_label = self.STATE_STYLES.get(state, ("", "", state))
            tip = self._extra_tips.get(fname, "")
            full_tip = f"{fname}\nStatus: {state_label}"
            if tip and tip != fname:
                full_tip += f"\n{tip}"
            self.setToolTip(full_tip)

    def leaveEvent(self, event):
        self._hover = -1
        self.update()

    def _idx_at(self, x: float) -> int:
        step = self.BLOCK_W + self.GAP
        idx = int((x - self.GAP - 3) / step)
        return idx if 0 <= idx < len(self._files) else -1

    def legend_widget(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(2, 0, 0, 0)
        lay.setSpacing(8)
        for colour, label in [
            (BLOCK_IDLE,       "Idle"),
            (BLOCK_EXTRACTING, "Extracting"),
            (BLOCK_READY,      "Ready"),
            (BLOCK_SAVING,     "Saving"),
            (BLOCK_DONE,       "Done"),
            (BLOCK_REPACK,     "Repacking"),
            (BLOCK_ERROR,      "Error"),
        ]:
            dot = QLabel("■")
            dot.setStyleSheet(f"color: {colour}; font-size: 12px;")
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px;")
            lay.addWidget(dot)
            lay.addWidget(lbl)
        lay.addStretch()
        return w


# ── Console log ───────────────────────────────────────────────────────────────

class ConsoleLog(QTextEdit):
    """Green-on-black monospace log; also prints to stdout for external monitoring."""

    COLORS = {
        "info":    "#a0ffb0",
        "warn":    "#ffe080",
        "error":   "#ff8888",
        "dim":     "#557799",
        "success": "#80ffcc",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumHeight(180)
        self.setMinimumHeight(80)

    def log(self, msg: str, level: str = "info"):
        colour = self.COLORS.get(level, self.COLORS["info"])
        ts = time.strftime("%H:%M:%S")
        html = (
            f'<span style="color:#334455;">[{ts}]</span>&nbsp;'
            f'<span style="color:{colour};">{msg}</span>'
        )
        self.append(html)
        self.moveCursor(QTextCursor.End)
        # Mirror to terminal
        print(f"[{ts}] {msg}", flush=True)


# ── Row action buttons ────────────────────────────────────────────────────────

_DEFAULT_ACTION_ICONS = {"update": "update", "mirror": "mirror", "auto": "auto", "clear": "clear"}

def _resolve_action_icon_font(preferred: str | None = None) -> str:
    families = set(QFontDatabase().families())
    candidates = (
        preferred,
        "Segoe UI Emoji",
        "Apple Color Emoji",
        "Noto Color Emoji",
        "Noto Emoji",
        "Twemoji Mozilla",
        "Segoe UI Symbol",
        "Arial Unicode MS",
    )
    for candidate in candidates:
        if candidate and candidate in families:
            return candidate
    return QFont().family()


def _normalize_action_icons(icons: dict[str, str] | None = None) -> dict[str, str]:
    merged = dict(_DEFAULT_ACTION_ICONS)
    merged.update({k: v for k, v in (icons or {}).items() if v})
    return merged

class RowActionWidget(QWidget):
    update_clicked = Signal(int)
    mirror_clicked = Signal(int)
    auto_clicked   = Signal(int)
    clear_clicked  = Signal(int)

    def __init__(self, row: int, icons: dict[str, str] | None = None, icon_font: str = "Noto Color Emoji", parent=None):
        super().__init__(parent)
        self._row = row
        icon_map = _normalize_action_icons(icons)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(6)

        self.btn_u = QPushButton(icon_map.get("update", "update"))
        self.btn_m = QPushButton(icon_map.get("mirror", "mirror"))
        self.btn_a = QPushButton(icon_map.get("auto", "auto"))
        self.btn_c = QPushButton(icon_map.get("clear", "clear"))

        for btn in (self.btn_u, self.btn_m, self.btn_a, self.btn_c):
            btn.setObjectName("row_btn")
            btn.setFixedHeight(26)
            btn.setMinimumWidth(68)
            btn.setFont(QFont(_resolve_action_icon_font(icon_font), 11))

        self.btn_u.setToolTip("Update — flash to confirm first-column value")
        self.btn_m.setToolTip("Mirror — copy col 1 value to ALL other columns")
        self.btn_a.setToolTip("Auto — fill columns with incrementing numbers")
        self.btn_c.setToolTip("Clear — wipe every cell on this row")

        self.btn_u.clicked.connect(lambda: self.update_clicked.emit(self._row))
        self.btn_m.clicked.connect(lambda: self.mirror_clicked.emit(self._row))
        self.btn_a.clicked.connect(lambda: self.auto_clicked.emit(self._row))
        self.btn_c.clicked.connect(lambda: self.clear_clicked.emit(self._row))

        lay.addWidget(self.btn_u)
        lay.addWidget(self.btn_m)
        lay.addWidget(self.btn_a)
        lay.addWidget(self.btn_c)


# ── Auto-increment dialog ─────────────────────────────────────────────────────

class AutoIncrementDialog(QDialog):
    def __init__(self, field_label: str, seed: int = 1, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Auto-number: {field_label}")
        self.setFixedWidth(280)
        layout = QFormLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 9999)
        self.start_spin.setValue(seed)

        self.step_spin = QSpinBox()
        self.step_spin.setRange(1, 100)
        self.step_spin.setValue(1)

        layout.addRow("Start value:", self.start_spin)
        layout.addRow("Step:", self.step_spin)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    @property
    def start(self): return self.start_spin.value()
    @property
    def step(self):  return self.step_spin.value()


# ── Spreadsheet table ─────────────────────────────────────────────────────────

LABEL_COL      = 0
ACTION_COL     = 1
FIRST_FILE_COL = 2


class MetadataTable(QTableWidget):
    log_message = Signal(str, str)   # message, level
    DEFAULT_ACTION_ICONS = dict(_DEFAULT_ACTION_ICONS)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.setAlternatingRowColors(False)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked
        )
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(True)
        self.setWordWrap(False)
        # Always-visible scrollbars
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        self._row_map: list[str | None] = []
        self._section_rows: set[int] = set()
        self._files: list[Path] = []
        self._section_start: dict[str, int] = {}
        self._action_icons = dict(self.DEFAULT_ACTION_ICONS)
        self._action_icon_font = _resolve_action_icon_font("Noto Color Emoji")

    # ── Build rows ────────────────────────────────────────────────────────────

    def setup_rows(self):
        rows: list[str | None] = []
        seen: set[str] = set()
        for tag, section, label, ftype in FIELDS:
            if section not in seen:
                seen.add(section)
                rows.append(None)
            rows.append(tag)

        self._row_map = rows
        self.setRowCount(len(rows))
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels(["General Information", "Operations"])

        current_section = ""
        for i, tag in enumerate(self._row_map):
            if tag is None:
                # Look ahead for section name
                for j in range(i + 1, len(self._row_map)):
                    if self._row_map[j] is not None:
                        current_section = next(
                            s for t, s, l, ft in FIELDS if t == self._row_map[j]
                        )
                        break
                self._section_start[current_section] = i
                self._section_rows.add(i)

                item = QTableWidgetItem(f"  ▼  {current_section}")
                item.setFlags(Qt.ItemIsEnabled)
                item.setBackground(QBrush(QColor(SECTION_BG)))
                item.setForeground(QBrush(QColor(TEXT_SECTION)))
                f = item.font(); f.setBold(True); f.setPointSize(10)
                item.setFont(f)
                self.setItem(i, LABEL_COL, item)
                # Blank action cell for section headers
                blank = QTableWidgetItem("")
                blank.setFlags(Qt.ItemIsEnabled)
                blank.setBackground(QBrush(QColor(SECTION_BG)))
                self.setItem(i, ACTION_COL, blank)
                self.setRowHeight(i, 32)
            else:
                label = next(l for t, s, l, ft in FIELDS if t == tag)
                litem = QTableWidgetItem(f"  {label}")
                litem.setFlags(Qt.ItemIsEnabled)
                litem.setBackground(QBrush(QColor(PANEL_BG)))
                litem.setForeground(QBrush(QColor(TEXT_MAIN)))
                self.setItem(i, LABEL_COL, litem)

                aw = RowActionWidget(i, icons=self._action_icons, icon_font=self._action_icon_font)
                aw.update_clicked.connect(self._on_update)
                aw.mirror_clicked.connect(self._on_mirror)
                aw.auto_clicked.connect(self._on_auto)
                aw.clear_clicked.connect(self._on_clear)
                self.setCellWidget(i, ACTION_COL, aw)
                self.setRowHeight(i, 32)

        self.setColumnWidth(LABEL_COL, 170)
        self.setColumnWidth(ACTION_COL, 340)
        self.horizontalHeader().setSectionResizeMode(LABEL_COL,  QHeaderView.Fixed)
        self.horizontalHeader().setSectionResizeMode(ACTION_COL, QHeaderView.Fixed)

    def set_action_icons(self, icons: dict[str, str], icon_font: str = "Noto Color Emoji") -> None:
        self._action_icons = _normalize_action_icons(icons)
        self._action_icon_font = _resolve_action_icon_font(icon_font)
        for row, tag in enumerate(self._row_map):
            if tag is None or row in self._section_rows:
                continue
            widget = self.cellWidget(row, ACTION_COL)
            if isinstance(widget, RowActionWidget):
                widget.btn_u.setText(self._action_icons["update"])
                widget.btn_m.setText(self._action_icons["mirror"])
                widget.btn_a.setText(self._action_icons["auto"])
                widget.btn_c.setText(self._action_icons["clear"])
                for btn in (widget.btn_u, widget.btn_m, widget.btn_a, widget.btn_c):
                    btn.setFont(QFont(_resolve_action_icon_font(self._action_icon_font), 11))

    # ── Column management ─────────────────────────────────────────────────────

    def add_file_column(self, archive: Path, metadata: dict,
                        page_count: int, is_loading: bool = False) -> int:
        col = len(self._files) + FIRST_FILE_COL
        self._files.append(archive)
        self.setColumnCount(col + 1)
        hdr = QTableWidgetItem(archive.name)
        hdr.setToolTip(str(archive))
        self.setHorizontalHeaderItem(col, hdr)
        self.horizontalHeader().setSectionResizeMode(col, QHeaderView.Interactive)
        self.setColumnWidth(col, 200)

        if is_loading:
            for i, tag in enumerate(self._row_map):
                bg = QColor(SECTION_BG if i in self._section_rows
                            else (CELL_ALT_BG if col % 2 == 0 else CELL_BG))
                item = QTableWidgetItem("" if i in self._section_rows else "…")
                item.setFlags(Qt.ItemIsEnabled)
                item.setBackground(QBrush(bg))
                item.setForeground(QBrush(QColor(TEXT_DIM)))
                self.setItem(i, col, item)
        else:
            self._populate_column(col, archive, metadata, page_count)
        return col

    def _populate_column(self, col: int, archive: Path, metadata: dict, page_count: int):
        for i, tag in enumerate(self._row_map):
            if i in self._section_rows:
                sec = QTableWidgetItem("")
                sec.setFlags(Qt.ItemIsEnabled)
                sec.setBackground(QBrush(QColor(SECTION_BG)))
                self.setItem(i, col, sec)
                continue
            if tag is None:
                continue

            ftype = next(ft for t, s, l, ft in FIELDS if t == tag)
            val   = metadata.get(tag, "")

            if tag == "Title" and not val:
                val = archive.stem
            if tag == "PageCount" and not val and page_count:
                val = str(page_count)

            bg = QColor(CELL_ALT_BG if col % 2 == 0 else CELL_BG)

            if ftype in ("bool", "dropdown"):
                options = DROPDOWN_OPTIONS.get(tag, ["", "Yes", "No"])
                widget = QComboBox()
                widget.addItems(options)
                if val and val not in options:
                    widget.addItem(val)
                widget.setCurrentText(val)
                self.setCellWidget(i, col, widget)
            else:
                item = QTableWidgetItem(val)
                item.setBackground(QBrush(bg))
                item.setForeground(QBrush(QColor(TEXT_MAIN)))
                self.setItem(i, col, item)

    def update_column(self, col: int, archive: Path, metadata: dict, page_count: int):
        self._populate_column(col, archive, metadata, page_count)

    # ── Value helpers ─────────────────────────────────────────────────────────

    def get_value(self, row: int, col: int) -> str:
        w = self.cellWidget(row, col)
        if isinstance(w, QComboBox):
            return w.currentText()
        item = self.item(row, col)
        return item.text() if item else ""

    def set_value(self, row: int, col: int, value: str):
        w = self.cellWidget(row, col)
        if isinstance(w, QComboBox):
            idx = w.findText(value)
            w.setCurrentIndex(idx if idx >= 0 else 0)
            return
        item = self.item(row, col)
        if item:
            item.setText(value)
        else:
            self.setItem(row, col, QTableWidgetItem(value))

    def get_all_metadata(self, col: int) -> dict:
        data = empty_metadata()
        for i, tag in enumerate(self._row_map):
            if tag and i not in self._section_rows:
                data[tag] = self.get_value(i, col)
        return data

    # ── Row actions ───────────────────────────────────────────────────────────

    def _label_for_row(self, row: int) -> str:
        tag = self._row_map[row] if row < len(self._row_map) else None
        return next((l for t, s, l, ft in FIELDS if t == tag), tag or "?") if tag else "?"

    def _on_update(self, row: int):
        if self.columnCount() <= FIRST_FILE_COL:
            return
        item = self.item(row, FIRST_FILE_COL)
        if item:
            orig = item.background()
            item.setBackground(QBrush(QColor(ACCENT)))
            QTimer.singleShot(350, lambda i=item, o=orig: i.setBackground(o))
        self.log_message.emit(f"♻  Updated: '{self._label_for_row(row)}'", "dim")

    def _on_mirror(self, row: int):
        if self.columnCount() <= FIRST_FILE_COL:
            return
        val = self.get_value(row, FIRST_FILE_COL)
        count = self.columnCount() - FIRST_FILE_COL - 1
        for c in range(FIRST_FILE_COL + 1, self.columnCount()):
            self.set_value(row, c, val)
        self.log_message.emit(
            f"🔍  Mirror '{self._label_for_row(row)}': "
            f"'{val}'  →  {count} column(s)",
            "info"
        )

    def _on_auto(self, row: int):
        if self.columnCount() <= FIRST_FILE_COL:
            return
        label = self._label_for_row(row)
        raw = self.get_value(row, FIRST_FILE_COL)
        try:
            seed = int(raw)
        except (ValueError, TypeError):
            seed = 1

        dlg = AutoIncrementDialog(label, seed=seed, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        val, step = dlg.start, dlg.step
        for c in range(FIRST_FILE_COL, self.columnCount()):
            self.set_value(row, c, str(val))
            val += step

        self.log_message.emit(
            f"🧮  Auto '{label}': {dlg.start} → … step={step}  "
            f"({self.columnCount() - FIRST_FILE_COL} columns filled)",
            "success"
        )

    # ── Context menu ──────────────────────────────────────────────────────────

    def _on_clear(self, row: int):
        for c in range(FIRST_FILE_COL, self.columnCount()):
            self.set_value(row, c, "")
        self.log_message.emit(f"🧹  Cleared row '{self._label_for_row(row)}'", "dim")

    def _context_menu(self, pos):
        col = self.columnAt(pos.x())
        row = self.currentRow()
        if col < FIRST_FILE_COL or row < 0:
            return
        tag = self._row_map[row] if row < len(self._row_map) else None
        if not tag:
            return

        menu = QMenu(self)
        val = self.get_value(row, col)
        label = self._label_for_row(row)

        if tag in AUTO_INCREMENT_FIELDS:
            menu.addAction(f"🧮 Auto-number '{label}'…").triggered.connect(
                lambda: self._on_auto(row))
            menu.addSeparator()

        menu.addAction("🔍 Mirror col 1 → all").triggered.connect(
            lambda: self._on_mirror(row))
        menu.addAction("Fill right from here →").triggered.connect(
            lambda v=val, r=row, c=col: [
                self.set_value(r, cc, v)
                for cc in range(c, self.columnCount())
            ])
        menu.addAction("Fill all columns").triggered.connect(
            lambda v=val, r=row: [
                self.set_value(r, cc, v)
                for cc in range(FIRST_FILE_COL, self.columnCount())
            ])
        menu.addSeparator()
        menu.addAction("Clear cell").triggered.connect(
            lambda r=row, c=col: self.set_value(r, c, ""))
        menu.addAction("Clear entire row").triggered.connect(
            lambda r=row: [
                self.set_value(r, cc, "")
                for cc in range(FIRST_FILE_COL, self.columnCount())
            ])
        menu.exec(self.viewport().mapToGlobal(pos))

    # ── Keyboard ──────────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_V and event.modifiers() == Qt.ControlModifier:
            self._paste()
        else:
            super().keyPressEvent(event)

    def _paste(self):
        text = QApplication.clipboard().text()
        if not text:
            return
        rows_data = [r.split("\t") for r in text.splitlines()]
        sel = self.selectedRanges()
        if not sel:
            return
        sr = sel[0].topRow()
        sc = max(sel[0].leftColumn(), FIRST_FILE_COL)
        for dr, row_vals in enumerate(rows_data):
            r = sr + dr
            if r >= self.rowCount() or r in self._section_rows:
                continue
            for dc, cv in enumerate(row_vals):
                c = sc + dc
                if c >= self.columnCount():
                    break
                self.set_value(r, c, cv.strip())


# ── Main Window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    log_emitted = Signal(str, str)

    def __init__(self, *, show_console: bool = True):
        super().__init__()
        self.setWindowTitle("Comic Bulk Metadata Editor")
        self.resize(1380, 880)

        self._source_folder: Path | None = None
        self._archive_files: list[Path] = []
        self._extract_dirs:  dict[str, Path] = {}
        self._metadata:      dict[str, dict] = {}
        self._page_counts:   dict[str, int]  = {}
        self._workers:       list            = []
        self._extraction_done:   set[str] = set()
        self._extraction_failed: set[str] = set()
        self._saved = False
        self._col_map: dict[str, int] = {}

        self._show_console = show_console
        self._build_ui()

    def _build_ui(self):
        # Toolbar
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        self.btn_open = QPushButton("📂  Open Folder")
        self.btn_open.setObjectName("secondary")
        self.btn_open.clicked.connect(self._open_folder)
        tb.addWidget(self.btn_open)
        tb.addSeparator()

        self.chk_recursive = QCheckBox("Include subfolders")
        tb.addWidget(self.chk_recursive)
        tb.addSeparator()

        self.lbl_path = QLabel("")
        self.lbl_path.setObjectName("dim")
        self.lbl_path.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.lbl_path.setAlignment(Qt.AlignCenter)
        tb.addWidget(self.lbl_path)

        self.btn_save = QPushButton("💾  Save")
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._save)
        tb.addWidget(self.btn_save)

        self.btn_repackage = QPushButton("📦  Repackage")
        self.btn_repackage.setEnabled(False)
        self.btn_repackage.clicked.connect(self._repackage)
        tb.addWidget(self.btn_repackage)

        # Central
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(5)

        # Defrag strip + legend
        self.defrag = DefragStrip()
        outer.addWidget(self.defrag)
        outer.addWidget(self.defrag.legend_widget())

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {BORDER};")
        outer.addWidget(sep)

        # Splitter: table / console
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(4)
        outer.addWidget(splitter, stretch=1)

        self.table = MetadataTable()
        self.table.setup_rows()
        self.table.log_message.connect(self._log)
        splitter.addWidget(self.table)

        self.console = None
        if self._show_console:
            log_frame = QWidget()
            log_lay = QVBoxLayout(log_frame)
            log_lay.setContentsMargins(0, 2, 0, 0)
            log_lay.setSpacing(1)
            log_hdr = QLabel("Console  (also visible in terminal)")
            log_hdr.setObjectName("dim")
            log_lay.addWidget(log_hdr)
            self.console = ConsoleLog()
            log_lay.addWidget(self.console)
            splitter.addWidget(log_frame)
            splitter.setSizes([660, 160])
        else:
            splitter.setSizes([820])
        splitter.setStretchFactor(0, 1)
        if self._show_console:
            splitter.setStretchFactor(1, 0)

        self._log("Ready. Open a folder containing comic archives to begin.", "dim")

    def _log(self, msg: str, level: str = "info"):
        if self.console is not None:
            self.console.log(msg, level)
        self.log_emitted.emit(msg, level)

    # ── Folder open ───────────────────────────────────────────────────────────

    def _open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Comic Folder")
        if not folder:
            return

        self._source_folder = Path(folder)
        files = scan_folder(self._source_folder, self.chk_recursive.isChecked())

        if not files:
            QMessageBox.information(
                self, "No Files",
                f"No comic files found.\nSupported: {', '.join(SUPPORTED_EXTENSIONS)}"
            )
            return

        # Reset state
        self._archive_files = files
        self._extraction_done.clear()
        self._extraction_failed.clear()
        self._metadata.clear()
        self._page_counts.clear()
        self._col_map.clear()
        self._saved = False
        self.btn_save.setEnabled(False)
        self.btn_repackage.setEnabled(False)

        self.table.setColumnCount(FIRST_FILE_COL)
        self.table._files.clear()

        self.defrag.set_files([a.name for a in files])

        self._log(f"Folder: {self._source_folder}", "info")
        self.lbl_path.setText(str(self._source_folder))
        self._log(f"Found {len(files)} file(s). Extracting first file now…", "info")

        for archive in files:
            col = self.table.add_file_column(archive, empty_metadata(), 0, is_loading=True)
            self._col_map[archive.name] = col

        self._extract_file(files[0], on_done_start_rest=True)

    # ── Extraction ────────────────────────────────────────────────────────────

    def _extract_file(self, archive: Path, on_done_start_rest: bool = False):
        extract_dir = get_extract_dir(self._source_folder, archive)
        self._extract_dirs[archive.name] = extract_dir
        self.defrag.set_state(archive.name, "extracting")

        from studio.metadata_archive import _is_our_extract
        if extract_dir.exists() and _is_our_extract(extract_dir, archive):
            self._log(f"  ↳ Cached: {archive.name}", "dim")
            self._on_file_extracted(archive, extract_dir, True, "", on_done_start_rest)
            return

        self._log(f"Extracting: {archive.name}", "dim")
        worker = ExtractionWorker(archive, extract_dir)
        worker.finished.connect(
            lambda ok, err, a=archive, ed=extract_dir, r=on_done_start_rest:
                self._on_file_extracted(a, ed, ok, err, r)
        )
        self._workers.append(worker)
        worker.start()

    def _on_file_extracted(self, archive: Path, extract_dir: Path,
                           success: bool, error: str, start_rest: bool):
        if not success:
            self._extraction_failed.add(archive.name)
            self.defrag.set_state(archive.name, "error", f"Error: {error}")
            self._log(f"⚠  Failed: {archive.name}  — {error}", "error")
        else:
            meta = load_or_init_comicinfo(extract_dir)
            if not meta.get("Title"):
                meta["Title"] = archive.stem
            pc = count_pages(extract_dir)
            self._metadata[archive.name] = meta
            self._page_counts[archive.name] = pc
            self._extraction_done.add(archive.name)

            col = self._col_map.get(archive.name, -1)
            if col >= FIRST_FILE_COL:
                self.table.update_column(col, archive, meta, pc)

            self.defrag.set_state(archive.name, "ready",
                                  f"{archive.name}  ({pc} pages)")
            self._log(
                f"✓ Ready: {archive.name}  "
                f"({pc} pages, title='{meta.get('Title','')}' )",
                "success"
            )

        if start_rest:
            for a in self._archive_files[1:]:
                self._extract_file(a)

        self._check_all_extracted()

    def _check_all_extracted(self):
        done   = len(self._extraction_done)
        failed = len(self._extraction_failed)
        if done + failed == len(self._archive_files):
            self._log(
                f"Extraction complete — {done} OK, {failed} failed.",
                "info" if not failed else "warn"
            )
            if done > 0:
                self.btn_save.setEnabled(True)

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self):
        if not self._source_folder:
            return

        finished_dir = self._source_folder / "finished"
        finished_dir.mkdir(exist_ok=True)

        saved = 0
        all_meta: dict[str, dict] = {}

        for archive in self._archive_files:
            if archive.name not in self._extraction_done:
                continue
            col = self._col_map.get(archive.name, -1)
            if col < FIRST_FILE_COL:
                continue

            self.defrag.set_state(archive.name, "saving")
            meta = self.table.get_all_metadata(col)

            if not meta.get("Title"):
                meta["Title"] = archive.stem
            if not meta.get("PageCount"):
                pc = self._page_counts.get(archive.name, 0)
                if pc:
                    meta["PageCount"] = str(pc)

            self._metadata[archive.name] = meta

            extract_dir = self._extract_dirs.get(archive.name)
            if extract_dir and extract_dir.exists():
                write_comicinfo(extract_dir / "ComicInfo.xml", meta)

            all_meta[archive.name] = meta
            saved += 1

        # CSV summary
        csv_path = self._source_folder / "ComicInfo.csv"
        try:
            generate_csv_report(all_meta, csv_path)
            self._log(f"CSV → {csv_path.name}", "dim")
        except Exception as e:
            self._log(f"CSV error: {e}", "error")

        # Sidecars → finished/
        for archive in self._archive_files:
            if archive.name not in self._extraction_done:
                continue
            ed = self._extract_dirs.get(archive.name)
            meta = self._metadata.get(archive.name, {})
            if ed:
                try:
                    generate_cover(ed, archive, output_dir=finished_dir)
                    generate_metadata_json(meta, archive, output_dir=finished_dir)
                    self._log(f"  Sidecars → finished/{archive.stem}.*", "dim")
                except Exception as e:
                    self._log(f"Sidecar error {archive.name}: {e}", "error")

        for archive in self._archive_files:
            if archive.name in self._extraction_done:
                self.defrag.set_state(archive.name, "done")

        self._saved = True
        self.btn_repackage.setEnabled(True)
        self._log(
            f"✓  SAVED  {saved} file(s).  "
            f"Sidecars + CSV → finished/  |  ComicInfo.xml updated in temp dirs.",
            "success"
        )

    # ── Repackage ─────────────────────────────────────────────────────────────

    def _repackage(self):
        if not self._saved:
            QMessageBox.warning(self, "Save First",
                                "Please save before repackaging.")
            return

        finished_dir = self._source_folder / "finished"
        cbr_count = sum(
            1 for a in self._archive_files
            if a.suffix.lower() == ".cbr" and a.name in self._extraction_done
        )
        notice = (
            f"\n⚠ {cbr_count} .cbr file(s) will be saved as .cbz "
            "(RAR creation requires a commercial license)."
        ) if cbr_count else ""

        reply = QMessageBox.question(
            self, "Repackage",
            f"Repackage {len(self._extraction_done)} archive(s)?\n"
            f"Output → {finished_dir}{notice}",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        finished_dir.mkdir(exist_ok=True)
        tasks = []
        for archive in self._archive_files:
            if archive.name not in self._extraction_done:
                continue
            ed = self._extract_dirs.get(archive.name)
            if not ed:
                continue
            # Same filename inside finished/ — clean, no _edited suffix
            output_path = finished_dir / archive.name
            tasks.append((ed, archive, output_path))

        if not tasks:
            return

        self.btn_repackage.setEnabled(False)
        self.btn_save.setEnabled(False)

        for archive in self._archive_files:
            if archive.name in self._extraction_done:
                self.defrag.set_state(archive.name, "repacking")

        self._log(f"Repacking {len(tasks)} archive(s) → {finished_dir}", "info")

        worker = RepackageWorker(tasks)
        worker.file_progress.connect(
            lambda fn, f: self.defrag.set_state(fn, "repacking",
                                                f"{fn}: {int(f*100)}%")
        )
        worker.file_done.connect(self._on_repack_file_done)
        worker.all_done.connect(self._on_repack_all_done)
        self._workers.append(worker)
        worker.start()

    def _on_repack_file_done(self, filename: str, success: bool, error: str):
        if success:
            self.defrag.set_state(filename, "done", f"Repacked: {filename}")
            self._log(f"  ✓ Repacked: {filename}", "success")
        else:
            self.defrag.set_state(filename, "error", f"Error: {error}")
            self._log(f"  ⚠ Repack failed: {filename} — {error}", "error")

    def _on_repack_all_done(self):
        self.btn_save.setEnabled(True)
        self.btn_repackage.setEnabled(True)
        finished = self._source_folder / "finished"
        self._log(f"✓  REPACKAGE COMPLETE  →  {finished}", "success")
        QMessageBox.information(self, "Done",
            f"All archives repackaged.\nOutput folder: {finished}")

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        for w in self._workers:
            if w.isRunning():
                w.terminate()
                w.wait(2000)
        if self._source_folder:
            tmp = get_temp_dir(self._source_folder)
            if tmp.exists():
                r = QMessageBox.question(
                    self, "Clean Up",
                    f"Delete temporary extraction folder?\n{tmp}",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if r == QMessageBox.Yes:
                    import shutil
                    shutil.rmtree(tmp, ignore_errors=True)
                    self._log("Temp folder deleted.", "dim")
        event.accept()
