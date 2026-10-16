"""R-IV.1052(e)(c)4 + R-IV.1043(e) + R-IV.1048(c) — the owed columns, and SERVING them.

R-IV.1048(c) is the point of this file: **the migration is not done when the columns exist, it
is done when `hub_get_positions` SERVES them.** A column added and never served is a migration
that looks complete from the database side and changes nothing for any reader — which is how
five owed columns stayed owed.

Paired throughout (convention #30). The companion to "the column exists" is "the payload
carries it"; the companion to "a null is not recorded" is "a recorded value is served as
itself".
"""
from __future__ import annotations

import ast
import os
import re
from datetime import date

import pytest

from models import position_taxonomy as tx

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: R-IV.1043(e)'s five, plus (c)4's.
OWED = ("sleeve_reason", "orientation_at_entry", "x4_result", "cut_due", "cut_status")
LEVERAGE = "leverage_factor"


def _src(rel):
    with open(os.path.join(BACKEND, rel), encoding="utf-8") as fh:
        return fh.read()


def _code_only(rel):
    """Source with comments and docstrings stripped.

    REQUIRED, not tidiness. `test_this_lane_writes_no_leverage_values` first failed on the
    COMMENT naming TSLQ to explain that POSITIONS owns those figures -- the prose trap this
    register has hit four times now. ast.unparse drops comments; docstrings are removed BY
    IDENTITY (the first statement of a body), never by comparing against get_docstring(),
    which cleans indentation and so never matches.
    """
    tree = ast.parse(_src(rel))
    docs = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(getattr(body[0], "value", None), ast.Constant) \
                and isinstance(body[0].value.value, str):
            docs.add(id(body[0]))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list):
            node.body = [n for n in body if id(n) not in docs] or [ast.Pass()]
    return ast.unparse(tree)


def _startup_added_columns():
    """Every column the STARTUP path adds. Reuses main.py only — a writer-side ALTER does not
    count, which is R-IV.1052(b)."""
    return {c.lower() for c in
            re.findall(r"ADD COLUMN IF NOT EXISTS\s+([a-z_][a-z0-9_]*)", _src("main.py"), re.I)}


# -- 1. the columns are migrated, and AT STARTUP ---------------------------------------

@pytest.mark.parametrize("col", OWED + (LEVERAGE,))
def test_the_column_is_added_by_the_startup_migration(col):
    assert col in _startup_added_columns(), (
        "%s is not added at startup, so a read reaches it before any writer has run" % col)


def test_the_five_owed_columns_are_ONE_statement():
    """R-IV.1043(e) said one migration. Five separate ALTERs would each be a chance to
    half-apply, and `leverage_factor` is deliberately NOT in this statement because (c)4
    ordered it first."""
    src = _src("main.py")
    stmts = re.findall(r'"ALTER TABLE unified_positions"((?:\s*"[^"]*")+)', src)
    holding = [s for s in stmts if all(c in s for c in OWED)]
    assert len(holding) == 1, (
        "the five owed columns are not carried by exactly one ALTER (found %d)" % len(holding))
    assert LEVERAGE not in holding[0], (
        "leverage_factor belongs to (c)4's own statement, which the ruling ordered first")


# -- 2. THE RULING'S REAL BAR: the payload serves them ---------------------------------

@pytest.mark.parametrize("col", OWED + (LEVERAGE,))
def test_hub_get_positions_serves_the_column(col):
    """R-IV.1048(c) verbatim: not done until hub_get_positions SERVES all five."""
    src = _src("hub_mcp/tools/positions.py")
    assert ('"%s":' % col) in src, (
        "hub_get_positions does not serve %s -- the column exists and no reader can see it"
        % col)


def test_the_payload_keys_are_actually_in_the_served_dict():
    """A key in a comment or a docstring is not a served field. This parses the module and
    looks at real dict literals, because a scan for the string alone would pass on prose --
    the trap this register has hit repeatedly."""
    tree = ast.parse(_src("hub_mcp/tools/positions.py"))
    served = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k in node.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    served.add(k.value)
    for col in OWED + (LEVERAGE, "classification_reason_origin"):
        assert col in served, "%s appears in the file but not in any dict literal" % col


