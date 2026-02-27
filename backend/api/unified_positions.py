"""
Brief 10 — Unified Positions API (v2)
One table, one API, one source of truth for all positions.
Replaces the fragmented positions + open_positions + options_positions system.
"""

from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timezone
from decimal import Decimal
import logging
import json
import os

from database.postgres_client import get_postgres_client
from websocket.broadcaster import manager
from models.position_risk import calculate_position_risk, infer_direction

logger = logging.getLogger(__name__)
router = APIRouter()

PIVOT_API_KEY = os.getenv("PIVOT_API_KEY") or ""


# ── Pydantic models ──────────────────────────────────────────────────

class CreatePositionRequest(BaseModel):
    ticker: str
    asset_type: str = "OPTION"  # EQUITY, OPTION, SPREAD
    structure: Optional[str] = None  # put_credit_spread, long_call, stock, etc.
    direction: Optional[str] = None  # LONG, SHORT, MIXED — auto-inferred if omitted
    legs: Optional[List[Dict[str, Any]]] = None

    entry_price: Optional[float] = None
    quantity: int = 1
    cost_basis: Optional[float] = None

    # Risk — auto-calculated if structure is provided, can be overridden
    max_loss: Optional[float] = None
    max_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None

    # Options-specific
    expiry: Optional[str] = None  # ISO date string
    long_strike: Optional[float] = None
    short_strike: Optional[float] = None

    # Metadata
    source: str = "MANUAL"
    signal_id: Optional[str] = None
    account: str = "ROBINHOOD"
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


class UpdatePositionRequest(BaseModel):
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    current_price: Optional[float] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    quantity: Optional[int] = None


class ClosePositionRequest(BaseModel):
    exit_price: float
    notes: Optional[str] = None


class BulkPositionItem(BaseModel):
    ticker: str
    asset_type: str = "OPTION"
    structure: Optional[str] = None
    direction: Optional[str] = None
    legs: Optional[List[Dict[str, Any]]] = None
    entry_price: Optional[float] = None
    quantity: int = 1
    long_strike: Optional[float] = None
    short_strike: Optional[float] = None
    expiry: Optional[str] = None
    source: str = "CSV_IMPORT"
    notes: Optional[str] = None
    # For closed positions in bulk import
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    status: str = "OPEN"


class BulkRequest(BaseModel):
    positions: List[BulkPositionItem]


class ReconcileItem(BaseModel):
    ticker: str
    position_type: str = "OPTION"
    direction: str = "LONG"
    quantity: int = 1
    option_type: Optional[str] = None
    strike: Optional[float] = None
    short_strike: Optional[float] = None
    expiry: Optional[str] = None
    spread_type: Optional[str] = None
    current_value: Optional[float] = None
    cost_basis: Optional[float] = None


class ReconcileRequest(BaseModel):
    positions: List[ReconcileItem]


# ── Helpers ───────────────────────────────────────────────────────────

def _generate_position_id(ticker: str) -> str:
    now = datetime.now(timezone.utc)
    return f"POS_{ticker.upper()}_{now.strftime('%Y%m%d_%H%M%S')}"


def _row_to_dict(row) -> dict:
    """Convert asyncpg Record to JSON-safe dict."""
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, Decimal):
            d[k] = float(v)
        elif isinstance(v, (datetime, date)):
            d[k] = v.isoformat()
        elif isinstance(v, list) and v and isinstance(v[0], Decimal):
            d[k] = [float(x) for x in v]
    return d


def _compute_unrealized_pnl(entry_price: float, current_price: float, quantity: int, structure: str) -> float:
    """Compute unrealized P&L based on position type."""
    if not entry_price or not current_price:
        return 0.0
    s = (structure or "").lower()
    if s in ("stock", "stock_long", "long_stock", "stock_short", "short_stock"):
        # Stock: (current - entry) * shares
        return round((current_price - entry_price) * quantity, 2)
    # Options: (current - entry) * 100 * contracts
    # For credits: entry is positive (received), current is what you'd pay to close
    # P&L = (entry - current) * 100 * qty for credits
    # P&L = (current - entry) * 100 * qty for debits
    return round((current_price - entry_price) * 100 * quantity, 2)


