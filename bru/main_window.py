"""
bru.main_window
===============
MainWindow — the top-level PySide6 window.

Responsibilities
----------------
* Build and own all UI widgets.
* Collect the params dict from every control widget.
* Drive the RenameEngine preview (debounced via QTimer).
* Execute the actual rename operation via os.rename.
* Delegate undo/redo to HistoryManager.
* Delegate preset I/O to PresetManager.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    Qt, QTimer,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox,
    QDialog, QDoubleSpinBox, QFileDialog, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSpinBox, QSplitter, QStatusBar, QTabWidget, QTextEdit,
    QVBoxLayout, QWidget,
)
from PySide6.QtGui import QCloseEvent

from bru.engine   import RenameEngine
from bru.history  import HistoryEntry, HistoryManager
from bru.metadata import MetadataExtractor
from bru.presets  import PresetManager
from bru.theme    import (
    COLORS, THEMES_DIR, apply_theme, load_cosmic_ron_palette,
)
from bru.widgets  import (
    COL_NEW, COL_ORIG, COL_STATUS,
    FileTable, HistoryPanel, PresetDialog, RegExLineEdit, SectionLabel,
)
from bru.comiceditor.ui import MainWindow as MetadataEditorMainWindow


class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self) -> None:
        super().__init__()
        # ── Core services ──────────────────────────────────────────── #
        self.engine    = RenameEngine()
        self.extractor = MetadataExtractor()
        self.presets   = PresetManager()
        self.history   = HistoryManager()

        self._current_dir: str              = str(Path.home())
        self._settings_path = Path(__file__).resolve().parent.parent / "settings.json"
        self._meta_cache: dict[str, dict]   = {}
        self._theme_choices: dict[str, str] = {}

        # Debounce: fire preview 150 ms after the last control change
        self._preview_timer = QTimer(singleShot=True, interval=150)
        self._preview_timer.timeout.connect(self._run_preview)

        self.setWindowTitle("Bulk Rename Utility  v3")
        self.resize(1920, 826)

        self._build_ui()
        self._load_settings()
        self._load_directory(self._current_dir)
    def _set_theme(self, mode: str) -> None:
        app = QApplication.instance()
        if app is None:
            return

        if not mode.startswith("ron:"):
            mode = next(iter(self._theme_choices.values()), "")

        if mode.startswith("ron:"):
            ron_path = mode.removeprefix("ron:")
            try:
                apply_theme(app, load_cosmic_ron_palette(ron_path))
                self._status.showMessage(f"Theme loaded from {Path(ron_path).name}.", 2500)
            except Exception as exc:
                self._status.showMessage(f"Failed to load theme: {exc}", 4000)

        self._metadata_window.setStyleSheet(app.styleSheet())
        self._save_settings()

    # ══════════════════════════════════════════════════════════════════ #
    #  UI BUILD
    # ══════════════════════════════════════════════════════════════════ #

    def _build_ui(self) -> None:
        c = COLORS
        root_w = QWidget(); self.setCentralWidget(root_w)
        root = QVBoxLayout(root_w)
        root.setContentsMargins(8, 4, 8, 6)
        root.setSpacing(5)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_rename_tab(), "Rename")
        self._tabs.addTab(self._build_metadata_tab(), "Metadata")
        self._tabs.addTab(self._build_history_tab(), "History")
        self._tabs.addTab(self._build_settings_tab(), "Settings")
        root.addWidget(self._tabs, stretch=1)

        self._status = QStatusBar()
        self._progress = QProgressBar()
        self._progress.setFixedWidth(200)
        self._progress.setVisible(False)
        self._status.addPermanentWidget(self._progress)
        self.setStatusBar(self._status)
        self._status.showMessage("Ready — select a folder to begin.")

    def _build_rename_tab(self) -> QWidget:
        tab = QWidget()
        v = QVBoxLayout(tab)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(5)
        v.addWidget(self._build_path_bar())

        hsplit = QSplitter(Qt.Horizontal)
        hsplit.setHandleWidth(5)
        hsplit.addWidget(self._build_controls_pane())
        hsplit.addWidget(self._build_table_pane())
        hsplit.setSizes([500, 1400])
        v.addWidget(hsplit, stretch=1)
        v.addWidget(self._build_action_bar())
        return tab

    def _build_metadata_tab(self) -> QWidget:
        tab = QWidget()
        v = QVBoxLayout(tab)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self._metadata_window = MetadataEditorMainWindow(show_console=False)
        self._metadata_window.setWindowFlags(Qt.Widget)
        self._metadata_window.setParent(tab)
        self._metadata_window.log_emitted.connect(self._append_console)
        v.addWidget(self._metadata_window)
        return tab

    def _build_history_tab(self) -> QWidget:
        tab = QWidget()
        v = QVBoxLayout(tab); v.setContentsMargins(0, 0, 0, 0)
        self._history_panel = HistoryPanel()
        self._history_panel.undo_requested.connect(self._do_undo)
        split = QSplitter(Qt.Vertical)
        split.addWidget(self._history_panel)
        self._history_console = QTextEdit()
        self._history_console.setReadOnly(True)
        self._history_console.setMinimumHeight(120)
        split.addWidget(self._history_console)
        split.setSizes([500, 220])
        v.addWidget(split)
        return tab

    def _build_settings_tab(self) -> QWidget:
        tab = QWidget()
        g = QGridLayout(tab)
        g.addWidget(QLabel("Theme"), 0, 0)
        self._theme_combo = QComboBox()
        self._refresh_theme_choices()
        self._theme_combo.addItems(list(self._theme_choices.keys()))
        self._theme_combo.currentTextChanged.connect(self._on_theme_combo_changed)
        g.addWidget(self._theme_combo, 0, 1)
        g.addWidget(QLabel("Default Path"), 1, 0)
        self._settings_path_edit = QLineEdit()
        self._settings_path_edit.editingFinished.connect(self._save_settings)
        g.addWidget(self._settings_path_edit, 1, 1)
        self._always_on_top = QCheckBox("Always on top")
        self._always_on_top.toggled.connect(self._on_always_on_top_toggled)
        g.addWidget(self._always_on_top, 2, 0, 1, 2)
        g.setColumnStretch(1, 1)
        return tab

    def _append_console(self, msg: str, _level: str = "info") -> None:
        self._history_console.append(msg)

    def _on_theme_combo_changed(self, label: str) -> None:
        self._set_theme(self._theme_choices.get(label, ""))

    def _refresh_theme_choices(self) -> None:
        self._theme_choices = {}
        if THEMES_DIR.exists():
            for ron_file in sorted(THEMES_DIR.glob("**/*.ron")):
                label = f"COSMIC • {ron_file.stem}"
                self._theme_choices[label] = f"ron:{ron_file.as_posix()}"

    def _load_settings(self) -> None:
        default_downloads = str(Path.home() / "Downloads")
        default_theme = next(iter(self._theme_choices.values()), "")
        settings = {
            "theme": default_theme,
            "default_path": default_downloads,
            "last_directory": default_downloads,
            "always_on_top": False,
            "window": {"x": 100, "y": 100, "w": 1920, "h": 826},
        }
        if self._settings_path.exists():
            try:
                settings.update(json.loads(self._settings_path.read_text(encoding="utf-8")))
            except Exception:
                pass
        self._settings_path_edit.setText(settings.get("default_path", default_downloads))
        self._current_dir = settings.get("last_directory") or settings.get("default_path", default_downloads)
        always_on_top = bool(settings.get("always_on_top", False))
        self._always_on_top.blockSignals(True)
        self._always_on_top.setChecked(always_on_top)
        self._always_on_top.blockSignals(False)
        self._apply_always_on_top(always_on_top)
        window = settings.get("window", {})
        self.setGeometry(
            int(window.get("x", 100)),
            int(window.get("y", 100)),
            int(window.get("w", 1920)),
            int(window.get("h", 826)),
        )
        selected_theme = settings.get("theme", default_theme)
        reverse = {value: key for key, value in self._theme_choices.items()}
        self._theme_combo.setCurrentText(reverse.get(selected_theme, next(iter(self._theme_choices.keys()), "")))
        self._set_theme(selected_theme)

    def _save_settings(self) -> None:
        g = self.geometry()
        data = {"theme": self._theme_choices.get(self._theme_combo.currentText(), next(iter(self._theme_choices.values()), "")),
                "default_path": self._settings_path_edit.text().strip() or str(Path.home() / "Downloads"),
                "last_directory": self._current_dir,
                "always_on_top": self._always_on_top.isChecked(),
                "window": {"x": g.x(), "y": g.y(), "w": g.width(), "h": g.height()}}
        self._settings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _on_always_on_top_toggled(self, checked: bool) -> None:
        self._apply_always_on_top(checked)
        self._save_settings()

    def _apply_always_on_top(self, enabled: bool) -> None:
        self.setWindowFlag(Qt.WindowStaysOnTopHint, enabled)
        self.show()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_settings()
        super().closeEvent(event)

    # ── Path bar ──────────────────────────────────────────────────────── #

    def _build_path_bar(self) -> QWidget:
        w = QWidget(); h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0); h.setSpacing(6)
        h.addWidget(QLabel("📂"))
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Directory path…")
        self._path_edit.returnPressed.connect(self._navigate_path_bar)
        h.addWidget(self._path_edit, stretch=1)
        for lbl, w_, slot in [
            ("Go",      44, self._navigate_path_bar),
            ("↑ Up",    56, self._go_up),
            ("Browse…", 80, self._browse_folder),
        ]:
            b = QPushButton(lbl); b.setFixedWidth(w_); b.clicked.connect(slot)
            h.addWidget(b)
        return w

    # ── Table pane ────────────────────────────────────────────────────── #

    def _build_table_pane(self) -> QWidget:
        w = QWidget(); v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(4)

        self._file_table = FileTable()

        # Mini toolbar
        tb = QWidget(); th = QHBoxLayout(tb)
        th.setContentsMargins(0, 0, 0, 0); th.setSpacing(4)
        th.addWidget(SectionLabel("Files"))
        th.addStretch()
        self._count_label = QLabel("")
        self._count_label.setStyleSheet(
            f"color:{COLORS['MUT']};font-size:11px;"
        )
        th.addWidget(self._count_label)
        v.addWidget(tb)

        self._file_table.rows_reordered.connect(self._schedule_preview)
        self._file_table.selection_toggled.connect(self._schedule_preview)
        v.addWidget(self._file_table)
        return w

    # ── Controls pane ─────────────────────────────────────────────────── #

    def _build_controls_pane(self) -> QWidget:
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        container = QWidget()
        g = QGridLayout(container)
        g.setContentsMargins(4, 4, 4, 4); g.setSpacing(5)
        groups = [
            self._grp_regex(),
            self._grp_name(),
            self._grp_replace(),
            self._grp_case(),
            self._grp_remove(),
            self._grp_add(),
            self._grp_auto_date(),
            self._grp_numbering(),
            self._grp_move_copy(),
            self._grp_extension(),
            self._grp_filters(),
        ]
        for row, group in enumerate(groups):
            g.addWidget(group, row, 0)
        g.setColumnStretch(0, 1)
        g.setRowStretch(len(groups), 1)
        scroll.setWidget(container)
        return scroll

    # ── Action bar ────────────────────────────────────────────────────── #

    def _build_action_bar(self) -> QWidget:
        bar = QWidget(); h = QHBoxLayout(bar)
        h.setContentsMargins(4, 2, 4, 2); h.setSpacing(8)
        self._info_label = QLabel("")
        self._info_label.setStyleSheet(
            f"color:{COLORS['MUT']};font-size:11px;"
        )
        h.addWidget(self._info_label, stretch=1)
        self._chk_auto_dedup = QCheckBox("Auto-dedup conflicts")
        self._chk_auto_dedup.setChecked(True)
        self._chk_auto_dedup.setToolTip(
            "If destination exists, append _(2), _(3)… automatically"
        )
        h.addWidget(self._chk_auto_dedup)
        self._btn_undo = QPushButton("⎌  Undo")
        self._btn_undo.setObjectName("undoBtn")
        self._btn_undo.setEnabled(False)
        self._btn_undo.clicked.connect(self._do_undo)
        h.addWidget(self._btn_undo)
        self._btn_rename = QPushButton("✦  Rename")
        self._btn_rename.setObjectName("renameBtn")
        self._btn_rename.clicked.connect(self._do_rename)
        h.addWidget(self._btn_rename)
        return bar

    # ══════════════════════════════════════════════════════════════════ #
    #  GROUP BOXES
    # ══════════════════════════════════════════════════════════════════ #

    def _gl(self, parent: QGroupBox) -> QGridLayout:
        g = QGridLayout(parent); g.setSpacing(4); g.setContentsMargins(8, 18, 8, 8)
        reset_btn = QPushButton("R")
        reset_btn.setFixedSize(18, 18)
        reset_btn.setToolTip("Reset this group")
        reset_btn.clicked.connect(lambda: self._reset_group(parent))
        g.addWidget(reset_btn, 0, 99, alignment=Qt.AlignRight)
        return g

    def _reset_group(self, group: QGroupBox) -> None:
        for widget in group.findChildren((QLineEdit, QSpinBox, QComboBox, QCheckBox)):
            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QSpinBox):
                widget.setValue(0)
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(0)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(False)
        self._schedule_preview()

    # ── RegEx (1) ─────────────────────────────────────────────────────── #

    def _grp_regex(self) -> QGroupBox:
        gb = QGroupBox("⚡  REGEX  (1)"); g = self._gl(gb)

        g.addWidget(QLabel("Match"), 0, 0)
        self.rx_match = RegExLineEdit()
        self.rx_match.setPlaceholderText("pattern…")
        self.rx_match.setToolTip("Python regular expression pattern")
        g.addWidget(self.rx_match, 0, 1, 1, 2)

        self._rx_err = QLabel("")
        self._rx_err.setStyleSheet(f"color:{COLORS['ERR']};font-size:10px;")
        self._rx_err.setVisible(False)
        self.rx_match.set_error_label(self._rx_err)
        g.addWidget(self._rx_err, 1, 1, 1, 2)

        g.addWidget(QLabel("Replace"), 2, 0)
        self.rx_replace = QLineEdit(); self.rx_replace.setPlaceholderText("replacement…")
        self.rx_replace.setToolTip("Replacement string (supports \\1 back-references)")
        g.addWidget(self.rx_replace, 2, 1, 1, 2)

        self.rx_inc_ext = QCheckBox("Inc.Ext.")
        self.rx_simple  = QCheckBox("Simple (i)")
        self.rx_v2      = QCheckBox("v2")
        g.addWidget(self.rx_inc_ext, 3, 0)
        g.addWidget(self.rx_simple,  3, 1)
        g.addWidget(self.rx_v2,      3, 2)

        self._wire(self.rx_match, self.rx_replace,
                   self.rx_inc_ext, self.rx_simple, self.rx_v2)
        return gb

    # ── Name (2) ──────────────────────────────────────────────────────── #

    def _grp_name(self) -> QGroupBox:
        gb = QGroupBox("✏️  NAME  (2)"); g = self._gl(gb)
        g.addWidget(QLabel("Name"), 0, 0)
        self.name_mode = QComboBox()
        self.name_mode.addItems(["Keep", "Remove", "Fixed", "Reverse"])
        g.addWidget(self.name_mode, 0, 1)
        g.addWidget(QLabel("Fixed"), 1, 0)
        self.name_fixed = QLineEdit(); self.name_fixed.setPlaceholderText("fixed name…")
        g.addWidget(self.name_fixed, 1, 1)
        self._wire(self.name_mode, self.name_fixed)
        return gb

    # ── Replace (3) ───────────────────────────────────────────────────── #

    def _grp_replace(self) -> QGroupBox:
        gb = QGroupBox("🔁  REPLACE  (3)"); g = self._gl(gb)
        g.addWidget(QLabel("Replace"), 0, 0)
        self.repl_find = QLineEdit(); self.repl_find.setPlaceholderText("find…")
        g.addWidget(self.repl_find, 0, 1, 1, 2)
        g.addWidget(QLabel("With"), 1, 0)
        self.repl_with = QLineEdit(); self.repl_with.setPlaceholderText("with…")
        g.addWidget(self.repl_with, 1, 1, 1, 2)
        self.repl_match_case = QCheckBox("Match Case")
        self.repl_first      = QCheckBox("First only")
        g.addWidget(self.repl_match_case, 2, 0, 1, 2)
        g.addWidget(self.repl_first, 2, 2)
        self._wire(self.repl_find, self.repl_with,
                   self.repl_match_case, self.repl_first)
        return gb

    # ── Case (4) ──────────────────────────────────────────────────────── #

    def _grp_case(self) -> QGroupBox:
        gb = QGroupBox("🔤  CASE  (4)"); g = self._gl(gb)
        g.addWidget(QLabel("Case"), 0, 0)
        self.case_mode = QComboBox()
        self.case_mode.addItems(["Same", "Lower", "Upper", "Title", "Sentence"])
        g.addWidget(self.case_mode, 0, 1)
        g.addWidget(QLabel("Exceptions"), 1, 0)
        self.case_except = QLineEdit()
        self.case_except.setPlaceholderText("word, word…")
        self.case_except.setToolTip("Comma-separated words to leave unchanged")
        g.addWidget(self.case_except, 1, 1)
        self._wire(self.case_mode, self.case_except)
        return gb

    # ── Remove (5) ────────────────────────────────────────────────────── #

    def _grp_remove(self) -> QGroupBox:
        gb = QGroupBox("✂️  REMOVE  (5)"); g = self._gl(gb)

        def sp(mx=999):
            s = QSpinBox(); s.setRange(0, mx); s.setFixedWidth(56); return s

        g.addWidget(QLabel("First n"), 0, 0); self.rm_first = sp()
        g.addWidget(self.rm_first, 0, 1)
        g.addWidget(QLabel("Last n"),  0, 2); self.rm_last  = sp()
        g.addWidget(self.rm_last,  0, 3)
        g.addWidget(QLabel("From"),    1, 0); self.rm_from  = sp()
        g.addWidget(self.rm_from,  1, 1)
        g.addWidget(QLabel("to"),      1, 2); self.rm_to    = sp()
        g.addWidget(self.rm_to,    1, 3)

        self.rm_digits    = QCheckBox("Digits")
        self.rm_symbols   = QCheckBox("Symbols")
        self.rm_high      = QCheckBox("High")
        self.rm_ds        = QCheckBox("D/S")
        self.rm_accents   = QCheckBox("Accents")
        self.rm_lead_dots = QCheckBox("Lead Dots")
        self.rm_brackets  = QCheckBox("Brackets ()")
        self.rm_trim      = QCheckBox("Trim spaces")

        g.addWidget(self.rm_digits,    2, 0); g.addWidget(self.rm_symbols,   2, 1)
        g.addWidget(self.rm_high,      2, 2); g.addWidget(self.rm_ds,        2, 3)
        g.addWidget(self.rm_accents,   3, 0); g.addWidget(self.rm_lead_dots, 3, 1)
        g.addWidget(self.rm_brackets,  3, 2); g.addWidget(self.rm_trim,      3, 3)

        self._wire(self.rm_first, self.rm_last, self.rm_from, self.rm_to,
                   self.rm_digits, self.rm_symbols, self.rm_high, self.rm_ds,
                   self.rm_accents, self.rm_lead_dots, self.rm_brackets, self.rm_trim)
        return gb

    # ── Add (7) ───────────────────────────────────────────────────────── #

    def _grp_add(self) -> QGroupBox:
        gb = QGroupBox("➕  ADD  (7)"); g = self._gl(gb)
        _tip = (
            "Token substitution:\n"
            "  {n}            1-based row counter\n"
            "  {n0}           0-based row counter\n"
            "  {comic_series} CBZ ComicInfo Series\n"
            "  {comic_volume} CBZ ComicInfo Volume\n"
            "  {pdf_title}    PDF title metadata\n"
            "  {exif_make}    Image camera make\n"
            "  {file_mtime}   File mod date YYYY-MM-DD\n"
            "  {file_size}    File size in bytes"
        )
        g.addWidget(QLabel("Prefix"), 0, 0)
        self.add_prefix = QLineEdit()
        self.add_prefix.setPlaceholderText("prefix… ({n}, {comic_series}…)")
        self.add_prefix.setToolTip(_tip)
        g.addWidget(self.add_prefix, 0, 1, 1, 4)

        g.addWidget(QLabel("Insert"), 1, 0)
        self.add_insert = QLineEdit(); self.add_insert.setPlaceholderText("text…")
        g.addWidget(self.add_insert, 1, 1, 1, 2)
        g.addWidget(QLabel("at pos."), 1, 3)
        self.add_pos = QSpinBox(); self.add_pos.setRange(0, 999); self.add_pos.setFixedWidth(52)
        self.add_pos.setToolTip("1-based position (0 = append)")
        g.addWidget(self.add_pos, 1, 4)

        g.addWidget(QLabel("Suffix"), 2, 0)
        self.add_suffix = QLineEdit()
        self.add_suffix.setPlaceholderText("suffix… (supports {tokens})")
        self.add_suffix.setToolTip(_tip)
        g.addWidget(self.add_suffix, 2, 1, 1, 4)

        self.add_word_space = QCheckBox("Word Space before suffix")
        g.addWidget(self.add_word_space, 3, 0, 1, 3)

        self._wire(self.add_prefix, self.add_insert, self.add_pos,
                   self.add_suffix, self.add_word_space)
        return gb

    # ── Auto Date (8) ─────────────────────────────────────────────────── #

    def _grp_auto_date(self) -> QGroupBox:
        gb = QGroupBox("📅  AUTO DATE  (8)"); g = self._gl(gb)
        g.addWidget(QLabel("Mode"), 0, 0)
        self.date_mode = QComboBox()
        self.date_mode.addItems(["None", "Prefix", "Suffix"])
        g.addWidget(self.date_mode, 0, 1)
        g.addWidget(QLabel("Type"), 1, 0)
        self.date_type = QComboBox()
        self.date_type.addItems(["Creation (Current)", "Modified", "Accessed"])
        g.addWidget(self.date_type, 1, 1)
        g.addWidget(QLabel("Fmt"), 2, 0)
        self.date_fmt = QComboBox()
        self.date_fmt.addItems(["YMD", "DMY", "MDY", "ISO", "YMDHM", "HUMAN"])
        g.addWidget(self.date_fmt, 2, 1)
        g.addWidget(QLabel("Sep."), 3, 0)
        self.date_sep = QLineEdit(); self.date_sep.setPlaceholderText("_")
        self.date_sep.setFixedWidth(44)
        g.addWidget(self.date_sep, 3, 1)
        self._wire(self.date_mode, self.date_type, self.date_fmt, self.date_sep)
        return gb

    # ── Numbering (10) ────────────────────────────────────────────────── #

    def _grp_numbering(self) -> QGroupBox:
        gb = QGroupBox("#  NUMBERING  (10)"); g = self._gl(gb)
        g.addWidget(QLabel("Mode"), 0, 0)
        self.num_mode = QComboBox()
        self.num_mode.addItems(["None", "Prefix", "Suffix", "Both"])
        g.addWidget(self.num_mode, 0, 1)

        for row, lbl, attr, val in [
            (1, "Start", "num_start", 1),
            (2, "Incr.", "num_incr",  1),
            (3, "Pad",   "num_pad",   0),
            (5, "Break", "num_break", 0),
        ]:
            g.addWidget(QLabel(lbl), row, 0)
            s = QSpinBox(); s.setRange(0, 99999); s.setValue(val)
            setattr(self, attr, s); g.addWidget(s, row, 1)

        g.addWidget(QLabel("Sep."), 4, 0)
        self.num_sep = QLineEdit(); self.num_sep.setPlaceholderText("_")
        g.addWidget(self.num_sep, 4, 1)

        g.addWidget(QLabel("Base"), 6, 0)
        self.num_base = QComboBox()
        self.num_base.addItems(["Decimal", "Alpha", "Roman"])
        self.num_base.setToolTip(
            "Decimal → 1 2 3 …\nAlpha → a b c … aa ab …\nRoman → i ii iii …"
        )
        g.addWidget(self.num_base, 6, 1)

        self.num_break.setToolTip("Reset counter every N files (0 = never)")
        self._wire(self.num_mode, self.num_start, self.num_incr,
                   self.num_pad, self.num_sep, self.num_break, self.num_base)
        return gb

    # ── Move / Copy Parts (6) ─────────────────────────────────────────── #

    def _grp_move_copy(self) -> QGroupBox:
        gb = QGroupBox("↔️  MOVE/COPY  (6)"); g = self._gl(gb)
        g.addWidget(QLabel("Mode"), 0, 0)
        self.mcp_mode = QComboBox()
        self.mcp_mode.addItems(["None", "Move", "Copy"])
        self.mcp_mode.setToolTip("Move or copy a character range to a new position")
        g.addWidget(self.mcp_mode, 0, 1)
        for row, lbl, attr in [
            (1, "From pos.", "mcp_from"),
            (2, "Length",    "mcp_length"),
            (3, "To pos.",   "mcp_to"),
        ]:
            g.addWidget(QLabel(lbl), row, 0)
            s = QSpinBox(); s.setRange(1, 999); s.setValue(1)
            setattr(self, attr, s); g.addWidget(s, row, 1)
        g.addWidget(QLabel("Sep."), 4, 0)
        self.mcp_sep = QLineEdit(); self.mcp_sep.setPlaceholderText("-")
        self.mcp_sep.setFixedWidth(40)
        g.addWidget(self.mcp_sep, 4, 1)
        self._wire(self.mcp_mode, self.mcp_from, self.mcp_length,
                   self.mcp_to, self.mcp_sep)
        return gb

    # ── Extension (11) ────────────────────────────────────────────────── #

    def _grp_extension(self) -> QGroupBox:
        gb = QGroupBox("🔗  EXTENSION  (11)"); g = self._gl(gb)
        g.addWidget(QLabel("Mode"), 0, 0)
        self.ext_mode = QComboBox()
        self.ext_mode.addItems(["Same", "Lower", "Upper", "Fixed", "Remove"])
        g.addWidget(self.ext_mode, 0, 1)
        g.addWidget(QLabel("Fixed"), 1, 0)
        self.ext_fixed = QLineEdit(); self.ext_fixed.setPlaceholderText(".ext")
        g.addWidget(self.ext_fixed, 1, 1)
        self._wire(self.ext_mode, self.ext_fixed)
        return gb

    # ── Filters (12) ──────────────────────────────────────────────────── #

    def _grp_filters(self) -> QGroupBox:
        gb = QGroupBox("🔍  FILTERS  (12)"); g = self._gl(gb)
        g.addWidget(QLabel("Mask"), 0, 0)
        self.flt_mask = QLineEdit("*")
        self.flt_mask.setToolTip("Glob pattern, e.g. *.cbz  or  Claymore*")
        g.addWidget(self.flt_mask, 0, 1, 1, 3)
        self.flt_folders    = QCheckBox("Folders")
        self.flt_files      = QCheckBox("Files"); self.flt_files.setChecked(True)
        self.flt_hidden     = QCheckBox("Hidden")
        self.flt_subfolders = QCheckBox("Subfolders")
        for col, w in enumerate([self.flt_folders, self.flt_files,
                                  self.flt_hidden, self.flt_subfolders]):
            g.addWidget(w, 1, col)
        g.addWidget(QLabel("Name Min"), 2, 0)
        self.flt_name_min = QSpinBox(); self.flt_name_min.setRange(0, 999)
        g.addWidget(self.flt_name_min, 2, 1)
        g.addWidget(QLabel("Max"), 2, 2)
        self.flt_name_max = QSpinBox(); self.flt_name_max.setRange(0, 999)
        g.addWidget(self.flt_name_max, 2, 3)
        # Filter changes reload the directory listing
        for w in (self.flt_mask, self.flt_folders, self.flt_files,
                  self.flt_hidden, self.flt_subfolders,
                  self.flt_name_min, self.flt_name_max):
            self._wire_to(w, self._on_filter_changed)
        return gb

    # ══════════════════════════════════════════════════════════════════ #
    #  SIGNAL WIRING HELPERS
    # ══════════════════════════════════════════════════════════════════ #

    def _wire(self, *widgets) -> None:
        """Connect each widget's primary signal to the debounced preview."""
        for w in widgets:
            self._wire_to(w, self._schedule_preview)

    def _wire_to(self, w: QWidget, slot) -> None:
        if isinstance(w, QLineEdit):                w.textChanged.connect(slot)
        elif isinstance(w, (QSpinBox, QDoubleSpinBox)): w.valueChanged.connect(slot)
        elif isinstance(w, QComboBox):              w.currentIndexChanged.connect(slot)
        elif isinstance(w, QCheckBox):              w.stateChanged.connect(slot)

    def _schedule_preview(self, *_) -> None:
        self._preview_timer.start()

    # ══════════════════════════════════════════════════════════════════ #
    #  PARAMS  collect / apply / reset
    # ══════════════════════════════════════════════════════════════════ #

    def _collect_params(self) -> dict[str, Any]:
        return {
            "regex_match":       self.rx_match.text(),
            "regex_replace":     self.rx_replace.text(),
            "regex_inc_ext":     self.rx_inc_ext.isChecked(),
            "regex_simple":      self.rx_simple.isChecked(),
            "name_mode":         self.name_mode.currentText(),
            "name_fixed":        self.name_fixed.text(),
            "replace_find":      self.repl_find.text(),
            "replace_with":      self.repl_with.text(),
            "replace_match_case":self.repl_match_case.isChecked(),
            "replace_first_only":self.repl_first.isChecked(),
            "case_mode":         self.case_mode.currentText(),
            "case_exceptions":   self.case_except.text(),
            "remove_first_n":    self.rm_first.value(),
            "remove_last_n":     self.rm_last.value(),
            "remove_from":       self.rm_from.value(),
            "remove_to":         self.rm_to.value(),
            "remove_digits":     self.rm_digits.isChecked(),
            "remove_symbols":    self.rm_symbols.isChecked(),
            "remove_high":       self.rm_high.isChecked(),
            "remove_ds":         self.rm_ds.isChecked(),
            "remove_accents":    self.rm_accents.isChecked(),
            "remove_lead_dots":  self.rm_lead_dots.isChecked(),
            "remove_brackets":   self.rm_brackets.isChecked(),
            "remove_trim":       self.rm_trim.isChecked(),
            "add_prefix":        self.add_prefix.text(),
            "add_insert":        self.add_insert.text(),
            "add_at_pos":        self.add_pos.value(),
            "add_suffix":        self.add_suffix.text(),
            "add_word_space":    self.add_word_space.isChecked(),
            "date_mode":         self.date_mode.currentText(),
            "date_type":         self.date_type.currentText(),
            "date_fmt":          self.date_fmt.currentText(),
            "date_sep":          self.date_sep.text(),
            "num_mode":          self.num_mode.currentText(),
            "num_start":         self.num_start.value(),
            "num_incr":          self.num_incr.value(),
            "num_pad":           self.num_pad.value(),
            "num_sep":           self.num_sep.text(),
            "num_break":         self.num_break.value(),
            "num_base":          self.num_base.currentText(),
            "mcp_mode":          self.mcp_mode.currentText(),
            "mcp_from":          self.mcp_from.value(),
            "mcp_length":        self.mcp_length.value(),
            "mcp_to":            self.mcp_to.value(),
            "mcp_sep":           self.mcp_sep.text(),
            "ext_mode":          self.ext_mode.currentText(),
            "ext_fixed":         self.ext_fixed.text(),
        }

    def _apply_params(self, params: dict) -> None:
        def _s(w, key):
            v = params.get(key)
            if v is None: return
            if isinstance(w, QLineEdit):                w.setText(str(v))
            elif isinstance(w, (QSpinBox, QDoubleSpinBox)): w.setValue(int(v))
            elif isinstance(w, QComboBox):
                i = w.findText(str(v))
                if i >= 0: w.setCurrentIndex(i)
            elif isinstance(w, QCheckBox):              w.setChecked(bool(v))

        pairs = [
            (self.rx_match, "regex_match"), (self.rx_replace, "regex_replace"),
            (self.rx_inc_ext, "regex_inc_ext"), (self.rx_simple, "regex_simple"),
            (self.name_mode, "name_mode"), (self.name_fixed, "name_fixed"),
            (self.repl_find, "replace_find"), (self.repl_with, "replace_with"),
            (self.repl_match_case, "replace_match_case"),
            (self.repl_first, "replace_first_only"),
            (self.case_mode, "case_mode"), (self.case_except, "case_exceptions"),
            (self.rm_first, "remove_first_n"), (self.rm_last, "remove_last_n"),
            (self.rm_from, "remove_from"), (self.rm_to, "remove_to"),
            (self.rm_digits, "remove_digits"), (self.rm_symbols, "remove_symbols"),
            (self.rm_high, "remove_high"), (self.rm_ds, "remove_ds"),
            (self.rm_accents, "remove_accents"),
            (self.rm_lead_dots, "remove_lead_dots"),
            (self.rm_brackets, "remove_brackets"), (self.rm_trim, "remove_trim"),
            (self.add_prefix, "add_prefix"), (self.add_insert, "add_insert"),
            (self.add_pos, "add_at_pos"), (self.add_suffix, "add_suffix"),
            (self.add_word_space, "add_word_space"),
            (self.date_mode, "date_mode"), (self.date_type, "date_type"),
            (self.date_fmt, "date_fmt"), (self.date_sep, "date_sep"),
            (self.num_mode, "num_mode"), (self.num_start, "num_start"),
            (self.num_incr, "num_incr"), (self.num_pad, "num_pad"),
            (self.num_sep, "num_sep"), (self.num_break, "num_break"),
            (self.num_base, "num_base"),
            (self.mcp_mode, "mcp_mode"), (self.mcp_from, "mcp_from"),
            (self.mcp_length, "mcp_length"), (self.mcp_to, "mcp_to"),
            (self.mcp_sep, "mcp_sep"),
            (self.ext_mode, "ext_mode"), (self.ext_fixed, "ext_fixed"),
        ]
        for w, key in pairs:
            _s(w, key)

    def _reset_controls(self) -> None:
        for w in (self.rx_match, self.rx_replace, self.name_fixed,
                  self.repl_find, self.repl_with, self.case_except,
                  self.add_prefix, self.add_insert, self.add_suffix,
                  self.date_sep, self.num_sep, self.mcp_sep, self.ext_fixed):
            w.setText("")
        for w in (self.rx_inc_ext, self.rx_simple, self.rx_v2,
                  self.repl_match_case, self.repl_first,
                  self.rm_digits, self.rm_symbols, self.rm_high, self.rm_ds,
                  self.rm_accents, self.rm_lead_dots, self.rm_brackets, self.rm_trim,
                  self.add_word_space):
            w.setChecked(False)
        for w, v in [(self.rm_first,0),(self.rm_last,0),(self.rm_from,0),(self.rm_to,0),
                     (self.add_pos,0),(self.num_start,1),(self.num_incr,1),(self.num_pad,0),
                     (self.num_break,0),(self.mcp_from,1),(self.mcp_length,1),(self.mcp_to,1)]:
            w.setValue(v)
        for w in (self.name_mode, self.case_mode, self.date_mode,
                  self.num_mode, self.num_base, self.mcp_mode,
                  self.ext_mode, self.date_fmt):
            w.setCurrentIndex(0)

    # ══════════════════════════════════════════════════════════════════ #
    #  DIRECTORY LOADING
    # ══════════════════════════════════════════════════════════════════ #

    def _load_directory(self, directory: str) -> None:
        d = Path(directory)
        if not d.is_dir():
            self._status.showMessage(f"Not a directory: {directory}", 4000)
            return
        self._current_dir = str(d)
        self._path_edit.setText(self._current_dir)
        self._meta_cache.clear()

        mask     = self.flt_mask.text().strip() or "*"
        show_f   = self.flt_files.isChecked()
        show_d   = self.flt_folders.isChecked()
        show_h   = self.flt_hidden.isChecked()
        name_min = self.flt_name_min.value()
        name_max = self.flt_name_max.value()

        try:
            items = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            self._status.showMessage("Permission denied.", 4000)
            return

        filtered: list[str] = []
        for item in items:
            if item.name.startswith(".") and not show_h: continue
            if item.is_dir()  and not show_d:            continue
            if item.is_file() and not show_f:            continue
            if not fnmatch.fnmatch(item.name, mask):     continue
            sl = len(Path(item.name).stem)
            if name_min and sl < name_min:               continue
            if name_max and sl > name_max:               continue
            filtered.append(item.name)

        self._file_table.populate(filtered)
        self._count_label.setText(f"{len(filtered)} files")
        self._run_preview()

    def _on_filter_changed(self, *_) -> None:
        if self._current_dir:
            self._load_directory(self._current_dir)

    def _navigate_path_bar(self) -> None:
        self._load_directory(self._path_edit.text().strip())

    def _go_up(self) -> None:
        self._load_directory(str(Path(self._current_dir).parent))

    def _browse_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Select Folder", self._current_dir,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if d:
            self._load_directory(d)

    # ══════════════════════════════════════════════════════════════════ #
    #  LIVE PREVIEW
    # ══════════════════════════════════════════════════════════════════ #

    def update_preview(self, *_) -> None:
        """Public entry-point — goes through the debounce timer."""
        self._schedule_preview()

    def _run_preview(self) -> None:
        """Compute new names for all rows and refresh the New Name column."""
        params  = self._collect_params()
        table   = self._file_table
        names   = table.original_names()
        changed = 0

        table.blockSignals(True)

        # Progress bar for large folders
        total = len(names)
        show_progress = total > 500
        if show_progress:
            self._progress.setRange(0, total)
            self._progress.setValue(0)
            self._progress.setVisible(True)

        enabled_idx = 0
        for row, original in enumerate(names):
            if not table.row_enabled(row):
                table.set_skip(row, original)
                continue

            # Lazily extract and cache metadata
            if original not in self._meta_cache:
                try:
                    self._meta_cache[original] = self.extractor.extract(
                        Path(self._current_dir) / original
                    )
                except Exception:
                    self._meta_cache[original] = {}

            try:
                new_name = self.engine.process(
                    original, params,
                    index=enabled_idx,
                    metadata=self._meta_cache[original],
                )
                error = False
            except re.error as exc:
                new_name = f"[regex: {exc}]"; error = True
            except Exception as exc:
                new_name = f"[error: {exc}]"; error = True

            enabled_idx += 1
            is_changed  = (not error) and (new_name != original)
            if is_changed:
                changed += 1

            table.set_new_name(row, new_name, is_changed, error)

            if show_progress and row % 50 == 0:
                self._progress.setValue(row)
                QApplication.processEvents()

        table.blockSignals(False)

        if show_progress:
            self._progress.setVisible(False)

        skipped = sum(1 for r in range(total) if not table.row_enabled(r))
        self._info_label.setText(
            f"{total} files  ·  {changed} will rename  ·  {skipped} skipped"
        )

    # ══════════════════════════════════════════════════════════════════ #
    #  RENAME
    # ══════════════════════════════════════════════════════════════════ #

    def _do_rename(self) -> None:
        params     = self._collect_params()
        table      = self._file_table
        names      = table.original_names()
        errors:    list[str]              = []
        batch:     list[tuple[str, str]]  = []
        auto_dedup = self._chk_auto_dedup.isChecked()

        enabled_idx = 0
        for row, original in enumerate(names):
            if not table.row_enabled(row):
                continue
            meta = self._meta_cache.get(original, {})
            try:
                new_name = self.engine.process(
                    original, params, index=enabled_idx, metadata=meta
                )
            except Exception as exc:
                errors.append(f"{original}: {exc}")
                continue
            finally:
                enabled_idx += 1

            if new_name == original:
                continue

            src = Path(self._current_dir) / original
            dst = Path(self._current_dir) / new_name

            # Auto-dedup: append _(2), _(3) … until no conflict
            if dst.exists() and auto_dedup:
                stem, ext = Path(new_name).stem, Path(new_name).suffix
                k = 2
                while dst.exists():
                    new_name = f"{stem}_({k}){ext}"
                    dst      = Path(self._current_dir) / new_name
                    k       += 1

            if dst.exists():
                errors.append(f"Destination exists: {new_name}")
                table.set_warn_status(row)
                continue

            try:
                os.rename(src, dst)
                batch.append((original, new_name))
                table.set_done(row)
            except OSError as exc:
                errors.append(f"{original} → {new_name}: {exc}")
                table.set_error_status(row)

        if batch:
            entry = HistoryEntry(self._current_dir, batch)
            self.history.push(entry)
            self._history_panel.refresh(self.history.visible_entries())
            self._btn_undo.setEnabled(True)

        if errors:
            QMessageBox.warning(
                self, "Rename Errors",
                f"{len(batch)} renamed successfully.\n\nErrors:\n" +
                "\n".join(errors[:15]),
            )
        else:
            self._status.showMessage(
                f"✓ {len(batch)} file(s) renamed.", 5000
            )

        self._load_directory(self._current_dir)

    # ══════════════════════════════════════════════════════════════════ #
    #  UNDO
    # ══════════════════════════════════════════════════════════════════ #

    def _do_undo(self) -> None:
        entry = self.history.undo()
        if not entry:
            return
        errors = entry.undo()
        self._history_panel.refresh(self.history.visible_entries())
        can = self.history.can_undo()
        self._btn_undo.setEnabled(can)
        if errors:
            QMessageBox.warning(self, "Undo Errors", "\n".join(errors[:15]))
        else:
            self._status.showMessage(
                f"⎌ Undone: {len(entry.renames)} rename(s).", 4000
            )
        if entry.directory == self._current_dir:
            self._load_directory(self._current_dir)

    # ══════════════════════════════════════════════════════════════════ #
    #  PRESETS
    # ══════════════════════════════════════════════════════════════════ #

    def _open_presets(self) -> None:
        dlg = PresetDialog(self.presets, self._collect_params(), self)
        if dlg.exec() == QDialog.Accepted and dlg.chosen_params:
            self._apply_params(dlg.chosen_params)
            self._run_preview()
