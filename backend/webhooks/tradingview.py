"""
TradingView Webhook Endpoint
Receives real-time alerts from TradingView when strategy conditions hit

Supports multiple strategies:
- Triple Line
- Sniper (Ursa/Taurus)
- Exhaustion (with BTC macro confluence)
"""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
import asyncio
import hashlib
import logging

import os

from strategies.exhaustion import validate_exhaustion_signal, classify_exhaustion_signal
from signals.pipeline import process_signal_unified

logger = logging.getLogger(__name__)

WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET") or ""

router = APIRouter()

# Top 20 crypto by market cap (+ common variations for TradingView)
CRYPTO_TICKERS = {
    # Base tickers
    'BTC', 'ETH', 'USDT', 'BNB', 'SOL', 'XRP', 'USDC', 'ADA', 'AVAX', 'DOGE',
    'DOT', 'TRX', 'LINK', 'MATIC', 'POL', 'SHIB', 'TON', 'LTC', 'BCH', 'XLM', 'UNI',
    # TradingView USD pairs
    'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'ADAUSD', 'AVAXUSD', 'DOGEUSD',
    'DOTUSD', 'LINKUSD', 'MATICUSD', 'LTCUSD', 'BCHUSD', 'XLMUSD', 'UNIUSD',
    'BNBUSD', 'TRXUSD', 'SHIBUSD', 'TONUSD',
    # TradingView USDT pairs  
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT', 'AVAXUSDT', 'DOGEUSDT',
    'DOTUSDT', 'LINKUSDT', 'MATICUSDT', 'LTCUSDT', 'BCHUSDT', 'XLMUSDT', 'UNIUSDT',
    'BNBUSDT', 'TRXUSDT', 'SHIBUSDT', 'TONUSDT',
    # Binance/Bybit perpetuals
    'BTCUSDTPERP', 'ETHUSDTPERP', 'BTCPERP', 'ETHPERP'
}


def is_crypto_ticker(ticker: str) -> bool:
    """Check if a ticker is a cryptocurrency"""
    return ticker.upper() in CRYPTO_TICKERS


async def _recompute_composite_background(factor_name: str) -> None:
    """
    Background task: recompute composite bias after a factor update.
    Runs AFTER the webhook response is sent so TradingView doesn't timeout.
    """
    try:
        from bias_engine.composite import compute_composite
        composite = await compute_composite()
        logger.info(
            "🔄 Background composite recomputed after %s: %s (%+.2f)",
            factor_name, composite.bias_level, composite.composite_score,
        )
    except Exception as e:
        logger.error("🔄 Background composite recomputation failed after %s: %s", factor_name, e)


class TradingViewAlert(BaseModel):
    """Flexible payload from TradingView webhook - supports multiple strategies"""
    ticker: str
    strategy: str
    direction: str  # "LONG" or "SHORT"
    entry_price: Optional[float] = 0  # Optional: Scout signals don't send entry_price
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    # Optional fields for specific strategies
    adx: Optional[float] = None
    line_separation: Optional[float] = None
    rsi: Optional[float] = None
    rvol: Optional[float] = None
    timeframe: Optional[str] = "1H"
    timestamp: Optional[str] = None
    # Scout Sniper alternate field names (PineScript sends entry/stop/tp1/tp2)
    entry: Optional[float] = None
    stop: Optional[float] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    price: Optional[float] = None
    tier: Optional[str] = None
    status: Optional[str] = None  # TRADEABLE / IGNORE
    sma_regime: Optional[str] = None
    plan_printed: Optional[bool] = None
    score: Optional[float] = None  # Pine signal quality score (0-6)
    # Absorption Wall fields (order flow data)
    signal_type: Optional[str] = None
    delta_ratio: Optional[float] = None
    buy_pct: Optional[float] = None
    buy_vol: Optional[float] = None
    sell_vol: Optional[float] = None
    total_vol: Optional[float] = None
    secret: Optional[str] = None


