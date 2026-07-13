"""Stater Swap v2 S-1 Phase 1 (F-1 task 1.4, AEGIS) — per-symbol input sanity
bounds for crypto vendor feeds.

Mirrors the existing Macro/Volatility Price Sanity Bounds pattern in
PROJECT_RULES.md (^VIX 9-90, ^VIX3M 9-60, DXY 80-120): out-of-range values are
rejected and never cached, never silently clamped or defaulted.

Bounds are deliberately generous — wide enough to never reject a real, if
extreme, market move; tight enough to catch parsing errors, decimal-shift
bugs, or a vendor returning garbage (e.g. a zero, a null coerced to 0, or a
different asset's price by symbol-mapping mistake). Reviewed 2026-07-13
against live prices observed during Phase 1 vendor testing (BTC ~$62-64K,
ETH ~$1.7-1.8K, SOL ~$74-78, HYPE ~$63, ZEC ~$495-540, FARTCOIN ~$0.14).
"""

from __future__ import annotations

from typing import Optional

# (low, high) inclusive bounds per symbol per feed type. Missing (symbol,
# feed_type) pair => UNVERIFIED, not silently unbounded — callers must treat
# a missing bounds entry as "do not cache" per the fail-visible principle.
PRICE_BOUNDS_USD: dict[str, tuple[float, float]] = {
    "BTC": (10_000, 500_000),
    "ETH": (200, 20_000),
    "SOL": (5, 2_000),
    "HYPE": (1, 500),
    "ZEC": (10, 5_000),
    "FARTCOIN": (0.01, 50),
}

# Funding rate is a per-interval percentage (matches the existing clients'
# convention of "value * 100" already being a percent, e.g. 0.05 = 0.05%).
# Real funding blowouts have hit ~1-3%/interval in extreme historical events;
# bounds are set well beyond that to avoid rejecting a genuine squeeze while
# still catching a decimal-shift bug (e.g. a raw fraction not multiplied by
# 100, which would show up as implausibly tiny, or an unconverted bps value,
# which would show up as implausibly huge).
FUNDING_RATE_PCT_BOUNDS: tuple[float, float] = (-5.0, 5.0)

# Open interest, USD notional. Order-of-magnitude bands per symbol — wide
# enough to track years of market growth/contraction without needing
# frequent revision, tight enough to catch a garbage/zero/mis-scaled read.
OPEN_INTEREST_USD_BOUNDS: dict[str, tuple[float, float]] = {
    "BTC": (1_000_000_000, 100_000_000_000),
    "ETH": (500_000_000, 50_000_000_000),
    "SOL": (100_000_000, 20_000_000_000),
    "HYPE": (10_000_000, 5_000_000_000),
    "ZEC": (5_000_000, 2_000_000_000),
    "FARTCOIN": (1_000_000, 2_000_000_000),
}

# Annualized basis, percent. Existing coinalyze/binance client logic already
# treats >15% as "extreme_contango" and <-5% as "backwardation" for SIGNAL
# purposes — sanity bounds must be wider than signal thresholds (a real
# signal-worthy value must never be rejected as implausible).
BASIS_ANNUALIZED_PCT_BOUNDS: tuple[float, float] = (-50.0, 150.0)

# 25-delta skew, percentage points (put IV - call IV). Existing client logic
# treats |skew| > 5 as signal-worthy; deep tail events can reach the low
# double digits.
SKEW_25D_PCT_BOUNDS: tuple[float, float] = (-40.0, 40.0)


def check_price(symbol: str, value: Optional[float]) -> tuple[bool, Optional[str]]:
    return _check(PRICE_BOUNDS_USD, symbol, value, "price")


def check_funding_rate(symbol: str, value: Optional[float]) -> tuple[bool, Optional[str]]:
    low, high = FUNDING_RATE_PCT_BOUNDS
    return _check_fixed(low, high, value, f"funding_rate[{symbol}]")


def check_open_interest(symbol: str, value: Optional[float]) -> tuple[bool, Optional[str]]:
    return _check(OPEN_INTEREST_USD_BOUNDS, symbol, value, "open_interest")


def check_basis_annualized(symbol: str, value: Optional[float]) -> tuple[bool, Optional[str]]:
    low, high = BASIS_ANNUALIZED_PCT_BOUNDS
    return _check_fixed(low, high, value, f"basis_annualized[{symbol}]")


def check_skew_25d(symbol: str, value: Optional[float]) -> tuple[bool, Optional[str]]:
    low, high = SKEW_25D_PCT_BOUNDS
    return _check_fixed(low, high, value, f"skew_25d[{symbol}]")


def _check(bounds_by_symbol: dict, symbol: str, value: Optional[float], label: str) -> tuple[bool, Optional[str]]:
    sym = (symbol or "").upper()
    if sym not in bounds_by_symbol:
        return False, f"{label}[{sym}]: no bounds configured (UNVERIFIED symbol) — refusing to cache unbounded value"
    low, high = bounds_by_symbol[sym]
    return _check_fixed(low, high, value, f"{label}[{sym}]")


def _check_fixed(low: float, high: float, value: Optional[float], label: str) -> tuple[bool, Optional[str]]:
    if value is None:
        return False, f"{label}: value is None"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False, f"{label}: value '{value}' is not numeric"
    if v < low or v > high:
        return False, f"{label}: value {v} outside bounds [{low}, {high}]"
    return True, None
