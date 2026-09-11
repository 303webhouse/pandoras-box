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

from jobs.poller_pause import check_paused

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
async def _record(job_name: str, coro_fn, session_date=None):
    """Run a job, recording success/failure to the job-status ledger. A thrown exception
    becomes a counter increment (no more silent retry loops) and, once per incident, one
    Hermes flatline alert. Never re-raises — the loop keeps ticking.

    R-IV.360(1): when `session_date` is given the run is ALSO written to `job_runs`,
    the durable per-session ledger the retry reads back. That write is what makes
    "did this session's pass complete?" survive a process restart -- the in-process
    `fired` set could not, and a restart at the wrong moment either lost the session
    or double-fired it."""
    from stable_engine import job_status

    run_id = None
    if session_date is not None:
        try:
            from jobs.job_runs import JOB_NIGHTLY, start_run
            ledger_name = JOB_NIGHTLY if job_name == "nightly" else job_name
            run_id = await start_run(ledger_name, session_date)
        except Exception as exc:
            # A supervision write must never stop the work it supervises.
            logger.warning("[stable_jobs] job_runs start_run(%s) failed: %s", job_name, exc)

    try:
        res = await coro_fn()
        await job_status.mark_success(job_name)
        await _finish_run(run_id, "ok")
        return res
    except Exception as e:
        logger.warning("[stable_jobs] %s failed: %s", job_name, e)
        await _finish_run(run_id, "error", str(e))
        should_alert = await job_status.mark_failure(job_name, f"{type(e).__name__}: {e}")
        if should_alert:
            await _fire_flatline_alert(job_name, e)
        return None


async def _finish_run(run_id, status: str, error: str = None) -> None:
    """Close the job_runs row. Swallows everything: this is the supervision
    channel, and it must not be able to fail the job it is supervising."""
    if run_id is None:
        return
    try:
        from jobs.job_runs import finish_run
        await finish_run(run_id, status, error=(error or "")[:500] or None)
    except Exception as exc:
        logger.warning("[stable_jobs] job_runs finish_run failed: %s", exc)


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
            # R-IV.273(c) spend pause. Checked BEFORE the RTH gate so the paused
            # state is observable off-hours, not only during a session.
            if not check_paused("tide") and is_rth(now_et()):
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


# R-IV.360(1). Retry cadence and cut-off, named rather than inlined.
NIGHTLY_RETRY_EVERY_S = 15 * 60          # a failed pass is re-attempted every 15 min
NIGHTLY_RETRY_UNTIL_HOUR_ET = 23         # ...until 23:59 ET; past that it is tomorrow's
_nightly_attempted_at: dict = {}         # session key -> last attempt (rate limit only)


# S8 (R-IV.361). 15:45 ET is a CHOICE: late enough that the session's IV is
# meaningful, early enough that quotes are still live. A post-close capture would
# record stale, wide, untradeable spreads -- and would look like data.
S8_SNAPSHOT_TIME = (15, 45)
S8_RETRY_UNTIL_HOUR_ET = 17              # quotes are worthless much past this
S8_RETRY_EVERY_S = 10 * 60
_s8_attempted_at: dict = {}


async def _maybe_run_s8(et, key_prefix: str) -> None:
    """Capture the chain if this session has not been captured. Never raises."""
    from jobs.job_runs import has_completed
    from jobs.option_chain_snapshot import JOB_NAME as S8_JOB

    last = _s8_attempted_at.get(key_prefix)
    if last is not None and (et - last).total_seconds() < S8_RETRY_EVERY_S:
        return
    try:
        done = await has_completed(S8_JOB, et.date())
    except Exception as exc:
        logger.warning("[s8] completion check failed: %s", exc)
        done = None
    if done is True:
        return
    _s8_attempted_at[key_prefix] = et
    if last is not None:
        logger.warning("[s8] RETRY for %s (completed=%s)", key_prefix, done)
    await _record(S8_JOB, _run_s8, session_date=et.date())


