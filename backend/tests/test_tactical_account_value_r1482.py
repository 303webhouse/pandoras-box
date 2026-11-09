"""R-IV.1482 — the Roth and 401(a) tactical reminders divide by the BALANCES SCREEN's value.

Before: both callers read the STORED `account_balances.balance`. The 401(a)'s stored figure was
the 0.00 seed placeholder (10-01), so its percentage was "account value unusable"; the Roth's
was a 09-24 number, so its percentage was off by the growth since.

After: both callers take `services.read_only.balances.account_values`, which is the same
derived value the balances screen serves (ledger cash from the latest anchor + open positions
at their marks).

These tests drive the REAL accessor (`get_account_balances` -> `_attach_derived_cash` ->
`position_economics.account_value`) on a fake pool. Only the data sources are faked: the
pool's rows, and the open-position list the accessor values positions from.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

import services.read_only.balances as bal
import services.read_only.positions as pos_reader

STORED = {"FIDELITY_ROTH": 1000.00, "FIDELITY_401A": 0.00}


def _balance_rows(stored):
    return [{"account_name": a, "broker": "fidelity", "balance": v, "cash": None,
             "buying_power": None, "margin_total": None,
             "updated_at": datetime(2026, 10, 1, tzinfo=timezone.utc), "updated_by": "seed"}
            for a, v in stored.items()]


def _anchor(acct, amount, i):
    return {"id": i, "account_name": acct, "flow_type": "OPENING_BALANCE", "amount": amount,
            "activity_date": date(2026, 9, 24), "imported_from": None, "source_ref": None,
            "meta": None}


class _Conn:
    def __init__(self, events):
        self.events = events

    async def fetch(self, sql, *args):
        assert "FROM cash_flows" in sql, sql
        return list(self.events)


class _Acq:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *a):
        return False


class _Pool:
    def __init__(self, stored, events):
        self.stored, self.conn = stored, _Conn(events)

    async def fetch(self, sql, *args):
        assert "FROM account_balances" in sql, sql
        return _balance_rows(self.stored)

    def acquire(self):
        return _Acq(self.conn)


def _open(acct, pid, mv):
    return {"position_id": pid, "account": acct, "status": "OPEN",
            "derived": {"market_value": mv}}


@pytest.fixture
def book(monkeypatch):
    """Roth: cash 2,000 + a 100 position = 2,100. 401(a): cash 1,000 + a 500 position = 1,500.
    Stored: Roth 1,000 and 401(a) 0.00, which must NOT be what anyone divides by."""
    state = {"events": [_anchor("FIDELITY_ROTH", 2000, 1), _anchor("FIDELITY_401A", 1000, 2)],
             "open": [_open("FIDELITY_ROTH", "R1", 100), _open("FIDELITY_401A", "A1", 500)],
             "stored": dict(STORED), "fail": False}

    async def _get():
        if state["fail"]:
            raise RuntimeError("db down")
        return _Pool(state["stored"], state["events"])

    async def _list_positions(status="OPEN", ticker=None, account=None):
        return list(state["open"])

    monkeypatch.setattr(bal, "get_postgres_client", _get)
    monkeypatch.setattr(pos_reader, "list_positions", _list_positions)
    return state


ROWS = [
    {"position_id": "R1", "account": "FIDELITY_ROTH", "classification": "TACTICAL",
     "structure": "stock", "current_price": 10.0, "quantity": 10, "open_quantity": 10},
    {"position_id": "A1", "account": "FIDELITY_401A", "classification": "STRATEGIC",
     "structure": "stock", "current_price": 50.0, "quantity": 10, "open_quantity": 10},
]


# ── the accessor ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_account_values_is_the_derived_value_not_the_stored_one(book):
    out = await bal.account_values(["fidelity_roth", "FIDELITY_401A"])
    assert Decimal(str(out["FIDELITY_ROTH"]["value"])) == Decimal("2100")
    assert Decimal(str(out["FIDELITY_401A"]["value"])) == Decimal("1500")
    assert out["FIDELITY_ROTH"]["partial"] is False


@pytest.mark.asyncio
async def test_account_values_raises_when_balances_cannot_be_read(book):
    book["fail"] = True
    with pytest.raises(RuntimeError):
        await bal.account_values(["FIDELITY_ROTH"])


# ── the positions tool ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_401a_percentage_is_computed_where_the_seed_row_said_unusable(book):
    from hub_mcp.tools.positions import _tactical_pct
    out = await _tactical_pct(ROWS, ticker=None, status="OPEN", account=None)
    a = out["FIDELITY_401A"]
    assert a["pct"] == "0.0", a        # all strategic, of a usable 1,500
    assert "unusable" not in a["reason"]


@pytest.mark.asyncio
async def test_the_roth_percentage_divides_by_the_derived_value(book):
    from hub_mcp.tools.positions import _tactical_pct
    out = await _tactical_pct(ROWS, ticker=None, status="OPEN", account=None)
    # 100 tactical of 2,100 = 4.8%. Of the stored 1,000 it would have read 10.0%.
    assert out["FIDELITY_ROTH"]["pct"] == "4.8"


@pytest.mark.asyncio
async def test_a_partial_account_value_is_flagged_as_overstating(book):
    from hub_mcp.tools.positions import _tactical_pct
    book["open"].append({"position_id": "R2", "account": "FIDELITY_ROTH", "status": "OPEN",
                         "derived": {"market_value": None}})
    out = await _tactical_pct(ROWS, ticker=None, status="OPEN", account=None)
    r = out["FIDELITY_ROTH"]
    assert r["account_value_partial"] is True
    assert "OVERSTATES" in r["reason"]
    assert r["pct"] == "4.8"


@pytest.mark.asyncio
async def test_no_derived_value_gives_no_percentage_and_says_why(book):
    from hub_mcp.tools.positions import _tactical_pct
    book["events"] = [e for e in book["events"] if e["account_name"] != "FIDELITY_401A"]
    out = await _tactical_pct(ROWS, ticker=None, status="OPEN", account=None)
    a = out["FIDELITY_401A"]
    assert a["pct"] is None
    assert "unusable" in a["reason"] and "the balances screen says" in a["reason"]


@pytest.mark.asyncio
async def test_unreadable_balances_name_the_failure(book):
    from hub_mcp.tools.positions import _tactical_pct
    book["fail"] = True
    out = await _tactical_pct(ROWS, ticker=None, status="OPEN", account=None)
    for acct in ("FIDELITY_ROTH", "FIDELITY_401A"):
        assert out[acct]["pct"] is None
        assert "unreadable" in out[acct]["reason"]


# ── the reminder job: the same figures ─────────────────────────────────────

class _JobConn:
    async def fetch(self, sql, *args):
        assert "FROM unified_positions" in sql, sql
        return [{k: r[k] for k in ("position_id", "account", "classification", "structure",
                                   "current_price", "quantity")} for r in ROWS]


class _JobPool:
    def acquire(self):
        return _Acq(_JobConn())


@pytest.mark.asyncio
async def test_the_reminder_job_gets_the_same_percentages(book, monkeypatch):
    import jobs.roth_cap_reminder as job
    import services.open_quantity as oq
    import integrations.ntfy_push as ntfy

    async def _stamp(conn, rows):
        for r in rows:
            r["open_quantity"] = r["quantity"]

    monkeypatch.setattr(oq, "stamp_open_quantity", _stamp)
    monkeypatch.setattr(ntfy, "is_configured", lambda: False)
    out = await job.run(pool=_JobPool())
    assert out["accounts"]["FIDELITY_ROTH"]["pct"] == "4.8"
    assert out["accounts"]["FIDELITY_401A"]["pct"] == "0.0"
