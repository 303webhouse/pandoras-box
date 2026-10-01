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
# Coinbase Exchange public market data: free, keyless, US-reachable from Railway.
# Stater Phase 0 (R-IV.619) moved BTC/ETH/SOL bars here from UW's metered OHLC.
COINBASE_EXCHANGE_URL = "https://api.exchange.coinbase.com"
OKX_MARKET_URL = "https://www.okx.com/api/v5/market"

# ── Who is spending the UW crypto-bar budget — R-IV.624(b) ───────────────
# Every crypto bar fetch used to reach the governor tagged `outcome_resolver`,
# this module's first consumer. Five more arrived; the tag did not move. So the
# governor counted six consumers under one wrong name, its 4,500 quota sat on a
# path that spends ~370/day, and a budget alarm naming `outcome_resolver` sent a
# reader to the wrong job. Measured 2026-10-01: an open Stater tab is 4 calls
# per 30s (11,520/day, 41% of DAILY_BUDGET) and was INDISTINGUISHABLE here from
# the resolver's own traffic.
#
# These constants are the ONE place a crypto-bar caller tag is written. Callers
# pass one; `caller` has no default, so a new consumer cannot inherit another's
# name by omission. test_crypto_bar_caller_tags.py proves every tag below has
# an explicit uw_governor.QUOTAS entry — an undeclared tag silently takes
# DEFAULT_QUOTA 500, which is exactly how `outcome_resolver` came to spend
# 2,764 against a default meant for unknown code paths (see that table's note).
CALLER_OUTCOME_RESOLVER = "crypto_bars_outcome_resolver"
CALLER_TAPE_HEALTH = "crypto_bars_tape_health"
CALLER_STATE_API = "crypto_bars_state_api"
CALLER_REGIME = "crypto_bars_regime"
CALLER_VP_MCP = "crypto_bars_vp_mcp"
CALLER_MARKET_STRUCTURE = "crypto_bars_market_structure"

CRYPTO_BAR_CALLERS = frozenset({
    CALLER_OUTCOME_RESOLVER,
    CALLER_TAPE_HEALTH,
    CALLER_STATE_API,
    CALLER_REGIME,
    CALLER_VP_MCP,
    CALLER_MARKET_STRUCTURE,
})


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


async def _fetch_uw_bars_full(base_symbol: str, candle_size: str, *, caller: str, limit: int = 500) -> List[Tuple[datetime, float, float, float, float]]:
    """Returns (ts, open, high, low, close) tuples.

    `caller` must be one of CRYPTO_BAR_CALLERS. The assert guards a programming
    error, not a data condition — every value reaching it is a module constant,
    so it cannot fire on live traffic, and it keeps an unrecognised tag from
    being spent under DEFAULT_QUOTA where no one would look for it.
    """
    from integrations import uw_api

    assert caller in CRYPTO_BAR_CALLERS, f"undeclared crypto-bar caller tag: {caller!r}"
    pair = f"{base_symbol}-USD"
    resp = await uw_api._uw_request(f"/api/crypto/{pair}/ohlc/{candle_size}", params={"limit": limit}, caller=caller)
    data = resp.get("data") if isinstance(resp, dict) else None
    if not data:
        return []
    bars = []
    for row in data:
        ts = _parse_iso_ts(row.get("start_time")) or _parse_iso_ts(row.get("timestamp"))
        if ts is None:
            continue
        try:
            bars.append((ts, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])))
        except (KeyError, TypeError, ValueError):
            continue
    return bars


