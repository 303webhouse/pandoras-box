"""
Sector Constituent Refresh — Phase A (2026-05-22), revised Phase A.3 (2026-05-22)

Populates the canonical Redis envelope cache (`integrations/sector_cache.py`)
with per-constituent WK%, MO%, and RSI(14) for the **top-3-per-sector** ticker
universe. The Sector Heatmap popup and the ticker profile popup read from
this cache; the route handlers never call UW directly for these three fields.

Phase A.3 changes (2026-05-22, incident remediation):
- Universe cut from ~220 constituents → ~33 (top-3 per sector ETF, ordered by
  `rank_in_sector` in `sector_constituents`).
- Refresh loops pause during market-closed hours via `_is_market_hours()`
  reused from `backend/api/sectors.py` (no new market-hours logic invented).
- New `refresh_close_snapshot()` runs once per weekday at 16:05 ET to capture
  the official 4 PM close into the cache as the canonical close-state value
  (scheduled by `sector_refresh_close_snapshot_loop` in `main.py`).
- Audit logging extended: per-tick universe / attempted / succeeded / 429d /
  duration_ms metrics. The 429 count is sampled from `uw_api.get_total_429s()`
  (delta between start and end of tick).

Two refresh entry points are exported, each driven by its own scheduler loop
in `main.py`:

- `refresh_fast()`  — WK% + RSI(14). 60s cadence during market hours; the
                      market-state guard makes off-hours invocations no-ops.
- `refresh_slow()`  — MO%. 3600s cadence; same market-state guard applies.
- `refresh_close_snapshot()` — all three fields, fired once at 16:05 ET on
                      weekdays regardless of the regular-hours guard.

Cache semantics (unchanged from Phase A):
- Envelopes carry the timestamp of the refresh write, not the underlying
  market timestamp. Readers infer close-state by comparing `ts` against the
  current market state plus the most recent close timestamp.
- `value=None` writes are intentional — they record that a refresh attempt
  ran but UW returned no usable data.
"""

import asyncio
import logging
import time
from typing import List, Optional, Set

from database.postgres_client import get_postgres_client
from integrations import sector_cache
from integrations.uw_api import get_ohlc, get_technical_indicator, get_total_429s
from integrations.uw_governor import is_unavailable

# B3 (2026-06-16): inter-request spacing inside a tick so the sector loop
# self-paces at the source (~2 req/s) and never drains the shared 60-token
# bucket — this is what protects foreground (quotes/chains) from being paced
# behind a sector burst. 0.5s matches the existing uw_flow poll precedent.
# A ~33-ticker tick spreads to ~33s, well inside the 180s in-market cadence.
INTER_REQUEST_SLEEP = 0.5

logger = logging.getLogger("sector_refresh")

WK_OFFSET = 5     # 5 regular sessions ago → week-to-date change
MO_OFFSET = 21    # 21 regular sessions ago → month-to-date change

# Phase A.3 (2026-05-22): refresh universe is top-N-per-sector by rank_in_sector.
# Cut from ~220 (full table) to ~33 (11 sectors × 3) to keep UW call volume
# inside the Basic-plan rate-limit envelope.
TOP_N_PER_SECTOR = 3

# Headroom guard retained from Phase A: when the UW token bucket has fewer
# than this fraction of its capacity available, the fast loop skips the
# lower-priority refresh. Less load-relevant now (universe is small) but
# defensive against bursts when other UW callers are heavy.
HEADROOM_GUARD_RATIO = 0.20


def _is_market_hours_safe() -> bool:
    """Detect US regular-session market state.

    Imports the existing `_is_market_hours()` helper from `api/sectors.py`
    per Phase A.3 brief direction (do not invent new market-hours logic).
    Falls back to inline ET-hours check if the import fails for any reason
    so that the refresh job never crashes on startup ordering issues.
    """
    try:
        from api.sectors import _is_market_hours
        return _is_market_hours()
    except Exception:
        try:
            import pytz
            from datetime import datetime as _dt
            et = _dt.now(pytz.timezone("America/New_York"))
            if et.weekday() >= 5:
                return False
            return 9 <= et.hour < 16
        except Exception:
            return True  # When in doubt, allow the refresh — safer than freezing the cache.


