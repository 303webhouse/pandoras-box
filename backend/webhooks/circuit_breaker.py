"""
Circuit Breaker System for Market Risk Events
Receives TradingView alerts and dynamically adjusts bias and scoring modifiers

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
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter()

# Circuit breaker state (in-memory)
_circuit_breaker_state = {
    "active": False,
    "trigger": None,
    "triggered_at": None,
    "bias_cap": None,          # Maximum bullish level allowed (e.g., "LEAN_TORO")
    "bias_floor": None,        # Minimum bearish level enforced (e.g., "MINOR_URSA")
    "scoring_modifier": 1.0,   # Multiplier for signal scores
    "description": None
}


class CircuitBreakerTrigger(BaseModel):
    """Payload from TradingView circuit breaker alert"""
    trigger: str  # spy_down_1pct, spy_down_2pct, vix_spike, vix_extreme, spy_up_2pct, spy_recovery
    timestamp: Optional[str] = None


def get_circuit_breaker_state() -> Dict[str, Any]:
    """
    Get current circuit breaker state

    Returns:
        Dict with active status, trigger, bias modifications, and scoring modifier
    """
    return _circuit_breaker_state.copy()


def reset_circuit_breaker() -> Dict[str, Any]:
    """
    Reset circuit breaker to normal state

    Returns:
        Dict with reset confirmation
    """
    global _circuit_breaker_state

    _circuit_breaker_state = {
        "active": False,
        "trigger": None,
        "triggered_at": None,
        "bias_cap": None,
        "bias_floor": None,
        "scoring_modifier": 1.0,
        "description": None
    }

    logger.info("🔓 Circuit breaker RESET - normal operations resumed")
    return {"status": "reset", "state": _circuit_breaker_state}


async def apply_circuit_breaker(trigger: str) -> Dict[str, Any]:
    """
    Apply circuit breaker logic based on trigger type

    Args:
        trigger: Type of market event (spy_down_1pct, spy_down_2pct, etc.)

    Returns:
        Dict with applied state and description
    """
    global _circuit_breaker_state

    trigger_lower = trigger.lower()

    # SPY DOWN 1% - Minor Caution
    if trigger_lower == "spy_down_1pct":
        _circuit_breaker_state = {
            "active": True,
            "trigger": "spy_down_1pct",
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "bias_cap": "MINOR_TORO",      # Can't be more bullish than MINOR_TORO
            "bias_floor": None,             # No floor yet
            "scoring_modifier": 0.9,        # Slight penalty to bullish signals
            "description": "SPY -1% intraday: Minor caution, cap bullish bias"
        }
        logger.warning("⚠️ Circuit Breaker: SPY -1% (Minor Caution)")

    # SPY DOWN 2% - Major Caution
    elif trigger_lower == "spy_down_2pct":
        _circuit_breaker_state = {
            "active": True,
            "trigger": "spy_down_2pct",
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "bias_cap": "LEAN_TORO",        # Cap at LEAN_TORO max
            "bias_floor": "LEAN_URSA",      # Force at least LEAN_URSA
            "scoring_modifier": 0.75,       # Penalize bullish signals heavily
            "description": "SPY -2% intraday: Major caution, force bearish lean"
        }
        logger.error("🚨 Circuit Breaker: SPY -2% (Major Caution)")

    # VIX SPIKE - Volatility Warning
    elif trigger_lower == "vix_spike":
        _circuit_breaker_state = {
            "active": True,
            "trigger": "vix_spike",
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "bias_cap": "MINOR_TORO",       # Cap bullishness
            "bias_floor": None,
            "scoring_modifier": 0.85,       # Moderate penalty
            "description": "VIX +15%: Heightened volatility, reduce bullish exposure"
        }
        logger.warning("⚠️ Circuit Breaker: VIX Spike +15%")

    # VIX EXTREME - Fear Spike
    elif trigger_lower == "vix_extreme":
        _circuit_breaker_state = {
            "active": True,
            "trigger": "vix_extreme",
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "bias_cap": "LEAN_TORO",        # Cap at lean bullish max
            "bias_floor": "MINOR_URSA",     # Force MINOR_URSA minimum
            "scoring_modifier": 0.7,        # Heavy penalty to longs
            "description": "VIX > 30: Extreme fear, force bearish stance"
        }
        logger.error("🚨 Circuit Breaker: VIX Extreme > 30")

    # SPY UP 2% - Recovery Signal
    elif trigger_lower == "spy_up_2pct":
        _circuit_breaker_state = {
            "active": True,
            "trigger": "spy_up_2pct",
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "bias_cap": None,               # No cap
            "bias_floor": "LEAN_URSA",      # Still cautious, but allow bullish
            "scoring_modifier": 1.1,        # Slight boost to longs
            "description": "SPY +2% recovery: Partial all-clear, cautious optimism"
        }
        logger.info("✅ Circuit Breaker: SPY +2% Recovery")

    # SPY RECOVERY - All Clear
    elif trigger_lower == "spy_recovery":
        reset_circuit_breaker()
        _circuit_breaker_state["description"] = "SPY back above prior close: All-clear signal"
        logger.info("✅ Circuit Breaker: SPY Recovery - All Clear")

    else:
        raise ValueError(f"Unknown circuit breaker trigger: {trigger}")

    return _circuit_breaker_state


@router.post("/circuit_breaker")
async def receive_circuit_breaker_alert(alert: CircuitBreakerTrigger):
    """
    Receive circuit breaker trigger from TradingView

    TradingView Alert Setup:
    - Symbol: SPY or VIX
    - Conditions: Price drops, VIX spikes, etc.
    - Webhook URL: https://your-app.railway.app/webhook/circuit_breaker
    - Message (JSON):
      {
        "trigger": "spy_down_1pct"
      }
    """
    logger.info(f"🔔 Circuit breaker webhook received: {alert.trigger}")

    try:
        # Apply circuit breaker logic
        state = await apply_circuit_breaker(alert.trigger)

        # Trigger immediate bias refresh to apply new constraints
        try:
            from scheduler.bias_scheduler import refresh_daily_bias
            logger.info("🔄 Triggering bias refresh after circuit breaker...")
            await refresh_daily_bias()
        except Exception as e:
            logger.warning(f"Could not trigger bias refresh: {e}")

        # Broadcast circuit breaker state via WebSocket
        try:
            from websocket.broadcaster import manager
            await manager.broadcast({
                "type": "circuit_breaker",
                "state": state,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            logger.warning(f"Could not broadcast circuit breaker state: {e}")

        return {
            "status": "success",
            "trigger": alert.trigger,
            "state": state,
            "description": state.get("description")
        }

    except Exception as e:
        logger.error(f"Error processing circuit breaker: {e}")
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

    # Trigger bias refresh after reset
    try:
        from scheduler.bias_scheduler import refresh_daily_bias
        logger.info("🔄 Triggering bias refresh after circuit breaker reset...")
        await refresh_daily_bias()
    except Exception as e:
        logger.warning(f"Could not trigger bias refresh: {e}")

    # Broadcast reset via WebSocket
    try:
        from websocket.broadcaster import manager
        await manager.broadcast({
            "type": "circuit_breaker",
            "state": result["state"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        logger.warning(f"Could not broadcast circuit breaker reset: {e}")

    return result


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
    logger.info(f"🧪 Testing circuit breaker with trigger: {trigger}")

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
            logger.warning(f"Could not broadcast test state: {e}")

        return {
            "status": "test_success",
            "trigger": trigger,
            "state": state,
            "description": state.get("description")
        }

    except Exception as e:
        logger.error(f"Error testing circuit breaker: {e}")
        raise HTTPException(status_code=400, detail=str(e))
