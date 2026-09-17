"""R-IV.444(b) — option rows become positions with legs, and nothing is dropped quietly.

FAIL-FIRST against the pre-2026-09-17 tree: no legs table, no outcome table, and a three-leg
structure could only be stored as two rows or as a sentence in a note.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
from datetime import date
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from database import legs_migration as LM  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "039_position_legs.sql"
BOOT = ROOT / "backend" / "database" / "postgres_client.py"

EXP = date(2026, 10, 16)


def _row(**kw):
    base = {"position_id": "POS_X", "structure": "put_debit_spread", "long_strike": 45,
            "short_strike": 40, "expiry": EXP, "quantity": 8, "asset_type": "OPTION"}
    base.update(kw)
    return base


# --- the mapping, as measured off the book -------------------------------------------------
def test_the_bought_leg_is_long_strike_and_the_sold_leg_is_short_strike():
    outcome, legs, _ = LM.classify(_row())
    assert outcome == LM.MIGRATED and len(legs) == 2
    assert legs[0] == {"leg_seq": 1, "option_type": "PUT", "side": "LONG", "strike": 45.0,
                       "expiry": EXP, "qty": 8.0, "price": None}
    assert legs[1]["side"] == "SHORT" and legs[1]["strike"] == 40.0


def test_a_call_spread_carries_calls_and_keeps_the_same_side_rule():
    _, legs, _ = LM.classify(_row(structure="call_debit_spread", long_strike=100,
                                  short_strike=110))
    assert [l["option_type"] for l in legs] == ["CALL", "CALL"]
    assert legs[0]["strike"] == 100.0 and legs[1]["side"] == "SHORT"


def test_a_credit_spread_sells_the_strike_stored_as_short():
    """The one live put credit spread holds the sold (higher) put in short_strike."""
    _, legs, _ = LM.classify(_row(structure="put_credit_spread", long_strike=30,
                                  short_strike=35))
    assert legs[1]["side"] == "SHORT" and legs[1]["strike"] == 35.0


def test_a_single_leg_structure_produces_one_leg():
    outcome, legs, _ = LM.classify(_row(structure="long_put", short_strike=None))
    assert outcome == LM.MIGRATED and len(legs) == 1 and legs[0]["side"] == "LONG"


def test_no_leg_is_given_a_price_the_book_never_recorded():
    """A vertical stores its NET; the split is not in the row and is not invented."""
    _, legs, _ = LM.classify(_row())
    assert all(l["price"] is None for l in legs)


# --- every row gets an outcome (R-IV.432(c)) ----------------------------------------------
def test_a_row_with_no_strikes_is_excluded_by_name_and_left_alone():
    outcome, legs, detail = LM.classify(_row(structure=None, long_strike=None,
                                             short_strike=None, expiry=None))
    assert outcome == LM.NO_STRIKES and legs == []
    assert "no strike" in detail


def test_a_structure_with_no_expiry_cannot_become_a_leg():
    outcome, legs, detail = LM.classify(_row(expiry=None))
    assert outcome == LM.NO_EXPIRY and legs == []
    assert "not a leg" in detail


def test_a_structure_with_more_legs_than_columns_waits_rather_than_being_halved():
    """R-IV.445(c): pending-capability, not a failure. It needs someone to type the legs,
    not a source to be found."""
    outcome, legs, detail = LM.classify(_row(structure="iron_condor"))
    assert outcome == LM.PENDING_CAPABILITY and legs == []
    assert "more legs" in detail and "hand-entry" in detail


def test_a_leg_that_lives_in_a_note_blocks_the_row_rather_than_publishing_two():
    """NVDA 415 holds a third leg in prose. Migrating the two stored strikes would assert a
    2-leg position where a 3-leg one exists — worse than not migrating it."""
    outcome, legs, detail = LM.classify(_row(position_id="POS_NVDA_20260911_001150"))
    assert outcome == LM.PENDING_CAPABILITY and legs == []
    assert "$50 put" in detail and "hand-entry" in detail


def test_an_unmapped_structure_is_not_forced_through_the_vertical_shape():
    outcome, legs, _ = LM.classify(_row(structure="butterfly"))
    assert outcome != LM.MIGRATED and legs == []


# --- the ruled XLF group --------------------------------------------------------------------
def test_the_xlf_group_is_one_position_with_three_legs():
    assert len(LM.XLF_LEGS) == 3
    strikes = [(l[1], l[2], l[3]) for l in LM.XLF_LEGS]
    assert strikes == [("PUT", "LONG", 45.0), ("PUT", "SHORT", 40.0), ("PUT", "LONG", 30.0)]
    assert all(l[4] == 10 for l in LM.XLF_LEGS), "8 from the June vintage plus 2 from 09-01"


def test_the_rows_that_fed_it_are_named_on_its_face():
    assert "id 300" in LM.XLF_DETAIL and "id 301" in LM.XLF_DETAIL and "id 420" in LM.XLF_DETAIL
    assert LM.XLF_SURVIVOR not in LM.XLF_MERGED
    assert len(LM.XLF_MERGED) == 2


def test_the_merged_rows_are_marked_rather_than_deleted():
    """Nothing is removed from the book by a schema migration."""
    src = (ROOT / "backend" / "database" / "legs_migration.py").read_text(encoding="utf-8")
    assert "DELETE" not in src.upper().replace("DELETE_", "")
    assert "MERGED_INTO" in src


def test_no_per_leg_price_is_asserted_for_the_merged_group():
    assert "no per-leg price is asserted" in LM.XLF_DETAIL


# --- the runner is idempotent ---------------------------------------------------------------
class _Txn:
    async def __aenter__(self): return None
    async def __aexit__(self, *a): return False


def _conn(rows, recorded=None):
    c = MagicMock()
    c.writes = []
    recorded = recorded or set()

    async def fetch(sql, *args):
        if "position_legs_migration m" in sql or "FROM unified_positions p" in sql:
            return [dict(r) for r in rows]
        return []

    async def fetchval(sql, *args):
        return 1 if args and args[0] in recorded else None

    async def execute(sql, *args):
        c.writes.append((" ".join(sql.split()), args))

    c.fetch = fetch
    c.fetchval = fetchval
    c.execute = execute
    c.transaction = lambda: _Txn()
    return c


def test_the_runner_records_an_outcome_for_every_row_it_sees():
    rows = [_row(position_id="POS_A"), _row(position_id="POS_B", structure=None,
                                            long_strike=None, short_strike=None, expiry=None)]
    c = _conn(rows)
    counts = asyncio.run(LM.run(c))
    assert counts.get(LM.MIGRATED) == 1 and counts.get(LM.NO_STRIKES) == 1
    records = [w for w in c.writes if "INSERT INTO position_legs_migration" in w[0]]
    assert len(records) == 2, "a row with no legs still gets a line"


def test_a_row_already_recorded_is_never_reconsidered():
    """The outcome table is the guard, not the legs: an excluded row has no legs by
    definition, so guarding on legs would reconsider it on every boot."""
    src = (ROOT / "backend" / "database" / "legs_migration.py").read_text(encoding="utf-8")
    assert "NOT EXISTS (SELECT 1 FROM position_legs_migration m" in " ".join(src.split())
    assert "ON CONFLICT (position_id) DO NOTHING" in src


def test_the_migration_and_boot_agree():
    sql = MIGRATION.read_text(encoding="utf-8")
    boot = BOOT.read_text(encoding="utf-8")
    for token in ("position_legs", "position_legs_migration", "UNIQUE (position_id, leg_seq)",
                  "option_type IN ('CALL', 'PUT')", "side IN ('LONG', 'SHORT')"):
        assert token in sql and token in boot, token
    assert "-- DOWN" in sql
    assert "legs_migration import run" in boot, "boot must run the expansion it created"


# --- pending-capability is not failure (R-IV.445(c)) ---------------------------------------
def test_the_two_classes_are_kept_apart():
    """An UNMIGRATABLE row needs a SOURCE; a PENDING_CAPABILITY row needs someone to type what
    the note already says. Filing the second under the first describes work as damage."""
    assert LM.PENDING_CAPABILITY != LM.NO_STRIKES
    no_src, _, _ = LM.classify(_row(structure=None, long_strike=None, short_strike=None,
                                    expiry=None))
    pending, _, _ = LM.classify(_row(structure="iron_condor"))
    assert no_src.startswith("UNMIGRATABLE") and pending == "PENDING_CAPABILITY"


def test_the_first_labels_are_re_filed_rather_than_left_behind():
    src = (ROOT / "backend" / "database" / "legs_migration.py").read_text(encoding="utf-8")
    flat = " ".join(src.split())
    assert "UPDATE position_legs_migration SET outcome = $1 WHERE outcome = ANY($2::text[])" in flat
    assert "UNMIGRATABLE_LEGS_EXCEED_STRIKES" in src and "UNMIGRATABLE_LEG_IN_NOTES" in src


def test_an_unmapped_structure_is_entered_not_guessed():
    outcome, legs, detail = LM.classify(_row(structure="butterfly"))
    assert outcome == LM.PENDING_CAPABILITY and legs == []
    assert "not guessed" in detail
