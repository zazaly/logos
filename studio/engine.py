"""
studio.engine
==========
Stateless rename engine.

Public API
----------
    engine = RenameEngine()
    new_name = engine.process(original, params, index=0, metadata={})

``params`` is the flat dict produced by ``MainWindow._collect_params()``.
``index`` is the 0-based position of this file among *enabled* rows.
``metadata`` is the dict returned by ``MetadataExtractor.extract()``.

The pipeline applies transformations in this fixed order:
    1. Name      — keep / remove / fixed / reverse
    2. RegEx     — pattern substitution (may raise re.error on bad pattern)
    3. Replace   — plain-text find-and-replace
    4. Remove    — strip chars / ranges / character classes
    5. MoveCopy  — move or copy a character range to a new position
    6. Add       — prefix / insert-at-pos / suffix  (with {token} expansion)
    7. AutoDate  — inject date string
    8. Numbering — sequential counter
    9. Case      — lower / upper / title / sentence
   10. Extension — normalise or replace file extension
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any


# ══════════════════════════════════════════════════════════════════════════════
class RenameEngine:
    """
    Stateless transformation engine.
    Every method is pure: same inputs → same output, no side effects.
    """

    # ------------------------------------------------------------------ #
    def process(
        self,
        original: str,
        params:   dict[str, Any],
        index:    int = 0,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """
        Return the renamed filename for *original* given *params*.

        Raises
        ------
        re.error   — if the RegEx pattern in params is invalid
        """
        path = Path(original)
        stem = path.stem
        ext  = path.suffix      # e.g. ".cbz"  (includes leading dot)
        meta = metadata or {}

        stem = self._name(stem, params)
        stem, ext = self._regex(stem, ext, params)  # may raise re.error; may update ext
        stem = self._replace(stem, params)
        stem = self._remove(stem, params)
        stem = self._move_copy(stem, params)
        stem = self._add(stem, params, index, meta)
        stem = self._auto_date(stem, params, meta)
        stem = self._numbering(stem, params, index)
        stem = self._case(stem, params)
        ext  = self._extension(ext, params)

        return stem + ext

    # ================================================================== #
    #  Step 1 — Name
    # ================================================================== #
    def _name(self, stem: str, p: dict) -> str:
        mode = p.get("name_mode", "Keep")
        if mode == "Remove":   return ""
        if mode == "Fixed":    return p.get("name_fixed") or stem
        if mode == "Reverse":  return stem[::-1]
        return stem                             # "Keep"

    # ================================================================== #
    #  Step 2 — RegEx
    # ================================================================== #
    def _regex(self, stem: str, ext: str, p: dict) -> tuple[str, str]:
        """
        Returns (new_stem, new_ext).
        When regex_inc_ext is set the substitution runs on the full filename
        and pathlib re-splits the result so the extension is correctly updated.
        """
        pattern = (p.get("regex_match") or "").strip()
        if not pattern:
            return stem, ext
        replace = p.get("regex_replace") or ""
        flags   = re.IGNORECASE if p.get("regex_simple") else 0

        if p.get("regex_inc_ext"):
            full     = stem + ext
            result   = re.sub(pattern, replace, full, flags=flags)
            new_path = Path(result)
            return (new_path.stem, new_path.suffix) if new_path.suffix else (result, "")
        else:
            return re.sub(pattern, replace, stem, flags=flags), ext

    # ================================================================== #
    #  Step 3 — Plain replace
    # ================================================================== #
    def _replace(self, stem: str, p: dict) -> str:
        find = p.get("replace_find") or ""
        if not find:
            return stem
        with_   = p.get("replace_with") or ""
        flags   = 0 if p.get("replace_match_case") else re.IGNORECASE
        count   = 1 if p.get("replace_first_only") else 0
        return re.sub(re.escape(find), with_, stem, count=count, flags=flags)

    # ================================================================== #
    #  Step 4 — Remove
    # ================================================================== #
    def _remove(self, stem: str, p: dict) -> str:
        first_n = int(p.get("remove_first_n") or 0)
        last_n  = int(p.get("remove_last_n")  or 0)
        from_   = int(p.get("remove_from")    or 0)
        to_     = int(p.get("remove_to")      or 0)

        if first_n:
            stem = stem[first_n:]
        if last_n:
            stem = stem[:-last_n] if last_n < len(stem) else ""
        if from_ and to_ and to_ >= from_:
            # positions are 1-based, inclusive
            stem = stem[: from_ - 1] + stem[to_:]

        if p.get("remove_digits"):    stem = re.sub(r"\d",        "", stem)
        if p.get("remove_symbols"):   stem = re.sub(r"[^\w\s]",   "", stem)
        if p.get("remove_high"):      stem = stem.encode("ascii", "ignore").decode()
        if p.get("remove_ds"):
            # collapse dots, spaces and dashes into a single space
            stem = re.sub(r"[\.\s\-]+", " ", stem).strip()
        if p.get("remove_accents"):
            stem = "".join(
                c for c in unicodedata.normalize("NFD", stem)
                if unicodedata.category(c) != "Mn"
            )
        if p.get("remove_lead_dots"): stem = stem.lstrip(".")
        if p.get("remove_brackets"):
            # remove content inside () [] {} including the brackets
            stem = re.sub(r"[\(\[\{][^\)\]\}]*[\)\]\}]", "", stem).strip()
        if p.get("remove_trim"):
            stem = stem.strip()

        return stem

    # ================================================================== #
    #  Step 5 — Move / Copy a character range
    # ================================================================== #
    def _move_copy(self, stem: str, p: dict) -> str:
        mode = p.get("mcp_mode") or "None"
        if mode == "None":
            return stem

        from_p = max(1, int(p.get("mcp_from")   or 1)) - 1  # 0-based
        length = max(1, int(p.get("mcp_length")  or 1))
        to_p   = max(1, int(p.get("mcp_to")      or 1)) - 1  # 0-based in result

        chunk = stem[from_p: from_p + length]
        if not chunk:
            return stem

        rest  = stem[:from_p] + stem[from_p + length:] if mode == "Move" else stem
        to_p  = min(to_p, len(rest))
        sep   = p.get("mcp_sep") or ""

        return rest[:to_p] + sep + chunk + sep + rest[to_p:]

    # ================================================================== #
    #  Step 6 — Add  (prefix / insert / suffix with token expansion)
    # ================================================================== #
    def _add(self, stem: str, p: dict, index: int, meta: dict) -> str:
        prefix = self._expand(p.get("add_prefix") or "", meta, index)
        suffix = self._expand(p.get("add_suffix") or "", meta, index)
        insert = self._expand(p.get("add_insert") or "", meta, index)
        at_pos = int(p.get("add_at_pos") or 0)
        sep    = " " if p.get("add_word_space") else ""

        if prefix:
            stem = prefix + stem
        if insert:
            # 1-based; 0 means append
            pos  = (max(0, at_pos - 1)) if at_pos > 0 else len(stem)
            stem = stem[:pos] + insert + stem[pos:]
        if suffix:
            stem = stem + sep + suffix

        return stem

    # ================================================================== #
    #  Step 7 — Auto Date
    # ================================================================== #
    _DATE_FMTS: dict[str, str] = {
        "YMD":   "%Y%m%d",
        "DMY":   "%d%m%Y",
        "MDY":   "%m%d%Y",
        "ISO":   "%Y-%m-%d",
        "YMDHM": "%Y%m%d_%H%M",
        "HUMAN": "%d %b %Y",
    }

    def _auto_date(self, stem: str, p: dict, meta: dict) -> str:
        mode = p.get("date_mode") or "None"
        if mode == "None":
            return stem

        dtype = p.get("date_type") or "Creation (Current)"
        fmt   = self._DATE_FMTS.get(p.get("date_fmt") or "YMD", "%Y%m%d")
        sep   = p.get("date_sep") or ""

        # Try to use file metadata date first
        if "Modified" in dtype and meta.get("file_mtime"):
            date_s = meta["file_mtime"]
        elif "Accessed" in dtype and meta.get("file_ctime"):
            date_s = meta["file_ctime"]
        else:
            date_s = datetime.now().strftime(fmt)

        if mode == "Prefix": return date_s + sep + stem
        if mode == "Suffix": return stem + sep + date_s
        return stem

    # ================================================================== #
    #  Step 8 — Numbering
    # ================================================================== #
    def _numbering(self, stem: str, p: dict, index: int) -> str:
        mode = p.get("num_mode") or "None"
        if mode == "None":
            return stem

        start = int(p.get("num_start") or 1)
        incr  = int(p.get("num_incr")  or 1)
        pad   = int(p.get("num_pad")   or 0)
        brk   = int(p.get("num_break") or 0)     # reset every N
        base  = p.get("num_base") or "Decimal"   # Decimal | Alpha | Roman

        effective_idx = (index % brk) if brk else index
        num           = effective_idx * incr + start

        if base == "Alpha":
            num_s = self._to_alpha(num)
        elif base == "Roman":
            num_s = self._to_roman(num)
        else:
            num_s = str(num).zfill(pad) if pad else str(num)

        sep = p.get("num_sep") or ""

        if mode == "Prefix": return num_s + sep + stem
        if mode == "Suffix": return stem + sep + num_s
        if mode == "Both":   return num_s + sep + stem + sep + num_s
        return stem

    # ================================================================== #
    #  Step 9 — Case
    # ================================================================== #
    def _case(self, stem: str, p: dict) -> str:
        mode = p.get("case_mode") or "Same"
        exc  = {w.strip().lower()
                for w in (p.get("case_exceptions") or "").split(",")
                if w.strip()}

        if   mode == "Lower":    result = stem.lower()
        elif mode == "Upper":    result = stem.upper()
        elif mode == "Title":    result = stem.title()
        elif mode == "Sentence": result = stem.capitalize()
        else:                    return stem

        # Restore exception words to their original capitalisation
        if exc:
            orig_words   = stem.split()
            result_words = result.split()
            result = " ".join(
                orig_words[i] if (i < len(orig_words) and w.lower() in exc) else w
                for i, w in enumerate(result_words)
            )
        return result

    # ================================================================== #
    #  Step 10 — Extension
    # ================================================================== #
    def _extension(self, ext: str, p: dict) -> str:
        mode = p.get("ext_mode") or "Same"
        if mode == "Lower":  return ext.lower()
        if mode == "Upper":  return ext.upper()
        if mode == "Remove": return ""
        if mode == "Fixed":
            val = (p.get("ext_fixed") or "").strip()
            return ("." + val.lstrip(".")) if val else ext
        return ext

    # ================================================================== #
    #  Token expansion  {token} → value from metadata
    # ================================================================== #
    def _expand(self, text: str, meta: dict, index: int) -> str:
        """
        Replace ``{token}`` placeholders.

        Built-in tokens
        ---------------
        {n}     1-based row counter
        {n0}    0-based row counter

        All keys from ``meta`` are also available, e.g.:
            {comic_series}, {pdf_title}, {exif_make}, {file_mtime}
        """
        if not text or "{" not in text:
            return text
        result = text
        result = result.replace("{n}",  str(index + 1))
        result = result.replace("{n0}", str(index))
        for key, val in meta.items():
            result = result.replace(f"{{{key}}}", val)
        return result

    # ================================================================== #
    #  Number-format helpers
    # ================================================================== #
    @staticmethod
    def _to_alpha(n: int) -> str:
        """1→a, 2→b … 26→z, 27→aa …"""
        result = ""
        while n > 0:
            n, rem = divmod(n - 1, 26)
            result = chr(ord("a") + rem) + result
        return result

    @staticmethod
    def _to_roman(n: int) -> str:
        """Convert positive integer to lowercase Roman numerals."""
        val = [
            (1000,"m"),(900,"cm"),(500,"d"),(400,"cd"),
            (100,"c"),(90,"xc"),(50,"l"),(40,"xl"),
            (10,"x"),(9,"ix"),(5,"v"),(4,"iv"),(1,"i"),
        ]
        result = ""
        for v, s in val:
            while n >= v:
                result += s; n -= v
        return result
