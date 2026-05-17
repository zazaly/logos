from __future__ import annotations

import os
import shutil
import zipfile
import tarfile
from pathlib import Path

try:
    import rarfile
    HAS_RAR = True
except ImportError:
    HAS_RAR = False

try:
    import py7zr
    HAS_7Z = True
except ImportError:
    HAS_7Z = False

SUPPORTED_EXTENSIONS = {".cbz", ".cbr", ".cb7", ".cbt", ".pdf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"}

_MAGIC = {
    b"\x50\x4B\x03\x04": "zip",
    b"\x50\x4B\x05\x06": "zip",
    b"\x52\x61\x72\x21\x1A\x07\x00": "rar",
    b"\x52\x61\x72\x21\x1A\x07\x01": "rar",
    b"\x37\x7A\xBC\xAF\x27\x1C": "7z",
    b"\x1F\x8B": "gz",
    b"\x42\x5A\x68": "bz2",
}

def _detect_format(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            header = f.read(16)
        for magic, fmt in _MAGIC.items():
            if header[:len(magic)] == magic:
                return fmt
    except Exception:
        pass
    return path.suffix.lower().lstrip(".")


def is_comic_file(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def scan_folder(folder: Path, recursive: bool = False) -> list[Path]:
    if recursive:
        files = [p for p in folder.rglob("*") if p.is_file() and is_comic_file(p)]
    else:
        files = [p for p in folder.iterdir() if p.is_file() and is_comic_file(p)]
    return sorted(files)


def get_temp_dir(source_folder: Path) -> Path:
    return source_folder / ".metadata_tmp"


def get_extract_dir(source_folder: Path, archive_path: Path) -> Path:
    tmp = get_temp_dir(source_folder)
    base = archive_path.stem.strip()  # strip trailing spaces: Windows mkdir strips them silently
    candidate = tmp / base
    counter = 2
    while candidate.exists() and not _is_our_extract(candidate, archive_path):
        candidate = tmp / f"{base}_{counter}"
        counter += 1
    return candidate


def _is_our_extract(folder: Path, archive_path: Path) -> bool:
    marker = folder / ".source_archive"
    if marker.exists():
        return marker.read_text(encoding="utf-8").strip() == str(archive_path)
    if folder.exists():
        return any(
            p.suffix.lower() in IMAGE_EXTENSIONS
            for p in folder.rglob("*") if p.is_file()
        )
    return False


def write_marker(extract_dir: Path, archive_path: Path):
    (extract_dir / ".source_archive").write_text(str(archive_path), encoding="utf-8")


def extract_archive(archive_path: Path, extract_dir: Path,
                    progress_callback=None) -> tuple[bool, str]:
    extract_dir.mkdir(parents=True, exist_ok=True)
    fmt = _detect_format(archive_path)
    try:
        if fmt == "zip":
            _extract_zip(archive_path, extract_dir, progress_callback)
        elif fmt == "rar":
            if not HAS_RAR:
                return False, "rarfile library not available"
            _extract_rar(archive_path, extract_dir, progress_callback)
        elif fmt == "7z":
            if not HAS_7Z:
                return False, "py7zr library not available"
            _extract_7z(archive_path, extract_dir, progress_callback)
        elif fmt in ("gz", "bz2") or archive_path.suffix.lower() == ".cbt":
            _extract_tar(archive_path, extract_dir, progress_callback)
        elif archive_path.suffix.lower() == ".pdf":
            _extract_pdf(archive_path, extract_dir, progress_callback)
        else:
            return False, f"Unrecognised format (magic={fmt}, ext={archive_path.suffix})"
        write_marker(extract_dir, archive_path)
        return True, ""
    except Exception as e:
        return False, str(e)


def _safe_extract_member(data: bytes, filename: str, dest: Path):
    name = Path(filename).name
    if not name or name.startswith("."):
        return
    dest.mkdir(parents=True, exist_ok=True)
    (dest / name).write_bytes(data)


def _extract_zip(archive_path: Path, dest: Path, cb):
    with zipfile.ZipFile(archive_path, "r") as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        total = max(len(members), 1)
        for i, info in enumerate(members):
            if Path(info.filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
                _safe_extract_member(zf.read(info.filename), info.filename, dest)
            if cb:
                cb((i + 1) / total)


def _extract_rar(archive_path: Path, dest: Path, cb):
    with rarfile.RarFile(archive_path, "r") as rf:
        members = [m for m in rf.infolist() if not m.is_dir()]
        total = max(len(members), 1)
        for i, info in enumerate(members):
            if Path(info.filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
                _safe_extract_member(rf.read(info.filename), info.filename, dest)
            if cb:
                cb((i + 1) / total)


def _extract_7z(archive_path: Path, dest: Path, cb):
    with py7zr.SevenZipFile(archive_path, "r") as zf:
        all_files = {n: d for n, d in zf.read().items() if d is not None}
    total = max(len(all_files), 1)
    for i, (name, data) in enumerate(all_files.items()):
        if Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS:
            raw = data.read() if hasattr(data, "read") else data
            _safe_extract_member(raw, name, dest)
        if cb:
            cb((i + 1) / total)


def _extract_tar(archive_path: Path, dest: Path, cb):
    with tarfile.open(archive_path, "r:*") as tf:
        members = [m for m in tf.getmembers() if m.isfile()]
        total = max(len(members), 1)
        for i, member in enumerate(members):
            if Path(member.name).suffix.lower() not in SUPPORTED_EXTENSIONS:
                f = tf.extractfile(member)
                if f:
                    _safe_extract_member(f.read(), member.name, dest)
            if cb:
                cb((i + 1) / total)


def _extract_pdf(archive_path: Path, dest: Path, cb):
    try:
        import pdfplumber
        with pdfplumber.open(archive_path) as pdf:
            total = max(len(pdf.pages), 1)
            for i, page in enumerate(pdf.pages):
                page.to_image(resolution=150).original.save(
                    dest / f"page_{i+1:04d}.jpg", "JPEG", quality=85)
                if cb:
                    cb((i + 1) / total)
    except Exception as e:
        raise RuntimeError(f"PDF extraction failed: {e}") from e


def get_image_files(extract_dir: Path) -> list[Path]:
    return sorted(
        p for p in extract_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def count_pages(extract_dir: Path) -> int:
    return len(get_image_files(extract_dir))


def get_cover_image(extract_dir: Path) -> Path | None:
    imgs = get_image_files(extract_dir)
    return imgs[0] if imgs else None


def repackage_archive(extract_dir: Path, original_path: Path,
                      output_path: Path, progress_callback=None) -> tuple[bool, str]:
    ext = original_path.suffix.lower()
    out_ext = ".cbz" if ext == ".cbr" else ext
    actual_output = output_path.with_suffix(out_ext)
    try:
        if out_ext == ".cbz":
            _repackage_zip(extract_dir, actual_output, progress_callback)
        elif out_ext == ".cb7":
            if not HAS_7Z:
                return False, "py7zr not available"
            _repackage_7z(extract_dir, actual_output, progress_callback)
        elif out_ext == ".cbt":
            _repackage_tar(extract_dir, actual_output, progress_callback)
        else:
            _repackage_zip(extract_dir, actual_output.with_suffix(".cbz"), progress_callback)
        return True, ""
    except Exception as e:
        return False, str(e)


def _repackage_zip(src: Path, dest: Path, cb):
    files = [p for p in sorted(src.rglob("*"))
             if p.is_file() and not p.name.startswith(".")]
    total = max(len(files), 1)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, f in enumerate(files):
            zf.write(f, f.relative_to(src))
            if cb:
                cb((i + 1) / total)


def _repackage_7z(src: Path, dest: Path, cb):
    files = [p for p in sorted(src.rglob("*"))
             if p.is_file() and not p.name.startswith(".")]
    with py7zr.SevenZipFile(dest, "w") as zf:
        for f in files:
            zf.write(f, str(f.relative_to(src)))
    if cb:
        cb(1.0)


def _repackage_tar(src: Path, dest: Path, cb):
    files = [p for p in sorted(src.rglob("*"))
             if p.is_file() and not p.name.startswith(".")]
    total = max(len(files), 1)
    with tarfile.open(dest, "w:gz") as tf:
        for i, f in enumerate(files):
            tf.add(f, arcname=str(f.relative_to(src)))
            if cb:
                cb((i + 1) / total)
