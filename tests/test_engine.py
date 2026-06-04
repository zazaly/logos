"""
tests/test_engine.py
====================
Unit tests for studio.engine.RenameEngine.

Run with:
    pytest tests/test_engine.py -v
"""
from __future__ import annotations

import re
import pytest

from studio.engine import RenameEngine


@pytest.fixture
def eng() -> RenameEngine:
    return RenameEngine()


# ══════════════════════════════════════════════════════════════════════════════
#  Helper
# ══════════════════════════════════════════════════════════════════════════════

def p(**kwargs) -> dict:
    """Build a minimal params dict; unspecified keys keep engine defaults."""
    return kwargs


# ══════════════════════════════════════════════════════════════════════════════
#  Step 1 — Name
# ══════════════════════════════════════════════════════════════════════════════

class TestName:
    def test_keep(self, eng):
        assert eng.process("hello.txt", p()) == "hello.txt"

    def test_remove(self, eng):
        assert eng.process("hello.txt", p(name_mode="Remove")) == ".txt"

    def test_fixed(self, eng):
        assert eng.process("hello.txt", p(name_mode="Fixed", name_fixed="world")) == "world.txt"

    def test_reverse(self, eng):
        assert eng.process("abc.txt", p(name_mode="Reverse")) == "cba.txt"


# ══════════════════════════════════════════════════════════════════════════════
#  Step 2 — RegEx
# ══════════════════════════════════════════════════════════════════════════════

class TestRegex:
    def test_basic_sub(self, eng):
        result = eng.process(
            "Claymore, Vol.01.cbz",
            p(regex_match=r", Vol\.(\d+)", regex_replace=r" Volume \1"),
        )
        assert result == "Claymore Volume 01.cbz"

    def test_simple_flag_case_insensitive(self, eng):
        result = eng.process(
            "Hello.txt",
            p(regex_match="hello", regex_replace="Hi", regex_simple=True),
        )
        assert result == "Hi.txt"

    def test_inc_ext(self, eng):
        # pattern touches extension too
        result = eng.process(
            "file.TXT",
            p(regex_match=r"\.TXT$", regex_replace=".txt", regex_inc_ext=True),
        )
        assert result == "file.txt"

    def test_invalid_pattern_raises(self, eng):
        with pytest.raises(re.error):
            eng.process("test.txt", p(regex_match="[invalid"))

    def test_no_match_unchanged(self, eng):
        result = eng.process("hello.txt", p(regex_match="zzz", regex_replace="x"))
        assert result == "hello.txt"


# ══════════════════════════════════════════════════════════════════════════════
#  Step 3 — Replace
# ══════════════════════════════════════════════════════════════════════════════

class TestReplace:
    def test_simple(self, eng):
        assert eng.process(
            "foo bar.txt", p(replace_find="bar", replace_with="baz")
        ) == "foo baz.txt"

    def test_case_sensitive(self, eng):
        result = eng.process(
            "Hello hello.txt",
            p(replace_find="Hello", replace_with="Hi", replace_match_case=True),
        )
        assert result == "Hi hello.txt"

    def test_first_only(self, eng):
        result = eng.process(
            "aaa.txt",
            p(replace_find="a", replace_with="b", replace_first_only=True),
        )
        assert result == "baa.txt"

    def test_case_insensitive_default(self, eng):
        result = eng.process(
            "Hello.txt",
            p(replace_find="hello", replace_with="World"),
        )
        assert result == "World.txt"


# ══════════════════════════════════════════════════════════════════════════════
#  Step 4 — Remove
# ══════════════════════════════════════════════════════════════════════════════

class TestRemove:
    def test_first_n(self, eng):
        assert eng.process("abcdef.txt", p(remove_first_n=3)) == "def.txt"

    def test_last_n(self, eng):
        assert eng.process("abcdef.txt", p(remove_last_n=3)) == "abc.txt"

    def test_range(self, eng):
        # from=2, to=4 removes characters at positions 2,3,4 (1-based)
        assert eng.process("abcde.txt", p(remove_from=2, remove_to=4)) == "ae.txt"

    def test_digits(self, eng):
        assert eng.process("abc123.txt", p(remove_digits=True)) == "abc.txt"

    def test_symbols(self, eng):
        assert eng.process("hello-world!.txt", p(remove_symbols=True)) == "helloworld.txt"

    def test_ds_collapses(self, eng):
        result = eng.process("foo..bar--baz.txt", p(remove_ds=True))
        assert result == "foo bar baz.txt"

    def test_accents(self, eng):
        assert eng.process("café.txt", p(remove_accents=True)) == "cafe.txt"

    def test_lead_dots(self, eng):
        assert eng.process("...hidden.txt", p(remove_lead_dots=True)) == "hidden.txt"

    def test_brackets(self, eng):
        # brackets + content are removed; surrounding spaces are stripped
        assert eng.process("File (2024) [HD].txt", p(remove_brackets=True)) == "File.txt"

    def test_trim(self, eng):
        assert eng.process("  hello  .txt", p(remove_trim=True)) == "hello.txt"


