"""
Portfolio API — Account balances, open positions, and trade history.

Brief 07-B: Powers the frontend dashboard and Pivot's screenshot-based sync.
"""

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from database.postgres_client import get_postgres_client

router = APIRouter()

PIVOT_API_KEY = os.getenv("PIVOT_API_KEY", "")


def verify_api_key(x_api_key: str = Header(None)):
    if PIVOT_API_KEY and x_api_key != PIVOT_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


def _row_to_dict(row) -> dict:
    """Convert an asyncpg Record to a JSON-safe dict."""
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, Decimal):
            d[k] = float(v)
        elif isinstance(v, (datetime, date)):
            d[k] = v.isoformat()
    return d


# ── 1. GET /balances ──

@router.get("/balances")
async def get_balances():
    pool = await get_postgres_client()
    rows = await pool.fetch("""
        SELECT account_name, broker, balance, cash, buying_power, margin_total, updated_at, updated_by
        FROM account_balances
        ORDER BY CASE broker WHEN 'robinhood' THEN 0 ELSE 1 END, account_name
    """)
    return [_row_to_dict(r) for r in rows]


# ── 2. POST /balances/update ──

class BalanceUpdate(BaseModel):
    account_name: str
    balance: float
    cash: Optional[float] = None
    buying_power: Optional[float] = None
    margin_total: Optional[float] = None


@router.post("/balances/update")
async def update_balance(body: BalanceUpdate, _=Depends(verify_api_key)):
    pool = await get_postgres_client()
    result = await pool.execute("""
        UPDATE account_balances
        SET balance = $1, cash = $2, buying_power = $3, margin_total = $4,
            updated_at = NOW(), updated_by = 'pivot_screenshot'
        WHERE account_name = $5
    """, body.balance, body.cash, body.buying_power, body.margin_total, body.account_name)

    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail=f"Account '{body.account_name}' not found")

    row = await pool.fetchrow(
        "SELECT * FROM account_balances WHERE account_name = $1", body.account_name
    )
    return _row_to_dict(row)


# ── 3. GET /positions ──

@router.get("/positions")
async def get_positions():
    pool = await get_postgres_client()
    rows = await pool.fetch("""
        SELECT * FROM open_positions
        WHERE is_active = TRUE
        ORDER BY expiry ASC NULLS LAST, ticker ASC
    """)
    return [_row_to_dict(r) for r in rows]


# ── 4. POST /positions/sync ──

class PositionData(BaseModel):
    ticker: str
    position_type: str
    direction: str
    quantity: int
    option_type: Optional[str] = None
    strike: Optional[float] = None
    expiry: Optional[str] = None
    spread_type: Optional[str] = None
    short_strike: Optional[float] = None
    cost_basis: float
    cost_per_unit: Optional[float] = None
    current_value: Optional[float] = None
    current_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    notes: Optional[str] = None


class PositionSync(BaseModel):
    positions: list[PositionData]


@router.post("/positions/sync")
async def sync_positions(body: PositionSync, _=Depends(verify_api_key)):
    pool = await get_postgres_client()

    # Fetch current active positions
    db_positions = await pool.fetch(
        "SELECT * FROM open_positions WHERE is_active = TRUE"
    )

    added = []
    updated = []
    closed = []

    # Track which DB positions were matched
    matched_db_ids = set()

    for pos in body.positions:
        expiry_date = None
        if pos.expiry:
            try:
                expiry_date = date.fromisoformat(pos.expiry)
            except ValueError:
                pass

        # Try to match existing position
        match = None
        for db_row in db_positions:
            if db_row["id"] in matched_db_ids:
                continue
            if (
                db_row["ticker"] == pos.ticker
                and _decimal_eq(db_row.get("strike"), pos.strike)
                and _date_eq(db_row.get("expiry"), expiry_date)
                and _decimal_eq(db_row.get("short_strike"), pos.short_strike)
                and db_row["direction"] == pos.direction
            ):
                match = db_row
                matched_db_ids.add(db_row["id"])
                break

        if match:
            # Update existing
            await pool.execute("""
                UPDATE open_positions
                SET current_value = $1, current_price = $2,
                    unrealized_pnl = $3, unrealized_pnl_pct = $4,
                    last_updated = NOW(), updated_by = 'pivot_screenshot'
                WHERE id = $5
            """, pos.current_value, pos.current_price,
                pos.unrealized_pnl, pos.unrealized_pnl_pct, match["id"])
            updated.append(pos.ticker)
        else:
            # Insert new
            await pool.execute("""
                INSERT INTO open_positions
                    (ticker, position_type, direction, quantity, option_type, strike,
                     expiry, spread_type, short_strike, cost_basis, cost_per_unit,
                     current_value, current_price, unrealized_pnl, unrealized_pnl_pct,
                     updated_by, notes)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, 'pivot_screenshot', $16)
            """, pos.ticker, pos.position_type, pos.direction, pos.quantity,
                pos.option_type, pos.strike, expiry_date, pos.spread_type,
                pos.short_strike, pos.cost_basis, pos.cost_per_unit,
                pos.current_value, pos.current_price, pos.unrealized_pnl,
                pos.unrealized_pnl_pct, pos.notes)
            added.append(pos.ticker)

    # Close positions not in incoming list
    for db_row in db_positions:
        if db_row["id"] not in matched_db_ids:
            await pool.execute(
                "UPDATE open_positions SET is_active = FALSE, last_updated = NOW() WHERE id = $1",
                db_row["id"],
            )
            closed.append(db_row["ticker"])

    return {"added": added, "updated": updated, "closed": closed}