@router.post("/tradingview")
async def receive_tradingview_alert(alert: TradingViewAlert):
    """
    Receive and process TradingView webhook
    Routes to appropriate strategy handler based on strategy field
    """
    # Webhook secret validation
    if WEBHOOK_SECRET:
        if (alert.secret or "") != WEBHOOK_SECRET:
            logger.warning("Rejected TradingView webhook — invalid secret from %s", alert.ticker)
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # Dedup: reject duplicate webhooks within 60s window
    dedup_raw = f"{alert.ticker}:{alert.strategy}:{alert.direction}:{alert.timeframe}"
    dedup_hash = hashlib.md5(dedup_raw.encode()).hexdigest()[:16]
    dedup_key = f"webhook:dedup:tv:{dedup_hash}"
    try:
        from database.redis_client import get_redis_client
        _rc = await get_redis_client()
        if _rc and await _rc.get(dedup_key):
            logger.info("Webhook dedup: skipping duplicate %s %s %s", alert.ticker, alert.strategy, alert.direction)
            return {"status": "duplicate", "detail": "duplicate webhook within 60s window"}
        if _rc:
            await _rc.set(dedup_key, "1", ex=60)
    except Exception:
        pass  # dedup is best-effort, don't block signal processing

    start_time = datetime.now()
    strategy_lower = alert.strategy.lower()

    logger.info(f"📨 Webhook received: {alert.ticker} {alert.direction} ({alert.strategy})")
    
    try:
        # Route to appropriate strategy handler
        # Scout signals first (early warning, not full trade signals)
        if "scout" in strategy_lower:
            return await process_scout_signal(alert, start_time)
        elif "holy_grail" in strategy_lower or "holygrail" in strategy_lower:
            return await process_holy_grail_signal(alert, start_time)
        elif "exhaustion" in strategy_lower:
            return await process_exhaustion_signal(alert, start_time)
        elif "sniper" in strategy_lower:
            return await process_sniper_signal(alert, start_time)
        elif "absorption" in strategy_lower or "wall" in strategy_lower:
            return await process_absorption_signal(alert, start_time)
        else:
            # Generic signal processing
            return await process_generic_signal(alert, start_time)
            
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def process_scout_signal(alert: TradingViewAlert, start_time: datetime):
    """
    Process Scout signals - early warning indicators from 15m charts

    These are NOT full trade signals - they're alerts that a reversal MAY be starting.
    They get a special signal_type and lower priority so they show differently in the UI.
    """

    # Build signal data with Scout-specific fields
    signal_id = f"SCOUT_{alert.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

    signal_data = {
        "signal_id": signal_id,
        "timestamp": alert.timestamp or datetime.now().isoformat(),
        "ticker": alert.ticker,
        "strategy": "Scout",
        "direction": alert.direction,
        "signal_type": "SCOUT_ALERT",  # Special type for UI differentiation
        "entry_price": alert.entry or alert.price or alert.entry_price or 0,
        "stop_loss": alert.stop or alert.stop_loss,
        "target_1": alert.tp1 or alert.target_1,
        "target_2": alert.tp2 or alert.target_2,
        "risk_reward": None,  # calculated below
        "timeframe": alert.timeframe or "15",
        "trade_type": "EARLY_WARNING",
        "asset_class": "CRYPTO" if is_crypto_ticker(alert.ticker) else "EQUITY",
        "status": "ACTIVE",
        "rsi": alert.rsi,
        "rvol": alert.rvol,
        # Scout-specific: lower priority, shorter TTL
        "priority": "LOW",
        "confidence": "SCOUT",  # Special confidence level
        "score": 40,  # Base score - scouts don't get full scoring
        "bias_alignment": "NEUTRAL",
        "note": "Early warning - confirm with 1H Sniper before entry"
    }

    # Calculate R:R if we have levels
    ep = signal_data["entry_price"]
    sl = signal_data["stop_loss"]
    t1 = signal_data["target_1"]
    if ep and sl and t1:
        is_long = (alert.direction or "").upper() in {"LONG", "BUY"}
        risk = (ep - sl) if is_long else (sl - ep)
        if risk > 0:
            reward = (t1 - ep) if is_long else (ep - t1)
            signal_data["risk_reward"] = round(reward / risk, 2) if reward > 0 else 0

    # Fire-and-forget: return 200 immediately, process in background
    asyncio.ensure_future(process_signal_unified(
        signal_data,
        source="tradingview",
        skip_scoring=True,
        cache_ttl=1800,
        priority_threshold=0,  # Always broadcast scouts
    ))

    logger.info(
        f"⚠️ Scout alert accepted: {alert.ticker} {alert.direction} "
        f"(RSI: {alert.rsi}, RVOL: {alert.rvol}, "
        f"entry: {signal_data.get('entry_price')}, stop: {signal_data.get('stop_loss')}, tp1: {signal_data.get('target_1')})"
    )

    return {
        "status": "accepted",
        "signal_id": signal_id,
        "signal_type": "SCOUT_ALERT",
        "message": "Early warning - not a trade signal",
    }


