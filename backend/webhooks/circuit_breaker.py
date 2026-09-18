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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from utils.pivot_auth import require_api_key
from utils.webhook_auth import validate_webhook_secret
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import logging
import json
import os
import time

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Chunk F cutover toggle (OBSERVE until flip-day) ──
# /webhook/circuit_breaker was intentionally public; an unauth POST can move
# bias_cap/bias_floor/scoring_modifier (scoring-DoS vector). Gate with the shared TV
# secret (reuses TRADINGVIEW_WEBHOOK_SECRET — CB is a TV-family Pine) and its own flag
# so the flip is independent. OBSERVE (validate-but-allow, logs verdict) until a CB
# fire logs secret PRESENT, then flip via WEBHOOK_CB_ENFORCE=1 (no redeploy).
def _cb_observe() -> bool:
    return (os.getenv("WEBHOOK_CB_ENFORCE") or "").strip().lower() not in ("1", "true", "yes")

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

# ── Provenance (observability only — no behaviour change) ────────────────────
# The board's kill-switch cell must say HOW it knows what it knows. Without this
# record the API cannot tell "an event confirmed CLEAR during this boot" apart
# from "nothing was ever stored and the module default is standing" — and it was
# reporting both as a maximum-confidence all-clear (DEF-KILLSWITCH-FAILOPEN).
#
# This is a read-only ledger about the in-memory state. It never influences
# `active`, enforcement, or any write path.
_BOOT_AT = datetime.now(timezone.utc)
_cb_provenance: Dict[str, Any] = {
    "source": "default-since-boot",   # | 'restored-at-boot' | 'event-confirmed'
    "as_of": _BOOT_AT,                # last state-affecting event, else boot
}


def get_circuit_breaker_provenance() -> Dict[str, Any]:
    """How the current in-memory CB state came to be. Display/provenance only."""
    return dict(_cb_provenance)


def _mark_provenance(source: str, as_of: Optional[datetime] = None) -> None:
    """Record how the in-memory state came to be. MUST NEVER RAISE.

    This is observability bolted onto the enforcement path. If it could throw it
    would become the deepest possible fail-open: a provenance failure aborting the
    persistence — or worse the arm itself — of the market-risk breaker. Bookkeeping
    added to prove honesty must never be able to break the thing it describes.
    """
    try:
        _cb_provenance["source"] = source
        _cb_provenance["as_of"] = as_of or datetime.now(timezone.utc)
    except Exception:  # noqa: BLE001 - deliberately total
        # Losing provenance degrades the display to its conservative default; it
        # must never propagate. Logging is best-effort and also guarded.
        try:
            logger.warning("Provenance mark failed; display falls back to default-since-boot")
        except Exception:  # noqa: BLE001
            pass

DISCORD_WEBHOOK_CB = os.getenv("DISCORD_WEBHOOK_CB") or ""


