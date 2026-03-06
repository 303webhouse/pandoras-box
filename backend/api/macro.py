"""
Macro Briefing API — persistent regime narrative for Pivot + Committee.

GET /api/macro/briefing — returns current macro briefing from Redis
POST /api/macro/briefing — updates macro briefing (requires API key)
"""

import json
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from database.redis_client import get_redis_client

router = APIRouter()

PIVOT_API_KEY = os.getenv("PIVOT_API_KEY") or ""
REDIS_KEY = "macro:briefing"


def verify_api_key(x_api_key: str = Header(None)):
    if PIVOT_API_KEY and x_api_key != PIVOT_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


class MacroBriefingUpdate(BaseModel):
    updated_at: str
    updated_by: str = "nick"
    regime: str = "UNKNOWN"
    narrative: str = ""
    key_facts: list[str] = []
    sectors_to_watch: dict[str, list[str]] = {}


@router.get("/briefing")
async def get_macro_briefing():
    """Return current macro briefing from Redis."""
    client = await get_redis_client()
    raw = await client.get(REDIS_KEY)
    if not raw:
        return {"status": "empty", "briefing": None}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"status": "error", "briefing": None}
    return {"status": "ok", "briefing": data}


@router.post("/briefing")
async def update_macro_briefing(body: MacroBriefingUpdate, _=Depends(verify_api_key)):
    """Update macro briefing in Redis. No TTL — persists until overwritten."""
    client = await get_redis_client()
    data = body.model_dump()
    await client.set(REDIS_KEY, json.dumps(data))
    return {"status": "ok", "briefing": data}