def _compute_dte(expiry_str: str) -> Optional[int]:
    """Compute days to expiration from date string."""
    if not expiry_str:
        return None
    try:
        exp = date.fromisoformat(str(expiry_str)[:10])
        return max(0, (exp - date.today()).days)
    except (ValueError, TypeError):
        return None


# ── CREATE ────────────────────────────────────────────────────────────

@router.post("/v2/positions")
async def create_position(req: CreatePositionRequest):
    """Create a new position. Auto-calculates max_loss for spreads."""
    pool = await get_postgres_client()

    position_id = _generate_position_id(req.ticker)

    # Auto-infer direction if not provided
    direction = req.direction
    if not direction and req.structure:
        direction = infer_direction(req.structure)
    direction = direction or "LONG"

    # Auto-calculate risk if structure is provided and max_loss not overridden
    max_loss = req.max_loss
    max_profit = req.max_profit
    breakeven = []
    if req.structure and req.entry_price is not None and max_loss is None:
        risk = calculate_position_risk(
            structure=req.structure,
            entry_price=req.entry_price,
            quantity=req.quantity,
            long_strike=req.long_strike,
            short_strike=req.short_strike,
            legs=req.legs,
        )
        max_loss = risk["max_loss"]
        max_profit = max_profit or risk["max_profit"]
        breakeven = risk["breakeven"] or []
        if not req.direction:
            direction = risk["direction"]

    # Compute cost basis if not provided
    cost_basis = req.cost_basis
    if cost_basis is None and req.entry_price is not None:
        s = (req.structure or "").lower()
        if s in ("stock", "stock_long", "long_stock", "stock_short", "short_stock"):
            cost_basis = abs(req.entry_price) * req.quantity
        else:
            cost_basis = abs(req.entry_price) * 100 * req.quantity

    # Parse expiry
    expiry = None
    dte = None
    if req.expiry:
        try:
            expiry = date.fromisoformat(str(req.expiry)[:10])
            dte = max(0, (expiry - date.today()).days)
        except (ValueError, TypeError):
            pass

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO unified_positions (
                position_id, ticker, asset_type, structure, direction, legs,
                entry_price, quantity, cost_basis,
                max_loss, max_profit, stop_loss, target_1, target_2, breakeven,
                expiry, dte, long_strike, short_strike,
                source, signal_id, account, notes, tags
            ) VALUES (
                $1, $2, $3, $4, $5, $6::jsonb,
                $7, $8, $9,
                $10, $11, $12, $13, $14, $15,
                $16, $17, $18, $19,
                $20, $21, $22, $23, $24
            )
            RETURNING *
        """,
            position_id, req.ticker.upper(), req.asset_type, req.structure, direction,
            json.dumps(req.legs) if req.legs else None,
            req.entry_price, req.quantity, cost_basis,
            max_loss, max_profit, req.stop_loss, req.target_1, req.target_2,
            breakeven if breakeven else None,
            expiry, dte, req.long_strike, req.short_strike,
            req.source, req.signal_id, req.account, req.notes,
            req.tags if req.tags else None,
        )

    # If from signal, update signal action
    if req.signal_id:
        try:
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE signals SET user_action = 'SELECTED', updated_at = NOW()
                    WHERE signal_id = $1
                """, req.signal_id)
        except Exception as e:
            logger.warning(f"Could not update signal {req.signal_id}: {e}")

    result = _row_to_dict(row)

    # Broadcast position update
    try:
        await manager.broadcast_position_update({
            "action": "POSITION_OPENED",
            "position": result,
        })
    except Exception:
        pass

    return {"status": "created", "position": result}


# ── READ ──────────────────────────────────────────────────────────────

