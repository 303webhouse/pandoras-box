"""DEF-CRYPTO-VP-ANCHOR (2026-07-22) -- regression coverage for the volume-
profile window-anchoring defect.

The bug: hub_get_crypto_market_profile and its scoring twin
get_market_structure_context selected the VP window with a POSITIONAL tail
slice `bars_1h[-24:]` over a bar list returned in VENDOR order (UW/OKX
newest-first, Binance oldest-first) and never sorted. On a newest-first list
`[-24:]` grabbed the OLDEST 24 bars -> a value area 3-5 days stale, entirely
outside the traded range, served as vp_status "ok" (fake-healthy).

Live 3-vendor natural experiment (2026-07-22): 5 of 6 symbols displaced
(BTC/ETH/SOL via UW, HYPE/FARTCOIN via OKX); ZEC (Binance-ascending) was the
sole clean control. These tests encode that experiment.

No live API calls or DB access -- vendor I/O is mocked. Async entrypoints are
driven via asyncio.run() (repo convention -- no pytest-asyncio marker).
"""

import sys
import os
import asyncio
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from strategies.btc_market_structure import compute_volume_profile
import strategies.btc_market_structure as bms
from hub_mcp.tools.crypto_market_profile import _va_outside_session


# --------------------------------------------------------------------------
# Guard predicate -- encodes the live 2026-07-22 three-vendor experiment.
# --------------------------------------------------------------------------

def test_va_outside_session_fires_on_displaced_symbols():
    """(vah, val, session_low, session_high) from the live 2026-07-22 sweep.
    The 5 displaced symbols must fire; ZEC (Binance control) must clear."""
    assert _va_outside_session(63150.23, 62758.83, 65484.00, 66113.98) is True   # BTC  (UW)  VAH < SL
    assert _va_outside_session(1838.97, 1824.36, 1911.56, 1941.60) is True        # ETH  (UW)  VAH < SL
    assert _va_outside_session(74.81, 74.32, 76.93, 77.90) is True                # SOL  (UW)  VAH < SL
    assert _va_outside_session(61.13, 60.77, 58.089, 59.223) is True              # HYPE (OKX) VAL > SH (mirror)
    assert _va_outside_session(517.27, 513.34, 511.37, 521.21) is False           # ZEC  (Binance) CONTROL -- in range


def test_va_outside_session_is_none_safe():
    assert _va_outside_session(None, 1.0, 2.0, 3.0) is False
    assert _va_outside_session(1.0, None, 2.0, 3.0) is False
    assert _va_outside_session(1.0, 2.0, None, 3.0) is False
    assert _va_outside_session(1.0, 2.0, 3.0, None) is False


# --------------------------------------------------------------------------
# Mechanism -- sort-before-slice selects the CURRENT window, not the stale tail.
# --------------------------------------------------------------------------

def _rising_bars_newest_first(old=60000.0, new=66000.0, n=200):
    """n 15m bars, price rising old->new over the span, newest bar at ~now.
    Returned NEWEST-FIRST (descending) -- the UW/OKX vendor order."""
    now = datetime.now(timezone.utc)
    asc = []
    for i in range(n):
        ts = now - timedelta(minutes=15 * (n - 1 - i))
        price = old + (new - old) * (i / (n - 1))
        asc.append((ts, price, price + 25.0, price - 25.0, price))  # (ts, o, h, l, c)
    return list(reversed(asc))  # descending


def _klines(bars):
    return [[int(b[0].timestamp() * 1000), b[1], b[2], b[3], b[4], 1.0] for b in bars]


def test_positional_slice_is_stale_sorted_slice_is_current():
    """Pure demonstration of the defect and the fix on the same bar list."""
    bars = _rising_bars_newest_first()  # descending (vendor order)
    buggy = compute_volume_profile(_klines(bars[-24:]))                                # OLD: positional tail
    fixed = compute_volume_profile(_klines(sorted(bars, key=lambda b: b[0])[-24:]))    # NEW: sort then slice
    assert buggy["poc"] < 61000, f"unsorted tail should anchor to the stale low, got {buggy['poc']}"
    assert fixed["poc"] > 65000, f"sorted tail should anchor to current tape, got {fixed['poc']}"
    assert fixed["poc"] - buggy["poc"] > 3000, "the fix must move POC off the multi-day-stale tail"