# -- 3. classification_reason_origin ---------------------------------------------------

def test_a_stored_reason_is_reported_as_stored():
    assert tx.classification_reason_origin(
        "ROTH", "STRATEGIC", "R-IV.797(c) backfill") == tx.ORIGIN_STORED


def test_the_robinhood_sentence_is_reported_as_COMPUTED():
    """THE 486 ROWS. The hub serves "not applicable: ROBINHOOD" where the book stores NULL.
    The text is right; it is also the hub's own words, and a reader must not cite it back as
    recorded provenance."""
    assert tx.classification_reason(
        "ROBINHOOD", None, None) == tx.NOT_APPLICABLE_REASON
    assert tx.classification_reason_origin(
        "ROBINHOOD", None, None) == tx.ORIGIN_COMPUTED


def test_a_classified_row_with_no_basis_is_COMPUTED_not_stored():
    """NO_BASIS_RECORDED is this module's sentence too. Reporting it as `stored` would be the
    same error one case over."""
    assert tx.classification_reason("ROTH", "STRATEGIC", None) == tx.NO_BASIS_RECORDED
    assert tx.classification_reason_origin("ROTH", "STRATEGIC", None) == tx.ORIGIN_COMPUTED
    # and a blank string is not a basis either
    assert tx.classification_reason_origin("ROTH", "STRATEGIC", "   ") == tx.ORIGIN_COMPUTED


def test_not_recorded_is_COMPUTED():
    assert tx.classification_reason("ROTH", None, None) == tx.NOT_RECORDED_REASON
    assert tx.classification_reason_origin("ROTH", None, None) == tx.ORIGIN_COMPUTED


def test_the_origin_never_invents_a_third_label():
    """R-IV.925(b). Only two values exist, and every branch must return one of them."""
    cases = [("ROBINHOOD", None, None), ("ROTH", "STRATEGIC", "x"), ("ROTH", "STRATEGIC", None),
             ("ROTH", None, None), (None, None, None), ("ROTH", "TACTICAL", "  y  "),
             ("robinhood", None, None), ("ROTH", "nonsense", "z")]
    for acct, cls, stored in cases:
        got = tx.classification_reason_origin(acct, cls, stored)
        assert got in tx.ORIGINS, "%r -> %r, which is not in %r" % ((acct, cls), got, tx.ORIGINS)


def test_origin_and_reason_agree_about_which_case_a_row_is_in():
    """THE PAIR THAT MATTERS. If the two functions branch differently, the origin describes a
    different row than the reason printed beside it. Whenever the reason is one of this
    module's OWN sentences, the origin must say `computed`, and never otherwise."""
    ours = {tx.NO_BASIS_RECORDED, tx.NOT_APPLICABLE_REASON, tx.NOT_RECORDED_REASON}
    for acct in ("ROBINHOOD", "ROTH", "FIDELITY_401A", None):
        for cls in ("STRATEGIC", "TACTICAL", None, "", "junk"):
            for stored in (None, "", "   ", "a real cited rule"):
                reason = tx.classification_reason(acct, cls, stored)
                origin = tx.classification_reason_origin(acct, cls, stored)
                if reason in ours:
                    assert origin == tx.ORIGIN_COMPUTED, (acct, cls, stored, reason, origin)
                else:
                    assert origin == tx.ORIGIN_STORED, (acct, cls, stored, reason, origin)


# -- 4. the sleeve axis now has a reason column ----------------------------------------

def test_sleeve_is_in_REASON_COLUMNS():
    """R-IV.1041(e) overruled the comment that said a sleeve reason would be a field with
    nothing in it. The map is the thing readers consult, so it has to carry the third axis."""
    assert tx.REASON_COLUMNS.get("sleeve") == "sleeve_reason"
    assert set(tx.REASON_COLUMNS) == {"classification", "bucket", "sleeve"}


def test_the_superseded_comment_is_gone():
    """A comment that contradicts the schema is worse than no comment: the next reader trusts
    it and concludes the column is a mistake."""
    src = _src("models/position_taxonomy.py")
    assert "a field with nothing to put in it" not in src or "overruled" in src


