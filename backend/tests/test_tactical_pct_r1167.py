"""R-IV.1167(a) — `tactical_pct` per capped account. DERIVED, and never a gate.

THE ARITHMETIC ALREADY HAD AN AUTHOR. `models.roth_tactical_cap.tactical_share` is pure, takes
rows plus the account value, and already refuses to report a percentage of an unusable total
("a zero would read as 'nothing tactical'"). `jobs.roth_cap_reminder` uses it for the push.
What was missing is that the figure never reached the payload, so a reader asking "how close am
I to 20%" had to wait for a push or recompute it by hand.

THE SCOPE TRAP, WHICH IS THE WHOLE DIFFICULTY. `tactical_share` filters the rows it is GIVEN by
account — it cannot know what the caller filtered out. Computing it from this tool's row set
would make `hub_get_positions(ticker="GUSH")` report the Roth's tactical share as whatever that
one position happens to be.

That is not hypothetical. The cap fields already on this payload DO behave that way, measured
live this session on one deploy:

    unfiltered      cap_enforceable: true,  classification_backfilled: true
    ticker="XLF"    cap_enforceable: false, classification_backfilled: false

The same book, two answers, because the filter changed the population. So `tactical_pct`
refuses rather than inheriting it: a percentage only when this call's rows are a capped
account's whole open set, otherwise None with a reason naming the filter that stopped it. An
understated cap figure is worse than an absent one when the entire purpose is noticing a limit
being approached.
"""
from __future__ import annotations

import io
import os

import pytest

from hub_mcp import field_origin as fo
from hub_mcp.tools.positions import _tactical_pct
from models.roth_tactical_cap import CAP_ACCOUNTS

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = "hub_get_positions"


def _src(rel: str) -> str:
    return io.open(os.path.join(BACKEND, rel), encoding="utf-8", errors="replace").read()


# ── it refuses what it cannot measure ───────────────────────────────────────

@pytest.mark.asyncio
async def test_a_ticker_filter_gives_no_percentage_and_names_the_filter():
    """THE TRAP. One ticker is not an account, and a share of one position would look exactly
    like a measurement."""
    out = await _tactical_pct([], ticker="GUSH", status="OPEN", account=None)
    for acct in CAP_ACCOUNTS:
        assert out[acct]["pct"] is None
        assert "ticker" in out[acct]["reason"]
        assert "GUSH" in out[acct]["reason"]


@pytest.mark.asyncio
async def test_a_non_OPEN_status_gives_no_percentage():
    """The tactical share is over OPEN positions. A CLOSED or ALL call is a different
    population, and the same arithmetic over it is a different number wearing this name."""
    for status in ("CLOSED", "ALL"):
        out = await _tactical_pct([], ticker=None, status=status, account=None)
        for acct in CAP_ACCOUNTS:
            assert out[acct]["pct"] is None
            assert status in out[acct]["reason"]


@pytest.mark.asyncio
async def test_an_account_the_cap_does_not_reach_gives_no_percentage():
    """ROBINHOOD is governed by a sleeve ceiling, not this cap. Reporting 0% for it would
    assert it has no tactical exposure, which is a claim about the wrong account."""
    out = await _tactical_pct([], ticker=None, status="OPEN", account="ROBINHOOD")
    for acct in CAP_ACCOUNTS:
        assert out[acct]["pct"] is None
        assert "not one the cap reaches" in out[acct]["reason"]


@pytest.mark.asyncio
async def test_every_refusal_is_NAMED_and_never_merely_absent():
    """"Not computed" with no reason is indistinguishable from a field nobody implemented."""
    out = await _tactical_pct([], ticker="GUSH", status="ALL", account=None)
    for acct in CAP_ACCOUNTS:
        assert out[acct]["reason"].startswith("not computed:")
        # both blockers named, not just the first one hit
        assert "ticker" in out[acct]["reason"] and "ALL" in out[acct]["reason"]


@pytest.mark.asyncio
async def test_a_refusal_still_lists_EVERY_capped_account():
    """A reader must not have to infer which accounts the field would have covered."""
    out = await _tactical_pct([], ticker="GUSH", status="OPEN", account=None)
    assert set(out) == set(CAP_ACCOUNTS)


@pytest.mark.asyncio
async def test_at_or_over_is_False_and_never_None_on_a_refusal():
    """It is a boolean a reader may render directly. None there would print as "None" beside a
    cap, which reads worse than False beside an explicit null pct."""
    out = await _tactical_pct([], ticker="GUSH", status="OPEN", account=None)
    for acct in CAP_ACCOUNTS:
        assert out[acct]["at_or_over"] is False


# ── it computes when it can, through the one author ─────────────────────────