async def _fetch_coinbase_candles_full(base_symbol: str, use_daily: bool) -> List[Tuple[datetime, float, float, float, float]]:
    """Returns (ts, open, high, low, close) tuples from Coinbase Exchange public candles.

    Row order on the wire is [time, LOW, HIGH, open, close, volume] -- low before
    high, unlike every other vendor here -- newest first. Up to 350 rows per call
    (measured 2026-10-01: 350 daily / 350 15-min rows for BTC, ETH and SOL).
    """
    product = f"{base_symbol}-USD"
    granularity = 86400 if use_daily else 900
    # 15-min bars take a second, older page: the outcome resolver walks 15-min bars
    # for signals up to 55 days old, and UW's 500-row window reached ~5.2 days.
    # Two pages reach ~7 days, so no signal loses coverage in the move.
    pages = 1 if use_daily else 2
    rows: list = []
    try:
        async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": "pandoras-box/stater"}) as client:
            params = {"granularity": granularity}
            for _ in range(pages):
                r = await client.get(f"{COINBASE_EXCHANGE_URL}/products/{product}/candles", params=params)
                if r.status_code != 200:
                    logger.warning("Coinbase candles %s failed: HTTP %d", product, r.status_code)
                    break
                page = r.json()
                if not isinstance(page, list) or not page:
                    break
                rows.extend(page)
                oldest = min(int(x[0]) for x in page)
                params = {"granularity": granularity,
                          "start": datetime.fromtimestamp(oldest - 300 * granularity, tz=timezone.utc).isoformat(),
                          "end": datetime.fromtimestamp(oldest - granularity, tz=timezone.utc).isoformat()}
    except Exception as e:
        logger.warning("Coinbase candles %s request failed: %s", product, e)
    seen = set()
    bars = []
    for row in rows:
        if not isinstance(row, list) or not row or row[0] in seen:
            continue
        seen.add(row[0])
        try:
            ts = datetime.fromtimestamp(int(row[0]), tz=timezone.utc)
            lo, hi, op, cl = float(row[1]), float(row[2]), float(row[3]), float(row[4])
        except (IndexError, TypeError, ValueError):
            continue
        if not (lo <= min(op, cl) and hi >= max(op, cl) and lo > 0):
            continue   # a row whose own range does not contain its open/close is not a bar
        bars.append((ts, op, hi, lo, cl))
    return bars


async def _fetch_binance_spot_klines_full(base_symbol: str, interval: str, limit: int = 500) -> List[Tuple[datetime, float, float, float, float]]:
    """Returns (ts, open, high, low, close) tuples."""
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
            # [open_time, open, high, low, close, ...]
            bars.append((ts, float(row[1]), float(row[2]), float(row[3]), float(row[4])))
        except (IndexError, TypeError, ValueError):
            continue
    return bars


async def _fetch_okx_candles_full(base_symbol: str, bar: str, limit: int = 300) -> List[Tuple[datetime, float, float, float, float]]:
    """Returns (ts, open, high, low, close) tuples."""
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
            # [ts, o, h, l, c, ...]
            bars.append((ts, float(row[1]), float(row[2]), float(row[3]), float(row[4])))
        except (IndexError, TypeError, ValueError):
            continue
    return bars


# Stater Phase 0 (R-IV.619): one bar set per (symbol, interval) is shared by every
# consumer for a short window. Before this, each of the regime job, tape-health
# event detection, the outcome resolver and every GET /crypto/state (ATR) fetched
# its own copy -- the /crypto/state path alone did so on every 30-second page poll.
# A 15-minute bar cannot change faster than its own close, so 5 minutes of reuse
# loses nothing a 15-minute consumer could see. Empty results are never cached,
# so a vendor hiccup is retried on the next call rather than remembered.
BARS_CACHE_TTL_SECONDS = {False: 300, True: 3600}   # keyed by use_daily
_bars_cache: dict = {}


async def _fetch_full_ohlc(base_symbol: str, use_daily: bool, *, caller: str) -> List[Tuple[datetime, float, float, float, float]]:
    """Shared vendor dispatch, per crypto_symbol_matrix's bar_walk_source, behind a
    short per-(symbol, interval) cache. Returns [] (never raises) if the symbol has
    no LIVE bar_walk_source. Internal -- fetch_crypto_bars() and fetch_crypto_ohlc()
    both wrap this. A cache hit spends nothing, so only the caller whose call
    reached the vendor is counted against its quota.
    """
    import time as _time
    # The vendor is part of the key, so re-pointing a symbol in the matrix can
    # never serve the previous vendor's bars from memory.
    vendor = ((get_symbol_entry(base_symbol) or {}).get("bar_walk_source") or {}).get("vendor")
    key = (base_symbol, bool(use_daily), vendor)
    hit = _bars_cache.get(key)
    if hit and _time.monotonic() - hit[0] < BARS_CACHE_TTL_SECONDS[bool(use_daily)]:
        return list(hit[1])
    bars = await _fetch_full_ohlc_uncached(base_symbol, use_daily, caller=caller)
    if bars:
        _bars_cache[key] = (_time.monotonic(), bars)
    return list(bars)


