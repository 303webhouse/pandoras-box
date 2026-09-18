"""R-IV.457 — the latch rulings, the correction path, and what the 09:30 job is allowed to clear.

FAIL-FIRST against the pre-2026-09-18 tree: a pending reset waited forever for a human accept;
the 09:30 job cleared the breaker unconditionally (fail-OPEN once it persisted); a disputed fire
could render as plain ACTIVE; and a closed row's realized result had no correction path at all.
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from webhooks import circuit_breaker as CB  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# --- (a)(2) a full session, measured on the calendar -----------------------------------------
def test_a_reset_pending_after_the_close_waits_for_the_next_whole_session():
    """The measured case: pending since Wed 09-16 19:19 ET. Thursday's session is the first that
    counts, and it has passed only once Thursday's close has."""
    since = utc(2026, 9, 16, 23, 19)                    # 19:19 ET Wed, after the close
    assert CB.full_session_elapsed_since(since, utc(2026, 9, 17, 19, 59)) is False
    assert CB.full_session_elapsed_since(since, utc(2026, 9, 17, 20, 0)) is True


def test_a_reset_pending_before_the_open_counts_that_same_session():
    since = utc(2026, 9, 17, 13, 0)                     # 09:00 ET Thu
    assert CB.full_session_elapsed_since(since, utc(2026, 9, 17, 20, 0)) is True


def test_a_reset_pending_mid_session_does_not_count_that_session():
    """Half a session is not a full one."""
    since = utc(2026, 9, 17, 15, 0)                     # 11:00 ET Thu
    assert CB.full_session_elapsed_since(since, utc(2026, 9, 17, 20, 30)) is False
    assert CB.full_session_elapsed_since(since, utc(2026, 9, 18, 20, 0)) is True


def test_a_weekend_is_not_a_session():
    since = utc(2026, 9, 18, 21, 0)                     # 17:00 ET Fri
    assert CB.full_session_elapsed_since(since, utc(2026, 9, 20, 23, 0)) is False  # Sunday
    assert CB.full_session_elapsed_since(since, utc(2026, 9, 21, 20, 0)) is True   # Mon close


def test_a_pending_reset_clears_itself_and_says_so():
    CB._circuit_breaker_state = {"active": True, "trigger": "spy_down_1pct",
                                 "triggered_at": "2026-09-16T19:11:50+00:00",
                                 "pending_reset": True,
                                 "pending_since": "2026-09-16T23:19:58.488941"}
    with patch.object(CB, "_persist_circuit_breaker_state", new=AsyncMock()) as persist, \
         patch.object(CB.logger, "warning") as warn:
        out = _run(CB.self_resolve_if_due(utc(2026, 9, 17, 20, 1)))
    assert out and out["status"] == "self_cleared"
    assert CB._circuit_breaker_state["active"] is False
    assert CB._circuit_breaker_state["last_self_clear"]["trigger"] == "spy_down_1pct"
    persist.assert_awaited()
    assert "SELF-CLEARED" in warn.call_args[0][0], "a self-clear logs a notice"


def test_an_armed_breaker_whose_condition_has_not_cleared_never_self_clears():
    """Fail-safe: only a PENDING reset (condition already cleared) is eligible."""
    CB._circuit_breaker_state = {"active": True, "trigger": "spy_down_2pct",
                                 "pending_reset": False, "pending_since": None}
    with patch.object(CB, "_persist_circuit_breaker_state", new=AsyncMock()):
        assert _run(CB.self_resolve_if_due(utc(2026, 9, 30, 20, 0))) is None
    assert CB._circuit_breaker_state["active"] is True


def test_the_market_open_job_applies_the_rule_not_a_wipe():
    """It cleared unconditionally every morning -- fail-OPEN once it persisted."""
    src = (ROOT / "backend" / "scheduler" / "bias_scheduler.py").read_text(encoding="utf-8")
    i = src.index("async def reset_circuit_breaker_scheduled")
    body = src[i:i + 1500]
    assert "self_resolve_if_due()" in body
    assert "reset_circuit_breaker()" not in body, "no unconditional clear at the open"


def test_the_decay_check_runs_the_self_resolution():
    assert "await self_resolve_if_due()" in inspect.getsource(CB.check_decay)