async def _fetch_constituent_universe() -> List[str]:
    """Load the refresh universe — top-N per sector ETF.

    Phase A.3 change: filter to `rank_in_sector <= TOP_N_PER_SECTOR`. The seed
    data in `api/sectors.py` SECTOR_SEEDS writes ranks 1..20 in market-cap
    order, so rank <= 3 selects the top-3 mega-caps per sector.

    Returns the deduped ticker list ordered by ticker so writes are
    predictable. Out-of-universe tickers are NOT touched by this job.
    """
    pool = await get_postgres_client()
    if not pool:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT ticker FROM sector_constituents "
            "WHERE rank_in_sector IS NOT NULL AND rank_in_sector <= $1 "
            "ORDER BY ticker",
            TOP_N_PER_SECTOR,
        )
    return [r["ticker"] for r in rows]


async def get_tracked_universe() -> Set[str]:
    """Public helper: return the current refresh universe as a set.

    Consumed by `/api/sectors/{etf}/leaders` and `/api/ticker/{symbol}/profile`
    so they can attach a `tracked: bool` flag to each row; the frontend uses
    that to distinguish "not tracked" from "no data" in the cell annotation.
    """
    universe = await _fetch_constituent_universe()
    return {t.upper() for t in universe}


def _regular_session_closes(bars: list) -> List[float]:
    """Extract close prices from UW OHLC bars, regular-session only."""
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
    """Return the current token-bucket headroom ratio (0..1)."""
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
    Also counts UW call attempts (always 1 if either refresh flag is true).
    """
    status = {
        "wk_written": False,
        "mo_written": False,
        "wk_value": None,
        "mo_value": None,
        "attempted": 0,
        "succeeded": 0,
        "quota_blocked": False,
    }
    if not (refresh_wk or refresh_mo):
        return status

    status["attempted"] = 1
    bars = await get_ohlc(ticker, "1d", lookback_days=35, caller="ohlc_sector")
    if is_unavailable(bars):
        # B3: BACKGROUND quota exhausted (governor block). Do NOT overwrite the
        # last-good envelope — neither with fresh data nor with None. Leaving the
        # existing cache entry lets the heatmap render visible staleness
        # ("stale as of HH:MM") from the aging timestamp. No faked-fresh cells.
        status["quota_blocked"] = True
        return status
    if bars is not None:
        status["succeeded"] = 1
    closes = _regular_session_closes(bars or [])
    if len(closes) < 2:
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


async def _refresh_rsi(ticker: str) -> dict:
    """Pull RSI(14) and write the envelope.

    Returns a status dict with attempt/success counts so the caller can
    aggregate audit metrics consistently with _refresh_ohlc_derived.
    """
    status = {"attempted": 1, "succeeded": 0, "written": False, "quota_blocked": False}
    payload = await get_technical_indicator(ticker, "RSI", lookback=14)
    if is_unavailable(payload):
        # B3: quota-blocked — preserve last-good RSI envelope (visible staleness),
        # do not blank the cell with a None write.
        status["quota_blocked"] = True
        return status
    if payload is None:
        await sector_cache.write_field(ticker, "rsi_14", None)
        return status
    status["succeeded"] = 1

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

    ok = await sector_cache.write_field(ticker, "rsi_14", value)
    status["written"] = ok and value is not None
    return status


async def refresh_fast() -> dict:
    """One fast-loop tick: refresh WK% + RSI(14) for the top-3-per-sector universe.

    Phase A.3 changes: market-hours guard, extended audit logging.
    """
    if not _is_market_hours_safe():
        logger.info("[sector_refresh] fast tick skipped — market closed")
        return {"loop": "fast", "skipped": True, "reason": "market_closed"}

    universe = await _fetch_constituent_universe()
    if not universe:
        logger.warning("[sector_refresh] fast tick: empty constituent universe — seed step pending?")
        return {"loop": "fast", "tickers": 0, "attempted": 0, "succeeded": 0, "rate_limited_429s": 0,
                "wk_ok": 0, "rsi_ok": 0, "failures": 0, "skipped_wk": 0, "duration_ms": 0}

    started_mono = time.monotonic()
    started_429s = get_total_429s()
    wk_ok = 0
    rsi_ok = 0
    failures = 0
    skipped_wk = 0
    attempted = 0
    succeeded = 0
    quota_blocked = 0

    logger.info(
        "[sector_refresh] fast tick start — universe=%d top_n_per_sector=%d",
        len(universe), TOP_N_PER_SECTOR,
    )

    for ticker in universe:
        refresh_wk = _check_headroom() >= HEADROOM_GUARD_RATIO
        if not refresh_wk:
            skipped_wk += 1

        try:
            status = await _refresh_ohlc_derived(ticker, refresh_wk=refresh_wk, refresh_mo=False)
            attempted += status["attempted"]
            succeeded += status["succeeded"]
            if status["wk_written"]:
                wk_ok += 1
            if status.get("quota_blocked"):
                quota_blocked += 1

            rsi_status = await _refresh_rsi(ticker)
            attempted += rsi_status["attempted"]
            succeeded += rsi_status["succeeded"]
            if rsi_status["written"]:
                rsi_ok += 1
            if rsi_status.get("quota_blocked"):
                quota_blocked += 1
        except Exception as e:
            failures += 1
            logger.debug("[sector_refresh] fast tick failure for %s: %s", ticker, e)

        # B3 source-shaping: space requests so the tick self-paces (~2 req/s)
        # and never drains the shared bucket, protecting foreground reads.
        await asyncio.sleep(INTER_REQUEST_SLEEP)

    duration_ms = int((time.monotonic() - started_mono) * 1000)
    rate_limited_429s = get_total_429s() - started_429s
    logger.info(
        "[sector_refresh] fast tick complete — universe=%d attempted=%d succeeded=%d "
        "rate_limited_429s=%d quota_blocked=%d wk_ok=%d rsi_ok=%d failures=%d skipped_wk=%d duration_ms=%d",
        len(universe), attempted, succeeded, rate_limited_429s, quota_blocked,
        wk_ok, rsi_ok, failures, skipped_wk, duration_ms,
    )
    return {
        "loop": "fast",
        "tickers": len(universe),
        "attempted": attempted,
        "succeeded": succeeded,
        "rate_limited_429s": rate_limited_429s,
        "quota_blocked": quota_blocked,
        "wk_ok": wk_ok,
        "rsi_ok": rsi_ok,
        "failures": failures,
        "skipped_wk": skipped_wk,
        "duration_ms": duration_ms,
    }


async def refresh_slow() -> dict:
    """One slow-loop tick: refresh MO% for the top-3-per-sector universe.

    Phase A.3 changes: market-hours guard, extended audit logging.
    """
    if not _is_market_hours_safe():
        logger.info("[sector_refresh] slow tick skipped — market closed")
        return {"loop": "slow", "skipped": True, "reason": "market_closed"}

    universe = await _fetch_constituent_universe()
    if not universe:
        logger.warning("[sector_refresh] slow tick: empty constituent universe")
        return {"loop": "slow", "tickers": 0, "attempted": 0, "succeeded": 0, "rate_limited_429s": 0,
                "mo_ok": 0, "failures": 0, "duration_ms": 0}

    started_mono = time.monotonic()
    started_429s = get_total_429s()
    mo_ok = 0
    failures = 0
    attempted = 0
    succeeded = 0

    logger.info(
        "[sector_refresh] slow tick start — universe=%d top_n_per_sector=%d",
        len(universe), TOP_N_PER_SECTOR,
    )

    for ticker in universe:
        try:
            status = await _refresh_ohlc_derived(ticker, refresh_wk=False, refresh_mo=True)
            attempted += status["attempted"]
            succeeded += status["succeeded"]
            if status["mo_written"]:
                mo_ok += 1
        except Exception as e:
            failures += 1
            logger.debug("[sector_refresh] slow tick failure for %s: %s", ticker, e)

    duration_ms = int((time.monotonic() - started_mono) * 1000)
    rate_limited_429s = get_total_429s() - started_429s
    logger.info(
        "[sector_refresh] slow tick complete — universe=%d attempted=%d succeeded=%d "
        "rate_limited_429s=%d mo_ok=%d failures=%d duration_ms=%d",
        len(universe), attempted, succeeded, rate_limited_429s,
        mo_ok, failures, duration_ms,
    )
    return {
        "loop": "slow",
        "tickers": len(universe),
        "attempted": attempted,
        "succeeded": succeeded,
        "rate_limited_429s": rate_limited_429s,
        "mo_ok": mo_ok,
        "failures": failures,
        "duration_ms": duration_ms,
    }


async def refresh_close_snapshot() -> dict:
    """One close-snapshot tick: refresh WK + RSI + MO for the universe.

    Phase A.3 (2026-05-22): scheduled at 16:05 ET on weekdays by
    `sector_refresh_close_snapshot_loop` in `main.py`. Bypasses the
    market-hours guard (16:05 ET is post-regular-session) so the official
    close snapshot lands in the cache as the canonical close-state value.

    All three fields run in one pass — ~33 tickers × 2 calls each = ~66 UW
    calls, well within the rate-limit budget for a one-shot daily run.
    """
    universe = await _fetch_constituent_universe()
    if not universe:
        logger.warning("[sector_refresh] close-snapshot: empty constituent universe")
        return {"loop": "close_snapshot", "tickers": 0, "attempted": 0, "succeeded": 0,
                "rate_limited_429s": 0, "wk_ok": 0, "mo_ok": 0, "rsi_ok": 0,
                "failures": 0, "duration_ms": 0}

    started_mono = time.monotonic()
    started_429s = get_total_429s()
    wk_ok = 0
    mo_ok = 0
    rsi_ok = 0
    failures = 0
    attempted = 0
    succeeded = 0

    logger.info(
        "[sector_refresh] close-snapshot start — universe=%d top_n_per_sector=%d",
        len(universe), TOP_N_PER_SECTOR,
    )

    for ticker in universe:
        try:
            ohlc_status = await _refresh_ohlc_derived(ticker, refresh_wk=True, refresh_mo=True)
            attempted += ohlc_status["attempted"]
            succeeded += ohlc_status["succeeded"]
            if ohlc_status["wk_written"]:
                wk_ok += 1
            if ohlc_status["mo_written"]:
                mo_ok += 1

            rsi_status = await _refresh_rsi(ticker)
            attempted += rsi_status["attempted"]
            succeeded += rsi_status["succeeded"]
            if rsi_status["written"]:
                rsi_ok += 1
        except Exception as e:
            failures += 1
            logger.debug("[sector_refresh] close-snapshot failure for %s: %s", ticker, e)

    duration_ms = int((time.monotonic() - started_mono) * 1000)
    rate_limited_429s = get_total_429s() - started_429s
    logger.info(
        "[sector_refresh] close-snapshot complete — universe=%d attempted=%d succeeded=%d "
        "rate_limited_429s=%d wk_ok=%d mo_ok=%d rsi_ok=%d failures=%d duration_ms=%d",
        len(universe), attempted, succeeded, rate_limited_429s,
        wk_ok, mo_ok, rsi_ok, failures, duration_ms,
    )
    return {
        "loop": "close_snapshot",
        "tickers": len(universe),
        "attempted": attempted,
        "succeeded": succeeded,
        "rate_limited_429s": rate_limited_429s,
        "wk_ok": wk_ok,
        "mo_ok": mo_ok,
        "rsi_ok": rsi_ok,
        "failures": failures,
        "duration_ms": duration_ms,
    }
