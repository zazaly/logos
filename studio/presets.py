"""
studio.presets
===========
Load / save / delete named rename-rule presets as JSON.

The preset file lives in the Qt settings directory so it follows the
OS convention (AppData on Windows, ~/.config on Linux, ~/Library on macOS).
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QSettings


class PresetManager:
    """
    Persist params dicts under human-readable names.

    All public methods are safe to call even if the backing file is
    absent or corrupt — they will silently start fresh.
    """

    def __init__(self) -> None:
        # Resolve config directory the same way Qt does
        cfg_file = QSettings("BRU", "BulkRenameUtility").fileName()
        cfg_dir  = Path(cfg_file).parent
        cfg_dir.mkdir(parents=True, exist_ok=True)
        self._path: Path           = cfg_dir / "presets.json"
        self._data: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text("utf-8"))
            except Exception:
                self._data = {}

    def _flush(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False), "utf-8"
            )
        except OSError:
            pass  # read-only filesystem etc. — silently ignore

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def names(self) -> list[str]:
        """Return preset names sorted alphabetically."""
        return sorted(self._data.keys())

    def load(self, name: str) -> dict | None:
        """Return a deep copy of the stored params, or None if not found."""
        data = self._data.get(name)
        return deepcopy(data) if data is not None else None

    def save(self, name: str, params: dict) -> None:
        """Persist *params* under *name*, overwriting if already present."""
        self._data[name] = deepcopy(params)
        self._flush()

    def delete(self, name: str) -> bool:
        """Remove *name*.  Returns True if it existed."""
        existed = name in self._data
        if existed:
            del self._data[name]
            self._flush()
        return existed

    def rename_preset(self, old: str, new: str) -> bool:
        """Rename a preset key. Returns False if *old* does not exist."""
        if old not in self._data or not new.strip():
            return False
        self._data[new] = self._data.pop(old)
        self._flush()
        return True

    def __len__(self) -> int:
        return len(self._data)