@router.get("/v2/positions")
async def list_positions(
    status: str = Query("OPEN", description="Filter by status: OPEN, CLOSED, EXPIRED, or ALL"),
    ticker: Optional[str] = Query(None),
    account: Optional[str] = Query(None),
):
    """List positions, filtered by status."""
    pool = await get_postgres_client()

    conditions = []
    params = []
    idx = 1

    if status.upper() != "ALL":
        conditions.append(f"status = ${idx}")
        params.append(status.upper())
        idx += 1

    if ticker:
        conditions.append(f"ticker = ${idx}")
        params.append(ticker.upper())
        idx += 1

    if account:
        conditions.append(f"account = ${idx}")
        params.append(account.upper())
        idx += 1

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT * FROM unified_positions {where}
            ORDER BY
                CASE WHEN status = 'OPEN' THEN 0 ELSE 1 END,
                COALESCE(expiry, '2099-12-31'::date) ASC,
                created_at DESC
        """, *params)

    positions = [_row_to_dict(r) for r in rows]

    # Refresh DTE for open positions
    today = date.today()
    for p in positions:
        if p.get("expiry") and p["status"] == "OPEN":
            try:
                exp = date.fromisoformat(str(p["expiry"])[:10])
                p["dte"] = max(0, (exp - today).days)
            except (ValueError, TypeError):
                pass

    return {"positions": positions, "count": len(positions)}


# ── PORTFOLIO SUMMARY ─────────────────────────────────────────────────
# NOTE: Must be defined BEFORE /v2/positions/{position_id} to avoid
#       "summary" being captured as a position_id path parameter.

@router.get("/v2/positions/summary")
async def portfolio_summary():
    """
    Portfolio summary for the bias row widget and committee context.
    Returns: total positions, capital at risk, net direction, nearest expiry.
    """
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM unified_positions WHERE status = 'OPEN' ORDER BY COALESCE(expiry, '2099-12-31'::date) ASC"
        )

    positions = [_row_to_dict(r) for r in rows]

    if not positions:
        # Fetch account balance even if no positions
        balance = 0.0
        try:
            async with pool.acquire() as conn:
                bal_row = await conn.fetchrow(
                    "SELECT balance FROM account_balances WHERE account_name = 'Robinhood'"
                )
            if bal_row:
                balance = float(bal_row["balance"])
        except Exception:
            pass

        return {
            "account_balance": balance,
            "position_count": 0,
            "capital_at_risk": 0.0,
            "capital_at_risk_pct": 0.0,
            "nearest_expiry": None,
            "nearest_dte": None,
            "net_direction": "FLAT",
            "positions": [],
        }

    # Fetch account balance
    balance = 0.0
    try:
        async with pool.acquire() as conn:
            bal_row = await conn.fetchrow(
                "SELECT balance FROM account_balances WHERE account_name = 'Robinhood'"
            )
        if bal_row:
            balance = float(bal_row["balance"])
    except Exception:
        pass

    # Calculate summary
    total_max_loss = sum(p.get("max_loss") or 0 for p in positions)
    today = date.today()

    # Nearest expiry
    nearest_expiry = None
    nearest_dte = None
    for p in positions:
        if p.get("expiry"):
            try:
                exp = date.fromisoformat(str(p["expiry"])[:10])
                dte = max(0, (exp - today).days)
                if nearest_dte is None or dte < nearest_dte:
                    nearest_dte = dte
                    nearest_expiry = p["expiry"]
            except (ValueError, TypeError):
                pass

    # Net direction
    long_count = sum(1 for p in positions if p.get("direction") == "LONG")
    short_count = sum(1 for p in positions if p.get("direction") == "SHORT")
    mixed_count = sum(1 for p in positions if p.get("direction") == "MIXED")
    if long_count > short_count:
        net_direction = "BULLISH"
    elif short_count > long_count:
        net_direction = "BEARISH"
    else:
        net_direction = "NEUTRAL"

    # Compact position summaries
    summaries = []
    for p in positions:
        dte = None
        if p.get("expiry"):
            try:
                exp = date.fromisoformat(str(p["expiry"])[:10])
                dte = max(0, (exp - today).days)
            except (ValueError, TypeError):
                pass
        summaries.append({
            "position_id": p["position_id"],
            "ticker": p["ticker"],
            "structure": p.get("structure"),
            "direction": p.get("direction"),
            "quantity": p.get("quantity"),
            "long_strike": p.get("long_strike"),
            "short_strike": p.get("short_strike"),
            "expiry": p.get("expiry"),
            "dte": dte,
            "max_loss": p.get("max_loss"),
            "unrealized_pnl": p.get("unrealized_pnl"),
            "entry_price": p.get("entry_price"),
        })

    return {
        "account_balance": balance,
        "position_count": len(positions),
        "capital_at_risk": round(total_max_loss, 2),
        "capital_at_risk_pct": round(total_max_loss / balance * 100, 2) if balance > 0 else 0.0,
        "nearest_expiry": nearest_expiry,
        "nearest_dte": nearest_dte,
        "net_direction": net_direction,
        "direction_breakdown": {"long": long_count, "short": short_count, "mixed": mixed_count},
        "positions": summaries,
    }


@router.get("/v2/positions/greeks")
async def portfolio_greeks():
    """
    Get aggregate portfolio greeks from Polygon.io options snapshots.
    Returns per-ticker and total portfolio greeks for committee context.
    """
    from integrations.polygon_options import get_ticker_greeks_summary, POLYGON_API_KEY

    if not POLYGON_API_KEY:
        raise HTTPException(status_code=503, detail="Polygon API key not configured")

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM unified_positions WHERE status = 'OPEN'"
        )

    if not rows:
        return {"status": "no_positions", "tickers": {}, "portfolio": {}}

    positions = [_row_to_dict(r) for r in rows]

    # Group positions by ticker
    by_ticker: Dict[str, list] = {}
    for p in positions:
        by_ticker.setdefault(p["ticker"], []).append(p)

    ticker_greeks = {}
    total_delta = 0.0
    total_gamma = 0.0
    total_theta = 0.0
    total_vega = 0.0

    for ticker, pos_list in by_ticker.items():
        try:
            result = await get_ticker_greeks_summary(ticker, pos_list)
            if result:
                ticker_greeks[ticker] = result
                total_delta += result.get("net_delta", 0)
                total_gamma += result.get("net_gamma", 0)
                total_theta += result.get("net_theta", 0)
                total_vega += result.get("net_vega", 0)
        except Exception as e:
            logger.warning("Greeks fetch failed for %s: %s", ticker, e)
            ticker_greeks[ticker] = {"error": str(e)}

    return {
        "status": "ok",
        "tickers": ticker_greeks,
        "portfolio": {
            "net_delta": round(total_delta, 2),
            "net_gamma": round(total_gamma, 4),
            "net_theta": round(total_theta, 2),
            "net_vega": round(total_vega, 2),
        },
    }


@router.get("/v2/positions/{position_id}")
async def get_position(position_id: str):
    """Get a single position by ID."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM unified_positions WHERE position_id = $1", position_id
        )
    if not row:
        raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
    return _row_to_dict(row)


