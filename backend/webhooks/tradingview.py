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
import logging

from strategies.triple_line import validate_triple_line_signal
from strategies.exhaustion import validate_exhaustion_signal, classify_exhaustion_signal
from bias_filters.tick_breadth import check_bias_alignment
from bias_filters.macro_confluence import upgrade_signal_if_confluence
from scoring.rank_trades import classify_signal
from scoring.trade_ideas_scorer import calculate_signal_score, get_score_tier
from database.redis_client import cache_signal
from database.postgres_client import log_signal, update_signal_with_score
from websocket.broadcaster import manager
from scheduler.bias_scheduler import get_bias_status
from utils.bias_snapshot import get_bias_snapshot

logger = logging.getLogger(__name__)

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


class TradingViewAlert(BaseModel):
    """Flexible payload from TradingView webhook - supports multiple strategies"""
    ticker: str
    strategy: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
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


@router.post("/tradingview")
async def receive_tradingview_alert(alert: TradingViewAlert):
    """
    Receive and process TradingView webhook
    Routes to appropriate strategy handler based on strategy field
    """
    start_time = datetime.now()
    strategy_lower = alert.strategy.lower()
    
    logger.info(f"📨 Webhook received: {alert.ticker} {alert.direction} ({alert.strategy})")
    
    try:
        # Route to appropriate strategy handler
        # Scout signals first (early warning, not full trade signals)
        if "scout" in strategy_lower:
            return await process_scout_signal(alert, start_time)
        elif "exhaustion" in strategy_lower:
            return await process_exhaustion_signal(alert, start_time)
        elif "sniper" in strategy_lower:
            return await process_sniper_signal(alert, start_time)
        elif "triple" in strategy_lower or "line" in strategy_lower:
            return await process_triple_line_signal(alert, start_time)
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
    signal_id = f"SCOUT_{alert.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    signal_data = {
        "signal_id": signal_id,
        "timestamp": alert.timestamp or datetime.now().isoformat(),
        "ticker": alert.ticker,
        "strategy": "Scout",
        "direction": alert.direction,
        "signal_type": "SCOUT_ALERT",  # Special type for UI differentiation
        "entry_price": alert.entry_price,
        "stop_loss": None,  # Scout doesn't provide SL/TP
        "target_1": None,
        "target_2": None,
        "risk_reward": None,
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

    signal_data = await attach_bias_snapshot(signal_data)

    # Cache with shorter TTL (30 mins instead of 1 hour)
    await cache_signal(signal_id, signal_data, ttl=1800)

    # Log to database
    await log_signal(signal_data)

    # Broadcast to UI - use dedicated scout broadcast (no priority threshold)
    await manager.broadcast({
        "type": "SCOUT_ALERT",
        "data": signal_data
    })

    elapsed = (datetime.now() - start_time).total_seconds() * 1000
    logger.info(f"⚠️ Scout alert: {alert.ticker} {alert.direction} (RSI: {alert.rsi}, RVOL: {alert.rvol}) in {elapsed:.1f}ms")

    return {
        "status": "success",
        "signal_id": signal_id,
        "signal_type": "SCOUT_ALERT",
        "message": "Early warning - not a trade signal",
        "processing_time_ms": round(elapsed, 1)
    }


async def process_exhaustion_signal(alert: TradingViewAlert, start_time: datetime):
    """Process Exhaustion strategy signals with BTC macro confluence check"""
    
    # Validate exhaustion signal
    is_valid, validation_details = await validate_exhaustion_signal(alert.dict())
    
    if not is_valid:
        logger.warning(f"Invalid exhaustion signal: {alert.ticker} - {validation_details}")
        return {"status": "rejected", "reason": validation_details}
    
    # Classify the signal
    classification = classify_exhaustion_signal(alert.direction, alert.entry_price)
    
    # Calculate risk/reward
    risk_reward = calculate_risk_reward(alert)
    
    # Build signal data
    signal_id = f"{alert.ticker}_{alert.direction}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
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
        "risk_reward": risk_reward,
        "timeframe": alert.timeframe,
        "trade_type": "REVERSAL",
        "asset_class": "CRYPTO" if is_crypto_ticker(alert.ticker) else "EQUITY",
        "status": "ACTIVE",
        "rsi": alert.rsi,
        "adx": alert.adx
    }
    
    # Apply proper scoring (this will also upgrade to APIS/KODIAK if high score)
    signal_data = await apply_signal_scoring(signal_data)
    signal_data = await attach_bias_snapshot(signal_data)
    
    # Cache, log, and broadcast
    await cache_signal(signal_id, signal_data, ttl=3600)
    await log_signal(signal_data)
    await manager.broadcast_signal_smart(signal_data, priority_threshold=75.0)
    
    elapsed = (datetime.now() - start_time).total_seconds() * 1000
    logger.info(f"✅ Exhaustion signal processed: {alert.ticker} {signal_data['signal_type']} in {elapsed:.1f}ms")
    
    return {
        "status": "success",
        "signal_id": signal_id,
        "signal_type": signal_data["signal_type"],
        "macro_confluence": signal_data.get("macro_confluence"),
        "processing_time_ms": round(elapsed, 1)
    }