class CircuitBreakerTrigger(BaseModel):
    """Payload from TradingView circuit breaker alert"""
    trigger: str  # spy_down_1pct, spy_down_2pct, vix_spike, vix_extreme, spy_up_2pct, spy_recovery
    timestamp: Optional[str] = None
    secret: Optional[str] = None


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
    # Single choke point for every state-affecting event (trip, decay transition,
    # accept/reject reset, manual reset), so it is the honest place to record that
    # this boot has a confirmed event behind its state.
    #
    # The mark runs in `finally`, strictly AFTER the persistence attempt, and
    # _mark_provenance() cannot raise. Two reasons it is positioned here and not
    # before the try:
    #   1. No call site guards this function. A throw ahead of the setex would abort
    #      persistence and, from apply_circuit_breaker(), the arm path itself —
    #      armed in memory, unpersisted, no Discord alert, 500 to the webhook.
    #      Observability must not be able to break enforcement.
    #   2. `finally` rather than the success path: `source` describes the IN-MEMORY
    #      state, and the in-memory event happened whether or not Redis accepted it.
    #      Marking only on success would report a real event as default-since-boot
    #      during a Redis outage — the mirror image of the lie being fixed. The Redis
    #      side is reported separately and truthfully via `persisted_record`.
    try:
        from database.redis_client import get_redis_client

        client = await get_redis_client()
        if not client:
            return
        payload = json.dumps(_circuit_breaker_state)
        if _circuit_breaker_state.get("active"):
            # ── R4 (DEF-KILLSWITCH-TTL-RESTART): ARMED STATE FAILS CLOSED ──────────
            # An armed breaker must not expire into silence. Under the old blanket
            # 24h TTL, a breaker armed more than a day before a process restart came
            # back CLEAR: restore_circuit_breaker_state() found no key, left the
            # module default standing, and the API stamped that fabricated all-clear
            # as live and not degraded. A safety device that quietly disarms itself
            # is worse than none, because the board keeps asserting the protection.
            #
            # SET with no expiry also CLEARS any TTL inherited from a previous
            # clear-state write, which is exactly the intent: once armed, the record
            # persists until an operator clears it.
            #
            # Recovery is documented and operator-verified, which is the precondition
            # for shipping this: docs/operations/circuit-breaker-manual-recovery.md
            await client.set(REDIS_CIRCUIT_BREAKER_KEY, payload)
        else:
            # Clear state keeps the 24h expiry, unchanged. Out of R4's scope, and it
            # is the mechanism that returns the board to NO TRIP ON RECORD unassisted
            # once a cleared record ages out.
            await client.setex(REDIS_CIRCUIT_BREAKER_KEY, REDIS_CIRCUIT_BREAKER_TTL, payload)
    except Exception as exc:
        logger.warning("Failed to persist circuit breaker state: %s", exc)
    finally:
        _mark_provenance("event-confirmed")


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
            _mark_provenance("restored-at-boot", _BOOT_AT)
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


async def hub_spy_reading() -> Dict[str, Any]:
    """The hub's OWN reading of SPY against its prior close, every input named and aged.

    R-IV.455(e) -- THE VINTAGE RULE. A breaker fire used to carry its verdict and nothing else:
    TradingView sends a trigger NAME, the hub cannot see the reference price, the current price,
    either timestamp, or the percentage behind it, and so a fire on a false reading looked
    exactly like a fire on a true one. This is the hub's independent measurement, recorded
    beside every SPY fire so the verdict carries its evidence. Never raises; a reading it cannot
    take is reported as not taken, never as a pass.
    """
    now = datetime.now(timezone.utc)
    out: Dict[str, Any] = {"read_at": now.isoformat(), "price": None, "prior_close": None,
                           "change_pct": None, "vendor": None, "method": None, "error": None}
    try:
        from integrations.uw_api import get_snapshot, get_previous_close
        snapshot = await get_snapshot("SPY")
        prev = await get_previous_close("SPY")
        prev_row = (prev.get("results") or [{}])[0] if isinstance(prev, dict) else {}
        current = None
        if snapshot:
            current = (snapshot.get("day") or {}).get("c") or \
                (snapshot.get("lastTrade") or {}).get("p")
        prior = prev_row.get("c") if isinstance(prev_row, dict) else None
        if current and prior and float(prior) > 0:
            out.update(price=float(current), prior_close=float(prior), vendor="uw",
                       method="snapshot vs previous close",
                       change_pct=round((float(current) - float(prior)) / float(prior) * 100, 3))
            return out
    except Exception as exc:
        out["error"] = f"uw: {type(exc).__name__}"
    try:
        from bias_engine.factor_utils import get_price_history, price_vendor
        data = await get_price_history("SPY", days=5)
        if data is not None and not data.empty and "close" in data.columns and len(data) >= 2:
            current = float(data["close"].iloc[-1])
            prior = float(data["close"].iloc[-2])
            if prior > 0:
                out.update(price=current, prior_close=prior, vendor=price_vendor(data),
                           method="last two daily closes (fallback)",
                           price_as_of=str(data.index[-1])[:10],
                           change_pct=round((current - prior) / prior * 100, 3))
                return out
    except Exception as exc:
        out["error"] = (out["error"] + "; " if out["error"] else "") + \
            f"history: {type(exc).__name__}"
    return out


async def _check_spy_recovery(threshold_pct: float) -> bool:
    """Is SPY no longer down by threshold_pct from its prior close? Fails CLOSED: a reading
    that cannot be taken is not a recovery."""
    reading = await hub_spy_reading()
    pct = reading.get("change_pct")
    return pct is not None and pct > threshold_pct


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

    # Already in pending_reset? Self-resolve once a full session has passed; otherwise fade.
    if _circuit_breaker_state.get("pending_reset"):
        cleared = await self_resolve_if_due()
        if cleared:
            return cleared
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


