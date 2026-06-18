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

from fastapi import APIRouter, Depends, HTTPException, Query
from utils.pivot_auth import require_api_key
from pydantic import BaseModel

from database.postgres_client import get_postgres_client

router = APIRouter()

PIVOT_API_KEY = os.getenv("PIVOT_API_KEY", "")


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
async def update_balance(body: BalanceUpdate, _=Depends(require_api_key)):
    pool = await get_postgres_client()
    # COALESCE on optional fields so a balance-only POST (e.g., from the RH
    # balance modal) preserves cash/buying_power/margin_total instead of
    # NULLing them. Backward-compatible — existing callers that send cash
    # explicitly still update it (COALESCE($2, cash) = $2 when $2 is not NULL).
    result = await pool.execute("""
        UPDATE account_balances
        SET balance = $1,
            cash = COALESCE($2, cash),
            buying_power = COALESCE($3, buying_power),
            margin_total = COALESCE($4, margin_total),
            updated_at = NOW(), updated_by = 'pivot_screenshot'
        WHERE account_name = $5
    """, body.balance, body.cash, body.buying_power, body.margin_total, body.account_name)

    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail=f"Account '{body.account_name}' not found")

    row = await pool.fetchrow(
        "SELECT * FROM account_balances WHERE account_name = $1", body.account_name
    )
    return _row_to_dict(row)


# ── 3. GET /positions (reads from unified_positions, mapped to legacy shape) ──

_STOCK_STRUCTURES = {"stock", "stock_long", "long_stock", "stock_short", "short_stock"}


def _v2_to_legacy_dict(row) -> dict:
    """Map a unified_positions row to the legacy open_positions response shape."""
    d = _row_to_dict(row)
    s = (d.get("structure") or "").lower()
    at = (d.get("asset_type") or "").upper()
    is_stock = s in _STOCK_STRUCTURES or (not s and at == "EQUITY")
    has_short_strike = d.get("short_strike") is not None

    # Derive legacy position_type
    if is_stock:
        pos_type = "stock"
    elif has_short_strike:
        pos_type = "option_spread"
    else:
        pos_type = "option"

    # Derive option_type from structure
    option_type = None
    if not is_stock:
        option_type = "Put" if "put" in s else "Call"

    # Derive spread_type from structure
    spread_type = None
    if has_short_strike:
        spread_type = "credit" if "credit" in s else "debit"

    # Compute current_value: current_price × qty × multiplier
    cp = d.get("current_price")
    qty = d.get("quantity") or 0
    multiplier = 1 if is_stock else 100
    current_value = round(cp * multiplier * qty, 2) if cp is not None else None

    # Compute unrealized_pnl_pct
    cost_basis = d.get("cost_basis")
    unrealized_pnl = d.get("unrealized_pnl")
    pnl_pct = None
    if unrealized_pnl is not None and cost_basis and cost_basis != 0:
        pnl_pct = round((unrealized_pnl / abs(cost_basis)) * 100, 2)

    return {
        "id": d.get("id"),
        "ticker": d.get("ticker"),
        "position_type": pos_type,
        "direction": d.get("direction"),
        "quantity": qty,
        "option_type": option_type,
        "strike": d.get("long_strike"),
        "short_strike": d.get("short_strike"),
        "expiry": d.get("expiry"),
        "spread_type": spread_type,
        "cost_basis": cost_basis,
        "cost_per_unit": d.get("entry_price"),
        "current_value": current_value,
        "current_price": cp,
        "unrealized_pnl": unrealized_pnl,
        "unrealized_pnl_pct": pnl_pct,
        "opened_at": d.get("entry_date"),
        "last_updated": d.get("updated_at"),
        "updated_by": d.get("source") or "manual",
        "notes": d.get("notes"),
        "is_active": True,
        "signal_id": d.get("signal_id"),
        "account": (d.get("account") or "robinhood").lower(),
        # Pass through v2-only fields that some consumers may benefit from
        "position_id": d.get("position_id"),
        "structure": d.get("structure"),
        "asset_type": d.get("asset_type"),
        "entry_price": d.get("entry_price"),
    }