async def process_sniper_signal(alert: TradingViewAlert, start_time: datetime):
    """Process Sniper (Ursa/Taurus) signals"""
    
    # Calculate risk/reward
    risk_reward = calculate_risk_reward(alert)
    
    # Determine signal type based on direction
    if alert.direction.upper() in ["LONG", "BUY"]:
        signal_type = "BULLISH_TRADE"
    else:
        signal_type = "BEAR_CALL"
    
    # Build signal data
    signal_id = f"{alert.ticker}_{alert.direction}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
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
        "risk_reward": risk_reward,
        "timeframe": alert.timeframe,
        "trade_type": "CONTINUATION",
        "asset_class": "CRYPTO" if is_crypto_ticker(alert.ticker) else "EQUITY",
        "status": "ACTIVE",
        "rsi": alert.rsi,
        "adx": alert.adx
    }
    
    # Apply proper scoring
    signal_data = await apply_signal_scoring(signal_data)
    signal_data = await attach_bias_snapshot(signal_data)
    
    # Cache, log, and broadcast
    await cache_signal(signal_id, signal_data, ttl=3600)
    await log_signal(signal_data)
    await manager.broadcast_signal_smart(signal_data, priority_threshold=75.0)
    
    elapsed = (datetime.now() - start_time).total_seconds() * 1000
    logger.info(f"✅ Sniper signal processed: {alert.ticker} {signal_type} in {elapsed:.1f}ms")
    
    return {
        "status": "success",
        "signal_id": signal_id,
        "signal_type": signal_type,
        "processing_time_ms": round(elapsed, 1)
    }


async def process_triple_line_signal(alert: TradingViewAlert, start_time: datetime):
    """Process Triple Line strategy signals (original handler)"""
    
    # Validate strategy setup
    is_valid, validation_details = await validate_triple_line_signal(alert.dict())
    
    if not is_valid:
        logger.warning(f"Invalid signal rejected: {alert.ticker} - {validation_details}")
        return {"status": "rejected", "reason": validation_details}
    
    # Check bias alignment
    bias_level, bias_aligned = await check_bias_alignment(
        alert.direction,
        alert.timeframe
    )
    
    # Classify signal strength
    signal_type = classify_signal(
        direction=alert.direction,
        bias_level=bias_level,
        bias_aligned=bias_aligned,
        adx=alert.adx or 25,
        line_separation=alert.line_separation or 10
    )
    
    # Calculate risk/reward
    risk_reward = calculate_risk_reward(alert)
    
    # Build signal data
    signal_id = f"{alert.ticker}_{alert.direction}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    signal_data = {
        "signal_id": signal_id,
        "timestamp": alert.timestamp or datetime.now().isoformat(),
        "ticker": alert.ticker,
        "strategy": "Triple Line Trend Retracement",
        "direction": alert.direction,
        "signal_type": signal_type,
        "entry_price": alert.entry_price,
        "stop_loss": alert.stop_loss,
        "target_1": alert.target_1,
        "target_2": alert.target_2,
        "risk_reward": risk_reward,
        "timeframe": alert.timeframe,
        "bias_level": bias_level,
        "adx": alert.adx,
        "rsi": alert.rsi,
        "line_separation": alert.line_separation,
        "asset_class": "CRYPTO" if is_crypto_ticker(alert.ticker) else "EQUITY",
        "status": "ACTIVE"
    }
    
    # Apply proper scoring
    signal_data = await apply_signal_scoring(signal_data)
    signal_data = await attach_bias_snapshot(signal_data)
    
    # Cache, log, and broadcast
    await cache_signal(signal_id, signal_data, ttl=3600)
    await log_signal(signal_data)
    await manager.broadcast_signal_smart(signal_data, priority_threshold=75.0)
    
    elapsed = (datetime.now() - start_time).total_seconds() * 1000
    logger.info(f"✅ Signal processed: {alert.ticker} {signal_type} in {elapsed:.1f}ms")
    
    return {
        "status": "success",
        "signal_id": signal_id,
        "signal_type": signal_type,
        "processing_time_ms": round(elapsed, 1)
    }


