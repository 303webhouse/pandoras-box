"""`notables_log` and `notables_outcomes`. R-IV.1259(h), wired under R-IV.1265(g)2.

WHAT THESE PIN, and why each one is an assertion rather than a comment:

1. THE DROPS ARE LOGGED. (h) says "every candidate, including dropped ones with the reason". A
   log that recorded only what it displayed would make its own cap, its per-ticker rule and its
   PYTHIA gate unauditable — the denominator of "what share was shown" would be unknowable.
   Same finding as `position_watch_events`.

2. `shown` AND `drop_reason` AGREE, IN THE DATABASE TOO. `row_for` refuses both bad shapes, but
   the writer is not the only thing that can insert: a backfill, a repair script or a future
   caller all bypass Python. The CHECK constraint is the one that holds for them.

3. AN OUTCOME IN EM UNITS KEEPS ITS DENOMINATOR. "1.4 EM" means nothing without the EM it was
   divided by, and a reader with only the ratio cannot tell a big move in a quiet name from a
   small one in a volatile one.

4. NO OPTION P&L, anywhere. (h) is explicit, and there is no position to compute it from: the
   strip highlights no rung (R-IV.1259(f)), so a P&L figure would be a claim about a trade
   nobody placed.

5. THE LOG IS APPEND-ONLY except for the tap. A log that rewrites its own history is a record of
   what we believe now, not of what we showed then.
"""
from __future__ import annotations

import ast
import datetime as _dt
import json
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from models import notables_log as nl                               # noqa: E402
from models import notables_strip as ns                             # noqa: E402

from ._srcscan import read_source                                   # noqa: E402

TODAY = _dt.date(2026, 10, 19)
NOW = _dt.datetime(2026, 10, 19, 14, 41, tzinfo=_dt.timezone.utc)


def _shown(**kw):
    base = dict(session_date=TODAY, detected_at=NOW, card_kind="VALUE_MOVED", ticker="SPY",
                shown=True)
    base.update(kw)
    return nl.row_for(**base)


# ── 1 · the drops are logged, with a reason ──────────────────────────────────

def test_a_dropped_candidate_needs_a_reason():
    with pytest.raises(ValueError) as e:
        nl.row_for(session_date=TODAY, detected_at=NOW, card_kind="VALUE_MOVED",
                   ticker="SPY", shown=False)
    assert "must say why" in str(e.value)


def test_a_shown_card_may_not_carry_a_drop_reason():
    with pytest.raises(ValueError) as e:
        _shown(drop_reason=nl.DROP_CAP_REACHED)
    assert "cannot carry a drop reason" in str(e.value)


def test_a_dropped_candidate_is_a_row_and_not_an_absence():
    row = nl.row_for(session_date=TODAY, detected_at=NOW, card_kind="FAILED_BREAK",
                     ticker="IWM", shown=False, drop_reason=nl.DROP_CAP_REACHED)
    assert row["shown"] is False and row["drop_reason"] == nl.DROP_CAP_REACHED
    assert row["ticker"] == "IWM" and row["card_kind"] == "FAILED_BREAK"


def test_every_drop_reason_is_a_named_constant_and_they_are_distinct():
    """R-IV.925(b): do not invent labels. A free-text reason could not be grouped by, which is
    the one thing the drop log is for."""
    assert len(set(nl.DROP_REASONS)) == len(nl.DROP_REASONS)
    for r in nl.DROP_REASONS:
        assert r and r == r.strip() and len(r) > 15, r


def test_the_five_card_kinds_are_the_rulings_and_an_invented_one_is_refused():
    assert nl.CARD_KINDS == ("LOUD_MOVE", "VALUE_MOVED", "FAILED_BREAK", "TREND_CHANGE",
                             "ROTATION_SHIFT")
    with pytest.raises(ValueError):
        _shown(card_kind="INTERESTING")


def test_a_lowercase_kind_is_accepted_and_stored_upper():
    assert _shown(card_kind="value_moved")["card_kind"] == "VALUE_MOVED"