@router.get("/positions")
async def get_positions():
    pool = await get_postgres_client()
    rows = await pool.fetch("""
        SELECT * FROM unified_positions
        WHERE status = 'OPEN'
        ORDER BY expiry ASC NULLS LAST, ticker ASC
    """)
    return [_v2_to_legacy_dict(r) for r in rows]


# ── Legacy RH-screenshot position sync — REMOVED 2026-06-17 ──
# POST /positions/sync, POST /positions, POST /positions/close wrote the legacy
# `open_positions` table. Source of truth is now `unified_positions` via the v2 API
# (/v2/positions, /v2/positions/{id}/close). The screenshot flow is unused.
# See docs/codex-briefs/2026-06-17-deprecate-open-positions-table.md

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


# ── 5c. PATCH /positions/closed/{closed_id} — backfill P&L on closed positions ──

class ClosedPositionUpdate(BaseModel):
    exit_value: Optional[float] = None
    exit_price: Optional[float] = None
    pnl_dollars: Optional[float] = None
    pnl_percent: Optional[float] = None
    close_reason: Optional[str] = None
    notes: Optional[str] = None


@router.patch("/positions/closed/{closed_id}")
async def update_closed_position(closed_id: int, body: ClosedPositionUpdate, _=Depends(require_api_key)):
    """Update a closed position — primarily for backfilling exit values and P&L."""
    pool = await get_postgres_client()

    existing = await pool.fetchrow(
        "SELECT * FROM closed_positions WHERE id = $1", closed_id
    )
    if not existing:
        raise HTTPException(status_code=404, detail=f"Closed position {closed_id} not found")

    # Auto-calculate P&L if exit_value provided but pnl not
    exit_val = body.exit_value
    pnl_d = body.pnl_dollars
    pnl_p = body.pnl_percent

    if exit_val is not None and pnl_d is None:
        cost_basis = float(existing["cost_basis"]) if existing.get("cost_basis") else None
        if cost_basis is not None:
            pnl_d = round(exit_val - cost_basis, 2)
            if cost_basis != 0:
                pnl_p = round((pnl_d / abs(cost_basis)) * 100, 2)

    await pool.execute("""
        UPDATE closed_positions
        SET exit_value = COALESCE($1, exit_value),
            exit_price = COALESCE($2, exit_price),
            pnl_dollars = COALESCE($3, pnl_dollars),
            pnl_percent = COALESCE($4, pnl_percent),
            close_reason = COALESCE($5, close_reason),
            notes = COALESCE($6, notes)
        WHERE id = $7
    """, exit_val, body.exit_price, pnl_d, pnl_p,
        body.close_reason, body.notes, closed_id)

    row = await pool.fetchrow("SELECT * FROM closed_positions WHERE id = $1", closed_id)
    return _row_to_dict(row)


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


# ── 8. Cash Flow Logging (withdrawals / deposits) ──

class CashFlowCreate(BaseModel):
    amount: float  # positive = deposit, negative = withdrawal
    flow_type: str = "ACH"  # ACH, WIRE, TRANSFER, ADJUSTMENT
    description: Optional[str] = None
    activity_date: Optional[str] = None  # ISO date, defaults to today
    account_name: str = "Robinhood"
    adjust_balance: bool = True  # auto-adjust account_balances cash


@router.post("/cash-flows")
async def log_cash_flow(body: CashFlowCreate, _=Depends(require_api_key)):
    """Log a withdrawal or deposit. Optionally adjusts account cash balance."""
    pool = await get_postgres_client()

    act_date = date.today()
    if body.activity_date:
        try:
            act_date = date.fromisoformat(body.activity_date)
        except ValueError:
            pass

    row = await pool.fetchrow("""
        INSERT INTO cash_flows (account_name, flow_type, amount, description, activity_date, imported_from)
        VALUES ($1, $2, $3, $4, $5, 'manual')
        RETURNING *
    """, body.account_name, body.flow_type, body.amount, body.description, act_date)

    result = _row_to_dict(row)

    if body.adjust_balance:
        updated = await pool.execute("""
            UPDATE account_balances
            SET cash = cash + $1, balance = balance + $1,
                updated_at = NOW(), updated_by = 'cash_flow'
            WHERE account_name = $2
        """, body.amount, body.account_name)
        result["balance_adjusted"] = updated != "UPDATE 0"

    return result