# -- 5. leverage_factor: a null is NOT 1x ----------------------------------------------

def test_leverage_factor_null_is_not_recorded_rather_than_unlevered():
    """The risk this column carries. TSLQ is -2x and SRTY and SOXS are -3x; a null read as 1x
    understates a -3x position threefold. The companion boolean is what makes the difference
    legible, so it must be served too."""
    src = _src("hub_mcp/tools/positions.py")
    assert '"leverage_factor_recorded":' in src
    m = re.search(r'"leverage_factor":(.{0,160})', src, re.S)
    assert m and "is not None" in m.group(1), (
        "leverage_factor must be served on identity, not truthiness -- `or None` would turn a "
        "stored 0 into a null: %r" % (m and m.group(1)))


def test_this_lane_writes_no_leverage_values():
    """(c)4: POSITIONS owns the figures. A backfill here would be this lane writing another
    lane's data, and the tickers are named in the ruling precisely so they are NOT guessed."""
    for rel in ("main.py", "hub_mcp/tools/positions.py", "models/position_taxonomy.py"):
        code = _code_only(rel)
        # No SQL here may write the column...
        assert not re.search(r"(UPDATE|SET|INSERT INTO)[^\n]{0,100}leverage_factor", code, re.I), \
            "%s writes leverage_factor" % rel
        # ...and nothing may assign it a value, which is the ticker-to-factor mapping the
        # ruling reserved for POSITIONS. Scanned as CODE: the hub_get_positions DESCRIPTION
        # legitimately cites TSLQ as a worked example in prose, and an earlier version of this
        # test failed on that sentence -- a tool description is prose too.
        assert not re.search(r"leverage_factor[\"']?\s*[:=]\s*-?\d", code), (
            "%s assigns a numeric leverage_factor; POSITIONS owns those figures" % rel)


# -- 6. cut_due is a date, serialised as one -------------------------------------------

def test_cut_due_is_a_DATE_column():
    """`cut_session()` returns a date, so the column that stores its due date is a DATE. A
    TIMESTAMPTZ would invite a midnight-in-which-zone question that convention #39 exists to
    stop."""
    src = _src("main.py")
    assert re.search(r"ADD COLUMN IF NOT EXISTS cut_due DATE", src)


def test_cut_due_is_serialised_not_handed_over_raw():
    """A date object is not JSON. Serving it raw works until something downstream calls
    json.dumps on the envelope."""
    src = _src("hub_mcp/tools/positions.py")
    assert re.search(r'"cut_due":', src), "cut_due is not served at all"
    # BEHAVIOUR, NOT SPELLING. This used to require the literal string "isoformat" beside the
    # key, and that exact line was taking the whole tool down with `'str' object has no
    # attribute 'isoformat'`: `_row_to_dict` is the one serialiser every position row passes
    # through and it stringifies dates before this code sees them. The test held the broken
    # implementation in place and would have failed any correct fix. What it should pin is
    # that the value comes out as a JSON-safe ISO day whatever shape it arrived in.
    from datetime import date as _date
    from datetime import datetime as _dt

    from hub_mcp.tools.positions import _iso_day

    assert _iso_day(_date(2026, 10, 24)) == "2026-10-24"       # a date object
    assert _iso_day("2026-10-24") == "2026-10-24"              # what it actually receives
    assert _iso_day("2026-10-24T13:05:00+00:00") == "2026-10-24"
    assert _iso_day(_dt(2026, 10, 24, 13, 5)) == "2026-10-24"
    assert _iso_day(None) is None
    import json

    json.dumps({"cut_due": _iso_day(_date(2026, 10, 24))})     # the original worry, direct


def test_the_b2_cut_verdicts_are_what_cut_status_would_hold():
    """Not a schema assertion -- a reminder that the vocabulary already exists. If cut_status
    ever gets a CHECK constraint it comes from here, not from a new list."""
    from models import b2_cut_alert as b2
    assert "NOT_YET" in b2.VERDICTS and "PROFITABLE" in b2.VERDICTS
