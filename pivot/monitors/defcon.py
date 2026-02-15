"""
DEFCON behavioral alert system for Pivot.

Evaluates market conditions across multiple signal sources and determines
the appropriate behavioral response level for Nick's trading.

This is a BEHAVIORAL layer — it tells Nick what to DO. The circuit breaker
(on Railway) handles algorithmic adjustments.

Levels:
  GREEN  — Normal operations
  YELLOW — Pause, observe 15-30 min (1 signal)
  ORANGE — No new trades, tighten stops (2+ signals or 1 orange-level event)
  RED    — Flatten everything (3+ signals or 1 red-level event)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from collectors.base_collector import get_json
from collectors.config import TIMEZONE

logger = logging.getLogger(__name__)

STATE_PATH = Path(__file__).resolve().parents[1] / "state" / "defcon.json"

LEVELS = {"green": 0, "yellow": 1, "orange": 2, "red": 3}
LEVEL_EMOJIS = {"green": "🟢", "yellow": "🟡", "orange": "🟠", "red": "🔴"}

# Circuit breaker trigger → DEFCON signal mapping
CB_SIGNAL_MAP: Dict[str, Optional[Dict[str, str]]] = {
    "spy_down_1pct": {
        "name": "spy_decline_minor",
        "severity": "yellow",
        "detail": "SPY -1% intraday",
    },
    "spy_down_2pct": {
        "name": "spy_decline_major",
        "severity": "yellow",
        "detail": "SPY -2% intraday",
    },
    "vix_spike": {
        "name": "vix_spike",
        "severity": "yellow",
        "detail": "VIX jumped 15%+",
    },
    "vix_extreme": {
        "name": "vix_extreme",
        "severity": "yellow",
        "detail": "VIX > 30",
    },
    # Recovery signals — these reduce DEFCON, not add signals
    "spy_up_2pct": None,
    "spy_recovery": None,
}

VIX_THRESHOLDS = [
    (35, "red",    "VIX extreme fear ({value:.0f})"),
    (28, "orange", "VIX elevated ({value:.0f})"),
    (20, "yellow", "VIX above normal ({value:.0f})"),
]


def _load_state() -> Dict[str, Any]:
    """Load DEFCON state from disk. Returns default green state if missing."""
    try:
        if STATE_PATH.exists():
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {
        "level": "green",
        "signals": [],
        "updated_at": None,
        "escalated_at": None,
        "session_date": None,
    }


def _save_state(state: Dict[str, Any]) -> None:
    """Persist DEFCON state to disk."""
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state), encoding="utf-8")
    except Exception as exc:
        logger.warning(f"Failed to save DEFCON state: {exc}")


def _now_iso() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).isoformat()


async def _gather_signals() -> List[Dict[str, Any]]:
    """
    Collect all active signals from multiple sources.

    Each signal is a dict:
    {
        "name": "vix_elevated",
        "source": "bias_factors",
        "severity": "yellow",
        "detail": "VIX at 22.5",
    }
    """
    signals: List[Dict[str, Any]] = []

    # ── 1. Circuit breaker ────────────────────────────────────────────────────
    try:
        cb_data = await get_json("/circuit_breaker/status")
        cb = cb_data.get("circuit_breaker", {})
        if cb.get("active"):
            trigger = cb.get("trigger", "")
            mapped = CB_SIGNAL_MAP.get(trigger)
            if mapped is not None:
                signals.append({**mapped, "source": "circuit_breaker"})
            elif trigger and trigger not in CB_SIGNAL_MAP:
                # Unknown trigger — treat as yellow
                signals.append({
                    "name": f"cb_{trigger}",
                    "source": "circuit_breaker",
                    "severity": "yellow",
                    "detail": cb.get("description") or f"Circuit breaker: {trigger}",
                })
    except Exception as exc:
        logger.warning(f"DEFCON: circuit breaker check failed: {exc}")

    # ── 2. Bias composite / factor data ──────────────────────────────────────
    try:
        composite = await get_json("/bias/composite")
        factors = composite.get("factors", {})

        # VIX level from vix_term factor or top-level
        vix_data = factors.get("vix_term", {}) or {}
        vix_current: Optional[float] = (
            vix_data.get("data", {}).get("vix")
            or vix_data.get("vix")
            or composite.get("vix")
        )
        vix_3m: Optional[float] = (
            vix_data.get("data", {}).get("vix3m")
            or vix_data.get("vix3m")
        )

        if vix_current is not None:
            for threshold, severity, tmpl in VIX_THRESHOLDS:
                if vix_current > threshold:
                    # Only add if not already captured by circuit breaker vix_extreme
                    existing_names = {s["name"] for s in signals}
                    sig_name = f"vix_level_{severity}"
                    if sig_name not in existing_names and "vix_extreme" not in existing_names:
                        signals.append({
                            "name": sig_name,
                            "source": "bias_factors",
                            "severity": severity,
                            "detail": tmpl.format(value=vix_current),
                        })
                    break  # Only apply the highest-matching threshold

            # VIX term structure inversion
            if vix_3m is not None and vix_current > vix_3m:
                signals.append({
                    "name": "vix_inversion",
                    "source": "bias_factors",
                    "severity": "orange",
                    "detail": f"VIX term inverted: {vix_current:.1f} > VIX3M {vix_3m:.1f}",
                })

        # TICK breadth — extreme readings
        tick_data = factors.get("tick_breadth", {}) or {}
        tick_value: Optional[float] = (
            tick_data.get("data", {}).get("tick")
            or tick_data.get("tick")
        )
        if tick_value is not None and abs(tick_value) > 1000:
            direction = "negative" if tick_value < 0 else "positive"
            signals.append({
                "name": "tick_extreme",
                "source": "bias_factors",
                "severity": "yellow",
                "detail": f"TICK sustained extreme: {tick_value:.0f} ({direction})",
            })

    except Exception as exc:
        logger.warning(f"DEFCON: bias composite check failed: {exc}")

    # ── 3. Breakout proximity ─────────────────────────────────────────────────
    try:
        from journal.breakout import check_breakout_danger
        danger = check_breakout_danger()
        danger_level = danger.get("danger_level") if danger else None
        if danger_level and danger_level not in ("green", "unknown"):
            breakout_map = {"yellow": "orange", "orange": "red", "red": "red"}
            severity = breakout_map.get(danger_level, "orange")
            room = danger.get("room_to_personal")
            detail = (
                f"Breakout {danger_level}: ${room:.0f} to personal floor"
                if room is not None
                else f"Breakout account at {danger_level} danger"
            )
            signals.append({
                "name": "breakout_danger",
                "source": "journal",
                "severity": severity,
                "detail": detail,
            })
    except Exception:
        pass  # Journal not populated yet — skip gracefully

    return signals


async def _evaluate_level(
    signals: List[Dict[str, Any]],
) -> Tuple[str, List[str]]:
    """
    Determine DEFCON level from active signals using confluence logic.

    Rules:
    - No signals → green
    - Any single red-severity signal → red
    - Any single orange-severity signal → orange
    - 3+ yellow signals → red
    - 2+ yellow signals → orange
    - 1 yellow signal → yellow
    """
    trigger_names = [s["name"] for s in signals]

    red_signals = [s for s in signals if s.get("severity") == "red"]
    orange_signals = [s for s in signals if s.get("severity") == "orange"]
    yellow_signals = [s for s in signals if s.get("severity") == "yellow"]

    if red_signals or len(yellow_signals) >= 3:
        return "red", trigger_names
    if orange_signals or len(yellow_signals) >= 2:
        return "orange", trigger_names
    if yellow_signals:
        return "yellow", trigger_names
    return "green", trigger_names


def _build_guidance(level: str, signals: List[Dict[str, Any]]) -> str:
    """Build the behavioral guidance message for Discord."""
    emoji = LEVEL_EMOJIS.get(level, "⚪")
    level_upper = level.upper()

    if level == "green":
        return f"{emoji} DEFCON GREEN — All clear. Trade per bias and rules."

    signal_lines = "\n".join(f"  • {s['detail']}" for s in signals)

    if level == "yellow":
        return (
            f"{emoji} DEFCON YELLOW — Heightened awareness.\n"
            f"Signal:\n{signal_lines}\n"
            f"Action: Pause new positions. Observe 15-30 minutes before entering."
        )

    if level == "orange":
        return (
            f"{emoji} DEFCON ORANGE — Defensive mode.\n"
            f"Signals:\n{signal_lines}\n"
            f"Action: NO new trades. Tighten stops to breakeven where possible.\n"
            f"Cancel working orders. Consider reducing exposure."
        )

    # RED
    return (
        f"{emoji} DEFCON RED — EMERGENCY.\n"
        f"Signals:\n{signal_lines}\n"
        f"Action: FLATTEN or hedge all positions immediately.\n"
        f"Close ALL Breakout positions. Do NOT re-enter until next session."
    )


def _log_defcon_event(
    level: str,
    previous_level: str,
    triggers: List[str],
    duration_minutes: Optional[int] = None,
    notes: str = "",
) -> None:
    """Log a DEFCON transition to the journal's defcon_events table."""
    try:
        import asyncio
        from journal.db import get_connection

        def _write():
            conn = get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO defcon_events
                        (level, previous_level, triggers, duration_minutes, notes)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        level,
                        previous_level,
                        json.dumps(triggers),
                        duration_minutes,
                        notes or None,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        # Run synchronously — this is called from async context via asyncio.to_thread
        _write()
    except Exception as exc:
        logger.warning(f"DEFCON: failed to log event to journal: {exc}")


