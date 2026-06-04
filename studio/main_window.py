"""
studio.main_window
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
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from studio.engine import RenameEngine
from studio.history import HistoryEntry, HistoryManager
from studio.metadata import MetadataExtractor
from studio.metadata_ui import MainWindow as MetadataEditorMainWindow
from studio.pipeline_ui import PipelineEditor
from studio.presets import PresetManager
from studio.theme import COLORS, THEMES_DIR, apply_theme, load_cosmic_ron_palette
from studio.ui_loader import load_ui
from studio.widgets import FileTable, HistoryPanel, PresetDialog


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
        self._history_preview_dir = Path(tempfile.mkdtemp(prefix="studio_history_preview_"))

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
        """Load the main window from Qt Designer files and wire runtime widgets."""
        self._ui = load_ui("main_window.ui", self)
        self.setCentralWidget(self._ui)

        def child(cls, name: str):
            widget = self._ui.findChild(cls, name)
            if widget is None:
                raise RuntimeError(f"Missing widget '{name}' in gui/main_window.ui")
            return widget

        self._tabs = child(QTabWidget, "tabs")

        # Rename tab: designer-owned shell plus custom runtime widgets.
        self._path_edit = child(QLineEdit, "pathEdit")
        self._path_edit.returnPressed.connect(self._navigate_path_bar)
        child(QPushButton, "pathGoButton").clicked.connect(self._navigate_path_bar)
        child(QPushButton, "pathUpButton").clicked.connect(self._go_up)
        child(QPushButton, "pathBrowseButton").clicked.connect(self._browse_folder)

        self._count_label = child(QLabel, "countLabel")
        self._count_label.setStyleSheet(f"color:{COLORS['MUT']};font-size:11px;")
        self._info_label = child(QLabel, "infoLabel")
        self._info_label.setStyleSheet(f"color:{COLORS['MUT']};font-size:11px;")
        self._chk_auto_dedup = child(QCheckBox, "autoDedupCheck")
        self._btn_undo = child(QPushButton, "undoBtn")
        self._btn_undo.clicked.connect(self._do_undo)
        self._btn_rename = child(QPushButton, "renameBtn")
        self._btn_rename.clicked.connect(self._do_rename)

        controls_scroll = child(QScrollArea, "controlsScroll")
        self._controls_widget = load_ui("rename_controls.ui", controls_scroll)
        controls_scroll.setWidget(self._controls_widget)
        self._bind_rename_controls()

        file_host = child(QWidget, "fileTableHost")
        file_layout = QVBoxLayout(file_host)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self._file_table = FileTable()
        self._file_table.rows_reordered.connect(self._schedule_preview)
        self._file_table.selection_toggled.connect(self._schedule_preview)
        file_layout.addWidget(self._file_table)

        # Rule Pipeline tab.
        pipeline_host = child(QWidget, "pipelineHost")
        pipeline_layout = QVBoxLayout(pipeline_host)
        pipeline_layout.setContentsMargins(0, 0, 0, 0)
        self._pipeline_panel = PipelineEditor()
        self._pipeline_panel.order_changed.connect(self._schedule_preview)
        self._pipeline_panel.library_changed.connect(self._on_pipeline_library_changed)
        pipeline_layout.addWidget(self._pipeline_panel)

        # Metadata tab.
        metadata_host = child(QWidget, "metadataHost")
        metadata_layout = QVBoxLayout(metadata_host)
        metadata_layout.setContentsMargins(0, 0, 0, 0)
        self._metadata_window = MetadataEditorMainWindow(show_console=False)
        self._metadata_window.setWindowFlags(Qt.Widget)
        self._metadata_window.setParent(metadata_host)
        self._metadata_window.log_emitted.connect(self._append_console)
        metadata_layout.addWidget(self._metadata_window)

        # History tab.
        history_host = child(QWidget, "historyPanelHost")
        history_layout = QVBoxLayout(history_host)
        history_layout.setContentsMargins(0, 0, 0, 0)
        self._history_panel = HistoryPanel()
        self._history_panel.undo_requested.connect(self._do_undo)
        history_layout.addWidget(self._history_panel)
        self._history_console = child(QTextEdit, "historyConsole")

        # Settings tab.
        self._theme_combo = child(QComboBox, "themeCombo")
        self._refresh_theme_choices()
        self._theme_combo.addItems(list(self._theme_choices.keys()))
        self._theme_combo.currentTextChanged.connect(self._on_theme_combo_changed)
        self._settings_path_edit = child(QLineEdit, "settingsPathEdit")
        self._settings_path_edit.editingFinished.connect(self._save_settings)
        self._always_on_top = child(QCheckBox, "alwaysOnTopCheck")
        self._always_on_top.toggled.connect(self._on_always_on_top_toggled)
        self._meta_icon_font_edit = child(QLineEdit, "metaIconFontEdit")
        self._meta_icon_font_edit.editingFinished.connect(self._on_metadata_icons_changed)
        self._meta_icon_edits = {
            "update": child(QLineEdit, "metaUpdateIconEdit"),
            "mirror": child(QLineEdit, "metaMirrorIconEdit"),
            "auto": child(QLineEdit, "metaAutoIconEdit"),
            "clear": child(QLineEdit, "metaClearIconEdit"),
        }
        for edit in self._meta_icon_edits.values():
            edit.editingFinished.connect(self._on_metadata_icons_changed)

        self._status = QStatusBar()
        self._progress = QProgressBar()
        self._progress.setFixedWidth(200)
        self._progress.setVisible(False)
        self._status.addPermanentWidget(self._progress)
        self.setStatusBar(self._status)
        self._status.showMessage("Ready — select a folder to begin.")

    def _bind_rename_controls(self) -> None:
        """Bind widgets from gui/rename_controls.ui to the attribute names used by the engine."""
        def control(cls, name: str):
            widget = self._controls_widget.findChild(cls, name)
            if widget is None:
                raise RuntimeError(f"Missing widget '{name}' in gui/rename_controls.ui")
            setattr(self, name, widget)
            return widget

        line_edits = [
            "rx_match", "rx_replace", "name_fixed", "repl_find", "repl_with",
            "case_except", "add_prefix", "add_insert", "add_suffix", "date_sep",
            "num_sep", "mcp_sep", "ext_fixed", "flt_mask",
        ]
        spin_boxes = [
            "rm_first", "rm_last", "rm_from", "rm_to", "add_pos", "num_start",
            "num_incr", "num_pad", "num_break", "mcp_from", "mcp_length", "mcp_to",
            "flt_name_min", "flt_name_max",
        ]
        combos = [
            "name_mode", "case_mode", "date_mode", "date_type", "date_fmt",
            "num_mode", "num_base", "mcp_mode", "ext_mode",
        ]
        checks = [
            "rx_inc_ext", "rx_simple", "rx_v2", "repl_match_case", "repl_first",
            "rm_digits", "rm_symbols", "rm_high", "rm_ds", "rm_accents",
            "rm_lead_dots", "rm_brackets", "rm_trim", "add_word_space",
            "flt_folders", "flt_files", "flt_hidden", "flt_subfolders",
        ]
        for name in line_edits:
            control(QLineEdit, name)
        for name in spin_boxes:
            control(QSpinBox, name)
        for name in combos:
            control(QComboBox, name)
        for name in checks:
            control(QCheckBox, name)

        combo_items = {
            "name_mode": ["Keep", "Remove", "Fixed", "Reverse"],
            "case_mode": ["Same", "Lower", "Upper", "Title", "Sentence"],
            "date_mode": ["None", "Prefix", "Suffix"],
            "date_type": ["Creation (Current)", "Modified", "Accessed"],
            "date_fmt": ["YMD", "DMY", "MDY", "ISO", "YMDHM", "HUMAN"],
            "num_mode": ["None", "Prefix", "Suffix", "Both"],
            "num_base": ["Decimal", "Alpha", "Roman"],
            "mcp_mode": ["None", "Move", "Copy"],
            "ext_mode": ["Same", "Lower", "Upper", "Fixed", "Remove"],
        }
        for name, items in combo_items.items():
            combo = getattr(self, name)
            combo.clear()
            combo.addItems(items)

        self._rx_err = self._controls_widget.findChild(QLabel, "rxErrLabel")
        if self._rx_err is not None:
            self._rx_err.setStyleSheet(f"color:{COLORS['ERR']};font-size:10px;")
            self._rx_err.setVisible(False)
            self.rx_match.textChanged.connect(self._validate_regex_control)

        preview_widgets = [
            self.rx_match, self.rx_replace, self.rx_inc_ext, self.rx_simple, self.rx_v2,
            self.name_mode, self.name_fixed, self.repl_find, self.repl_with,
            self.repl_match_case, self.repl_first, self.case_mode, self.case_except,
            self.rm_first, self.rm_last, self.rm_from, self.rm_to, self.rm_digits,
            self.rm_symbols, self.rm_high, self.rm_ds, self.rm_accents,
            self.rm_lead_dots, self.rm_brackets, self.rm_trim, self.add_prefix,
            self.add_insert, self.add_pos, self.add_suffix, self.add_word_space,
            self.date_mode, self.date_type, self.date_fmt, self.date_sep,
            self.num_mode, self.num_start, self.num_incr, self.num_pad, self.num_sep,
            self.num_break, self.num_base, self.mcp_mode, self.mcp_from,
            self.mcp_length, self.mcp_to, self.mcp_sep, self.ext_mode, self.ext_fixed,
        ]
        for widget in preview_widgets:
            self._wire(widget)
        for widget in (
            self.flt_mask, self.flt_folders, self.flt_files, self.flt_hidden,
            self.flt_subfolders, self.flt_name_min, self.flt_name_max,
        ):
            self._wire_to(widget, self._on_filter_changed)

    def _validate_regex_control(self, text: str) -> None:
        if self._rx_err is None:
            return
        if not text.strip():
            self._rx_err.clear()
            self._rx_err.setVisible(False)
            return
        try:
            re.compile(text)
        except re.error as exc:
            self._rx_err.setText(f"  ✗ {exc}")
            self._rx_err.setVisible(True)
        else:
            self._rx_err.clear()
            self._rx_err.setVisible(False)

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
        default_theme = self._theme_choices.get(
            "COSMIC • Windows 10 Light", next(iter(self._theme_choices.values()), "")
        )
        settings = {
            "theme": default_theme,
            "default_path": default_downloads,
            "last_directory": default_downloads,
            "always_on_top": False,
            "window": {"x": 100, "y": 100, "w": 1920, "h": 826},
            "pipelines": {},
            "active_pipeline": "Factory Default",
        }
        if self._settings_path.exists():
            try:
                settings.update(json.loads(self._settings_path.read_text(encoding="utf-8")))
            except Exception:
                pass
        self._settings_path_edit.setText(settings.get("default_path", default_downloads))
        self._current_dir = settings.get("last_directory") or settings.get(
            "default_path", default_downloads
        )
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
        self._theme_combo.setCurrentText(
            reverse.get(selected_theme, next(iter(self._theme_choices.keys()), ""))
        )
        self._set_theme(selected_theme)
        self._pipeline_panel.set_library(
            settings.get("pipelines", {}), settings.get("active_pipeline")
        )
        meta_icons = settings.get("metadata_icons", {})
        self._meta_icon_font_edit.setText(settings.get("metadata_icon_font", "Noto Color Emoji"))
        for key, edit in self._meta_icon_edits.items():
            edit.setText(meta_icons.get(key, ""))
        self._on_metadata_icons_changed()

    def _save_settings(self) -> None:
        g = self.geometry()
        data = {
            "theme": self._theme_choices.get(
                self._theme_combo.currentText(), next(iter(self._theme_choices.values()), "")
            ),
            "default_path": self._settings_path_edit.text().strip()
            or str(Path.home() / "Downloads"),
            "last_directory": self._current_dir,
            "always_on_top": self._always_on_top.isChecked(),
            "metadata_icon_font": self._meta_icon_font_edit.text().strip() or "Noto Color Emoji",
            "metadata_icons": {k: e.text().strip() for k, e in self._meta_icon_edits.items()},
            "pipelines": self._pipeline_panel.pipeline_library(),
            "active_pipeline": self._pipeline_panel.active_pipeline_name(),
            "window": {"x": g.x(), "y": g.y(), "w": g.width(), "h": g.height()},
        }
        self._settings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _on_pipeline_library_changed(self, _library: dict, _active_name: str) -> None:
        self._save_settings()

    def _on_metadata_icons_changed(self) -> None:
        icons = {k: e.text().strip() for k, e in self._meta_icon_edits.items()}
        self._metadata_window.table.set_action_icons(
            icons, self._meta_icon_font_edit.text().strip()
        )
        self._save_settings()

    def _on_always_on_top_toggled(self, checked: bool) -> None:
        self._apply_always_on_top(checked)
        self._save_settings()

    def _apply_always_on_top(self, enabled: bool) -> None:
        self.setWindowFlag(Qt.WindowStaysOnTopHint, enabled)
        self.show()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_settings()
        shutil.rmtree(self._history_preview_dir, ignore_errors=True)
        super().closeEvent(event)

    # ══════════════════════════════════════════════════════════════════ #
    #  SIGNAL WIRING HELPERS
    # ══════════════════════════════════════════════════════════════════ #

    def _wire(self, *widgets) -> None:
        """Connect each widget's primary signal to the debounced preview."""
        for w in widgets:
            self._wire_to(w, self._schedule_preview)

    def _wire_to(self, w: QWidget, slot) -> None:
        if isinstance(w, QLineEdit):
            w.textChanged.connect(slot)
        elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
            w.valueChanged.connect(slot)
        elif isinstance(w, QComboBox):
            w.currentIndexChanged.connect(slot)
        elif isinstance(w, QCheckBox):
            w.stateChanged.connect(slot)

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
            "pipeline_order":    self._pipeline_panel.current_order(),
            "pipeline_name":     self._pipeline_panel.active_pipeline_name(),
        }

    def _apply_params(self, params: dict) -> None:
        def _s(w, key):
            v = params.get(key)
            if v is None:
                return
            if isinstance(w, QLineEdit):
                w.setText(str(v))
            elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                w.setValue(int(v))
            elif isinstance(w, QComboBox):
                i = w.findText(str(v))
                if i >= 0:
                    w.setCurrentIndex(i)
            elif isinstance(w, QCheckBox):
                w.setChecked(bool(v))

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
            if item.name.startswith(".") and not show_h:
                continue
            if item.is_dir() and not show_d:
                continue
            if item.is_file() and not show_f:
                continue
            if not fnmatch.fnmatch(item.name, mask):
                continue
            sl = len(Path(item.name).stem)
            if name_min and sl < name_min:
                continue
            if name_max and sl > name_max:
                continue
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
                new_name = f"[regex: {exc}]"
                error = True
            except Exception as exc:
                new_name = f"[error: {exc}]"
                error = True

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
            preview_file = self._history_preview_dir / f"history_preview_{len(self.history.visible_entries())+1}_{time.time_ns()}.png"
            self._file_table.grab().save(str(preview_file), "PNG")
            entry = HistoryEntry(self._current_dir, batch, preview_path=str(preview_file))
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
