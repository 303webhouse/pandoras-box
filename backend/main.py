"""
Pandora's Box - Main FastAPI Application
High-performance trading signal processor with sub-100ms latency
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from contextlib import asynccontextmanager
import asyncio
from typing import Set
import logging
import os
import sys

# Import our modules (will create these next)
from database.redis_client import get_redis_client
from database.postgres_client import get_postgres_client
from websocket.broadcaster import manager

# Configure logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

# WebSocket connection manager (imported from broadcaster.py for shared instance)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    logger.info("🚀 Pandora's Box backend starting...")
    
    # Initialize database connections
    redis_client = await get_redis_client()
    postgres_client = await get_postgres_client()
    
    # Initialize/update database schema (adds new columns if they don't exist)
    try:
        from database.postgres_client import init_database
        await init_database()
    except Exception as e:
        logger.warning(f"⚠️ Could not initialize database schema: {e}")

    # Initialize watchlist config table
    try:
        from api.watchlist import init_watchlist_table
        await init_watchlist_table()
        logger.info("✅ Watchlist table ready")
    except Exception as e:
        logger.warning(f"⚠️ Could not initialize watchlist table: {e}")

    # Initialize trade watchlist table
    try:
        from api.trade_watchlist import init_trade_watchlist_table
        await init_trade_watchlist_table()
        logger.info("✅ Trade watchlist table ready")
    except Exception as e:
        logger.warning(f"⚠️ Could not initialize trade watchlist table: {e}")

    # Initialize earnings calendar table
    try:
        from api.chronos import init_chronos_table
        await init_chronos_table()
        logger.info("✅ Chronos earnings table ready")
    except Exception as e:
        logger.warning(f"⚠️ Could not initialize Chronos table: {e}")

    # Add confirmations column to lightning_cards if missing
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute("ALTER TABLE lightning_cards ADD COLUMN IF NOT EXISTS confirmations JSONB DEFAULT '[]'")
        logger.info("✅ Lightning cards confirmations column ready")
    except Exception as e:
        logger.debug("Lightning cards column check: %s", e)

    logger.info("✅ Database connections established")
    # One-time cleanup of cached anomalous prices before schedulers consume data.
    try:
        from bias_engine.factor_utils import purge_suspicious_cache_entries

        purge_result = await purge_suspicious_cache_entries()
        logger.info(
            "Price cache purge complete (scanned=%s purged=%s)",
            purge_result.get("scanned", 0),
            purge_result.get("purged", 0),
        )
    except Exception as e:
        logger.warning(f"Could not purge suspicious cache entries: {e}")

    # Restore circuit-breaker state so protective caps/floors survive restarts.
    try:
        from webhooks.circuit_breaker import restore_circuit_breaker_state

        restored = await restore_circuit_breaker_state()
        if restored:
            logger.info("Circuit breaker state restored from Redis")
    except Exception as e:
        logger.warning(f"Could not restore circuit breaker state: {e}")
    
    # Start the bias scheduler
    try:
        from scheduler.bias_scheduler import start_scheduler
        await start_scheduler()
        logger.info("✅ Bias scheduler started")
    except Exception as e:
        logger.warning(f"⚠️ Could not start scheduler: {e}")
    
    # Start signal expiry background task
    async def signal_expiry_loop():
        """Expire stale signals every 5 minutes."""
        while True:
            try:
                from api.trade_ideas import expire_stale_signals
                await expire_stale_signals()
            except Exception as e:
                logger.warning(f"Signal expiry loop error: {e}")
            try:
                from database.postgres_client import expire_pending_trades
                expired = await expire_pending_trades()
                if expired > 0:
                    logger.info(f"🕐 Expired {expired} stale pending trades")
            except Exception as e:
                logger.warning(f"Pending trade expiry error: {e}")
            await asyncio.sleep(300)  # 5 minutes

    # Universe enrichment cache refresh (every 30 min during market hours)
    async def universe_cache_loop():
        """Refresh universe enrichment cache during market hours."""
        import pytz
        from datetime import datetime as dt_cls

        while True:
            try:
                et = dt_cls.now(pytz.timezone("America/New_York"))
                # Only refresh during extended market hours (8 AM - 5 PM ET, weekdays)
                if et.weekday() < 5 and 8 <= et.hour < 17:
                    from enrichment.universe_cache import refresh_universe
                    await refresh_universe()
                else:
                    logger.debug("Universe cache: outside market hours, skipping")
            except Exception as e:
                logger.warning(f"Universe cache loop error: {e}")
            await asyncio.sleep(1800)  # 30 minutes

    # Mark-to-market: refresh position prices at :02, :17, :32, :47 past each hour
    # during market hours (offset 2 min from quarter-hour boundaries to allow data settle)
    async def mark_to_market_loop():
        """Fetch live UW API prices for open positions during market hours.
        Clock-aware: fires at :02, :17, :32, :47 past each hour (9 AM - 5 PM ET weekdays).
        Forces a closing bell run at 4:17 PM ET to capture near-close prices.
        """
        import pytz
        from datetime import datetime as dt_cls

        MTM_MINUTES = [2, 17, 32, 47]  # 2 min offset from :00/:15/:30/:45 quarter-hours
        closing_bell_fired_today = None  # Track date to fire once per day

        while True:
            try:
                et = dt_cls.now(pytz.timezone("America/New_York"))
                today_date = et.date()
                is_weekday = et.weekday() < 5
                in_market_window = is_weekday and 9 <= et.hour < 17

                # Closing bell run: 4:17 PM ET, once per day
                is_closing_bell = (
                    is_weekday
                    and et.hour == 16 and et.minute >= 17 and et.minute < 30
                    and closing_bell_fired_today != today_date
                )

                should_run = False
                if in_market_window or is_closing_bell:
                    # Check if we're at one of the target minutes
                    if et.minute in MTM_MINUTES or is_closing_bell:
                        should_run = True

                if should_run:
                    from api.unified_positions import run_mark_to_market
                    result = await run_mark_to_market()
                    updated = result.get("updated", 0)
                    errors = result.get("errors", [])
                    if is_closing_bell:
                        closing_bell_fired_today = today_date
                        logger.info("🔔 Closing bell MTM: updated %d positions", updated)
                    elif updated > 0:
                        logger.info("📊 Mark-to-market: updated %d positions (%02d:%02d ET)", updated, et.hour, et.minute)
                    # Snapshot balances after MTM for PnL tracking
                    try:
                        from api.portfolio import snapshot_account_balances
                        await snapshot_account_balances()
                    except Exception as snap_err:
                        logger.warning("Balance snapshot after MTM failed: %s", snap_err)
                    if errors:
                        logger.warning("📊 Mark-to-market: %d errors", len(errors))

                # Sleep until next target minute
                # Calculate seconds until next :02/:17/:32/:47
                now_min = et.minute
                now_sec = et.second
                next_targets = [m for m in MTM_MINUTES if m > now_min]
                if next_targets:
                    next_min = next_targets[0]
                else:
                    next_min = MTM_MINUTES[0] + 60  # wrap to next hour
                sleep_secs = (next_min - now_min) * 60 - now_sec
                if sleep_secs <= 0:
                    sleep_secs = 60  # safety floor
                sleep_secs = min(sleep_secs, 900)  # cap at 15 min
            except Exception as e:
                logger.warning("Mark-to-market loop error: %s", e)
                sleep_secs = 60  # retry in 1 min on error
            await asyncio.sleep(sleep_secs)

    # Confluence engine: group signals by ticker+direction every 15 min
    async def confluence_engine_loop():
        """Run confluence scan during market hours."""
        import pytz
        from datetime import datetime as dt_cls

        # Initial delay to let other systems start first
        await asyncio.sleep(60)

        while True:
            try:
                et = dt_cls.now(pytz.timezone("America/New_York"))
                # Market hours: 9:30 AM - 4:30 PM ET, weekdays
                if et.weekday() < 5 and 9 <= et.hour < 17:
                    from confluence.engine import run_confluence_scan
                    await run_confluence_scan()
                else:
                    logger.debug("Confluence engine: outside market hours, skipping")
            except Exception as e:
                logger.warning("Confluence engine error: %s", e)
            await asyncio.sleep(900)  # 15 minutes

    # Holy Grail scanner: scan for ADX+EMA pullback setups every 15 min
    async def holy_grail_scan_loop():
        """Run Holy Grail scanner during market hours."""
        import pytz
        from datetime import datetime as dt_cls

        # Offset from other scanners to spread load
        await asyncio.sleep(180)  # 3 min after startup

        while True:
            try:
                et = dt_cls.now(pytz.timezone("America/New_York"))
                # Market hours: 9:30 AM - 4:00 PM ET, weekdays
                if et.weekday() < 5 and 9 <= et.hour < 16:
                    from scanners.holy_grail_scanner import run_holy_grail_scan, HG_SCANNER_AVAILABLE
                    if HG_SCANNER_AVAILABLE:
                        await run_holy_grail_scan()
                else:
                    logger.debug("Holy Grail scanner: outside market hours, skipping")
            except Exception as e:
                logger.warning("Holy Grail scan loop error: %s", e)
            await asyncio.sleep(900)  # 15 minutes

    # Scout Sniper scanner: RSI hooks + reversal candles every 15 min
    async def scout_scan_loop():
        """Run Scout Sniper scanner during market hours."""
        import pytz
        from datetime import datetime as dt_cls

        # Offset from Holy Grail to spread load
        await asyncio.sleep(360)  # 6 min after startup

        while True:
            try:
                et = dt_cls.now(pytz.timezone("America/New_York"))
                # Market hours: 9:30 AM - 4:00 PM ET, weekdays
                if et.weekday() < 5 and 9 <= et.hour < 16:
                    from scanners.scout_sniper_scanner import run_scout_scan, SCOUT_SCANNER_AVAILABLE
                    if SCOUT_SCANNER_AVAILABLE:
                        await run_scout_scan()
                else:
                    logger.debug("Scout scanner: outside market hours, skipping")
            except Exception as e:
                logger.warning("Scout scan loop error: %s", e)
            await asyncio.sleep(900)  # 15 minutes

    # Sector RS: compute daily pre-market, then check every hour
    async def sector_rs_loop():
        """Compute sector relative strength daily at 8:00 AM ET, recheck hourly."""
        import pytz
        from datetime import datetime as dt_cls

        await asyncio.sleep(30)  # Brief startup delay

        while True:
            try:
                et = dt_cls.now(pytz.timezone("America/New_York"))
                # Run at 8:00 AM ET on weekdays, or if data is stale
                if et.weekday() < 5 and (
                    (7 <= et.hour <= 8) or et.hour == 0  # Pre-market window or midnight catch-up
                ):
                    from scanners.sector_rs import compute_sector_rs, is_sector_rs_stale
                    if await is_sector_rs_stale():
                        await compute_sector_rs()
            except Exception as e:
                logger.warning("Sector RS loop error: %s", e)
            await asyncio.sleep(3600)  # Check hourly

    # Sell the Rip scanner: fade relief rallies every 5 min during market hours
    async def sell_the_rip_scan_loop():
        """Run Sell the Rip scanner during market hours."""
        import pytz
        from datetime import datetime as dt_cls

        # Offset from other scanners
        await asyncio.sleep(480)  # 8 min after startup

        while True:
            try:
                et = dt_cls.now(pytz.timezone("America/New_York"))
                # Market hours: 9:35 AM - 3:55 PM ET, weekdays
                if et.weekday() < 5 and 9 <= et.hour < 16:
                    time_decimal = et.hour + et.minute / 60.0
                    if time_decimal >= 9.583:  # 9:35 AM
                        from scanners.sell_the_rip_scanner import run_sell_the_rip_scan, STR_SCANNER_AVAILABLE
                        if STR_SCANNER_AVAILABLE:
                            await run_sell_the_rip_scan()
                else:
                    logger.debug("Sell the Rip scanner: outside market hours, skipping")
            except Exception as e:
                logger.warning("Sell the Rip scan loop error: %s", e)
            await asyncio.sleep(14400)  # 4 hours (daily bars don't change intraday)

    # VWAP validation: compute server-side VWAP every 15 min (4-min offset) during market hours
    async def vwap_validation_loop():
        """Compute VWAP bands and log for TradingView comparison."""
        import pytz
        from datetime import datetime as dt_cls

        # 4-minute offset from other 15-min loops
        await asyncio.sleep(240)

        while True:
            try:
                et = dt_cls.now(pytz.timezone("America/New_York"))
                # Market hours: 9:30 AM - 4:15 PM ET, weekdays
                if et.weekday() < 5 and 9 <= et.hour < 17:
                    time_decimal = et.hour + et.minute / 60.0
                    if time_decimal >= 9.5:  # After 9:30 AM
                        from scanners.vwap_validator import run_vwap_validation, VALIDATOR_AVAILABLE
                        if VALIDATOR_AVAILABLE:
                            await run_vwap_validation()
                else:
                    logger.debug("VWAP validation: outside market hours, skipping")
            except Exception as e:
                logger.warning("VWAP validation loop error: %s", e)
            await asyncio.sleep(900)  # 15 minutes

    # Factor staleness monitor — check every 60 min
    async def factor_staleness_loop():
        """Check factor freshness and alert on stale readings."""
        await asyncio.sleep(120)  # 2 min after startup
        while True:
            try:
                from monitoring.factor_staleness import run_staleness_check
                result = await run_staleness_check(alert=True)
                stale_count = len(result.get("stale_factors", []))
                missing_count = len(result.get("missing_factors", []))
                if stale_count or missing_count:
                    logger.warning(
                        "Factor staleness: %d stale, %d missing", stale_count, missing_count
                    )
            except Exception as e:
                logger.warning("Factor staleness loop error: %s", e)
            await asyncio.sleep(3600)  # 60 minutes

    # Crypto setup engine: scan for BTC funding/session/liquidation setups
    async def crypto_scan_loop():
        """Run crypto setup engine every 5 minutes (24/7 — crypto never sleeps)."""
        await asyncio.sleep(90)  # 1.5 min after startup

        while True:
            try:
                from strategies.crypto_setups import run_crypto_scan
                signals = await run_crypto_scan()
                if signals:
                    logger.info("₿ Crypto scan: %d signal(s) generated", len(signals))
            except Exception as e:
                logger.warning("Crypto scan loop error: %s", e)
            await asyncio.sleep(300)  # 5 minutes

    # UW flow poller: populate flow_events every 5 min during market hours (ZEUS 1A.0)
    async def uw_flow_poller_loop():
        """Poll UW per-ticker flow and write to flow_events every 5 min."""
        import pytz
        from datetime import datetime as dt_cls

        await asyncio.sleep(120)  # 2 min after startup (let DB connections settle)

        while True:
            try:
                et = dt_cls.now(pytz.timezone("America/New_York"))
                if et.weekday() < 5 and 9 <= et.hour < 16:
                    from jobs.uw_flow_poller import run_flow_poller
                    await run_flow_poller()
                else:
                    logger.debug("UW flow poller: outside market hours, skipping")
            except Exception as e:
                logger.warning("UW flow poller loop error: %s", e)
            await asyncio.sleep(300)  # 5 minutes

    async def flow_deadfeed_watchdog_loop():
        """L1.0 Chunk 3: RTH-gated, debounced dead-feed alarm for the uw:flow:* feed.

        Independent of run_flow_poller on purpose — a stopped poller must still trip
        this (dead-man's-switch). Evaluates uw:flow:* freshness directly each cycle;
        fires ONCE per episode (Redis latch) and sends a recovery alert on heal.
        """
        import json as _json
        from datetime import datetime as _dt, time as _t, timezone as _tz
        from zoneinfo import ZoneInfo

        STALE_S = 900            # matches the uw:flow TTL that governs flow_data_available
        LATCH_KEY = "alarm:flow_dead:active"
        LATCH_TTL = 7200         # ~2h — one alarm per dead episode, not per cycle

        def _in_rth() -> bool:
            # Strict 09:30–16:00 ET (NOT api/sectors._is_market_hours, which runs to
            # ~16:30 and would false-alarm daily after the poller stops at 16:00).
            # No half-day calendar: early-close days (~3-4/yr) may throw one false
            # "feed dead" in the after-close window. Known, acceptable.
            now = _dt.now(ZoneInfo("America/New_York"))
            if now.weekday() >= 5:
                return False
            return _t(9, 30) <= now.time() <= _t(16, 0)

        await asyncio.sleep(180)  # let the poller seed uw:flow:* first

        while True:
            try:
                if _in_rth():
                    redis = await get_redis_client()
                    if redis:
                        cursor = b"0"
                        keys = []
                        while True:
                            cursor, batch = await redis.scan(cursor, match="uw:flow:*", count=200)
                            keys.extend(batch)
                            if cursor in (b"0", 0):
                                break
                        now_utc = _dt.now(_tz.utc)
                        summaries = 0
                        fresh = 0
                        oldest_age = None
                        newest_iso = None
                        for k in keys:
                            ks = k.decode() if isinstance(k, bytes) else k
                            if ks.endswith(":recent"):
                                continue  # the recent-alerts list, not a summary
                            val = await redis.get(k)
                            if not val:
                                continue
                            try:
                                summ = _json.loads(val)
                            except Exception:
                                continue
                            if not isinstance(summ, dict):
                                continue
                            dua = summ.get("updated_at")
                            if not dua:
                                continue
                            try:
                                age = (now_utc - _dt.fromisoformat(dua)).total_seconds()
                            except Exception:
                                continue
                            summaries += 1
                            if age <= STALE_S:
                                fresh += 1
                            if oldest_age is None or age > oldest_age:
                                oldest_age = int(age)
                            if newest_iso is None or dua > newest_iso:
                                newest_iso = dua

                        feed_dead = (fresh == 0)
                        latched = bool(await redis.get(LATCH_KEY))
                        if feed_dead and not latched:
                            from bias_engine.anomaly_alerts import send_alert
                            status = (f"No fresh uw:flow within {STALE_S}s during RTH. "
                                      f"summaries={summaries} fresh=0 "
                                      f"oldest_age={oldest_age}s last_write={newest_iso}")
                            await send_alert("🚨 Flow feed dead", status, severity="warning")
                            await redis.set(LATCH_KEY, "1", ex=LATCH_TTL)
                            logger.warning("Flow dead-feed alarm FIRED: %s", status)
                        elif (not feed_dead) and latched:
                            from bias_engine.anomaly_alerts import send_alert
                            status = (f"Flow feed healthy: {fresh} fresh tickers, "
                                      f"oldest_age={oldest_age}s last_write={newest_iso}")
                            await send_alert("✅ Flow feed restored", status, severity="info")
                            await redis.delete(LATCH_KEY)
                            logger.info("Flow dead-feed alarm CLEARED: %s", status)
            except Exception as e:
                logger.warning("Flow dead-feed watchdog error: %s", e)
            await asyncio.sleep(300)  # 5-min cadence

    async def pythia_staleness_watchdog_loop():
        """Per-name PYTHIA MP-feed staleness alarm -- durable fix, full liquid-20 roster.

        docs/codex-briefs/2026-06-29-pythia-mp-feed-reliability-titans-brief.md
        Part 1, BUILT 2026-07-17 (10-min ATLAS freshness re-check passed --
        config.liquid_universe.LIQUID_UNIVERSE unchanged, still the 20-ticker
        doc-exhaustive/provisional-ratified set). Part 2 (feed-shed root-cause)
        was already answered by Fable's 2026-07-15 TV log export (one ~240-symbol
        watchlist alert, ~39 calc slots, survivor set reshuffles on watchlist
        edits) -- confirms the brief's own leading hypothesis almost exactly
        (~40-64 guessed, ~39 found). No separate Part 2 build needed.

        The existing `_maybe_mp_feed_down_alarm` (config/l1_gate.py) checks GLOBAL
        MAX(timestamp) across ALL of pythia_events -- any surviving liquid ticker
        keeps that timestamp fresh and masks individual dead names. This is the
        third time that exact blind spot caused an undetected outage (B4 6/10:
        decay to 3 tickers; 6/29 review: decay to 23, SPY dark 12 days; 7/1-7/16:
        SPY+QQQ dark 14 days). Live proof the blind spot is still active right
        now (2026-07-17, checked before shipping this): 14 of the 20 liquid-20
        tickers are stale by 7-95+ days (HYG since April) while SPY/QQQ/SMH/
        TSLA/IWM/NVDA stay fresh and keep the global alarm quiet throughout.

        Started as a same-evening STOPGAP (2026-07-16, SPY/QQQ only, Fable GO) --
        promoted in-place to the full liquid-20 roster rather than standing up a
        second parallel watchdog; same task/latch infrastructure, just the
        roster and framing changed. The "stopgap retires" by becoming this.

        Per-ticker Redis latch (mirrors flow_deadfeed_watchdog_loop exactly) --
        each roster ticker alarms/recovers independently, not conflated.

        Threshold is SESSION-aware, not a raw hour count: "no event for more than
        1 full session" means the last event predates the previous COMPLETE
        trading session, not "no event in the last 24-26h" -- a raw-hours
        threshold would false-alarm every Monday morning across the weekend gap
        (exactly the class of bug already found and fixed once this week for a
        different feed's staleness math). Reuses the session-date helpers already
        built and vetted for pythia_events in services/read_only/market_profile.py
        rather than reimplementing weekday-session arithmetic a second time.

        AEGIS (brief guardrail): alarm bodies carry ticker + timestamp + session-
        gap count only -- no secrets/DSN/payloads.
        """
        from datetime import datetime as _dt, timezone as _tz
        from zoneinfo import ZoneInfo
        from config.liquid_universe import LIQUID_UNIVERSE

        ROSTER = sorted(LIQUID_UNIVERSE)  # full liquid-20, per the 6/29 brief's Part 1
        LATCH_TTL = 7200  # ~2h -- one alarm per dead episode, not per cycle

        def _in_rth() -> bool:
            from datetime import time as _t
            now = _dt.now(ZoneInfo("America/New_York"))
            if now.weekday() >= 5:
                return False
            return _t(9, 30) <= now.time() <= _t(16, 0)

        await asyncio.sleep(210)  # after the flow watchdog's 180s settle

        while True:
            try:
                if _in_rth():
                    from services.read_only.market_profile import _current_session_date, _prev_weekday

                    redis = await get_redis_client()
                    pool = await get_postgres_client()
                    if redis and pool:
                        now_et = _dt.now(ZoneInfo("America/New_York"))
                        current_session = _current_session_date(now_et)

                        for ticker in ROSTER:
                            async with pool.acquire() as conn:
                                ts = await conn.fetchval(
                                    "SELECT MAX(timestamp) FROM pythia_events WHERE ticker = $1", ticker
                                )

                            latch_key = f"alarm:pythia_stale:{ticker}"
                            latched = bool(await redis.get(latch_key))

                            if ts is None:
                                gap = None  # never fired at all -- treat as stale
                                stale = True
                            else:
                                if ts.tzinfo is None:
                                    ts = ts.replace(tzinfo=_tz.utc)
                                event_session = ts.astimezone(ZoneInfo("America/New_York")).date()
                                gap = 0
                                d = current_session
                                while d > event_session:
                                    d = _prev_weekday(d)
                                    gap += 1
                                stale = gap > 1  # missed MORE than 1 full session

                            if stale and not latched:
                                from bias_engine.anomaly_alerts import send_alert
                                age_desc = "no pythia_events row ever" if ts is None else f"last event {ts.isoformat()} ({gap} sessions ago)"
                                status = f"{ticker}: {age_desc}. Per-name liquid-20 roster alarm (6/29 brief Part 1)."
                                await send_alert(f"🚨 PYTHIA feed dead: {ticker}", status, severity="warning")
                                await redis.set(latch_key, "1", ex=LATCH_TTL)
                                logger.warning("PYTHIA staleness alarm FIRED for %s: %s", ticker, status)
                            elif (not stale) and latched:
                                from bias_engine.anomaly_alerts import send_alert
                                status = f"{ticker}: fresh again, last event {ts.isoformat() if ts else 'unknown'} ({gap} sessions ago)."
                                await send_alert(f"✅ PYTHIA feed restored: {ticker}", status, severity="info")
                                await redis.delete(latch_key)
                                logger.info("PYTHIA staleness alarm CLEARED for %s: %s", ticker, status)
            except Exception as e:
                logger.warning("PYTHIA staleness watchdog error: %s", e)
            await asyncio.sleep(1800)  # 30-min cadence -- session-day-granularity condition, no need for tighter polling

    # WH-ACCUMULATION scanner: detect institutional accumulation hourly (ZEUS 1A.3)
    async def wh_accumulation_loop():
        """Run WH-ACCUMULATION scanner every hour during market hours."""
        import pytz
        from datetime import datetime as dt_cls

        await asyncio.sleep(600)  # 10 min after startup (let flow_events seed first)

        while True:
            try:
                et = dt_cls.now(pytz.timezone("America/New_York"))
                if et.weekday() < 5 and 9 <= et.hour < 16:
                    from scanners.wh_accumulation import run_wh_accumulation_scan
                    await run_wh_accumulation_scan()
                else:
                    logger.debug("WH-ACCUMULATION scanner: outside market hours, skipping")
            except Exception as e:
                logger.warning("WH-ACCUMULATION loop error: %s", e)
            await asyncio.sleep(3600)  # 1 hour

    # WH-REVERSAL scanner: detect pullbacks to VAL after accumulation (ZEUS 1B.1)
    async def wh_reversal_loop():
        """Run WH-REVERSAL scanner every 15 min during market hours."""
        import pytz
        from datetime import datetime as dt_cls

        await asyncio.sleep(750)  # 12.5 min after startup (after wh_accumulation first run)

        while True:
            try:
                et = dt_cls.now(pytz.timezone("America/New_York"))
                if et.weekday() < 5 and 9 <= et.hour < 16:
                    from scanners.wh_reversal import run_wh_reversal_scan
                    await run_wh_reversal_scan()
                else:
                    logger.debug("WH-REVERSAL scanner: outside market hours, skipping")
            except Exception as e:
                logger.warning("WH-REVERSAL loop error: %s", e)
            await asyncio.sleep(900)  # 15 minutes

    # Sector constituent refresh (Phase A — 2026-05-22)
    # Populates sector:constituent:{ticker}:{field} envelope cache that the
    # sector heatmap popup + ticker profile popup read for WK%, MO%, RSI(14).
    async def sector_refresh_fast_loop():
        """Refresh WK% + RSI for every sector constituent.

        60s cadence during market hours; 300s off-hours (the underlying values
        only move during the regular session). The UW token-bucket limiter
        inside `uw_api._consume_token` paces calls; if a tick takes longer
        than the cadence the next tick fires back-to-back.
        """
        import pytz
        from datetime import datetime as dt_cls

        await asyncio.sleep(150)  # 2.5 min after startup — DB pool + sector seed must be live

        while True:
            tick_started = asyncio.get_event_loop().time()
            try:
                from jobs.sector_constituent_refresh import refresh_fast
                await refresh_fast()
            except Exception as e:
                logger.warning("[sector_refresh] fast loop error: %s", e)

            et = dt_cls.now(pytz.timezone("America/New_York"))
            in_market = et.weekday() < 5 and 9 <= et.hour < 16
            base_interval = 180 if in_market else 300  # was 60 - UW 429 incident 2026-06-16
            # UW 429 incident 2026-06-16: sleep a FULL interval AFTER the tick completes.
            # Never let a 429-throttled slow tick collapse to the old 5s floor and fire
            # the next ~66-call burst back-to-back (the self-amplification that blew the cap).
            await asyncio.sleep(base_interval)

    async def sector_refresh_slow_loop():
        """Refresh MO% for sector constituents.

        3600s (1 h) cadence; the refresh function itself no-ops during
        market-closed hours via Phase A.3's market-hours guard.
        """
        await asyncio.sleep(300)  # 5 min after startup — let fast loop's first pass land

        while True:
            tick_started = asyncio.get_event_loop().time()
            try:
                from jobs.sector_constituent_refresh import refresh_slow
                await refresh_slow()
            except Exception as e:
                logger.warning("[sector_refresh] slow loop error: %s", e)
            elapsed = asyncio.get_event_loop().time() - tick_started
            await asyncio.sleep(max(5, 3600 - elapsed))

    # Phase A.3 (2026-05-22): single weekday run at 16:05 ET captures the
    # official 4 PM close into the cache. The refresh_fast / refresh_slow
    # loops above no-op during market-closed hours, so this is the only
    # path that populates the cache once the regular session ends.
    async def sector_refresh_close_snapshot_loop():
        """Fire refresh_close_snapshot() once per weekday at 16:05 ET."""
        import pytz
        from datetime import datetime as dt_cls, timedelta as td_cls

        await asyncio.sleep(60)  # startup delay — let other init settle

        ny_tz = pytz.timezone("America/New_York")
        while True:
            try:
                now_et = dt_cls.now(ny_tz)
                target = now_et.replace(hour=16, minute=5, second=0, microsecond=0)
                if now_et >= target:
                    target = target + td_cls(days=1)
                while target.weekday() >= 5:
                    target = target + td_cls(days=1)
                wait_s = max(5.0, (target - now_et).total_seconds())
                logger.info(
                    "[sector_refresh] close-snapshot scheduled in %.0fs (target %s ET)",
                    wait_s, target.strftime("%Y-%m-%d %H:%M %Z"),
                )
                await asyncio.sleep(wait_s)
                from jobs.sector_constituent_refresh import refresh_close_snapshot
                await refresh_close_snapshot()
            except Exception as e:
                logger.warning("[sector_refresh] close-snapshot loop error: %s", e)
                # Sleep a defensive minute before retrying scheduling math
                await asyncio.sleep(60)

    async def adx_regime_loop():
        """sub-brief 3 Chunk 3: SPY ADX(14) → regime:spy_adx_shadow (RTH, 15-min)."""
        import pytz
        from datetime import datetime as dt_cls

        await asyncio.sleep(150)  # startup offset
        while True:
            try:
                et = dt_cls.now(pytz.timezone("America/New_York"))
                # RTH only (9:30 AM – 4:00 PM ET, weekdays); 90-min TTL lets the
                # shadow key expire overnight → 'unknown' by design.
                if et.weekday() < 5 and 9 <= et.hour < 16:
                    if et.hour + et.minute / 60.0 >= 9.5:
                        from jobs.adx_regime_job import compute_and_store_spy_adx
                        await compute_and_store_spy_adx()
            except Exception as e:
                logger.warning("[adx_regime] loop error: %s", e)
            await asyncio.sleep(900)  # 15 minutes

    expiry_task = asyncio.create_task(signal_expiry_loop())
    universe_task = asyncio.create_task(universe_cache_loop())
    mtm_task = asyncio.create_task(mark_to_market_loop())
    confluence_task = asyncio.create_task(confluence_engine_loop())
    holy_grail_task = asyncio.create_task(holy_grail_scan_loop())
    scout_task = asyncio.create_task(scout_scan_loop())
    sector_rs_task = asyncio.create_task(sector_rs_loop())
    sell_the_rip_task = asyncio.create_task(sell_the_rip_scan_loop())
    staleness_task = asyncio.create_task(factor_staleness_loop())
    vwap_task = asyncio.create_task(vwap_validation_loop())
    crypto_scan_task = asyncio.create_task(crypto_scan_loop())
    # RE-ENABLED 2026-06-18 (L1.0 Chunk 4): trimmed to the L0.2 liquid universe
    # (20 tickers) and flow-only (snapshot call dropped) → ~1,680 UW calls/day
    # (~1 call/ticker @ 5-min over the session), down from the ~6,720 that caused
    # the 06-16 budget incident. Self-gates to 09:00–16:00 ET. Restores the
    # flow_events feed for pipeline P2C / wh_confluence / committee briefings.
    uw_flow_poller_task = asyncio.create_task(uw_flow_poller_loop())
    flow_deadfeed_watchdog_task = asyncio.create_task(flow_deadfeed_watchdog_loop())  # L1.0 Chunk 3
    pythia_staleness_watchdog_task = asyncio.create_task(pythia_staleness_watchdog_loop())  # 6/29 brief Part 1, full liquid-20 as of 2026-07-17
    adx_regime_task = asyncio.create_task(adx_regime_loop())

    # Stable Engine: nightly close recompute + provisional snapshots + index/rates
    # strip (yfinance, zero UW).
    try:
        from jobs.stable_jobs import (
            stable_engine_loop, stable_strip_loop, stable_movers_loop, stable_tide_warmer_loop,
        )
        stable_engine_task = asyncio.create_task(stable_engine_loop())
        stable_strip_task = asyncio.create_task(stable_strip_loop())
        stable_movers_task = asyncio.create_task(stable_movers_loop())
        stable_tide_task = asyncio.create_task(stable_tide_warmer_loop())
        logger.info("✅ Stable Engine scheduler started")
    except Exception as e:
        logger.warning(f"⚠️ Could not start Stable Engine scheduler: {e}")

    # Triton Step-0: whale-flow shadow poller (RTH 09:30-16:00 ET, 120s cadence).
    # SHADOW-ONLY — writes triton_flow_shadow; nothing reads it for scoring.
    async def triton_shadow_poller_loop():
        import os, pytz
        from datetime import datetime as _dt, time as _t
        if os.getenv("TRITON_SHADOW_ENABLED", "true").lower() == "false":
            logger.info("triton_shadow: disabled via TRITON_SHADOW_ENABLED=false")
            return
        await asyncio.sleep(150)  # let DB connections settle
        while True:
            try:
                et = _dt.now(pytz.timezone("America/New_York"))
                if et.weekday() < 5 and _t(9, 30) <= et.time() <= _t(16, 0):
                    from jobs.triton_shadow_poller import run_triton_shadow_poller
                    await run_triton_shadow_poller()
            except Exception as e:
                logger.warning("triton_shadow poller loop error: %s", e)
            await asyncio.sleep(120)
    triton_shadow_task = asyncio.create_task(triton_shadow_poller_loop())

    # Triton Step-0 grader: daily post-close direction-adjusted forward returns.
    async def triton_grader_loop():
        import os, pytz
        from datetime import datetime as _dt, time as _t
        if os.getenv("TRITON_SHADOW_ENABLED", "true").lower() == "false":
            return
        last_run = None
        await asyncio.sleep(180)
        while True:
            try:
                et = _dt.now(pytz.timezone("America/New_York"))
                if et.weekday() < 5 and et.time() >= _t(16, 15) and last_run != et.date():
                    from jobs.triton_shadow_grader import run_triton_shadow_grader
                    await run_triton_shadow_grader()
                    last_run = et.date()
            except Exception as e:
                logger.warning("triton_shadow grader loop error: %s", e)
            await asyncio.sleep(1800)  # 30-min check
    triton_grader_task = asyncio.create_task(triton_grader_loop())

    # UW budget watchdog (Fable 2026-07-09): in-hub runtime circuit breaker. 24/7 as of
    # 2026-07-13 (7/10 lesson: first real 17K crossing landed AFTER the close; the counter
    # accumulates on the UTC day). Formerly RTH-gated
    # ~5-min tick; daily UW total >= 17K -> set the runtime shed flag (Triton poller
    # skips) + ONE Discord alert; >= 18K -> human-call escalation. No env var, no
    # redeploy. Replaces the TRITON_SHADOW_ENABLED env shed (which forced a mid-session
    # redeploy = RTH-blackout violation); env remains manual fallback only.
    async def uw_budget_watchdog_loop():
        await asyncio.sleep(160)
        while True:
            try:
                from jobs.uw_budget_watchdog import run_budget_watchdog
                await run_budget_watchdog()
            except Exception as e:
                logger.warning("uw_budget_watchdog loop error: %s", e)
            await asyncio.sleep(300)  # 5 min
    uw_budget_watchdog_task = asyncio.create_task(uw_budget_watchdog_loop())

    # UW daily-burn snapshot: persist each completed UTC day's per-caller + grand total
    # to uw_daily_burn so the 48h Redis counter TTL can never blind us again. Runs 24/7
    # (not RTH-gated — the UTC rollover is at 20:00 ET); snapshots the prior day once.
    async def uw_daily_burn_snapshot_loop():
        from datetime import datetime as _dt, timezone as _tz
        await asyncio.sleep(200)
        last_snap = None
        while True:
            try:
                today_utc = _dt.now(_tz.utc).date()
                if last_snap != today_utc:
                    from jobs.uw_budget_watchdog import run_daily_burn_snapshot
                    await run_daily_burn_snapshot()  # snapshots yesterday
                    last_snap = today_utc
            except Exception as e:
                logger.warning("uw_daily_burn snapshot loop error: %s", e)
            await asyncio.sleep(1800)  # 30-min check
    uw_daily_burn_snapshot_task = asyncio.create_task(uw_daily_burn_snapshot_loop())

    wh_accumulation_task = asyncio.create_task(wh_accumulation_loop())
    wh_reversal_task = asyncio.create_task(wh_reversal_loop())
    sector_refresh_fast_task = asyncio.create_task(sector_refresh_fast_loop())
    sector_refresh_slow_task = asyncio.create_task(sector_refresh_slow_loop())
    sector_refresh_close_snapshot_task = asyncio.create_task(sector_refresh_close_snapshot_loop())

    # Oracle insights: pre-compute analytics payload hourly
    async def oracle_refresh_loop():
        """Refresh Oracle insights cache every hour."""
        await asyncio.sleep(120)  # 2 min after startup

        while True:
            try:
                from analytics.oracle_engine import compute_oracle_payload
                import json as _json

                for asset_class in [None, "EQUITY", "CRYPTO"]:
                    for days in [7, 30, 90]:
                        payload = await compute_oracle_payload(
                            days=days, asset_class=asset_class
                        )
                        cache_key = f"oracle:insights:{days}:ALL:{asset_class or 'ALL'}"
                        await redis_client.set(
                            cache_key,
                            _json.dumps(payload, default=str),
                            ex=3600,
                        )
                logger.info("🔮 Oracle insights refreshed (9 variants)")
            except Exception as e:
                logger.warning("Oracle refresh error: %s", e)
            await asyncio.sleep(3600)  # 1 hour

    oracle_task = asyncio.create_task(oracle_refresh_loop())

    # Price collector: daily OHLCV for SPY + watchlist (backtesting + factor accuracy)
    async def price_collector_loop():
        """Collect daily prices for SPY + watchlist tickers."""
        await asyncio.sleep(180)  # 3 min startup delay
        while True:
            try:
                from analytics.price_collector import collect_price_history_cycle
                result = await collect_price_history_cycle()
                upserted = result.get("rows_upserted", 0)
                if upserted > 0:
                    logger.info("📈 Price collector: %d rows upserted", upserted)
            except Exception as e:
                logger.warning("Price collector error: %s", e)
            await asyncio.sleep(3600)  # 1 hour

    price_collector_task = asyncio.create_task(price_collector_loop())

    # Watchlist price alert: check every 30 min during market hours
    async def watchlist_price_alert_loop():
        import pytz
        from datetime import datetime as dt_cls

        await asyncio.sleep(120)  # 2 min startup delay

        while True:
            try:
                et = dt_cls.now(pytz.timezone("America/New_York"))
                if et.weekday() < 5 and 9 <= et.hour < 16:
                    from api.trade_watchlist import check_watchlist_price_alerts
                    await check_watchlist_price_alerts()
                else:
                    logger.debug("Watchlist alerts: outside market hours, skipping")
            except Exception as e:
                logger.warning("Watchlist price alert error: %s", e)
            await asyncio.sleep(1800)  # 30 minutes

    watchlist_alert_task = asyncio.create_task(watchlist_price_alert_loop())

    # Chronos: refresh earnings calendar daily at 6 AM ET
    async def chronos_earnings_loop():
        """Daily earnings calendar refresh from FMP."""
        import pytz
        from datetime import datetime as dt_cls

        await asyncio.sleep(60)  # 1 min startup delay

        while True:
            try:
                et = dt_cls.now(pytz.timezone("America/New_York"))
                # Run once daily around 6 AM ET on weekdays
                if et.weekday() < 5 and (5 <= et.hour <= 6):
                    from jobs.chronos_ingest import run_chronos_earnings_ingest
                    await run_chronos_earnings_ingest()
                    # Weekly ETF component refresh (Mondays only)
                    if et.weekday() == 0:
                        from utils.position_overlap import refresh_etf_components
                        await refresh_etf_components()
                elif et.hour == 7 and et.minute < 15:
                    # Catch-up run if 6 AM was missed
                    from jobs.chronos_ingest import run_chronos_earnings_ingest
                    await run_chronos_earnings_ingest()
            except Exception as e:
                logger.warning("Chronos earnings loop error: %s", e)
            await asyncio.sleep(3600)  # Check every hour (only runs at 6-7 AM)

    chronos_task = asyncio.create_task(chronos_earnings_loop())

    # Outcome resolver: walk 15m bars for accepted signals every 15 min (market hours)
    # S-1 Phase 2 (F-2, 2026-07-13): scoped to EQUITY only -- crypto now has its
    # own 24/7 loop below (crypto_outcome_resolver_loop), since crypto trades
    # around the clock and this equity-hours gate would otherwise delay a
    # Saturday-night BTC signal's resolution until Monday morning.
    async def outcome_resolver_loop():
        """Resolve WIN/LOSS for accepted EQUITY signals via intraday bar walk-forward."""
        import pytz
        from datetime import datetime as dt_cls
        from jobs.outcome_resolver import resolve_signal_outcomes

        await asyncio.sleep(120)  # 2 min startup delay

        while True:
            try:
                et = dt_cls.now(pytz.timezone("America/New_York"))
                if et.weekday() < 5 and 9 <= et.hour < 16:
                    await resolve_signal_outcomes(asset_class_filter="EQUITY")
                else:
                    logger.debug("Outcome resolver: outside market hours, skipping")
            except Exception as e:
                logger.warning("Outcome resolver loop error: %s", e)
            await asyncio.sleep(900)  # 15 minutes

    outcome_resolver_task = asyncio.create_task(outcome_resolver_loop())

    # Crypto outcome resolver: same 15-min bar-walk, but 24/7 -- no market-hours
    # gate. S-1 Phase 2 (F-2, 2026-07-13). Separate task from the equity loop
    # above so neither is blocked by the other's cadence/gating, and so the
    # two never double-process the same signal (each filters to one
    # asset_class).
    async def crypto_outcome_resolver_loop():
        """Resolve WIN/LOSS for accepted CRYPTO signals via intraday bar walk-forward, 24/7."""
        from jobs.outcome_resolver import resolve_signal_outcomes

        await asyncio.sleep(135)  # offset 15s from the equity loop's 120s startup delay

        while True:
            try:
                await resolve_signal_outcomes(asset_class_filter="CRYPTO")
            except Exception as e:
                logger.warning("Crypto outcome resolver loop error: %s", e)
            await asyncio.sleep(900)  # 15 minutes, 24/7

    crypto_outcome_resolver_task = asyncio.create_task(crypto_outcome_resolver_loop())

    # B2 options-P&L resolver: capture entry/exit marks for signal_options_expressions
    async def b2_options_resolver_loop():
        """Capture entry/exit marks for B2 expression rows (15 min, market hours)."""
        import pytz
        from datetime import datetime as dt_cls
        from jobs.b2_options_resolver import run_b2_resolver_tick, B2_SHADOW_MODE

        if B2_SHADOW_MODE:
            logger.info("B2 options resolver: shadow mode ON (data collection, no live decisions)")

        await asyncio.sleep(150)  # offset 30s from outcome_resolver's 120s startup delay

        while True:
            try:
                et = dt_cls.now(pytz.timezone("America/New_York"))
                in_market = (
                    et.weekday() < 5
                    and (
                        (et.hour == 9 and et.minute >= 30)
                        or (10 <= et.hour < 16)
                    )
                )
                if in_market:
                    pool = await get_postgres_client()
                    await run_b2_resolver_tick(pool)
                else:
                    logger.debug("B2 resolver: outside market hours, skipping")
            except Exception as e:
                logger.warning("B2 options resolver loop error: %s", e)
            await asyncio.sleep(900)  # 15 minutes

    b2_resolver_task = asyncio.create_task(b2_options_resolver_loop())

    # Initial Chronos data load
    try:
        from jobs.chronos_ingest import run_chronos_earnings_ingest
        asyncio.create_task(run_chronos_earnings_ingest())
        logger.info("📅 Chronos initial earnings load queued")
    except Exception as e:
        logger.warning("Chronos initial load error: %s", e)

    # Ensure proximity attribution columns exist
    try:
        from analytics.proximity_attribution import ensure_attribution_columns
        await ensure_attribution_columns()
    except Exception as e:
        logger.warning("Attribution columns setup: %s", e)

    # ZEUS Phase 3: verify feed_tier schema after startup
    asyncio.create_task(verify_zeus_schema())

    # MCP server lifespan — must wrap the parent yield so FastMCP's
    # StreamableHTTPSessionManager task group is live for the duration
    # of the parent app. Imported lazily here to keep startup tolerant
    # if hub_mcp fails to load (yield still runs).
    try:
        from hub_mcp.router import mcp_lifespan as _mcp_lifespan
    except Exception as exc:
        logger.error("MCP lifespan import failed; running without MCP: %s", exc)
        _mcp_lifespan = None

    logger.info("✅ Pandora's Box is live")

    if _mcp_lifespan is None:
        yield
    else:
        async with _mcp_lifespan(app):
            yield

    # Shutdown
    expiry_task.cancel()
    universe_task.cancel()
    mtm_task.cancel()
    confluence_task.cancel()
    holy_grail_task.cancel()
    scout_task.cancel()
    sector_rs_task.cancel()
    sell_the_rip_task.cancel()
    staleness_task.cancel()
    vwap_task.cancel()
    crypto_scan_task.cancel()
    uw_flow_poller_task.cancel()  # RE-ENABLED 2026-06-18 (L1.0 Chunk 4) — see creation site
    flow_deadfeed_watchdog_task.cancel()  # L1.0 Chunk 3 dead-feed watchdog
    pythia_staleness_watchdog_task.cancel()  # PYTHIA per-name liquid-20 staleness alarm (6/29 brief Part 1)
    triton_shadow_task.cancel()  # Triton Step-0 shadow poller
    triton_grader_task.cancel()  # Triton Step-0 grader
    wh_accumulation_task.cancel()
    wh_reversal_task.cancel()
    oracle_task.cancel()
    price_collector_task.cancel()
    watchlist_alert_task.cancel()
    chronos_task.cancel()
    outcome_resolver_task.cancel()
    crypto_outcome_resolver_task.cancel()
    logger.info("🛑 Shutting down Pandora's Box...")
    await redis_client.close()
    await postgres_client.close()
    logger.info("👋 Goodbye")

# Initialize FastAPI app
app = FastAPI(
    title="Pandora's Box API",
    description="Real-time trading signal processor",
    version="1.0.0",
    lifespan=lifespan
)

# CORS — restrict to known frontend origins.
# SECURITY (2026-06-11, cookie auth): never combine "*" with allow_credentials — Starlette
# reflects ANY origin for credentialed (cookie-bearing) requests, which would defeat the
# session cookie. The dashboard is same-origin (CORS doesn't apply to it), so no cross-origin
# credentialed access is needed by default. Set ALLOWED_ORIGINS to a real comma-separated
# list ONLY if a genuine cross-origin browser caller is ever added.
_cors_origins = (os.getenv("ALLOWED_ORIGINS") or "").strip()
if _cors_origins in ("", "*"):
    _allowed_origins: list[str] = []
    _allow_credentials = False
else:
    _allowed_origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]
    _allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Compress responses >1KB. AEGIS: minimum_size=1000 is the BREACH/CRIME floor — do not lower.
app.add_middleware(GZipMiddleware, minimum_size=1000)

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Pandora's Box",
        "version": "1.0.0"
    }

@app.get("/api/l0/status")
async def l0_status_endpoint():
    """L0.1a enforcement visibility (E3): enforce flag + today's would_suppress
    count, so suppression is never silent. Read-only, fail-safe, on-demand."""
    from config.l0_routing import l0_status
    from datetime import date as _date
    pool = await get_postgres_client()
    return {"date": _date.today().isoformat(), **(await l0_status(pool))}

@app.get("/health")
async def health_check():
    """Resilient health check (never throws on transient dependency failures)."""
    from scheduler.bias_scheduler import get_eastern_now
    from database.redis_client import get_redis_status
    
    redis_state = "unknown"
    postgres_state = "unknown"

    try:
        redis_status = get_redis_status()
        redis_state = redis_status.get("status", "unknown")
    except Exception:
        redis_state = "error"

    try:
        postgres_client = await get_postgres_client()
        postgres_state = "connected" if postgres_client else "disconnected"
    except Exception:
        postgres_state = "error"
    
    now_et = get_eastern_now()
    overall = "healthy"
    if postgres_state in {"error", "disconnected"}:
        overall = "degraded"
    
    # ZEUS Phase 3 — feed_tier schema + distribution check
    zeus_block: dict = {}
    try:
        from config import ZEUS_TIERED_ROUTING_ENABLED
        zeus_block["routing_enabled"] = ZEUS_TIERED_ROUTING_ENABLED

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            # Confirm feed_tier column exists
            col_exists = await conn.fetchval(
                """
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_name = 'signals' AND column_name = 'feed_tier'
                """
            )
            zeus_block["feed_tier_column"] = bool(col_exists)

            # 7-day tier distribution
            if col_exists:
                rows = await conn.fetch(
                    """
                    SELECT feed_tier, COUNT(*) AS n
                    FROM signals
                    WHERE created_at > NOW() - INTERVAL '7 days'
                    GROUP BY feed_tier
                    ORDER BY n DESC
                    """
                )
                zeus_block["tier_distribution_7d"] = {
                    r["feed_tier"] or "null": int(r["n"]) for r in rows
                }

            # flow_events last 24h
            flow_count = await conn.fetchval(
                "SELECT COUNT(*) FROM flow_events WHERE captured_at > NOW() - INTERVAL '24 hours'"
            )
            zeus_block["flow_events_24h"] = int(flow_count or 0)

    except Exception as _ze:
        zeus_block["error"] = str(_ze)

    # Stable Engine job health — a dead data pipe is now visible where we already look.
    stable_jobs_block: dict = {}
    try:
        from stable_engine.job_status import health_summary
        stable_jobs_block = await health_summary()
        if stable_jobs_block.get("any_flatline") and overall == "healthy":
            overall = "degraded"
    except Exception as _sje:
        stable_jobs_block = {"error": str(_sje)}

    return {
        "status": overall,
        "server_time_et": now_et.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "redis": redis_state,
        "postgres": postgres_state,
        "websocket_connections": len(manager.active_connections),
        "zeus": zeus_block,
        "stable_jobs": stable_jobs_block,
    }


async def verify_zeus_schema() -> None:
    """
    Startup check — warn to Discord if feed_tier column is missing.
    Fires once after a 30s delay to let DB pool initialize.
    """
    import asyncio
    await asyncio.sleep(30)
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            col_exists = await conn.fetchval(
                """
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_name = 'signals' AND column_name = 'feed_tier'
                """
            )
        if not col_exists:
            import os, urllib.request, json as _json
            webhook = os.getenv("DISCORD_WEBHOOK_SIGNALS") or ""
            if webhook:
                payload = _json.dumps({
                    "content": "**ZEUS WARNING** — `feed_tier` column missing from `signals` table. Run `backfill_feed_tier.py` and check DB migrations."
                }).encode()
                req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass  # Never crash startup


@app.get("/live")
async def live_check():
    """Pure liveness probe for platform health checks."""
    return {"status": "alive"}


@app.get("/api/monitoring/factor-staleness")
async def factor_staleness_endpoint():
    """Check factor freshness — returns stale, healthy, and missing factors."""
    from monitoring.factor_staleness import check_factor_staleness
    return await check_factor_staleness()


@app.get("/api/monitoring/vwap-validation")
async def vwap_validation_endpoint():
    """Compute current VWAP bands for SPY and return latest reading."""
    from scanners.vwap_validator import run_vwap_validation
    result = await run_vwap_validation()
    if result:
        return result
    return {"status": "unavailable", "message": "VWAP validation not available (missing yfinance/pandas or outside market hours)"}


@app.get("/api/analytics/confluence-validation")
async def confluence_validation_endpoint(days: int = 30):
    """Compare outcomes of confluent vs standalone signals."""
    from analytics.confluence_validation import compute_confluence_validation
    return await compute_confluence_validation(days=days)


@app.get("/api/analytics/shadow-validation")
async def shadow_validation_endpoint(days: int = 5):
    """Compare server-side scanner signals vs TradingView webhook signals."""
    from analytics.confluence_validation import compute_shadow_validation
    return await compute_shadow_validation(days=days)


@app.get("/api/bias/{timeframe}")
async def get_bias_data(timeframe: str):
    """Get current bias for a specific timeframe"""
    timeframe_lower = timeframe.lower()
    if timeframe_lower == "summary":
        from api.bias import get_all_bias_indicators
        return await get_all_bias_indicators()
    if timeframe_lower == "tick":
        from api.bias import get_tick_bias
        return await get_tick_bias()
    if timeframe_lower == "composite":
        from api.bias import get_composite_bias
        return await get_composite_bias()
    if timeframe_lower == "factor-health":
        from api.bias import get_factor_health
        return await get_factor_health()
    if timeframe_lower == "health":
        from api.bias import get_pivot_health
        return await get_pivot_health()
    # Composite-system timeframes: read from the composite engine
    if timeframe_lower in {"intraday", "macro", "overall"}:
        try:
            from api.bias import get_composite_timeframes
            tf_data = await get_composite_timeframes()
            if timeframe_lower == "overall":
                return {
                    "level": tf_data.get("composite_bias", "NEUTRAL"),
                    "score": tf_data.get("composite_score", 0.0),
                    "data": {"confidence": tf_data.get("confidence")},
                    "updated_at": tf_data.get("timestamp"),
                }
            entry = (tf_data.get("timeframes") or {}).get(timeframe_lower)
            if entry:
                return {
                    "level": entry.get("bias_level", "NEUTRAL"),
                    "score": entry.get("sub_score", 0.0),
                    "data": {
                        "momentum": entry.get("momentum"),
                        "divergent": entry.get("divergent"),
                        "active_count": entry.get("active_count"),
                        "total_count": entry.get("total_count"),
                    },
                    "updated_at": tf_data.get("timestamp"),
                }
        except Exception as _ce:
            logger.warning("Composite timeframe lookup failed for %s: %s", timeframe_lower, _ce)
        return {"level": "NEUTRAL", "data": {}, "updated_at": None}

    if timeframe_lower not in {"daily", "weekly", "monthly", "cyclical"}:
        raise HTTPException(status_code=404, detail="Unknown bias timeframe")

    from database.redis_client import get_bias

    bias = await get_bias(timeframe.upper())
    if bias:
        return bias

    # Fallback: read from bias_history.json (populated by the scheduler)
    # Handles the window between deploys and the next scheduler run.
    try:
        import json as _json
        _hist = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "bias_history.json")
        with open(_hist) as _f:
            _history = _json.load(_f)
        _current = (_history.get(timeframe_lower) or {}).get("current") or {}
        if _current:
            return {
                "level": _current.get("level", "NEUTRAL"),
                "data": _current.get("details", {}),
                "updated_at": _current.get("timestamp"),
            }
    except Exception as _fe:
        logger.debug("bias_history fallback failed for %s: %s", timeframe_lower, _fe)

    return {"level": "NEUTRAL", "data": {}, "updated_at": None}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time signal updates
    Connects computer, laptop, and phone simultaneously
    """
    await manager.connect(websocket)
    logger.info(f"New WebSocket connection. Total: {len(manager.active_connections)}")
    
    try:
        while True:
            # Keep connection alive with ping/pong
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info(f"WebSocket disconnected. Remaining: {len(manager.active_connections)}")

# Import and include routers (webhook endpoints, API routes)
from webhooks.tradingview import router as webhook_router
from webhooks.circuit_breaker import router as circuit_breaker_router
from webhooks.whale import router as whale_webhook_router
from webhooks.footprint import router as footprint_webhook_router
from webhooks.hermes import router as hermes_webhook_router
from webhooks.pythia_events import router as pythia_webhook_router
from api.auth import router as auth_router
from api.bias_source_comparison import router as bias_comparison_router
from api.committee_history import router as committee_history_router
from api.uw_health import router as uw_health_router
from api.insider import router as insider_router
from api.briefing_store import router as briefing_store_router
from api.hydra import router as hydra_router
from api.positions import router as positions_router
from api.watchlist import router as watchlist_router
from api.bias import router as bias_router
from api.strategies import router as strategies_router
from api.cta import router as cta_router
from api.btc_signals import router as btc_signals_router
from api.flow import router as flow_router
from api.dollar_smile import router as dollar_smile_router
from api.sector_rotation import router as sector_rotation_router
from api.market_indicators import router as market_indicators_router
from api.hybrid_scanner import router as hybrid_scanner_router

from api.knowledgebase import router as knowledgebase_router
from api.dev_shadow import router as dev_shadow_router
from api.alerts import router as alerts_router
from api.uw_integration import router as uw_integration_router
from api.uw import router as uw_router
from api.analyzer import router as analyzer_router
from api.crypto_market import router as crypto_market_router
from api.redis_health import router as redis_health_router
from api.weekly_audit import router as weekly_audit_router
from analytics.api import analytics_router
from api.footprint_correlation import router as footprint_correlation_router
from api.portfolio import router as portfolio_router
from api.unified_positions import router as unified_positions_router
from api.trade_ideas import router as trade_ideas_router
from api.accept_flow import router as accept_flow_router
from api.committee_bridge import router as committee_bridge_router
from api.market_data import router as market_data_router
from api.confluence import router as confluence_router
from api.macro import router as macro_router
from api.macro_strip import router as macro_strip_router
from api.trip_wires import router as trip_wires_router
from api.sectors import router as sectors_router
from api.flow_summary import router as flow_summary_router
from api.flow_ingestion import router as flow_ingestion_router
from api.flow_radar import router as flow_radar_router
from api.regime import router as regime_router
from api.catalyst_calendar import router as catalyst_router
from api.ticker_profile import router as ticker_profile_router
from api.trade_watchlist import router as trade_watchlist_router
from api.chronos import router as chronos_router
from api.mp import router as mp_router
from webhooks.mp_levels import router as mp_webhook_router
from api.signals import router as signals_router

app.include_router(webhook_router, prefix="/webhook", tags=["webhooks"])
app.include_router(circuit_breaker_router, prefix="/webhook", tags=["circuit-breaker"])
app.include_router(whale_webhook_router, prefix="/webhook", tags=["whale"])
app.include_router(footprint_webhook_router, prefix="/webhook", tags=["webhooks"])
app.include_router(hermes_webhook_router, prefix="/api", tags=["hermes"])
app.include_router(pythia_webhook_router, prefix="/api", tags=["pythia"])
app.include_router(auth_router, prefix="/api", tags=["auth"])  # /api/auth/login|logout|session
app.include_router(bias_comparison_router, prefix="/api", tags=["bias-comparison"])
app.include_router(committee_history_router, prefix="/api", tags=["committee-history"])
app.include_router(uw_health_router, prefix="/api", tags=["uw-health"])
app.include_router(insider_router, prefix="/api", tags=["insider-congress"])
app.include_router(briefing_store_router, prefix="/api", tags=["briefing"])
app.include_router(hydra_router, prefix="/api", tags=["hydra"])
app.include_router(positions_router, prefix="/api", tags=["positions"])
app.include_router(watchlist_router, prefix="/api", tags=["watchlist"])
app.include_router(bias_router, prefix="/api", tags=["bias"])
app.include_router(strategies_router, prefix="/api", tags=["strategies"])
app.include_router(cta_router, prefix="/api", tags=["cta"])
app.include_router(btc_signals_router, prefix="/api", tags=["btc-signals"])
app.include_router(flow_router, prefix="/api", tags=["options-flow"])
app.include_router(dollar_smile_router, prefix="/api", tags=["dollar-smile"])
app.include_router(sector_rotation_router, prefix="/api", tags=["sector-rotation"])
app.include_router(market_indicators_router, prefix="/api", tags=["market-indicators"])

app.include_router(hybrid_scanner_router, prefix="/api", tags=["hybrid-scanner"])
app.include_router(knowledgebase_router, prefix="/api", tags=["knowledgebase"])
app.include_router(dev_shadow_router, tags=["dev-shadow"])  # prefix="/api/dev" already in router
app.include_router(alerts_router, prefix="/api", tags=["alerts"])
app.include_router(uw_integration_router, prefix="/api", tags=["unusual-whales"])
app.include_router(uw_router, prefix="/api", tags=["unusual-whales"])
app.include_router(analyzer_router, prefix="/api", tags=["analyzer"])
app.include_router(crypto_market_router, prefix="/api", tags=["crypto-market"])
app.include_router(redis_health_router, prefix="/api", tags=["health"])
app.include_router(weekly_audit_router, prefix="/api", tags=["weekly-audit"])
app.include_router(analytics_router, prefix="/api/analytics", tags=["analytics"])
app.include_router(footprint_correlation_router, prefix="/api", tags=["footprint"])
app.include_router(portfolio_router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(unified_positions_router, prefix="/api", tags=["unified-positions"])
app.include_router(trade_ideas_router, prefix="/api", tags=["trade-ideas"])
app.include_router(accept_flow_router, prefix="/api", tags=["accept-flow"])
app.include_router(committee_bridge_router, prefix="/api", tags=["committee"])
app.include_router(market_data_router, prefix="/api", tags=["market-data"])
app.include_router(confluence_router, prefix="/api", tags=["confluence"])
app.include_router(macro_router, prefix="/api/macro", tags=["macro"])
app.include_router(macro_strip_router, prefix="/api", tags=["macro-strip"])
app.include_router(trip_wires_router, prefix="/api", tags=["trip-wires"])
app.include_router(sectors_router, prefix="/api", tags=["sectors"])
app.include_router(flow_summary_router, prefix="/api", tags=["flow-summary"])
app.include_router(flow_radar_router, prefix="/api", tags=["flow-radar"])
app.include_router(flow_ingestion_router, prefix="/api", tags=["uw-flow"])
app.include_router(regime_router, prefix="/api", tags=["regime"])
app.include_router(catalyst_router, prefix="/api", tags=["catalyst"])
app.include_router(ticker_profile_router, prefix="/api", tags=["ticker-profile"])
app.include_router(trade_watchlist_router, prefix="/api", tags=["trade-watchlist"])
app.include_router(chronos_router, prefix="/api", tags=["chronos"])
app.include_router(mp_router, prefix="/api", tags=["market-profile"])
app.include_router(mp_webhook_router, prefix="/webhook", tags=["market-profile"])
app.include_router(signals_router, prefix="/api", tags=["signals"])
from api.stable import router as stable_router
app.include_router(stable_router, prefix="/api", tags=["stable"])
from api.layout import router as layout_router
app.include_router(layout_router, prefix="/api", tags=["layout"])
from api.board_state import router as board_router
app.include_router(board_router, prefix="/api", tags=["board"])

# ─── MCP server (v1) ────────────────────────────────────────────────────
# Mounted as an isolated ASGI sub-app at /mcp/v1. CORS / bearer auth /
# rate limit / audit middleware are wrapped inside the sub-app so they
# never loosen the parent app. Tools register via @mcp_tool at import
# time inside hub_mcp.router. See backend/hub_mcp/README.md.
#
# The FastMCP lifespan is chained into the parent's lifespan above; the
# session-manager task group needs to be live before any request fires.
try:
    import time as _time
    from datetime import datetime as _datetime, timezone as _timezone

    # Captured at module import (≈ container/worker start) so /mcp/v1/health
    # can report uptime + a "deploy timestamp" without an extra system call.
    _HUB_MCP_START_MONOTONIC = _time.monotonic()
    _HUB_MCP_START_UTC = _datetime.now(_timezone.utc)

    # Register the health route BEFORE app.mount("/mcp/v1", ...) below.
    # Starlette iterates app.routes in registration order; a Mount registered
    # earlier swallows every path under its prefix, so a specific Route at
    # /mcp/v1/health declared after the mount returns 404. (Verified
    # empirically post-deploy 2026-05-24T22:30 UTC.) Register the Route
    # first, then the Mount.
    async def _mcp_asgi_self_check(target_app, method: str, path: str, host: str) -> dict:
        """Fire a real ASGI request at an MCP sub-app in-process and report
        what actually came back. Used so /mcp/v1/health can tell "discovery
        endpoint is broken" apart from "app didn't even start" — the 421
        incident on 2026-07-09 was invisible to the old health check because
        it only proved the parent app was up, never that FastMCP's own
        mounted routes were reachable."""
        status_holder: dict = {"code": None}
        body_buf = bytearray()
        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "root_path": "",
            "scheme": "https",
            "headers": [
                (b"host", host.encode("ascii")),
                (b"accept", b"application/json"),
            ],
            "client": ("127.0.0.1", 0),
            "server": (host, 443),
        }
        body_sent = {"v": False}

        async def receive():
            if not body_sent["v"]:
                body_sent["v"] = True
                return {"type": "http.request", "body": b"", "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
            elif message["type"] == "http.response.body":
                body_buf.extend(message.get("body", b""))

        try:
            await target_app(scope, receive, send)
        except Exception as e:
            return {"ok": False, "status": status_holder["code"], "error": f"{type(e).__name__}: {e}"}
        code = status_holder["code"]
        return {
            "ok": code is not None and code < 400,
            "status": code,
            "body_snippet": bytes(body_buf[:200]).decode("utf-8", "replace"),
        }

    @app.get("/mcp/v1/health", include_in_schema=False)
    async def _mcp_v1_health():
        # Unauthenticated by design — Nick needs to hit this from a browser
        # to tell "session stale" apart from "server down" without touching
        # an OAuth flow. See docs/operations/mcp-connection-guide.md § 1.
        uptime = int(_time.monotonic() - _HUB_MCP_START_MONOTONIC)

        from importlib.metadata import version as _pkg_version, PackageNotFoundError

        versions: dict = {}
        for _pkg_name in ("fastmcp", "mcp"):
            try:
                versions[_pkg_name] = _pkg_version(_pkg_name)
            except PackageNotFoundError:
                versions[_pkg_name] = "not installed"
            except Exception as e:
                versions[_pkg_name] = f"lookup error: {e}"

        public_host = os.environ.get("RAILWAY_PUBLIC_DOMAIN") or "pandoras-box-production.up.railway.app"
        discovery_check = await _mcp_asgi_self_check(
            _fastmcp_inner, "GET", "/.well-known/oauth-authorization-server", public_host
        )

        status = "ok" if discovery_check.get("ok") else "degraded"
        return {
            "status": status,
            "service": "mcp/v1",
            "uptime_seconds": uptime,
            "deployed_at": _HUB_MCP_START_UTC.isoformat(),
            "worker_id": f"pid-{os.getpid()}",
            "version": (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "unknown")[:7],
            "package_versions": versions,
            "discovery_self_check": discovery_check,
        }
    logger.info("✅ /mcp/v1/health endpoint registered")

    from hub_mcp.router import mcp_app, fastmcp_app as _fastmcp_inner
    app.mount("/mcp/v1", mcp_app)
    logger.info("✅ MCP v1 server mounted at /mcp/v1")

    # ─── OAuth discovery + DCR at the DOMAIN ROOT ────────────────────────
    # Claude.ai's MCP connector and RFC 8414 expect these endpoints at the
    # host root, but FastMCP serves them under /mcp/v1/.well-known/* (its
    # mount prefix). These handlers forward each root request to the
    # unwrapped FastMCP starlette app via ASGI scope rewriting.
    #
    # The receive callable returns http.disconnect immediately after the
    # first body chunk — the inner app reads the body once and sends a
    # complete response; further receive() calls (if any) signal end of
    # the request cleanly. (An earlier version blocked on a fresh
    # asyncio.Event().wait() that was never .set(), which hung the
    # request worker on the new endpoints. Don't reintroduce that.)
    from fastapi import Request
    from fastapi.responses import Response as FastResponse

    async def _forward_to_fastmcp(request: Request, target_path: str) -> FastResponse:
        """Proxy a request from the parent app to the mounted FastMCP sub-app
        by manipulating the ASGI scope. Bypasses the middleware chain in
        mcp_app — these discovery / DCR endpoints are unauthenticated by
        design (clients hit them before they have any credentials).
        """
        body = await request.body()

        scope = dict(request.scope)
        scope["path"] = target_path
        scope["raw_path"] = target_path.encode("ascii")
        scope["root_path"] = ""

        body_sent = {"v": False}

        async def receive():
            if not body_sent["v"]:
                body_sent["v"] = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        status_holder = {"code": 0}
        headers_holder: list = []
        body_buf = bytearray()

        async def send(message):
            t = message.get("type")
            if t == "http.response.start":
                status_holder["code"] = message["status"]
                headers_holder[:] = message.get("headers", [])
            elif t == "http.response.body":
                body_buf.extend(message.get("body", b""))

        await _fastmcp_inner(scope, receive, send)

        out_headers: dict[str, str] = {}
        for k, v in headers_holder:
            name = k.decode("latin-1")
            if name.lower() == "content-length":
                # Let Starlette recompute
                continue
            out_headers[name] = v.decode("latin-1")

        return FastResponse(
            content=bytes(body_buf),
            status_code=status_holder["code"] or 500,
            headers=out_headers,
        )

    @app.get("/.well-known/oauth-authorization-server", include_in_schema=False)
    async def _oauth_authz_metadata_root(request: Request):
        return await _forward_to_fastmcp(
            request, "/.well-known/oauth-authorization-server"
        )

    @app.get("/.well-known/oauth-authorization-server/mcp/v1", include_in_schema=False)
    async def _oauth_authz_metadata_rfc8414(request: Request):
        # RFC 8414 path-suffix form (for issuers with a path component).
        return await _forward_to_fastmcp(
            request, "/.well-known/oauth-authorization-server"
        )

    @app.get("/.well-known/oauth-protected-resource", include_in_schema=False)
    @app.get("/.well-known/oauth-protected-resource/mcp/v1", include_in_schema=False)
    async def _oauth_protected_resource_root(request: Request):
        return await _forward_to_fastmcp(
            request, "/.well-known/oauth-protected-resource/mcp/v1/"
        )

    @app.post("/register", include_in_schema=False)
    async def _dcr_register_root(request: Request):
        return await _forward_to_fastmcp(request, "/register")

    # ─── /mcp/v1 (no trailing slash) — avoid the FastAPI mount 307 ───
    # Claude.ai's connector uses the OAuth `issuer` URL (".../mcp/v1" without
    # trailing slash) as the MCP endpoint and POSTs there. FastAPI's mount at
    # /mcp/v1 normally 307-redirects to /mcp/v1/, which Claude.ai does not
    # follow on POST. This explicit handler bypasses the redirect by
    # forwarding the request directly to the wrapped MCP ASGI app
    # (mcp_app — the full CORS+RateLimit+Audit chain wrapping FastMCP).

    async def _forward_to_mcp_app(request: Request) -> FastResponse:
        body = await request.body()

        scope = dict(request.scope)
        # The mounted mcp_app expects to see paths relative to its mount
        # point, i.e. "/" for the protocol root.
        scope["path"] = "/"
        scope["raw_path"] = b"/"
        scope["root_path"] = "/mcp/v1"

        body_sent = {"v": False}

        async def receive():
            if not body_sent["v"]:
                body_sent["v"] = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        status_holder = {"code": 0}
        headers_holder: list = []
        body_buf = bytearray()

        async def send(message):
            t = message.get("type")
            if t == "http.response.start":
                status_holder["code"] = message["status"]
                headers_holder[:] = message.get("headers", [])
            elif t == "http.response.body":
                body_buf.extend(message.get("body", b""))

        await mcp_app(scope, receive, send)

        out_headers: dict[str, str] = {}
        for k, v in headers_holder:
            name = k.decode("latin-1")
            if name.lower() == "content-length":
                continue
            out_headers[name] = v.decode("latin-1")

        return FastResponse(
            content=bytes(body_buf),
            status_code=status_holder["code"] or 500,
            headers=out_headers,
        )

    @app.api_route(
        "/mcp/v1",
        methods=["GET", "POST", "DELETE"],
        include_in_schema=False,
    )
    async def _mcp_v1_no_slash(request: Request):
        return await _forward_to_mcp_app(request)

    logger.info(
        "✅ MCP OAuth discovery + DCR exposed at domain root for Claude.ai; "
        "/mcp/v1 (no slash) explicit handler installed"
    )
except Exception as exc:
    logger.error(f"❌ MCP v1 server failed to mount: {exc}", exc_info=True)

# Serve frontend static files
# Multiple path resolution strategies for different deployment environments
possible_paths = [
    os.path.join(os.path.dirname(__file__), "..", "frontend"),  # Running from backend/
    os.path.join(os.getcwd(), "..", "frontend"),  # CWD is backend/
    os.path.join(os.getcwd(), "frontend"),  # CWD is root
    "/app/frontend",  # Railway absolute path
]

frontend_path = None
for path in possible_paths:
    if os.path.exists(path) and os.path.isdir(path):
        frontend_path = os.path.abspath(path)
        logger.info(f"✅ Frontend found at: {frontend_path}")
        break

if frontend_path:
    # THE FLIP (2026-07-13, c4 of dashboard-rebuild-v2 brief): /app now serves
    # v2 ("Judgment Layer"); the old layout moves to /app/legacy for a 7-day
    # parallel-run window before a removal commit retires it (~2026-07-20).
    @app.get("/app", response_class=FileResponse)
    async def serve_frontend():
        """Serve the v2 dashboard (flipped 2026-07-13; was legacy index.html)"""
        return FileResponse(os.path.join(frontend_path, "v2.html"))

    # /app/v2 kept as a redundant alias post-flip (harmless; avoids breaking
    # any bookmarked/shared links). MUST stay declared before the /app/{mode}
    # catch-all so it isn't swallowed and served the legacy index.html.
    @app.get("/app/v2", response_class=FileResponse)
    async def serve_frontend_v2():
        """Serve the v2 dashboard shell (alias of /app post-flip)."""
        return FileResponse(os.path.join(frontend_path, "v2.html"))

    @app.get("/v2.js", response_class=FileResponse)
    async def serve_v2_js():
        return FileResponse(os.path.join(frontend_path, "v2.js"))

    @app.get("/v2.css", response_class=FileResponse)
    async def serve_v2_css():
        return FileResponse(os.path.join(frontend_path, "v2.css"))

    @app.get("/app/{mode}", response_class=FileResponse)
    async def serve_frontend_mode(mode: str):
        """Serve legacy frontend for SPA client-side routes, including
        /app/legacy (post-flip retention window) and pre-existing deep links
        like /app/crypto, /app/hub."""
        return FileResponse(os.path.join(frontend_path, "index.html"))
    
    @app.get("/knowledgebase", response_class=FileResponse)
    async def serve_knowledgebase():
        """Serve the knowledgebase page"""
        return FileResponse(os.path.join(frontend_path, "knowledgebase.html"))

    @app.get("/dev/shadow-3-10", response_class=FileResponse)
    async def serve_shadow_3_10():
        """Serve the 3-10 shadow-mode dev view. No nav link — direct URL only."""
        return FileResponse(os.path.join(frontend_path, "shadow_3_10.html"))
    
    @app.get("/app.js", response_class=FileResponse)
    async def serve_app_js():
        return FileResponse(os.path.join(frontend_path, "app.js"))

    @app.get("/cockpit.js", response_class=FileResponse)
    async def serve_cockpit_js():
        return FileResponse(os.path.join(frontend_path, "cockpit.js"))

    @app.get("/laboratory.js", response_class=FileResponse)
    async def serve_laboratory_js():
        return FileResponse(os.path.join(frontend_path, "laboratory.js"))

    @app.get("/knowledgebase.js", response_class=FileResponse)
    async def serve_knowledgebase_js():
        return FileResponse(os.path.join(frontend_path, "knowledgebase.js"))
    
    @app.get("/styles.css", response_class=FileResponse)
    async def serve_styles():
        return FileResponse(os.path.join(frontend_path, "styles.css"))
    
    @app.get("/manifest.json", response_class=FileResponse)
    async def serve_manifest():
        return FileResponse(os.path.join(frontend_path, "manifest.json"))

    @app.get("/favicon.ico", response_class=FileResponse)
    async def serve_favicon():
        favicon_path = os.path.join(frontend_path, "favicon.ico")
        if os.path.exists(favicon_path):
            return FileResponse(favicon_path)
        return Response(status_code=204)

    @app.get("/icon-192.png", response_class=FileResponse)
    async def serve_icon_192():
        return FileResponse(os.path.join(frontend_path, "icon-192.png"), media_type="image/png")

    @app.get("/icon-512.png", response_class=FileResponse)
    async def serve_icon_512():
        return FileResponse(os.path.join(frontend_path, "icon-512.png"), media_type="image/png")
    
    # Mount frontend assets directory (images, etc.)
    assets_path = os.path.join(frontend_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="frontend-assets")
        logger.info(f"✅ Frontend assets mounted from: {assets_path}")
else:
    logger.warning("⚠️ Frontend directory not found. Tried paths:")
    for path in possible_paths:
        logger.warning(f"  - {path}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