async def check_defcon() -> Optional[Dict[str, Any]]:
    """
    Main entry point — called by cron_runner heartbeat every 15 minutes.

    Gathers signals, evaluates level, compares to previous state.
    Returns a dict if the level CHANGED (for notification), None if unchanged.
    """
    now = _now_iso()
    today = date.today().isoformat()

    # Load and potentially reset state for new trading day
    state = _load_state()
    if state.get("session_date") != today:
        state = {
            "level": "green",
            "signals": [],
            "updated_at": now,
            "escalated_at": None,
            "session_date": today,
        }
        _save_state(state)

    previous_level = state.get("level", "green")
    previous_escalated_at = state.get("escalated_at")

    # Gather all active signals
    try:
        signals = await _gather_signals()
    except Exception as exc:
        logger.error(f"DEFCON: signal gathering failed: {exc}")
        return None

    current_level, trigger_names = await _evaluate_level(signals)

    if current_level == previous_level:
        return None  # No change — no notification needed

    # Calculate duration of the previous non-green level
    duration_minutes: Optional[int] = None
    if previous_level != "green" and previous_escalated_at:
        try:
            escalated_dt = datetime.fromisoformat(previous_escalated_at)
            now_dt = datetime.now(ZoneInfo(TIMEZONE))
            if escalated_dt.tzinfo is None:
                escalated_dt = escalated_dt.replace(tzinfo=ZoneInfo(TIMEZONE))
            duration_minutes = int((now_dt - escalated_dt).total_seconds() / 60)
        except Exception:
            pass

    # Log to journal
    await asyncio.to_thread(
        _log_defcon_event,
        current_level,
        previous_level,
        trigger_names,
        duration_minutes,
        "",
    )

    # Update state
    new_escalated_at = (
        now
        if (
            LEVELS.get(current_level, 0) > LEVELS.get(previous_level, 0)
            or current_level != "green"
        )
        else None
    )
    state = {
        "level": current_level,
        "signals": [s["name"] for s in signals],
        "updated_at": now,
        "escalated_at": new_escalated_at if current_level != "green" else None,
        "session_date": today,
    }
    _save_state(state)

    guidance = _build_guidance(current_level, signals)

    # Add de-escalation context to guidance
    if current_level == "green" and previous_level != "green":
        duration_str = f" (held for {duration_minutes} minutes)" if duration_minutes else ""
        guidance = (
            f"{LEVEL_EMOJIS['green']} DEFCON GREEN — All clear.\n"
            f"Previous: {previous_level.upper()}{duration_str}\n"
            f"All signals have cleared. Normal operations resumed."
        )

    return {
        "type": "defcon",
        "previous_level": previous_level,
        "current_level": current_level,
        "signals": signals,
        "guidance": guidance,
        "timestamp": now,
    }


