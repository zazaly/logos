"""
bru.history
===========
Undo/redo stack for rename batches.

Usage
-----
    mgr = HistoryManager()
    entry = HistoryEntry(directory="/some/path", renames=[("old.txt","new.txt")])
    mgr.push(entry)

    if mgr.can_undo():
        entry = mgr.undo()
        errors = entry.undo()     # physically reverses the renames
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

MAX_HISTORY = 50


@dataclass
class HistoryEntry:
    """
    One committed batch rename.

    Attributes
    ----------
    directory : str
        Absolute path of the folder in which renames occurred.
    renames : list[tuple[str, str]]
        Ordered list of (original_name, new_name) pairs.
    timestamp : str
        HH:MM:SS string captured at construction time.
    """
    directory: str
    renames:   list[tuple[str, str]]
    preview_path: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))

    # ------------------------------------------------------------------ #
    def undo(self) -> list[str]:
        """
        Reverse every rename in this entry (applied in reverse order).

        Returns a list of human-readable error strings; empty on full success.
        """
        errors: list[str] = []
        for original, new_name in reversed(self.renames):
            src = Path(self.directory) / new_name
            dst = Path(self.directory) / original
            if not src.exists():
                errors.append(f"Missing (cannot undo): {new_name}")
                continue
            if dst.exists():
                errors.append(f"Destination already exists: {original}")
                continue
            try:
                os.rename(src, dst)
            except OSError as exc:
                errors.append(f"{new_name} → {original}: {exc}")
        return errors

    # ------------------------------------------------------------------ #
    def summary_label(self) -> str:
        """Short human-readable string for the history list widget."""
        folder = Path(self.directory).name or self.directory
        preview = f"  ·  preview: {self.preview_path}" if self.preview_path else ""
        return f"{self.timestamp}  ·  {len(self.renames)} file(s)  ·  …/{folder}{preview}"


class HistoryManager:
    """
    Linear undo stack with a fixed capacity.

    ``push`` discards any forward (re-done) history, matching the
    behaviour users expect from Ctrl-Z in standard editors.
    """

    def __init__(self, max_entries: int = MAX_HISTORY) -> None:
        self._stack: list[HistoryEntry] = []
        self._pos:   int                = -1
        self._max:   int                = max_entries

    # ------------------------------------------------------------------ #
    def push(self, entry: HistoryEntry) -> None:
        """Commit a new entry, trimming the stack to capacity."""
        # Drop any forward history
        self._stack = self._stack[: self._pos + 1]
        self._stack.append(entry)
        # Trim oldest if over capacity
        if len(self._stack) > self._max:
            self._stack.pop(0)
        self._pos = len(self._stack) - 1

    # ------------------------------------------------------------------ #
    def can_undo(self) -> bool:
        return self._pos >= 0

    def undo(self) -> HistoryEntry | None:
        """Pop the most recent entry off the undo stack (does not call entry.undo())."""
        if not self.can_undo():
            return None
        entry      = self._stack[self._pos]
        self._pos -= 1
        return entry

    # ------------------------------------------------------------------ #
    def visible_entries(self) -> list[HistoryEntry]:
        """Return entries in newest-first order for display."""
        return list(reversed(self._stack[: self._pos + 1]))

    def clear(self) -> None:
        self._stack.clear()
        self._pos = -1