# ══════════════════════════════════════════════════════════════════════════════
#  Step 5 — Move / Copy
# ══════════════════════════════════════════════════════════════════════════════

class TestMoveCopy:
    def test_move(self, eng):
        # stem "ABCDE": move chars at pos 1 (len 2) to pos 4 → "CDE" + "AB" inserted at 3
        # from_p=1(0-based=0), length=2 → chunk="AB", rest="CDE", insert at to_p=3(0-based=3→clamped=3)
        result = eng.process(
            "ABCDE.txt", p(mcp_mode="Move", mcp_from=1, mcp_length=2, mcp_to=4)
        )
        # rest="CDE", insert "AB" at pos 3 → "CDEAB"
        assert result == "CDEAB.txt"

    def test_copy(self, eng):
        result = eng.process(
            "HELLO.txt", p(mcp_mode="Copy", mcp_from=1, mcp_length=2, mcp_to=6)
        )
        # chunk="HE", rest="HELLO", insert at 5 (end) → "HELLOHE"
        assert result == "HELLOHE.txt"

    def test_none_unchanged(self, eng):
        assert eng.process("test.txt", p(mcp_mode="None")) == "test.txt"


# ══════════════════════════════════════════════════════════════════════════════
#  Step 6 — Add
# ══════════════════════════════════════════════════════════════════════════════

class TestAdd:
    def test_prefix(self, eng):
        assert eng.process("world.txt", p(add_prefix="hello_")) == "hello_world.txt"

    def test_suffix(self, eng):
        assert eng.process("hello.txt", p(add_suffix="_v2")) == "hello_v2.txt"

    def test_suffix_word_space(self, eng):
        assert eng.process("hello.txt", p(add_suffix="world", add_word_space=True)) == "hello world.txt"

    def test_insert_at_pos(self, eng):
        # insert "X" at position 3 (1-based) in "abcde"
        assert eng.process("abcde.txt", p(add_insert="X", add_at_pos=3)) == "abXcde.txt"

    def test_insert_at_zero_appends(self, eng):
        assert eng.process("hello.txt", p(add_insert="!", add_at_pos=0)) == "hello!.txt"

    def test_token_n(self, eng):
        result = eng.process("file.txt", p(add_prefix="{n}_"), index=4)
        assert result == "5_file.txt"

    def test_token_n0(self, eng):
        result = eng.process("file.txt", p(add_suffix="_{n0}"), index=2)
        assert result == "file_2.txt"

    def test_token_metadata(self, eng):
        meta = {"comic_series": "Claymore", "comic_volume": "01"}
        result = eng.process(
            "file.cbz",
            p(add_prefix="{comic_series} Vol.{comic_volume} - "),
            metadata=meta,
        )
        assert result == "Claymore Vol.01 - file.cbz"


# ══════════════════════════════════════════════════════════════════════════════
#  Step 7 — Auto Date
# ══════════════════════════════════════════════════════════════════════════════

class TestAutoDate:
    def test_none_unchanged(self, eng):
        assert eng.process("file.txt", p(date_mode="None")) == "file.txt"

    def test_prefix_ymd(self, eng):
        import re as _re
        result = eng.process("file.txt", p(date_mode="Prefix", date_fmt="YMD"))
        assert _re.match(r"^\d{8}file\.txt$", result), f"Unexpected: {result}"

    def test_suffix_with_sep(self, eng):
        import re as _re
        result = eng.process("file.txt", p(date_mode="Suffix", date_fmt="YMD", date_sep="_"))
        assert _re.match(r"^file_\d{8}\.txt$", result), f"Unexpected: {result}"

    def test_uses_file_mtime(self, eng):
        meta   = {"file_mtime": "2020-01-15"}
        result = eng.process(
            "file.txt",
            p(date_mode="Prefix", date_type="Modified", date_sep="-"),
            metadata=meta,
        )
        assert result.startswith("2020-01-15-"), result


