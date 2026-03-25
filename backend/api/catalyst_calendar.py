"""
Catalyst Calendar API (Brief 5J)

Serves upcoming macro events (FOMC, CPI, NFP, OPEX, earnings) and custom
catalysts. Powers the regime bar's "next catalyst" display and the full
calendar view.

Data sources:
- data/econ_calendar_2026.json (static, curated)
- Redis regime:custom_catalysts (user-added via POST)
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import date, datetime, timezone, timedelta
import json
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter()

try:
    from utils.pivot_auth import verify_pivot_key
except ModuleNotFoundError:
    from backend.utils.pivot_auth import verify_pivot_key

try:
    from database.redis_client import get_redis_client
except ModuleNotFoundError:
    from backend.database.redis_client import get_redis_client


# ── Models ──────────────────────────────────────────────────

class CatalystEvent(BaseModel):
    date: str  # YYYY-MM-DD
    event: str
    impact: str = "MEDIUM"  # HIGH, MEDIUM, LOW
    category: Optional[str] = None  # FOMC, CPI, NFP, OPEX, EARNINGS, CUSTOM
    ticker: Optional[str] = None  # For earnings or ticker-specific events


# ── Static Calendar Loading ──────────────────────────────────

_CALENDAR_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")


def _load_static_calendar() -> List[dict]:
    """Load the curated econ calendar JSON."""
    results = []
    for fname in sorted(os.listdir(_CALENDAR_DIR)):
        if fname.startswith("econ_calendar") and fname.endswith(".json"):
            fpath = os.path.join(_CALENDAR_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    events = json.load(f)
                for ev in events:
                    ev.setdefault("category", _infer_category(ev.get("event", "")))
                    results.append(ev)
            except Exception as e:
                logger.warning("Failed to load calendar file %s: %s", fname, e)
    return results


def _infer_category(event_name: str) -> str:
    """Infer event category from name."""
    name = event_name.upper()
    if "FOMC" in name:
        return "FOMC"
    if "CPI" in name:
        return "CPI"
    if "NFP" in name or "EMPLOYMENT" in name:
        return "NFP"
    if "OPEX" in name or "EXPIRATION" in name:
        return "OPEX"
    if "GDP" in name:
        return "GDP"
    if "PCE" in name:
        return "PCE"
    if "EARNING" in name:
        return "EARNINGS"
    return "MACRO"


# ── Endpoints ───────────────────────────────────────────────

@router.get("/catalyst/upcoming")
async def get_upcoming_catalysts(days: int = 14):
    """
    Get upcoming catalyst events within the next N days.
    Merges static econ calendar with user-added custom catalysts.
    """
    today = date.today()
    cutoff = today + timedelta(days=days)

    # Static events
    static = _load_static_calendar()
    upcoming = []
    for ev in static:
        try:
            ev_date = date.fromisoformat(ev["date"])
            if today <= ev_date <= cutoff:
                upcoming.append(ev)
        except (ValueError, KeyError):
            continue

    # Custom catalysts from Redis
    try:
        redis = await get_redis_client()
        raw = await redis.lrange("regime:custom_catalysts", 0, -1)
        if raw:
            for item in raw:
                ev = json.loads(item)
                try:
                    ev_date = date.fromisoformat(ev["date"])
                    if today <= ev_date <= cutoff:
                        ev["category"] = ev.get("category", "CUSTOM")
                        upcoming.append(ev)
                except (ValueError, KeyError):
                    continue
    except Exception as e:
        logger.warning("Failed to load custom catalysts: %s", e)

    # Sort by date
    upcoming.sort(key=lambda e: e.get("date", "9999"))

    # Next catalyst (first upcoming)
    next_catalyst = upcoming[0] if upcoming else None

    return {
        "events": upcoming,
        "count": len(upcoming),
        "next_catalyst": next_catalyst,
    }


@router.get("/catalyst/next")
async def get_next_catalyst():
    """Get just the next upcoming catalyst (for regime bar display)."""
    today = date.today()
    static = _load_static_calendar()

    # Find nearest future event
    nearest = None
    for ev in static:
        try:
            ev_date = date.fromisoformat(ev["date"])
            if ev_date >= today:
                if nearest is None or ev_date < date.fromisoformat(nearest["date"]):
                    nearest = ev
        except (ValueError, KeyError):
            continue

    # Also check custom catalysts
    try:
        redis = await get_redis_client()
        raw = await redis.lrange("regime:custom_catalysts", 0, -1)
        if raw:
            for item in raw:
                ev = json.loads(item)
                try:
                    ev_date = date.fromisoformat(ev["date"])
                    if ev_date >= today:
                        if nearest is None or ev_date < date.fromisoformat(nearest["date"]):
                            ev["category"] = ev.get("category", "CUSTOM")
                            nearest = ev
                except (ValueError, KeyError):
                    continue
    except Exception:
        pass

    if nearest:
        days_until = (date.fromisoformat(nearest["date"]) - today).days
        nearest["days_until"] = days_until
        return nearest

    return {"event": None, "message": "No upcoming catalysts found"}


@router.post("/catalyst/custom")
async def add_custom_catalyst(event: CatalystEvent, _=Depends(verify_pivot_key)):
    """Add a custom catalyst event (earnings, policy, etc.)."""
    try:
        redis = await get_redis_client()
        ev_data = {
            "date": event.date,
            "event": event.event,
            "impact": event.impact.upper(),
            "category": event.category or "CUSTOM",
            "ticker": event.ticker,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        await redis.lpush("regime:custom_catalysts", json.dumps(ev_data))
        await redis.ltrim("regime:custom_catalysts", 0, 99)
        await redis.expire("regime:custom_catalysts", 86400 * 90)
        return {"status": "success", "event": ev_data}
    except Exception as e:
        logger.error(f"Error adding custom catalyst: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/catalyst/custom")
async def clear_custom_catalysts(_=Depends(verify_pivot_key)):
    """Clear all custom catalyst events."""
    try:
        redis = await get_redis_client()
        await redis.delete("regime:custom_catalysts")
        return {"status": "success", "message": "Custom catalysts cleared"}
    except Exception as e:
        logger.error(f"Error clearing custom catalysts: {e}")
        raise HTTPException(status_code=500, detail=str(e))
