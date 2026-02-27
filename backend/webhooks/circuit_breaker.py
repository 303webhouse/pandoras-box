"""
Circuit Breaker System for Market Risk Events
Receives TradingView alerts and dynamically adjusts bias and scoring modifiers.

Triggers:
- spy_down_1pct: SPY drops 1% intraday -> apply minor caution
- spy_down_2pct: SPY drops 2% intraday -> apply major caution
- vix_spike: VIX jumps 15%+ -> heightened volatility
- vix_extreme: VIX > 30 -> extreme fear
- spy_up_2pct: SPY rallies 2%+ after decline -> recovery signal
- spy_recovery: SPY back above prior session close -> all-clear

Circuit Breaker Effects:
- bias_cap: Maximum bullish level allowed (prevents overly bullish bias during risk-off)
- bias_floor: Minimum bearish level enforced (forces bearish lean during crashes)
- scoring_modifier: Multiplier applied to signal scores (penalizes counter-trend trades)

Decay System (condition-verified):
- NOT pure time-based. Decay requires both timer elapsed AND condition cleared.
- States: active -> (timer + condition) -> pending_reset -> (Nick accepts) -> inactive
- No-downgrade: spy_down_1pct cannot overwrite spy_down_2pct (severity ranking)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import logging
import json
import os
import time

logger = logging.getLogger(__name__)

router = APIRouter()

# Severity ranking: higher = more severe. Lower severity cannot overwrite higher.
TRIGGER_SEVERITY = {
    "spy_recovery": 0,
    "spy_up_2pct": 1,
    "spy_down_1pct": 2,
    "vix_spike": 3,
    "spy_down_2pct": 4,
    "vix_extreme": 5,
}

# Decay config per trigger: max_minutes before condition check, and verification function
DECAY_CONFIG = {
    "spy_down_1pct": {"max_minutes": 240, "verify": "spy_not_down_1pct"},
    "spy_down_2pct": {"max_minutes": 1440, "verify": "spy_not_down_2pct"},
    "vix_spike": {"max_minutes": 360, "verify": "vix_below_20"},
    "vix_extreme": {"max_minutes": 1440, "verify": "vix_below_30"},
}

# Circuit breaker state (in-memory)
_circuit_breaker_state = {
    "active": False,
    "trigger": None,
    "triggered_at": None,
    "bias_cap": None,          # Maximum bullish level allowed
    "bias_floor": None,        # Minimum bearish level enforced
    "scoring_modifier": 1.0,   # Multiplier for signal scores
    "description": None,
    "pending_reset": False,    # True when timer elapsed + condition cleared
    "pending_since": None,     # When pending_reset was triggered
    "decay_fade": 1.0,        # Linear fade factor during pending_reset (1.0 -> 0.0)
}

REDIS_CIRCUIT_BREAKER_KEY = "bias:circuit_breaker"
REDIS_CIRCUIT_BREAKER_TTL = 86400

DISCORD_WEBHOOK_CB = os.getenv("DISCORD_WEBHOOK_CB") or ""


class CircuitBreakerTrigger(BaseModel):
    """Payload from TradingView circuit breaker alert"""
    trigger: str  # spy_down_1pct, spy_down_2pct, vix_spike, vix_extreme, spy_up_2pct, spy_recovery
    timestamp: Optional[str] = None


def get_circuit_breaker_state() -> Dict[str, Any]:
    """Get current circuit breaker state."""
    return _circuit_breaker_state.copy()


def reset_circuit_breaker() -> Dict[str, Any]:
    """Reset circuit breaker to normal state."""
    global _circuit_breaker_state

    _circuit_breaker_state = {
        "active": False,
        "trigger": None,
        "triggered_at": None,
        "bias_cap": None,
        "bias_floor": None,
        "scoring_modifier": 1.0,
        "description": None,
        "pending_reset": False,
        "pending_since": None,
        "decay_fade": 1.0,
    }

    logger.info("Circuit breaker reset - normal operations resumed")
    return {"status": "reset", "state": _circuit_breaker_state}


async def _persist_circuit_breaker_state() -> None:
    try:
        from database.redis_client import get_redis_client

        client = await get_redis_client()
        if not client:
            return
        await client.setex(
            REDIS_CIRCUIT_BREAKER_KEY,
            REDIS_CIRCUIT_BREAKER_TTL,
            json.dumps(_circuit_breaker_state),
        )
    except Exception as exc:
        logger.warning("Failed to persist circuit breaker state: %s", exc)


async def restore_circuit_breaker_state() -> bool:
    """Restore circuit-breaker state from Redis after process restart."""
    global _circuit_breaker_state
    try:
        from database.redis_client import get_redis_client

        client = await get_redis_client()
        if not client:
            return False
        raw = await client.get(REDIS_CIRCUIT_BREAKER_KEY)
        if not raw:
            return False

        restored = json.loads(raw)
        if isinstance(restored, dict):
            # Ensure new fields exist for backward compat
            restored.setdefault("pending_reset", False)
            restored.setdefault("pending_since", None)
            restored.setdefault("decay_fade", 1.0)
            _circuit_breaker_state = restored
            logger.info(
                "Circuit breaker state restored (trigger=%s active=%s pending=%s)",
                _circuit_breaker_state.get("trigger"),
                _circuit_breaker_state.get("active"),
                _circuit_breaker_state.get("pending_reset"),
            )
            return True
    except Exception as exc:
        logger.warning("Failed to restore circuit breaker state: %s", exc)
    return False


async def _verify_condition_cleared(verify_type: str) -> bool:
    """
    Check if the trigger condition has cleared.
    Uses Polygon snapshot for SPY triggers, yfinance for VIX.
    """
    try:
        if verify_type == "spy_not_down_1pct":
            return await _check_spy_recovery(threshold_pct=-1.0)
        elif verify_type == "spy_not_down_2pct":
            return await _check_spy_recovery(threshold_pct=-2.0)
        elif verify_type == "vix_below_20":
            return await _check_vix_below(threshold=20)
        elif verify_type == "vix_below_30":
            return await _check_vix_below(threshold=30)
    except Exception as exc:
        logger.warning("Condition verification failed for %s: %s", verify_type, exc)
    return False


async def _check_spy_recovery(threshold_pct: float) -> bool:
    """Check if SPY is no longer down by threshold_pct from previous close."""
    try:
        # Try Polygon first
        from integrations.polygon_equities import get_snapshot, get_previous_close
        snapshot = await get_snapshot("SPY")
        prev = await get_previous_close("SPY")
        if snapshot and prev:
            current = snapshot.get("day", {}).get("c") or snapshot.get("lastTrade", {}).get("p")
            prev_close = prev.get("c")
            if current and prev_close and prev_close > 0:
                change_pct = ((current - prev_close) / prev_close) * 100
                return change_pct > threshold_pct
    except ImportError:
        pass
    except Exception:
        pass

    # yfinance fallback
    try:
        from bias_engine.factor_utils import get_price_history
        data = await get_price_history("SPY", days=5)
        if data is not None and not data.empty and "close" in data.columns and len(data) >= 2:
            current = float(data["close"].iloc[-1])
            prev_close = float(data["close"].iloc[-2])
            if prev_close > 0:
                change_pct = ((current - prev_close) / prev_close) * 100
                return change_pct > threshold_pct
    except Exception:
        pass
    return False


async def _check_vix_below(threshold: float) -> bool:
    """Check if VIX is below the given threshold."""
    try:
        from bias_engine.factor_utils import get_latest_price
        vix = await get_latest_price("^VIX")
        if vix is not None:
            return vix < threshold
    except Exception:
        pass
    return False


async def check_decay() -> Optional[Dict[str, Any]]:
    """
    Check if circuit breaker should transition to pending_reset.
    Called from compute_composite() on every scoring cycle.

    Returns decay status dict if a state change occurred, None otherwise.
    """
    global _circuit_breaker_state

    if not _circuit_breaker_state.get("active"):
        return None

    trigger = _circuit_breaker_state.get("trigger")
    if not trigger or trigger not in DECAY_CONFIG:
        return None

    # Already in pending_reset? Just update fade factor.
    if _circuit_breaker_state.get("pending_reset"):
        return _update_pending_fade()

    # Check if max time has elapsed
    triggered_at = _circuit_breaker_state.get("triggered_at")
    if not triggered_at:
        return None

    try:
        if isinstance(triggered_at, str):
            # Parse ISO format
            ts_str = triggered_at.strip()
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
            triggered_dt = datetime.fromisoformat(ts_str)
            if triggered_dt.tzinfo:
                triggered_dt = triggered_dt.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            triggered_dt = triggered_at
    except (ValueError, TypeError):
        return None

    config = DECAY_CONFIG[trigger]
    max_age = timedelta(minutes=config["max_minutes"])
    now = datetime.utcnow()

    if (now - triggered_dt) < max_age:
        return None  # Timer hasn't elapsed yet

    # Timer elapsed — verify condition has cleared
    condition_cleared = await _verify_condition_cleared(config["verify"])
    if not condition_cleared:
        logger.info(
            "CB decay: timer elapsed for %s but condition NOT cleared — staying active",
            trigger,
        )
        return {"status": "timer_elapsed_condition_active", "trigger": trigger}

    # Both timer elapsed AND condition cleared -> transition to pending_reset
    _circuit_breaker_state["pending_reset"] = True
    _circuit_breaker_state["pending_since"] = now.isoformat()
    _circuit_breaker_state["decay_fade"] = 1.0
    await _persist_circuit_breaker_state()

    logger.info("CB decay: %s transitioning to pending_reset", trigger)

    # Send Discord notification
    await _send_discord_notification(
        f"Circuit Breaker Pending Reset: **{trigger}**",
        (
            f"The `{trigger}` circuit breaker timer has elapsed and the condition has cleared.\n"
            f"Dashboard: Accept or reject the reset.\n"
            f"Scoring modifier is fading linearly toward 1.0."
        ),
    )

    # Broadcast pending_reset to frontend via WebSocket
    try:
        from websocket.broadcaster import manager
        await manager.broadcast({
            "type": "circuit_breaker_pending_reset",
            "state": _circuit_breaker_state,
            "timestamp": now.isoformat(),
        })
    except Exception as e:
        logger.warning("Could not broadcast pending_reset: %s", e)

    return {"status": "pending_reset", "trigger": trigger}


def _update_pending_fade() -> Optional[Dict[str, Any]]:
    """Update the linear fade factor during pending_reset state."""
    pending_since = _circuit_breaker_state.get("pending_since")
    if not pending_since:
        return None

    try:
        if isinstance(pending_since, str):
            pending_dt = datetime.fromisoformat(pending_since)
        else:
            pending_dt = pending_since
        if hasattr(pending_dt, 'tzinfo') and pending_dt.tzinfo:
            pending_dt = pending_dt.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None

    # Linear fade over 60 minutes: scoring_modifier fades toward 1.0
    elapsed_min = (datetime.utcnow() - pending_dt).total_seconds() / 60
    fade = max(0.0, 1.0 - (elapsed_min / 60.0))
    _circuit_breaker_state["decay_fade"] = round(fade, 3)

    return {"status": "pending_fade_update", "fade": fade}


async def accept_reset() -> Dict[str, Any]:
    """Nick accepts the pending reset — clear CB entirely."""
    global _circuit_breaker_state

    if not _circuit_breaker_state.get("pending_reset") and not _circuit_breaker_state.get("active"):
        return {"status": "no_pending_reset", "message": "No circuit breaker is pending reset"}

    old_trigger = _circuit_breaker_state.get("trigger", "unknown")
    result = reset_circuit_breaker()
    await _persist_circuit_breaker_state()

    logger.info("CB reset accepted by user for trigger: %s", old_trigger)

    # Recompute composite without CB constraints
    try:
        from bias_engine.composite import compute_composite
        await compute_composite()
    except Exception as e:
        logger.warning("Could not recompute composite after CB reset: %s", e)

    # Broadcast reset via WebSocket
    try:
        from websocket.broadcaster import manager
        await manager.broadcast({
            "type": "circuit_breaker",
            "state": result["state"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.warning("Could not broadcast CB reset: %s", e)

    await _send_discord_notification(
        "Circuit Breaker Reset Accepted",
        f"The `{old_trigger}` circuit breaker has been reset.",
    )

    return {"status": "accepted", "trigger": old_trigger}


async def reject_reset() -> Dict[str, Any]:
    """Nick rejects the pending reset — keep CB active, reset the timer."""
    global _circuit_breaker_state

    if not _circuit_breaker_state.get("pending_reset"):
        return {"status": "no_pending_reset", "message": "No circuit breaker is pending reset"}

    trigger = _circuit_breaker_state.get("trigger", "unknown")
    _circuit_breaker_state["pending_reset"] = False
    _circuit_breaker_state["pending_since"] = None
    _circuit_breaker_state["decay_fade"] = 1.0
    # Reset the timer by updating triggered_at to now
    _circuit_breaker_state["triggered_at"] = datetime.now(timezone.utc).isoformat()
    await _persist_circuit_breaker_state()

    logger.info("CB reset rejected by user for trigger: %s — timer reset", trigger)

    # Broadcast updated state
    try:
        from websocket.broadcaster import manager
        await manager.broadcast({
            "type": "circuit_breaker",
            "state": _circuit_breaker_state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.warning("Could not broadcast CB reject: %s", e)

    await _send_discord_notification(
        "Circuit Breaker Reset Rejected",
        f"The `{trigger}` circuit breaker remains active. Timer has been reset.",
    )

    return {"status": "rejected", "trigger": trigger}


async def _send_discord_notification(title: str, message: str) -> None:
    """Send a Discord notification via webhook (direct HTTP, no bot)."""
    if not DISCORD_WEBHOOK_CB:
        logger.debug("DISCORD_WEBHOOK_CB not set — skipping notification")
        return

    try:
        import httpx
        payload = {
            "embeds": [{
                "title": title,
                "description": message,
                "color": 0xFFA500,  # Amber
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }]
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(DISCORD_WEBHOOK_CB, json=payload)
            if resp.status_code not in (200, 204):
                logger.warning("Discord webhook failed: HTTP %s", resp.status_code)
    except Exception as exc:
        logger.warning("Discord notification failed: %s", exc)


async def apply_circuit_breaker(trigger: str) -> Dict[str, Any]:
    """
    Apply circuit breaker logic based on trigger type.
    Includes no-downgrade guard: lower severity cannot overwrite higher.
    """
    global _circuit_breaker_state

    trigger_lower = trigger.lower()

    # No-downgrade guard: check severity
    if _circuit_breaker_state.get("active"):
        current_trigger = _circuit_breaker_state.get("trigger", "")
        current_severity = TRIGGER_SEVERITY.get(current_trigger, 0)
        new_severity = TRIGGER_SEVERITY.get(trigger_lower, 0)
        if new_severity < current_severity:
            logger.info(
                "CB no-downgrade: %s (severity %d) cannot overwrite %s (severity %d)",
                trigger_lower, new_severity, current_trigger, current_severity,
            )
            return _circuit_breaker_state

    # SPY DOWN 1% - Minor Caution
    if trigger_lower == "spy_down_1pct":
        _circuit_breaker_state = {
            "active": True,
            "trigger": "spy_down_1pct",
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "bias_cap": "MINOR_TORO",
            "bias_floor": None,
            "scoring_modifier": 0.9,
            "description": "SPY -1% intraday: Minor caution, cap bullish bias",
            "pending_reset": False,
            "pending_since": None,
            "decay_fade": 1.0,
        }
        logger.warning("Circuit Breaker: SPY -1% (Minor Caution)")

    # SPY DOWN 2% - Major Caution
    elif trigger_lower == "spy_down_2pct":
        _circuit_breaker_state = {
            "active": True,
            "trigger": "spy_down_2pct",
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "bias_cap": "LEAN_TORO",
            "bias_floor": "LEAN_URSA",
            "scoring_modifier": 0.75,
            "description": "SPY -2% intraday: Major caution, force bearish lean",
            "pending_reset": False,
            "pending_since": None,
            "decay_fade": 1.0,
        }
        logger.error("Circuit Breaker: SPY -2% (Major Caution)")

    # VIX SPIKE - Volatility Warning
    elif trigger_lower == "vix_spike":
        _circuit_breaker_state = {
            "active": True,
            "trigger": "vix_spike",
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "bias_cap": "MINOR_TORO",
            "bias_floor": None,
            "scoring_modifier": 0.85,
            "description": "VIX +15%: Heightened volatility, reduce bullish exposure",
            "pending_reset": False,
            "pending_since": None,
            "decay_fade": 1.0,
        }
        logger.warning("Circuit Breaker: VIX Spike +15%")

    # VIX EXTREME - Fear Spike
    elif trigger_lower == "vix_extreme":
        _circuit_breaker_state = {
            "active": True,
            "trigger": "vix_extreme",
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "bias_cap": "LEAN_TORO",
            "bias_floor": "MINOR_URSA",
            "scoring_modifier": 0.7,
            "description": "VIX > 30: Extreme fear, force bearish stance",
            "pending_reset": False,
            "pending_since": None,
            "decay_fade": 1.0,
        }
        logger.error("Circuit Breaker: VIX Extreme > 30")

    # SPY UP 2% - Recovery Signal
    elif trigger_lower == "spy_up_2pct":
        _circuit_breaker_state = {
            "active": True,
            "trigger": "spy_up_2pct",
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "bias_cap": None,
            "bias_floor": "LEAN_URSA",
            "scoring_modifier": 1.1,
            "description": "SPY +2% recovery: Partial all-clear, cautious optimism",
            "pending_reset": False,
            "pending_since": None,
            "decay_fade": 1.0,
        }
        logger.info("Circuit Breaker: SPY +2% Recovery")

    # SPY rebound - all clear
    elif trigger_lower == "spy_recovery":
        reset_circuit_breaker()
        _circuit_breaker_state["description"] = "SPY back above prior close: All-clear signal"
        logger.info("Circuit Breaker: SPY Recovery - All Clear")

    else:
        raise ValueError(f"Unknown circuit breaker trigger: {trigger}")

    await _persist_circuit_breaker_state()

    # Send Discord notification for significant triggers
    if trigger_lower in ("spy_down_2pct", "vix_extreme", "vix_spike"):
        await _send_discord_notification(
            f"Circuit Breaker Triggered: {trigger_lower}",
            _circuit_breaker_state.get("description", ""),
        )

    return _circuit_breaker_state


@router.post("/circuit_breaker")
async def receive_circuit_breaker_alert(alert: CircuitBreakerTrigger):
    """
    Receive circuit breaker trigger from TradingView

    TradingView Alert Setup:
    - Symbol: SPY or VIX
    - Conditions: Price drops, VIX spikes, etc.
    - Webhook URL: https://pandoras-box-production.up.railway.app/webhook/circuit_breaker
    - Message (JSON):
      {
        "trigger": "spy_down_1pct"
      }
    """
    logger.info("Circuit breaker webhook received: %s", alert.trigger)

    try:
        # Apply circuit breaker logic
        state = await apply_circuit_breaker(alert.trigger)

        # Force re-score all factors with fresh data, then recompute composite
        try:
            from bias_engine.factor_scorer import score_all_factors
            logger.info("Circuit breaker: forcing full factor re-score...")
            await score_all_factors()
        except Exception as e:
            logger.warning("Could not re-score factors: %s", e)

        try:
            from bias_engine.composite import compute_composite
            logger.info("Circuit breaker: recomputing composite with CB constraints...")
            await compute_composite()
        except Exception as e:
            logger.warning("Could not recompute composite: %s", e)

        # Also refresh legacy daily bias for backward compatibility
        try:
            from scheduler.bias_scheduler import refresh_daily_bias
            await refresh_daily_bias()
        except Exception as e:
            logger.warning("Could not trigger legacy bias refresh: %s", e)

        # Broadcast circuit breaker state via WebSocket
        try:
            from websocket.broadcaster import manager
            await manager.broadcast({
                "type": "circuit_breaker",
                "state": state,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            logger.warning("Could not broadcast circuit breaker state: %s", e)

        return {
            "status": "success",
            "trigger": alert.trigger,
            "state": state,
            "description": state.get("description")
        }

    except Exception as e:
        logger.error("Error processing circuit breaker: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/circuit_breaker/status")
async def get_circuit_breaker_status():
    """Get current circuit breaker status"""
    state = get_circuit_breaker_state()
    return {
        "status": "ok",
        "circuit_breaker": state
    }


@router.post("/circuit_breaker/reset")
async def reset_circuit_breaker_endpoint():
    """Manually reset circuit breaker"""
    result = reset_circuit_breaker()
    await _persist_circuit_breaker_state()

    # Recompute composite without CB constraints, then refresh legacy bias
    try:
        from bias_engine.composite import compute_composite
        logger.info("Circuit breaker reset: recomputing composite...")
        await compute_composite()
    except Exception as e:
        logger.warning("Could not recompute composite: %s", e)

    try:
        from scheduler.bias_scheduler import refresh_daily_bias
        await refresh_daily_bias()
    except Exception as e:
        logger.warning("Could not trigger legacy bias refresh: %s", e)

    # Broadcast reset via WebSocket
    try:
        from websocket.broadcaster import manager
        await manager.broadcast({
            "type": "circuit_breaker",
            "state": result["state"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        logger.warning("Could not broadcast circuit breaker reset: %s", e)

    return result


@router.post("/circuit_breaker/accept_reset")
async def accept_reset_endpoint():
    """Nick accepts the pending circuit breaker reset — clear CB entirely."""
    return await accept_reset()


@router.post("/circuit_breaker/reject_reset")
async def reject_reset_endpoint():
    """Nick rejects the pending reset — keep CB active, reset timer."""
    return await reject_reset()


@router.post("/circuit_breaker/test/{trigger}")
async def test_circuit_breaker(trigger: str):
    """
    Test circuit breaker with a specific trigger (for development)

    Available triggers:
    - spy_down_1pct
    - spy_down_2pct
    - vix_spike
    - vix_extreme
    - spy_up_2pct
    - spy_recovery
    """
    logger.info("Testing circuit breaker with trigger: %s", trigger)

    try:
        state = await apply_circuit_breaker(trigger)

        # Broadcast test state
        try:
            from websocket.broadcaster import manager
            await manager.broadcast({
                "type": "circuit_breaker",
                "state": state,
                "test_mode": True,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            logger.warning("Could not broadcast test state: %s", e)

        return {
            "status": "test_success",
            "trigger": trigger,
            "state": state,
            "description": state.get("description")
        }

    except Exception as e:
        logger.error("Error testing circuit breaker: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
