"""
Sector Constituent Refresh — Phase A (2026-05-22)

Populates the canonical Redis envelope cache (`integrations/sector_cache.py`)
with per-constituent WK%, MO%, and RSI(14) for every ticker in the
`sector_constituents` table. The Sector Heatmap popup and the ticker profile
popup read from this cache; the route handlers never call UW directly for
these three fields anymore.

Two refresh entry points are exported, each driven by its own scheduler loop
in `main.py`:

- `refresh_fast()`  — WK% + RSI(14). Cadence: 60s during market hours, 300s
                      off-hours. Updates the two fields that move intraday.
- `refresh_slow()`  — MO%. Cadence: 3600s (1h) regardless of market state.
                      The 21-session derivative does not need minute-fresh
                      refresh and the slower cadence preserves rate-limit
                      headroom for the fast loop.

Rate-limit envelope (UW Basic plan, 120 req/min):
- Fast tick attempts up to 2 calls per constituent (OHLC + technical-indicator
  RSI). The UW client's token-bucket limiter (`_consume_token` in
  `integrations/uw_api.py`) naturally throttles the loop without explicit
  pacing here.
- When headroom drops below ~20% of the bucket capacity, the fast loop drops
  the lowest-priority refresh first (MO via the slow loop will defer its
  next tick if invoked while the fast loop is mid-cycle). RSI is preserved
  because it is the most operationally visible gap in the popup today.

Cache semantics: writes always carry the current timestamp via
`sector_cache.write_field`. A `value=None` write is intentional — it tells
readers the refresh ran but UW returned no usable data, which is distinct
from "we have not attempted recently" (absent key).

The job logs structured audit lines: `[sector_refresh]` prefix, the loop
tag (fast/slow), counts of refreshed/failed/skipped constituents per tick.
Per `_shared/TITANS_RULES.md`, observable side effects (cache key writes)
are the closure proof — log lines are the audit trail.
"""

import asyncio
import logging
import time
from typing import List, Optional

from database.postgres_client import get_postgres_client
from integrations import sector_cache
from integrations.uw_api import get_ohlc, get_technical_indicator

logger = logging.getLogger("sector_refresh")

WK_OFFSET = 5     # 5 regular sessions ago → week-to-date change
MO_OFFSET = 21    # 21 regular sessions ago → month-to-date change

# Headroom guard: when the UW token bucket has fewer than this fraction of its
# capacity available, the fast loop skips the lower-priority refresh. The
# bucket's actual capacity (_bucket_max) is 120; 0.20 ratio leaves ~24 tokens
# of headroom for other UW callers (committee enrichment, ticker profile, etc.)
HEADROOM_GUARD_RATIO = 0.20


async def _fetch_constituent_universe() -> List[str]:
    """Load the constituent ticker universe from Postgres.

    Returns the deduped list of constituent tickers across all sector ETFs.
    Order is by sector ETF then rank — gives a stable iteration order so
    Redis writes are predictable.
    """
    pool = await get_postgres_client()
    if not pool:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT ticker FROM sector_constituents "
            "ORDER BY ticker"
        )
    return [r["ticker"] for r in rows]


def _regular_session_closes(bars: list) -> List[float]:
    """Extract close prices from UW OHLC bars, regular-session only.

    UW returns bars tagged with `market_time` ∈ {'pr', 'r', 'po'}. We filter
    to regular sessions for change-vs-N-sessions-ago math; including extended
    hours bars would double-count days.
    """
    closes: List[float] = []
    for b in bars or []:
        if b.get("market_time") != "r":
            continue
        c = b.get("close")
        if c is None:
            continue
        try:
            closes.append(float(c))
        except (TypeError, ValueError):
            continue
    return closes


def _pct_change_back(closes: List[float], offset: int) -> Optional[float]:
    """% change from closes[-offset-1] to closes[-1]. None if not enough data."""
    if len(closes) < offset + 1:
        return None
    old = closes[-(offset + 1)]
    if not old:
        return None
    return round((closes[-1] / old - 1) * 100, 2)


def _check_headroom() -> float:
    """Return the current token-bucket headroom ratio (0..1).

    Reads the live module-level bucket state from `integrations.uw_api`. A
    value < HEADROOM_GUARD_RATIO is the signal to start shedding low-priority
    refreshes this tick.
    """
    try:
        from integrations import uw_api as _uw
        if _uw._bucket_max <= 0:
            return 1.0
        return max(0.0, min(1.0, _uw._bucket_tokens / _uw._bucket_max))
    except Exception:
        return 1.0


async def _refresh_ohlc_derived(
    ticker: str,
    *,
    refresh_wk: bool,
    refresh_mo: bool,
) -> dict:
    """Pull one ticker's OHLC and write the requested derived fields.

    Returns a per-call status dict for the caller to aggregate audit counts.
    """
    status = {"wk_written": False, "mo_written": False, "wk_value": None, "mo_value": None}
    if not (refresh_wk or refresh_mo):
        return status

    # Pull 35 calendar days to comfortably cover 21 trading sessions + buffer
    bars = await get_ohlc(ticker, "1d", lookback_days=35)
    closes = _regular_session_closes(bars or [])
    if len(closes) < 2:
        # Record null writes so readers know the attempt ran but data was unavailable
        if refresh_wk:
            await sector_cache.write_field(ticker, "wk_change_pct", None)
        if refresh_mo:
            await sector_cache.write_field(ticker, "mo_change_pct", None)
        return status

    if refresh_wk:
        wk_value = _pct_change_back(closes, WK_OFFSET)
        ok = await sector_cache.write_field(ticker, "wk_change_pct", wk_value)
        status["wk_written"] = ok
        status["wk_value"] = wk_value

    if refresh_mo:
        mo_value = _pct_change_back(closes, MO_OFFSET)
        ok = await sector_cache.write_field(ticker, "mo_change_pct", mo_value)
        status["mo_written"] = ok
        status["mo_value"] = mo_value

    return status


