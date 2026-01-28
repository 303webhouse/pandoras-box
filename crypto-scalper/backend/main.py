"""
Crypto Scalper - FastAPI Backend
Real-time BTC trading signals for Breakout prop trading accounts

This is the main entry point for the crypto scalper interface.
It connects to Bybit for real-time data and broadcasts actionable
trading signals through WebSocket.

Optimized for:
- Breakout 1-Step: 6% max drawdown, 4% daily loss limit
- Conservative phase: 1% risk per trade, 2:1 minimum R:R
- 24/7 operation with session-aware strategies
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Import our modules
from exchange.bybit_client import BybitWebSocketClient, start_bybit_client, get_bybit_client, MarketData
from risk.position_manager import (
    PositionManager, get_position_manager, init_position_manager,
    AccountType, RiskPhase
)
from strategies.signal_engine import get_signal_engine, StrategyType
from websocket.broadcaster import ConnectionManager, manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state
bybit_client: BybitWebSocketClient = None
signal_engine = None
position_manager = None


# Pydantic models for API requests
class AccountConfig(BaseModel):
    account_type: str = "1-step"
    starting_balance: float = 25000.0
    risk_phase: str = "conservative"


class PositionSizeRequest(BaseModel):
    entry_price: float
    stop_loss_price: float
    take_profit_price: float = None
    leverage: float = 1.0
    confidence: float = 1.0


class StrategyToggle(BaseModel):
    strategy: str
    enabled: bool


# Callback functions for Bybit data
async def on_price_update(data: MarketData):
    """Handle real-time price updates from Bybit"""
    global signal_engine
    
    if signal_engine:
        # Process through signal engine
        signals = await signal_engine.process_price_update(
            price=data.last_price,
            vwap=data.session_vwap,
            volume=sum(t["size"] for t in data.recent_trades[-10:]) if data.recent_trades else 0,
            orderbook_imbalance=data.orderbook_imbalance
        )
        
        # Broadcast new signals
        for signal in signals:
            await manager.broadcast({
                "type": "NEW_SIGNAL",
                "data": {
                    "id": signal.id,
                    "strategy": signal.strategy.value,
                    "direction": signal.direction,
                    "entry": signal.entry_price,
                    "stop": signal.stop_loss,
                    "target_1": signal.take_profit_1,
                    "target_2": signal.take_profit_2,
                    "target_3": signal.take_profit_3,
                    "confidence": signal.confidence,
                    "priority": signal.priority.value,
                    "rr_ratio": signal.risk_reward_ratio,
                    "reasoning": signal.reasoning,
                    "position_size_btc": signal.position_size_btc,
                    "risk_amount_usd": signal.risk_amount_usd,
                    "timestamp": signal.timestamp.isoformat()
                }
            })
    
    # Broadcast price update
    await manager.broadcast({
        "type": "PRICE_UPDATE",
        "data": {
            "price": data.last_price,
            "bid": data.bid,
            "ask": data.ask,
            "spread": data.spread,
            "vwap": data.session_vwap,
            "funding_rate": data.funding_rate,
            "next_funding": data.next_funding_time,
            "orderbook_imbalance": round(data.orderbook_imbalance, 3),
            "bid_depth": round(data.bid_depth, 2),
            "ask_depth": round(data.ask_depth, 2),
            "volume_24h": data.volume_24h,
            "high_24h": data.high_24h,
            "low_24h": data.low_24h,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    })


async def on_funding_update(data: MarketData):
    """Handle funding rate updates"""
    global signal_engine
    
    if signal_engine and data.next_funding_time > 0:
        signal = await signal_engine.process_funding_update(
            price=data.last_price,
            funding_rate=data.funding_rate,
            next_funding_time=data.next_funding_time,
            open_interest=data.open_interest
        )
        
        if signal:
            await manager.broadcast({
                "type": "FUNDING_SIGNAL",
                "data": {
                    "id": signal.id,
                    "direction": signal.direction,
                    "entry": signal.entry_price,
                    "stop": signal.stop_loss,
                    "target_1": signal.take_profit_1,
                    "funding_rate": data.funding_rate,
                    "confidence": signal.confidence,
                    "reasoning": signal.reasoning
                }
            })
    
    # Broadcast funding info
    await manager.broadcast({
        "type": "FUNDING_UPDATE",
        "data": {
            "funding_rate": data.funding_rate,
            "next_funding_time": data.next_funding_time,
            "open_interest": data.open_interest
        }
    })


async def on_liquidation(liq_data: Dict, market_data: MarketData):
    """Handle liquidation events"""
    global signal_engine
    
    if signal_engine:
        signal = await signal_engine.process_liquidation(
            liq_data=liq_data,
            current_price=market_data.last_price
        )
        
        if signal:
            await manager.broadcast({
                "type": "LIQUIDATION_SIGNAL", 
                "data": {
                    "id": signal.id,
                    "direction": signal.direction,
                    "entry": signal.entry_price,
                    "stop": signal.stop_loss,
                    "target_1": signal.take_profit_1,
                    "confidence": signal.confidence,
                    "reasoning": signal.reasoning
                }
            })
    
    # Broadcast liquidation event
    await manager.broadcast({
        "type": "LIQUIDATION",
        "data": {
            **liq_data,
            "long_liq_1h": market_data.long_liq_volume_1h,
            "short_liq_1h": market_data.short_liq_volume_1h
        }
    })


async def on_orderbook_update(data: MarketData):
    """Handle orderbook updates"""
    # Broadcast orderbook state
    await manager.broadcast({
        "type": "ORDERBOOK_UPDATE",
        "data": {
            "bid": data.bid,
            "ask": data.ask,
            "spread": data.spread,
            "bid_depth": round(data.bid_depth, 2),
            "ask_depth": round(data.ask_depth, 2),
            "imbalance": round(data.orderbook_imbalance, 3)
        }
    })


async def on_kline_update(timeframe: str, klines: list):
    """Handle kline/candlestick updates"""
    if klines:
        latest = klines[-1]
        await manager.broadcast({
            "type": "KLINE_UPDATE",
            "data": {
                "timeframe": timeframe,
                "open": latest["open"],
                "high": latest["high"],
                "low": latest["low"],
                "close": latest["close"],
                "volume": latest["volume"],
                "confirmed": latest["confirm"]
            }
        })


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global bybit_client, signal_engine, position_manager
    
    logger.info("🚀 Starting Crypto Scalper...")
    
    # Initialize position manager with default settings
    position_manager = init_position_manager(
        account_type=AccountType.ONE_STEP,
        starting_balance=25000.0,
        risk_phase=RiskPhase.CONSERVATIVE
    )
    
    # Initialize signal engine
    signal_engine = get_signal_engine()
    signal_engine.set_position_manager(position_manager)
    
    # Start Bybit WebSocket client
    bybit_task = asyncio.create_task(
        start_bybit_client(
            on_price_update=on_price_update,
            on_orderbook_update=on_orderbook_update,
            on_liquidation=on_liquidation,
            on_funding_update=on_funding_update,
            on_kline_update=on_kline_update
        )
    )
    
    logger.info("✅ Crypto Scalper started - ready for signals")
    
    yield
    
    # Cleanup
    logger.info("Shutting down Crypto Scalper...")
    bybit_task.cancel()
    
    client = await get_bybit_client()
    if client:
        await client.disconnect()


# Create FastAPI app
app = FastAPI(
    title="Crypto Scalper",
    description="Real-time BTC trading signals for Breakout prop trading",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== WebSocket Endpoint ==============

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket connection for real-time updates"""
    await manager.connect(websocket)
    
    try:
        # Send initial state
        await websocket.send_json({
            "type": "CONNECTED",
            "data": {
                "message": "Connected to Crypto Scalper",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        })
        
        # Send current signals
        if signal_engine:
            signals = signal_engine.get_active_signals()
            await websocket.send_json({
                "type": "INITIAL_SIGNALS",
                "data": signals
            })
        
        # Send account status
        if position_manager:
            status = position_manager.get_status()
            await websocket.send_json({
                "type": "ACCOUNT_STATUS",
                "data": status
            })
        
        # Keep connection alive
        while True:
            data = await websocket.receive_text()
            
            # Handle ping/pong
            if data == "ping":
                await websocket.send_text("pong")
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket client disconnected")


# ============== API Endpoints ==============

@app.get("/")
async def root():
    """Health check"""
    return {
        "status": "running",
        "service": "Crypto Scalper",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/health")
async def health():
    """Detailed health check"""
    global bybit_client
    
    client = await get_bybit_client() if bybit_client else None
    
    return {
        "status": "healthy",
        "bybit_connected": client is not None and client.running if client else False,
        "active_connections": len(manager.active_connections),
        "signal_engine_ready": signal_engine is not None,
        "position_manager_ready": position_manager is not None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ----- Signals API -----

@app.get("/api/signals")
async def get_signals():
    """Get all active trading signals"""
    if not signal_engine:
        raise HTTPException(status_code=503, detail="Signal engine not initialized")
    
    return {
        "signals": signal_engine.get_active_signals(),
        "summary": signal_engine.get_summary()
    }


@app.delete("/api/signals/{signal_id}")
async def dismiss_signal(signal_id: str):
    """Dismiss a signal"""
    if not signal_engine:
        raise HTTPException(status_code=503, detail="Signal engine not initialized")
    
    success = signal_engine.dismiss_signal(signal_id)
    if not success:
        raise HTTPException(status_code=404, detail="Signal not found")
    
    return {"status": "dismissed", "signal_id": signal_id}


# ----- Strategy API -----

@app.get("/api/strategies")
async def get_strategies():
    """Get status of all trading strategies"""
    if not signal_engine:
        raise HTTPException(status_code=503, detail="Signal engine not initialized")
    
    return signal_engine.get_strategy_status()


@app.post("/api/strategies/toggle")
async def toggle_strategy(toggle: StrategyToggle):
    """Enable or disable a strategy"""
    if not signal_engine:
        raise HTTPException(status_code=503, detail="Signal engine not initialized")
    
    try:
        strategy = StrategyType(toggle.strategy)
        signal_engine.enable_strategy(strategy, toggle.enabled)
        return {"status": "success", "strategy": toggle.strategy, "enabled": toggle.enabled}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid strategy: {toggle.strategy}")


# ----- Risk Management API -----

@app.get("/api/risk/status")
async def get_risk_status():
    """Get current risk management status"""
    if not position_manager:
        raise HTTPException(status_code=503, detail="Position manager not initialized")
    
    return position_manager.get_status()


@app.post("/api/risk/configure")
async def configure_account(config: AccountConfig):
    """Configure account settings"""
    global position_manager
    
    try:
        account_type = AccountType(config.account_type)
        risk_phase = RiskPhase(config.risk_phase)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    position_manager = init_position_manager(
        account_type=account_type,
        starting_balance=config.starting_balance,
        risk_phase=risk_phase
    )
    
    if signal_engine:
        signal_engine.set_position_manager(position_manager)
    
    return position_manager.get_status()


@app.post("/api/risk/calculate-position")
async def calculate_position(request: PositionSizeRequest):
    """Calculate position size for a potential trade"""
    if not position_manager:
        raise HTTPException(status_code=503, detail="Position manager not initialized")
    
    result = position_manager.calculate_position_size(
        entry_price=request.entry_price,
        stop_loss_price=request.stop_loss_price,
        take_profit_price=request.take_profit_price,
        leverage=request.leverage,
        signal_confidence=request.confidence
    )
    
    return result


@app.post("/api/risk/update-balance")
async def update_balance(balance: float):
    """Update current account balance"""
    if not position_manager:
        raise HTTPException(status_code=503, detail="Position manager not initialized")
    
    position_manager.update_balance(balance)
    return position_manager.get_status()


@app.post("/api/risk/set-phase")
async def set_risk_phase(phase: str):
    """Change risk phase"""
    if not position_manager:
        raise HTTPException(status_code=503, detail="Position manager not initialized")
    
    try:
        risk_phase = RiskPhase(phase)
        position_manager.set_risk_phase(risk_phase)
        return {"status": "success", "phase": phase}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid phase: {phase}")


# ----- Market Data API -----

@app.get("/api/market")
async def get_market_data():
    """Get current market data"""
    client = await get_bybit_client()
    
    if not client:
        raise HTTPException(status_code=503, detail="Bybit client not connected")
    
    data = client.get_market_data()
    
    return {
        "symbol": data.symbol,
        "price": data.last_price,
        "bid": data.bid,
        "ask": data.ask,
        "spread": data.spread,
        "vwap": data.session_vwap,
        "funding_rate": data.funding_rate,
        "next_funding_time": data.next_funding_time,
        "open_interest": data.open_interest,
        "volume_24h": data.volume_24h,
        "high_24h": data.high_24h,
        "low_24h": data.low_24h,
        "orderbook_imbalance": data.orderbook_imbalance,
        "long_liq_1h": data.long_liq_volume_1h,
        "short_liq_1h": data.short_liq_volume_1h
    }


@app.get("/api/market/sessions")
async def get_sessions():
    """Get upcoming trading sessions"""
    if not signal_engine:
        raise HTTPException(status_code=503, detail="Signal engine not initialized")
    
    return signal_engine.session_strategy.get_upcoming_sessions()


@app.get("/api/market/funding-windows")
async def get_funding_windows():
    """Get upcoming funding settlement windows"""
    if not signal_engine:
        raise HTTPException(status_code=503, detail="Signal engine not initialized")
    
    return signal_engine.funding_strategy.get_next_funding_windows()


@app.get("/api/market/liquidations")
async def get_liquidations():
    """Get current liquidation statistics"""
    if not signal_engine:
        raise HTTPException(status_code=503, detail="Signal engine not initialized")
    
    return signal_engine.liquidation_strategy.get_current_stats()


# Mount static files for frontend
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")
    
    @app.get("/app")
    async def serve_frontend():
        return FileResponse(os.path.join(frontend_path, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
