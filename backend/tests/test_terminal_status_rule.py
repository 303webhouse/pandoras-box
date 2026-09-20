"""R-IV.453/454 — a terminal status needs a recorded exit, and a record correction is not a fill.

FAIL-FIRST against the pre-2026-09-18 tree: the PATCH could set CLOSED/EXPIRED/DUPLICATE_OF
with nothing beside it; a quantity edit recomputed cost_basis AND moved the account's cash
(measured: NVDA 415, qty 2 -> 3, debited ROBINHOOD 16.00 and rewrote 32.00 to 48.00); the
expiry sweep ran on GET and recorded no result; nothing at the database stopped a direct write
from ending a position with no exit.
"""
from __future__ import annotations

import inspect
import pathlib
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

ROOT = pathlib.Path(__file__).resolve().parents[2]
API = ROOT / "backend" / "api" / "unified_positions.py"
MIGRATION = ROOT / "migrations" / "044_terminal_status_needs_exit.sql"
BOOT = ROOT / "backend" / "database" / "postgres_client.py"
JOBS = ROOT / "backend" / "jobs" / "stable_jobs.py"


# --- the PATCH: a record correction, never a fill, never an ending --------------------------
def test_every_terminal_status_names_the_path_that_records_it():
    from api.unified_positions import TERMINAL_VIA_PATH
    assert set(TERMINAL_VIA_PATH) == {"CLOSED", "EXPIRED", "DUPLICATE_OF"}
    assert "/close" in TERMINAL_VIA_PATH["CLOSED"]
    assert "UNKNOWN" in TERMINAL_VIA_PATH["EXPIRED"]
    assert "retire-duplicate" in TERMINAL_VIA_PATH["DUPLICATE_OF"]


@pytest.mark.parametrize("target", ["CLOSED", "closed", " Expired ", "DUPLICATE_OF"])
def test_the_patch_refuses_to_end_a_position(monkeypatch, target):
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from api import unified_positions as U

    row = {"position_id": "p1", "status": "OPEN", "ticker": "X", "cost_basis": 32,
           "account": "ROBINHOOD"}

    class _Acq:
        def __init__(self, c): self.c = c
        async def __aenter__(self): return self.c
        async def __aexit__(self, *a): return False
        def __call__(self): return self

    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=row)
    pool = MagicMock()
    pool.acquire = _Acq(conn)
    monkeypatch.setattr(U, "get_postgres_client", AsyncMock(return_value=pool))
    monkeypatch.setattr(U, "_row_to_dict", lambda r: dict(r))
    with pytest.raises(HTTPException) as e:
        asyncio.new_event_loop().run_until_complete(
            U.update_position("p1", U.UpdatePositionRequest(status=target)))
    assert e.value.status_code == 400
    assert "not set by an edit" in e.value.detail


def test_reopening_is_not_what_the_rule_governs():
    src = inspect.getsource(__import__("api.unified_positions", fromlist=["x"]).update_position)
    assert "if target in TERMINAL_VIA_PATH:" in src, "OPEN is not in the map, so it passes"


def test_a_quantity_edit_no_longer_moves_cash_or_rewrites_the_basis():
    """The measured instance: qty 2 -> 3 debited 16.00 and rewrote 32.00 to 48.00."""
    from api import unified_positions as U
    src = inspect.getsource(U.update_position)
    assert "_adjust_account_cash(" not in src, "an edit is not a fill"
    assert "UPDATE unified_positions SET cost_basis" not in src
    assert "A RECORD CORRECTION IS NOT A FILL" in src


# --- the expiry sweep ---------------------------------------------------------------------
def test_the_sweep_records_the_expiry_date_and_an_explicit_unknown():
    from api import unified_positions as U
    src = inspect.getsource(U._sweep_expired_positions)
    # R-IV.464(a): the day it expired, in the principal's timezone -- expiry::timestamptz would
    # stamp 00:00 UTC, which renders as the day before on every surface he reads.
    assert "expiry::timestamp AT TIME ZONE 'America/Denver'" in src
    assert "trade_outcome = COALESCE(trade_outcome, 'UNKNOWN')" in src
    assert "set_config('app.actor'" in src, "the audit names the sweep as the actor"


