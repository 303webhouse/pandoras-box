"""The trade_date decay, and the guard R-IV.1272(b)2 asks for.

WHAT HAPPENED, measured before anything was written. Closures 1971 and 1972 were inserted
2026-10-21 12:22:44Z (06:22 MT) with `trade_date` NULL, on a production serving c331e5ee —
which CARRIES 863fae8d's writer. Their disposal lot 3947 has `fill_time`
2026-10-19T06:00:00Z, Mountain midnight on a Monday, so the app's derivation would have
produced 2026-10-19. It did not run:

    position_id   POS_IWM_20261016_R1268
    source        MANUAL        provenance  UNKNOWN        broker_ref  NULL
    two closures (1971, 1972) sharing ONE disposal lot, qty -2 split 1 + 1

THE WRITER IS NOT IN THIS REPO. There are exactly three `INSERT INTO position_lot_closures`
statements in the tree and all three set the column; a lane's own script wrote these two
directly. So patching app paths could not have stopped it, AND NEITHER CAN A SUITE GUARD — the
suite cannot see a script that is not here. That is why the fix is a database trigger, and why
this file's assertions are mostly ABOUT the trigger rather than about Python.

The same reasoning, and the same house pattern, as R-IV.517(c)'s legs trigger: "the app routes
are closed in code; this trigger closes the door for direct writes."

THE TRIGGER FILLS, THE CHECK REFUSES, and the order matters. A check alone would have REJECTED
those two inserts outright, turning a missing label into a failed write for a lane doing
legitimate work. The trigger derives first; the check only catches a row that could not be
derived at all.
"""
from __future__ import annotations

import ast
import pathlib
import re
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from models import session_day as sd                                # noqa: E402

from ._srcscan import read_source                                   # noqa: E402

MAIN = _BACKEND / "main.py"
WRITER = _BACKEND / "api" / "unified_positions.py"


def _main() -> str:
    return read_source(str(MAIN))


def _migration_block() -> str:
    """The startup block that owns this table's trade_date schema, anchored at BOTH ends."""
    src = _main()
    start = src.index("R-IV.1272(b): THE DECAY")
    end = src.index("closure trade_date migration failed", start)
    return src[start:end]


# ── the trigger exists, and covers every writer ──────────────────────────────

def test_a_before_insert_trigger_fills_the_column_for_every_writer():
    """The only thing that reaches a writer outside this repo."""
    block = _migration_block()
    assert "CREATE OR REPLACE FUNCTION position_lot_closures_trade_date()" in block
    assert "BEFORE INSERT ON position_lot_closures" in block
    assert "FOR EACH ROW EXECUTE FUNCTION position_lot_closures_trade_date()" in block


def test_the_trigger_derives_from_the_disposal_lots_own_fill_time():
    block = _migration_block()
    assert "FROM position_lots WHERE id = NEW.disposal_lot_id" in block
    assert '_TD_DATE_SQL("v_fill")' in block, (
        "the expression must be interpolated from the shared helper, not retyped")


def test_the_trigger_keeps_the_midnight_utc_discriminator():
    """MEASURED, not assumed. R-IV.1272(b)1 says "fill_time's ET date", and a blanket ET
    conversion would have dated lot 3901's trade to SUNDAY 2026-10-11:

        lot 3900  2026-10-09 00:00:00 UTC  as written 10-09 Fri  ET 10-08 Thu
        lot 3901  2026-10-12 00:00:00 UTC  as written 10-12 Mon  ET 10-11 SUN

    A midnight-UTC stamp is a DAY WRITTEN DOWN and converting it moves it backwards. The
    ruling's ET rule applies to a real fill time; a written-down day is taken as written.
    """
    assert "CASE WHEN" in sd.session_date_sql()
    assert "AT TIME ZONE 'UTC')::time = TIME '00:00:00'" in sd.session_date_sql()
    assert "AT TIME ZONE 'UTC')::date" in sd.session_date_sql()
    assert "AT TIME ZONE 'America/New_York')::date" in sd.session_date_sql()
    assert "SUNDAY" in _main().upper()


def test_the_basis_comes_from_the_same_discriminator_as_the_date():
    """Two readings, two labels, one discriminator. Hard-coding one label would have marked
    every day-written-down row as a converted one -- a caption lying about its field."""
    for col in ("fill_time", "v_fill"):
        d, b = sd.session_date_sql(col), sd.session_basis_sql(col)
        cond = "(%s AT TIME ZONE 'UTC')::time = TIME '00:00:00'" % col
        assert cond in d and cond in b, col
    assert sd.BASIS_FILL_TIME_DAY in sd.session_basis_sql()
    assert sd.BASIS_FILL_TIME_ET in sd.session_basis_sql()