async def process_holy_grail_signal(alert: TradingViewAlert, start_time: datetime):
    """
    Process Holy Grail Pullback Continuation signals (Raschke-style).

    These are continuation entries: strong trend (ADX >= 25), pullback to 20 EMA,
    confirmation candle back in trend direction. Full committee review signals.

    Timeframe affects signal type:
    - 1H  -> HOLY_GRAIL_1H  (higher base score — cleaner pullbacks)
    - 15m -> HOLY_GRAIL_15M (lower base score — noisier)
    """

    # Determine signal type based on timeframe
    tf = (alert.timeframe or "15").upper().replace("M", "").replace("MIN", "")
    if tf in ("60", "1H", "H", "1"):
        signal_type_suffix = "1H"
    else:
        signal_type_suffix = "15M"

    signal_type = f"HOLY_GRAIL_{signal_type_suffix}"

    # Calculate risk/reward
    rr = calculate_risk_reward(alert)

    # Build signal data
    signal_id = f"HG_{alert.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

    signal_data = {
        "signal_id": signal_id,
        "timestamp": alert.timestamp or datetime.now().isoformat(),
        "ticker": alert.ticker,
        "strategy": "Holy_Grail",
        "direction": alert.direction,
        "signal_type": signal_type,
        "entry_price": alert.entry_price,
        "stop_loss": alert.stop_loss,
        "target_1": alert.target_1,
        "target_2": alert.target_2,
        "risk_reward": rr["primary"],
        "risk_reward_t1": rr["t1_rr"],
        "risk_reward_t2": rr["t2_rr"],
        "timeframe": alert.timeframe,
        "trade_type": "CONTINUATION",
        "asset_class": "CRYPTO" if is_crypto_ticker(alert.ticker) else "EQUITY",
        "status": "ACTIVE",
        "rsi": alert.rsi,
        "adx": alert.adx,
        "rvol": alert.rvol,  # Carries DI spread from PineScript
    }

    # Fire-and-forget: return 200 immediately, process in background
    asyncio.ensure_future(process_signal_unified(signal_data, source="tradingview"))

    logger.info(f"📨 Holy Grail accepted: {alert.ticker} {signal_type} ({alert.timeframe})")

    return {
        "status": "accepted",
        "signal_id": signal_id,
        "signal_type": signal_type,
    }


async def process_exhaustion_signal(alert: TradingViewAlert, start_time: datetime):
    """Process Exhaustion strategy signals with BTC macro confluence check"""
    
    # Validate exhaustion signal (keep sync — fast, no I/O)
    is_valid, validation_details = await validate_exhaustion_signal(alert.dict())
    
    if not is_valid:
        logger.warning(f"Invalid exhaustion signal: {alert.ticker} - {validation_details}")
        return {"status": "rejected", "reason": validation_details}
    
    # Classify the signal
    classification = classify_exhaustion_signal(alert.direction, alert.entry_price)

    # Suppress EXHAUSTION_BULL in strong bearish regime (< -0.3)
    # Signal still persists (useful as short profit-taking awareness) but tagged IGNORE
    suppressed = False
    if classification["signal_type"] == "EXHAUSTION_BULL":
        try:
            from bias_engine.composite import get_cached_composite
            cached = await get_cached_composite()
            if cached and cached.composite_score < -0.3:
                suppressed = True
                logger.info(
                    f"🔇 Exhaustion BULL suppressed: {alert.ticker} "
                    f"(bias={cached.composite_score:.2f})"
                )
        except Exception:
            pass

    # Calculate risk/reward
    rr = calculate_risk_reward(alert)
    
    # Build signal data
    signal_id = f"{alert.ticker}_{alert.direction}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    
    signal_data = {
        "signal_id": signal_id,
        "timestamp": alert.timestamp or datetime.now().isoformat(),
        "ticker": alert.ticker,
        "strategy": "Exhaustion",
        "direction": alert.direction,
        "signal_type": classification["signal_type"],
        "entry_price": alert.entry_price,
        "stop_loss": alert.stop_loss,
        "target_1": alert.target_1,
        "target_2": alert.target_2,
        "risk_reward": rr["primary"],
        "risk_reward_t1": rr["t1_rr"],
        "risk_reward_t2": rr["t2_rr"],
        "timeframe": alert.timeframe,
        "trade_type": "REVERSAL",
        "asset_class": "CRYPTO" if is_crypto_ticker(alert.ticker) else "EQUITY",
        "status": "ACTIVE",
        "rsi": alert.rsi,
        "adx": alert.adx
    }

    if suppressed:
        signal_data["status"] = "IGNORE"
        signal_data["note"] = "Exhaustion BULL suppressed — strong bearish bias. Use as short profit-taking indicator only."

    # Fire-and-forget: return 200 immediately, process in background
    asyncio.ensure_future(process_signal_unified(signal_data, source="tradingview"))

    logger.info(f"📨 Exhaustion accepted: {alert.ticker} {classification['signal_type']}")

    return {
        "status": "accepted",
        "signal_id": signal_id,
        "signal_type": classification["signal_type"],
    }