# --- (a)(1) a disputed fire arms but is never plain ACTIVE -----------------------------------
def test_the_board_never_renders_a_disputed_fire_as_plain_active():
    from services.read_only import board
    fake = {"active": True, "trigger": "spy_down_1pct", "disputed": True,
            "hub_reading": {"change_pct": -0.2}, "triggered_at": "2026-09-18T17:44:46+00:00"}
    with patch("webhooks.circuit_breaker.get_circuit_breaker_state", return_value=fake), \
         patch("webhooks.circuit_breaker.get_circuit_breaker_provenance",
               return_value={"source": "event-confirmed"}), \
         patch.object(board, "_persisted_cb_record", new=AsyncMock(return_value="present-armed")):
        out = _run(board.get_kill_switch())
    k = out["kill_switch"]
    assert k["active"] is True, "a disputed fire still ARMS (fail-safe)"
    assert k["display_state"] == "DISPUTED"
    assert k["readings"]["alert"]["claims"] == "SPY down at least 1% intraday"
    assert k["readings"]["hub"]["change_pct"] == -0.2


def test_the_composite_carries_the_same_word():
    src = (ROOT / "backend" / "bias_engine" / "composite.py").read_text(encoding="utf-8")
    assert '"DISPUTED" if cb_state.get("disputed") is True' in src


# --- (d) the correction path ---------------------------------------------------------------
class _Acq:
    def __init__(self, c): self.c = c
    async def __aenter__(self): return self.c
    async def __aexit__(self, *a): return False
    def __call__(self): return self


class _Txn:
    async def __aenter__(self): return None
    async def __aexit__(self, *a): return False


def _correct(monkeypatch, row, **body):
    from api import unified_positions as U
    conn = MagicMock()
    conn.calls = []
    conn.fetchrow = AsyncMock(return_value=row)

    async def execute(sql, *args):
        conn.calls.append((" ".join(sql.split()), args))

    conn.execute = execute
    conn.transaction = lambda: _Txn()
    pool = MagicMock()
    pool.acquire = _Acq(conn)
    monkeypatch.setattr(U, "get_postgres_client", AsyncMock(return_value=pool))
    req = U.CorrectRealizedRequest(**{"realized_pnl": 64.0, "ruling": "R-IV.457(d)",
                                      "evidence": "export lines ...", "reason": "basis leg missing",
                                      **body})
    return _run(U.correct_realized("POS_XLE_20260715_164155", req)), conn


CLOSED = {"position_id": "POS_XLE_20260715_164155", "status": "CLOSED", "realized_pnl": 81.94,
          "exit_price": 0.9994, "notes": "x"}


def test_a_correction_keeps_the_prior_figure_and_the_evidence_on_the_row(monkeypatch):
    out, conn = _correct(monkeypatch, CLOSED)
    upd = [c for c in conn.calls if "UPDATE unified_positions" in c[0]][0]
    note = upd[1][3]
    assert "+81.94 -> +64.00" in note and "EVIDENCE: export lines" in note
    assert out["realized_before"] == 81.94 and out["realized_after"] == 64.0


@pytest.mark.parametrize("field", ["evidence", "reason", "ruling"])
def test_a_verdict_without_its_evidence_is_refused(monkeypatch, field):
    with pytest.raises(HTTPException) as e:
        _correct(monkeypatch, CLOSED, **{field: "  "})
    assert e.value.status_code == 400 and "#23" in e.value.detail


def test_an_open_row_is_not_corrected_here(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _correct(monkeypatch, dict(CLOSED, status="OPEN"))
    assert "/close" in e.value.detail


# --- the filings ---------------------------------------------------------------------------
def test_conventions_22_is_filed():
    src = (ROOT / "docs" / "conventions" / "conventions.md").read_text(encoding="utf-8")
    assert "## #22 A LATCHED STATE CARRIES A CLEARING PATH THAT DOES NOT DEPEND ON BEING SEEN" in src


def test_the_phantom_stays_open_on_the_defs_face():
    src = (ROOT / "docs" / "defects" / "DEF-KILLSWITCH-LATCH.md").read_text(encoding="utf-8")
    assert "This DEF is not closed" in src and "UNEXPLAINED" in src