async def _refresh_rsi(ticker: str) -> bool:
    """Pull RSI(14) and write the envelope. Returns True on successful write."""
    payload = await get_technical_indicator(ticker, "RSI", lookback=14)
    if payload is None:
        await sector_cache.write_field(ticker, "rsi_14", None)
        return False

    # UW returns either a dict with an `rsi` field or a list of timestamped
    # readings — accept both, prefer the latest value.
    value: Optional[float] = None
    if isinstance(payload, dict):
        v = payload.get("rsi") or payload.get("value")
        if v is not None:
            try:
                value = float(v)
            except (TypeError, ValueError):
                value = None
    elif isinstance(payload, list) and payload:
        latest = payload[-1] if isinstance(payload[-1], dict) else payload[0]
        if isinstance(latest, dict):
            v = latest.get("rsi") or latest.get("value")
            if v is not None:
                try:
                    value = float(v)
                except (TypeError, ValueError):
                    value = None

    await sector_cache.write_field(ticker, "rsi_14", value)
    return value is not None


async def refresh_fast() -> dict:
    """One fast-loop tick: refresh WK% + RSI(14) for every constituent.

    Iterates the full universe sequentially; the UW client's token-bucket
    rate limiter throttles the cadence so we don't need to pace explicitly.
    Headroom guard: if the bucket drops below HEADROOM_GUARD_RATIO partway
    through the tick, RSI refresh is preserved (most operationally visible
    gap) and WK refresh is dropped for remaining tickers.

    Returns audit counts for the scheduler loop to log.
    """
    universe = await _fetch_constituent_universe()
    if not universe:
        logger.warning("[sector_refresh] fast tick: empty constituent universe — seed step pending?")
        return {"loop": "fast", "tickers": 0, "wk_ok": 0, "rsi_ok": 0, "failures": 0, "skipped_wk": 0}

    started = time.monotonic()
    wk_ok = 0
    rsi_ok = 0
    failures = 0
    skipped_wk = 0

    logger.info("[sector_refresh] fast tick start — universe=%d", len(universe))

    for ticker in universe:
        # Re-check headroom each iteration; if it sinks mid-tick, drop WK first
        refresh_wk = _check_headroom() >= HEADROOM_GUARD_RATIO
        if not refresh_wk:
            skipped_wk += 1

        try:
            status = await _refresh_ohlc_derived(ticker, refresh_wk=refresh_wk, refresh_mo=False)
            if status["wk_written"]:
                wk_ok += 1
            ok = await _refresh_rsi(ticker)
            if ok:
                rsi_ok += 1
        except Exception as e:
            failures += 1
            logger.debug("[sector_refresh] fast tick failure for %s: %s", ticker, e)

    elapsed = round(time.monotonic() - started, 1)
    logger.info(
        "[sector_refresh] fast tick complete — universe=%d wk_ok=%d rsi_ok=%d "
        "failures=%d skipped_wk=%d elapsed=%.1fs",
        len(universe), wk_ok, rsi_ok, failures, skipped_wk, elapsed,
    )
    return {
        "loop": "fast",
        "tickers": len(universe),
        "wk_ok": wk_ok,
        "rsi_ok": rsi_ok,
        "failures": failures,
        "skipped_wk": skipped_wk,
        "elapsed_s": elapsed,
    }


async def refresh_slow() -> dict:
    """One slow-loop tick: refresh MO% for every constituent.

    MO% derives from a 21-session-old close. It does not need minute-fresh
    refresh — the slow loop fires once per hour regardless of market state.
    Headroom guard is not applied here; the slow loop's cadence already keeps
    UW load minimal (one full pass per hour).
    """
    universe = await _fetch_constituent_universe()
    if not universe:
        logger.warning("[sector_refresh] slow tick: empty constituent universe")
        return {"loop": "slow", "tickers": 0, "mo_ok": 0, "failures": 0}

    started = time.monotonic()
    mo_ok = 0
    failures = 0

    logger.info("[sector_refresh] slow tick start — universe=%d", len(universe))

    for ticker in universe:
        try:
            status = await _refresh_ohlc_derived(ticker, refresh_wk=False, refresh_mo=True)
            if status["mo_written"]:
                mo_ok += 1
        except Exception as e:
            failures += 1
            logger.debug("[sector_refresh] slow tick failure for %s: %s", ticker, e)

    elapsed = round(time.monotonic() - started, 1)
    logger.info(
        "[sector_refresh] slow tick complete — universe=%d mo_ok=%d failures=%d elapsed=%.1fs",
        len(universe), mo_ok, failures, elapsed,
    )
    return {
        "loop": "slow",
        "tickers": len(universe),
        "mo_ok": mo_ok,
        "failures": failures,
        "elapsed_s": elapsed,
    }
