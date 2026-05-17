"""
sidecar.py — Generate .cover.jpg and .metadata.json sidecar files.

Both functions now accept an optional output_dir; if omitted they write
next to the original archive (legacy behaviour).
"""
from __future__ import annotations

import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def generate_cover(
    extract_dir: Path,
    original_archive: Path,
    max_width: int = 600,
    quality: int = 85,
    output_dir: Path | None = None,
) -> Path:
    """
    Extract first image from extract_dir and save as a JPEG cover.
    Output filename: <archive_stem>.cover.jpg
    If output_dir is given, the file is placed there; otherwise next to the archive.
    Returns the output path.
    """
    from bru.comiceditor.archive import get_cover_image

    dest = output_dir if output_dir is not None else original_archive.parent
    out_path = dest / f"{original_archive.stem}.cover.jpg"

    cover_src = get_cover_image(extract_dir)
    if cover_src is None:
        _make_placeholder(original_archive.stem, out_path)
        return out_path

    try:
        img = Image.open(cover_src).convert("RGB")
        if img.width > max_width:
            ratio = max_width / img.width
            img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
        img.save(out_path, "JPEG", quality=quality)
    except Exception:
        _make_placeholder(original_archive.stem, out_path)

    return out_path


def _make_placeholder(title: str, out_path: Path):
    """Gray placeholder with the title centred."""
    w, h = 400, 600
    img = Image.new("RGB", (w, h), color=(70, 70, 85))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20
        )
    except Exception:
        try:
            # Windows fallback
            import os
            win_font = os.path.join(
                os.environ.get("WINDIR", "C:\\Windows"),
                "Fonts", "arial.ttf"
            )
            font = ImageFont.truetype(win_font, 20)
        except Exception:
            font = ImageFont.load_default()

    # Simple word-wrap
    words = title.replace("_", " ").split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] < w - 40:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    text_block = "\n".join(lines)
    bbox = draw.textbbox((0, 0), text_block, font=font)
    x = (w - (bbox[2] - bbox[0])) / 2
    y = (h - (bbox[3] - bbox[1])) / 2
    draw.multiline_text((x, y), text_block, fill=(210, 210, 225),
                        font=font, align="center")
    img.save(out_path, "JPEG", quality=85)


def generate_metadata_json(
    metadata: dict,
    original_archive: Path,
    output_dir: Path | None = None,
) -> Path:
    """
    Write a flat JSON sidecar.
    Output filename: <archive_stem>.metadata.json
    If output_dir is given, the file is placed there; otherwise next to the archive.
    Returns the output path.
    """
    dest = output_dir if output_dir is not None else original_archive.parent
    out_path = dest / f"{original_archive.stem}.metadata.json"

    from bru.comiceditor.comicxml import FIELDS
    json_data: dict = {}
    for tag, _, _, ftype in FIELDS:
        val = metadata.get(tag, "")
        if ftype == "bool":
            if val.lower() in ("yes", "true", "1"):
                json_data[tag] = True
            elif val.lower() in ("no", "false", "0"):
                json_data[tag] = False
            else:
                json_data[tag] = None
        elif ftype == "number":
            try:
                json_data[tag] = int(val) if val else None
            except (ValueError, TypeError):
                json_data[tag] = val or None
        else:
            json_data[tag] = val if val else None

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    return out_path


def generate_csv_report(all_metadata: dict[str, dict], output_path: Path):
    """
    Write a CSV summary — one row per metadata field, one column per file.
    Header row: Field, file1.cbz, file2.cbz, …
    """
    import csv
    from bru.comiceditor.comicxml import FIELD_TAGS

    filenames = list(all_metadata.keys())
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Field"] + filenames)
        for tag in FIELD_TAGS:
            row = [tag] + [all_metadata[fn].get(tag, "") for fn in filenames]
            writer.writerow(row)
