"""
comicxml.py — ComicInfo.xml read, write, and schema definition.
"""
from __future__ import annotations

from pathlib import Path
from lxml import etree

COMICINFO_FILENAME = "ComicInfo.xml"
COMICINFO_BAK_FILENAME = "ComicInfo.xml.bak"

# Field definitions: (xml_tag, section, display_label, field_type)
# field_type: "text" | "number" | "bool" | "dropdown" | "longtext"
FIELDS = [
    # --- General Information ---
    ("Title",           "General Information",   "Title",              "text"),
    ("Subtitle",        "General Information",   "Subtitle",           "text"),
    ("LanguageISO",     "General Information",   "Language",           "text"),
    ("Writer",          "General Information",   "Authors",            "text"),
    ("Publisher",       "General Information",   "Publisher",          "text"),
    ("Date",            "General Information",   "Publish Date",       "text"),
    ("Genre",           "General Information",   "Genre",              "text"),
    ("Moods",           "General Information",   "Moods",              "text"),
    ("Tags",            "General Information",   "Tags",               "text"),
    ("Series",          "General Information",   "Series Name",        "text"),
    ("Number",          "General Information",   "Series #",           "number"),
    ("SeriesTotal",     "General Information",   "Series Total",       "number"),
    ("CommunityRating", "General Information",   "Public Reviews",     "text"),
    ("ISBN10",          "General Information",   "ISBN 10",            "text"),
    ("ISBN13",          "General Information",   "ISBN 13",            "text"),
    ("AgeRating",       "General Information",   "Age Rating",         "dropdown"),
    ("ContentRating",   "General Information",   "Content Rating",     "dropdown"),
    ("PageCount",       "General Information",   "Pages",              "number"),

    # --- Comic Book Details ---
    ("Issue",           "Comic Book Details",    "Issue #",            "number"),
    ("Volume",          "Comic Book Details",    "Volume",             "text"),
    ("VolumeNumber",    "Comic Book Details",    "Volume #",           "number"),
    ("StoryArc",        "Comic Book Details",    "Story Arc",          "text"),
    ("ArcNumber",       "Comic Book Details",    "Arc #",              "number"),
    ("AlternateSeries", "Comic Book Details",    "Alt. Series",        "text"),
    ("AlternateNumber", "Comic Book Details",    "Alt. Issue",         "text"),
    ("Imprint",         "Comic Book Details",    "Imprint",            "text"),
    ("Format",          "Comic Book Details",    "Format",             "text"),
    ("ReadingDirection","Comic Book Details",    "Reading Direction",  "dropdown"),
    ("Web",             "Comic Book Details",    "Web Link",           "text"),
    ("BlackAndWhite",   "Comic Book Details",    "Black & White",      "bool"),
    ("Manga",           "Comic Book Details",    "Manga",              "bool"),
    ("Penciller",       "Comic Book Details",    "Pencilers",          "text"),
    ("Inker",           "Comic Book Details",    "Inkers",             "text"),
    ("Colorist",        "Comic Book Details",    "Colorist",           "text"),
    ("Letterer",        "Comic Book Details",    "Letterers",          "text"),
    ("CoverArtist",     "Comic Book Details",    "Cover Artists",      "text"),
    ("Editor",          "Comic Book Details",    "Editors",            "text"),
    ("Characters",      "Comic Book Details",    "Characters",         "text"),
    ("Teams",           "Comic Book Details",    "Teams",              "text"),
    ("Locations",       "Comic Book Details",    "Locations",          "text"),
    ("Notes",           "Comic Book Details",    "Notes",              "longtext"),

    # --- Provider Metadata ---
    ("AmazonASIN",      "Provider Metadata",     "Amazon ASIN",        "text"),
    ("Amazon",          "Provider Metadata",     "Amazon",             "text"),
    ("AmazonNumber",    "Provider Metadata",     "Amazon #",           "text"),
    ("GoogleBooksID",   "Provider Metadata",     "Google Books ID",    "text"),
    ("GoodreadsID",     "Provider Metadata",     "Goodreads ID",       "text"),
    ("Goodreads",       "Provider Metadata",     "Goodreads",          "text"),
    ("GoodreadsNumber", "Provider Metadata",     "Goodreads #",        "text"),
    ("HardcoverID",     "Provider Metadata",     "Hardcover ID",       "text"),
    ("HardcoverBookID", "Provider Metadata",     "Hardcover Book ID",  "text"),
    ("Hardcover",       "Provider Metadata",     "Hardcover",          "text"),
    ("HardcoverNumber", "Provider Metadata",     "Hardcover #",        "text"),
    ("LubimyCzytacID",  "Provider Metadata",     "LubimyCzytac ID",    "text"),
    ("LubimyCzytac",    "Provider Metadata",     "LubimyCzytac",       "text"),
    ("ComicVineID",     "Provider Metadata",     "ComicVine ID",       "text"),
    ("RanobeDB",        "Provider Metadata",     "RanobeDB",           "text"),
    ("AudibleID",       "Provider Metadata",     "Audible ID",         "text"),
    ("Audible",         "Provider Metadata",     "Audible",            "text"),
    ("AudibleNumber",   "Provider Metadata",     "Audible #",          "text"),
    ("Description",     "Provider Metadata",     "Description",        "longtext"),
]

