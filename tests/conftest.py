"""
conftest.py
===========
Shared pytest fixtures for the studio test suite.

Fixtures
--------
sample_dir      tmp_path populated with a realistic set of dummy files.
engine          A clean RenameEngine instance.
preset_manager  A PresetManager backed by a temp directory (no QSettings).
history_manager A fresh HistoryManager.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from studio.engine  import RenameEngine
from studio.history import HistoryManager


# ── sample directory ──────────────────────────────────────────────────────── #

SAMPLE_FILES = [
    # Comic volumes
    "Claymore, Vol.01 - Norihiro Yagi.cbz",
    "Claymore, Vol.02 - Norihiro Yagi.cbz",
    "Claymore, Vol.03 - Norihiro Yagi.cbz",
    # Images
    "DSC_0001.JPG",
    "DSC_0002.JPG",
    "photo with spaces.png",
    # Documents
    "report 2024.pdf",
    "README.txt",
    # Tricky names
    "...dotfile.md",
    "file (copy).docx",
    "résumé.pdf",
    "UPPERCASE_NAME.TXT",
    "mixed-Case_File.Mp3",
]


@pytest.fixture
def sample_dir(tmp_path: Path) -> Path:
    """Return a tmp_path populated with zero-byte dummy files."""
    for name in SAMPLE_FILES:
        (tmp_path / name).touch()
    return tmp_path


# ── engine ────────────────────────────────────────────────────────────────── #

@pytest.fixture
def engine() -> RenameEngine:
    return RenameEngine()


# ── history manager ───────────────────────────────────────────────────────── #

@pytest.fixture
def history_manager() -> HistoryManager:
    return HistoryManager()


# ── preset manager backed by tmp dir ─────────────────────────────────────── #

@pytest.fixture
def preset_manager(tmp_path: Path):
    """
    A PresetManager that writes to tmp_path instead of the real Qt config dir.
    Uses a thin subclass so no QSettings is needed.
    """
    from studio.presets import PresetManager

    class _IsolatedPM(PresetManager):
        def __init__(self, path: Path):
            import json
            self._path: Path            = path / "presets.json"
            self._data: dict[str, dict] = {}
            self._load()

    return _IsolatedPM(tmp_path)