# ══════════════════════════════════════════════════════════════════════════════
#  Step 8 — Numbering
# ══════════════════════════════════════════════════════════════════════════════

class TestNumbering:
    def test_prefix(self, eng):
        assert eng.process("file.txt", p(num_mode="Prefix"), index=0) == "1file.txt"
        assert eng.process("file.txt", p(num_mode="Prefix"), index=2) == "3file.txt"

    def test_suffix_sep(self, eng):
        result = eng.process("file.txt", p(num_mode="Suffix", num_sep="_"), index=0)
        assert result == "file_1.txt"

    def test_padding(self, eng):
        result = eng.process("f.txt", p(num_mode="Prefix", num_pad=3), index=4)
        assert result == "005f.txt"

    def test_start_and_incr(self, eng):
        result = eng.process(
            "f.txt", p(num_mode="Suffix", num_start=10, num_incr=5), index=2
        )
        assert result == "f20.txt"    # 10 + 2*5 = 20

    def test_break_reset(self, eng):
        eng2 = RenameEngine()
        r0 = eng2.process("f.txt", p(num_mode="Prefix", num_break=3), index=0)
        r3 = eng2.process("f.txt", p(num_mode="Prefix", num_break=3), index=3)
        # index 0 and index 3 are both at position 0 within their group
        assert r0 == r3

    def test_alpha_base(self, eng):
        assert eng.process("f.txt", p(num_mode="Prefix", num_base="Alpha"), index=0) == "af.txt"
        assert eng.process("f.txt", p(num_mode="Prefix", num_base="Alpha"), index=25) == "zf.txt"
        assert eng.process("f.txt", p(num_mode="Prefix", num_base="Alpha"), index=26) == "aaf.txt"

    def test_roman_base(self, eng):
        assert eng.process("f.txt", p(num_mode="Suffix", num_base="Roman"), index=3) == "fiv.txt"


# ══════════════════════════════════════════════════════════════════════════════
#  Step 9 — Case
# ══════════════════════════════════════════════════════════════════════════════

class TestCase:
    def test_lower(self, eng):
        assert eng.process("Hello World.TXT", p(case_mode="Lower")) == "hello world.TXT"

    def test_upper(self, eng):
        assert eng.process("hello.txt", p(case_mode="Upper")) == "HELLO.txt"

    def test_title(self, eng):
        assert eng.process("hello world.txt", p(case_mode="Title")) == "Hello World.txt"

    def test_sentence(self, eng):
        assert eng.process("hello world.txt", p(case_mode="Sentence")) == "Hello world.txt"

    def test_exceptions(self, eng):
        result = eng.process(
            "hello world foo.txt",
            p(case_mode="Title", case_exceptions="world"),
        )
        assert result == "Hello world Foo.txt"


# ══════════════════════════════════════════════════════════════════════════════
#  Step 10 — Extension
# ══════════════════════════════════════════════════════════════════════════════

class TestExtension:
    def test_lower(self, eng):
        assert eng.process("FILE.TXT", p(ext_mode="Lower")) == "FILE.txt"

    def test_upper(self, eng):
        assert eng.process("file.txt", p(ext_mode="Upper")) == "file.TXT"

    def test_fixed(self, eng):
        assert eng.process("file.txt", p(ext_mode="Fixed", ext_fixed="md")) == "file.md"
        assert eng.process("file.txt", p(ext_mode="Fixed", ext_fixed=".md")) == "file.md"

    def test_remove(self, eng):
        assert eng.process("file.txt", p(ext_mode="Remove")) == "file"

    def test_same(self, eng):
        assert eng.process("file.TXT", p(ext_mode="Same")) == "file.TXT"


# ══════════════════════════════════════════════════════════════════════════════
#  Pipeline composition
# ══════════════════════════════════════════════════════════════════════════════