# ── 2 · the constraint holds for writers that are not this module ────────────

def test_the_database_itself_refuses_a_disagreeing_row():
    """Not only `row_for`. The CHECK covers the backfill, the repair script and the caller that
    does not exist yet."""
    assert "notables_log_drop_reason_agrees" in nl.DDL_CHECK
    sql = " ".join(nl.DDL_CHECK.split())
    assert "shown IS TRUE AND drop_reason IS NULL" in sql
    assert "shown IS FALSE AND drop_reason IS NOT NULL" in sql


def test_the_migration_creates_both_tables_and_is_idempotent_by_construction():
    for ddl in (nl.DDL, nl.OUTCOMES_DDL):
        assert "CREATE TABLE IF NOT EXISTS" in ddl
    for idx in (nl.DDL_INDEX, nl.OUTCOMES_DDL_INDEX):
        assert "CREATE INDEX IF NOT EXISTS" in idx
    assert "ON CONFLICT (log_id, horizon_days) DO UPDATE" in nl._OUTCOME_INSERT


def test_the_migration_runs_in_its_own_try_at_warning():
    """The startup block it sits in ends in `except Exception` logged at DEBUG, so a failure
    anywhere in that block is invisible AND every statement after it silently never runs. That
    is how a migration comes to be shipped and absent at once — which is exactly what happened
    to this column's neighbour, `trade_date`, whose writer was missing for a day."""
    src = read_source(str(_BACKEND / "main.py"))
    i = src.index("from models.notables_log import migrate")
    window = src[i - 900:i + 600]
    assert "try:" in window and "except Exception as _nb_err" in window
    assert "logger.warning" in window


def test_the_tables_are_created_in_the_same_deploy_as_the_writer():
    """(h): "Both tables are created in the deploy that writes to them." The writer is this
    module's `insert`, and the migration is this module's too — so they cannot ship apart."""
    src = read_source(str(_BACKEND / "models" / "notables_log.py"))
    tree = ast.parse(src)
    names = {n.name for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert {"migrate", "insert", "record_outcome"} <= names


# ── 3 · outcomes in EM units, with the denominator ───────────────────────────

def test_a_move_in_em_is_the_move_over_the_em_and_both_are_stored():
    r = nl.outcome_row(log_id=1, horizon_days=3, move_pct=2.8, em_pct=2.0, basis="t")
    assert r["move_in_em"] == 1.4
    assert r["move_pct"] == 2.8 and r["em_pct"] == 2.0, "the denominator must be kept"
    assert r["unavailable_reason"] is None


def test_a_zero_or_missing_em_yields_no_ratio_and_says_why():
    """Never a division. And never a 0 standing in for "could not compute"."""
    for em in (0, 0.0, None):
        r = nl.outcome_row(log_id=1, horizon_days=1, move_pct=1.0, em_pct=em, basis="t")
        assert r["move_in_em"] is None
        assert "expected move was zero or unavailable" in r["unavailable_reason"]


def test_an_ungraded_horizon_says_there_is_no_close_yet():
    r = nl.outcome_row(log_id=1, horizon_days=5, move_pct=None, em_pct=2.0, basis="t")
    assert r["move_in_em"] is None and "no close for this horizon yet" in r["unavailable_reason"]


def test_the_three_horizons_are_the_rulings_and_a_fourth_is_refused():
    assert nl.HORIZONS == (1, 3, 5)
    with pytest.raises(ValueError):
        nl.outcome_row(log_id=1, horizon_days=2, move_pct=1.0, em_pct=1.0, basis="t")


def test_a_horizon_that_cannot_be_graded_is_an_absent_row_not_a_null_in_a_complete_one():
    """One row per horizon, keyed (log_id, horizon_days). Three columns in one row would make an
    ungraded +5d indistinguishable from a graded one whose move was unknown."""
    assert "horizon_days    SMALLINT    NOT NULL" in nl.OUTCOMES_DDL
    assert "UNIQUE (log_id, horizon_days)" in nl.OUTCOMES_DDL


# ── 4 · no option P&L, anywhere ──────────────────────────────────────────────

@pytest.mark.parametrize("forbidden", ["option_pnl", "contract_pnl", "premium_pnl",
                                       "realized", "option_return"])
def test_the_outcomes_table_has_no_option_pnl_column(forbidden):
    """(h) is explicit. And there is no position to compute it from: the strip highlights no
    rung, so a P&L figure would be a claim about a trade nobody placed."""
    cols = nl.OUTCOMES_DDL.lower()
    assert forbidden not in cols, forbidden


def test_the_outcome_is_the_stocks_move_and_the_docstring_says_so():
    src = read_source(str(_BACKEND / "models" / "notables_log.py"))
    assert "CARRIES NO OPTION P&L" in src


# ── 5 · append-only, except the tap ──────────────────────────────────────────

def test_the_only_update_statement_in_the_module_is_the_tap():
    """A log that rewrites its own history is a record of what we believe now, not of what we
    showed then. Read from the PARSED tree: the module's prose discusses UPDATE, and a raw text
    scan would fail on the sentence explaining the rule it enforces."""
    tree = ast.parse(read_source(str(_BACKEND / "models" / "notables_log.py")))
    updates = [n.value for n in ast.walk(tree)
               if isinstance(n, ast.Constant) and isinstance(n.value, str)
               and "UPDATE notables_log" in n.value]
    assert len(updates) == 1, updates
    assert "SET tap = $2, tapped_at = NOW()" in updates[0]
    assert "shown" not in updates[0] and "drop_reason" not in updates[0]


def test_an_aged_or_re_reasoned_card_is_a_new_row_pointing_at_the_first():
    assert "supersedes      BIGINT REFERENCES notables_log(id)" in nl.DDL
    assert _shown(supersedes=11)["supersedes"] == 11


def test_the_three_taps_are_the_rulings_and_a_fourth_is_refused():
    assert nl.TAPS == ("looked", "useful", "noise")
    import asyncio

    class _Conn:
        async def execute(self, *a):
            return None
    with pytest.raises(ValueError):
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            nl.record_tap(_Conn(), 1, "good"))


