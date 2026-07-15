"""Stater Swap v2 S-1 Phase 2 (F-2) — crypto bar-fetching for outcome_resolver.py.

Provides the asset-class-aware bars layer the 15-min BAR_WALK resolver needs:
ticker normalization (signals.ticker varies by writer -- Yahoo-style "BTC-USD"
from Crypto Scanner, Binance-native "BTCUSDT" from Session_Sweep, TradingView
".P"-suffixed from the webhook path) and per-symbol bar fetching dispatched
via each symbol's `bar_walk_source` in crypto_symbol_matrix.py -- NOT a single
universal crypto bars source. Phase 1 findings (symbol-capability-matrix.md)
proved a one-size-fits-all rule breaks silently: UW covers BTC/ETH/SOL bars
but returns an empty candle array for ZEC despite ZEC's quote endpoint
working, and has no data at all for HYPE/FARTCOIN.

All three per-symbol sources (UW crypto OHLC, Binance spot klines, OKX
candles) were live-verified at 15-minute granularity on 2026-07-13 before
this module was wired into the resolver -- see
docs/strategy-reviews/stater-swap-redesign/s1-phase2-findings.md.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import httpx

from config.crypto_symbol_matrix import get_symbol_entry

logger = logging.getLogger(__name__)

_CRYPTO_BASE_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE", "ZEC", "FARTCOIN")
_KNOWN_SUFFIXES = ("-USD", "USD", "-USDT", "USDT", "PERP", "-PERP", "USDTPERP")

BINANCE_SPOT_URL = "https://data-api.binance.vision/api/v3"
OKX_MARKET_URL = "https://www.okx.com/api/v5/market"


def normalize_crypto_ticker(raw_ticker: Optional[str]) -> Optional[str]:
    """Map a raw signals.ticker value to one of the six tracked base symbols.

    Returns None if the ticker doesn't match a known base+suffix pattern --
    callers must treat that as "cannot resolve," never guess.
    """
    t = (raw_ticker or "").upper().strip()
    if not t:
        return None
    if t.endswith(".P"):
        t = t[:-2]
    for base in _CRYPTO_BASE_SYMBOLS:
        if t == base:
            return base
        if t.startswith(base) and t[len(base):] in _KNOWN_SUFFIXES:
            return base
    return None


def _parse_iso_ts(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        s = raw.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


async def _fetch_uw_bars(base_symbol: str, candle_size: str, limit: int = 500) -> List[Tuple[datetime, float, float]]:
    from integrations import uw_api

    pair = f"{base_symbol}-USD"
    resp = await uw_api._uw_request(f"/api/crypto/{pair}/ohlc/{candle_size}", params={"limit": limit}, caller="outcome_resolver")
    data = resp.get("data") if isinstance(resp, dict) else None
    if not data:
        return []
    bars = []
    for row in data:
        ts = _parse_iso_ts(row.get("start_time")) or _parse_iso_ts(row.get("timestamp"))
        if ts is None:
            continue
        try:
            bars.append((ts, float(row["high"]), float(row["low"])))
        except (KeyError, TypeError, ValueError):
            continue
    return bars


async def _fetch_binance_spot_klines(base_symbol: str, interval: str, limit: int = 500) -> List[Tuple[datetime, float, float]]:
    pair = f"{base_symbol}USDT"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(f"{BINANCE_SPOT_URL}/klines", params={"symbol": pair, "interval": interval, "limit": limit})
            if r.status_code != 200:
                logger.warning("Binance spot klines %s failed: HTTP %d", pair, r.status_code)
                return []
            rows = r.json()
    except Exception as e:
        logger.warning("Binance spot klines %s request failed: %s", pair, e)
        return []
    bars = []
    for row in rows or []:
        try:
            ts = datetime.fromtimestamp(row[0] / 1000.0, tz=timezone.utc)
            bars.append((ts, float(row[2]), float(row[3])))  # [open_time, open, high, low, close, ...]
        except (IndexError, TypeError, ValueError):
            continue
    return bars


async def _fetch_okx_candles(base_symbol: str, bar: str, limit: int = 300) -> List[Tuple[datetime, float, float]]:
    inst = f"{base_symbol}-USDT-SWAP"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(f"{OKX_MARKET_URL}/candles", params={"instId": inst, "bar": bar, "limit": limit})
            if r.status_code != 200:
                logger.warning("OKX candles %s failed: HTTP %d", inst, r.status_code)
                return []
            body = r.json()
    except Exception as e:
        logger.warning("OKX candles %s request failed: %s", inst, e)
        return []
    rows = body.get("data") if isinstance(body, dict) else None
    bars = []
    for row in rows or []:
        try:
            ts = datetime.fromtimestamp(int(row[0]) / 1000.0, tz=timezone.utc)
            bars.append((ts, float(row[2]), float(row[3])))  # [ts, o, h, l, c, ...]
        except (IndexError, TypeError, ValueError):
            continue
    return bars


async def fetch_crypto_bars(base_symbol: str, signal_ts: datetime, use_daily: bool) -> List[Tuple[datetime, float, float]]:
    """Dispatch to the correct vendor per crypto_symbol_matrix's bar_walk_source
    for `base_symbol`. Returns [] (never raises) if the symbol has no LIVE
    bar_walk_source -- the caller (outcome_resolver) treats that as
    "cannot resolve, stay shadow-only," per F-2 task 2.1's explicit
    shadow-only-when-unsanctioned requirement.
    """
    entry = get_symbol_entry(base_symbol)
    if not entry:
        logger.debug("No matrix entry for crypto symbol %s -- shadow-only, skipping", base_symbol)
        return []

    bar_walk = entry.get("bar_walk_source", {})
    if bar_walk.get("status") != "LIVE":
        logger.debug("%s bar_walk_source status=%s (not LIVE) -- shadow-only, skipping", base_symbol, bar_walk.get("status"))
        return []

    vendor = bar_walk.get("vendor")
    if vendor == "uw_crypto_ohlc":
        return await _fetch_uw_bars(base_symbol, "1d" if use_daily else "15m")
    if vendor == "binance_spot_klines":
        return await _fetch_binance_spot_klines(base_symbol, "1d" if use_daily else "15m")
    if vendor == "okx_candles":
        return await _fetch_okx_candles(base_symbol, "1D" if use_daily else "15m")

    logger.warning("Unknown bar_walk_source vendor '%s' for %s -- shadow-only, skipping", vendor, base_symbol)
    return []
