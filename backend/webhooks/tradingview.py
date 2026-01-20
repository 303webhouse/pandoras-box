"""
TradingView Webhook Endpoint
Receives real-time alerts from TradingView when strategy conditions hit
"""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
import logging

from strategies.triple_line import validate_triple_line_signal
from bias_filters.tick_breadth import check_bias_alignment
from scoring.rank_trades import classify_signal
from database.redis_client import cache_signal
from database.postgres_client import log_signal
from websocket.broadcaster import manager

logger = logging.getLogger(__name__)

router = APIRouter()

class TradingViewAlert(BaseModel):
    """Expected payload from TradingView webhook"""
    ticker: str
    strategy: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: Optional[float] = None
    adx: float
    line_separation: float
    timeframe: str
    timestamp: Optional[str] = None

@router.post("/tradingview")
async def receive_tradingview_alert(alert: TradingViewAlert):
    """
    Receive and process TradingView webhook
    Target: <100ms total processing time
    """
    start_time = datetime.now()
    
    try:
        # 1. Validate strategy setup (10ms target)
        is_valid, validation_details = await validate_triple_line_signal(alert.dict())
        
        if not is_valid:
            logger.warning(f"Invalid signal rejected: {alert.ticker} - {validation_details}")
            return {"status": "rejected", "reason": validation_details}
        
        # 2. Check bias alignment (5ms target)
        bias_level, bias_aligned = await check_bias_alignment(
            alert.direction,
            alert.timeframe
        )
        
        # 3. Classify signal strength (APIS CALL, KODIAK CALL, etc.)
        signal_type = classify_signal(
            direction=alert.direction,
            bias_level=bias_level,
            bias_aligned=bias_aligned,
            adx=alert.adx,
            line_separation=alert.line_separation
        )
        
        # 4. Calculate risk/reward
        if alert.direction == "LONG":
            risk = alert.entry_price - alert.stop_loss
            reward = alert.target_1 - alert.entry_price
        else:
            risk = alert.stop_loss - alert.entry_price
            reward = alert.entry_price - alert.target_1
        
        risk_reward = round(reward / risk, 2) if risk > 0 else 0
        
        # 5. Build signal data structure
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
            "bias_level": bias_level,
            "bias_aligned": bias_aligned,
            "adx": alert.adx,
            "line_separation": alert.line_separation,
            "asset_class": "EQUITY" if alert.ticker not in ["BTC", "ETH", "SOL"] else "CRYPTO",
            "status": "ACTIVE"
        }
        
        # 6. Cache in Redis (2ms target)
        await cache_signal(signal_id, signal_data, ttl=3600)
        
        # 7. Log to PostgreSQL (async, non-blocking)
        await log_signal(signal_data)
        
        # 8. Broadcast to all connected devices (3ms target)
        await manager.broadcast_signal(signal_data)
        
        # Calculate total processing time
        elapsed = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(f"✅ Signal processed: {alert.ticker} {signal_type} in {elapsed:.1f}ms")
        
        return {
            "status": "success",
            "signal_id": signal_id,
            "signal_type": signal_type,
            "processing_time_ms": round(elapsed, 1)
        }
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/test")
async def test_webhook(request: Request):
    """
    Test endpoint to verify webhook is working
    Send any JSON payload to test connectivity
    """
    body = await request.json()
    logger.info(f"Test webhook received: {body}")
    return {"status": "test_success", "received": body}