def test_a_fresh_row_carries_no_tap():
    r = _shown()
    assert r["tap"] is None and r["tapped_at"] is None


# ── the frozen inputs and the rung mid ───────────────────────────────────────

def test_the_inputs_are_frozen_as_json_and_the_rung_mid_is_its_own_column():
    """(h): frozen inputs, timestamps and the 1x rung's mid. The mid is a column rather than a
    key inside `inputs` because it is the number a later reader compares against, and it must
    not have to be re-derived from a chain that has since moved."""
    r = _shown(inputs={"ib_high": 679.1, "value_high": 677.65}, rung_1x_mid=0.90)
    assert json.loads(r["inputs"])["ib_high"] == 679.1
    assert r["rung_1x_mid"] == 0.90
    assert "rung_1x_mid     NUMERIC" in nl.DDL


def test_a_date_that_is_not_serialisable_still_freezes():
    """`default=str` rather than a raised TypeError: losing the whole frozen input set because
    one value is a date would be the log failing at the moment it matters."""
    r = _shown(inputs={"session": TODAY})
    assert json.loads(r["inputs"])["session"] == "2026-10-19"


def test_the_iv_band_must_be_one_of_the_ruled_three():
    """R-IV.1265(c). A stored band outside the three would be grouped by and reported."""
    assert _shown(iv_band=ns.IV_MID)["iv_band"] == "IV MID"
    with pytest.raises(ValueError):
        _shown(iv_band="RICH")


def test_the_session_date_is_a_session_and_created_at_is_the_write_instant():
    """Convention #39, and the fault `position_lot_closures.trade_date` was created to fix one
    table over: a write timestamp is not a session, and one column cannot be both."""
    assert "session_date    DATE        NOT NULL" in nl.DDL
    assert "created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()" in nl.DDL
    assert "detected_at     TIMESTAMPTZ NOT NULL" in nl.DDL
