"""
worker.py — Background QThread workers for extraction and repackaging.
"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QThread, Signal


class ExtractionWorker(QThread):
    """Extracts a single archive in a background thread."""
    progress = Signal(float)          # 0.0–1.0
    finished = Signal(bool, str)      # success, error_message

    def __init__(self, archive_path: Path, extract_dir: Path):
        super().__init__()
        self.archive_path = archive_path
        self.extract_dir = extract_dir

    def run(self):
        from studio.metadata_archive import extract_archive
        success, error = extract_archive(
            self.archive_path, self.extract_dir,
            progress_callback=lambda f: self.progress.emit(f)
        )
        self.finished.emit(success, error)


class RepackageWorker(QThread):
    """Repackages a single archive in a background thread."""
    file_progress = Signal(str, float)   # filename, 0.0–1.0
    file_done = Signal(str, bool, str)   # filename, success, error
    all_done = Signal()

    def __init__(self, tasks: list[tuple]):
        """tasks: list of (extract_dir, original_path, output_path)"""
        super().__init__()
        self.tasks = tasks

    def run(self):
        from studio.metadata_archive import repackage_archive
        for extract_dir, original_path, output_path in self.tasks:
            fname = original_path.name

            def cb(f, _fname=fname):
                self.file_progress.emit(_fname, f)

            success, error = repackage_archive(
                extract_dir, original_path, output_path,
                progress_callback=cb
            )
            self.file_done.emit(fname, success, error)
        self.all_done.emit()
