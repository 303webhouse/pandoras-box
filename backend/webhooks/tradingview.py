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
        if "exhaustion" in strategy_lower:
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
    
    # 🔥 CHECK MACRO CONFLUENCE FOR BTC
    if "btc" in alert.ticker.lower():
        logger.info(f"🔍 BTC Exhaustion detected - checking macro confluence...")
        signal_data = await upgrade_signal_if_confluence(signal_data)
        
        if signal_data.get("signal_type") in ["APIS_CALL", "KODIAK_CALL"]:
            logger.info(f"⭐ BTC signal upgraded to {signal_data['signal_type']}!")
    
    # Apply proper scoring
    signal_data = await apply_signal_scoring(signal_data)
    
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


async def apply_signal_scoring(signal_data: dict) -> dict:
    """
    Apply the Trade Ideas Scorer to a signal.
    Gets current bias and calculates proper score, alignment, and triggering factors.
    """
    try:
        # Get current bias for scoring
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
        
        # Set confidence based on score
        if score >= 75:
            signal_data["confidence"] = "HIGH"
        elif score >= 55:
            signal_data["confidence"] = "MEDIUM"
        else:
            signal_data["confidence"] = "LOW"
        
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


@router.post("/test")
async def test_webhook(request: Request):
    """Test endpoint to verify webhook is working"""
    body = await request.json()
    logger.info(f"Test webhook received: {body}")
    return {"status": "test_success", "received": body}