async def _run_s8():
    from jobs.option_chain_snapshot import run_option_chain_snapshot
    res = await run_option_chain_snapshot()
    # A capture that wrote nothing is a FAILED capture, not a quiet success --
    # otherwise has_completed() marks the session done and the retry stops on a
    # day with no data at all.
    if not res or not res.get("rows"):
        raise RuntimeError("s8 capture wrote no rows: %s" % res)
    return res


async def _maybe_run_nightly(et, key_prefix: str) -> None:
    """Run the nightly if this session's pass has not completed. Never raises.

    THE TRI-STATE IS LOAD-BEARING. `has_completed` returns True / False / None,
    and None means THE QUESTION COULD NOT BE ANSWERED -- which, on the night this
    fix exists for, is exactly what an unreachable Postgres returns.

        True  -> done. Stop.
        False -> not done. Run.
        None  -> UNKNOWN. Run anyway, rate-limited.

    Collapsing None into True would reproduce the defect precisely: a database too
    sick to answer would be read as a session already handled. Collapsing it into
    False is what we do, deliberately, and the rate limit is what makes that safe --
    without it an unreadable database would re-fire the nightly every 45 seconds.
    """
    from jobs.job_runs import JOB_NIGHTLY, has_completed

    last = _nightly_attempted_at.get(key_prefix)
    if last is not None and (et - last).total_seconds() < NIGHTLY_RETRY_EVERY_S:
        return
    try:
        done = await has_completed(JOB_NIGHTLY, et.date())
    except Exception as exc:
        logger.warning("[stable_jobs] nightly completion check failed: %s", exc)
        done = None
    if done is True:
        return
    _nightly_attempted_at[key_prefix] = et
    if last is not None:
        logger.warning("[stable_jobs] nightly RETRY for %s (completed=%s)", key_prefix, done)
    await _record("nightly", run_nightly_close_recompute, session_date=et.date())


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
                # ── S8 option-chain snapshot (R-IV.361) ──────────────────────
                # FORWARD COLLECTION. A session not captured is gone: no vendor
                # call returns yesterday's bid/ask/IV as they stood. So this uses
                # the SAME completion-backed retry as the nightly rather than a
                # one-shot window -- for a collector, "we tried once" is the one
                # outcome that cannot be repaired.
                sh, sm = S8_SNAPSHOT_TIME
                if (et.hour, et.minute) >= (sh, sm) and et.hour <= S8_RETRY_UNTIL_HOUR_ET:
                    await _maybe_run_s8(et, key_prefix)

                # ── Nightly recompute — R-IV.360(1), RETRY ───────────────────
                # THE OLD SHAPE HAD TWO INDEPENDENT WAYS TO LOSE A SESSION:
                #   1. `fired.add(nkey)` ran BEFORE the job, so a FAILED pass was
                #      recorded as fired and never retried;
                #   2. the trigger was a two-minute window (`minute in (nm, nm+1)`),
                #      so after 21:01 the condition could not be true again that day
                #      even with an empty `fired`.
                # On 2026-09-10 Postgres entered recovery mid-run: the pass was lost
                # and `stable_daily_bars` went a day without advancing.
                #
                # NOW: run at or after NIGHTLY_TIME whenever THIS SESSION'S PASS HAS
                # NOT COMPLETED, where "completed" is a DURABLE question answered by
                # job_runs -- not an in-process set that a restart clears.
                nh, nm = NIGHTLY_TIME
                if (et.hour, et.minute) >= (nh, nm) and et.hour <= NIGHTLY_RETRY_UNTIL_HOUR_ET:
                    await _maybe_run_nightly(et, key_prefix)
            # Trim yesterday's keys at midnight ET
            if et.hour == 0 and et.minute < 2:
                fired = {k for k in fired if k.startswith(key_prefix)}
        except Exception as e:
            logger.warning("[stable_jobs] loop error: %s", e)
        await asyncio.sleep(45)
