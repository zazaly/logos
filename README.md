# Logos Studio

Logos Studio is a desktop-first, monolithic batch file renaming and archive metadata editing tool built with **PySide6**.

It combines:
- High-volume rename workflows (preview, regex, tokens, transforms, undo)
- Built-in metadata extraction and token expansion
- Spreadsheet-style archive metadata editing
- ComicInfo sidecar generation and archive repackaging workflows
- Theme customization via `.ron` palettes

## Quick Start

```bash
python -m studio
```

Windows launch helpers:
- `run.bat`
- `setup_and_run.bat`

## Project Structure

```text
.
├── studio/
│   ├── __main__.py
│   ├── main_window.py
│   ├── engine.py
│   ├── metadata.py
│   ├── history.py
│   ├── presets.py
│   ├── theme.py
│   ├── widgets.py
│   ├── metadata_ui.py
│   ├── metadata_archive.py
│   ├── metadata_comicxml.py
│   ├── metadata_sidecar.py
│   └── metadata_worker.py
├── tests/
├── themes/
└── pyproject.toml
```

## Core Features

### 1) Batch Rename Engine
- Token-driven naming (`{name}`, `{ext}`, date/time, metadata-backed fields)
- Chained transforms (case conversion, trimming, replace/regex rules)
- Drag/drop deterministic rule pipelines with named reusable pipeline presets
- Regex extraction and replacement with previews
- Collision-safe renaming with optional auto-dedup

### 2) Patch-Cable Rule Pipeline Editor
- Reorder rename groups on a VSTHost-inspired canvas without changing the file table workflow
- Save named reusable pipelines such as `Factory Default`, `Clean Then Number`, and custom variants
- The same deterministic pipeline order powers preview, rename, presets, and tests

### 3) Live Preview + History
- Debounced preview updates for responsive interaction
- Operation history stack with undo support
- Dry-run style visibility before file operations

### 4) Metadata-Aware Renaming
- Pull metadata from supported file types
- Use metadata directly in rename templates
- Caching to keep large folder operations fast

### 5) Archive Metadata Editor
- Table-based editing across multiple archives
- Row action buttons: `update`, `mirror`, `auto`, `clear`
- Auto-increment support for key metadata fields
- Background extraction and repackaging workers

### 6) Sidecar + Export Support
- Generate cover images
- Export `.metadata.json`
- Build CSV summary reports
- Update ComicInfo.xml in extracted package content

### 7) Theming
- Runtime-selectable themes from `themes/**/*.ron`
- Default theme preference set to **Windows 10 Light**

## Development

Install dependencies and run tests:

```bash
pip install -e .[dev]
pytest -q
```

## Configuration

The app persists user settings (theme, paths, window geometry, metadata action icon/text overrides, etc.) in a local JSON settings file managed by the app.

## Top 10 Recommendations to Take This Project to the Next Level

1. **Add a plugin architecture** for token providers, metadata parsers, and export backends.
2. **Create a job queue + session manager** so long operations can be paused/resumed and recovered after crashes.
3. **Introduce a command palette** (Ctrl/Cmd+K) for fast navigation and action discovery.
4. **Expand the deterministic rule pipeline editor** with conditional branches, import/export, and per-pipeline safety reports.
5. **Ship first-class file safety tooling** (transaction logs, checkpoint snapshots, rollback wizard).
6. **Add rich observability** (structured logs, telemetry toggles, performance dashboards for large batches).
7. **Expand format support** (audio/video EXIF/XMP/ID3, EPUB metadata, office document metadata).
8. **Implement profile sync/import-export** for teams and multi-machine usage.
9. **Add full integration test fixtures for GUI flows** using headless Qt testing harnesses.
10. **Package native distributables** (MSI, macOS app bundle, Linux AppImage/Flatpak) with auto-update channels.

## License

Add or update a project license file if redistribution is planned.
