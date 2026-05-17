"""
bru.widgets
===========
Reusable PySide6 widgets used by the main window.

Classes
-------
FileTable          QTableWidget subclass with drag-to-reorder rows,
                   per-row enable checkboxes, and a right-click menu.
HistoryPanel       Read-only QListWidget panel for the undo history.
PresetDialog       Modal dialog for managing saved presets.
SectionLabel       Styled QLabel used as a panel header.
RegExLineEdit      QLineEdit that turns red on invalid regex patterns
                   and shows an inline error label.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QDrag, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QDialogButtonBox,
    QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QPushButton,
    QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

import re

from bru.theme import COLORS

# Column indices (shared constant — import from here if needed)
COL_ENABLE = 0
COL_ORIG   = 1
COL_NEW    = 2
COL_STATUS = 3


# ══════════════════════════════════════════════════════════════════════════════
#  SectionLabel
# ══════════════════════════════════════════════════════════════════════════════

class SectionLabel(QLabel):
    """Pill-style panel header label."""
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(f"  {text}", parent)
        c = COLORS
        self.setStyleSheet(
            f"background:{c['BG3']};color:{c['MUT']};"
            "font-size:10px;font-weight:700;letter-spacing:0.1em;"
            "padding:4px 8px;border-radius:4px;"
        )


# ══════════════════════════════════════════════════════════════════════════════
#  RegExLineEdit
# ══════════════════════════════════════════════════════════════════════════════

class RegExLineEdit(QLineEdit):
    """
    QLineEdit that validates its text as a Python regex on every change
    and emits ``regex_valid(bool)`` accordingly.
    Turns the border red when the pattern is invalid.
    """
    regex_valid = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._error_lbl: QLabel | None = None
        self.textChanged.connect(self._validate)

    def set_error_label(self, lbl: QLabel) -> None:
        """Attach an external QLabel that will show the error text."""
        self._error_lbl = lbl

    def _validate(self, text: str) -> None:
        if not text.strip():
            self._set_valid(True, "")
            return
        try:
            re.compile(text)
            self._set_valid(True, "")
        except re.error as exc:
            self._set_valid(False, str(exc))

    def _set_valid(self, valid: bool, msg: str) -> None:
        self.setProperty("valid", "true" if valid else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        if self._error_lbl is not None:
            self._error_lbl.setText(f"  ✗ {msg}" if msg else "")
            self._error_lbl.setVisible(bool(msg))
        self.regex_valid.emit(valid)


# ══════════════════════════════════════════════════════════════════════════════
#  FileTable
# ══════════════════════════════════════════════════════════════════════════════

class FileTable(QTableWidget):
    """
    Four-column table:  ☐ | Original Name | New Name | Status

    Features
    --------
    • Per-row enable/disable checkbox in column 0.
    • Drag-to-reorder rows (internal move).
    • Right-click context menu: enable / disable / copy new names.
    • ``rows_reordered`` signal emitted after a drag-drop reorder.
    • ``selection_toggled`` signal emitted when a checkbox changes.
    """

    rows_reordered   = Signal()
    selection_toggled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, 4, parent)
        self._setup_appearance()
        self._setup_dnd()
        self.itemChanged.connect(self._on_item_changed)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

    # ------------------------------------------------------------------ #
    def _setup_appearance(self) -> None:
        c = COLORS
        self.setHorizontalHeaderLabels(["", "Original Name", "New Name", "Status"])
        hh = self.horizontalHeader()
        hh.setSectionResizeMode(COL_ENABLE, QHeaderView.Fixed)
        hh.setSectionResizeMode(COL_ORIG,   QHeaderView.Stretch)
        hh.setSectionResizeMode(COL_NEW,    QHeaderView.Stretch)
        hh.setSectionResizeMode(COL_STATUS, QHeaderView.Fixed)
        self.setColumnWidth(COL_ENABLE, 28)
        self.setColumnWidth(COL_STATUS, 90)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.verticalHeader().setDefaultSectionSize(22)
        self.verticalHeader().setVisible(False)

    def _setup_dnd(self) -> None:
        """Enable internal drag-and-drop row reordering."""
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDragDropOverwriteMode(False)
        self.setDefaultDropAction(Qt.MoveAction)

    # ------------------------------------------------------------------ #
    # Public helpers
    # ------------------------------------------------------------------ #
    def populate(self, filenames: list[str]) -> None:
        """Replace table contents with *filenames*. Preserves no state."""
        self.blockSignals(True)
        self.setRowCount(0)
        self.setRowCount(len(filenames))
        c = COLORS
        for row, name in enumerate(filenames):
            # Column 0: enable checkbox
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Checked)
            self.setItem(row, COL_ENABLE, chk)
            # Column 1: original name
            orig = QTableWidgetItem(name)
            orig.setForeground(QColor(c["FG"]))
            self.setItem(row, COL_ORIG, orig)
            # Columns 2–3: placeholders
            self.setItem(row, COL_NEW,    QTableWidgetItem(""))
            self.setItem(row, COL_STATUS, QTableWidgetItem(""))
        self.blockSignals(False)

    def row_enabled(self, row: int) -> bool:
        it = self.item(row, COL_ENABLE)
        return it is not None and it.checkState() == Qt.Checked

    def set_all_enabled(self, state: bool) -> None:
        self.blockSignals(True)
        for row in range(self.rowCount()):
            it = self.item(row, COL_ENABLE)
            if it:
                it.setCheckState(Qt.Checked if state else Qt.Unchecked)
        self.blockSignals(False)
        self.selection_toggled.emit()

    def invert_enabled(self) -> None:
        self.blockSignals(True)
        for row in range(self.rowCount()):
            it = self.item(row, COL_ENABLE)
            if it:
                it.setCheckState(
                    Qt.Unchecked if it.checkState() == Qt.Checked else Qt.Checked
                )
        self.blockSignals(False)
        self.selection_toggled.emit()

    def original_names(self) -> list[str]:
        """Return the current (possibly reordered) list of original names."""
        result: list[str] = []
        for row in range(self.rowCount()):
            it = self.item(row, COL_ORIG)
            result.append(it.text() if it else "")
        return result

    def set_new_name(self, row: int, new_name: str, changed: bool, error: bool) -> None:
        """Paint a single New Name cell with appropriate colour."""
        c  = COLORS
        ni = QTableWidgetItem(new_name)
        if error:
            ni.setForeground(QColor(c["ERR"]))
            st_text, st_color = "✗ error", c["ERR"]
        elif changed:
            ni.setForeground(QColor(c["ACC2"]))
            st_text, st_color = "→ rename", c["OK"]
        else:
            ni.setForeground(QColor(c["MUT"]))
            st_text, st_color = "—", c["MUT"]
        si = QTableWidgetItem(st_text)
        si.setForeground(QColor(st_color))
        self.setItem(row, COL_NEW,    ni)
        self.setItem(row, COL_STATUS, si)

    def set_skip(self, row: int, original: str) -> None:
        """Mark a row as skipped (checkbox unchecked)."""
        c  = COLORS
        ni = QTableWidgetItem(original)
        ni.setForeground(QColor(c["MUT"]))
        si = QTableWidgetItem("(skip)")
        si.setForeground(QColor(c["MUT"]))
        self.setItem(row, COL_NEW,    ni)
        self.setItem(row, COL_STATUS, si)

    def set_done(self, row: int) -> None:
        it = QTableWidgetItem("✓ done")
        it.setForeground(QColor(COLORS["OK"]))
        self.setItem(row, COL_STATUS, it)

    def set_error_status(self, row: int, msg: str = "✗ error") -> None:
        it = QTableWidgetItem(msg)
        it.setForeground(QColor(COLORS["ERR"]))
        self.setItem(row, COL_STATUS, it)

    def set_warn_status(self, row: int, msg: str = "⚠ exists") -> None:
        it = QTableWidgetItem(msg)
        it.setForeground(QColor(COLORS["WARN"]))
        self.setItem(row, COL_STATUS, it)

    # ------------------------------------------------------------------ #
    # Drag-and-drop row reorder (override dropEvent)
    # ------------------------------------------------------------------ #
    def dropEvent(self, event) -> None:  # type: ignore[override]
        if event.source() is not self:
            event.ignore()
            return

        drop_row = self.indexAt(event.position().toPoint()).row()
        if drop_row < 0:
            drop_row = self.rowCount()

        # Collect all selected rows in original order
        selected_rows = sorted({idx.row() for idx in self.selectedIndexes()})
        if not selected_rows:
            event.ignore()
            return

        # Snapshot every row's data before mutating
        def _snapshot(row: int) -> list[QTableWidgetItem | None]:
            return [self.takeItem(row, col) for col in range(self.columnCount())]

        rows_data = [_snapshot(r) for r in selected_rows]

        # Remove rows in reverse order so indices stay valid
        for r in reversed(selected_rows):
            self.removeRow(r)
            if drop_row > r:
                drop_row -= 1

        # Re-insert at new position
        for i, data in enumerate(rows_data):
            ins = drop_row + i
            self.insertRow(ins)
            for col, item in enumerate(data):
                if item:
                    self.setItem(ins, col, item)

        event.accept()
        self.rows_reordered.emit()

    # ------------------------------------------------------------------ #
    # Signals
    # ------------------------------------------------------------------ #
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == COL_ENABLE:
            self.selection_toggled.emit()

    # ------------------------------------------------------------------ #
    # Context menu
    # ------------------------------------------------------------------ #
    def _context_menu(self, pos) -> None:
        rows = {idx.row() for idx in self.selectedIndexes()}
        if not rows:
            return
        menu   = QMenu(self)
        a_en   = menu.addAction("✓  Enable selected")
        a_dis  = menu.addAction("○  Disable selected")
        menu.addSeparator()
        a_copy = menu.addAction("📋  Copy new names to clipboard")
        a_orig = menu.addAction("📋  Copy original names to clipboard")
        action = menu.exec(self.viewport().mapToGlobal(pos))
        if action == a_en:
            for r in rows:
                self.item(r, COL_ENABLE).setCheckState(Qt.Checked)
            self.selection_toggled.emit()
        elif action == a_dis:
            for r in rows:
                self.item(r, COL_ENABLE).setCheckState(Qt.Unchecked)
            self.selection_toggled.emit()
        elif action == a_copy:
            names = [self.item(r, COL_NEW).text() for r in sorted(rows)
                     if self.item(r, COL_NEW)]
            QApplication.clipboard().setText("\n".join(names))
        elif action == a_orig:
            names = [self.item(r, COL_ORIG).text() for r in sorted(rows)
                     if self.item(r, COL_ORIG)]
            QApplication.clipboard().setText("\n".join(names))


# ══════════════════════════════════════════════════════════════════════════════
#  HistoryPanel
# ══════════════════════════════════════════════════════════════════════════════

class HistoryPanel(QWidget):
    """
    Sidebar panel showing recent rename batches.
    Double-clicking an entry emits ``undo_requested``.
    """
    undo_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        v.addWidget(SectionLabel("Undo History"))

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setToolTip("Double-click to undo that rename batch")
        self._list.itemDoubleClicked.connect(lambda _: self.undo_requested.emit())
        v.addWidget(self._list)

        btn = QPushButton("⎌  Undo Latest")
        btn.clicked.connect(self.undo_requested.emit)
        v.addWidget(btn)

    def refresh(self, entries: list) -> None:
        """Re-populate with ``HistoryEntry`` objects (newest first)."""
        self._list.clear()
        for entry in entries:
            self._list.addItem(QListWidgetItem(entry.summary_label()))


# ══════════════════════════════════════════════════════════════════════════════
#  PresetDialog
# ══════════════════════════════════════════════════════════════════════════════

class PresetDialog(QDialog):
    """
    Modal dialog for managing named presets.

    After ``exec()`` returns ``Accepted``, check ``chosen_params`` for the
    loaded params dict (or ``None`` if the user only saved/deleted).
    """

    def __init__(self, manager, current_params: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.manager        = manager
        self.current_params = current_params
        self.chosen_params: dict | None = None

        self.setWindowTitle("Manage Presets")
        self.setMinimumSize(380, 360)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Saved presets  (double-click to load):"))

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.addItems(manager.names())
        self._list.itemDoubleClicked.connect(self._load_selected)
        layout.addWidget(self._list)

        # Button row
        btn_row = QHBoxLayout()
        for lbl, slot in [
            ("Load",          self._load_selected),
            ("Save Current…", self._save_current),
            ("Rename…",       self._rename_preset),
            ("Delete",        self._delete_selected),
        ]:
            b = QPushButton(lbl)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        layout.addLayout(btn_row)

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def _load_selected(self) -> None:
        item = self._list.currentItem()
        if item:
            self.chosen_params = self.manager.load(item.text())
            self.accept()

    def _save_current(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Preset", "Preset name:")
        if ok and name.strip():
            self.manager.save(name.strip(), self.current_params)
            self._list.clear()
            self._list.addItems(self.manager.names())

    def _rename_preset(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        new_name, ok = QInputDialog.getText(
            self, "Rename Preset", "New name:", text=item.text()
        )
        if ok and new_name.strip() and new_name.strip() != item.text():
            self.manager.rename_preset(item.text(), new_name.strip())
            self._list.clear()
            self._list.addItems(self.manager.names())

    def _delete_selected(self) -> None:
        item = self._list.currentItem()
        if item:
            self.manager.delete(item.text())
            self._list.takeItem(self._list.row(item))
