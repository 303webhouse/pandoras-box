"""Cached-quote restore (2026-06-22) — aggregate_ticker_flow re-populates
price / change_pct / volume from _get_regular_session_change.

Real code path: the REAL aggregate_ticker_flow runs; only the two UW calls
(get_flow_per_expiry + _get_regular_session_change) are mocked at their source
module (the function imports them inline from integrations.uw_api).
"""

import asyncio
from unittest.mock import AsyncMock, patch

from jobs.uw_flow_poller import aggregate_ticker_flow

# Non-empty flow so aggregate_ticker_flow reaches the quote block + return dict.
_FLOW = [{"call_premium": "5000000", "put_premium": "1000000",
          "call_volume": 100, "put_volume": 50}]


def _run(reg_return=None, reg_raises=False):
    gfpe = AsyncMock(return_value=_FLOW)
    if reg_raises:
        grsc = AsyncMock(side_effect=RuntimeError("uw throttled"))
    else:
        grsc = AsyncMock(return_value=reg_return)
    with patch("integrations.uw_api.get_flow_per_expiry", new=gfpe), \
         patch("integrations.uw_api._get_regular_session_change", new=grsc):
        return asyncio.run(aggregate_ticker_flow("SPY"))


def test_quote_fields_populated_from_helper():
    row = _run({"today_close": 601.5, "change_pct": 1.23, "today_volume": 45_000_000})
    assert row is not None
    assert row["price"] == 601.5
    assert row["change_pct"] == 1.23
    assert row["volume"] == 45_000_000
    # flow aggregation still intact alongside the restore
    assert row["call_premium"] == 5_000_000
    assert row["put_premium"] == 1_000_000


def test_quote_fields_none_when_helper_returns_none():
    row = _run(None)
    assert row is not None
    assert row["price"] is None
    assert row["change_pct"] is None
    assert row["volume"] is None


def test_quote_helper_exception_degrades_no_raise():
    row = _run(reg_raises=True)            # UW miss/throttle → degrade, never crash
    assert row is not None
    assert row["price"] is None and row["change_pct"] is None and row["volume"] is None
    assert row["call_premium"] == 5_000_000   # flow path unaffected
