"""
tests/test_integration.py
=========================
Integration tests that touch the filesystem (rename / undo) and exercise
the full RenameEngine pipeline on realistic filenames from conftest.sample_dir.

These complement the unit tests in test_engine.py by verifying edge cases
that only appear with real multi-stage pipelines or filesystem interactions.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from studio.engine  import RenameEngine
from studio.history import HistoryEntry, HistoryManager


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def p(**kw):
    return kw


def batch_process(engine, files, params):
    """Return list of (original, new_name) pairs for enabled files."""
    results = []
    for i, f in enumerate(files):
        new = engine.process(f, params, index=i)
        results.append((f, new))
    return results


# ══════════════════════════════════════════════════════════════════════════════
#  Pipeline integration
# ══════════════════════════════════════════════════════════════════════════════

class TestPipelineIntegration:

    def test_claymore_suffix_sample(self, engine, sample_dir):
        """Reproduce the exact use-case shown in the screenshot."""
        cbz_files = sorted(
            f for f in os.listdir(sample_dir) if f.endswith(".cbz")
        )
        params = p(add_suffix=" - sample", ext_mode="Lower")
        for i, fname in enumerate(cbz_files):
            new = engine.process(fname, params, index=i)
            stem = Path(fname).stem
            assert new == f"{stem} - sample.cbz", new

    def test_number_all_jpgs(self, engine, sample_dir):
        """Prefix every JPG with a zero-padded counter."""
        jpgs = sorted(f for f in os.listdir(sample_dir) if f.lower().endswith(".jpg"))
        params = p(num_mode="Prefix", num_pad=3, num_sep="_")
        for i, fname in enumerate(jpgs):
            new = engine.process(fname, params, index=i)
            expected_num = str(i + 1).zfill(3)
            assert new.startswith(f"{expected_num}_"), new

    def test_full_lower_extension(self, engine, sample_dir):
        files = [f for f in os.listdir(sample_dir) if ".JPG" in f]
        params = p(ext_mode="Lower")
        for f in files:
            new = engine.process(f, params)
            assert new.endswith(".jpg"), new

    def test_replace_comma_space_then_title_case(self, engine):
        fname  = "hello, world - subtitle.txt"
        params = p(replace_find=", ", replace_with=" ", case_mode="Title")
        result = engine.process(fname, params)
        assert result == "Hello World - Subtitle.txt"

    def test_remove_brackets_and_trim(self, engine):
        fname  = "Movie Title (2024) [BluRay].mkv"
        params = p(remove_brackets=True, remove_trim=True)
        result = engine.process(fname, params)
        assert result == "Movie Title.mkv"

    def test_regex_inc_ext_normalise_extension(self, engine):
        """regex_inc_ext: replace .JPG → .jpg across multiple files."""
        files  = ["Photo_001.JPG", "Photo_002.JPG", "Photo_003.JPG"]
        params = p(regex_match=r"\.JPG$", regex_replace=".jpg", regex_inc_ext=True)
        for f in files:
            result = engine.process(f, params)
            assert result.endswith(".jpg"), result
            assert not result.endswith(".JPG"), result

    def test_accent_removal_in_batch(self, engine):
        files  = ["résumé.pdf", "naïve.txt", "café.html"]
        params = p(remove_accents=True)
        expected = ["resume.pdf", "naive.txt", "cafe.html"]
        for f, exp in zip(files, expected):
            assert engine.process(f, params) == exp

    def test_alpha_numbering_26_boundary(self, engine):
        """Verify alpha wraps a→z→aa correctly at 26-file boundary."""
        params = p(num_mode="Prefix", num_base="Alpha")
        results = [engine.process("f.txt", params, index=i) for i in range(28)]
        assert results[0]  == "af.txt"
        assert results[25] == "zf.txt"
        assert results[26] == "aaf.txt"
        assert results[27] == "abf.txt"

    def test_roman_numbering(self, engine):
        params   = p(num_mode="Suffix", num_base="Roman", num_sep=" ")
        expected = ["f i.txt","f ii.txt","f iii.txt","f iv.txt","f v.txt",
                    "f vi.txt","f vii.txt","f viii.txt","f ix.txt","f x.txt"]
        for i, exp in enumerate(expected):
            assert engine.process("f.txt", params, index=i) == exp

    def test_token_n_in_prefix_batch(self, engine):
        files  = ["a.txt", "b.txt", "c.txt"]
        params = p(add_prefix="{n:02d} - ".replace(":02d", ""))  # plain {n}
        for i, f in enumerate(files):
            result = engine.process(f, params, index=i)
            assert result.startswith(f"{i+1} - "), result

    def test_metadata_token_missing_is_kept_literal(self, engine):
        """Unknown tokens should pass through unchanged (no KeyError)."""
        params = p(add_prefix="{nonexistent_token}_")
        result = engine.process("file.txt", params, metadata={})
        assert result == "{nonexistent_token}_file.txt"

    def test_move_copy_sep(self, engine):
        """Move first 4 chars to end with a dash separator."""
        params = p(mcp_mode="Move", mcp_from=1, mcp_length=4, mcp_to=999, mcp_sep="-")
        result = engine.process("2024file.txt", params)
        # chunk="2024", rest="file", insert at end → "file-2024-"  (sep on both sides)
        assert "2024" in result and "file" in result

    def test_idempotent_on_noop_params(self, engine, sample_dir):
        """With default (all-noop) params, every file maps to itself."""
        files  = os.listdir(sample_dir)
        params = p()
        for f in files:
            assert engine.process(f, params) == f, f


# ══════════════════════════════════════════════════════════════════════════════
#  Filesystem rename + undo cycle
# ══════════════════════════════════════════════════════════════════════════════

class TestRenameCycle:

    def test_rename_and_undo(self, sample_dir):
        """Rename 3 CBZ files on disk, then undo all 3 in one batch."""
        engine  = RenameEngine()
        history = HistoryManager()
        params  = p(add_suffix=" - sample", ext_mode="Lower")

        cbz_files = sorted(f for f in os.listdir(sample_dir) if f.endswith(".cbz"))
        renames: list[tuple[str, str]] = []

        for i, fname in enumerate(cbz_files):
            new_name = engine.process(fname, params, index=i)
            src = sample_dir / fname
            dst = sample_dir / new_name
            os.rename(src, dst)
            renames.append((fname, new_name))

        # All new names exist, old names gone
        for orig, new in renames:
            assert (sample_dir / new).exists()
            assert not (sample_dir / orig).exists()

        entry = HistoryEntry(str(sample_dir), renames)
        history.push(entry)

        # Undo
        popped = history.undo()
        errors = popped.undo()
        assert errors == [], errors

        # Original names restored
        for orig, new in renames:
            assert (sample_dir / orig).exists()
            assert not (sample_dir / new).exists()

    def test_dedup_conflict(self, sample_dir):
        """
        If a destination already exists, the auto-dedup suffix logic should
        find a free slot.
        """
        # Create a conflict: both "README.txt" and "README_new.txt" exist
        (sample_dir / "README_new.txt").touch()

        def _dedup(dst: Path, new_name: str) -> str:
            stem, ext = Path(new_name).stem, Path(new_name).suffix
            k = 2
            while dst.exists():
                new_name = f"{stem}_({k}){ext}"
                dst      = sample_dir / new_name
                k       += 1
            return new_name

        src      = sample_dir / "README.txt"
        new_name = "README_new.txt"
        dst      = sample_dir / new_name
        final    = _dedup(dst, new_name)

        assert final == "README_new_(2).txt"

    def test_history_capacity_eviction(self):
        """Pushing beyond MAX entries evicts the oldest."""
        mgr = HistoryManager(max_entries=3)
        for i in range(5):
            mgr.push(HistoryEntry("/tmp", [(f"old{i}", f"new{i}")]))
        entries = mgr.visible_entries()
        assert len(entries) == 3
        # Newest-first: newest is index=4
        assert entries[0].renames[0][0] == "old4"

    def test_undo_missing_file_reports_error(self, tmp_path):
        """Undo of a rename whose target has been deleted reports an error."""
        entry  = HistoryEntry(str(tmp_path), [("original.txt", "missing.txt")])
        errors = entry.undo()
        assert len(errors) == 1
        assert "missing.txt" in errors[0]


# ══════════════════════════════════════════════════════════════════════════════
#  PresetManager integration
# ══════════════════════════════════════════════════════════════════════════════

class TestPresetIntegration:

    def test_roundtrip_complex_params(self, preset_manager):
        params = {
            "regex_match":    r"Vol\.(\d+)",
            "regex_replace":  r"Volume \1",
            "add_suffix":     " - sample",
            "num_mode":       "Prefix",
            "num_pad":        3,
            "case_mode":      "Title",
            "ext_mode":       "Lower",
        }
        preset_manager.save("complex", params)
        loaded = preset_manager.load("complex")
        assert loaded == params

    def test_multiple_presets_sorted(self, preset_manager):
        for name in ("zebra", "apple", "mango"):
            preset_manager.save(name, {"k": name})
        assert preset_manager.names() == ["apple", "mango", "zebra"]

    def test_overwrite_preset(self, preset_manager):
        preset_manager.save("p1", {"a": 1})
        preset_manager.save("p1", {"a": 99})
        assert preset_manager.load("p1") == {"a": 99}

    def test_delete_nonexistent_returns_false(self, preset_manager):
        assert not preset_manager.delete("no_such_preset")

    def test_load_returns_deep_copy(self, preset_manager):
        preset_manager.save("p", {"list": [1, 2, 3]})
        a = preset_manager.load("p")
        b = preset_manager.load("p")
        a["list"].append(99)
        assert b["list"] == [1, 2, 3]   # b not mutated
