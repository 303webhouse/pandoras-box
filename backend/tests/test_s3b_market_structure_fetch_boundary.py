"""S-3b Phase 0.1 fix -- canonical-to-pair conversion boundary tests.

Regression coverage for the fetch-boundary defect found during S-3b's Phase
0.1 klines audit: get_market_structure_context()'s three legs (volume
profile, CVD, orderbook) were feeding vendors a canonical bare base symbol
("BTC") where a Binance Futures pair symbol ("BTCUSDT") was required -- a
regression introduced by 0037375's ticker normalization at ingress.

Fable ruling rev-2 (2026-07-17):
- LEG 1 (volume profile): rerouted off Binance Futures klines onto the F-2
  bar source (jobs.crypto_bars.fetch_crypto_ohlc), which is already
  canonical-ticker-native -- no format conversion needed, just a vendor swap.
- LEG 2 (CVD) / LEG 3 (orderbook): format fix via ONE conversion choke point,
  config.crypto_symbol_matrix.get_binance_futures_symbol().

No live API calls or database access -- all vendor I/O is mocked/bypassed.
"""

import sys
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.crypto_symbol_matrix import get_binance_futures_symbol, BINANCE_FUTURES_PAIR_SYMBOL
from strategies.btc_market_structure import get_market_structure_context
import strategies.btc_market_structure as bms


@pytest.fixture(autouse=True)
def _clear_market_structure_cache():
    """get_market_structure_context()'s module-level _cache persists across
    tests -- each test needs a clean slate so an earlier test's cached
    volume_profile_24h/orderbook entry can't mask this test's mocks."""
    bms._cache.clear()
    yield
    bms._cache.clear()


# ---------------------------------------------------------------------------
# Canonical -> Binance Futures pair symbol, the choke point for legs 2/3
# ---------------------------------------------------------------------------

def test_binance_futures_symbol_mapping_all_six():
    """Every tracked symbol resolves to its Binance Futures pair symbol."""
    expected = {
        "BTC": "BTCUSDT",
        "ETH": "ETHUSDT",
        "SOL": "SOLUSDT",
        "HYPE": "HYPEUSDT",
        "ZEC": "ZECUSDT",
        "FARTCOIN": "FARTCOINUSDT",
    }
    assert set(BINANCE_FUTURES_PAIR_SYMBOL.keys()) == set(expected.keys())
    for base, pair in expected.items():
        assert get_binance_futures_symbol(base) == pair


def test_binance_futures_symbol_case_insensitive():
    assert get_binance_futures_symbol("btc") == "BTCUSDT"


def test_binance_futures_symbol_no_coverage_case():
    """An untracked symbol (not one of the six) returns None, not a guess."""
    assert get_binance_futures_symbol("DOGE") is None
    assert get_binance_futures_symbol("") is None
    assert get_binance_futures_symbol(None) is None


# ---------------------------------------------------------------------------
# LEG 1: volume profile reroute (canonical in -> profile out)
# ---------------------------------------------------------------------------

def _synthetic_bars(n=30, base_price=64000.0):
    """n synthetic (ts, open, high, low, close) 15m bars ending ~now, with real
    price spread, matching fetch_crypto_ohlc's return shape. Timestamps are
    fresh + incrementing (oldest->newest, newest ~= now) so the DEF-CRYPTO-VP-
    ANCHOR freshness guard (newest bar must be < 20 min old) does not reject
    them -- the fixed 2026-07-17 stamp this used before made every bar days
    stale and tripped that guard."""
    from datetime import timedelta
    bars = []
    now = datetime.now(timezone.utc)
    for i in range(n):
        ts = now - timedelta(minutes=15 * (n - 1 - i))
        px = base_price + (i % 5) * 50
        bars.append((ts, px, px + 30, px - 30, px + 10))
    return bars


def test_volume_profile_reroute_canonical_in_profile_out():
    """get_market_structure_context() takes a canonical ticker and, via the
    F-2 bar source, produces a real (non-error) volume profile -- proving
    the leg-1 reroute works without ever touching Binance Futures klines."""
    import asyncio

    async def _run():
        with patch(
            "jobs.crypto_bars.fetch_crypto_ohlc",
            new=AsyncMock(return_value=_synthetic_bars()),
        ) as mock_fetch:
            result = await get_market_structure_context(
                ticker="BTC", entry_price=64050.0, direction="LONG"
            )
            # Canonical ticker passed straight through to the F-2 source --
            # no Binance-pair conversion needed for this leg.
            mock_fetch.assert_awaited_once_with("BTC", use_daily=False)
            return result

    result = asyncio.run(_run())
    vp = result["volume_profile"]
    assert "error" not in vp, f"expected a real profile, got: {vp}"
    assert vp["poc"] > 0
    assert vp["vah"] >= vp["poc"] >= vp["val"]


def test_volume_profile_reroute_no_bars_is_honest_unavailable():
    """When the F-2 source has no LIVE bar_walk_source for a symbol, it
    returns [] (never raises) -- the leg must degrade honestly, not fabricate
    a score."""
    import asyncio

    async def _run():
        with patch(
            "jobs.crypto_bars.fetch_crypto_ohlc",
            new=AsyncMock(return_value=[]),
        ):
            return await get_market_structure_context(
                ticker="BTC", entry_price=64050.0, direction="LONG"
            )

    result = asyncio.run(_run())
    # vp_data stays at its {"error": "not fetched"} initial value -- the
    # volume-profile leg contributes 0, not a fabricated number.
    assert "error" in result["volume_profile"]


# ---------------------------------------------------------------------------
# LEG 2 / LEG 3: verify the pair symbol (not the bare canonical form) is what
# actually reaches the vendor call -- locks the boundary against a future
# normalization pass reintroducing the bare-symbol regression.
# ---------------------------------------------------------------------------

def test_cvd_leg_receives_pair_symbol_not_canonical():
    import asyncio

    async def _run():
        with patch(
            "jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(return_value=[])
        ), patch(
            "strategies.btc_market_structure._fetch_cvd",
            new=AsyncMock(return_value={"direction": "NEUTRAL"}),
        ) as mock_cvd:
            await get_market_structure_context(
                ticker="ETH", entry_price=1800.0, direction="LONG"
            )
            mock_cvd.assert_awaited_once_with("ETHUSDT")

    asyncio.run(_run())


def test_orderbook_leg_receives_pair_symbol_not_canonical():
    import asyncio

    async def _run():
        with patch(
            "jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(return_value=[])
        ), patch(
            "integrations.binance_futures.get_orderbook_depth",
            new=AsyncMock(return_value=None),
        ) as mock_ob:
            result = await get_market_structure_context(
                ticker="ZEC", entry_price=550.0, direction="LONG"
            )
            mock_ob.assert_awaited_once_with("ZECUSDT", limit=20)
            # Honest NA label, never a fabricated zero disguised as data.
            assert "NA:BINANCE_FUTURES_UNAVAILABLE" in result["orderbook"]["error"]

    asyncio.run(_run())
