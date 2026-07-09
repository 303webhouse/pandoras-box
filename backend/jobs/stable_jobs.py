"""Stable Engine scheduled jobs (nightly close recompute + provisional snapshots).

Adapted from Stable Market Board by Ryan Scott (shared within The Stable, 2026).
yfinance-only (zero UW calls). The engine is synchronous/pandas-heavy, so every job
runs the work in a worker thread (asyncio.to_thread) to avoid blocking the event loop.

Schedule (ET, trading days best-effort — weekday gate):
  - Nightly full recompute ~21:00 ET: incremental bar refresh + full metrics +
    theme scores (anchor='close').
  - Provisional snapshots 08:00 / 09:45 / 16:05 ET: live-price theme scores
    (anchor='provisional'); structural metrics stay anchored to last close.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import pytz

logger = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")

# Snapshot targets (hour, minute) ET.
PROVISIONAL_TIMES = [(8, 0), (9, 45), (16, 5)]
NIGHTLY_TIME = (21, 0)


def now_et() -> datetime:
    return datetime.now(ET)


def is_weekday(dt: datetime) -> bool:
    return dt.weekday() < 5


def _all_tickers() -> list[str]:
    from stable_engine import universe, config
    return sorted(set(universe.universe_tickers()) | set(config.BENCHMARK_SYMBOLS))


def _nightly_work() -> dict:
    from stable_engine import bars_yf, metrics, scoring
    tickers = _all_tickers()
    coverage = bars_yf.download_and_store(tickers, days=15)   # incremental refresh
    m = metrics.compute_metrics()
    scores = scoring.compute_theme_scores()
    stored = scoring.store_theme_scores(scores, anchor="close", degraded=coverage["degraded"])
    return {"coverage": coverage["coverage_pct"], "degraded": coverage["degraded"],
            "metrics_rows": m.get("rows_written", 0), "themes_stored": stored}


def _provisional_work() -> dict:
    from stable_engine import live
    tickers = _all_tickers()
    return live.run_provisional_snapshot(tickers)


def _strip_work() -> dict:
    from stable_engine import strip
    return strip.run_strip_update()


def is_rth(dt: datetime) -> bool:
    """Roughly regular trading hours 09:30-16:00 ET on weekdays (holidays best-effort)."""
    if not is_weekday(dt):
        return False
    mins = dt.hour * 60 + dt.minute
    return 9 * 60 + 30 <= mins <= 16 * 60


# ── Flatline detection: record every run on the async pool (never psycopg2) ──────
async def _record(job_name: str, coro_fn):
    """Run a job, recording success/failure to the job-status ledger. A thrown exception
    becomes a counter increment (no more silent retry loops) and, once per incident, one
    Hermes flatline alert. Never re-raises — the loop keeps ticking."""
    from stable_engine import job_status
    try:
        res = await coro_fn()
        await job_status.mark_success(job_name)
        return res
    except Exception as e:
        logger.warning("[stable_jobs] %s failed: %s", job_name, e)
        should_alert = await job_status.mark_failure(job_name, f"{type(e).__name__}: {e}")
        if should_alert:
            await _fire_flatline_alert(job_name, e)
        return None


async def _fire_flatline_alert(job_name: str, err: Exception) -> None:
    """One Hermes catalyst alert per flatline incident (dedup guaranteed by the ledger's
    alerted flag, not by poll cadence)."""
    try:
        from webhooks.hermes import _store_catalyst_event
        await _store_catalyst_event(
            event_type="stable_flatline", tier=1, trigger_ticker="STABLE",
            sector_velocity={
                "headline": f"Stable Engine '{job_name}' job flatlined — no successful run "
                            f"({type(err).__name__}). Data pipe is DEAD, not just stale.",
                "source": "stable_watchdog", "scenario": "flatline", "direction": "down",
            },
        )
        logger.error("[stable_jobs] FLATLINE alert fired for job=%s", job_name)
    except Exception as e:
        logger.warning("[stable_jobs] could not fire flatline alert for %s: %s", job_name, e)


async def run_index_rates_strip() -> dict:
    res = await asyncio.to_thread(_strip_work)
    return res


async def stable_strip_loop():
    """Refresh the index/rates live strip every 10 min during RTH (market-days)."""
    while True:
        try:
            if is_rth(now_et()):
                await _record("strip", run_index_rates_strip)
        except Exception as e:
            logger.warning("[stable_jobs] strip loop error: %s", e)
        await asyncio.sleep(600)  # 10 minutes


def _movers_work() -> dict:
    from stable_engine import movers
    return movers.run_movers_update()


async def run_movers() -> dict:
    return await asyncio.to_thread(_movers_work)


async def stable_movers_loop():
    """Movers screener every 10 min during RTH + one best-effort premarket pull ~08:00 ET."""
    fired_premarket: set[str] = set()
    while True:
        try:
            et = now_et()
            if is_weekday(et):
                pkey = et.strftime("%Y-%m-%d") + "-premarket"
                if et.hour == 8 and et.minute < 10 and pkey not in fired_premarket:
                    fired_premarket.add(pkey)
                    await _record("movers", run_movers)
                elif is_rth(et):
                    await _record("movers", run_movers)
                if et.hour == 0:
                    fired_premarket = {k for k in fired_premarket if k.startswith(et.strftime("%Y-%m-%d"))}
        except Exception as e:
            logger.warning("[stable_jobs] movers loop error: %s", e)
        await asyncio.sleep(600)  # 10 minutes


async def _warm_tide() -> None:
    """Pull the UW market-tide and stash the latest entry in a longer-lived redis key so the
    v2 tide cell stays lit past the 60s UW cache TTL. Reuses the existing get_market_tide
    caller (Nick-approved 2026-07-09) — one UW call per warm."""
    import json
    from integrations.uw_api import get_market_tide
    from database.redis_client import get_redis_client
    raw = await get_market_tide()
    if not raw:
        return
    td = raw.get("data", raw) if isinstance(raw, dict) else raw
    if isinstance(td, list) and td:
        td = td[-1]
    if not isinstance(td, dict):
        return
    client = await get_redis_client()
    if not client:
        return
    payload = {
        "net_call_premium": td.get("net_call_premium"),
        "net_put_premium": td.get("net_put_premium"),
        "net_volume": td.get("net_volume"),
        "warmed_at": datetime.now(timezone.utc).isoformat(),
    }
    await client.setex("board:tide:latest", 1800, json.dumps(payload))


async def stable_tide_warmer_loop():
    """Keep the v2 tide cell lit during RTH by warming the market-tide every 5 min (RTH only,
    ~1 UW call each). Matches the legacy /app market-intel cadence; board /tide prefers the
    warmed key so the cell no longer goes dark between the 60s UW cache windows."""
    await asyncio.sleep(120)  # let the DB/redis pools settle after boot
    while True:
        try:
            if is_rth(now_et()):
                await _warm_tide()
        except Exception as e:
            logger.warning("[stable_jobs] tide warmer error: %s", e)
        await asyncio.sleep(300)  # 5 minutes


async def run_nightly_close_recompute() -> dict:
    logger.info("[stable_jobs] nightly close recompute starting")
    res = await asyncio.to_thread(_nightly_work)
    logger.info("[stable_jobs] nightly close recompute done: %s", res)
    return res


async def run_provisional_snapshot() -> dict:
    logger.info("[stable_jobs] provisional snapshot starting")
    res = await asyncio.to_thread(_provisional_work)
    logger.info("[stable_jobs] provisional snapshot done: %s", res)
    return res


async def stable_engine_loop():
    """One-minute ticker that fires the nightly recompute + provisional snapshots at
    their ET times (weekdays), each at most once per calendar day."""
    fired: set[str] = set()
    while True:
        try:
            et = now_et()
            key_prefix = et.strftime("%Y-%m-%d")
            if is_weekday(et):
                # Provisional snapshots
                for (h, m) in PROVISIONAL_TIMES:
                    key = f"{key_prefix}-prov-{h:02d}{m:02d}"
                    if et.hour == h and et.minute in (m, m + 1) and key not in fired:
                        fired.add(key)
                        await _record("provisional", run_provisional_snapshot)
                # Nightly recompute
                nh, nm = NIGHTLY_TIME
                nkey = f"{key_prefix}-nightly"
                if et.hour == nh and et.minute in (nm, nm + 1) and nkey not in fired:
                    fired.add(nkey)
                    await _record("nightly", run_nightly_close_recompute)
            # Trim yesterday's keys at midnight ET
            if et.hour == 0 and et.minute < 2:
                fired = {k for k in fired if k.startswith(key_prefix)}
        except Exception as e:
            logger.warning("[stable_jobs] loop error: %s", e)
        await asyncio.sleep(45)
