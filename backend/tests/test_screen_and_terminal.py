"""R-IV.470(a)(b) -- a broker screen is its own rung, and a wrong terminal status is correctable.

FAIL-FIRST against the pre-R-IV.470 tree: a figure the broker DISPLAYED was stored
PRINCIPAL_REPORTED, the weakest claim in the vocabulary, because the only rung above it required
a reference; and a terminal status written wrongly -- the sweep stamped HYG 218 EXPIRED/UNKNOWN
before the ruling that it had been rolled -- could be corrected only by SQL straight into the
table, since the PATCH refuses terminal statuses and the close path takes only OPEN rows.
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from api import unified_positions as U  # noqa: E402
from models.position_lots import (  # noqa: E402
    BROKER_VERIFIED, IMPORTED, PRINCIPAL_REPORTED, PROVENANCE_RANK, PROVENANCE_VALUES,
    SCREEN_VERIFIED, UNKNOWN, outranks,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Txn:
    async def __aenter__(self): return None
    async def __aexit__(self, *a): return False


class _Acq:
    def __init__(self, c): self.c = c
    async def __aenter__(self): return self.c
    async def __aexit__(self, *a): return False
    def __call__(self): return self


def _conn(row):
    conn = MagicMock()
    conn.calls = []

    async def execute(sql, *args):
        conn.calls.append((" ".join(sql.split()), args))

    conn.execute = execute
    conn.fetchrow = AsyncMock(return_value=row)
    conn.fetchval = AsyncMock(return_value=None)
    conn.transaction = lambda: _Txn()
    return conn


def _pool(monkeypatch, conn):
    pool = MagicMock()
    pool.acquire = _Acq(conn)
    monkeypatch.setattr(U, "get_postgres_client", AsyncMock(return_value=pool))
    monkeypatch.setattr(U, "_audit_leg", AsyncMock())


# --- (a) the vocabulary ------------------------------------------------------------------------
def test_the_ladder_puts_a_screen_between_the_principal_and_an_export():
    assert SCREEN_VERIFIED in PROVENANCE_VALUES
    assert (PROVENANCE_RANK[UNKNOWN] < PROVENANCE_RANK[PRINCIPAL_REPORTED]
            < PROVENANCE_RANK[SCREEN_VERIFIED] < PROVENANCE_RANK[IMPORTED]
            < PROVENANCE_RANK[BROKER_VERIFIED])
    assert outranks(SCREEN_VERIFIED, PRINCIPAL_REPORTED)
    assert not outranks(SCREEN_VERIFIED, IMPORTED), "an export line always supersedes a screen"
    assert not outranks(SCREEN_VERIFIED, BROKER_VERIFIED)


def test_both_mirrors_accept_the_value_and_demand_its_evidence():
    mig = (ROOT / "migrations" / "052_screen_verified.sql").read_text(encoding="utf-8")
    boot = (ROOT / "backend" / "database" / "postgres_client.py").read_text(encoding="utf-8")
    for text in (mig, boot):
        for table in ("unified_positions", "position_lots", "position_legs"):
            assert f"{table}_screen_needs_evidence" in text
        assert text.count("'SCREEN_VERIFIED'") >= 4


REQ = dict(fields_read=["net debit 0.4067", "qty 3"], captured_at="2026-09-18",
           transcribed_by="positions-lane", ruling="R-IV.470(a)")


def test_the_evidence_line_names_what_was_read_when_and_by_whom():
    evidence, captured = U._screen_evidence(U.ScreenVerifyRequest(**REQ))
    assert "net debit 0.4067" in evidence and "qty 3" in evidence
    assert "transcribed by positions-lane" in evidence
    # R-IV.464(a): a bare date is the principal's day -- the capture instant, not the fill's
    assert captured == datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc)
    assert captured.isoformat() in evidence


@pytest.mark.parametrize("bad,phrase", [
    ({"fields_read": []}, "fields_read is required"),
    ({"fields_read": ["  "]}, "fields_read is required"),
    ({"transcribed_by": " "}, "transcribed_by is required"),
    ({"captured_at": "2099-01-01"}, "in the future"),
    ({"captured_at": "whenever"}, "must be a date"),
])
def test_a_screen_reading_without_its_evidence_is_refused(bad, phrase):
    with pytest.raises(HTTPException) as e:
        U._screen_evidence(U.ScreenVerifyRequest(**{**REQ, **bad}))
    assert phrase in e.value.detail


def test_a_row_the_broker_displayed_is_stamped_with_the_capture_instant(monkeypatch):
    conn = _conn({"position_id": "P", "ticker": "HYG", "provenance": PRINCIPAL_REPORTED})
    _pool(monkeypatch, conn)
    out = _run(U.screen_verify_position("P", U.ScreenVerifyRequest(**REQ)))
    assert out["provenance"] == SCREEN_VERIFIED and out["was"] == PRINCIPAL_REPORTED
    upd = [c for c in conn.calls if c[0].startswith("UPDATE unified_positions")][0]
    assert upd[1][0] == SCREEN_VERIFIED
    assert upd[1][2] == datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("current", [IMPORTED, BROKER_VERIFIED])
def test_a_screen_never_overwrites_a_stronger_claim(monkeypatch, current):
    conn = _conn({"position_id": "P", "ticker": "HYG", "provenance": current})
    _pool(monkeypatch, conn)
    with pytest.raises(HTTPException) as e:
        _run(U.screen_verify_position("P", U.ScreenVerifyRequest(**REQ)))
    assert e.value.status_code == 409 and "supersedes a screen" in e.value.detail


def test_a_lot_and_a_leg_have_the_same_route():
    assert inspect.iscoroutinefunction(U.screen_verify_lot)
    assert 'key_column="leg_seq"' in inspect.getsource(U.screen_verify_leg)
    src = inspect.getsource(U._screen_verify_row)
    assert "SCREEN_VERIFIED" in src and "_screen_refusal" in src


# --- (b) a wrong terminal status ---------------------------------------------------------------
HYG = {"position_id": "POS_HYG", "ticker": "HYG", "status": "EXPIRED",
       "exit_date": datetime(2026, 9, 18, 6, tzinfo=timezone.utc), "exit_price": 0.04,
       "realized_pnl": -110.0, "trade_outcome": "LOSS"}
BODY = dict(evidence="Robinhood filled-order screen: roll 9/18 -> 11/20, net -110.00",
            reason="closed by the roll, not expired", ruling="R-IV.470(b)",
            actor="positions-lane")


def _correct(monkeypatch, row, **body):
    conn = _conn(row)
    _pool(monkeypatch, conn)
    req = U.CorrectTerminalStatusRequest(**{**BODY, **body})
    return _run(U.correct_terminal_status(row["position_id"], req)), conn


def test_an_expired_row_that_was_closed_is_corrected_with_its_evidence(monkeypatch):
    out, conn = _correct(monkeypatch, dict(HYG), status="CLOSED")
    assert out["was"] == "EXPIRED" and out["now"] == "CLOSED" and out["cleared"] is None
    upd = [c for c in conn.calls if c[0].startswith("UPDATE unified_positions")][0]
    assert upd[1][0] == "CLOSED"
    assert "TERMINAL STATUS CORRECTED: EXPIRED -> CLOSED" in upd[1][1]
    assert "EVIDENCE: Robinhood filled-order screen" in upd[1][1]


def test_a_row_moved_back_to_open_cannot_keep_an_exit_it_did_not_have(monkeypatch):
    out, conn = _correct(monkeypatch, dict(HYG), status="OPEN")
    assert set(out["cleared"]) == {"exit_date", "exit_price", "realized_pnl", "trade_outcome"}
    upd = [c for c in conn.calls if c[0].startswith("UPDATE unified_positions")][0]
    for field in ("exit_date = NULL", "exit_price = NULL", "realized_pnl = NULL",
                  "trade_outcome = NULL"):
        assert field in upd[0]


def test_a_terminal_status_still_needs_its_exit(monkeypatch):
    bare = dict(HYG, status="CLOSED", exit_price=None, realized_pnl=None, trade_outcome=None)
    with pytest.raises(HTTPException) as e:
        _correct(monkeypatch, bare, status="EXPIRED")
    assert "R-IV.454(d)" in e.value.detail


@pytest.mark.parametrize("row,body,phrase", [
    (dict(HYG, status="OPEN"), {"status": "CLOSED"}, "not terminal"),
    (dict(HYG), {"status": "EXPIRED"}, "already EXPIRED"),
    (dict(HYG), {"status": "DUPLICATE_OF"}, "retire-duplicate"),
    (dict(HYG), {"status": "CLOSED", "evidence": " "}, "evidence is required"),
    (dict(HYG), {"status": "CLOSED", "ruling": ""}, "ruling is required"),
])
def test_what_the_correction_refuses(monkeypatch, row, body, phrase):
    with pytest.raises(HTTPException) as e:
        _correct(monkeypatch, row, **body)
    assert phrase in e.value.detail


def test_the_correction_names_its_actor(monkeypatch):
    _, conn = _correct(monkeypatch, dict(HYG), status="CLOSED")
    assert any("set_config('app.actor'" in c[0] and c[1] == ("positions-lane",)
               for c in conn.calls)