# --------------------------------------------------------------------------
# Integration -- the actual scoring path uses the current window post-fix, and
# fails closed to a 0 VP score (never a phantom -5) on stale bars.
# --------------------------------------------------------------------------

def test_get_market_structure_context_uses_current_window(monkeypatch):
    """FAILS AGAINST PRE-FIX CODE: pre-fix positional [-24:] on descending bars
    anchors POC to the stale ~60k tail; post-fix sort anchors it to current tape."""
    bars = _rising_bars_newest_first(old=60000.0, new=66000.0, n=200)  # descending, fresh

    async def _fake_fetch(ticker, use_daily=True):
        return bars

    monkeypatch.setattr("jobs.crypto_bars.fetch_crypto_ohlc", _fake_fetch)
    # Neutralize CVD + orderbook legs (no network): no pair mapping -> both score 0.
    monkeypatch.setattr("config.crypto_symbol_matrix.get_binance_futures_symbol", lambda t: None)
    bms._cache.clear()

    result = asyncio.run(bms.get_market_structure_context("BTC", entry_price=65950.0, direction="LONG"))
    vp = result["volume_profile"]
    assert "error" not in vp, f"expected a computed profile, got {vp}"
    assert vp["poc"] > 64000, f"POC {vp['poc']} must be in the current window, not the stale ~60k tail"


def test_stale_bars_fail_closed_to_zero_score(monkeypatch):
    """Bars all older than 20 min -> freshness guard trips -> vp error ->
    _score_volume_profile returns 0 (verified branch), never the -5 phantom."""
    now = datetime.now(timezone.utc)
    stale = [
        (now - timedelta(hours=48) - timedelta(minutes=15 * i), 63000.0, 63025.0, 62975.0, 63000.0)
        for i in range(120)
    ]

    async def _fake_fetch(ticker, use_daily=True):
        return stale

    monkeypatch.setattr("jobs.crypto_bars.fetch_crypto_ohlc", _fake_fetch)
    monkeypatch.setattr("config.crypto_symbol_matrix.get_binance_futures_symbol", lambda t: None)
    bms._cache.clear()

    result = asyncio.run(bms.get_market_structure_context("BTC", entry_price=65950.0, direction="LONG"))
    vp = result["volume_profile"]
    assert "error" in vp, "stale bars must fail closed, not produce a phantom value area"
    # All three legs neutralized -> score_modifier is exactly 0, proving the VP leg
    # contributed 0 (not the -5 "extended" phantom that contaminated Session_Sweep scores).
    assert result["score_modifier"] == 0, f"expected 0 modifier on stale VP, got {result['score_modifier']}"
    assert "volume profile unavailable" in result["reasoning"]


# --------------------------------------------------------------------------
# Source-level sort -- _fetch_full_ohlc normalizes vendor order for ALL
# consumers (the sibling fix; every downstream positional slice is chronological).
# --------------------------------------------------------------------------

def test_fetch_full_ohlc_sorts_source_level(monkeypatch):
    """_fetch_full_ohlc must return ascending-by-timestamp regardless of vendor
    order, so bars[-24:]/recent[-1]/walk in every consumer are chronological.
    FAILS pre-fix: UW/OKX return newest-first and the old code passed it through."""
    import jobs.crypto_bars as cb
    now = datetime.now(timezone.utc)
    # descending (newest-first) -- the UW/OKX vendor order
    desc = [(now - timedelta(minutes=15 * i), 100.0 + i, 100.5 + i, 99.5 + i, 100.0 + i) for i in range(30)]
    monkeypatch.setattr(
        cb, "get_symbol_entry",
        lambda s: {"bar_walk_source": {"status": "LIVE", "vendor": "uw_crypto_ohlc"}},
    )

    async def _fake_uw(base, size, limit=500):
        return desc

    monkeypatch.setattr(cb, "_fetch_uw_bars_full", _fake_uw)
    out = asyncio.run(cb._fetch_full_ohlc("BTC", use_daily=False))
    ts = [b[0] for b in out]
    assert ts == sorted(ts), "source fetch must emit ascending-by-timestamp"
    assert out[-1][0] == max(ts), "newest bar must be last, so consumer [-1] is the current bar"
    assert len(out) == 30


if __name__ == "__main__":
    import traceback
    tests = [
        test_va_outside_session_fires_on_displaced_symbols,
        test_va_outside_session_is_none_safe,
        test_positional_slice_is_stale_sorted_slice_is_current,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL: {t.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} pure tests passed (monkeypatch tests require pytest).")
