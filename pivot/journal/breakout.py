"""
Breakout prop evaluation-specific tracking.

All functions are synchronous; wrap in asyncio.to_thread() when calling
from async contexts (cron_runner, Discord bot).
"""

from __future__ import annotations

import logging
from typing import Optional

from journal.db import get_connection
from journal.models import BreakoutSnapshot

logger = logging.getLogger(__name__)

# Danger thresholds (distance from personal drawdown floor)
_DANGER_GREEN = 1000   # > $1000 from personal floor
_DANGER_YELLOW = 500   # $500–$1000 from personal floor
_DANGER_ORANGE = 300   # $300–$500 from personal floor
# red: < $300 from REAL floor


def _row_to_dict(row) -> dict:
    return dict(row) if row is not None else {}


def log_breakout_snapshot(snapshot: BreakoutSnapshot) -> int:
    """
    Record current Breakout account state.

    Called after each Breakout trade closes and at EOD.
    Auto-calculates drawdown_floor_real = high_water_mark - 2000.
    Auto-calculates drawdown_floor_personal = drawdown_floor_real + 500.
    Returns the snapshot ID.
    """
    hwm = snapshot["high_water_mark"]
    floor_real = hwm - 2000
    floor_personal = floor_real + 500

    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO breakout_tracking (
                balance, high_water_mark,
                drawdown_floor_real, drawdown_floor_personal,
                daily_loss_used, daily_loss_limit,
                step, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot["balance"],
                hwm,
                floor_real,
                floor_personal,
                snapshot.get("daily_loss_used", 0),
                snapshot.get("daily_loss_limit"),
                snapshot.get("step", 1),
                snapshot.get("notes"),
            ),
        )
        conn.commit()
        snap_id = cursor.lastrowid
        logger.info(
            f"Breakout snapshot {snap_id}: balance=${snapshot['balance']}, "
            f"HWM=${hwm}, floor_real=${floor_real}, floor_personal=${floor_personal}"
        )
        return snap_id
    finally:
        conn.close()


def get_latest_breakout_state() -> Optional[dict]:
    """
    Get the most recent Breakout snapshot.
    Returns None if no snapshots exist yet.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM breakout_tracking ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_breakout_history(limit: int = 30) -> list[dict]:
    """
    Get recent Breakout snapshots for trend analysis.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM breakout_tracking ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def check_breakout_danger(snapshot: Optional[dict] = None) -> dict:
    """
    Evaluate how close the Breakout account is to danger zones.

    If snapshot is None, fetches the latest from the DB.

    Returns a dict with balance, floors, room, daily loss info,
    danger_level ('green'|'yellow'|'orange'|'red'), and warnings.
    """
    state = snapshot or get_latest_breakout_state()

    if state is None:
        return {
            "balance": None,
            "high_water_mark": None,
            "floor_real": None,
            "floor_personal": None,
            "room_to_personal": None,
            "room_to_real": None,
            "daily_loss_used": None,
            "daily_loss_remaining": None,
            "danger_level": "unknown",
            "warnings": ["No Breakout snapshots found — run log_breakout_snapshot first"],
        }

    balance = state["balance"]
    hwm = state["high_water_mark"]
    floor_real = state["drawdown_floor_real"]
    floor_personal = state["drawdown_floor_personal"]
    daily_loss_used = state.get("daily_loss_used", 0) or 0
    daily_loss_limit = state.get("daily_loss_limit")

    room_to_personal = round(balance - floor_personal, 2)
    room_to_real = round(balance - floor_real, 2)
    daily_loss_remaining = (
        round(daily_loss_limit - daily_loss_used, 2)
        if daily_loss_limit is not None
        else None
    )

    warnings: list[str] = []

    # Determine danger level
    if room_to_real < 300:
        danger_level = "red"
        warnings.append(
            f"CRITICAL: Only ${room_to_real:.0f} above REAL drawdown floor — FLATTEN EVERYTHING"
        )
    elif room_to_personal < 300:
        danger_level = "red"
        warnings.append(
            f"CRITICAL: Only ${room_to_personal:.0f} above personal floor"
        )
    elif room_to_personal < _DANGER_ORANGE:
        danger_level = "orange"
        warnings.append(
            f"WARNING: ${room_to_personal:.0f} from personal floor — stop trading"
        )
    elif room_to_personal < _DANGER_YELLOW:
        danger_level = "yellow"
        warnings.append(
            f"CAUTION: ${room_to_personal:.0f} from personal floor — reduce size"
        )
    else:
        danger_level = "green"

    if daily_loss_remaining is not None and daily_loss_remaining < 100:
        warnings.append(
            f"Daily loss limit nearly exhausted: ${daily_loss_remaining:.0f} remaining"
        )

    return {
        "balance": balance,
        "high_water_mark": hwm,
        "floor_real": floor_real,
        "floor_personal": floor_personal,
        "room_to_personal": room_to_personal,
        "room_to_real": room_to_real,
        "daily_loss_used": daily_loss_used,
        "daily_loss_remaining": daily_loss_remaining,
        "danger_level": danger_level,
        "warnings": warnings,
    }


def update_hwm_if_needed(new_balance: float) -> bool:
    """
    If new_balance > current HWM, update HWM and recalculate floors.
    Called after profitable Breakout trades.
    Returns True if HWM was updated.
    """
    state = get_latest_breakout_state()
    if state is None:
        logger.warning("update_hwm_if_needed: no existing snapshot to compare against")
        return False

    current_hwm = state["high_water_mark"]
    if new_balance <= current_hwm:
        return False

    # Log a new snapshot with updated HWM and recalculated floors
    from journal.models import BreakoutSnapshot
    new_snapshot: BreakoutSnapshot = {
        "balance": new_balance,
        "high_water_mark": new_balance,
        "drawdown_floor_real": new_balance - 2000,
        "drawdown_floor_personal": new_balance - 2000 + 500,
        "daily_loss_used": state.get("daily_loss_used", 0) or 0,
        "daily_loss_limit": state.get("daily_loss_limit", 0) or 0,
        "step": state.get("step", 1),
        "notes": f"HWM updated from ${current_hwm} to ${new_balance}",
    }
    log_breakout_snapshot(new_snapshot)
    logger.info(f"HWM updated: ${current_hwm} → ${new_balance}")
    return True
