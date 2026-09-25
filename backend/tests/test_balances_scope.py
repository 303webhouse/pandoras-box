"""R-IV.440(a) — GET /api/portfolio/balances carries the canonical account scope.

The v2 Book strip's Balance is the TRADEABLE book. Until this field existed, every consumer
either summed parked money into the headline or kept its own list of account names — the
second source of truth this vocabulary exists to delete (config/accounts.py, T2/T4).

The field is additive: `account_name` and `balance` are untouched, so existing readers
(legacy app.js, the reconcile banner) are unaffected.
"""
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

PATH = "/api/portfolio/balances"

ROWS = [
    {"account_name": "ROBINHOOD", "broker": "robinhood", "balance": Decimal("1234.56"),
     "cash": Decimal("10"), "buying_power": None, "margin_total": None,
     "updated_at": None, "updated_by": "auto"},
    {"account_name": "FIDELITY_ROTH", "broker": "fidelity", "balance": Decimal("8443.22"),
     "cash": Decimal("5"), "buying_power": None, "margin_total": None,
     "updated_at": None, "updated_by": "auto"},
    {"account_name": "BROKERAGE_LINK_401K", "broker": "fidelity", "balance": Decimal("11642.35"),
     "cash": Decimal("0"), "buying_power": None, "margin_total": None,
     "updated_at": None, "updated_by": "pivot_screenshot"},
]


@pytest.fixture
def balances(client, test_api_key):
    # The route reads through the ONE read service (services.read_only.balances), which resolves the
    # account rows and their derived cash itself; what this file pins is the scope the ROUTE adds to
    # each row, so the service is what is stubbed, with copies because the route tags rows in place.
    with patch("services.read_only.balances.get_account_balances",
               new=AsyncMock(side_effect=lambda *a, **k: [dict(r) for r in ROWS])):
    # And it is a STRONGER assertion than the pool patch it replaces: if the route ever went back
    # to querying for itself, this stub would have no effect and every case below would fail on an
    # empty list rather than quietly passing.
        r = client.get(PATH, headers={"X-API-Key": test_api_key})
    assert r.status_code == 200, r.text
    return {row["account_name"]: row for row in r.json()}


def test_tradeable_accounts_are_in_scope(balances):
    assert balances["ROBINHOOD"]["in_scope"] is True
    assert balances["FIDELITY_ROTH"]["in_scope"] is True


def test_parked_money_is_out_of_scope(balances):
    row = balances["BROKERAGE_LINK_401K"]
    assert row["in_scope"] is False
    assert row["scope"] == "OUT_OF_SCOPE"


def test_scope_carries_the_canonical_name(balances):
    assert balances["ROBINHOOD"]["scope"] == "ROBINHOOD"
    assert balances["FIDELITY_ROTH"]["scope"] == "FIDELITY_ROTH"


def test_every_row_is_classified(balances):
    for name, row in balances.items():
        assert "in_scope" in row and "scope" in row, name


def test_the_existing_fields_are_untouched(balances):
    """Additive: a reader that does not know about scope sees exactly what it saw before."""
    row = balances["ROBINHOOD"]
    assert row["balance"] == 1234.56
    assert row["broker"] == "robinhood"
    assert row["updated_by"] == "auto"


def test_the_in_scope_sum_is_the_tradeable_book(balances):
    """The headline the Book strip shows: parked money is not in it."""
    total = sum(r["balance"] for r in balances.values() if r["in_scope"])
    assert round(total, 2) == 9677.78
    assert round(sum(r["balance"] for r in balances.values()), 2) == 21320.13


def test_the_classification_is_the_shared_vocabulary(balances):
    """Not a list kept here: the same helper the MCP tool uses (hub_mcp T4)."""
    from config.accounts import is_in_scope, normalize_account
    for name, row in balances.items():
        assert row["in_scope"] is is_in_scope(name)
        assert row["scope"] == normalize_account(name)
