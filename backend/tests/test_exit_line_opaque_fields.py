"""The EXIT-line parser splits on U+00B7 and treats each field as opaque — R-IV.695, R-IV.696(b).

TA-089 standardises field text on ASCII with U+00B7 as the separator from here on; existing rows
keep their en dashes, em dashes and multiplication signs. So the parser must find a field by its
POSITION between separators and pass its text through untouched.

THE OLD PARSER DID NEITHER. It ran three content-anchored regexes that matched the literal phrases
`time stop` and `stop` to LOCATE a field, and it normalised characters: `_clean` stripped
`·—-` from every field's edges, and the capture classes `[^·—\\n]` / `[^·;—\\n]` EXCLUDED U+2014.
It passed the 34 live lines by luck of position — every em dash happened to sit in the invalidation
field, which the lookahead swallowed whole.

MEASURED ON THE LIVE CORPUS, 2026-10-07, which is what makes position-indexing safe:

  * 36 rows contain `EXIT:` but only 34 contain `EXIT: invalidation`. The two extra are PROSE
    (ids 404, 406: "EXIT: open in the book for three days after the sale..."), so the marker must
    be the longer phrase or two sentences enter as structured lines.
  * 30 of the 34 do NOT begin the notes. 437's sits at offset 751 of 2,649, reading
    `... || TA-052 EXIT: invalidation ...` — so containment is required, and even "the start of a
    || block" fails, because that block starts `TA-052 `.
  * 23 have a ` || ` tail, 1 has a ` | ` tail, 10 run to the end. Bounding is not optional.
  * every one carries EXACTLY TWO separators in its bounded segment, so 0/1/2 is invalidation /
    time stop / stop with no ambiguity about how many fields there are.
"""

import ast
import io
import os
from datetime import date

import pytest

from models.exit_plan import (BROKER_ORDER, EXIT_LINE_MARKER, FIELD_SEPARATOR, NONE,
                              find_exit_segment, has_exit_line, parse_exit_line)

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOT = "·"
EM = "—"
EN = "–"
MUL = "×"


def _code(rel):
    src = io.open(os.path.join(BACKEND, rel), encoding="utf-8-sig").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    return "".join(l for l in src.splitlines(keepends=True)
                   if not l.strip().startswith("#"))


def line(inval="x", ts="2026-11-20", stop="none"):
    return "EXIT: invalidation %s %s time stop %s %s stop %s" % (inval, DOT, ts, DOT, stop)


class TestItSplitsOnTheSeparator:
    def test_the_separator_is_U00B7(self):
        assert FIELD_SEPARATOR == "·"

    def test_the_split_is_on_the_separator_not_on_a_phrase(self):
        src = _code("models/exit_plan.py")
        assert "seg.split(FIELD_SEPARATOR)" in src
        # the old content anchors are gone
        assert "(?=\\s+·\\s*time stop" not in src
        assert "(?<!time )\\bstop" not in src

    def test_fields_are_taken_by_position(self):
        src = _code("models/exit_plan.py")
        for idx in ("fields[0]", "fields[1]", "fields[2]"):
            assert idx in src


class TestTheFieldTextIsOpaque:
    def test_an_em_dash_inside_the_time_stop_field_no_longer_loses_the_date(self):
        """The old capture class excluded U+2014, so the date sitting right there was lost."""
        out = parse_exit_line(line(ts=EM + " 2026-11-20"))
        assert out["time_stop"] == date(2026, 11, 20)
        assert out["unparsed"] == []

    def test_an_em_dash_inside_the_stop_field_no_longer_loses_the_type(self):
        out = parse_exit_line(line(stop=EM + " broker order"))
        assert out["stop_type"] == BROKER_ORDER
        assert out["unparsed"] == []

    def test_a_field_ending_in_an_em_dash_KEEPS_it(self):
        """`_clean` used to `.strip("·—-")`, which deleted a character from the principal's own
        text. Only whitespace comes off now."""
        out = parse_exit_line(line(inval="hold until earnings " + EM))
        assert out["invalidation"] == "hold until earnings " + EM
        assert out["invalidation"].endswith(EM)

    def test_en_dash_em_dash_and_multiplication_sign_all_survive(self):
        """701 MSFT's shape (U+2013, U+2014, U+00D7), which R-IV.695 names."""
        text = "none %s defined risk; harvest 60%s70%% of max, sell 1 at 2%s3%s cost" % (
            EM, EN, EN, MUL)
        out = parse_exit_line(line(inval=text))
        assert out["invalidation"] == text
        for ch in (EM, EN, MUL):
            assert ch in out["invalidation"]

    def test_the_phrase_time_stop_inside_the_invalidation_does_not_move_a_field(self):
        """By design now, not by luck: the old lookahead terminated the invalidation on the
        literal phrase."""
        out = parse_exit_line(line(inval="ignore any time stop chatter"))
        assert out["invalidation"] == "ignore any time stop chatter"
        assert out["time_stop"] == date(2026, 11, 20)

    def test_no_character_class_excludes_a_dash(self):
        src = _code("models/exit_plan.py")
        assert "[^·—" not in src
        assert '.strip("\\u00b7' not in src
        assert "strip(\"·—-\")" not in src