@pytest.mark.asyncio
async def test_it_computes_for_an_unfiltered_OPEN_call(monkeypatch):
    """THE POSITIVE CONTROL. Without it, a helper that refused everything would satisfy every
    test above."""
    import hub_mcp.tools.positions as t

    rows = [
        {"position_id": "A", "account": "FIDELITY_ROTH", "classification": "TACTICAL",
         "structure": "stock", "current_price": 10.0, "quantity": 10, "open_quantity": 10},
        {"position_id": "B", "account": "FIDELITY_ROTH", "classification": "STRATEGIC",
         "structure": "stock", "current_price": 10.0, "quantity": 90, "open_quantity": 90},
    ]

    class _Conn:
        async def fetch(self, sql, *args):
            return [{"account_name": "FIDELITY_ROTH", "balance": 1000.0}]

    class _Acq:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Acq()

    async def _get():
        return _Pool()

    import database.postgres_client as pc
    monkeypatch.setattr(pc, "get_postgres_client", _get)

    out = await _tactical_pct(rows, ticker=None, status="OPEN", account=None)
    # 10 shares x 10.00 = 100 tactical against a 1000 balance
    assert out["FIDELITY_ROTH"]["pct"] == "10.0"
    assert out["FIDELITY_ROTH"]["at_or_over"] is False


@pytest.mark.asyncio
async def test_an_unreadable_account_value_gives_no_percentage(monkeypatch):
    """No denominator, no percentage — and `tactical_share` already refuses to call that zero.
    A cap that cannot be computed must not look like a satisfied one."""
    import database.postgres_client as pc

    async def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(pc, "get_postgres_client", _boom)
    out = await _tactical_pct([], ticker=None, status="OPEN", account=None)
    for acct in CAP_ACCOUNTS:
        assert out[acct]["pct"] is None
        assert "unreadable" in out[acct]["reason"]


@pytest.mark.asyncio
async def test_an_account_filter_on_a_capped_account_narrows_to_that_account(monkeypatch):
    """An account filter IS the whole account, so it may compute — but only for the one named."""
    import database.postgres_client as pc

    class _Conn:
        async def fetch(self, sql, *args):
            return []

    class _Acq:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Acq()

    async def _get():
        return _Pool()

    monkeypatch.setattr(pc, "get_postgres_client", _get)
    out = await _tactical_pct([], ticker=None, status="OPEN", account="FIDELITY_ROTH")
    assert "FIDELITY_ROTH" in out
    assert out["FIDELITY_ROTH"]["account"] == "FIDELITY_ROTH"


def test_the_arithmetic_is_not_reimplemented_here():
    """One author. A second computation of the cap's own figure is how the push and the payload
    come to disagree about the same limit."""
    from tests._srcscan import function_code

    import hub_mcp.tools.positions as t

    code = function_code(t.__file__, "_tactical_pct")
    assert "tactical_share" in code
    for reinvented in ("* 100", "/ 100", "Decimal("):
        assert reinvented not in code, reinvented


# ── a reminder, never a gate ────────────────────────────────────────────────

def test_it_is_declared_DERIVED():
    assert fo.origin_of(TOOL, "tactical_pct") == fo.DERIVED
    assert fo.origin_of(TOOL, "tactical_pct_basis") == fo.DERIVED


def test_no_gate_may_rest_on_it():
    """R-IV.1033(e): the cap REMINDS and blocks nothing, so the figure measuring it must not
    become a block. DERIVED alone withholds permission; the GATE_FORBIDDEN entry says it out
    loud, which is what `strategy_tag` needed too."""
    ok, why = fo.may_gate(TOOL, "tactical_pct")
    assert ok is False
    assert "gate-forbidden" in why


def test_the_gate_prohibition_names_its_ruling_and_its_reason():
    note = fo.GATE_FORBIDDEN.get((TOOL, "tactical_pct"))
    assert note
    assert "R-IV.1033(e)" in note
    assert "null" in note, "the filtered-call null is half the reason a gate cannot use it"


def test_the_payload_says_what_the_figure_is_and_that_it_blocks_nothing():
    src = _src(os.path.join("hub_mcp", "tools", "positions.py"))
    assert '"tactical_pct": tactical,' in src
    assert '"tactical_pct_basis"' in src
    i = src.index('"tactical_pct_basis"')
    basis = src[i:i + 700]
    assert "REMINDER" in basis
    assert "R-IV.1033(e)" in basis
    assert "#42" in basis or "convention #42" in basis


def test_the_scope_refusal_is_explained_where_it_is_implemented():
    """The next reader's first instinct will be to compute it from the rows already in hand.
    The reason that is wrong belongs next to the code, with the measurement that proved it."""
    src = _src(os.path.join("hub_mcp", "tools", "positions.py"))
    i = src.index("async def _tactical_pct")
    doc = src[i:i + 1800]
    assert "cap_enforceable" in doc, "the live evidence belongs in the docstring"
    assert "understate" in doc or "understates" in doc