@router.get("/pnl")
async def get_portfolio_pnl():
    """
    Compare current balances to snapshots for daily, weekly, and monthly PnL.
    Daily = today vs yesterday, Weekly = today vs last Friday,
    Monthly = today vs first snapshot of this month.
    """
    pool = await get_postgres_client()
    from datetime import timedelta

    today = date.today()
    yesterday = today - timedelta(days=1)
    # Walk back to find last business day if yesterday was a weekend
    while yesterday.weekday() >= 5:
        yesterday -= timedelta(days=1)

    # Last Friday
    days_since_friday = (today.weekday() - 4) % 7
    if days_since_friday == 0:
        days_since_friday = 7  # If today is Friday, compare to last Friday
    last_friday = today - timedelta(days=days_since_friday)

    # First of month
    first_of_month = today.replace(day=1)

    # Current balances
    current_rows = await pool.fetch("SELECT account_name, balance FROM account_balances")
    current = {r["account_name"]: float(r["balance"] or 0) for r in current_rows}
    current_total = sum(current.values())

    async def get_snapshot_total(target_date):
        """Get total balance from snapshot on or before target_date."""
        rows = await pool.fetch("""
            SELECT DISTINCT ON (account_name) account_name, balance
            FROM balance_snapshots
            WHERE snapshot_date <= $1
            ORDER BY account_name, snapshot_date DESC
        """, target_date)
        if not rows:
            return None
        return sum(float(r["balance"] or 0) for r in rows)

    daily_snap = await get_snapshot_total(yesterday)
    weekly_snap = await get_snapshot_total(last_friday)
    monthly_snap = await get_snapshot_total(first_of_month)

    def calc_pnl(prev_total):
        if prev_total is None or prev_total == 0:
            return None, None
        dollar = round(current_total - prev_total, 2)
        pct = round((dollar / prev_total) * 100, 2)
        return dollar, pct

    daily_dollar, daily_pct = calc_pnl(daily_snap)
    weekly_dollar, weekly_pct = calc_pnl(weekly_snap)
    monthly_dollar, monthly_pct = calc_pnl(monthly_snap)

    return {
        "current_total": current_total,
        "daily": {"dollar": daily_dollar, "pct": daily_pct, "compare_date": yesterday.isoformat()},
        "weekly": {"dollar": weekly_dollar, "pct": weekly_pct, "compare_date": last_friday.isoformat()},
        "monthly": {"dollar": monthly_dollar, "pct": monthly_pct, "compare_date": first_of_month.isoformat()},
    }


async def snapshot_account_balances():
    """
    Save a daily snapshot of each account balance for PnL tracking.
    Uses UPSERT so running multiple times per day just updates the snapshot.
    Called automatically after mark-to-market during market hours.
    """
    pool = await get_postgres_client()
    import logging
    logger = logging.getLogger(__name__)

    try:
        rows = await pool.fetch("SELECT account_name, balance, cash FROM account_balances")
        today = date.today()
        for r in rows:
            # Compute position_value = balance - cash
            balance = float(r["balance"] or 0)
            cash = float(r["cash"] or 0)
            position_value = round(balance - cash, 2)
            await pool.execute("""
                INSERT INTO balance_snapshots (snapshot_date, account_name, balance, cash, position_value)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (snapshot_date, account_name)
                DO UPDATE SET balance = $3, cash = $4, position_value = $5, created_at = NOW()
            """, today, r["account_name"], balance, cash, position_value)
        logger.info("📸 Balance snapshot saved for %d accounts", len(rows))
    except Exception as e:
        logger.warning("Balance snapshot failed: %s", e)


@router.get("/cash-flows")
async def get_cash_flows(
    account: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """List recent cash flows (withdrawals, deposits)."""
    pool = await get_postgres_client()
    rows = await pool.fetch("""
        SELECT * FROM cash_flows
        WHERE ($1::text IS NULL OR account_name = $1)
        ORDER BY activity_date DESC, id DESC
        LIMIT $2
    """, account, limit)
    return [_row_to_dict(r) for r in rows]