class TestTheSegmentIsFoundByContainmentAndBounded:
    def test_a_marker_mid_notes_is_found(self):
        """30 of 34 live lines are like this; 437 is at offset 751 of 2,649."""
        notes = "a long preamble || TA-052 " + line() + " || and a tail"
        assert has_exit_line(notes) is True
        assert find_exit_segment(notes) == line()

    def test_the_double_pipe_tail_is_cut_off(self):
        """23 of the 34 have one. Unbounded, the trailing prose lands in the stop field."""
        notes = line() + " || R-IV.600(a) context displaced out of the fixed EXIT line"
        assert find_exit_segment(notes) == line()
        assert parse_exit_line(notes)["stop_type"] == NONE

    def test_the_single_pipe_tail_is_cut_off(self):
        notes = line() + " | a second block"
        assert find_exit_segment(notes) == line()

    def test_no_tail_is_normal(self):
        """10 of the 34 run to the end of the notes."""
        assert find_exit_segment(line()) == line()

    def test_the_marker_is_the_LONGER_phrase(self):
        """Bare `EXIT:` admits prose. Measured: ids 404 and 406 read "EXIT: open in the book for
        three days after the sale..." and are not structured lines."""
        assert EXIT_LINE_MARKER == "EXIT: invalidation"
        assert has_exit_line("EXIT: open in the book for three days after the sale.") is False

    def test_absent_is_absent(self):
        for notes in (None, "", "Trimmed half; will exit the rest into strength"):
            out = parse_exit_line(notes)
            assert out["unparsed"] == ["no EXIT line"]
            assert find_exit_segment(notes) is None


class TestAMissingFieldIsEmptyNotGuessed:
    def test_a_two_field_line_leaves_the_stop_unset_and_says_so(self):
        out = parse_exit_line("EXIT: invalidation x %s time stop none" % DOT)
        assert out["stop_type"] is None
        assert "stop" in out["unparsed"]

    def test_a_one_field_line_leaves_both_unset(self):
        out = parse_exit_line("EXIT: invalidation x")
        assert out["invalidation"] == "x"
        assert out["time_stop"] is None and out["stop_type"] is None
        assert "time stop" in out["unparsed"] and "stop" in out["unparsed"]

    def test_an_unreadable_time_stop_is_named_not_dropped(self):
        out = parse_exit_line(line(ts="next Friday"))
        assert out["time_stop"] is None
        assert any("time_stop" in u for u in out["unparsed"])

    def test_stop_none_is_a_DECLARED_none_not_an_absence(self):
        """POSITIVE CONTROL. `none` written down and a field never written are different facts:
        the first says the principal chose no stop, the second says nobody said."""
        assert parse_exit_line(line(stop="none"))["stop_type"] == NONE
        assert parse_exit_line("EXIT: invalidation x %s time stop none" % DOT)["stop_type"] is None


class TestTheLiveCorpus:
    """Pinned to the measurement, so a regression against real data fails here."""

    def test_every_live_shape_parses_with_nothing_unparsed(self):
        shapes = [
            line(),
            line(inval="daily close below 18.75", ts="none", stop="none"),
            line(inval="SMH daily close above its 50-day SMA", ts="2026-10-24", stop="none"),
            line(stop="broker order"),
            line(stop="daily close"),
        ]
        for s in shapes:
            assert parse_exit_line(s)["unparsed"] == [], s

    def test_each_bounded_segment_carries_exactly_two_separators(self):
        """What makes position-indexing safe: measured 2 on all 34 live lines."""
        assert find_exit_segment(line()).count(FIELD_SEPARATOR) == 2
