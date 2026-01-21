"""
Redis Client for Real-Time Signal State
In-memory cache for lightning-fast signal access (<2ms)
"""

import redis.asyncio as redis
from typing import Optional, Dict, Any
import json
import os
from datetime import timedelta
from dotenv import load_dotenv
import numpy as np


def sanitize_for_json(obj):
    """Convert numpy types to native Python types for JSON serialization"""
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, (np.bool_, np.integer)):
        return bool(obj) if isinstance(obj, np.bool_) else int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', 'config', '.env'))

# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# Global connection pool
_redis_client: Optional[redis.Redis] = None

async def get_redis_client() -> redis.Redis:
    """Get or create Redis client with connection pooling"""
    global _redis_client
    
    if _redis_client is None:
        # Build Redis URL with optional password and SSL support
        if REDIS_PASSWORD:
            # Use rediss:// for SSL (Upstash requires SSL)
            redis_url = f"rediss://default:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
        else:
            redis_url = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
        
        _redis_client = await redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            ssl_cert_reqs=None  # Don't verify SSL certificates for development
        )
    
    return _redis_client

async def close_redis_client():
    """Close Redis connection"""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None

# Signal cache operations
async def cache_signal(signal_id: str, signal_data: Dict[Any, Any], ttl: int = 3600):
    """
    Cache a signal in Redis with TTL
    Args:
        signal_id: Unique identifier (e.g., "AAPL_LONG_20260105_142311")
        signal_data: Signal details
        ttl: Time to live in seconds (default 1 hour)
    """
    client = await get_redis_client()
    # Sanitize data to ensure all numpy types are converted to Python natives
    sanitized_data = sanitize_for_json(signal_data)
    await client.setex(
        f"signal:{signal_id}",
        ttl,
        json.dumps(sanitized_data)
    )

async def get_signal(signal_id: str) -> Optional[Dict[Any, Any]]:
    """Retrieve a cached signal"""
    client = await get_redis_client()
    data = await client.get(f"signal:{signal_id}")
    return json.loads(data) if data else None

async def get_active_signals() -> list:
    """Get all active signals (last 100)"""
    client = await get_redis_client()
    keys = await client.keys("signal:*")
    
    signals = []
    for key in keys:
        data = await client.get(key)
        if data:
            signals.append(json.loads(data))
    
    return signals

async def delete_signal(signal_id: str):
    """Remove a signal from cache (user dismissed or expired)"""
    client = await get_redis_client()
    await client.delete(f"signal:{signal_id}")

# Bias state operations
async def set_bias(timeframe: str, bias_level: str, bias_data: Dict[Any, Any]):
    """
    Store current bias state
    Args:
        timeframe: "DAILY" | "WEEKLY" | "MONTHLY"
        bias_level: "URSA_MAJOR" | "URSA_MINOR" | "NEUTRAL" | "TORO_MINOR" | "TORO_MAJOR"
        bias_data: Supporting data (TICK ranges, etc.)
    """
    client = await get_redis_client()
    await client.setex(
        f"bias:{timeframe}",
        86400,  # 24 hour TTL
        json.dumps({
            "level": bias_level,
            "data": bias_data,
            "updated_at": str(bias_data.get("timestamp"))
        })
    )

async def get_bias(timeframe: str) -> Optional[Dict[Any, Any]]:
    """Retrieve current bias for a timeframe"""
    client = await get_redis_client()
    data = await client.get(f"bias:{timeframe}")
    return json.loads(data) if data else None

# Watchlist operations
async def set_watchlist(user_id: str, tickers: list):
    """Store user's equity watchlist"""
    client = await get_redis_client()
    await client.set(
        f"watchlist:{user_id}",
        json.dumps(tickers)
    )

async def get_watchlist(user_id: str) -> list:
    """Retrieve user's watchlist"""
    client = await get_redis_client()
    data = await client.get(f"watchlist:{user_id}")
    return json.loads(data) if data else []
