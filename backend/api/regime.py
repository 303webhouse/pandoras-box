"""
Regime awareness layer for Agora.
Manages active market regime labels, manual overrides, and reversal mode.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import logging
import json

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

try:
    from database.postgres_client import get_postgres_client
except ModuleNotFoundError:
    from backend.database.postgres_client import get_postgres_client


class RegimeOverride(BaseModel):
    """Manual regime override from the trader."""
    regime_label: str
    direction: str = "NEUTRAL"
    dominant_driver: Optional[str] = None
    sectors_favored: List[str] = []
    sectors_avoided: List[str] = []
    theme_keywords: List[str] = []
    reversal_mode: bool = False
    expires_hours: float = 8.0


class ThemeHit(BaseModel):
    """A tweet or headline that matched the active regime's theme keywords."""
    text: str
    author: str
    url: Optional[str] = None
    matched_keywords: List[str] = []
    timestamp: Optional[str] = None


REGIME_CACHE_KEY = "regime:current_override"


@router.get("/regime/current")
async def get_current_regime():
    """
    Get the current market regime.
    Priority: manual override > auto-generated from composite > default.
    """
    try:
        redis = await get_redis_client()

        # Check for manual override first
        override_raw = await redis.get(REGIME_CACHE_KEY)
        if override_raw:
            override = json.loads(override_raw)
            if override.get("expires_at"):
                exp = datetime.fromisoformat(override["expires_at"])
                if datetime.now(timezone.utc) > exp:
                    await redis.delete(REGIME_CACHE_KEY)
                else:
                    return {**override, "source": "manual_override"}

        # Fall back to auto-generated regime from composite
        composite_raw = await redis.get("bias:composite:latest")
        if composite_raw:
            composite = json.loads(composite_raw)
            raw_score = composite.get("composite_score", 0)
            if isinstance(raw_score, str):
                try:
                    raw_score = float(raw_score)
                except (ValueError, TypeError):
                    raw_score = 0.0

            # Convert from -1..+1 scale to 0..100 for display and thresholds
            score = round(((raw_score + 1) / 2) * 100)

            if score >= 70:
                label = f"Favorable ({score}/100) — full signal menu, normal sizing"
            elif score >= 50:
                label = f"Cautious ({score}/100) — high-conviction setups only"
            elif score >= 30:
                label = f"Unfavorable ({score}/100) — minimal new positions, hedge exposure"
            else:
                label = f"Hostile ({score}/100) — capital preservation only"

            return {
                "regime_label": label,
                "direction": "BULLISH" if score >= 60 else "BEARISH" if score <= 40 else "NEUTRAL",
                "dominant_driver": None,
                "sectors_favored": [],
                "sectors_avoided": [],
                "theme_keywords": [],
                "reversal_mode": False,
                "source": "auto_composite",
                "expires_at": None,
                "created_at": composite.get("timestamp"),
            }

        # Default fallback
        return {
            "regime_label": "No regime data available. Check bias composite.",
            "direction": "NEUTRAL",
            "dominant_driver": None,
            "sectors_favored": [],
            "sectors_avoided": [],
            "theme_keywords": [],
            "reversal_mode": False,
            "source": "default",
            "expires_at": None,
            "created_at": None,
        }

    except Exception as e:
        logger.error(f"Error getting regime: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/regime/override")
