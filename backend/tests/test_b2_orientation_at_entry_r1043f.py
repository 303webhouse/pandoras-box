"""R-IV.1043(f) — the B2 cut reads `orientation_at_entry`; a stock row needs it.

Three things, and the third is the one that nearly shipped broken:

  1. `orientation_at_entry` is read FIRST, as a recorded +1/-1;
  2. `DEBIT_WHITELIST` survives as the FALLBACK for option shapes, as the ruling preserved it;
  3. **A STOCK ROW IS EVALUATED ONLY WITH `orientation_at_entry` RECORDED.**

And a fourth that is really the first-boot lesson one surface over: a reader can only read a
column the QUERY selects. `orientation()` consulted `position_orientation`, which the job's
SELECT never fetched -- so that branch had never fired in production, only in tests that hand
`decide` a row directly. The job's own TA-152 comment describes exactly that gap for four other
fields. Worse, `position_orientation` is a name this module ANTICIPATED and no migration ever
created, so "just select it too" would have failed the entire query with UndefinedColumn and
taken the cut alert down.
"""
from __future__ import annotations

import os
import re

import pytest

from models import b2_cut_alert as b2

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(rel):
    with open(os.path.join(BACKEND, rel), encoding="utf-8") as fh:
        return fh.read()


# -- 1. the recorded column is read, and read FIRST ------------------------------------

def test_plus_one_is_debit():
    sign, why = b2.orientation({"orientation_at_entry": 1})
    assert sign == 1 and "orientation_at_entry" in why


def test_minus_one_is_credit():
    sign, why = b2.orientation({"orientation_at_entry": -1})
    assert sign == -1 and "orientation_at_entry" in why


def test_it_wins_over_the_structure_fallback():
    """THE ORDERING CONTROL. A recorded -1 on a row whose structure is on DEBIT_WHITELIST must
    come back -1. If the whitelist won, the column would be decorative."""
    sign, why = b2.orientation({"orientation_at_entry": -1,
                                "structure": "put_debit_spread"})
    assert sign == -1, why
    assert "orientation_at_entry" in why


def test_the_whitelist_still_answers_when_nothing_is_recorded():
    """THE PAIR. R-IV.1043(f) kept the whitelist as the fallback; a change that made the
    column mandatory everywhere would hold every option row in the book."""
    sign, why = b2.orientation({"structure": "put_debit_spread"})
    assert sign == 1 and "DEBIT_WHITELIST" in why


@pytest.mark.parametrize("bad", [0, 2, -2, "yes", "+", "1.5"])
def test_a_value_that_is_neither_plus_nor_minus_one_is_UNDETERMINED(bad):
    """The column admits two values. Anything else is unreadable, and unreadable is not a
    licence to fall through to a guess -- it returns None with the reason."""
    sign, why = b2.orientation({"orientation_at_entry": bad,
                                "structure": "put_debit_spread"})
    assert sign is None, (bad, sign, why)
    assert "orientation_at_entry" in why


def test_a_null_falls_through_rather_than_failing():
    """NULL means not recorded, which is the ordinary case for every row until POSITIONS
    writes them. It must not poison the fallback."""
    sign, why = b2.orientation({"orientation_at_entry": None,
                                "structure": "call_debit_spread"})
    assert sign == 1 and "DEBIT_WHITELIST" in why


def test_an_empty_string_is_also_not_recorded():
    sign, why = b2.orientation({"orientation_at_entry": "  ",
                                "structure": "long_call"})
    assert sign == 1, why


def test_a_recorded_string_sign_is_honoured():
    """asyncpg hands back a number, but a hand-built row or a JSON round trip may carry "1"."""
    assert b2.orientation({"orientation_at_entry": "1"})[0] == 1
    assert b2.orientation({"orientation_at_entry": "-1"})[0] == -1


# -- 2. STOCK: the column or nothing ---------------------------------------------------

def test_a_stock_row_without_the_column_is_HELD():
    sign, why = b2.orientation({"structure": "stock"})
    assert sign is None, why
    assert "orientation_at_entry" in why and "R-IV.1043(f)" in why


def test_a_stock_row_WITH_the_column_is_evaluated():
    """THE PAIR. Holding stock unconditionally would make the column pointless for the exact
    asset class the ruling named."""
    assert b2.orientation({"structure": "stock", "orientation_at_entry": -1})[0] == -1
    assert b2.orientation({"structure": "stock", "orientation_at_entry": 1})[0] == 1


def test_stock_is_checked_BEFORE_the_whitelist():
    """The rule must not depend on 'stock' being absent from DEBIT_WHITELIST. If a share shape
    were ever added there by someone who had not read R-IV.1043(f), the stock rule would
    silently stop applying -- so it is tested by putting one there."""
    original = b2.DEBIT_WHITELIST
    try:
        b2.DEBIT_WHITELIST = frozenset(set(original) | {"stock"})
        sign, why = b2.orientation({"structure": "stock"})
        assert sign is None, (
            "a share shape on DEBIT_WHITELIST overrode the stock rule: %s" % why)
        assert "SHARES" in why
    finally:
        b2.DEBIT_WHITELIST = original


def test_a_stock_composite_is_also_held():
    sign, why = b2.orientation({"structure": "stock+stock"})
    assert sign is None and "SHARES" in why


def test_a_MIXED_composite_is_still_held_as_a_composite():
    """Not a stock row and not a whitelisted shape: TA-161 §1.6 holds composites whatever
    their legs are, and that rule must survive the stock branch being added above it."""
    sign, why = b2.orientation({"structure": "stock+long_call"})
    assert sign is None
    assert "COMPOSITE" in why or "SHARES" in why


# -- 3. THE QUERY MUST SELECT WHAT THE READER READS ------------------------------------

def test_the_job_query_selects_orientation_at_entry():
    assert re.search(r"p\.orientation_at_entry", _src("jobs/b2_cut_alert_job.py")), (
        "the job reads orientation_at_entry and does not select it, so the column exists and "
        "this path cannot see it")


def test_the_route_query_selects_it_too():
    """Both surfaces adjudicate the same rows. One of them missing the column would let them
    disagree about a single row's orientation."""
    assert re.search(r"p\.orientation_at_entry", _src("api/b2_cut_status.py"))


def test_neither_query_selects_the_column_that_DOES_NOT_EXIST():
    """`position_orientation` is a name this module anticipated; no migration creates it.
    Selecting it fails the whole query with UndefinedColumn and takes the cut alert down."""
    for rel in ("jobs/b2_cut_alert_job.py", "api/b2_cut_status.py"):
        assert not re.search(r"p\.position_orientation", _src(rel)), rel


def test_position_orientation_really_is_created_nowhere():
    """The premise of the test above, asserted rather than assumed. If a migration ever adds
    it, that test's reasoning changes and this one says so."""
    hits = []
    for dirpath, _d, files in os.walk(BACKEND):
        if any(p in dirpath for p in ("__pycache__", "tests")):
            continue
        for f in files:
            if f.endswith((".py", ".sql")):
                src = _src(os.path.relpath(os.path.join(dirpath, f), BACKEND))
                if re.search(r"ADD COLUMN IF NOT EXISTS\s+position_orientation", src, re.I):
                    hits.append(f)
    assert not hits, "position_orientation is now migrated by %s -- revisit the SELECTs" % hits
