"""FEAT-POSITION-LIFECYCLE Phase 2 — endpoint contracts.

Three endpoints, one invariant. The contracts here are the ones Phase 4's fail-first
P&L insulation test is written against:

  * a manual edit writes neither a mark nor a realized field   (Phase 1 D1 allowlist)
  * a cash event touches no position row and no realized field (this module)
  * an added lot is not a valuation event and not a close

FAIL-FIRST: every test fails against pre-Phase-2 unified_positions.py, where none of
the endpoints, the invariant, or the request fields existed.
"""
from __future__ import annotations

import pathlib
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from api._position_write_scope import MARK_COLUMNS, REALIZED_COLUMNS  # noqa: E402
from api.unified_positions import (  # noqa: E402
    _ETF_ONLY_ACCOUNTS, _CANONICAL_ACCOUNTS, _assert_etf_only,
    AddLotRequest, CashEventRequest, UpdatePositionRequest,
)

UP = pathlib.Path(__file__).resolve().parents[1] / "api" / "unified_positions.py"


# --- ETF-only invariant (R-IV.75(d)) -----------------------------------------
def test_option_on_roth_is_refused_at_entry():
    with pytest.raises(HTTPException) as e:
        _assert_etf_only("FIDELITY_ROTH", "OPTION")
    assert e.value.status_code == 400
    assert "mis-attributed" in e.value.detail, "the refusal must say WHY, not just refuse"


def test_equity_on_roth_is_permitted():
    _assert_etf_only("FIDELITY_ROTH", "EQUITY")


def test_option_on_robinhood_is_permitted():
    """The invariant is account-scoped; it must not become a global options ban."""
    _assert_etf_only("ROBINHOOD", "OPTION")
    _assert_etf_only("ROBINHOOD", "SPREAD")


def test_invariant_is_case_insensitive():
    for acct in ("fidelity_roth", "Fidelity_Roth", "FIDELITY_ROTH"):
        with pytest.raises(HTTPException):
            _assert_etf_only(acct, "option")


def test_invariant_applies_at_both_entry_points():
    """Create and add-lot are both entries; guarding one leaves the other open."""
    src = UP.read_text(encoding="utf-8")
    assert src.count("_assert_etf_only(") >= 3, (
        "expected the definition plus a call on the create path and the add-lot path")


# --- cash events --------------------------------------------------------------
def test_cash_event_accounts_are_the_canonical_vocabulary():
    """D3 canonicalised the account labels; the API must not reintroduce a fifth form."""
    assert _CANONICAL_ACCOUNTS == {"ROBINHOOD", "FIDELITY_ROTH", "FIDELITY_401A"}


def test_cash_event_model_carries_no_position_or_realized_field():
    """The insulation contract, enforced at the schema: a cash event cannot name a
    position or a P&L field, so it cannot move one even by accident."""
    fields = set(CashEventRequest.model_fields)
    assert fields == {"account", "direction", "amount", "event_date", "description"}
    assert not (fields & MARK_COLUMNS), "a cash event must not carry a mark field"
    assert not (fields & REALIZED_COLUMNS), "a cash event must not carry a realized field"
    assert "position_id" not in fields


def test_cash_event_endpoint_touches_no_position_table():
    """Structural: the handler's SQL may reach cash_flows and account_balances only."""
    src = UP.read_text(encoding="utf-8")
    i = src.index("async def record_cash_event")
    body = src[i:src.index("\n@router", i + 1)] if "\n@router" in src[i:] else src[i:]
    assert "unified_positions" not in body, (
        "the cash-event handler references unified_positions — the insulation contract "
        "is that it touches no position row")
    assert "realized_pnl" not in body
    assert "cash_flows" in body and "account_balances" in body


# --- add lot ------------------------------------------------------------------
def test_add_lot_model_carries_no_mark_or_realized_field():
    fields = set(AddLotRequest.model_fields)
    assert not (fields & MARK_COLUMNS), "adding a lot is not a valuation event"
    assert not (fields & REALIZED_COLUMNS), "adding a lot is not a close"


def test_add_lot_reserves_the_backfill_source():
    src = UP.read_text(encoding="utf-8")
    assert 'req.source not in ("MANUAL", "IMPORT")' in src, (
        "LEGACY-SINGLE-LOT must stay reserved for the Phase-1 backfill; a caller "
        "stamping it would make hand-entered lots indistinguishable from migrated ones")


def test_blended_basis_uses_priced_lots_only():
    src = UP.read_text(encoding="utf-8")
    assert "priced = [l for l in lots if l[\"price\"] is not None]" in src, (
        "an unpriced lot must move quantity without diluting the basis; folding it in "
        "at zero would silently understate cost")


# --- reason / actor (R-IV.116) -------------------------------------------------
def test_reason_and_actor_are_optional_on_patch():
    """OPTIONAL at the API layer: the legacy caller sends neither and must still work."""
    m = UpdatePositionRequest.model_fields
    assert "reason" in m and "actor" in m
    assert UpdatePositionRequest().reason is None
    assert UpdatePositionRequest().actor is None


def test_actor_defaults_to_legacy_ui_when_absent():
    src = UP.read_text(encoding="utf-8")
    assert '(req.actor or "legacy-ui")' in src


def test_set_config_runs_inside_a_transaction():
    """SET LOCAL outside a transaction is a silent no-op — the trigger would then
    record 'legacy-ui' for every lifecycle-UI edit and the reason would be lost."""
    src = UP.read_text(encoding="utf-8")
    i = src.index("SELECT set_config('app.actor'")
    window = src[max(0, i - 400):i]
    assert "async with conn.transaction():" in window, (
        "set_config must be inside an open transaction to bind for the trigger")
