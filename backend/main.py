"""
Pandora's Box - Main FastAPI Application
High-performance trading signal processor with sub-100ms latency
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
    # (2 minutes after Polygon's 15-min data refresh) during market hours
    async def mark_to_market_loop():
        """Fetch live Polygon prices for open positions during market hours.
        Clock-aware: fires at :02, :17, :32, :47 past each hour (9 AM - 5 PM ET weekdays).
        Forces a closing bell run at 4:17 PM ET to capture near-close prices.
        """
        import pytz
        from datetime import datetime as dt_cls

        MTM_MINUTES = [2, 17, 32, 47]  # 2 min after Polygon refresh at :00/:15/:30/:45
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
            await asyncio.sleep(300)  # 5 minutes

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

    # Ensure proximity attribution columns exist
    try:
        from analytics.proximity_attribution import ensure_attribution_columns
        await ensure_attribution_columns()
    except Exception as e:
        logger.warning("Attribution columns setup: %s", e)

    logger.info("✅ Pandora's Box is live")

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
    oracle_task.cancel()
    price_collector_task.cancel()
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

# CORS — restrict to known frontend origins
_cors_origins = os.getenv("ALLOWED_ORIGINS") or "*"
if _cors_origins == "*":
    _allowed_origins = ["*"]
else:
    _allowed_origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Pandora's Box",
        "version": "1.0.0"
    }

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
    
    return {
        "status": overall,
        "server_time_et": now_et.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "redis": redis_state,
        "postgres": postgres_state,
        "websocket_connections": len(manager.active_connections)
    }


@app.get("/live")
async def live_check():
    """Pure liveness probe for platform health checks."""
    return {"status": "alive"}


@app.get("/api/monitoring/factor-staleness")
async def factor_staleness_endpoint():
    """Check factor freshness — returns stale, healthy, and missing factors."""
    from monitoring.factor_staleness import check_factor_staleness
    return await check_factor_staleness()


@app.get("/api/monitoring/polygon-health")
async def polygon_health_endpoint():
    """Check Polygon.io API health from rolling call window."""
    from monitoring.polygon_health import get_polygon_health
    return get_polygon_health()


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
    if timeframe_lower not in {"daily", "weekly", "monthly", "cyclical"}:
        raise HTTPException(status_code=404, detail="Unknown bias timeframe")

    from database.redis_client import get_bias
    
    bias = await get_bias(timeframe.upper())
    if bias:
        return bias
    else:
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
from api.positions import router as positions_router
from api.scanner import router as scanner_router
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
from api.sectors import router as sectors_router
from api.flow_summary import router as flow_summary_router
from api.flow_ingestion import router as flow_ingestion_router

app.include_router(webhook_router, prefix="/webhook", tags=["webhooks"])
app.include_router(circuit_breaker_router, prefix="/webhook", tags=["circuit-breaker"])
app.include_router(whale_webhook_router, prefix="/webhook", tags=["whale"])
app.include_router(footprint_webhook_router, prefix="/webhook", tags=["webhooks"])
app.include_router(positions_router, prefix="/api", tags=["positions"])
app.include_router(scanner_router, prefix="/api", tags=["scanner"])
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
app.include_router(sectors_router, prefix="/api", tags=["sectors"])
app.include_router(flow_summary_router, prefix="/api", tags=["flow-summary"])
app.include_router(flow_ingestion_router, prefix="/api", tags=["uw-flow"])

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
    @app.get("/app", response_class=FileResponse)
    async def serve_frontend():
        """Serve the frontend dashboard"""
        return FileResponse(os.path.join(frontend_path, "index.html"))

    @app.get("/app/{mode}", response_class=FileResponse)
    async def serve_frontend_mode(mode: str):
        """Serve frontend for SPA client-side routes (/app/crypto, /app/hub)"""
        return FileResponse(os.path.join(frontend_path, "index.html"))
    
    @app.get("/knowledgebase", response_class=FileResponse)
    async def serve_knowledgebase():
        """Serve the knowledgebase page"""
        return FileResponse(os.path.join(frontend_path, "knowledgebase.html"))
    
    @app.get("/app.js", response_class=FileResponse)
    async def serve_app_js():
        return FileResponse(os.path.join(frontend_path, "app.js"))

    @app.get("/analytics.js", response_class=FileResponse)
    async def serve_analytics_js():
        return FileResponse(os.path.join(frontend_path, "analytics.js"))

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
