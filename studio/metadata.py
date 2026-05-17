"""
studio.metadata
============
Extract rename-relevant metadata from files.

The public surface is a single class:

    extractor = MetadataExtractor()
    meta: dict[str, str] = extractor.extract(Path("file.cbz"))

Returned dict keys (all values are plain strings):

  General
    file_mtime      modification date  YYYY-MM-DD
    file_ctime      creation/inode-change date  YYYY-MM-DD
    file_size       byte size as decimal string

  Images  (.jpg .jpeg .png .tiff .webp)  — requires Pillow
    img_width, img_height, img_mode
    exif_datetimeoriginal, exif_make, exif_model, exif_artist

  CBZ / ZIP with ComicInfo.xml  — requires lxml
    comic_series, comic_volume, comic_number, comic_year,
    comic_writer,  comic_publisher, comic_title

  PDF  — requires pdfplumber
    pdf_title, pdf_author, pdf_subject, pdf_creator

  Generic XML  — requires lxml
    xml_root   (local name of root element)
"""
from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

# ── Optional heavy dependencies ───────────────────────────────────────────── #
try:
    from PIL import Image as _PilImage
    from PIL.ExifTags import TAGS as _EXIF_TAGS
    _HAS_PIL = True
except ImportError:
    _PilImage = None   # type: ignore
    _HAS_PIL  = False

try:
    from lxml import etree as _lxml
    _HAS_LXML = True
except ImportError:
    _lxml    = None    # type: ignore
    _HAS_LXML = False

try:
    import pdfplumber as _pdfplumber
    _HAS_PDF = True
except ImportError:
    _pdfplumber = None # type: ignore
    _HAS_PDF    = False

# ── Capability flags (importable by UI to show/hide tooltips) ─────────────── #
HAS_PIL  = _HAS_PIL
HAS_LXML = _HAS_LXML
HAS_PDF  = _HAS_PDF


class MetadataExtractor:
    """Thread-safe, stateless extractor.  All methods return ``dict[str, str]``."""

    # ------------------------------------------------------------------ #
    def extract(self, filepath: Path) -> dict[str, str]:
        """
        Return a flat ``{token: value}`` dict for *filepath*.
        Never raises; errors are silently swallowed and missing fields
        simply absent from the result.
        """
        meta: dict[str, str] = {}

        # ── Basic filesystem stats ──────────────────────────────────── #
        try:
            stat = filepath.stat()
            meta["file_mtime"] = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
            meta["file_ctime"] = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d")
            meta["file_size"]  = str(stat.st_size)
        except OSError:
            pass

        # ── Format-specific extraction ──────────────────────────────── #
        suffix = filepath.suffix.lower()
        dispatch = {
            ".jpg":  self._image_meta,
            ".jpeg": self._image_meta,
            ".png":  self._image_meta,
            ".tiff": self._image_meta,
            ".tif":  self._image_meta,
            ".webp": self._image_meta,
            ".cbz":  self._cbz_meta,
            ".zip":  self._cbz_meta,
            ".pdf":  self._pdf_meta,
            ".xml":  self._xml_meta,
        }
        handler = dispatch.get(suffix)
        if handler:
            try:
                meta.update(handler(filepath))
            except Exception:
                pass   # never let metadata extraction crash the UI

        return meta

    # ------------------------------------------------------------------ #
    # Image  (Pillow)
    # ------------------------------------------------------------------ #
    def _image_meta(self, p: Path) -> dict[str, str]:
        if not _HAS_PIL:
            return {}
        result: dict[str, str] = {}
        try:
            img = _PilImage.open(p)
            result.update({
                "img_width":  str(img.width),
                "img_height": str(img.height),
                "img_mode":   img.mode,
            })
            # EXIF (JPEG / TIFF)
            get_exif = getattr(img, "_getexif", None)
            if get_exif:
                exif_data = get_exif() or {}
                _WANT = {"DateTimeOriginal", "Make", "Model", "Artist",
                         "LensModel", "Software"}
                for tag_id, value in exif_data.items():
                    tag = _EXIF_TAGS.get(tag_id, "")
                    if tag in _WANT:
                        result[f"exif_{tag.lower()}"] = str(value).strip()
        except Exception:
            pass
        return result

    # ------------------------------------------------------------------ #
    # CBZ / ZIP  (lxml for ComicInfo.xml)
    # ------------------------------------------------------------------ #
    def _cbz_meta(self, p: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        try:
            with zipfile.ZipFile(p, "r") as zf:
                names_lower = [n.lower() for n in zf.namelist()]
                if "comicinfo.xml" in names_lower:
                    idx  = names_lower.index("comicinfo.xml")
                    data = zf.read(zf.namelist()[idx])
                    result.update(self._parse_comicinfo(data))
        except Exception:
            pass
        return result

    def _parse_comicinfo(self, xml_bytes: bytes) -> dict[str, str]:
        if not _HAS_LXML:
            return {}
        result: dict[str, str] = {}
        try:
            root = _lxml.fromstring(xml_bytes)
            for tag in ("Series", "Volume", "Number", "Year",
                        "Writer", "Publisher", "Title", "Genre",
                        "LanguageISO", "Count"):
                el = root.find(tag)
                if el is not None and el.text:
                    result[f"comic_{tag.lower()}"] = el.text.strip()
        except Exception:
            pass
        return result

    # ------------------------------------------------------------------ #
    # PDF  (pdfplumber)
    # ------------------------------------------------------------------ #
    def _pdf_meta(self, p: Path) -> dict[str, str]:
        if not _HAS_PDF:
            return {}
        result: dict[str, str] = {}
        try:
            with _pdfplumber.open(p) as pdf:
                meta = pdf.metadata or {}
                for k in ("Title", "Author", "Subject", "Creator", "Producer"):
                    val = meta.get(k) or meta.get(f"/{k}")
                    if val:
                        result[f"pdf_{k.lower()}"] = str(val).strip()
                # Page count is useful for numbering
                result["pdf_pages"] = str(len(pdf.pages))
        except Exception:
            pass
        return result

    # ------------------------------------------------------------------ #
    # Generic XML  (lxml)
    # ------------------------------------------------------------------ #
    def _xml_meta(self, p: Path) -> dict[str, str]:
        if not _HAS_LXML:
            return {}
        result: dict[str, str] = {}
        try:
            tree = _lxml.parse(str(p))
            root = tree.getroot()
            tag  = root.tag
            result["xml_root"] = tag.split("}")[-1] if "}" in tag else tag
            # Try a few common child text elements
            for child_tag in ("title", "name", "Title", "Name"):
                el = root.find(child_tag)
                if el is not None and el.text:
                    result["xml_first_text"] = el.text.strip()
                    break
        except Exception:
            pass
        return result