FIELD_TAGS = [f[0] for f in FIELDS]
SECTION_ORDER = ["General Information", "Comic Book Details", "Provider Metadata"]

AGE_RATING_VALUES = [
    "", "Unknown", "Adults Only 18+", "Early Childhood", "Everyone",
    "Everyone 10+", "G", "Kids to Adults", "M", "MA15+",
    "Mature 17+", "PG", "R18+", "Rating Pending", "Teen", "X18+"
]

CONTENT_RATING_VALUES = [
    "", "Everyone", "Teen", "Mature", "Adults Only", "Explicit"
]

READING_DIRECTION_VALUES = ["", "LTR", "RTL"]

DROPDOWN_OPTIONS = {
    "AgeRating": AGE_RATING_VALUES,
    "ContentRating": CONTENT_RATING_VALUES,
    "ReadingDirection": READING_DIRECTION_VALUES,
}

# Fields that auto-increment is meaningful for
AUTO_INCREMENT_FIELDS = {
    "Number", "Issue", "VolumeNumber", "ArcNumber", "SeriesTotal"
}


def empty_metadata() -> dict:
    """Return a dict with all fields set to empty string."""
    return {tag: "" for tag in FIELD_TAGS}


def read_comicinfo(xml_path: Path) -> dict:
    """Parse a ComicInfo.xml into a flat dict. Missing fields → empty string."""
    data = empty_metadata()
    if not xml_path.exists():
        return data
    try:
        tree = etree.parse(str(xml_path))
        root = tree.getroot()
        for tag in FIELD_TAGS:
            el = root.find(tag)
            if el is not None and el.text:
                data[tag] = el.text.strip()
    except Exception:
        pass
    return data


def write_comicinfo(xml_path: Path, data: dict):
    """Write all fields to ComicInfo.xml, preserving empty tags."""
    root = etree.Element("ComicInfo")
    root.set("{http://www.w3.org/2001/XMLSchema-instance}noNamespaceSchemaLocation",
             "ComicInfo.xsd")

    current_section = None
    for tag, section, label, _ in FIELDS:
        if section != current_section:
            current_section = section
            comment = etree.Comment(f" {section} ")
            root.append(comment)
        el = etree.SubElement(root, tag)
        val = data.get(tag, "")
        if val:
            el.text = str(val)

    tree = etree.ElementTree(root)
    etree.indent(tree, space="  ")
    with open(xml_path, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="utf-8"?>\n')
        tree.write(f, encoding="utf-8", xml_declaration=False, pretty_print=True)


def backup_comicinfo(extract_dir: Path):
    """Copy ComicInfo.xml → ComicInfo.xml.bak if it exists."""
    src = extract_dir / COMICINFO_FILENAME
    dst = extract_dir / COMICINFO_BAK_FILENAME
    if src.exists() and not dst.exists():
        import shutil
        shutil.copy2(src, dst)


def load_or_init_comicinfo(extract_dir: Path) -> dict:
    """
    After extraction: backup existing xml, then load (or init empty).
    Returns the metadata dict.
    """
    backup_comicinfo(extract_dir)
    xml_path = extract_dir / COMICINFO_FILENAME
    bak_path = extract_dir / COMICINFO_BAK_FILENAME
    # Read from backup if it exists (preserves original data)
    source = bak_path if bak_path.exists() else xml_path
    return read_comicinfo(source)