class TestPipeline:
    def test_manga_volume_rename(self, eng):
        """Simulate the Claymore manga use-case from the screenshot."""
        meta = {"comic_series": "Claymore", "comic_volume": "01"}
        result = eng.process(
            "Claymore, Vol.01 - Norihiro Yagi.cbz",
            p(
                add_suffix=" - sample",
                ext_mode="Lower",
            ),
            index=0,
            metadata=meta,
        )
        assert result == "Claymore, Vol.01 - Norihiro Yagi - sample.cbz"

    def test_replace_then_case(self, eng):
        result = eng.process(
            "hello_world.txt",
            p(replace_find="_", replace_with=" ", case_mode="Title"),
        )
        assert result == "Hello World.txt"

    def test_number_then_suffix(self, eng):
        result = eng.process(
            "track.mp3",
            p(num_mode="Prefix", num_pad=2, num_sep=" - ", add_suffix=" (demo)"),
            index=0,
        )
        assert result == "01 - track (demo).mp3"

    def test_date_prefix_then_numbering(self, eng):
        import re as _re
        result = eng.process(
            "photo.jpg",
            p(date_mode="Prefix", date_fmt="YMD", date_sep="_",
              num_mode="Suffix", num_sep="_", num_pad=3),
            index=5,
        )
        # e.g. "20240516_photo_006.jpg"
        assert _re.match(r"^\d{8}_photo_006\.jpg$", result), result

    def test_custom_pipeline_order_changes_result(self, eng):
        legacy = eng.process(
            "hello.txt",
            p(add_prefix="x", case_mode="Upper"),
        )
        custom = eng.process(
            "hello.txt",
            p(
                add_prefix="x",
                case_mode="Upper",
                pipeline_order=[
                    "name",
                    "regex",
                    "replace",
                    "remove",
                    "move_copy",
                    "case",
                    "add",
                    "auto_date",
                    "numbering",
                    "extension",
                ],
            ),
        )
        assert legacy == "XHELLO.txt"
        assert custom == "xHELLO.txt"

    def test_partial_pipeline_order_is_normalised(self, eng):
        result = eng.process(
            "file.TXT",
            p(ext_mode="Lower", pipeline_order=["extension"]),
        )
        assert result == "file.txt"


# ══════════════════════════════════════════════════════════════════════════════
#  HistoryManager
# ══════════════════════════════════════════════════════════════════════════════

class TestHistory:
    def test_push_and_undo(self, tmp_path):
        from studio.history import HistoryEntry, HistoryManager
        # Create a real file so undo can actually rename it back
        src = tmp_path / "new.txt"
        src.write_text("x")
        entry = HistoryEntry(str(tmp_path), [("original.txt", "new.txt")])
        mgr   = HistoryManager()
        mgr.push(entry)
        assert mgr.can_undo()
        popped = mgr.undo()
        assert popped is entry
        assert not mgr.can_undo()

    def test_capacity(self):
        from studio.history import HistoryEntry, HistoryManager
        mgr = HistoryManager(max_entries=3)
        for i in range(5):
            mgr.push(HistoryEntry("/tmp", [(f"a{i}.txt", f"b{i}.txt")]))
        assert len(mgr.visible_entries()) == 3

    def test_undo_reverses_rename(self, tmp_path):
        from studio.history import HistoryEntry, HistoryManager
        orig = tmp_path / "original.txt"
        new_ = tmp_path / "renamed.txt"
        orig.write_text("hello")
        # simulate a rename
        orig.rename(new_)
        assert new_.exists() and not orig.exists()

        entry = HistoryEntry(str(tmp_path), [("original.txt", "renamed.txt")])
        errors = entry.undo()
        assert errors == [], errors
        assert orig.exists() and not new_.exists()


# ══════════════════════════════════════════════════════════════════════════════
#  PresetManager
# ══════════════════════════════════════════════════════════════════════════════

class TestPresets:
    def test_save_load_delete(self, tmp_path, monkeypatch):
        """
        Patch QSettings to store in tmp_path so tests stay isolated.
        """
        from studio.presets import PresetManager

        # Redirect the preset file to a temp location
        fake_preset_path = tmp_path / "presets.json"

        class _PM(PresetManager):
            def __init__(self):  # skip QSettings lookup
                import json, copy
                self._path = fake_preset_path
                self._data: dict = {}
                self._load()

        mgr = _PM()
        params = {"add_suffix": "- sample", "case_mode": "Lower"}
        mgr.save("my preset", params)
        assert "my preset" in mgr.names()

        loaded = mgr.load("my preset")
        assert loaded == params
        assert loaded is not params   # deep copy

        mgr.delete("my preset")
        assert "my preset" not in mgr.names()

    def test_rename_preset(self, tmp_path):
        from studio.presets import PresetManager
        fake_path = tmp_path / "presets.json"

        class _PM(PresetManager):
            def __init__(self):
                import json
                self._path = fake_path
                self._data = {}

        mgr = _PM()
        mgr.save("old", {"k": "v"})
        assert mgr.rename_preset("old", "new")
        assert "new" in mgr.names()
        assert "old" not in mgr.names()
