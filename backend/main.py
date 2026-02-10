"""
Pandora's Box - Main FastAPI Application
High-performance trading signal processor with sub-100ms latency
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import asyncio
from typing import Set
import logging
import os

# Import our modules (will create these next)
from database.redis_client import get_redis_client
from database.postgres_client import get_postgres_client
from websocket.broadcaster import manager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    
    # Start the bias scheduler
    try:
        from scheduler.bias_scheduler import start_scheduler
        await start_scheduler()
        logger.info("✅ Bias scheduler started")
    except Exception as e:
        logger.warning(f"⚠️ Could not start scheduler: {e}")
    
    # Sync open positions from database
    try:
        from api.positions import sync_positions_from_database
        await sync_positions_from_database()
        logger.info("✅ Positions synced from database")
    except Exception as e:
        logger.warning(f"⚠️ Could not sync positions: {e}")
    
    logger.info("✅ Pandora's Box is live")
    
    yield
    
    # Shutdown
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

# CORS middleware for cross-device access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly in production
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
    """Detailed health check"""
    from scheduler.bias_scheduler import get_eastern_now
    
    redis_client = await get_redis_client()
    postgres_client = await get_postgres_client()
    
    now_et = get_eastern_now()
    
    return {
        "status": "healthy",
        "server_time_et": now_et.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "redis": "connected" if redis_client else "disconnected",
        "postgres": "connected" if postgres_client else "disconnected",
        "websocket_connections": len(manager.active_connections)
    }

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
from api.bias_scheduler import router as bias_scheduler_router
from api.knowledgebase import router as knowledgebase_router
from api.alerts import router as alerts_router
from api.uw_integration import router as uw_integration_router
from api.uw import router as uw_router
from api.options_positions import router as options_router
from api.analyzer import router as analyzer_router

app.include_router(webhook_router, prefix="/webhook", tags=["webhooks"])
app.include_router(circuit_breaker_router, prefix="/webhook", tags=["circuit-breaker"])
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
app.include_router(bias_scheduler_router, prefix="/api", tags=["bias-scheduler"])
app.include_router(hybrid_scanner_router, prefix="/api", tags=["hybrid-scanner"])
app.include_router(knowledgebase_router, prefix="/api", tags=["knowledgebase"])
app.include_router(alerts_router, prefix="/api", tags=["alerts"])
app.include_router(uw_integration_router, prefix="/api", tags=["unusual-whales"])
app.include_router(uw_router, prefix="/api", tags=["unusual-whales"])
app.include_router(options_router, prefix="/api", tags=["options"])
app.include_router(analyzer_router, prefix="/api", tags=["analyzer"])

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
    
    @app.get("/knowledgebase.js", response_class=FileResponse)
    async def serve_knowledgebase_js():
        return FileResponse(os.path.join(frontend_path, "knowledgebase.js"))
    
    @app.get("/styles.css", response_class=FileResponse)
    async def serve_styles():
        return FileResponse(os.path.join(frontend_path, "styles.css"))
    
    @app.get("/manifest.json", response_class=FileResponse)
    async def serve_manifest():
        return FileResponse(os.path.join(frontend_path, "manifest.json"))
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
        log_level="info"
    )
