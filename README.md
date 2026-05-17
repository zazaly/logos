# Bulk Rename Utility  v3

A production-quality desktop bulk-rename tool built with **Python 3.11+ and PySide6**.

---

## Quick Start

```bash
# 1. Clone / unzip the project
# 2. Install
pip install -e ".[dev]"

# 3. Run the GUI
python -m bru
# or, after install:
bru
```

---

## Package Layout

```
bulk_rename_v3/
├── bru/
│   ├── __init__.py        version constant
│   ├── __main__.py        entry-point  (python -m bru)
│   ├── engine.py          RenameEngine — pure stateless pipeline
│   ├── history.py         HistoryManager + HistoryEntry  (undo/redo)
│   ├── main_window.py     MainWindow  (all UI, no business logic)
│   ├── metadata.py        MetadataExtractor  (Pillow / lxml / pdfplumber)
│   ├── presets.py         PresetManager  (JSON persistence)
│   ├── theme.py           Dark palette + QSS stylesheet builder
│   └── widgets.py         Reusable widgets: FileTable, HistoryPanel, etc.
├── tests/
│   ├── conftest.py        Shared fixtures (sample_dir, engine, presets…)
│   ├── test_engine.py     64 unit tests  — one per transformation branch
│   └── test_integration.py  22 integration tests — filesystem + pipelines
├── pyproject.toml
└── README.md
```

---

## Transformation Pipeline

Steps are applied in this fixed order for every file:

| # | Step | Key params |
|---|------|-----------|
| 1 | **Name** | `name_mode` (Keep / Remove / Fixed / Reverse) |
| 2 | **RegEx** | `regex_match`, `regex_replace`, `regex_inc_ext`, `regex_simple` |
| 3 | **Replace** | `replace_find`, `replace_with`, `replace_match_case`, `replace_first_only` |
| 4 | **Remove** | `remove_first_n/last_n`, range `from/to`, digits/symbols/accents/brackets/trim |
| 5 | **Move/Copy** | `mcp_mode`, `mcp_from`, `mcp_length`, `mcp_to`, `mcp_sep` |
| 6 | **Add** | `add_prefix`, `add_insert` at pos, `add_suffix`, `add_word_space` + **{tokens}** |
| 7 | **Auto Date** | `date_mode`, `date_type`, `date_fmt`, `date_sep` |
| 8 | **Numbering** | `num_mode`, `num_start/incr/pad/break`, Decimal / Alpha / Roman |
| 9 | **Case** | `case_mode` + `case_exceptions` |
|10 | **Extension** | `ext_mode` (Same / Lower / Upper / Fixed / Remove) |

---

## Token Substitution  (Add group)

Type `{token}` in any **Prefix**, **Insert**, or **Suffix** field:

| Token | Source | Example value |
|-------|--------|---------------|
| `{n}` | row index 1-based | `1`, `2`, `3` … |
| `{n0}` | row index 0-based | `0`, `1`, `2` … |
| `{file_mtime}` | filesystem | `2024-05-16` |
| `{file_size}` | filesystem | `1048576` |
| `{comic_series}` | CBZ ComicInfo.xml | `Claymore` |
| `{comic_volume}` | CBZ ComicInfo.xml | `01` |
| `{comic_number}` | CBZ ComicInfo.xml | `1` |
| `{pdf_title}` | PDF metadata | `Annual Report` |
| `{pdf_author}` | PDF metadata | `Jane Smith` |
| `{exif_make}` | JPEG EXIF | `Canon` |
| `{exif_model}` | JPEG EXIF | `EOS R5` |
| `{exif_datetimeoriginal}` | JPEG EXIF | `2024:03:15 10:30:00` |

Unknown tokens are left as-is (no error).

---

## Numbering Bases

| Base | Example output |
|------|---------------|
| Decimal | `1  2  3 … 10 11` |
| Alpha   | `a  b  c … z  aa ab` |
| Roman   | `i  ii iii … x  xi` |

---

## UI Features

| Feature | Detail |
|---------|--------|
| **Live preview** | 150 ms debounce — every control change updates the New Name column instantly |
| **Per-row enable** | Checkbox in column 0; disabled rows are skipped but still shown |
| **Drag-to-reorder** | Drag rows in the file table to change processing order (affects `{n}` numbering) |
| **Selection controls** | All / None / Invert buttons + right-click context menu |
| **Auto-dedup** | On conflict, appends `_(2)`, `_(3)` … instead of failing |
| **Undo** | Full batch undo via Ctrl-Z or the Undo button; history sidebar shows all batches |
| **Presets** | Save, load, rename, delete named rule presets (JSON in Qt config dir) |
| **Filters** | Glob mask, show/hide files/folders/hidden, min/max name length |
| **Progress bar** | Shown automatically for folders with > 500 files |
| **Inline RegEx error** | Red border + error text appears immediately on bad patterns |

---

## Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/test_engine.py -v

# Integration tests only
pytest tests/test_integration.py -v

# With coverage
pytest --cov=bru --cov-report=term-missing
```

Current: **86 tests, 86 pass, 0 skip, 0 fail**.

---

## Optional Dependencies

All three are soft dependencies — the app runs without them; metadata tokens
simply return empty strings.

| Library | Feature unlocked |
|---------|-----------------|
| `Pillow>=10` | `{exif_*}`, `{img_width/height}` tokens for JPEG/PNG/TIFF |
| `lxml>=5`   | `{comic_*}` tokens from CBZ `ComicInfo.xml` |
| `pdfplumber>=0.10` | `{pdf_*}` tokens from PDF metadata |