# ── UPDATE ────────────────────────────────────────────────────────────

@router.patch("/v2/positions/{position_id}")
async def update_position(position_id: str, req: UpdatePositionRequest):
    """Update position fields. Recalculates unrealized P&L if current_price is updated."""
    pool = await get_postgres_client()

    # Build dynamic SET clause
    sets = ["updated_at = NOW()"]
    params = []
    idx = 1

    if req.stop_loss is not None:
        sets.append(f"stop_loss = ${idx}")
        params.append(req.stop_loss)
        idx += 1
    if req.target_1 is not None:
        sets.append(f"target_1 = ${idx}")
        params.append(req.target_1)
        idx += 1
    if req.target_2 is not None:
        sets.append(f"target_2 = ${idx}")
        params.append(req.target_2)
        idx += 1
    if req.notes is not None:
        sets.append(f"notes = ${idx}")
        params.append(req.notes)
        idx += 1
    if req.tags is not None:
        sets.append(f"tags = ${idx}")
        params.append(req.tags)
        idx += 1
    if req.quantity is not None:
        sets.append(f"quantity = ${idx}")
        params.append(req.quantity)
        idx += 1
    if req.current_price is not None:
        sets.append(f"current_price = ${idx}")
        params.append(req.current_price)
        idx += 1
        sets.append(f"price_updated_at = NOW()")

    if len(sets) <= 1:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(position_id)
    set_clause = ", ".join(sets)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(f"""
            UPDATE unified_positions SET {set_clause}
            WHERE position_id = ${idx} AND status = 'OPEN'
            RETURNING *
        """, *params)

    if not row:
        raise HTTPException(status_code=404, detail=f"Open position {position_id} not found")

    result = _row_to_dict(row)

    # Recalculate unrealized P&L if current_price was updated
    if req.current_price is not None and result.get("entry_price"):
        unrealized = _compute_unrealized_pnl(
            result["entry_price"], req.current_price,
            result["quantity"], result.get("structure", "")
        )
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE unified_positions SET unrealized_pnl = $1 WHERE position_id = $2",
                unrealized, position_id
            )
        result["unrealized_pnl"] = unrealized

    try:
        await manager.broadcast_position_update({
            "action": "POSITION_UPDATED",
            "position": result,
        })
    except Exception:
        pass

    return {"status": "updated", "position": result}