async def process_sniper_signal(alert: TradingViewAlert, start_time: datetime):
    """Process Sniper (Ursa/Taurus) signals"""
    
    # Calculate risk/reward
    rr = calculate_risk_reward(alert)
    
    # Determine signal type based on direction
    if alert.direction.upper() in ["LONG", "BUY"]:
        signal_type = "BULLISH_TRADE"
    else:
        signal_type = "BEAR_CALL"
    
    # Build signal data
    signal_id = f"{alert.ticker}_{alert.direction}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    
    signal_data = {
        "signal_id": signal_id,
        "timestamp": alert.timestamp or datetime.now().isoformat(),
        "ticker": alert.ticker,
        "strategy": "Sniper",
        "direction": alert.direction,
        "signal_type": signal_type,
        "entry_price": alert.entry_price,
        "stop_loss": alert.stop_loss,
        "target_1": alert.target_1,
        "target_2": alert.target_2,
        "risk_reward": rr["primary"],
        "risk_reward_t1": rr["t1_rr"],
        "risk_reward_t2": rr["t2_rr"],
        "timeframe": alert.timeframe,
        "trade_type": "CONTINUATION",
        "asset_class": "CRYPTO" if is_crypto_ticker(alert.ticker) else "EQUITY",
        "status": "ACTIVE",
        "rsi": alert.rsi,
        "adx": alert.adx
    }
    
    # Fire-and-forget: return 200 immediately, process in background
    asyncio.ensure_future(process_signal_unified(signal_data, source="tradingview"))

    logger.info(f"📨 Sniper accepted: {alert.ticker} {signal_type}")

    return {
        "status": "accepted",
        "signal_id": signal_id,
        "signal_type": signal_type,
    }


async def process_absorption_signal(alert: TradingViewAlert, start_time: datetime):
    """Process Absorption Wall signals with order flow context."""
    signal_id = f"WALL_{alert.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

    direction = (alert.direction or "").upper()
    signal_type = alert.signal_type or ("BULL_WALL" if direction in ["LONG", "BUY"] else "BEAR_WALL")

    signal_data = {
        "signal_id": signal_id,
        "timestamp": alert.timestamp or datetime.now().isoformat(),
        "ticker": alert.ticker,
        "strategy": "AbsorptionWall",
        "direction": alert.direction,
        "signal_type": signal_type,
        "entry_price": alert.entry_price,
        "timeframe": alert.timeframe,
        "trade_type": "ORDER_FLOW",
        "asset_class": "CRYPTO" if is_crypto_ticker(alert.ticker) else "EQUITY",
        "status": "ACTIVE",
        "rvol": alert.rvol,
        "delta_ratio": alert.delta_ratio,
        "buy_pct": alert.buy_pct,
    }

    asyncio.ensure_future(process_signal_unified(signal_data, source="tradingview"))

    logger.info("Absorption Wall accepted: %s %s (delta=%.4f)",
                alert.ticker, signal_type,
                alert.delta_ratio if alert.delta_ratio is not None else 0)

    return {"status": "accepted", "signal_id": signal_id, "signal_type": signal_type}


