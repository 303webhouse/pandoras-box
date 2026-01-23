"""
Pandora's Box - Main FastAPI Application
High-performance trading signal processor with sub-100ms latency
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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
from websocket.broadcaster import ConnectionManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# WebSocket connection manager
manager = ConnectionManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    logger.info("🚀 Pandora's Box backend starting...")
    
    # Initialize database connections
    redis_client = await get_redis_client()
    postgres_client = await get_postgres_client()
    
    logger.info("✅ Database connections established")
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
    redis_client = await get_redis_client()
    postgres_client = await get_postgres_client()
    
    return {
        "status": "healthy",
        "redis": "connected" if redis_client else "disconnected",
        "postgres": "connected" if postgres_client else "disconnected",
        "websocket_connections": len(manager.active_connections)
    }

@app.get("/api/bias/{timeframe}")
async def get_bias_data(timeframe: str):
    """Get current bias for a specific timeframe"""
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
from api.positions import router as positions_router
from api.scanner import router as scanner_router
from api.watchlist import router as watchlist_router
from api.bias import router as bias_router
from api.strategies import router as strategies_router
from api.cta import router as cta_router
from api.btc_signals import router as btc_signals_router
from api.flow import router as flow_router
from api.dollar_smile import router as dollar_smile_router
from api.hybrid_scanner import router as hybrid_scanner_router

app.include_router(webhook_router, prefix="/webhook", tags=["webhooks"])
app.include_router(positions_router, prefix="/api", tags=["positions"])
app.include_router(scanner_router, prefix="/api", tags=["scanner"])
app.include_router(watchlist_router, prefix="/api", tags=["watchlist"])
app.include_router(bias_router, prefix="/api", tags=["bias"])
app.include_router(strategies_router, prefix="/api", tags=["strategies"])
app.include_router(cta_router, prefix="/api", tags=["cta"])
app.include_router(btc_signals_router, prefix="/api", tags=["btc-signals"])
app.include_router(flow_router, prefix="/api", tags=["options-flow"])
app.include_router(dollar_smile_router, prefix="/api", tags=["dollar-smile"])
app.include_router(hybrid_scanner_router, prefix="/api", tags=["hybrid-scanner"])

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
    
    @app.get("/app.js", response_class=FileResponse)
    async def serve_app_js():
        return FileResponse(os.path.join(frontend_path, "app.js"))
    
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
