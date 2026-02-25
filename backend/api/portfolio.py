"""
Portfolio API — Account balances, open positions, and trade history.

Brief 07-B: Powers the frontend dashboard and Pivot's screenshot-based sync.
Brief 10: Gap fixes — signal_id/account columns, partial sync, single create,
          closed_positions table with proper P&L, rewritten close endpoint.
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
    cost_basis: Optional[float] = None
    cost_per_unit: Optional[float] = None
    current_value: Optional[float] = None
    current_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    notes: Optional[str] = None
    signal_id: Optional[str] = None
    account: Optional[str] = None


class PositionSync(BaseModel):
    positions: list[PositionData]
    partial: bool = False
    account: Optional[str] = None


@router.post("/positions/sync")
async def sync_positions(body: PositionSync, _=Depends(verify_api_key)):
    pool = await get_postgres_client()

    # Fetch current active positions, filtered by account if specified
    if body.account:
        db_positions = await pool.fetch(
            "SELECT * FROM open_positions WHERE is_active = TRUE AND (account = $1 OR account IS NULL)",
            body.account,
        )
    else:
        db_positions = await pool.fetch(
            "SELECT * FROM open_positions WHERE is_active = TRUE"
        )

    added = []
    updated = []
    closed = []
    possibly_closed = []

    # Track which DB positions were matched
    matched_db_ids = set()

    for pos in body.positions:
        expiry_date = None
        if pos.expiry:
            try:
                expiry_date = date.fromisoformat(pos.expiry)
            except ValueError:
                pass

        pos_account = pos.account or "robinhood"

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
                and (db_row.get("account") or "robinhood") == pos_account
            ):
                match = db_row
                matched_db_ids.add(db_row["id"])
                break

        if match:
            # Update existing — refresh price data AND cost/quantity
            await pool.execute("""
                UPDATE open_positions
                SET current_value = COALESCE($1, current_value),
                    current_price = COALESCE($2, current_price),
                    unrealized_pnl = COALESCE($3, unrealized_pnl),
                    unrealized_pnl_pct = COALESCE($4, unrealized_pnl_pct),
                    cost_basis = COALESCE($5, cost_basis),
                    cost_per_unit = COALESCE($6, cost_per_unit),
                    quantity = $7,
                    last_updated = NOW(), updated_by = 'pivot_screenshot'
                WHERE id = $8
            """, pos.current_value, pos.current_price,
                pos.unrealized_pnl, pos.unrealized_pnl_pct,
                pos.cost_basis, pos.cost_per_unit,
                pos.quantity, match["id"])
            updated.append(pos.ticker)
        else:
            # Insert new
            await pool.execute("""
                INSERT INTO open_positions
                    (ticker, position_type, direction, quantity, option_type, strike,
                     expiry, spread_type, short_strike, cost_basis, cost_per_unit,
                     current_value, current_price, unrealized_pnl, unrealized_pnl_pct,
                     updated_by, notes, signal_id, account)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, 'pivot_screenshot', $16, $17, $18)
            """, pos.ticker, pos.position_type, pos.direction, pos.quantity,
                pos.option_type, pos.strike, expiry_date, pos.spread_type,
                pos.short_strike, pos.cost_basis, pos.cost_per_unit,
                pos.current_value, pos.current_price, pos.unrealized_pnl,
                pos.unrealized_pnl_pct, pos.notes, pos.signal_id,
                pos.account or "robinhood")
            added.append(pos.ticker)

    # Close positions not in incoming list
    # Skip if partial=True (screenshot may not show all positions)
    if not body.partial:
        for db_row in db_positions:
            if db_row["id"] not in matched_db_ids:
                # If account filter is set, only close positions from that account
                if body.account and (db_row.get("account") or "robinhood") != body.account:
                    continue
                await pool.execute(
                    "UPDATE open_positions SET is_active = FALSE, last_updated = NOW() WHERE id = $1",
                    db_row["id"],
                )
                closed.append(db_row["ticker"])
    else:
        # In partial mode, report what's missing but don't close
        for db_row in db_positions:
            if db_row["id"] not in matched_db_ids:
                if body.account and (db_row.get("account") or "robinhood") != body.account:
                    continue
                possibly_closed.append({
                    "id": db_row["id"],
                    "ticker": db_row["ticker"],
                    "strike": float(db_row["strike"]) if db_row.get("strike") else None,
                    "short_strike": float(db_row["short_strike"]) if db_row.get("short_strike") else None,
                    "expiry": db_row["expiry"].isoformat() if db_row.get("expiry") else None,
                    "direction": db_row["direction"],
                })

    return {
        "added": added,
        "updated": updated,
        "closed": closed,
        "possibly_closed": possibly_closed if body.partial else [],
    }


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


# ── 4b. POST /positions (single create) ──

class SinglePositionCreate(BaseModel):
    ticker: str
    position_type: str
    direction: str
    quantity: int
    option_type: Optional[str] = None
    strike: Optional[float] = None
    expiry: Optional[str] = None
    spread_type: Optional[str] = None
    short_strike: Optional[float] = None
    cost_basis: Optional[float] = None
    cost_per_unit: Optional[float] = None
    current_value: Optional[float] = None
    current_price: Optional[float] = None
    signal_id: Optional[str] = None
    account: str = "robinhood"
    notes: Optional[str] = None


@router.post("/positions")
async def create_position(body: SinglePositionCreate, _=Depends(verify_api_key)):
    pool = await get_postgres_client()

    expiry_date = None
    if body.expiry:
        try:
            expiry_date = date.fromisoformat(body.expiry)
        except ValueError:
            pass

    # Check for duplicate
    existing = await pool.fetchrow("""
        SELECT id FROM open_positions
        WHERE is_active = TRUE
          AND ticker = $1
          AND direction = $2
          AND COALESCE(strike, 0) = COALESCE($3::numeric, 0)
          AND COALESCE(short_strike, 0) = COALESCE($4::numeric, 0)
          AND COALESCE(expiry, '1970-01-01') = COALESCE($5::date, '1970-01-01')
          AND account = $6
    """, body.ticker, body.direction, body.strike, body.short_strike,
        expiry_date, body.account)

    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Position already exists (id={existing['id']}). Use sync to update."
        )

    row = await pool.fetchrow("""
        INSERT INTO open_positions
            (ticker, position_type, direction, quantity, option_type, strike,
             expiry, spread_type, short_strike, cost_basis, cost_per_unit,
             current_value, current_price, updated_by, signal_id, account, notes)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                'committee_take', $14, $15, $16)
        RETURNING *
    """, body.ticker, body.position_type, body.direction, body.quantity,
        body.option_type, body.strike, expiry_date, body.spread_type,
        body.short_strike, body.cost_basis, body.cost_per_unit,
        body.current_value, body.current_price,
        body.signal_id, body.account, body.notes)

    return _row_to_dict(row)


# ── 5. POST /positions/close ──

class PositionClose(BaseModel):
    ticker: str
    strike: Optional[float] = None
    expiry: Optional[str] = None
    short_strike: Optional[float] = None
    direction: Optional[str] = None
    exit_value: Optional[float] = None
    exit_price: Optional[float] = None
    close_reason: Optional[str] = "manual"
    closed_at: Optional[str] = None
    account: Optional[str] = None
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

    close_dt = None
    if body.closed_at:
        try:
            close_dt = datetime.fromisoformat(body.closed_at)
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
            if body.direction and row["direction"] != body.direction:
                continue
            if body.account and (row.get("account") or "robinhood") != body.account:
                continue
            match = row
            break

    if not match:
        raise HTTPException(status_code=404, detail=f"No active position found for {body.ticker}")

    # Compute PnL
    cost_basis = float(match["cost_basis"]) if match.get("cost_basis") else None
    pnl_dollars = None
    pnl_percent = None
    if body.exit_value is not None and cost_basis is not None:
        pnl_dollars = round(body.exit_value - cost_basis, 2)
        if cost_basis != 0:
            pnl_percent = round((pnl_dollars / abs(cost_basis)) * 100, 2)

    # Compute hold days
    opened_at = match.get("opened_at")
    hold_days = None
    if opened_at and close_dt:
        hold_days = (close_dt.date() - opened_at.date()).days if hasattr(opened_at, "date") else None
    elif opened_at:
        hold_days = (datetime.now().date() - opened_at.date()).days if hasattr(opened_at, "date") else None

    # Insert into closed_positions
    closed_row = await pool.fetchrow("""
        INSERT INTO closed_positions
            (position_id, ticker, position_type, direction, quantity,
             option_type, strike, short_strike, expiry, spread_type,
             cost_basis, exit_value, exit_price, pnl_dollars, pnl_percent,
             opened_at, closed_at, hold_days, signal_id, account,
             close_reason, notes)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                $14, $15, $16, COALESCE($17, NOW()), $18, $19, $20, $21, $22)
        RETURNING *
    """, match["id"], match["ticker"], match["position_type"], match["direction"],
        match["quantity"], match.get("option_type"),
        float(match["strike"]) if match.get("strike") else None,
        float(match["short_strike"]) if match.get("short_strike") else None,
        match.get("expiry"), match.get("spread_type"),
        cost_basis, body.exit_value, body.exit_price,
        pnl_dollars, pnl_percent,
        opened_at, close_dt, hold_days,
        match.get("signal_id"), match.get("account") or "robinhood",
        body.close_reason, body.notes)

    # Mark open position as inactive
    await pool.execute(
        "UPDATE open_positions SET is_active = FALSE, last_updated = NOW() WHERE id = $1",
        match["id"],
    )

    return _row_to_dict(closed_row)


# ── 5b. GET /positions/closed ──

@router.get("/positions/closed")
async def get_closed_positions(
    ticker: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    pool = await get_postgres_client()
    rows = await pool.fetch("""
        SELECT * FROM closed_positions
        WHERE ($1::text IS NULL OR ticker = $1)
        ORDER BY closed_at DESC
        LIMIT $2
    """, ticker, limit)
    return [_row_to_dict(r) for r in rows]


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