async def _fetch_full_ohlc_uncached(base_symbol: str, use_daily: bool, *, caller: str) -> List[Tuple[datetime, float, float, float, float]]:
    """Vendor dispatch without the cache."""
    entry = get_symbol_entry(base_symbol)
    if not entry:
        logger.debug("No matrix entry for crypto symbol %s -- shadow-only, skipping", base_symbol)
        return []

    bar_walk = entry.get("bar_walk_source", {})
    if bar_walk.get("status") != "LIVE":
        logger.debug("%s bar_walk_source status=%s (not LIVE) -- shadow-only, skipping", base_symbol, bar_walk.get("status"))
        return []

    vendor = bar_walk.get("vendor")
    if vendor == "coinbase_exchange_candles":
        bars = await _fetch_coinbase_candles_full(base_symbol, use_daily)
        if not bars:
            # Free fallback, same instrument family the tape-health engine already reads.
            bars = await _fetch_okx_candles_full(base_symbol, "1D" if use_daily else "15m")
    elif vendor == "uw_crypto_ohlc":
        # Retained for any matrix entry that still names it; since Stater Phase 0 no
        # tracked symbol does, so this branch spends no UW calls in production.
        bars = await _fetch_uw_bars_full(base_symbol, "1d" if use_daily else "15m", caller=caller)
    elif vendor == "binance_spot_klines":
        bars = await _fetch_binance_spot_klines_full(base_symbol, "1d" if use_daily else "15m")
    elif vendor == "okx_candles":
        bars = await _fetch_okx_candles_full(base_symbol, "1D" if use_daily else "15m")
    else:
        logger.warning("Unknown bar_walk_source vendor '%s' for %s -- shadow-only, skipping", vendor, base_symbol)
        return []

    # DEF-CRYPTO-VP-ANCHOR sibling fix (2026-07-22): vendors disagree on order --
    # UW and OKX return newest-first (descending), Binance oldest-first
    # (ascending). Normalize to ASCENDING here, at the single source, so every
    # consumer's positional slice / [-1] / touch-walk is chronological. This
    # generalizes the local fix crypto_regime.py:115 applied for exactly one
    # consumer while five siblings stayed exposed (VP tool + scoring twin, the
    # CVD event engine, the crypto-state ATR). Per-consumer sorts (VP surfaces,
    # regime, _walk_touch) remain as defense-in-depth.
    return sorted(bars, key=lambda b: b[0])


async def fetch_crypto_bars(base_symbol: str, signal_ts: datetime, use_daily: bool, *, caller: str) -> List[Tuple[datetime, float, float]]:
    """Dispatch to the correct vendor per crypto_symbol_matrix's bar_walk_source
    for `base_symbol`. Returns [] (never raises) if the symbol has no LIVE
    bar_walk_source -- the caller (outcome_resolver) treats that as
    "cannot resolve, stay shadow-only," per F-2 task 2.1's explicit
    shadow-only-when-unsanctioned requirement.

    (ts, high, low) only -- outcome_resolver's touch-detection walk doesn't
    need open/close. Existing callers/contract unchanged; see
    fetch_crypto_ohlc() for the full-OHLC variant (S-2 regime classifier).
    """
    full = await _fetch_full_ohlc(base_symbol, use_daily, caller=caller)
    return [(ts, hi, lo) for ts, _o, hi, lo, _c in full]


async def fetch_crypto_ohlc(base_symbol: str, use_daily: bool = True, *, caller: str) -> List[Tuple[datetime, float, float, float, float]]:
    """Full (ts, open, high, low, close) tuples via the same per-symbol vendor
    routing as fetch_crypto_bars() -- for consumers that need close prices
    (DMA, slope, ADX). S-2 (R-1) regime classifier's only consumer today.
    Returns [] (never raises) if the symbol has no LIVE bar_walk_source.
    """
    return await _fetch_full_ohlc(base_symbol, use_daily, caller=caller)