async def process_generic_signal(alert: TradingViewAlert, start_time: datetime):
    """Process signals from unknown/custom strategies"""
    
    risk_reward = calculate_risk_reward(alert)
    
    # Default signal type based on direction
    if alert.direction.upper() in ["LONG", "BUY"]:
        signal_type = "BULLISH_TRADE"
    else:
        signal_type = "BEAR_CALL"
    
    signal_id = f"{alert.ticker}_{alert.direction}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
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
        "risk_reward": risk_reward,
        "timeframe": alert.timeframe,
        "asset_class": "CRYPTO" if is_crypto_ticker(alert.ticker) else "EQUITY",
        "status": "ACTIVE",
        "rsi": alert.rsi,
        "adx": alert.adx
    }
    
    # Apply proper scoring
    signal_data = await apply_signal_scoring(signal_data)
    signal_data = await attach_bias_snapshot(signal_data)
    
    await cache_signal(signal_id, signal_data, ttl=3600)
    await log_signal(signal_data)
    await manager.broadcast_signal_smart(signal_data, priority_threshold=75.0)
    
    elapsed = (datetime.now() - start_time).total_seconds() * 1000
    logger.info(f"✅ Generic signal processed: {alert.ticker} {signal_type} in {elapsed:.1f}ms")
    
    return {
        "status": "success",
        "signal_id": signal_id,
        "signal_type": signal_type,
        "processing_time_ms": round(elapsed, 1)
    }


def calculate_risk_reward(alert: TradingViewAlert) -> float:
    """Calculate risk/reward ratio from alert data"""
    if not alert.stop_loss or not alert.target_1:
        return 0
    
    if alert.direction.upper() in ["LONG", "BUY"]:
        risk = alert.entry_price - alert.stop_loss
        reward = alert.target_1 - alert.entry_price
    else:
        risk = alert.stop_loss - alert.entry_price
        reward = alert.entry_price - alert.target_1
    
    return round(reward / risk, 2) if risk > 0 else 0


async def attach_bias_snapshot(signal_data: dict) -> dict:
    """Attach bias indicator snapshot at signal time for archiving."""
    if not signal_data.get("bias_at_signal"):
        signal_data["bias_at_signal"] = await get_bias_snapshot()
    return signal_data


async def apply_signal_scoring(signal_data: dict) -> dict:
    """
    Apply the Trade Ideas Scorer to a signal.
    Gets current bias and calculates proper score, alignment, and triggering factors.
    
    High-scoring signals get upgraded to special signal types:
    - APIS_CALL: Strong LONG signal (score >= 75)
    - KODIAK_CALL: Strong SHORT signal (score >= 75)
    """
    try:
        # Primary: use composite engine score for bias alignment
        composite_score = None
        try:
            from bias_engine.composite import get_cached_composite
            cached = await get_cached_composite()
            if cached:
                composite_score = cached.composite_score
        except Exception as comp_err:
            logger.warning(f"Composite bias unavailable, falling back to old system: {comp_err}")
        
        # Build bias data — prefer composite, fall back to old voting system
        if composite_score is not None:
            current_bias = {"composite_score": composite_score}
        else:
            bias_status = get_bias_status()
            current_bias = {
                "daily": bias_status.get("daily", {}),
                "weekly": bias_status.get("weekly", {}),
                "cyclical": bias_status.get("cyclical", {})
            }
        
        # Calculate score using the scorer
        score, bias_alignment, triggering_factors = calculate_signal_score(signal_data, current_bias)
        
        # Update signal data
        signal_data["score"] = score
        signal_data["bias_alignment"] = bias_alignment
        signal_data["triggering_factors"] = triggering_factors
        signal_data["scoreTier"] = get_score_tier(score)
        
        # Set confidence and potentially upgrade signal type based on score
        direction = signal_data.get("direction", "").upper()
        
        if score >= 85:
            signal_data["confidence"] = "HIGH"
            signal_data["priority"] = "HIGH"
            # Upgrade to APIS/KODIAK for strongest signals (rare, 85+ only)
            if direction in ["LONG", "BUY"]:
                signal_data["signal_type"] = "APIS_CALL"
                logger.info(f"APIS CALL: {signal_data.get('ticker')} (score: {score})")
            elif direction in ["SHORT", "SELL"]:
                signal_data["signal_type"] = "KODIAK_CALL"
                logger.info(f"KODIAK CALL: {signal_data.get('ticker')} (score: {score})")
        elif score >= 75:
            signal_data["confidence"] = "HIGH"
            signal_data["priority"] = "HIGH"
        elif score >= 55:
            signal_data["confidence"] = "MEDIUM"
            signal_data["priority"] = "MEDIUM"
        else:
            signal_data["confidence"] = "LOW"
            signal_data["priority"] = "LOW"
        
        logger.info(f"📊 Signal scored: {signal_data.get('ticker')} = {score} ({bias_alignment})")
        
        # Update score in database
        try:
            await update_signal_with_score(
                signal_data.get("signal_id"),
                score,
                bias_alignment,
                triggering_factors
            )
        except Exception as db_err:
            logger.warning(f"Failed to update score in DB: {db_err}")
        
        return signal_data
        
    except Exception as e:
        logger.warning(f"Error applying signal scoring: {e}")
        # Return signal with defaults if scoring fails
        signal_data["score"] = 50
        signal_data["bias_alignment"] = "NEUTRAL"
        signal_data["confidence"] = "MEDIUM"
        return signal_data