def test_no_read_path_runs_the_sweep():
    """A request to LOOK at the book could end positions in it."""
    from api import unified_positions as U
    for fn in (U._compute_positions, U.portfolio_summary):
        assert "await _sweep_expired_positions()" not in inspect.getsource(fn), fn.__name__


def test_the_manual_endpoint_and_the_schedule_share_one_function():
    from api import unified_positions as U
    assert "await _sweep_expired_positions()" in inspect.getsource(U.expire_sweep)
    jobs = JOBS.read_text(encoding="utf-8")
    assert "from api.unified_positions import _sweep_expired_positions" in jobs
    assert "EXPIRY_SWEEP_JOB = \"expiry_sweep\"" in jobs
    assert "await _record(EXPIRY_SWEEP_JOB, _run, session_date=day)" in jobs


# --- the database guard for direct writes ---------------------------------------------------
def test_the_trigger_fires_on_the_transition_not_on_every_write():
    """A CHECK would freeze the 23 historical rows; the rule is about REACHING terminal."""
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").split())
    assert "BEFORE INSERT OR UPDATE OF status ON unified_positions" in sql
    assert "TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM NEW.status" in sql


def test_any_one_recorded_exit_satisfies_it_including_unknown():
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").split())
    assert ("NEW.exit_price IS NULL AND NEW.realized_pnl IS NULL AND NEW.trade_outcome IS NULL"
            in sql)
    assert "UNKNOWN is a valid one" in sql


def test_the_refusal_names_the_row_and_the_paths():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "would reach % with no exit recorded" in sql
    assert "Use the close or reduce path" in sql


def test_boot_mirrors_it_one_statement_at_a_time():
    boot = BOOT.read_text(encoding="utf-8")
    assert "trg_unified_positions_terminal_needs_exit" in boot
    i = boot.index("terminal-needs-exit function")
    loop_end = boot.index("except Exception as e:", i)
    assert "for _label, _sql in" in boot[i - 3000:i] and loop_end - i < 12000, (
        "a refused statement must never end the rest of the bootstrap (R-IV.449)")


def test_the_known_consequence_is_on_the_face():
    """The CSV sync's close writes CLOSED with its own date and no result; it is refused now."""
    assert "sync_rh_csv.py" in MIGRATION.read_text(encoding="utf-8")


# --- R-IV.454(c): Group E ---------------------------------------------------------------------
def test_group_e_is_marked_with_a_reason_not_a_flag():
    sql = MIGRATION.read_text(encoding="utf-8")
    for pid in ("POS_GUSH_20260609_232044", "POS_SOXS_20260610_154556",
                "POS_GDXJ_20260618_174846", "POS_XLE_20260618_174913"):
        assert pid in sql
    assert "backfill_exempt_reason TEXT" in sql
    assert "no blanket backfill of closed-with-no-realized, ever" in sql


def test_the_exemption_is_readable_by_any_sweep():
    from models.position_status import is_backfill_exempt
    assert is_backfill_exempt({"backfill_exempt_reason": "R-IV.454(c) GROUP E"})
    assert not is_backfill_exempt({"backfill_exempt_reason": None})
    assert not is_backfill_exempt({"backfill_exempt_reason": "   "})
    assert not is_backfill_exempt(None)


# --- R-IV.454(b): the NULL predicate -----------------------------------------------------------
def test_both_date_predicates_carry_their_null_branch():
    from models.accounts import reconciliation_scope
    clause, _ = reconciliation_scope("ROBINHOOD", "2026-09-01", "2026-09-17")
    assert "p.exit_date IS NULL OR p.exit_date >= $2" in clause
    assert "p.entry_date IS NULL OR p.entry_date <= $3" in clause


def test_the_null_rule_and_the_instance_count_are_recorded():
    src = (ROOT / "backend" / "models" / "accounts.py").read_text(encoding="utf-8")
    flat = " ".join(src.split())
    assert "THE NULL-PREDICATE RULE (R-IV.454(b))" in flat
    assert "THIRD SCOPE INSTANCE" in flat
