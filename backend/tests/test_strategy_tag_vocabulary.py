"""TAIL joins the strategy vocabulary, and the vocabulary gets one author — R-IV.624(d)2.

MEASURED 2026-10-01. `unified_positions.strategy_tag` is text, nullable, no CHECK — deliberate,
on the cash_flows.flow_type precedent, with enforcement placed "in the entry UI". Two findings:

  * **No UI writes this column.** The only writer is the PATCH route, so the enforcement point
    the decision rested on was never built.
  * **The declared list and the stored data were disjoint but for CORE.** Declared:
    CORE | B1_MACRO | B1_C_CONVEXITY | B2_TACTICAL | B3_SCALP | HEDGE | MOMENTUM | OTHER.
    Stored: CONVEXITY 8, B1 4, B2 3, CORE 1 — fifteen of sixteen rows carrying a word the
    vocabulary did not contain.

So the canonical spellings are the book's own, which is the family TAIL joins.
"""

import ast
import io
import os

import pytest

from models.strategy_tag import (ALIASES, B1, B2, CONVEXITY, CORE, TAGS, TAIL,
                                 UNWRITTEN_DECLARED, all_recognised, canonical,
                                 column_comment, is_known)

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(BACKEND)

# exactly what the book held when this ruling was written
STORED_2026_10_01 = {"CONVEXITY": 8, "B1": 4, "B2": 3, "CORE": 1}


def _code(rel, root=BACKEND):
    """Live code only: docstrings and comments both removed, spacing preserved."""
    import tokenize

    src = io.open(os.path.join(root, rel), encoding="utf-8-sig").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    lines = src.splitlines(keepends=True)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type != tokenize.COMMENT:
                continue
            r, c0, c1 = tok.start[0] - 1, tok.start[1], tok.end[1]
            lines[r] = lines[r][:c0] + " " * (c1 - c0) + lines[r][c1:]
    except (tokenize.TokenError, IndentationError):
        pass
    return "".join(lines)


# ─────────────────────── TAIL is in, and so is everything already written

class TestTailJoins:

    def test_tail_is_canonical(self):
        assert TAIL == "TAIL"
        assert TAIL in TAGS
        assert is_known("TAIL")
        assert canonical("tail") == "TAIL"       # POSITIONS' stamp may arrive lowercase

    @pytest.mark.parametrize("stored", sorted(STORED_2026_10_01))
    def test_every_word_already_in_the_book_is_canonical(self, stored):
        """THE DEFECT. Adding TAIL to the OLD list would have added a word to a vocabulary
        nobody writes against — the stored spellings were not in it."""
        assert stored in TAGS, stored
        assert canonical(stored) == stored

    def test_the_canonical_set_is_the_book_plus_tail(self):
        assert set(TAGS) == set(STORED_2026_10_01) | {TAIL}


# ─────────────────────── nothing already written becomes unreadable

class TestTheOldSpellingsStillRead:

    @pytest.mark.parametrize("long_form,short", sorted(ALIASES.items()))
    def test_a_long_form_maps_to_its_canonical(self, long_form, short):
        """A tag written in an old brief must not become unreadable because the vocabulary
        moved. Deleting these would have been the easy, lossy choice."""
        assert canonical(long_form) == short
        assert is_known(long_form)

    def test_the_aliases_are_the_three_that_map_cleanly(self):
        assert ALIASES == {"B1_MACRO": B1, "B2_TACTICAL": B2, "B1_C_CONVEXITY": CONVEXITY}

    @pytest.mark.parametrize("declared", UNWRITTEN_DECLARED)
    def test_a_declared_but_unwritten_word_is_recognised_not_refused(self, declared):
        """R-IV.143(2) declared these and no row ever carried one. Recognised, so a write is
        not refused; listed apart, so a reader is not told they are current."""
        assert is_known(declared)
        assert canonical(declared) == declared
        assert declared not in TAGS

    def test_every_word_r_iv_143_declared_is_still_readable(self):
        """POSITIVE CONTROL for the whole alias design: not one of the eight originally
        declared words is lost."""
        for w in ("CORE", "B1_MACRO", "B1_C_CONVEXITY", "B2_TACTICAL",
                  "B3_SCALP", "HEDGE", "MOMENTUM", "OTHER"):
            assert is_known(w), w


# ─────────────────────── unknown is unknown, and NULL is not a tag

class TestUnknownAndNull:

    def test_an_unknown_word_is_not_known(self):
        assert not is_known("B4")
        assert canonical("B4") is None

    def test_null_is_untagged_and_is_not_a_tag(self):
        """NULL means untagged, never OTHER: OTHER is a classification, NULL is its absence.
        `is_known(None)` must be False or an untagged row reads as a valid tag."""
        assert canonical(None) is None
        assert not is_known(None)
        assert not is_known("")
        assert canonical("   ") is None

    def test_nothing_here_can_be_used_as_a_default(self):
        """A vocabulary with a default turns "nobody classified this" into a claim."""
        code = _code("models/strategy_tag.py")
        assert "DEFAULT" not in code.upper().replace("DEFAULT_", "")


# ─────────────────────── one author

class TestOneAuthor:

    def test_the_column_comment_is_generated_from_the_list(self):
        """It was a retyped string literal in the SAME FILE as the list — two copies, so one
        edit left the database describing a vocabulary the code had moved on from."""
        c = column_comment()
        for tag in TAGS:
            assert tag in c, tag
        for long_form in ALIASES:
            assert long_form in c, long_form

    def test_the_migration_script_no_longer_retypes_the_vocabulary(self):
        code = _code("scripts/feat_position_lifecycle_strategy_tag.py", root=REPO)
        assert "column_comment()" in code
        assert "VOCAB = [" not in code
        assert "B1_C_CONVEXITY" not in code   # not retyped anywhere in the script

    def test_the_api_model_does_not_restate_the_list(self):
        """A third copy of a list is a third thing to forget."""
        code = _code("api/unified_positions.py")
        assert "B1_C_CONVEXITY" not in code
        assert "B3_SCALP" not in code

    def test_the_comment_records_that_no_check_is_deliberate(self):
        """The precedent is not this ruling's to overturn — but it must not be silent either,
        because the enforcement point it named does not exist."""
        c = column_comment()
        assert "NO CHECK" in c
        assert "no UI writes this column" in c

    def test_all_recognised_is_the_union_and_has_no_duplicates(self):
        words = all_recognised()
        assert len(words) == len(set(words))
        assert set(words) == set(TAGS) | set(ALIASES) | set(UNWRITTEN_DECLARED)