class TickDataPayload(BaseModel):
    """Payload for TICK range data from TradingView"""
    tick_high: float  # Daily/session TICK high (e.g., +1200)
    tick_low: float   # Daily/session TICK low (e.g., -800)
    tick_close: Optional[float] = None  # Latest TICK close
    tick_avg: Optional[float] = None    # Session average TICK
    date: Optional[str] = None  # Optional date (YYYY-MM-DD), defaults to today


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
    from bias_filters.tick_breadth import store_tick_data, compute_score as compute_tick_score
    
    logger.info(f"📊 TICK webhook received: high={payload.tick_high}, low={payload.tick_low}, close={payload.tick_close}, avg={payload.tick_avg}")
    
    result = await store_tick_data(
        tick_high=payload.tick_high,
        tick_low=payload.tick_low,
        date=payload.date,
        tick_close=payload.tick_close,
        tick_avg=payload.tick_avg,
    )
    
    # Auto-score tick_breadth and feed into composite bias engine
    try:
        tick_data = {
            "tick_high": payload.tick_high,
            "tick_low": payload.tick_low,
            "tick_close": payload.tick_close,
            "tick_avg": payload.tick_avg,
        }
        reading = await compute_tick_score(tick_data)
        if reading:
            from bias_engine.composite import store_factor_reading, compute_composite
            await store_factor_reading(reading)
            composite = await compute_composite()
            logger.info(
                f"📊 TICK factor scored: {reading.score:+.2f} ({reading.signal}) → "
                f"composite {composite.bias_level} ({composite.composite_score:+.2f})"
            )
            result["factor_score"] = reading.score
            result["factor_signal"] = reading.signal
            result["composite_bias"] = composite.bias_level
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


class PCRPayload(BaseModel):
    """Payload for Put/Call Ratio data from TradingView"""
    pcr: float  # CBOE equity put/call ratio (e.g., 0.85)
    date: Optional[str] = None  # Optional date (YYYY-MM-DD), defaults to today


@router.post("/pcr")
async def receive_pcr_data(payload: PCRPayload):
    """
    Receive CBOE Put/Call Ratio data from TradingView webhook.
    
    TradingView Alert Setup:
    - Symbol: $CPCE (CBOE equity put/call ratio)
    - Timeframe: Daily
    - Condition: Once per bar close
    - Webhook URL: https://your-app.railway.app/webhook/pcr
    - Message (JSON): {"pcr": {{close}}}
    """
    from bias_filters.put_call_ratio import store_pcr_data, compute_score as compute_pcr_score
    
    logger.info(f"📊 PCR webhook received: {payload.pcr:.3f}")
    
    result = await store_pcr_data(pcr_value=payload.pcr, date=payload.date)
    
    # Auto-score put_call_ratio and feed into composite bias engine
    try:
        pcr_data = {"pcr": payload.pcr}
        reading = await compute_pcr_score(pcr_data)
        if reading:
            from bias_engine.composite import store_factor_reading, compute_composite
            await store_factor_reading(reading)
            composite = await compute_composite()
            logger.info(
                f"📊 PCR factor scored: {reading.score:+.2f} ({reading.signal}) → "
                f"composite {composite.bias_level} ({composite.composite_score:+.2f})"
            )
            result["factor_score"] = reading.score
            result["factor_signal"] = reading.signal
            result["composite_bias"] = composite.bias_level
        else:
            logger.warning("📊 PCR factor scoring returned None")
    except Exception as e:
        logger.error(f"📊 PCR factor scoring failed (data still stored): {e}")
    
    return result


@router.get("/pcr/status")
async def get_pcr_status():
    """Get current Put/Call Ratio data and status"""
    from bias_filters.put_call_ratio import compute_score
    reading = await compute_score()
    if reading:
        return {
            "status": "ok",
            "pcr": reading.raw_data.get("pcr"),
            "score": reading.score,
            "signal": reading.signal,
            "detail": reading.detail,
        }
    return {"status": "no_data", "message": "No PCR data available"}


@router.post("/test")
async def test_webhook(request: Request):
    """Test endpoint to verify webhook is working"""
    body = await request.json()
    logger.info(f"Test webhook received: {body}")
    return {"status": "test_success", "received": body}
