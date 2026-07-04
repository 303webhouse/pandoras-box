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
from datetime import datetime

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


async def run_index_rates_strip() -> dict:
    res = await asyncio.to_thread(_strip_work)
    return res


async def stable_strip_loop():
    """Refresh the index/rates live strip every 10 min during RTH (market-days)."""
    while True:
        try:
            if is_rth(now_et()):
                await run_index_rates_strip()
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
                    await run_movers()
                elif is_rth(et):
                    await run_movers()
                if et.hour == 0:
                    fired_premarket = {k for k in fired_premarket if k.startswith(et.strftime("%Y-%m-%d"))}
        except Exception as e:
            logger.warning("[stable_jobs] movers loop error: %s", e)
        await asyncio.sleep(600)  # 10 minutes


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
                        await run_provisional_snapshot()
                # Nightly recompute
                nh, nm = NIGHTLY_TIME
                nkey = f"{key_prefix}-nightly"
                if et.hour == nh and et.minute in (nm, nm + 1) and nkey not in fired:
                    fired.add(nkey)
                    await run_nightly_close_recompute()
            # Trim yesterday's keys at midnight ET
            if et.hour == 0 and et.minute < 2:
                fired = {k for k in fired if k.startswith(key_prefix)}
        except Exception as e:
            logger.warning("[stable_jobs] loop error: %s", e)
        await asyncio.sleep(45)