# ── CLOSE (with trade bridge) ─────────────────────────────────────────

@router.post("/v2/positions/{position_id}/close")
async def close_position(position_id: str, req: ClosePositionRequest):
    """
    Close a position: calculate realized P&L, create trades record, update signal if linked.
    This is the close-to-trade bridge (Phase A4).
    """
    pool = await get_postgres_client()

    # Fetch the position
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM unified_positions WHERE position_id = $1 AND status = 'OPEN'",
            position_id
        )
    if not row:
        raise HTTPException(status_code=404, detail=f"Open position {position_id} not found")

    pos = _row_to_dict(row)
    entry_price = pos.get("entry_price") or 0
    structure = pos.get("structure") or ""

    # Calculate realized P&L
    s = structure.lower()
    if s in ("stock", "stock_long", "long_stock", "stock_short", "short_stock"):
        realized_pnl = round((req.exit_price - entry_price) * pos["quantity"], 2)
    else:
        realized_pnl = round((req.exit_price - entry_price) * 100 * pos["quantity"], 2)

    # Determine outcome
    if realized_pnl > 0:
        trade_outcome = "WIN"
    elif realized_pnl < 0:
        trade_outcome = "LOSS"
    else:
        trade_outcome = "BREAKEVEN"

    now = datetime.now(timezone.utc)

    # Create trade record for analytics
    trade_id = None
    try:
        async with pool.acquire() as conn:
            trade_row = await conn.fetchrow("""
                INSERT INTO trades (
                    signal_id, ticker, direction, status, account, structure,
                    signal_source, entry_price, stop_loss, target_1,
                    quantity, opened_at, closed_at, exit_price,
                    pnl_dollars, exit_reason, notes,
                    strike, expiry, short_strike, long_strike, origin
                ) VALUES (
                    $1, $2, $3, 'closed', $4, $5,
                    $6, $7, $8, $9,
                    $10, $11, $12, $13,
                    $14, $15, $16,
                    $17, $18, $19, $20, $21
                )
                RETURNING id
            """,
                pos.get("signal_id"), pos["ticker"], pos["direction"],
                pos.get("account", "ROBINHOOD"), pos.get("structure"),
                pos.get("source", "MANUAL"),
                entry_price, pos.get("stop_loss"), pos.get("target_1"),
                pos["quantity"],
                datetime.fromisoformat(pos["entry_date"]) if isinstance(pos.get("entry_date"), str) else pos.get("entry_date", now),
                now, req.exit_price,
                realized_pnl, req.notes or "Closed via unified positions",
                req.notes,
                pos.get("long_strike") or pos.get("short_strike"),
                date.fromisoformat(str(pos["expiry"])[:10]) if pos.get("expiry") else None,
                pos.get("short_strike"), pos.get("long_strike"),
                "position_ledger",
            )
            trade_id = trade_row["id"] if trade_row else None
    except Exception as e:
        logger.warning(f"Could not create trade record: {e}")

    # Close the position
    async with pool.acquire() as conn:
        updated = await conn.fetchrow("""
            UPDATE unified_positions SET
                status = 'CLOSED',
                exit_price = $1,
                exit_date = $2,
                realized_pnl = $3,
                trade_outcome = $4,
                trade_id = $5,
                notes = COALESCE($6, notes),
                updated_at = NOW()
            WHERE position_id = $7
            RETURNING *
        """, req.exit_price, now, realized_pnl, trade_outcome,
            trade_id, req.notes, position_id)

    # Update linked signal outcome if applicable
    if pos.get("signal_id"):
        try:
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE signals SET
                        trade_outcome = $1,
                        actual_exit_price = $2,
                        notes = COALESCE(notes || ' | ', '') || $3,
                        updated_at = NOW()
                    WHERE signal_id = $4
                """, trade_outcome, req.exit_price,
                    f"Closed: {trade_outcome} (${realized_pnl:+.2f})",
                    pos["signal_id"])
        except Exception as e:
            logger.warning(f"Could not update signal outcome: {e}")

    result = _row_to_dict(updated) if updated else pos

    try:
        await manager.broadcast_position_update({
            "action": "POSITION_CLOSED",
            "position": result,
        })
    except Exception:
        pass

    return {
        "status": "closed",
        "position": result,
        "trade_id": trade_id,
        "realized_pnl": realized_pnl,
        "trade_outcome": trade_outcome,
    }


# ── DELETE ────────────────────────────────────────────────────────────

@router.delete("/v2/positions/{position_id}")
async def delete_position(position_id: str):
    """Delete a position (for errors/test data). No trade record created."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM unified_positions WHERE position_id = $1", position_id
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail=f"Position {position_id} not found")

    try:
        await manager.broadcast_position_update({
            "action": "POSITION_DELETED",
            "position_id": position_id,
        })
    except Exception:
        pass

    return {"status": "deleted", "position_id": position_id}


