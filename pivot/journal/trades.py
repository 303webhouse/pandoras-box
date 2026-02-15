"""
CRUD operations for trade journal entries.

All functions are synchronous; wrap in asyncio.to_thread() when calling
from async contexts (cron_runner, Discord bot).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from journal.db import get_connection
from journal.models import TradeEntry, TradeExit

logger = logging.getLogger(__name__)

_VALID_ACCOUNTS = {"401k", "robinhood", "breakout"}
_VALID_DIRECTIONS = {"long", "short", "neutral"}


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row) if row is not None else {}


def open_trade(entry: TradeEntry) -> int:
    """
    Insert a new trade record. Returns the trade ID.

    Validates required fields: account, ticker, direction.
    Validates account is one of: '401k', 'robinhood', 'breakout'.
    Auto-captures entry_date as today if not provided.
    """
    account = entry.get("account", "")
    ticker = entry.get("ticker", "")
    direction = entry.get("direction", "")

    if not account:
        raise ValueError("account is required")
    if not ticker:
        raise ValueError("ticker is required")
    if not direction:
        raise ValueError("direction is required")
    if account not in _VALID_ACCOUNTS:
        raise ValueError(f"account must be one of {_VALID_ACCOUNTS}, got '{account}'")
    if direction not in _VALID_DIRECTIONS:
        raise ValueError(f"direction must be one of {_VALID_DIRECTIONS}, got '{direction}'")

    entry_date = entry.get("entry_date") or date.today().isoformat()

    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO trades (
                account, ticker, strategy, direction,
                entry_price, entry_date, size, max_loss, stop_price, target_price,
                bias_at_entry, defcon_at_entry, iv_rank,
                thesis, catalyst, invalidation, confidence,
                status
            ) VALUES (
                :account, :ticker, :strategy, :direction,
                :entry_price, :entry_date, :size, :max_loss, :stop_price, :target_price,
                :bias_at_entry, :defcon_at_entry, :iv_rank,
                :thesis, :catalyst, :invalidation, :confidence,
                'open'
            )
            """,
            {
                "account": account,
                "ticker": ticker,
                "strategy": entry.get("strategy"),
                "direction": direction,
                "entry_price": entry.get("entry_price"),
                "entry_date": entry_date,
                "size": entry.get("size"),
                "max_loss": entry.get("max_loss"),
                "stop_price": entry.get("stop_price"),
                "target_price": entry.get("target_price"),
                "bias_at_entry": entry.get("bias_at_entry"),
                "defcon_at_entry": entry.get("defcon_at_entry"),
                "iv_rank": entry.get("iv_rank"),
                "thesis": entry.get("thesis"),
                "catalyst": entry.get("catalyst"),
                "invalidation": entry.get("invalidation"),
                "confidence": entry.get("confidence"),
            },
        )
        conn.commit()
        trade_id = cursor.lastrowid
        logger.info(f"Opened trade {trade_id}: {account} {ticker} {direction}")
        return trade_id
    finally:
        conn.close()


