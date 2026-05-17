"""
main.py — Entry point for Comic Bulk Metadata Editor.
Usage: python main.py

Handles PySide6 path resolution on Python 3.12+ / Windows automatically.
"""

from __future__ import annotations
import sys
import os
import subprocess


def _fix_pyside6_path() -> bool:
    """
    On some Python installs (especially 3.13/3.14 on Windows), PySide6 is
    installed but its DLLs aren't on PATH, or the package root isn't on
    sys.path.  We try three escalating fixes before giving up.
    """
    # Already importable — nothing to do.
    try:
        import PySide6  # noqa: F401
        return True
    except ModuleNotFoundError:
        pass

    # Fix 1: ask pip where site-packages is and add it manually.
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "PySide6"],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if line.startswith("Location:"):
                location = line.split(":", 1)[1].strip()
                if location not in sys.path:
                    sys.path.insert(0, location)
                try:
                    import PySide6  # noqa: F401
                    return True
                except ModuleNotFoundError:
                    pass
    except Exception:
        pass

    # Fix 2: walk common Windows site-packages locations.
    base = os.path.dirname(sys.executable)
    candidates = [
        os.path.join(base, "Lib", "site-packages"),
        os.path.join(base, "..", "Lib", "site-packages"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python",
                     f"Python{sys.version_info.major}{sys.version_info.minor}",
                     "Lib", "site-packages"),
    ]
    for candidate in candidates:
        candidate = os.path.normpath(candidate)
        if os.path.isdir(candidate) and candidate not in sys.path:
            sys.path.insert(0, candidate)
            try:
                import PySide6  # noqa: F401
                return True
            except ModuleNotFoundError:
                continue

    return False


def _check_dependencies() -> list[str]:
    """Return list of missing package names."""
    missing = []
    for pkg, import_name in [
        ("PySide6", "PySide6"),
        ("rarfile", "rarfile"),
        ("py7zr", "py7zr"),
        ("Pillow", "PIL"),
        ("lxml", "lxml"),
        ("pdfplumber", "pdfplumber"),
    ]:
        try:
            __import__(import_name)
        except ModuleNotFoundError:
            missing.append(pkg)
    return missing


def main():
    _fix_pyside6_path()

    missing = _check_dependencies()
    if missing:
        print("=" * 60)
        print("ERROR: Missing required packages:")
        for pkg in missing:
            print(f"  • {pkg}")
        print()
        print("Fix: run this command, then try again:")
        print(f"  {sys.executable} -m pip install " + " ".join(missing))
        print("=" * 60)
        sys.exit(1)

    # All good — import and launch.
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from comiceditor.ui import MainWindow

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Comic Bulk Metadata Editor")
    app.setOrganizationName("ComicEditor")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