def test_the_trigger_is_dropped_before_it_is_created_so_a_redeploy_replaces_it():
    """`CREATE TRIGGER` has no IF NOT EXISTS. Without the drop, every redeploy would raise and
    the house pattern's per-statement catch would swallow it — leaving whichever version
    happened to be installed first."""
    block = _migration_block()
    assert block.index("DROP TRIGGER IF EXISTS trg_position_lot_closures_trade_date") \
        < block.index("CREATE TRIGGER trg_position_lot_closures_trade_date")


def test_the_check_is_the_backstop_and_is_not_valid():
    """NOT VALID binds NEW rows only. 840-odd historical closures predate the column and are
    history, not violations — validating against them would fail the migration outright."""
    block = _migration_block()
    assert "ADD CONSTRAINT position_lot_closures_trade_date_known" in block
    assert "CHECK (trade_date IS NOT NULL OR trade_date_reason IS NOT NULL)" in block
    assert "NOT VALID" in block


def test_the_trigger_runs_before_the_check_so_a_derivable_row_is_filled_not_refused():
    """Stated as an assertion because the ORDER is the whole design: BEFORE INSERT triggers fire
    ahead of constraint evaluation, so a row the trigger can fill never reaches the check."""
    block = _migration_block()
    assert "BEFORE INSERT" in block
    assert "turns a missing label into a failed write" in _main()


# ── the one exemption, and the reason that makes it a decision ───────────────

def test_a_stated_reason_is_left_alone_which_is_the_rulings_one_exemption():
    """R-IV.1272(b)2: unless the lot is MANUAL with a stated reason. The reason is what makes
    an absent date a decision rather than an omission, so the trigger returns early on it."""
    block = _migration_block()
    assert "IF NEW.trade_date IS NOT NULL OR NEW.trade_date_reason IS NOT NULL THEN" in block
    assert "RETURN NEW" in block


def test_both_new_columns_are_migrated():
    block = _migration_block()
    assert "ADD COLUMN IF NOT EXISTS trade_date_basis TEXT" in block
    assert "ADD COLUMN IF NOT EXISTS trade_date_reason TEXT" in block


def test_the_exemption_cannot_be_taken_by_leaving_the_column_null():
    """The check demands one or the other. A writer that wants no date must SAY SO; silence is
    exactly what produced 1971 and 1972."""
    block = _migration_block()
    assert "trade_date IS NOT NULL OR trade_date_reason IS NOT NULL" in block


# ── the app paths still set it, and label it ─────────────────────────────────

def test_every_app_insert_sets_both_the_date_and_its_basis():
    src = read_source(str(WRITER))
    tree = ast.parse(src)
    lits = [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and "INSERT INTO position_lot_closures" in n.value]
    assert len(lits) == 3, len(lits)
    for sql in lits:
        assert "trade_date, trade_date_basis)" in sql, sql[:260]
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "trade_date_values"]
    assert len(calls) == 3, len(calls)


def test_the_app_and_the_trigger_cannot_drift():
    """The trigger's body is BUILT FROM the same helpers the app paths use, interpolated rather
    than retyped, so there is one author for the expression. A trigger in ET and an app path in
    Mountain would date the same fill to two different sessions depending on which wrote it."""
    assert "America/New_York" in sd.session_date_sql("fill_time")
    assert "America/Denver" not in sd.session_date_sql("fill_time")
    block = _migration_block()
    assert "_TD_DATE_SQL" in block and "_TD_BASIS_SQL" in block
    assert "session_basis_sql as _TD_BASIS_SQL" in _main()
    assert "session_date_sql as _TD_DATE_SQL" in _main()


def test_the_basis_labels_are_constants_used_by_both():
    assert sd.BASIS_FILL_TIME_ET == "FILL_TIME_ET"
    assert sd.BASIS_FILL_TIME_DAY == "FILL_TIME_DAY"
    vals = sd.trade_date_values(2)
    assert sd.BASIS_FILL_TIME_ET in vals and sd.BASIS_FILL_TIME_DAY in vals