def _decimal_eq(db_val, api_val) -> bool:
    """Compare a DB decimal and an API float, treating None == None."""
    if db_val is None and api_val is None:
        return True
    if db_val is None or api_val is None:
        return False
    return float(db_val) == float(api_val)


def _date_eq(db_val, api_val) -> bool:
    """Compare a DB date and an API date."""
    if db_val is None and api_val is None:
        return True
    if db_val is None or api_val is None:
        return False
    return db_val == api_val


# ── 5. POST /positions/close ──

class PositionClose(BaseModel):
    ticker: str
    strike: Optional[float] = None
    expiry: Optional[str] = None
    short_strike: Optional[float] = None
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    realized_pnl: Optional[float] = None
    notes: Optional[str] = None


@router.post("/positions/close")
async def close_position(body: PositionClose, _=Depends(verify_api_key)):
    pool = await get_postgres_client()

    expiry_date = None
    if body.expiry:
        try:
            expiry_date = date.fromisoformat(body.expiry)
        except ValueError:
            pass

    # Find matching active position
    rows = await pool.fetch(
        "SELECT * FROM open_positions WHERE is_active = TRUE AND ticker = $1",
        body.ticker,
    )

    match = None
    for row in rows:
        if (
            _decimal_eq(row.get("strike"), body.strike)
            and _date_eq(row.get("expiry"), expiry_date)
            and _decimal_eq(row.get("short_strike"), body.short_strike)
        ):
            match = row
            break

    if not match:
        raise HTTPException(status_code=404, detail=f"No active position found for {body.ticker}")

    close_notes = []
    if match.get("notes"):
        close_notes.append(match["notes"])
    if body.exit_price is not None:
        close_notes.append(f"Exit: ${body.exit_price}")
    if body.exit_date:
        close_notes.append(f"Date: {body.exit_date}")
    if body.realized_pnl is not None:
        close_notes.append(f"P&L: ${body.realized_pnl}")
    if body.notes:
        close_notes.append(body.notes)

    await pool.execute("""
        UPDATE open_positions
        SET is_active = FALSE, notes = $1, last_updated = NOW()
        WHERE id = $2
    """, " | ".join(close_notes) if close_notes else None, match["id"])

    return {"closed": body.ticker, "id": match["id"]}


# ── 6. GET /trade-history ──

@router.get("/trade-history")
async def get_trade_history(
    ticker: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    is_option: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    pool = await get_postgres_client()

    start_d = None
    end_d = None
    if start_date:
        try:
            start_d = date.fromisoformat(start_date)
        except ValueError:
            pass
    if end_date:
        try:
            end_d = date.fromisoformat(end_date)
        except ValueError:
            pass

    rows = await pool.fetch("""
        SELECT * FROM rh_trade_history
        WHERE ($1::text IS NULL OR ticker = $1)
          AND ($2::date IS NULL OR activity_date >= $2)
          AND ($3::date IS NULL OR activity_date <= $3)
          AND ($4::boolean IS NULL OR is_option = $4)
        ORDER BY activity_date DESC, id DESC
        LIMIT $5 OFFSET $6
    """, ticker, start_d, end_d, is_option, limit, offset)

    return [_row_to_dict(r) for r in rows]


# ── 7. GET /trade-history/stats ──

@router.get("/trade-history/stats")
async def get_trade_history_stats():
    pool = await get_postgres_client()

    stats = await pool.fetchrow("""
        SELECT
            COUNT(*) AS total_trades,
            COUNT(*) FILTER (WHERE is_option = TRUE) AS total_option_trades,
            COUNT(*) FILTER (WHERE is_option = FALSE) AS total_stock_trades,
            COUNT(DISTINCT ticker) AS unique_tickers,
            MIN(activity_date) AS date_start,
            MAX(activity_date) AS date_end
        FROM rh_trade_history
    """)

    cf_total = await pool.fetchval(
        "SELECT COALESCE(SUM(amount), 0) FROM cash_flows"
    )

    return {
        "total_trades": stats["total_trades"],
        "total_option_trades": stats["total_option_trades"],
        "total_stock_trades": stats["total_stock_trades"],
        "unique_tickers": stats["unique_tickers"],
        "date_range": {
            "start": stats["date_start"].isoformat() if stats["date_start"] else None,
            "end": stats["date_end"].isoformat() if stats["date_end"] else None,
        },
        "total_cash_flows": float(cf_total),
    }