def close_trade(trade_id: int, exit_data: TradeExit) -> dict:
    """
    Update a trade record with exit details. Sets status to 'closed'.

    Auto-calculates pnl_percent if entry_price and exit_price are both present
    and pnl_percent is not explicitly provided.
    Returns the full updated trade record as a dict.
    Raises ValueError if trade not found or already closed.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()

        if row is None:
            raise ValueError(f"Trade {trade_id} not found")
        trade = _row_to_dict(row)
        if trade["status"] != "open":
            raise ValueError(
                f"Trade {trade_id} is already {trade['status']}, cannot close"
            )

        exit_date = exit_data.get("exit_date") or date.today().isoformat()
        exit_price = exit_data.get("exit_price")
        pnl_dollars = exit_data.get("pnl_dollars")
        pnl_percent = exit_data.get("pnl_percent")

        # Auto-calculate pnl_percent if we have the necessary data
        if pnl_percent is None and exit_price is not None and trade.get("entry_price"):
            entry_price = trade["entry_price"]
            if entry_price != 0:
                pnl_percent = ((exit_price - entry_price) / entry_price) * 100
                if trade.get("direction") == "short":
                    pnl_percent = -pnl_percent

        followed_plan = exit_data.get("followed_plan")
        followed_plan_int = None
        if followed_plan is not None:
            followed_plan_int = 1 if followed_plan else 0

        conn.execute(
            """
            UPDATE trades SET
                exit_price = :exit_price,
                exit_date = :exit_date,
                pnl_dollars = :pnl_dollars,
                pnl_percent = :pnl_percent,
                followed_plan = :followed_plan,
                exit_reason = :exit_reason,
                lesson = :lesson,
                status = 'closed',
                updated_at = datetime('now')
            WHERE id = :id
            """,
            {
                "exit_price": exit_price,
                "exit_date": exit_date,
                "pnl_dollars": pnl_dollars,
                "pnl_percent": pnl_percent,
                "followed_plan": followed_plan_int,
                "exit_reason": exit_data.get("exit_reason"),
                "lesson": exit_data.get("lesson"),
                "id": trade_id,
            },
        )
        conn.commit()

        updated = conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()
        result = _row_to_dict(updated)
        logger.info(
            f"Closed trade {trade_id}: {result.get('ticker')} "
            f"P&L ${result.get('pnl_dollars')}"
        )
        return result
    finally:
        conn.close()


def cancel_trade(trade_id: int, reason: str = "") -> dict:
    """
    Mark a trade as cancelled (never executed). Sets status to 'cancelled'.
    Returns the updated trade record.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Trade {trade_id} not found")

        conn.execute(
            """
            UPDATE trades SET
                status = 'cancelled',
                lesson = :reason,
                updated_at = datetime('now')
            WHERE id = :id
            """,
            {"reason": reason or None, "id": trade_id},
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()
        return _row_to_dict(updated)
    finally:
        conn.close()


def get_trade(trade_id: int) -> Optional[dict]:
    """Get a single trade by ID."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_open_trades(account: Optional[str] = None) -> list[dict]:
    """
    Get all open trades, optionally filtered by account.
    Returns list of trade dicts, ordered by entry_date desc.
    """
    conn = get_connection()
    try:
        if account:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status = 'open' AND account = ? "
                "ORDER BY entry_date DESC",
                (account,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status = 'open' ORDER BY entry_date DESC"
            ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_recent_trades(days: int = 7, account: Optional[str] = None) -> list[dict]:
    """
    Get trades from the last N days (both open and closed).
    Used for weekly reviews.
    """
    since = (date.today() - timedelta(days=days)).isoformat()
    conn = get_connection()
    try:
        if account:
            rows = conn.execute(
                "SELECT * FROM trades WHERE entry_date >= ? AND account = ? "
                "ORDER BY entry_date DESC",
                (since, account),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trades WHERE entry_date >= ? ORDER BY entry_date DESC",
                (since,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_trade_history(
    ticker: Optional[str] = None,
    account: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """
    Query trade history with optional filters.
    Returns most recent trades first.
    """
    conditions = []
    params: list = []

    if ticker:
        conditions.append("ticker = ?")
        params.append(ticker)
    if account:
        conditions.append("account = ?")
        params.append(account)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT * FROM trades {where} ORDER BY entry_date DESC LIMIT ?",
            params,
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_streak(account: Optional[str] = None) -> dict:
    """
    Calculate current win/loss streak from closed trades.

    Returns: {'type': 'win'|'loss'|'none', 'count': int, 'trades': list}

    Important for Playbook rule: size down after 2 consecutive losses.
    """
    conn = get_connection()
    try:
        if account:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status = 'closed' AND account = ? "
                "ORDER BY exit_date DESC, id DESC",
                (account,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status = 'closed' "
                "ORDER BY exit_date DESC, id DESC"
            ).fetchall()

        trades = [_row_to_dict(r) for r in rows]

        if not trades:
            return {"type": "none", "count": 0, "trades": []}

        # Determine win/loss for the most recent trade
        first = trades[0]
        pnl = first.get("pnl_dollars")
        if pnl is None:
            return {"type": "none", "count": 0, "trades": []}

        streak_type = "win" if pnl >= 0 else "loss"
        streak_trades = [first]

        for trade in trades[1:]:
            t_pnl = trade.get("pnl_dollars")
            if t_pnl is None:
                break
            t_type = "win" if t_pnl >= 0 else "loss"
            if t_type == streak_type:
                streak_trades.append(trade)
            else:
                break

        return {
            "type": streak_type,
            "count": len(streak_trades),
            "trades": streak_trades,
        }
    finally:
        conn.close()