async def get_current_defcon() -> Dict[str, Any]:
    """
    Get current DEFCON status without triggering notifications.
    Used by morning briefs and trade evaluation prompts.
    """
    state = _load_state()
    level = state.get("level", "green")
    signal_names = state.get("signals", [])
    since = state.get("escalated_at") or state.get("updated_at")

    emoji = LEVEL_EMOJIS.get(level, "⚪")

    guidance_map = {
        "green": "All clear. Trade per bias and rules.",
        "yellow": "Pause new positions. Observe 15-30 minutes before entering.",
        "orange": "NO new trades. Tighten stops. Cancel working orders.",
        "red": "FLATTEN or hedge all positions. Do NOT re-enter until next session.",
    }

    return {
        "level": level,
        "emoji": emoji,
        "signals": signal_names,
        "since": since,
        "guidance": guidance_map.get(level, ""),
    }


async def force_defcon(level: str, reason: str = "") -> Dict[str, Any]:
    """
    Manually override DEFCON level. Used for Black Swan events
    or situations the automated system can't detect.

    Saves state, logs to journal, returns the new state.
    """
    if level not in LEVELS:
        raise ValueError(f"Invalid DEFCON level '{level}'. Must be one of: {list(LEVELS)}")

    now = _now_iso()
    today = date.today().isoformat()
    state = _load_state()
    previous_level = state.get("level", "green")

    signals = [
        {
            "name": "manual_override",
            "source": "manual",
            "severity": level if level != "green" else "yellow",
            "detail": reason or f"Manual DEFCON override to {level.upper()}",
        }
    ] if level != "green" else []

    # Log to journal
    await asyncio.to_thread(
        _log_defcon_event,
        level,
        previous_level,
        ["manual_override"],
        None,
        reason,
    )

    new_state = {
        "level": level,
        "signals": ["manual_override"] if signals else [],
        "updated_at": now,
        "escalated_at": now if level != "green" else None,
        "session_date": today,
    }
    _save_state(new_state)

    guidance = _build_guidance(level, signals)

    return {
        "type": "defcon",
        "previous_level": previous_level,
        "current_level": level,
        "signals": signals,
        "guidance": guidance,
        "timestamp": now,
        "forced": True,
        "reason": reason,
    }


# Needed for asyncio.to_thread usage inside async function
import asyncio