def test_the_preferred_source_is_recorded_as_absent_rather_than_invented():
    """R-IV.1272(b)1 prefers "the disposal lot's broker action date" and `position_lots` HAS NO
    SUCH COLUMN — its date fields are `fill_time` and `verified_at`, and verified_at's own
    comment says it is "the time of the MATCH, never of the fill". The label exists and is
    unused, with the reason written down, rather than a nullable column implying a second
    source is available (R-IV.925(b))."""
    assert sd.BASIS_BROKER_ACTION == "BROKER_ACTION"
    src = read_source(str(_BACKEND / "models" / "session_day.py"))
    assert "HAS NO SUCH" in src.upper()
    assert "verified_at" in src
    assert sd.BASIS_BROKER_ACTION not in sd.trade_date_values(2), (
        "it must not be emitted while no column backs it")


# ── the ET rule is a different question from Abacus's, and Abacus is untouched ──

def test_a_trade_date_is_an_exchange_session_not_the_principals_day():
    """`day_sql` answers which of the PRINCIPAL'S days a value landed on, measured over the 557
    census rows. A trade date answers which EXCHANGE SESSION the trade was in. They differ: a
    fill at 05:00 UTC is 23:00 the previous day in Mountain and 01:00 the SAME day in Eastern,
    so using the census rule for a trade date would date a late fill to the session before it."""
    assert "America/New_York" in sd.session_date_sql()
    assert "America/Denver" in sd.day_sql("x")
    assert "America/Denver" not in sd.session_date_sql()
    # BOTH keep the midnight-UTC discriminator -- that part of R-IV.726 is about the COLUMN's
    # mixed contents, not about whose clock the conversion uses, and lot 3901 proved it.
    assert "CASE WHEN" in sd.day_sql("x") and "CASE WHEN" in sd.session_date_sql()


def test_abacus_window_predicate_is_byte_identical():
    """It is what Abacus windows its period figures on. Moving it would move trades between
    periods — the silent reclassification its own test was written to prevent."""
    assert sd.day_sql("x") == (
        "(CASE WHEN (x AT TIME ZONE 'UTC')::time = TIME '00:00:00' "
        "THEN (x AT TIME ZONE 'UTC')::date "
        "ELSE (x AT TIME ZONE 'America/Denver')::date END)")
    from api.abacus import _day_sql
    assert _day_sql("x") == sd.day_sql("x")


# ── the measured case, as a regression ───────────────────────────────────────

@pytest.mark.parametrize("utc,expected", [
    # Lot 3947, the one that decayed: Mountain midnight on a Monday.
    ("2026-10-19T06:00:00+00:00", "2026-10-19"),
    # 05:00 UTC — the case where ET and Mountain disagree. ET says the 19th; Mountain would
    # say the 18th, and the 18th was a Sunday, so the census rule would have dated this trade
    # to a day the exchange was shut.
    ("2026-10-19T05:00:00+00:00", "2026-10-19"),
    # A plain intraday fill.
    ("2026-10-19T18:30:00+00:00", "2026-10-19"),
    # 23:30 ET is still the same session's calendar day.
    ("2026-10-20T03:30:00+00:00", "2026-10-19"),
])
def test_the_et_date_of_the_fills_that_matter(utc, expected):
    import datetime as _dt
    from zoneinfo import ZoneInfo
    ts = _dt.datetime.fromisoformat(utc)
    assert ts.astimezone(ZoneInfo("America/New_York")).date().isoformat() == expected


def test_the_decay_is_recorded_with_its_measurements_not_only_its_fix():
    """The ids, the lot, the fill_time and the fact that the writer is outside the repo. A fix
    whose cause is not written down is one the next reader cannot check."""
    block = _main()
    for fact in ("1971 and 1972", "3947", "2026-10-19T06:00:00Z", "NOT IN THIS REPO",
                 "POS_IWM_20261016_R1268"):
        assert fact in block, fact


def test_the_migration_has_its_own_try_at_warning():
    """The startup block it sits in ends in `except Exception` at DEBUG, so a failure anywhere
    in it is invisible AND every statement after it silently never runs."""
    # ANCHORED ON CONTENT AT BOTH ENDS, not on a character count. The first version of this
    # assertion took a fixed 5,200-character window and fell short of the handler it was
    # looking for — a locator sized by guess, which is the same fault as a line-numbered edit
    # (Convention #43). The end anchor is the handler's own message.
    src = _main()
    start = src.index("R-IV.1272(b): THE DECAY")
    end = src.index("closure trade_date migration failed", start)
    window = src[start:end + 80]
    assert "except Exception as _td_err" in window
    assert "logger.warning" in window