async def process_generic_signal(alert: TradingViewAlert, start_time: datetime):
    """Process signals from unknown/custom strategies"""
    
    rr = calculate_risk_reward(alert)
    
    # Default signal type based on direction
    if alert.direction.upper() in ["LONG", "BUY"]:
        signal_type = "BULLISH_TRADE"
    else:
        signal_type = "BEAR_CALL"
    
    signal_id = f"{alert.ticker}_{alert.direction}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    
    signal_data = {
        "signal_id": signal_id,
        "timestamp": alert.timestamp or datetime.now().isoformat(),
        "ticker": alert.ticker,
        "strategy": alert.strategy,
        "direction": alert.direction,
        "signal_type": signal_type,
        "entry_price": alert.entry_price,
        "stop_loss": alert.stop_loss,
        "target_1": alert.target_1,
        "target_2": alert.target_2,
        "risk_reward": rr["primary"],
        "risk_reward_t1": rr["t1_rr"],
        "risk_reward_t2": rr["t2_rr"],
        "timeframe": alert.timeframe,
        "asset_class": "CRYPTO" if is_crypto_ticker(alert.ticker) else "EQUITY",
        "status": "ACTIVE",
        "rsi": alert.rsi,
        "adx": alert.adx
    }
    
    # Fire-and-forget: return 200 immediately, process in background
    asyncio.ensure_future(process_signal_unified(signal_data, source="tradingview"))

    logger.info(f"📨 Generic signal accepted: {alert.ticker} {signal_type}")

    return {
        "status": "accepted",
        "signal_id": signal_id,
        "signal_type": signal_type,
    }


def calculate_risk_reward(alert: TradingViewAlert) -> dict:
    """
    Calculate risk/reward ratios from alert data.
    Returns dict with t1_rr and t2_rr (if target_2 exists).
    For backward compat, also sets 'primary' to t2_rr if available, else t1_rr.
    """
    if not alert.stop_loss or not alert.target_1:
        return {"t1_rr": 0, "t2_rr": 0, "primary": 0}

    direction = (alert.direction or "").upper()
    is_long = direction in {"LONG", "BUY"}

    risk = (alert.entry_price - alert.stop_loss) if is_long else (alert.stop_loss - alert.entry_price)
    if risk <= 0:
        logger.warning(
            "Invalid risk for %s %s (entry=%s stop=%s direction=%s)",
            alert.strategy, alert.ticker, alert.entry_price, alert.stop_loss, alert.direction,
        )
        return {"t1_rr": 0, "t2_rr": 0, "primary": 0}

    reward_t1 = (alert.target_1 - alert.entry_price) if is_long else (alert.entry_price - alert.target_1)
    t1_rr = round(reward_t1 / risk, 2) if reward_t1 > 0 else 0

    t2_rr = 0
    if alert.target_2:
        reward_t2 = (alert.target_2 - alert.entry_price) if is_long else (alert.entry_price - alert.target_2)
        t2_rr = round(reward_t2 / risk, 2) if reward_t2 > 0 else 0

    return {
        "t1_rr": t1_rr,
        "t2_rr": t2_rr,
        "primary": t2_rr if t2_rr > 0 else t1_rr,
    }


class BreadthPayload(BaseModel):
    """Payload for $UVOL/$DVOL breadth data from TradingView"""
    uvol: float  # NYSE Up Volume (e.g., 1500000000)
    dvol: float  # NYSE Down Volume (e.g., 800000000)
    secret: Optional[str] = None