async def set_regime_override(override: RegimeOverride, _=Depends(verify_pivot_key)):
    """
    Manually set the market regime. Overrides auto-generated labels.
    Requires API key auth.
    """
    try:
        redis = await get_redis_client()

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=override.expires_hours)

        regime_data = {
            "regime_label": override.regime_label,
            "direction": override.direction.upper(),
            "dominant_driver": override.dominant_driver,
            "sectors_favored": override.sectors_favored,
            "sectors_avoided": override.sectors_avoided,
            "theme_keywords": [kw.lower().strip() for kw in override.theme_keywords],
            "reversal_mode": override.reversal_mode,
            "expires_at": expires_at.isoformat(),
            "created_at": now.isoformat(),
        }

        ttl_seconds = int(override.expires_hours * 3600)
        await redis.setex(REGIME_CACHE_KEY, ttl_seconds, json.dumps(regime_data))

        # Also store in Postgres for audit history
        try:
            pool = await get_postgres_client()
            await pool.execute(
                """INSERT INTO regime_overrides
                   (regime_label, direction, dominant_driver, sectors_favored,
                    sectors_avoided, theme_keywords, reversal_mode, expires_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                override.regime_label,
                override.direction.upper(),
                override.dominant_driver,
                json.dumps(override.sectors_favored),
                json.dumps(override.sectors_avoided),
                json.dumps(override.theme_keywords),
                override.reversal_mode,
                expires_at,
            )
        except Exception as db_err:
            logger.warning(f"Failed to log regime override to DB (non-critical): {db_err}")

        return {"status": "success", "regime": regime_data}

    except Exception as e:
        logger.error(f"Error setting regime override: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/regime/override")
async def clear_regime_override(_=Depends(verify_pivot_key)):
    """Clear the manual regime override. Falls back to auto-generated."""
    try:
        redis = await get_redis_client()
        await redis.delete(REGIME_CACHE_KEY)
        return {"status": "success", "message": "Override cleared. Falling back to auto-generated regime."}
    except Exception as e:
        logger.error(f"Error clearing regime override: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/regime/theme-hit")
async def store_theme_hit(hit: ThemeHit, _=Depends(verify_pivot_key)):
    """Store a theme-matched tweet/headline from Pivot or other scrapers."""
    try:
        redis = await get_redis_client()
        hit_data = {
            "text": hit.text[:500],
            "author": hit.author,
            "url": hit.url,
            "matched_keywords": hit.matched_keywords,
            "timestamp": hit.timestamp or datetime.now(timezone.utc).isoformat(),
        }

        key = "regime:theme_hits"
        await redis.lpush(key, json.dumps(hit_data))
        await redis.ltrim(key, 0, 49)
        await redis.expire(key, 86400)

        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error storing theme hit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regime/correlations")
async def get_correlations():
    """Get latest correlation collapse scan results."""
    try:
        redis = await get_redis_client()
        raw = await redis.get("regime:correlations")
        if raw:
            return json.loads(raw)
        return {"pairs": [], "alerts": [], "collapse_count": 0, "decorrelated_count": 0, "timestamp": None}
    except Exception as e:
        logger.error(f"Error fetching correlations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regime/theme-hits")
async def get_theme_hits(limit: int = 20):
    """Get recent theme-matched tweets/headlines."""
    try:
        redis = await get_redis_client()
        raw_hits = await redis.lrange("regime:theme_hits", 0, limit - 1)
        hits = [json.loads(h) for h in raw_hits] if raw_hits else []
        return {"hits": hits, "count": len(hits)}
    except Exception as e:
        logger.error(f"Error fetching theme hits: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Trip Wire Endpoints ──────────────────────────────────────

@router.get("/regime/trip-wires")
async def get_trip_wires_endpoint():
    """Get configured trip wires and latest scan results."""
    try:
        redis = await get_redis_client()
        raw = await redis.get("regime:trip_wire_latest")
        if raw:
            return json.loads(raw)
        # No scan yet — return the wire config
        from analysis.trip_wire_monitor import get_trip_wires
        wires = await get_trip_wires()
        return {"wires": wires, "triggered_count": 0, "newly_breached": [], "timestamp": None}
    except Exception as e:
        logger.error(f"Error fetching trip wires: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/regime/trip-wires")
async def update_trip_wires(wires: List[dict], _=Depends(verify_pivot_key)):
    """Replace the full trip wire config."""
    try:
        from analysis.trip_wire_monitor import save_trip_wires
        await save_trip_wires(wires)
        return {"status": "success", "count": len(wires)}
    except Exception as e:
        logger.error(f"Error saving trip wires: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regime/trip-wire-alerts")
async def get_trip_wire_alerts(limit: int = 20):
    """Get recent trip wire breach alerts."""
    try:
        redis = await get_redis_client()
        raw_alerts = await redis.lrange("regime:trip_wire_alerts", 0, limit - 1)
        alerts = [json.loads(a) for a in raw_alerts] if raw_alerts else []
        return {"alerts": alerts, "count": len(alerts)}
    except Exception as e:
        logger.error(f"Error fetching trip wire alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Flow-Signal Confluence Endpoint ──────────────────────────

@router.get("/regime/flow-confluence")
async def get_flow_confluence():
    """Get tickers where active signals and UW flow overlap."""
    try:
        redis = await get_redis_client()
        raw = await redis.get("regime:flow_confluence")
        if raw:
            return json.loads(raw)
        return {"confluences": [], "count": 0, "timestamp": None}
    except Exception as e:
        logger.error(f"Error fetching flow confluence: {e}")
        raise HTTPException(status_code=500, detail=str(e))