# ── BULK OPERATIONS ───────────────────────────────────────────────────

@router.post("/v2/positions/bulk")
async def bulk_create_positions(req: BulkRequest):
    """Create or update multiple positions at once (CSV import, screenshot sync)."""
    pool = await get_postgres_client()
    created = []
    errors = []

    for item in req.positions:
        try:
            position_id = _generate_position_id(item.ticker)

            # Infer direction
            direction = item.direction or (infer_direction(item.structure) if item.structure else "LONG")

            # Calculate risk
            max_loss = None
            max_profit = None
            breakeven = []
            if item.structure and item.entry_price is not None:
                risk = calculate_position_risk(
                    structure=item.structure,
                    entry_price=item.entry_price,
                    quantity=item.quantity,
                    long_strike=item.long_strike,
                    short_strike=item.short_strike,
                    legs=item.legs,
                )
                max_loss = risk["max_loss"]
                max_profit = risk["max_profit"]
                breakeven = risk["breakeven"] or []

            expiry = None
            dte = None
            if item.expiry:
                try:
                    expiry = date.fromisoformat(str(item.expiry)[:10])
                    dte = max(0, (expiry - date.today()).days)
                except (ValueError, TypeError):
                    pass

            # Handle closed positions from CSV import
            exit_price = item.exit_price
            exit_date_val = None
            realized_pnl = None
            trade_outcome = None
            status = item.status.upper()

            if status == "CLOSED" and exit_price is not None and item.entry_price is not None:
                s = (item.structure or "").lower()
                if s in ("stock", "stock_long", "long_stock"):
                    realized_pnl = round((exit_price - item.entry_price) * item.quantity, 2)
                else:
                    realized_pnl = round((exit_price - item.entry_price) * 100 * item.quantity, 2)
                trade_outcome = "WIN" if realized_pnl > 0 else ("LOSS" if realized_pnl < 0 else "BREAKEVEN")
                if item.exit_date:
                    try:
                        exit_date_val = datetime.fromisoformat(item.exit_date)
                    except (ValueError, TypeError):
                        exit_date_val = datetime.now(timezone.utc)
                else:
                    exit_date_val = datetime.now(timezone.utc)

            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO unified_positions (
                        position_id, ticker, asset_type, structure, direction, legs,
                        entry_price, quantity, max_loss, max_profit, breakeven,
                        expiry, dte, long_strike, short_strike,
                        source, notes, status,
                        exit_price, exit_date, realized_pnl, trade_outcome
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6::jsonb,
                        $7, $8, $9, $10, $11,
                        $12, $13, $14, $15,
                        $16, $17, $18,
                        $19, $20, $21, $22
                    )
                """,
                    position_id, item.ticker.upper(), item.asset_type,
                    item.structure, direction,
                    json.dumps(item.legs) if item.legs else None,
                    item.entry_price, item.quantity, max_loss, max_profit,
                    breakeven if breakeven else None,
                    expiry, dte, item.long_strike, item.short_strike,
                    item.source, item.notes, status,
                    exit_price, exit_date_val, realized_pnl, trade_outcome,
                )

            created.append({"position_id": position_id, "ticker": item.ticker, "status": status})
        except Exception as e:
            errors.append({"ticker": item.ticker, "error": str(e)})

    return {
        "status": "bulk_complete",
        "created": len(created),
        "errors": len(errors),
        "positions": created,
        "error_details": errors,
    }


# ── RECONCILE (screenshot sync) ──────────────────────────────────────

@router.post("/v2/positions/reconcile")
async def reconcile_positions(req: ReconcileRequest):
    """
    Reconcile incoming positions (from screenshot) against existing.
    Match by ticker+strike+expiry+direction. Update values, create new, flag missing.
    """
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        existing = await conn.fetch(
            "SELECT * FROM unified_positions WHERE status = 'OPEN'"
        )
    existing_positions = [_row_to_dict(r) for r in existing]

    matched = []
    created = []
    missing = []

    # Build lookup of existing positions by (ticker, strike, expiry)
    existing_lookup = {}
    for ep in existing_positions:
        key = (
            ep["ticker"],
            float(ep.get("long_strike") or ep.get("short_strike") or 0),
            str(ep.get("expiry") or ""),
        )
        existing_lookup[key] = ep

    incoming_keys = set()
    for item in req.positions:
        key = (
            item.ticker.upper(),
            float(item.strike or item.short_strike or 0),
            str(item.expiry or ""),
        )
        incoming_keys.add(key)

        if key in existing_lookup:
            # Update existing position with current value
            ep = existing_lookup[key]
            updates = {}
            if item.current_value is not None:
                updates["current_price"] = item.current_value
                if ep.get("entry_price"):
                    updates["unrealized_pnl"] = _compute_unrealized_pnl(
                        ep["entry_price"], item.current_value,
                        ep["quantity"], ep.get("structure", "")
                    )
            if updates:
                set_parts = []
                params = []
                pidx = 1
                for k, v in updates.items():
                    set_parts.append(f"{k} = ${pidx}")
                    params.append(v)
                    pidx += 1
                set_parts.append("price_updated_at = NOW()")
                set_parts.append("updated_at = NOW()")
                params.append(ep["position_id"])
                async with pool.acquire() as conn:
                    await conn.execute(
                        f"UPDATE unified_positions SET {', '.join(set_parts)} WHERE position_id = ${pidx}",
                        *params
                    )
            matched.append({
                "ticker": item.ticker,
                "position_id": ep["position_id"],
                "updated_value": item.current_value,
            })
        else:
            # New position from screenshot
            position_id = _generate_position_id(item.ticker)
            structure = item.spread_type or ("stock" if item.position_type == "STOCK" else "long_call")
            direction = item.direction or "LONG"

            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO unified_positions (
                        position_id, ticker, asset_type, structure, direction,
                        entry_price, quantity, cost_basis, current_price,
                        expiry, long_strike, short_strike,
                        source, status
                    ) VALUES (
                        $1, $2, $3, $4, $5,
                        $6, $7, $8, $9,
                        $10, $11, $12,
                        'SCREENSHOT_SYNC', 'OPEN'
                    )
                """,
                    position_id, item.ticker.upper(), item.position_type,
                    structure, direction,
                    item.cost_basis, item.quantity, item.cost_basis, item.current_value,
                    date.fromisoformat(str(item.expiry)[:10]) if item.expiry else None,
                    item.strike, item.short_strike,
                )
            created.append({"ticker": item.ticker, "position_id": position_id})

    # Flag existing positions not in screenshot
    for key, ep in existing_lookup.items():
        if key not in incoming_keys and ep.get("source") != "MANUAL":
            missing.append({
                "ticker": ep["ticker"],
                "position_id": ep["position_id"],
                "structure": ep.get("structure"),
            })

    return {
        "matched": matched,
        "created": created,
        "missing": missing,
        "summary": {
            "matched_count": len(matched),
            "created_count": len(created),
            "missing_count": len(missing),
        }
    }