@router.post("/breadth")
async def receive_breadth_data(payload: BreadthPayload):
    """
    Receive NYSE UVOL/DVOL breadth data from TradingView webhook.

    TradingView Alert Setup:
    - Create a custom indicator or use two alerts
    - Symbol: $UVOL (NYSE up volume) and $DVOL (NYSE down volume)
    - Condition: Every 15 minutes during market hours
    - Webhook URL: https://pandoras-box-production.up.railway.app/webhook/breadth
    - Message (JSON): {"uvol": {{close of $UVOL}}, "dvol": {{close of $DVOL}}}
    """
    from bias_filters.breadth_intraday import store_breadth_data, compute_score as compute_breadth_score

    if WEBHOOK_SECRET:
        if (payload.secret or "") != WEBHOOK_SECRET:
            logger.warning("Rejected breadth webhook — invalid secret")
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    logger.info("breadth webhook received: UVOL=%.0f, DVOL=%.0f", payload.uvol, payload.dvol)

    if payload.dvol <= 0:
        return {"status": "rejected", "reason": "DVOL must be positive"}

    result = await store_breadth_data(uvol=payload.uvol, dvol=payload.dvol)

    # Score the factor and store reading (fast — Redis only)
    try:
        reading = await compute_breadth_score()
        if reading:
            from bias_engine.composite import store_factor_reading
            await store_factor_reading(reading)
            result["factor_score"] = reading.score
            result["factor_signal"] = reading.signal
            # Defer heavy composite recomputation to background
            asyncio.ensure_future(_recompute_composite_background("breadth_intraday"))
        else:
            logger.warning("breadth factor scoring returned None")
    except Exception as e:
        logger.error("breadth factor scoring failed (data still stored): %s", e)

    return result


class TickDataPayload(BaseModel):
    """Payload for TICK range data from TradingView"""
    tick_high: float  # Daily/session TICK high (e.g., +1200)
    tick_low: float   # Daily/session TICK low (e.g., -800)
    tick_close: Optional[float] = None  # Latest TICK close
    tick_avg: Optional[float] = None    # Session average TICK
    date: Optional[str] = None  # Optional date (YYYY-MM-DD), defaults to today
    secret: Optional[str] = None


@router.post("/tick")
async def receive_tick_data(payload: TickDataPayload):
    """
    Receive NYSE TICK data from TradingView webhook (fires every 15 min during market hours).
    
    TradingView Alert Setup:
    - Symbol: $TICK (NYSE TICK index)
    - Condition: Every 15 minutes during market hours
    - Webhook URL: https://your-app.railway.app/webhook/tick
    - Message (JSON):
      {
        "tick_high": {{high}},
        "tick_low": {{low}},
        "tick_close": {{close}},
        "tick_avg": {{hl2}}
      }
    """
    if WEBHOOK_SECRET:
        if (payload.secret or "") != WEBHOOK_SECRET:
            logger.warning("Rejected TICK webhook — invalid secret")
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    from bias_filters.tick_breadth import store_tick_data, compute_score as compute_tick_score

    logger.info(f"📊 TICK webhook received: high={payload.tick_high}, low={payload.tick_low}, close={payload.tick_close}, avg={payload.tick_avg}")
    
    result = await store_tick_data(
        tick_high=payload.tick_high,
        tick_low=payload.tick_low,
        date=payload.date,
        tick_close=payload.tick_close,
        tick_avg=payload.tick_avg,
    )
    
    # Score the factor and store reading (fast — Redis only)
    try:
        reading = await compute_tick_score()
        if reading:
            from bias_engine.composite import store_factor_reading
            await store_factor_reading(reading)
            result["factor_score"] = reading.score
            result["factor_signal"] = reading.signal
            # Defer heavy composite recomputation to background
            asyncio.ensure_future(_recompute_composite_background("tick_breadth"))
        else:
            logger.warning("📊 TICK factor scoring returned None")
    except Exception as e:
        logger.error(f"📊 TICK factor scoring failed (data still stored): {e}")
    
    return result


@router.get("/tick/status")
async def get_tick_status_endpoint():
    """Get current TICK data and bias status"""
    from bias_filters.tick_breadth import get_tick_status
    return await get_tick_status()


class McClellanPayload(BaseModel):
    """Daily NYSE advancing/declining issues from TradingView"""
    advn: float  # NYSE advancing issues count
    decln: float  # NYSE declining issues count
    secret: Optional[str] = None