# ── R-IV.457(a)(2) / CONVENTIONS #22: A LATCH CLEARS WITHOUT BEING SEEN ─────────────────────
#
# A pending reset -- the trigger's condition has already cleared -- used to wait for a human to
# accept it, on a surface the principal does not watch, announced through a notification path
# that had been retired. It waited 42 hours. An alarm whose clearing depends on a human seeing
# it is a latch by construction.
#
# So once the condition has cleared AND one full regular session has passed since, the breaker
# clears ITSELF, persists the clear, and logs a notice. Human accept remains the path for a
# same-session clear, which is the only case where a person's judgement adds something the
# condition check does not.
SESSION_OPEN_ET = (9, 30)
SESSION_CLOSE_ET = (16, 0)
_LAST_SELF_CLEAR: Dict[str, Any] = {}


def full_session_elapsed_since(since_utc: datetime, now_utc: Optional[datetime] = None) -> bool:
    """Has a complete regular session (open to close, on a trading day) run AFTER `since`?

    The first session that counts is the one whose OPEN is at or after `since`. A day the
    calendar cannot answer for is not assumed to be a session -- for a kill switch, unknown is
    not permission.
    """
    from zoneinfo import ZoneInfo
    from datetime import time as _time
    from stable_engine.market_calendar import is_trading_day_or_none

    et = ZoneInfo("America/New_York")
    now_utc = now_utc or datetime.now(timezone.utc)
    if since_utc.tzinfo is None:
        since_utc = since_utc.replace(tzinfo=timezone.utc)
    since_et = since_utc.astimezone(et)
    day = since_et.date()
    if since_et.time() > _time(*SESSION_OPEN_ET):
        day = day + timedelta(days=1)
    for _ in range(14):
        if is_trading_day_or_none(day) is True:
            close = datetime.combine(day, _time(*SESSION_CLOSE_ET), tzinfo=et)
            return now_utc >= close.astimezone(timezone.utc)
        day = day + timedelta(days=1)
    return False