# ── MARK TO MARKET ────────────────────────────────────────────────────

@router.post("/v2/positions/mark-to-market")
async def mark_to_market():
    """
    Fetch current spread values via Polygon.io options snapshots.
    Falls back to yfinance underlying price for equity positions.
    Updates unrealized P&L based on actual spread mid-prices.
    """
    from integrations.polygon_options import (
        get_spread_value, get_single_option_value, POLYGON_API_KEY
    )

    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM unified_positions WHERE status = 'OPEN'"
        )

    if not rows:
        return {"status": "no_open_positions", "updated": 0}

    updated = 0
    errors = []
    use_polygon = bool(POLYGON_API_KEY)

    # Cache chain snapshots per ticker to avoid duplicate API calls
    for row in rows:
        ticker = row["ticker"]
        structure = (row.get("structure") or "").lower()
        entry_price = float(row["entry_price"]) if row["entry_price"] else None
        quantity = row["quantity"]
        expiry = row.get("expiry")
        long_strike = float(row["long_strike"]) if row.get("long_strike") else None
        short_strike = float(row["short_strike"]) if row.get("short_strike") else None

        if entry_price is None:
            continue

        current_price = None
        unrealized = None
        greeks_json = None

        # --- Polygon path: real spread-level pricing ---
        if use_polygon and expiry and long_strike:
            try:
                if short_strike and ("spread" in structure or "credit" in structure or "debit" in structure):
                    # Spread position — get both legs
                    result = await get_spread_value(
                        ticker, long_strike, short_strike, str(expiry), structure
                    )
                    if result and result.get("spread_value") is not None:
                        current_price = result["spread_value"]
                        # P&L = (current_spread - entry_debit) * 100 * qty for debits
                        # P&L = (entry_credit - current_cost_to_close) * 100 * qty for credits
                        if "credit" in structure:
                            unrealized = round((entry_price - current_price) * 100 * quantity, 2)
                        else:
                            unrealized = round((current_price - entry_price) * 100 * quantity, 2)

                        greeks_json = json.dumps({
                            "long": result.get("long_greeks"),
                            "short": result.get("short_greeks"),
                            "underlying_price": result.get("underlying_price"),
                        })

                else:
                    # Single leg (long_put, long_call, etc.)
                    opt_type = "put" if "put" in structure else "call"
                    result = await get_single_option_value(
                        ticker, long_strike, str(expiry), opt_type
                    )
                    if result and result.get("option_value") is not None:
                        current_price = result["option_value"]
                        unrealized = round((current_price - entry_price) * 100 * quantity, 2)
                        greeks_json = json.dumps({
                            "greeks": result.get("greeks"),
                            "underlying_price": result.get("underlying_price"),
                        })

            except Exception as e:
                errors.append({"position_id": row["position_id"], "error": str(e)})
                logger.warning("Polygon mark-to-market failed for %s: %s", row["position_id"], e)

        # --- Fallback: yfinance for equity or if Polygon failed ---
        if current_price is None and structure in ("stock", "stock_long", "long_stock", "stock_short", "short_stock", ""):
            try:
                import yfinance as yf
                t = yf.Ticker(ticker)
                info = t.fast_info
                if hasattr(info, 'last_price') and info.last_price:
                    current_price = float(info.last_price)
                    unrealized = _compute_unrealized_pnl(
                        entry_price, current_price, quantity, structure
                    )
            except Exception:
                pass

        if current_price is not None and unrealized is not None:
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE unified_positions SET
                        current_price = $1, unrealized_pnl = $2,
                        price_updated_at = NOW(), updated_at = NOW()
                    WHERE position_id = $3
                """, current_price, unrealized, row["position_id"])
            updated += 1

    result = {"status": "updated", "updated": updated, "source": "polygon" if use_polygon else "yfinance"}
    if errors:
        result["errors"] = errors
    return result


