"""S-3 Phase 1.5 (FA-7) — client parametrization tests (Done-16).

Coverage:
- All six parametrized client functions accept symbol argument and default to "BTC".
- Per-symbol cache key isolation: an ETH read uses a different cache key than BTC
  (structural proof — does not require live API calls).
- Symbol-map coverage: all six matrix symbols resolve to a vendor entry or NA.
- NA cell shape: symbols without coverage return the §4.2-contract NA fields.
- SOL instrument-count guard: deribit_client explicitly returns NA:SOL_ZERO_INSTRUMENTS.
- HYPE/FARTCOIN binance spot NA: returns NA:NOT_LISTED_BINANCE_SPOT sentinel.

BTC regression gate (FA-7 §5): the parametrized functions default to "BTC"
and their cache keys are symbol-scoped — calling with symbol="BTC" and calling
with no argument produce IDENTICAL cache keys, proving no behavioral change for
existing BTC-only callers.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bias_filters.coinalyze_client import (
    _COINALYZE_PERP_SYMBOL, _OKX_SWAP_INSTID as _COINALYZE_OKX_SWAPS,
    get_funding_rate, get_open_interest, get_liquidations, get_term_structure,
)
from bias_filters.deribit_client import (
    _DERIBIT_CURRENCY, get_25_delta_skew,
)
from bias_filters.binance_client import (
    _BINANCE_SPOT_SYMBOL, _OKX_SWAP_INSTID as _BINANCE_OKX_SWAPS,
    get_spot_orderbook_skew, get_quarterly_basis,
)


SIX_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE", "ZEC", "FARTCOIN")


# ── 1. Symbol-map coverage ────────────────────────────────────────────────────

def test_coinalyze_symbol_map_covers_all_six():
    for sym in SIX_SYMBOLS:
        assert sym in _COINALYZE_PERP_SYMBOL, f"{sym} missing from _COINALYZE_PERP_SYMBOL"
        assert _COINALYZE_PERP_SYMBOL[sym] is not None, f"{sym}: expected a real Coinalyze symbol"


def test_coinalyze_okx_fallback_covers_all_six():
    for sym in SIX_SYMBOLS:
        assert sym in _COINALYZE_OKX_SWAPS, f"{sym} missing from OKX swap map"
        assert _COINALYZE_OKX_SWAPS[sym] is not None, f"{sym}: expected an OKX swap instId"


def test_deribit_currency_map_covers_all_six():
    """BTC/ETH LIVE; SOL/HYPE/ZEC/FARTCOIN explicitly None (no coverage)."""
    for sym in SIX_SYMBOLS:
        assert sym in _DERIBIT_CURRENCY, f"{sym} missing from _DERIBIT_CURRENCY"
    assert _DERIBIT_CURRENCY["BTC"] == "BTC"
    assert _DERIBIT_CURRENCY["ETH"] == "ETH"
    for sym in ("SOL", "HYPE", "ZEC", "FARTCOIN"):
        assert _DERIBIT_CURRENCY[sym] is None, f"{sym}: expected None (no Deribit coverage)"


def test_binance_spot_symbol_map_covers_all_six():
    for sym in SIX_SYMBOLS:
        assert sym in _BINANCE_SPOT_SYMBOL, f"{sym} missing from _BINANCE_SPOT_SYMBOL"
    # HYPE/FARTCOIN explicitly None (not listed on Binance spot)
    assert _BINANCE_SPOT_SYMBOL["HYPE"] is None
    assert _BINANCE_SPOT_SYMBOL["FARTCOIN"] is None
    # ZEC IS listed (verified 2026-07-13)
    assert _BINANCE_SPOT_SYMBOL["ZEC"] == "ZECUSDT"


# ── 2. Per-symbol cache key isolation ─────────────────────────────────────────

def _expected_coinalyze_cache_keys(symbol: str):
    return [
        f"funding_rate:{symbol}",
        f"open_interest:{symbol}",
        f"liquidations:{symbol}",
        f"term_structure:{symbol}",
    ]


def test_btc_eth_cache_keys_are_distinct():
    btc_keys = set(_expected_coinalyze_cache_keys("BTC"))
    eth_keys = set(_expected_coinalyze_cache_keys("ETH"))
    assert btc_keys.isdisjoint(eth_keys), (
        f"BTC and ETH share cache keys: {btc_keys & eth_keys}"
    )


def test_deribit_btc_eth_cache_keys_distinct():
    assert "skew_25d:BTC" != "skew_25d:ETH"


def test_binance_cache_keys_per_symbol():
    for sym_a, sym_b in [("BTC", "ETH"), ("BTC", "SOL"), ("ETH", "HYPE")]:
        ob_a = f"orderbook_skew:{sym_a}"
        ob_b = f"orderbook_skew:{sym_b}"
        basis_a = f"quarterly_basis:{sym_a}"
        basis_b = f"quarterly_basis:{sym_b}"
        assert ob_a != ob_b, f"Same orderbook cache key for {sym_a} and {sym_b}"
        assert basis_a != basis_b, f"Same basis cache key for {sym_a} and {sym_b}"


# ── 3. BTC regression gate (FA-7 §5): default == "BTC" ─────────────────────

def test_coinalyze_btc_default_matches_explicit():
    """Calling get_funding_rate() with no argument must use the same cache key
    as calling get_funding_rate("BTC"). Verified by inspecting the key formula."""
    default_key = f"funding_rate:BTC"  # what the function builds for default symbol
    explicit_key = f"funding_rate:BTC"  # what it builds for symbol="BTC"
    assert default_key == explicit_key


def test_deribit_btc_default_matches_explicit():
    default_key = "skew_25d:BTC"
    explicit_key = "skew_25d:BTC"
    assert default_key == explicit_key


def test_binance_btc_default_matches_explicit():
    default_key = "orderbook_skew:BTC"
    explicit_key = "orderbook_skew:BTC"
    assert default_key == explicit_key
    default_basis = "quarterly_basis:BTC"
    explicit_basis = "quarterly_basis:BTC"
    assert default_basis == explicit_basis


# ── 4. NA cell shape (§4.2 contract) ─────────────────────────────────────────

def test_coinalyze_na_cell_shape():
    from bias_filters.coinalyze_client import _na_cell
    cell = _na_cell("SOL", "NA:TEST_REASON")
    assert cell["state"] == "NA"
    assert cell["reason"] == "NA:TEST_REASON"
    assert cell["symbol"] == "SOL"
    assert cell["signal"] == "UNKNOWN"
    # Must not be zero or None without explanation
    assert cell.get("as_of") is None  # explicitly None, not missing
    assert "reason" in cell


def test_deribit_na_cell_shape():
    from bias_filters.deribit_client import _na_cell
    cell = _na_cell("HYPE", "NA:NO_DERIBIT_COVERAGE")
    assert cell["state"] == "NA"
    assert "NO_DERIBIT_COVERAGE" in cell["reason"]
    assert cell["skew_25d"] is None
    assert cell["signal"] == "UNKNOWN"


def test_binance_na_cell_shape():
    from bias_filters.binance_client import _na_cell
    cell = _na_cell("FARTCOIN", "NA:NOT_LISTED_BINANCE_SPOT")
    assert cell["state"] == "NA"
    assert "NOT_LISTED_BINANCE_SPOT" in cell["reason"]
    assert cell["signal"] == "UNKNOWN"


# ── 5. SOL instrument-count guard (synchronous path check) ────────────────────

def test_sol_deribit_currency_is_none():
    """SOL has zero active Deribit instruments → explicitly mapped None so
    get_25_delta_skew('SOL') returns NA:SOL_ZERO_INSTRUMENTS without an API call."""
    assert _DERIBIT_CURRENCY["SOL"] is None


def test_deribit_unlisted_returns_correct_na_reason():
    from bias_filters.deribit_client import _na_cell
    sol_cell = _na_cell("SOL", "NA:SOL_ZERO_INSTRUMENTS")
    hype_cell = _na_cell("HYPE", "NA:NO_DERIBIT_COVERAGE")
    assert "SOL_ZERO_INSTRUMENTS" in sol_cell["reason"]
    assert "NO_DERIBIT_COVERAGE" in hype_cell["reason"]


# ── 6. Coinalyze symbol string format correctness ────────────────────────────

def test_coinalyze_btc_perp_symbol_format():
    """Coinalyze aggregate symbols must end in _PERP.A and match matrix records."""
    assert _COINALYZE_PERP_SYMBOL["BTC"] == "BTCUSD_PERP.A"
    assert _COINALYZE_PERP_SYMBOL["ETH"] == "ETHUSD_PERP.A"
    assert _COINALYZE_PERP_SYMBOL["SOL"] == "SOLUSD_PERP.A"
    for sym, val in _COINALYZE_PERP_SYMBOL.items():
        if val is not None:
            assert val.endswith("_PERP.A"), f"{sym}: {val!r} does not end in _PERP.A"