async def self_resolve_if_due(now_utc: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """Clear a pending reset whose condition cleared a full session ago. Never raises."""
    global _LAST_SELF_CLEAR
    try:
        if not (_circuit_breaker_state.get("active") and
                _circuit_breaker_state.get("pending_reset")):
            return None
        since = _circuit_breaker_state.get("pending_since")
        if not since:
            return None
        since_dt = datetime.fromisoformat(str(since).replace("Z", "+00:00"))
        if not full_session_elapsed_since(since_dt, now_utc):
            return None
        trigger = _circuit_breaker_state.get("trigger")
        _LAST_SELF_CLEAR = {
            "trigger": trigger,
            "triggered_at": _circuit_breaker_state.get("triggered_at"),
            "pending_since": since,
            "cleared_at": (now_utc or datetime.now(timezone.utc)).isoformat(),
            "rule": "R-IV.457(a)(2): condition cleared and a full session passed",
        }
        reset_circuit_breaker()
        _circuit_breaker_state["last_self_clear"] = dict(_LAST_SELF_CLEAR)
        await _persist_circuit_breaker_state()
        logger.warning(
            "CIRCUIT BREAKER SELF-CLEARED: %s (fired %s, condition cleared %s) -- a full "
            "session passed with no human accept; cleared per R-IV.457(a)(2)",
            trigger, _LAST_SELF_CLEAR["triggered_at"], since)
        return {"status": "self_cleared", **_LAST_SELF_CLEAR}
    except Exception as exc:
        logger.warning("Circuit breaker self-resolution check failed: %s", exc)
        return None


# What each alert CLAIMS, so a disputed fire can show the claim beside the hub's reading.
TRIGGER_CLAIMS = {
    "spy_down_1pct": "SPY down at least 1% intraday",
    "spy_down_2pct": "SPY down at least 2% intraday",
    "vix_spike": "VIX up 15% or more",
    "vix_extreme": "VIX above 30",
    "spy_up_2pct": "SPY up at least 2% after a decline",
    "spy_recovery": "SPY back above the prior session close",
}


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


SPY_TRIGGER_THRESHOLD = {"spy_down_1pct": -1.0, "spy_down_2pct": -2.0}


async def _stamp_hub_reading(trigger: Optional[str]) -> None:
    """Record the hub's own SPY reading on a SPY fire, and flag a fire it does not confirm.

    Recorded and flagged, NOT rejected: refusing to arm on a disagreement would change what the
    safety device does, which is a ruling. What changes here is that a disputed fire can no
    longer look like a confirmed one.
    """
    threshold = SPY_TRIGGER_THRESHOLD.get((trigger or "").lower())
    if threshold is None or not _circuit_breaker_state.get("active"):
        return
    reading = await hub_spy_reading()
    pct = reading.get("change_pct")
    disputed = None if pct is None else pct > threshold
    _circuit_breaker_state["hub_reading"] = reading
    _circuit_breaker_state["disputed"] = disputed
    base = _circuit_breaker_state.get("description") or trigger
    if pct is None:
        note = "hub reading NOT TAKEN (" + str(reading.get("error")) + ")"
    else:
        note = (f"hub reading at fire: SPY {reading['price']:.2f} vs prior close "
                f"{reading['prior_close']:.2f} = {pct:+.2f}% ({reading['vendor']}, "
                f"{reading['method']})")
        if disputed:
            note += f" -- DOES NOT CONFIRM the {threshold:.0f}% trigger"
    _circuit_breaker_state["description"] = f"{base} | {note}"
    await _persist_circuit_breaker_state()
    if disputed:
        logger.warning("Circuit breaker %s DISPUTED by the hub's own reading: %s", trigger, note)


async def _circuit_breaker_background_work(state: dict):
    """Heavy follow-up work after circuit breaker triggers. Runs as background task."""
    try:
        await _stamp_hub_reading(state.get("trigger"))
    except Exception as e:
        logger.warning("Could not stamp the hub's reading on the fire: %s", e)
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

    logger.info("Circuit breaker background work complete for trigger: %s", state.get("trigger"))


@router.post("/circuit_breaker")
async def receive_circuit_breaker_alert(alert: CircuitBreakerTrigger, background_tasks: BackgroundTasks):
    """
    Receive circuit breaker trigger from TradingView.

    AUTH (Chunk F): formerly intentionally public. Now gated by the shared webhook
    secret via the CB Pine's "Webhook Secret" input (reuses TRADINGVIEW_WEBHOOK_SECRET).
    Runs OBSERVE-mode until flip-day; flips fail-closed via WEBHOOK_CB_ENFORCE=1.
    The management routes below (reset, accept, reject, test) remain require_api_key.

    TradingView Alert Setup:
    - Symbol: SPY or VIX
    - Conditions: Price drops, VIX spikes, etc.
    - Webhook URL: https://pandoras-box-production.up.railway.app/webhook/circuit_breaker
    - Message (JSON):
      {
        "trigger": "spy_down_1pct",
        "secret": "<TRADINGVIEW_WEBHOOK_SECRET>"
      }
    """
    # ── Chunk F hardening (shared AEGIS helper) — OBSERVE until market-hours flip ──
    validate_webhook_secret(
        alert.secret,
        secret=os.getenv("TRADINGVIEW_WEBHOOK_SECRET") or "",
        observe=_cb_observe(),
        label="circuit_breaker",
    )

    logger.info("Circuit breaker webhook received: %s", alert.trigger)

    try:
        # Apply circuit breaker logic (fast — in-memory + Redis write)
        state = await apply_circuit_breaker(alert.trigger)

        # Schedule heavy re-scoring work as background task so TradingView gets a fast response
        background_tasks.add_task(_circuit_breaker_background_work, state)

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
async def reset_circuit_breaker_endpoint(_=Depends(require_api_key)):
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
async def accept_reset_endpoint(_=Depends(require_api_key)):
    """Nick accepts the pending circuit breaker reset — clear CB entirely."""
    return await accept_reset()


@router.post("/circuit_breaker/reject_reset")
async def reject_reset_endpoint(_=Depends(require_api_key)):
    """Nick rejects the pending reset — keep CB active, reset timer."""
    return await reject_reset()


@router.post("/circuit_breaker/test/{trigger}")
async def test_circuit_breaker(trigger: str, _=Depends(require_api_key)):
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