@router.post("/mcclellan")
async def receive_mcclellan_data(payload: McClellanPayload):
    """
    Receive daily NYSE ADVN/DECLN from TradingView webhook.
    Stores net advances in Redis history and recomputes McClellan Oscillator.
    Fires once per day at market close.
    """
    import json as _json
    from bias_filters.mcclellan_oscillator import (
        REDIS_KEY_MCCLELLAN_HISTORY,
        REDIS_MCCLELLAN_TTL,
        _compute_mcclellan,
        _score_mcclellan,
    )
    from bias_engine.composite import FactorReading, store_factor_reading
    from bias_engine.factor_utils import score_to_signal
    import pandas as pd

    if WEBHOOK_SECRET:
        if (payload.secret or "") != WEBHOOK_SECRET:
            logger.warning("Rejected McClellan webhook — invalid secret")
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    logger.info("McClellan webhook: ADVN=%.0f, DECLN=%.0f", payload.advn, payload.decln)

    if payload.advn <= 0 or payload.decln <= 0:
        return {"status": "rejected", "reason": "ADVN and DECLN must be positive"}

    net = payload.advn - payload.decln
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")

    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if not redis:
            return {"status": "error", "reason": "Redis unavailable"}

        # Store this day's reading
        entry = _json.dumps({
            "net": round(net, 0),
            "advn": round(payload.advn, 0),
            "decln": round(payload.decln, 0),
            "date": date_str,
        })
        ts = now.timestamp()
        await redis.zadd(REDIS_KEY_MCCLELLAN_HISTORY, {entry: ts})
        await redis.expire(REDIS_KEY_MCCLELLAN_HISTORY, REDIS_MCCLELLAN_TTL)

        # Trim to last 90 entries
        total = await redis.zcard(REDIS_KEY_MCCLELLAN_HISTORY)
        if total > 90:
            await redis.zremrangebyrank(REDIS_KEY_MCCLELLAN_HISTORY, 0, total - 91)

        # Read full history and compute McClellan
        entries = await redis.zrangebyscore(
            REDIS_KEY_MCCLELLAN_HISTORY, "-inf", "+inf"
        )
        net_values = [float(_json.loads(e)["net"]) for e in entries]

        if len(net_values) < 40:
            logger.info("McClellan: building baseline (%d/40 days)", len(net_values))
            return {
                "status": "accepted",
                "net_advances": net,
                "history_days": len(net_values),
                "message": f"Building baseline ({len(net_values)}/40 days)",
            }

        series = pd.Series(net_values)
        mcclellan = _compute_mcclellan(series)
        if mcclellan is None:
            return {"status": "error", "reason": "McClellan computation failed"}

        score = _score_mcclellan(mcclellan)

        reading = FactorReading(
            factor_id="mcclellan_oscillator",
            score=score,
            signal=score_to_signal(score),
            detail=f"McClellan Oscillator: {mcclellan:.1f} (from webhook, {len(net_values)} days)",
            timestamp=now,
            source="tradingview",
            raw_data={
                "mcclellan": round(mcclellan, 2),
                "net_advances": round(net, 0),
                "data_points": len(net_values),
            },
        )
        await store_factor_reading(reading)

        # Recompute composite in background
        asyncio.ensure_future(_recompute_composite_background("mcclellan_oscillator"))

        logger.info("McClellan webhook scored: %.1f (score=%+.2f, %d days)",
                     mcclellan, score, len(net_values))

        return {
            "status": "accepted",
            "net_advances": net,
            "mcclellan": round(mcclellan, 2),
            "score": score,
            "history_days": len(net_values),
        }

    except Exception as e:
        logger.error("McClellan webhook error: %s", e)
        return {"status": "error", "reason": str(e)}



@router.get("/outcomes/{signal_id}")
async def get_signal_outcome(signal_id: str):
    """
    Return outcome data for a signal. Used by VPS outcome matcher.
    Returns 404 if signal_id not found in signal_outcomes table.
    """
    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM signal_outcomes WHERE signal_id = $1",
            signal_id,
        )

    if row is None:
        raise HTTPException(status_code=404, detail="Signal outcome not found")

    # Serialize row: convert datetime/decimal types to JSON-safe values
    result = {}
    for key, value in dict(row).items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        elif hasattr(value, "as_tuple"):  # Decimal
            result[key] = float(value)
        else:
            result[key] = value
    return result


@router.post("/test")
async def test_webhook(request: Request):
    """Test endpoint to verify webhook is working"""
    body = await request.json()
    logger.info(f"Test webhook received: {body}")
    return {"status": "test_success", "received": body}
