"""
Brief 10 — Unified Positions API (v2)
One table, one API, one source of truth for all positions.
Replaces the fragmented positions + open_positions + options_positions system.
"""

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from utils.pivot_auth import require_api_key
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
import asyncio
import logging
import json
import os

from database.postgres_client import get_postgres_client
from database.redis_client import get_redis_client
from websocket.broadcaster import manager
from models.position_risk import calculate_position_risk, infer_direction

logger = logging.getLogger(__name__)
router = APIRouter()

# Structures where entry_price is credit received — PnL flips: (entry - exit) * 100 * qty
CREDIT_STRUCTURES = frozenset({
    "credit_spread", "put_credit_spread", "bull_put_spread",
    "call_credit_spread", "bear_call_spread",
    "iron_condor", "iron_butterfly",
    "short_call", "naked_call", "short_put", "naked_put",
    "cash_secured_put", "covered_call",
})

PIVOT_API_KEY = os.getenv("PIVOT_API_KEY") or ""

# Robust account name matching — handles case and naming variations
ACCOUNT_DISPLAY_MAP = {
    "ROBINHOOD": ["robinhood", "rh", "robinhood - individual"],
    "FIDELITY_ROTH": ["fidelity roth"],
    "FIDELITY_401A": ["fidelity 401a"],
    "FIDELITY": ["fidelity", "fidelity - individual", "fid"],  # legacy fallback
}


def _match_account_balance(account_filter: str, balance_name: str) -> bool:
    """Check if a balance row name matches the requested account filter."""
    filter_upper = account_filter.upper()
    name_lower = balance_name.lower().strip()
    aliases = ACCOUNT_DISPLAY_MAP.get(filter_upper, [])
    # Normalize underscores to spaces for startsWith matching (FIDELITY_ROTH → fidelity roth)
    filter_normalized = filter_upper.lower().replace("_", " ")
    return name_lower in aliases or name_lower.startswith(filter_normalized)


async def _adjust_account_cash_with_conn(conn, account: str, delta: float) -> bool:
    """Adjust cash balance using an externally-provided connection.
    Call this inside an existing transaction to keep cash updates atomic with position changes."""
    rows = await conn.fetch("SELECT account_name, cash FROM account_balances")
    for row in rows:
        if _match_account_balance(account, row["account_name"]):
            await conn.execute(
                "UPDATE account_balances SET cash = cash + $1, updated_at = NOW(), updated_by = 'auto' WHERE account_name = $2",
                round(delta, 2), row["account_name"],
            )
            logger.info("Cash adjusted for %s: %+.2f", row["account_name"], delta)
            return True
    logger.error("CASH ADJUSTMENT FAILED: No matching account_balance row for account=%s (delta=%+.2f)", account, delta)
    return False


async def _adjust_account_cash(pool, account: str, delta: float) -> bool:
    """Backward-compatible pool-based cash adjustment. Use _adjust_account_cash_with_conn
    when inside a transaction to keep cash updates atomic."""
    async with pool.acquire() as conn:
        return await _adjust_account_cash_with_conn(conn, account, delta)


def normalize_spread_strikes(
    long_strike: float | None,
    short_strike: float | None,
    structure: str | None,
) -> tuple[float | None, float | None]:
    """
    Ensure long_strike/short_strike match option spread conventions.

    For debit spreads the LONG leg is the more expensive option:
      - put_debit:  long = MAX strike (higher put costs more)
      - call_debit: long = MIN strike (lower call costs more)
    For credit spreads the SHORT leg is the more expensive option:
      - put_credit:  short = MAX strike → long = MIN
      - call_credit: short = MIN strike → long = MAX
    """
    if not long_strike or not short_strike or not structure:
        return long_strike, short_strike

    s = structure.lower()
    hi, lo = max(long_strike, short_strike), min(long_strike, short_strike)

    # put_debit / bear_put → long = higher strike
    # call_credit / bear_call → long = higher strike
    if ("put" in s and "debit" in s) or ("put" in s and "bear" in s) \
       or ("call" in s and "credit" in s) or ("call" in s and "bear" in s):
        return hi, lo

    # call_debit / bull_call → long = lower strike
    # put_credit / bull_put → long = lower strike
    if ("call" in s and "debit" in s) or ("call" in s and "bull" in s) \
       or ("put" in s and "credit" in s) or ("put" in s and "bull" in s):
        return lo, hi

    # Fallback: don't change
    return long_strike, short_strike


# ── Pydantic models ──────────────────────────────────────────────────

class CreatePositionRequest(BaseModel):
    model_config = {"populate_by_name": True}

    ticker: str
    asset_type: str = "OPTION"  # EQUITY, OPTION, SPREAD
    structure: Optional[str] = Field(default=None, alias="strategy")
    direction: Optional[str] = None  # LONG, SHORT, MIXED — auto-inferred if omitted
    legs: Optional[List[Dict[str, Any]]] = None

    entry_price: Optional[float] = None
    quantity: int = Field(default=1, alias="contracts")
    cost_basis: Optional[float] = None

    # Risk — auto-calculated if structure is provided, can be overridden
    max_loss: Optional[float] = None
    max_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None

    # Options-specific — accept both "expiry" and "expiration"
    expiry: Optional[str] = Field(default=None, alias="expiration")
    long_strike: Optional[float] = Field(default=None, alias="strike_long")
    short_strike: Optional[float] = Field(default=None, alias="strike_short")

    # Metadata
    source: str = "MANUAL"
    signal_id: Optional[str] = None
    account: str = "ROBINHOOD"
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    bucket: Optional[str] = None
    thesis: Optional[str] = None


class UpdatePositionRequest(BaseModel):
    status: Optional[str] = None  # OPEN, CLOSED, EXPIRED — allows reopening closed positions
    direction: Optional[str] = None  # LONG, SHORT
    structure: Optional[str] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    current_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    quantity: Optional[int] = None
    entry_price: Optional[float] = None
    cost_basis: Optional[float] = None
    legs: Optional[str] = None
    long_strike: Optional[float] = None
    short_strike: Optional[float] = None
    expiry: Optional[str] = None
    max_loss: Optional[float] = None
    max_profit: Optional[float] = None
    source: Optional[str] = None
    signal_id: Optional[str] = None
    # Close-out fields
    exit_price: Optional[float] = None
    realized_pnl: Optional[float] = None
    trade_outcome: Optional[str] = None
    closed_at: Optional[str] = None


class ClosePositionRequest(BaseModel):
    exit_price: float
    notes: Optional[str] = None
    quantity: Optional[int] = None  # If < total qty, partial close (reduce position, keep remainder open)
    exit_value: Optional[float] = None       # Total exit value (exit_price × multiplier × qty)
    trade_outcome: Optional[str] = None      # WIN / LOSS / BREAKEVEN (frontend-computed)
    loss_reason: Optional[str] = None        # SETUP_FAILED / EXECUTION_ERROR / MARKET_CONDITIONS
    close_reason: Optional[str] = "manual"   # profit / loss / expired / manual


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

def _combine_notes(notes: Optional[str], thesis: Optional[str], bucket: Optional[str]) -> Optional[str]:
    """Combine notes, thesis, and bucket into a single notes string."""
    parts = []
    if thesis:
        parts.append(f"Thesis: {thesis}")
    if bucket:
        parts.append(f"Bucket: {bucket}")
    if notes:
        parts.append(notes)
    return " | ".join(parts) if parts else None


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


def _compute_unrealized_pnl(entry_price: float, current_price: float, quantity: int, structure: str, asset_type: str = "", direction: str = "") -> float:
    """Compute unrealized P&L based on position type and credit/debit nature."""
    if not entry_price or not current_price:
        return 0.0
    s = (structure or "").lower()
    at = (asset_type or "").upper()
    d = (direction or "").upper()
    is_stock = s in ("stock", "stock_long", "long_stock", "stock_short", "short_stock") or (not s and at == "EQUITY")
    if is_stock:
        qty = abs(quantity)
        if s in ("stock_short", "short_stock") or d == "SHORT":
            # Short stock: profit when price drops
            return round((entry_price - current_price) * qty, 2)
        return round((current_price - entry_price) * qty, 2)
    if s in CREDIT_STRUCTURES:
        # Most credit structures: received premium at open, pay to close
        # Exception: iron condors/butterflies can be net debit depending on strikes
        # LONG iron condor = debit (paid to open) → profit when value increases
        # SHORT iron condor = credit (received to open) → profit when value decreases
        if s in ("iron_condor", "iron_butterfly") and d == "LONG":
            return round((current_price - entry_price) * 100 * quantity, 2)
        # Standard credit: profit when current < entry
        return round((entry_price - current_price) * 100 * quantity, 2)
    # Debit: paid premium at open → profit when current > entry
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


# Structures that require legs JSONB for correct pricing (>2 legs)
MULTI_LEG_STRUCTURES = frozenset({"iron_condor", "iron_butterfly", "straddle", "strangle", "custom"})

import re
# Matches "long 36p/45c" or "short 30p/50c" — captures the action word and
# the full slash-separated strike group so each strike inherits the action.
_LEG_GROUP_PATTERN = re.compile(
    r'(long|short)\s+([\d.]+\s*(?:p|c|put|call)(?:\s*/\s*[\d.]+\s*(?:p|c|put|call))*)',
    re.IGNORECASE,
)
_STRIKE_PATTERN = re.compile(r'([\d.]+)\s*(p|c|put|call)', re.IGNORECASE)


def _infer_legs_from_notes(notes: str) -> Optional[List[Dict[str, Any]]]:
    """
    Parse legs from notes like "4-leg: long 36p/45c, short 30p/50c".
    Handles slash-separated strikes where all strikes after the slash
    inherit the preceding long/short action.
    Returns list of leg dicts compatible with get_multi_leg_value(), or None.
    """
    if not notes:
        return None
    legs = []
    for action_match in _LEG_GROUP_PATTERN.finditer(notes):
        action_word = action_match.group(1)   # "long" or "short"
        strikes_part = action_match.group(2)  # "36p/45c" or "30p/50c"
        action = "BUY" if action_word.lower() == "long" else "SELL"
        for strike_match in _STRIKE_PATTERN.finditer(strikes_part):
            strike_str = strike_match.group(1)
            type_char = strike_match.group(2)
            opt_type = "put" if type_char.lower().startswith("p") else "call"
            legs.append({
                "action": action,
                "option_type": opt_type,
                "strike": float(strike_str),
                "quantity": 1,
            })
    return legs if len(legs) >= 2 else None


# ── CREATE ────────────────────────────────────────────────────────────

@router.post("/v2/positions")
async def create_position(req: CreatePositionRequest, _=Depends(require_api_key)):
    """Create a new position, or add to existing if same ticker+account+structure is open."""
    pool = await get_postgres_client()

    # Auto-infer direction if not provided
    direction = req.direction
    if not direction and req.structure:
        direction = infer_direction(req.structure)
    direction = direction or "LONG"

    # Handle short stock: normalize negative qty to positive + SHORT direction
    if req.quantity < 0:
        req.quantity = abs(req.quantity)
        direction = "SHORT"

    # Normalize strike order based on spread type before any calculation
    norm_long, norm_short = normalize_spread_strikes(
        req.long_strike, req.short_strike, req.structure
    )

    # --- Check for existing open position to combine with ---
    account = (req.account or "ROBINHOOD").upper()
    existing = None
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("""
            SELECT * FROM unified_positions
            WHERE ticker = $1 AND account = $2 AND status = 'OPEN'
              AND COALESCE(structure, '') = COALESCE($3, '')
              AND COALESCE(long_strike, 0) = COALESCE($4, 0)
              AND COALESCE(short_strike, 0) = COALESCE($5, 0)
              AND COALESCE(expiry::text, '') = COALESCE($6, '')
            LIMIT 1
        """, req.ticker.upper(), account, req.structure,
            norm_long or 0, norm_short or 0,
            str(req.expiry)[:10] if req.expiry else "",
        )

    if existing and req.entry_price is not None:
        # --- ADD TO EXISTING POSITION (weighted average cost basis) ---
        old_qty = existing["quantity"] or 0
        old_entry = float(existing["entry_price"] or 0)
        add_qty = req.quantity
        add_entry = req.entry_price

        new_qty = old_qty + add_qty
        new_entry = ((old_entry * old_qty) + (add_entry * add_qty)) / new_qty if new_qty else add_entry

        # Recompute cost basis
        s = (req.structure or existing["structure"] or "").lower()
        is_stock = s in ("stock", "stock_long", "long_stock", "stock_short", "short_stock")
        new_cost_basis = abs(new_entry) * new_qty * (1 if is_stock else 100)

        # Recalculate risk for new quantity
        new_max_loss = existing["max_loss"]
        new_max_profit = existing["max_profit"]
        new_breakeven = existing.get("breakeven")
        structure = req.structure or existing["structure"]
        if structure and new_max_loss is not None and old_qty > 0:
            # Scale risk proportionally to new quantity
            scale = new_qty / old_qty
            new_max_loss = round(float(new_max_loss) * scale, 2) if new_max_loss else None
            new_max_profit = round(float(new_max_profit) * scale, 2) if new_max_profit else None

        pos_id = existing["position_id"]
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                UPDATE unified_positions
                SET quantity = $2, entry_price = $3, cost_basis = $4,
                    max_loss = $5, max_profit = $6, updated_at = NOW()
                WHERE position_id = $1
                RETURNING *
            """, pos_id, new_qty, round(new_entry, 4), round(new_cost_basis, 2),
                new_max_loss, new_max_profit,
            )

        # Adjust cash for the added portion only
        add_cost = abs(add_entry) * add_qty * (1 if is_stock else 100)
        cash_ok = True
        if add_cost:
            d_existing = (existing.get("direction") or "").upper()
            is_short_equity = d_existing == "SHORT" and is_stock
            cash_delta = add_cost if (s in CREDIT_STRUCTURES or is_short_equity) else -add_cost
            try:
                cash_ok = await _adjust_account_cash(pool, account, cash_delta)
            except Exception as e:
                logger.error("Cash adjustment failed on add-to-position: %s", e)
                cash_ok = False

        result = _row_to_dict(row)
        logger.info(
            "Position combined: %s %s — %d+%d=%d @ $%.4f avg",
            pos_id, req.ticker.upper(), old_qty, add_qty, new_qty, new_entry,
        )

        try:
            await manager.broadcast_position_update({
                "action": "POSITION_UPDATED",
                "position": result,
            })
        except Exception:
            pass

        return {"status": "combined", "position": result,
                "detail": f"Added {add_qty} to existing position ({old_qty} → {new_qty} @ ${new_entry:.4f} avg)"}

    # --- CREATE NEW POSITION ---
    position_id = _generate_position_id(req.ticker)

    # Auto-calculate risk if structure is provided and max_loss not overridden
    max_loss = req.max_loss
    max_profit = req.max_profit
    breakeven = []
    if req.structure and req.entry_price is not None and max_loss is None:
        risk = calculate_position_risk(
            structure=req.structure,
            entry_price=req.entry_price,
            quantity=req.quantity,
            long_strike=norm_long,
            short_strike=norm_short,
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
            expiry, dte, norm_long, norm_short,
            req.source, req.signal_id, account,
            _combine_notes(req.notes, req.thesis, req.bucket),
            req.tags if req.tags else None,
        )

    # Auto-adjust cash: deduct cost for debit, add premium for credit
    # Short stock: selling shares generates cash proceeds (like a credit)
    cash_ok = True
    if cost_basis:
        s = (req.structure or "").lower()
        d = (direction or "").upper()
        is_short_equity = d == "SHORT" and s in ("stock", "stock_short", "short_stock", "")
        cash_delta = cost_basis if (s in CREDIT_STRUCTURES or is_short_equity) else -cost_basis
        try:
            cash_ok = await _adjust_account_cash(pool, account, cash_delta)
        except Exception as e:
            logger.error("Cash adjustment failed on create: %s", e)
            cash_ok = False

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

    return {"status": "created", "position": result, "cash_adjusted": cash_ok}


# ── READ ──────────────────────────────────────────────────────────────

async def _sweep_expired_positions():
    """Mark OPEN positions as EXPIRED if their expiry date has passed."""
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE unified_positions
                SET status = 'EXPIRED', updated_at = NOW()
                WHERE status = 'OPEN'
                  AND expiry IS NOT NULL
                  AND expiry < CURRENT_DATE
            """)
            count = int(result.split()[-1]) if result else 0
            if count > 0:
                logger.info("Auto-expired %d positions past their expiry date", count)
    except Exception as e:
        logger.warning("Expired position sweep failed: %s", e)


@router.get("/v2/positions")
async def list_positions(
    status: str = Query("OPEN", description="Filter by status: OPEN, CLOSED, EXPIRED, or ALL"),
    ticker: Optional[str] = Query(None),
    account: Optional[str] = Query(None),
    asset_type: Optional[str] = Query(None, description="Filter by asset type: OPTION, EQUITY, SPREAD"),
):
    """List positions, filtered by status."""
    # Auto-expire positions past their expiry date
    await _sweep_expired_positions()

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

    if asset_type:
        conditions.append(f"asset_type = ${idx}")
        params.append(asset_type.upper())
        idx += 1

    if account:
        if account.upper() == "FIDELITY":
            conditions.append("account LIKE 'FIDELITY%'")
        else:
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

    # Attach counter-signal warnings from Redis for open positions
    if status.upper() == "OPEN":
        try:
            from database.redis_client import get_redis_client
            redis = await get_redis_client()
            if redis:
                for p in positions:
                    ticker = (p.get("ticker") or "").upper()
                    if ticker:
                        raw = await redis.get(f"counter_signal:{ticker}")
                        if raw:
                            p["counter_signal"] = json.loads(raw)
                        raw_conf = await redis.get(f"confirming_signal:{ticker}")
                        if raw_conf:
                            p["confirming_signal"] = json.loads(raw_conf)
                        # UW flow badge — compare flow sentiment to position direction
                        raw_flow = await redis.get(f"uw:flow:{ticker}")
                        if raw_flow:
                            flow = json.loads(raw_flow)
                            flow_sent = (flow.get("sentiment") or "").upper()
                            pos_dir = (p.get("direction") or "").upper()
                            bullish_dirs = {"LONG", "BUY", "BULLISH"}
                            bearish_dirs = {"SHORT", "SELL", "BEARISH"}
                            if flow_sent in ("BULLISH", "BEARISH") and pos_dir:
                                flow_bull = flow_sent == "BULLISH"
                                pos_bull = pos_dir in bullish_dirs
                                pos_bear = pos_dir in bearish_dirs
                                if (flow_bull and pos_bull) or (not flow_bull and pos_bear):
                                    alignment = "CONFIRMING"
                                elif (flow_bull and pos_bear) or (not flow_bull and pos_bull):
                                    alignment = "OPPOSING"
                                else:
                                    alignment = "NEUTRAL"
                            else:
                                alignment = "NEUTRAL"
                            # Strength: HIGH if total premium > $100M, else MODERATE
                            tp = flow.get("total_premium") or 0
                            strength = "HIGH" if tp > 100_000_000 else "MODERATE"
                            p["flow_badge"] = {
                                "sentiment": flow_sent or "NEUTRAL",
                                "alignment": alignment,
                                "strength": strength,
                                "pc_ratio": flow.get("pc_ratio"),
                                "total_premium": tp,
                                "call_premium": flow.get("call_premium"),
                                "put_premium": flow.get("put_premium"),
                                "last_updated": flow.get("last_updated"),
                            }
        except Exception as e:
            logger.warning(f"Failed to attach counter-signals: {e}")

    return {"positions": positions, "count": len(positions)}


# ── PORTFOLIO SUMMARY ─────────────────────────────────────────────────
# NOTE: Must be defined BEFORE /v2/positions/{position_id} to avoid
#       "summary" being captured as a position_id path parameter.

@router.post("/v2/positions/expire-sweep")
async def expire_sweep(_=Depends(require_api_key)):
    """Manually trigger expiry sweep for positions past their expiry date."""
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                UPDATE unified_positions
                SET status = 'EXPIRED', updated_at = NOW()
                WHERE status = 'OPEN'
                  AND expiry IS NOT NULL
                  AND expiry < CURRENT_DATE
                RETURNING position_id, ticker, expiry
            """)
        expired = [{"position_id": r["position_id"], "ticker": r["ticker"],
                     "expiry": str(r["expiry"])} for r in rows]
        return {"status": "ok", "expired_count": len(expired), "expired": expired}
    except Exception as e:
        logger.error("Expire sweep failed: %s", e)
        return {"status": "error", "detail": str(e)}


@router.get("/v2/positions/summary")
async def portfolio_summary(account: Optional[str] = Query(None)):
    """
    Portfolio summary for the bias row widget and committee context.
    Returns: total positions, capital at risk, net direction, nearest expiry.
    Optional account filter: ?account=ROBINHOOD or ?account=FIDELITY
    """
    # Auto-expire first
    await _sweep_expired_positions()

    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM unified_positions WHERE status = 'OPEN' ORDER BY COALESCE(expiry, '2099-12-31'::date) ASC"
        )

    positions = [_row_to_dict(r) for r in rows]

    # Filter by account if specified
    if account:
        account_upper = account.upper()
        if account_upper == "FIDELITY":
            # Show all Fidelity sub-accounts
            positions = [p for p in positions if (p.get("account") or "").upper().startswith("FIDELITY")]
        else:
            positions = [p for p in positions if (p.get("account") or "ROBINHOOD").upper() == account_upper]

    # Fetch cash balance from account_balances
    cash = 0.0
    try:
        async with pool.acquire() as conn:
            if account:
                # Find matching account balance row(s)
                bal_rows = await conn.fetch("SELECT account_name, cash, balance FROM account_balances")
                if account.upper() == "FIDELITY":
                    # Sum all Fidelity sub-accounts
                    cash = sum(float(br["cash"] or 0) for br in bal_rows if (br["account_name"] or "").lower().startswith("fidelity"))
                else:
                    for br in bal_rows:
                        if _match_account_balance(account, br["account_name"]):
                            cash = float(br["cash"] or 0)
                            break
            else:
                # Default: sum all account cash balances
                bal_rows = await conn.fetch("SELECT cash FROM account_balances")
                cash = sum(float(br["cash"] or 0) for br in bal_rows)
    except Exception:
        pass

    if not positions:
        return {
            "account_balance": cash,
            "cash": cash,
            "position_value": 0.0,
            "position_count": 0,
            "capital_at_risk": 0.0,
            "capital_at_risk_pct": 0.0,
            "nearest_expiry": None,
            "nearest_dte": None,
            "net_direction": "FLAT",
            "positions": [],
        }

    # Calculate summary
    total_max_loss = sum(p.get("max_loss") or 0 for p in positions)
    # Position market value = cost_basis + unrealized_pnl (what positions are currently worth)
    # Exception: short stock is a liability — value = -(current_price * qty)
    # Fallback: if cost_basis is null, compute from entry_price * quantity * 100
    total_position_value = 0.0
    for p in positions:
        s = (p.get("structure") or "").lower()
        d = (p.get("direction") or "").upper()
        is_short_stock = d == "SHORT" and s in ("stock", "stock_short", "short_stock", "")
        if is_short_stock:
            # Short stock: position is a liability (cost to buy back)
            # Value = -(current_price * qty) = unrealized_pnl - cost_basis
            # This correctly represents the buyback liability when cash
            # already includes the short sale proceeds (as reported by broker)
            pnl = p.get("unrealized_pnl") or 0
            cost = p.get("cost_basis") or 0
            total_position_value += pnl - cost
        else:
            cost = p.get("cost_basis")
            if cost is None:
                ep = p.get("entry_price") or 0
                qty = p.get("quantity") or 0
                cost = ep * qty * 100
            pnl = p.get("unrealized_pnl") or 0
            total_position_value += cost + pnl
    total_position_value = round(total_position_value, 2)
    # Total account = cash + position market value
    account_balance = round(cash + total_position_value, 2)
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

    # Flag positions with stale pricing
    # During market hours: stale if no update in 30+ minutes
    # Outside market hours: stale if not updated after 4:00 PM ET on most recent trading day
    import pytz
    now_utc = datetime.now(timezone.utc)
    et_tz = pytz.timezone("America/New_York")
    now_et = now_utc.astimezone(et_tz)
    is_market_hours = now_et.weekday() < 5 and 9 <= now_et.hour < 17

    if is_market_hours:
        stale_threshold = now_utc - timedelta(minutes=30)
    else:
        # Find most recent 4:00 PM ET (closing bell)
        last_close_et = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        if now_et.hour < 16 or now_et.weekday() >= 5:
            # Before market close today or weekend — go back to last weekday
            days_back = 1
            if now_et.weekday() == 0 and now_et.hour < 16:
                days_back = 3  # Monday before close → Friday
            elif now_et.weekday() == 6:
                days_back = 2  # Sunday → Friday
            elif now_et.weekday() == 5:
                days_back = 1  # Saturday → Friday
            last_close_et = last_close_et - timedelta(days=days_back)
        stale_threshold = last_close_et.astimezone(timezone.utc)

    stale_count = 0
    for p in positions:
        pua = p.get("price_updated_at")
        if not pua:
            stale_count += 1
        else:
            try:
                if isinstance(pua, str):
                    pua_dt = datetime.fromisoformat(pua).replace(tzinfo=timezone.utc) if "+" not in pua and "Z" not in pua else datetime.fromisoformat(pua.replace("Z", "+00:00"))
                else:
                    pua_dt = pua if pua.tzinfo else pua.replace(tzinfo=timezone.utc)
                if pua_dt < stale_threshold:
                    stale_count += 1
            except Exception:
                stale_count += 1

    # Compute expiry clusters for timeline view
    expiry_map = {}
    for p in positions:
        exp = p.get("expiry")
        if not exp:
            continue
        exp_str = str(exp)[:10]
        if exp_str not in expiry_map:
            expiry_map[exp_str] = {"date": exp_str, "count": 0, "total_cost": 0}
        expiry_map[exp_str]["count"] += 1
        expiry_map[exp_str]["total_cost"] += abs(p.get("cost_basis") or 0)
    expiry_clusters = sorted(expiry_map.values(), key=lambda x: x["date"])

    return {
        "account_balance": account_balance,
        "cash": cash,
        "position_value": total_position_value,
        "position_count": len(positions),
        "capital_at_risk": round(total_max_loss, 2),
        "capital_at_risk_pct": round(total_max_loss / account_balance * 100, 2) if account_balance > 0 else 0.0,
        "nearest_expiry": nearest_expiry,
        "nearest_dte": nearest_dte,
        "net_direction": net_direction,
        "direction_breakdown": {"long": long_count, "short": short_count, "mixed": mixed_count},
        "stale_positions": stale_count,
        "expiry_clusters": expiry_clusters,
        "positions": summaries,
    }


@router.patch("/v2/positions/account-balance")
async def update_account_balance(request: Request, _=Depends(require_api_key)):
    """
    Update stored cash balance for any account.
    Body: {"cash": 3044.19} or {"cash": 3044.19, "account_name": "Fidelity Roth"}
    Defaults to Robinhood if account_name not specified.
    """
    body = await request.json()
    new_cash = body.get("cash")
    if new_cash is None:
        raise HTTPException(status_code=400, detail="cash field required")

    account_name = body.get("account_name", "Robinhood")

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE account_balances SET cash = $1, updated_at = NOW(), updated_by = 'dashboard' WHERE account_name = $2",
            float(new_cash), account_name,
        )

    logger.info("Cash balance updated for %s to %.2f", account_name, float(new_cash))
    return {"status": "ok", "account": account_name, "cash": float(new_cash)}


@router.get("/v2/positions/greeks")
async def portfolio_greeks():
    """
    Get aggregate portfolio greeks from Polygon.io options snapshots.
    Returns per-ticker and total portfolio greeks for committee context.
    Gracefully returns zeros if API is unavailable (e.g., after hours).
    """
    _zeros = {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}
    try:
        return await _portfolio_greeks_inner()
    except Exception as e:
        logger.error("Greeks endpoint unhandled error: %s", e, exc_info=True)
        return {"status": "error", "tickers": {}, "totals": _zeros}


async def _portfolio_greeks_inner():
    # Check Redis cache first (60s TTL)
    redis = await get_redis_client()
    if redis:
        try:
            cached = await redis.get("portfolio:greeks:cache")
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    # Also check stale cache (24h TTL) for after-hours display
    if redis:
        try:
            stale = await redis.get("portfolio:greeks:stale")
            if stale:
                stale_data = json.loads(stale)
                stale_data["stale"] = True
                return stale_data
        except Exception:
            pass

    # UW API only — Polygon is deprecated
    try:
        from integrations.uw_api import get_ticker_greeks_summary, UW_API_KEY
        if not UW_API_KEY:
            return {"status": "no_api_key", "tickers": {}, "totals": {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}}
    except ImportError:
        return {"status": "unavailable", "tickers": {}, "totals": {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}}

    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM unified_positions WHERE status = 'OPEN'"
            )
    except Exception as e:
        logger.error("Greeks: DB query failed: %s", e)
        return {"status": "db_error", "tickers": {}, "totals": {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}}

    if not rows:
        return {"status": "no_positions", "tickers": {}, "totals": {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}}

    try:
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
                logger.info("Greeks: fetching for %s (%d positions). Strikes: %s",
                           ticker, len(pos_list),
                           [(p.get("long_strike"), p.get("short_strike"), p.get("expiry")) for p in pos_list])
                greeks_result = await get_ticker_greeks_summary(ticker, pos_list)
                if greeks_result:
                    logger.info("Greeks: %s returned delta=%.2f gamma=%.4f theta=%.2f vega=%.2f",
                               ticker,
                               greeks_result.get("net_delta", 0),
                               greeks_result.get("net_gamma", 0),
                               greeks_result.get("net_theta", 0),
                               greeks_result.get("net_vega", 0))
                    ticker_greeks[ticker] = greeks_result
                else:
                    logger.warning("Greeks: %s returned None (snapshot empty or no matching contracts)", ticker)
                    total_delta += greeks_result.get("net_delta", 0)
                    total_gamma += greeks_result.get("net_gamma", 0)
                    total_theta += greeks_result.get("net_theta", 0)
                    total_vega += greeks_result.get("net_vega", 0)
            except Exception as e:
                logger.warning("Greeks fetch failed for %s: %s", ticker, e)
                ticker_greeks[ticker] = {"error": str(e)}

        result = {
            "status": "ok",
            "tickers": ticker_greeks,
            "totals": {
                "delta": round(total_delta, 2),
                "gamma": round(total_gamma, 4),
                "theta": round(total_theta, 2),
                "vega": round(total_vega, 2),
            },
            "portfolio": {
                "net_delta": round(total_delta, 2),
                "net_gamma": round(total_gamma, 4),
                "net_theta": round(total_theta, 2),
                "net_vega": round(total_vega, 2),
            },
        }

    except Exception as e:
        logger.error("Greeks computation failed: %s", e)
        return {"status": "computation_error", "error": str(e), "tickers": {}, "totals": {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}}

    # Cache for 60 seconds + stale cache for 24 hours (after-hours fallback)
    if redis:
        try:
            result_json = json.dumps(result)
            await redis.set("portfolio:greeks:cache", result_json, ex=60)
            await redis.set("portfolio:greeks:stale", result_json, ex=86400)
        except Exception:
            pass

    return result


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
async def update_position(position_id: str, req: UpdatePositionRequest, _=Depends(require_api_key)):
    """Update position fields. Recalculates unrealized P&L if current_price is updated."""
    pool = await get_postgres_client()

    # Fetch old row for cash delta calculation
    async with pool.acquire() as conn:
        old_row = await conn.fetchrow(
            "SELECT * FROM unified_positions WHERE position_id = $1", position_id
        )
    if not old_row:
        raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
    old_pos = _row_to_dict(old_row)

    # Build dynamic SET clause
    sets = ["updated_at = NOW()"]
    params = []
    idx = 1

    if req.status is not None:
        sets.append(f"status = ${idx}")
        params.append(req.status.upper())
        idx += 1
    if req.direction is not None:
        sets.append(f"direction = ${idx}")
        params.append(req.direction.upper())
        idx += 1
    if req.structure is not None:
        sets.append(f"structure = ${idx}")
        params.append(req.structure)
        idx += 1
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
    if req.entry_price is not None:
        sets.append(f"entry_price = ${idx}")
        params.append(req.entry_price)
        idx += 1
    if req.cost_basis is not None:
        sets.append(f"cost_basis = ${idx}")
        params.append(req.cost_basis)
        idx += 1
    if req.legs is not None:
        sets.append(f"legs = ${idx}")
        params.append(req.legs)
        idx += 1
    if req.long_strike is not None:
        sets.append(f"long_strike = ${idx}")
        params.append(req.long_strike)
        idx += 1
    if req.short_strike is not None:
        sets.append(f"short_strike = ${idx}")
        params.append(req.short_strike)
        idx += 1
    if req.expiry is not None:
        try:
            exp_date = date.fromisoformat(str(req.expiry)[:10])
            sets.append(f"expiry = ${idx}")
            params.append(exp_date)
            idx += 1
            dte = max(0, (exp_date - date.today()).days)
            sets.append(f"dte = ${idx}")
            params.append(dte)
            idx += 1
        except (ValueError, TypeError):
            pass
    if req.unrealized_pnl is not None:
        sets.append(f"unrealized_pnl = ${idx}")
        params.append(req.unrealized_pnl)
        idx += 1
    if req.max_loss is not None:
        sets.append(f"max_loss = ${idx}")
        params.append(req.max_loss)
        idx += 1
    if req.max_profit is not None:
        sets.append(f"max_profit = ${idx}")
        params.append(req.max_profit)
        idx += 1
    if req.source is not None:
        sets.append(f"source = ${idx}")
        params.append(req.source)
        idx += 1
    if req.signal_id is not None:
        sets.append(f"signal_id = ${idx}")
        params.append(req.signal_id)
        idx += 1
    if req.exit_price is not None:
        sets.append(f"exit_price = ${idx}")
        params.append(req.exit_price)
        idx += 1
    if req.realized_pnl is not None:
        sets.append(f"realized_pnl = ${idx}")
        params.append(req.realized_pnl)
        idx += 1
    if req.trade_outcome is not None:
        sets.append(f"trade_outcome = ${idx}")
        params.append(req.trade_outcome)
        idx += 1
    if req.closed_at is not None:
        sets.append(f"exit_date = ${idx}")
        params.append(datetime.fromisoformat(req.closed_at.replace("Z", "+00:00")))
        idx += 1

    if len(sets) <= 1:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(position_id)
    set_clause = ", ".join(sets)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(f"""
            UPDATE unified_positions SET {set_clause}
            WHERE position_id = ${idx}
            RETURNING *
        """, *params)

    if not row:
        raise HTTPException(status_code=404, detail=f"Position {position_id} not found")

    result = _row_to_dict(row)

    # Recalculate unrealized P&L if price, quantity, direction, or structure changed
    if (req.current_price is not None or req.entry_price is not None or req.quantity is not None or req.direction is not None or req.structure is not None) and result.get("entry_price") and result.get("current_price"):
        unrealized = _compute_unrealized_pnl(
            result["entry_price"], result["current_price"],
            result["quantity"], result.get("structure", ""),
            direction=result.get("direction", "")
        )
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE unified_positions SET unrealized_pnl = $1 WHERE position_id = $2",
                unrealized, position_id
            )
        result["unrealized_pnl"] = unrealized

    # BUG 3: If entry_price or quantity changed on an OPEN position, adjust cash for the cost_basis delta
    cash_ok = None
    if (req.entry_price is not None or req.quantity is not None) and result.get("status", "").upper() == "OPEN":
        old_cost = float(old_pos.get("cost_basis") or 0)
        s = (result.get("structure") or "").lower()
        is_stock = s in ("stock", "stock_long", "long_stock", "stock_short", "short_stock")
        new_entry = float(result.get("entry_price") or 0)
        new_qty = int(result.get("quantity") or 0)
        new_cost = abs(new_entry) * new_qty * (1 if is_stock else 100)

        if round(new_cost, 2) != round(old_cost, 2):
            cost_delta = new_cost - old_cost
            # For debit positions: more cost = less cash. For credit: more cost = more cash.
            cash_delta = cost_delta if s in CREDIT_STRUCTURES else -cost_delta
            cash_ok = await _adjust_account_cash(pool, result.get("account", "ROBINHOOD"), cash_delta)

            # Update cost_basis in DB to match
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE unified_positions SET cost_basis = $1 WHERE position_id = $2",
                    round(new_cost, 2), position_id
                )
            result["cost_basis"] = round(new_cost, 2)

    try:
        await manager.broadcast_position_update({
            "action": "POSITION_UPDATED",
            "position": result,
        })
    except Exception:
        pass

    resp = {"status": "updated", "position": result}
    if cash_ok is not None:
        resp["cash_adjusted"] = cash_ok
    return resp


# ── Ariadne's Thread: Signal Outcome Resolution ──────────────────────

async def _resolve_signal_outcome(pool, position: dict, exit_price: float,
                                   realized_pnl: float, trade_outcome: str,
                                   closed_at) -> None:
    """
    When a position closes, resolve the full outcome chain back to the originating signal.
    Ariadne's Thread: Signal → Position → Outcome with P&L and options metrics.
    """
    signal_id = position.get("signal_id")
    if not signal_id:
        return

    entry = position.get("entry_price") or 0
    direction = position.get("direction", "LONG")

    # Compute P&L percentage
    if entry and exit_price:
        if direction == "LONG":
            pnl_pct = ((exit_price - entry) / entry * 100)
        else:
            pnl_pct = ((entry - exit_price) / entry * 100)
    else:
        pnl_pct = 0

    # Options-specific metrics
    options_metrics = None
    asset_type = (position.get("asset_type") or "").upper()
    if asset_type == "OPTION":
        expiry = position.get("expiry")
        dte_at_exit = None
        if expiry and closed_at:
            try:
                from datetime import date as date_type
                exp_date = date_type.fromisoformat(str(expiry)[:10]) if not isinstance(expiry, date_type) else expiry
                close_date = closed_at.date() if hasattr(closed_at, "date") else closed_at
                dte_at_exit = (exp_date - close_date).days
            except Exception:
                pass

        max_loss = position.get("max_loss")
        max_profit = position.get("max_profit")
        options_metrics = {
            "structure": position.get("structure"),
            "dte_at_exit": dte_at_exit,
            "premium_at_risk": float(position.get("cost_basis") or 0),
            "max_loss_utilization": round((realized_pnl / float(max_loss)) * 100, 1) if max_loss and float(max_loss) != 0 else None,
            "max_profit_utilization": round((realized_pnl / float(max_profit)) * 100, 1) if max_profit and float(max_profit) != 0 else None,
            "exit_quality": (
                "EARLY_PROFIT" if pnl_pct > 0 and dte_at_exit and dte_at_exit > 7 else
                "HELD_TO_EXPIRY" if dte_at_exit is not None and dte_at_exit <= 1 else
                "STOPPED_OUT" if pnl_pct < -50 else "NORMAL"
            ),
        }

    import json as _json
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE signals SET
                trade_outcome = $2,
                actual_exit_price = $3,
                outcome = $4,
                outcome_pnl_pct = $5,
                outcome_pnl_dollars = $6,
                outcome_resolved_at = $7,
                outcome_options_metrics = $8,
                notes = COALESCE(notes || ' | ', '') || $9,
                outcome_source = 'ACTUAL_TRADE'
            WHERE signal_id = $1
        """,
            signal_id,
            trade_outcome,
            exit_price,
            trade_outcome,  # outcome mirrors trade_outcome for taken signals
            round(pnl_pct, 2),
            round(realized_pnl, 2),
            closed_at,
            _json.dumps(options_metrics) if options_metrics else None,
            f"Closed: {trade_outcome} (${realized_pnl:+.2f}, {pnl_pct:+.1f}%)",
        )

    logger.info(f"Ariadne: resolved {signal_id} -> {trade_outcome} ({pnl_pct:+.1f}%, ${realized_pnl:+.2f})")


async def _resolve_signal_with_failure_logging(
    pool, position_dict: dict, exit_price: float,
    realized_pnl: float, trade_outcome: str, closed_at,
) -> None:
    """Run signal resolution as a background task; log failures to background_task_failures."""
    try:
        await _resolve_signal_outcome(
            pool, position_dict, exit_price, realized_pnl, trade_outcome, closed_at
        )
    except Exception as exc:
        import traceback
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO background_task_failures
                        (task_name, related_id, error_class, error_message, stack_trace)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    "_resolve_signal_outcome",
                    position_dict.get("position_id"),
                    type(exc).__name__,
                    str(exc),
                    traceback.format_exc(),
                )
        except Exception as log_exc:
            logger.error("Failed to log background_task_failure: %s", log_exc)


# ── CLOSE (with trade bridge) ─────────────────────────────────────────

@router.post("/v2/positions/{position_id}/close")
async def close_position(position_id: str, req: ClosePositionRequest, _=Depends(require_api_key)):
    """
    Close a position: calculate realized P&L, create trades record, update signal if linked.
    This is the close-to-trade bridge (Phase A4).
    SELECT FOR UPDATE prevents double-close races; single transaction keeps position/cash/analytics atomic.
    """
    pool = await get_postgres_client()
    now = datetime.now(timezone.utc)

    # Record the attempt for auditability (outside main transaction — logged even on failure)
    attempt_id = None
    try:
        async with pool.acquire() as conn:
            attempt_row = await conn.fetchrow(
                "INSERT INTO close_attempts (position_id, exit_price) VALUES ($1, $2) RETURNING id",
                position_id, req.exit_price,
            )
            attempt_id = attempt_row["id"] if attempt_row else None
    except Exception:
        pass  # Audit table failure never blocks the close

    # These are set inside the try block; defined here so they're visible after it.
    pos = None
    row = None
    trade_id = None
    realized_pnl = 0.0
    trade_outcome = "BREAKEVEN"
    close_cash_ok = True
    updated = None
    total_qty = 0
    close_qty = 0
    is_partial = False
    is_stock = False
    s = ""

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # SELECT FOR UPDATE — row-level lock prevents double-close races.
                # NOWAIT: a racing second request gets immediate 409 instead of queuing.
                try:
                    row = await conn.fetchrow(
                        "SELECT * FROM unified_positions WHERE position_id = $1 AND status = 'OPEN' FOR UPDATE NOWAIT",
                        position_id,
                    )
                except Exception as lock_exc:
                    if "LockNotAvailable" in type(lock_exc).__name__ or "55P03" in str(lock_exc):
                        raise HTTPException(status_code=409, detail="Position close already in progress; please retry.")
                    raise

                if not row:
                    raise HTTPException(status_code=404, detail=f"Open position {position_id} not found")

                pos = _row_to_dict(row)
                entry_price = pos.get("entry_price") or 0
                structure = pos.get("structure") or ""
                total_qty = pos["quantity"]

                close_qty = req.quantity if req.quantity and req.quantity < total_qty else total_qty
                is_partial = close_qty < total_qty

                s = structure.lower()
                asset_type = (pos.get("asset_type") or "").upper()
                is_stock = s in ("stock", "stock_long", "long_stock", "stock_short", "short_stock") or (not s and asset_type == "EQUITY")

                if is_stock:
                    direction = (pos.get("direction") or "LONG").upper()
                    if direction == "SHORT":
                        realized_pnl = round((entry_price - req.exit_price) * close_qty, 2)
                    else:
                        realized_pnl = round((req.exit_price - entry_price) * close_qty, 2)
                elif s in CREDIT_STRUCTURES:
                    realized_pnl = round((entry_price - req.exit_price) * 100 * close_qty, 2)
                else:
                    realized_pnl = round((req.exit_price - entry_price) * 100 * close_qty, 2)

                trade_outcome = "WIN" if realized_pnl > 0 else "LOSS" if realized_pnl < 0 else "BREAKEVEN"

                # INSERT trade record — inside main transaction for full atomicity.
                # Failure rolls back the entire close so no position/trade drift can occur.
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
                    close_qty,
                    datetime.fromisoformat(str(pos.get("entry_date") or pos.get("created_at") or now)) if isinstance(pos.get("entry_date") or pos.get("created_at"), str) else (pos.get("entry_date") or pos.get("created_at") or now),
                    now, req.exit_price,
                    realized_pnl, req.notes or "Closed via unified positions",
                    req.notes,
                    pos.get("long_strike") or pos.get("short_strike"),
                    date.fromisoformat(str(pos["expiry"])[:10]) if pos.get("expiry") else None,
                    pos.get("short_strike"), pos.get("long_strike"),
                    "position_ledger",
                )
                trade_id = trade_row["id"] if trade_row else None

                # UPDATE unified_positions (partial or full close)
                if is_partial:
                    remaining_qty = total_qty - close_qty
                    old_cost_basis = pos.get("cost_basis") or 0
                    new_cost_basis = round(old_cost_basis * remaining_qty / total_qty, 2) if total_qty > 0 else 0
                    updated = await conn.fetchrow("""
                        UPDATE unified_positions SET
                            quantity = $1,
                            cost_basis = $2,
                            notes = COALESCE(notes || ' | ', '') || $3,
                            updated_at = NOW()
                        WHERE position_id = $4
                        RETURNING *
                    """, remaining_qty, new_cost_basis,
                        f"Partial close {close_qty}/{total_qty} @ {req.exit_price} ({trade_outcome} ${realized_pnl:+.2f})",
                        position_id)
                else:
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

                    # INSERT closed_positions inside main transaction — full atomicity with position update.
                    # Failure rolls back the entire close, keeping unified_positions and closed_positions in sync.
                    exit_val = req.exit_value or round(abs(req.exit_price) * (1 if is_stock else 100) * close_qty, 2)
                    cost_basis_val = float(pos["cost_basis"]) if pos.get("cost_basis") else None
                    pnl_pct = round((realized_pnl / abs(cost_basis_val)) * 100, 2) if cost_basis_val and cost_basis_val != 0 else None
                    raw_opened = pos.get("entry_date") or pos.get("created_at")
                    opened_at = datetime.fromisoformat(str(raw_opened)) if isinstance(raw_opened, str) else raw_opened
                    hold_days = (now.date() - opened_at.date()).days if opened_at and hasattr(opened_at, "date") else None
                    opt_type = "Put" if "put" in s else "Call" if s else None
                    spread_type = "debit" if "debit" in s else "credit" if "credit" in s else None
                    pos_type = "option_spread" if pos.get("short_strike") else ("option" if pos.get("asset_type") == "OPTION" else "stock")

                    await conn.execute("""
                        INSERT INTO closed_positions
                            (ticker, position_type, direction, quantity,
                             option_type, strike, short_strike, expiry, spread_type,
                             cost_basis, exit_value, exit_price, pnl_dollars, pnl_percent,
                             opened_at, closed_at, hold_days, signal_id, account,
                             close_reason, notes)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                                $14, $15, $16, $17, $18, $19, $20, $21)
                    """,
                        pos["ticker"], pos_type, pos["direction"], close_qty,
                        opt_type,
                        float(pos["long_strike"]) if pos.get("long_strike") else None,
                        float(pos["short_strike"]) if pos.get("short_strike") else None,
                        date.fromisoformat(str(pos["expiry"])[:10]) if pos.get("expiry") else None,
                        spread_type,
                        cost_basis_val, exit_val, req.exit_price,
                        realized_pnl, pnl_pct,
                        opened_at, now, hold_days,
                        pos.get("signal_id"), pos.get("account", "ROBINHOOD"),
                        req.close_reason or "manual", req.notes,
                    )

                # Cash adjustment — same conn/transaction as position update
                if req.exit_price is not None:
                    multiplier = 1 if is_stock else 100
                    exit_value = round(abs(req.exit_price) * multiplier * close_qty, 2)
                    d_close = (pos.get("direction") or "").upper()
                    is_short_equity = d_close == "SHORT" and is_stock
                    cash_delta = -exit_value if (s in CREDIT_STRUCTURES or is_short_equity) else exit_value
                    try:
                        close_cash_ok = await _adjust_account_cash_with_conn(conn, pos.get("account", "ROBINHOOD"), cash_delta)
                    except Exception as e:
                        logger.error("Cash adjustment failed on close: %s", e)
                        close_cash_ok = False

    except HTTPException:
        if attempt_id:
            try:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE close_attempts SET status = 'failed', error_message = $1 WHERE id = $2",
                        "position not found or locked", attempt_id,
                    )
            except Exception:
                pass
        raise
    except Exception as e:
        if attempt_id:
            try:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE close_attempts SET status = 'failed', error_message = $1 WHERE id = $2",
                        str(e)[:500], attempt_id,
                    )
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Close failed: {e}")

    # Transaction committed — update audit record
    if attempt_id:
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE close_attempts SET status = 'completed', trade_id = $1 WHERE id = $2",
                    trade_id, attempt_id,
                )
        except Exception:
            pass

    # Proximity attribution (background — fire after transaction commits)
    if trade_id:
        try:
            from analytics.proximity_attribution import attribute_trade
            asyncio.ensure_future(attribute_trade(
                trade_id=trade_id, ticker=pos["ticker"],
                action='close', timestamp=datetime.now(timezone.utc),
            ))
        except Exception as e:
            logger.warning(f"Proximity attribution failed: {e}")

    # Signal resolution (background — safe after transaction commits; pool sees committed state)
    if not is_partial and pos.get("signal_id"):
        asyncio.ensure_future(
            _resolve_signal_with_failure_logging(pool, dict(row), req.exit_price, realized_pnl, trade_outcome, now)
        )

    result = _row_to_dict(updated) if updated else pos

    try:
        await manager.broadcast_position_update({
            "action": "POSITION_PARTIAL_CLOSE" if is_partial else "POSITION_CLOSED",
            "position": result,
        })
    except Exception:
        pass

    return {
        "status": "partial_close" if is_partial else "closed",
        "position": result,
        "trade_id": trade_id,
        "realized_pnl": realized_pnl,
        "trade_outcome": trade_outcome,
        "closed_qty": close_qty,
        "remaining_qty": total_qty - close_qty if is_partial else 0,
        "cash_adjusted": close_cash_ok,
    }


# ── CLOSE ATTEMPTS (audit log) ────────────────────────────────────────

@router.get("/v2/positions/{position_id}/close-attempts")
async def get_close_attempts(position_id: str, _=Depends(require_api_key)):
    """Return the audit log of close attempts for a position (most recent first)."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM close_attempts WHERE position_id = $1 ORDER BY attempted_at DESC LIMIT 20",
            position_id,
        )
    return {"position_id": position_id, "attempts": [dict(r) for r in rows]}


# ── DELETE ────────────────────────────────────────────────────────────

@router.delete("/v2/positions/{position_id}")
async def delete_position(position_id: str, _=Depends(require_api_key)):
    """Delete a position (for errors/test data). Reverses cash adjustment from creation."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM unified_positions WHERE position_id = $1", position_id
        )
    if not row:
        raise HTTPException(status_code=404, detail=f"Position {position_id} not found")

    pos = _row_to_dict(row)

    # Reverse cash for OPEN positions (closed positions already had cash adjusted on close)
    cash_ok = True
    if pos.get("status") == "OPEN" and pos.get("cost_basis"):
        s = (pos.get("structure") or "").lower()
        cost = float(pos["cost_basis"])
        d_del = (pos.get("direction") or "").upper()
        is_short_equity = d_del == "SHORT" and s in ("stock", "stock_short", "short_stock", "")
        # Reverse: credit structures added cash at open → now subtract. Debit subtracted → now add.
        cash_delta = -cost if (s in CREDIT_STRUCTURES or is_short_equity) else cost
        try:
            cash_ok = await _adjust_account_cash(pool, pos.get("account", "ROBINHOOD"), cash_delta)
        except Exception as e:
            logger.error("Cash reversal failed on delete: %s", e)
            cash_ok = False

    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM unified_positions WHERE position_id = $1", position_id
        )

    try:
        await manager.broadcast_position_update({
            "action": "POSITION_DELETED",
            "position_id": position_id,
        })
    except Exception:
        pass

    return {"status": "deleted", "position_id": position_id, "cash_reversed": cash_ok}


# ── BULK OPERATIONS ───────────────────────────────────────────────────

@router.post("/v2/positions/bulk")
async def bulk_create_positions(req: BulkRequest, _=Depends(require_api_key)):
    """Create or update multiple positions at once (CSV import, screenshot sync)."""
    pool = await get_postgres_client()
    created = []
    errors = []

    for item in req.positions:
        try:
            position_id = _generate_position_id(item.ticker)

            # Infer direction
            direction = item.direction or (infer_direction(item.structure) if item.structure else "LONG")

            # Normalize strikes before risk calc
            n_long, n_short = normalize_spread_strikes(
                item.long_strike, item.short_strike, item.structure
            )

            # Calculate risk
            max_loss = None
            max_profit = None
            breakeven = []
            if item.structure and item.entry_price is not None:
                risk = calculate_position_risk(
                    structure=item.structure,
                    entry_price=item.entry_price,
                    quantity=item.quantity,
                    long_strike=n_long,
                    short_strike=n_short,
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
                    expiry, dte, n_long, n_short,
                    item.source, item.notes, status,
                    exit_price, exit_date_val, realized_pnl, trade_outcome,
                )

            # Auto-adjust cash for OPEN positions only (closed imports don't affect current cash)
            if status == "OPEN" and item.entry_price:
                s_lower = (item.structure or "").lower()
                bulk_cost = abs(item.entry_price) * (1 if s_lower in ("stock", "stock_long", "long_stock") else 100) * item.quantity
                cash_delta = bulk_cost if s_lower in CREDIT_STRUCTURES else -bulk_cost
                try:
                    await _adjust_account_cash(pool, "ROBINHOOD", cash_delta)
                except Exception:
                    pass

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


# ── RECONCILE CASH ───────────────────────────────────────────────────

@router.post("/v2/positions/reconcile-cash")
async def reconcile_cash(request: Request, _=Depends(require_api_key)):
    """Set cash to a known value from the broker. Fixes all accumulated drift."""
    body = await request.json()
    known_cash = body.get("cash")
    account = body.get("account", "ROBINHOOD")
    if known_cash is None:
        raise HTTPException(status_code=400, detail="cash field required")

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT account_name, cash FROM account_balances")
        for row in rows:
            if _match_account_balance(account, row["account_name"]):
                old_cash = float(row["cash"] or 0)
                drift = round(float(known_cash) - old_cash, 2)
                await conn.execute(
                    "UPDATE account_balances SET cash = $1, updated_at = NOW(), updated_by = 'cash_reconcile' WHERE account_name = $2",
                    round(float(known_cash), 2), row["account_name"],
                )
                logger.info("Cash reconciled for %s: was $%.2f, now $%.2f (drift: $%+.2f)",
                           row["account_name"], old_cash, float(known_cash), drift)
                return {"status": "reconciled", "account": row["account_name"],
                        "old_cash": old_cash, "new_cash": float(known_cash), "drift": drift}

    raise HTTPException(status_code=404, detail=f"No account_balance row matching '{account}'")


# ── RECONCILE (screenshot sync) ──────────────────────────────────────

@router.post("/v2/positions/reconcile")
async def reconcile_positions(req: ReconcileRequest, _=Depends(require_api_key)):
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
                        ep["quantity"], ep.get("structure", ""),
                        direction=ep.get("direction", "")
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

async def run_mark_to_market() -> dict:
    """
    Core mark-to-market logic. Callable from background loop or HTTP endpoint.
    Fetches current spread values via Polygon.io options snapshots.
    Falls back to yfinance underlying price for equity positions.
    Updates unrealized P&L based on actual spread mid-prices.
    """
    # UW API only — Polygon is deprecated
    try:
        from integrations.uw_api import (
            get_spread_value, get_single_option_value, get_multi_leg_value, UW_API_KEY
        )
    except ImportError:
        UW_API_KEY = ""
        get_spread_value = None
        get_single_option_value = None
        get_multi_leg_value = None

    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM unified_positions WHERE status = 'OPEN'"
        )

    if not rows:
        return {"status": "no_open_positions", "updated": 0}

    updated = 0
    errors = []
    use_options_pricing = bool(UW_API_KEY) and get_spread_value is not None

    # Cache chain snapshots per ticker to avoid duplicate API calls
    for row in rows:
        ticker = row["ticker"]
        structure = (row.get("structure") or "").lower()
        at = (row.get("asset_type") or "").upper()
        entry_price = float(row["entry_price"]) if row["entry_price"] else None
        quantity = row["quantity"]
        expiry = row.get("expiry")
        long_strike = float(row["long_strike"]) if row.get("long_strike") else None
        short_strike = float(row["short_strike"]) if row.get("short_strike") else None
        # Normalize strike order in case DB has them swapped
        long_strike, short_strike = normalize_spread_strikes(
            long_strike, short_strike, structure
        )

        if entry_price is None:
            continue

        current_price = None
        unrealized = None
        greeks_json = None
        long_leg_price = None
        short_leg_price = None

        # --- Multi-leg path: iron condors, straddles, etc. via legs JSONB ---
        legs_data = row.get("legs")

        # Auto-infer legs from notes if missing for multi-leg structures
        if not legs_data and structure in MULTI_LEG_STRUCTURES:
            inferred = _infer_legs_from_notes(row.get("notes") or "")
            if inferred:
                legs_data = inferred
                # Persist inferred legs back to DB so future MTM runs don't re-parse
                try:
                    legs_json_str = json.dumps(inferred)
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE unified_positions SET legs = $1 WHERE position_id = $2",
                            legs_json_str, row["position_id"],
                        )
                    logger.info("Auto-populated legs for %s from notes", row["position_id"])
                except Exception as e:
                    logger.warning("Failed to persist inferred legs for %s: %s", row["position_id"], e)

        if use_options_pricing and expiry and legs_data:
            try:
                if isinstance(legs_data, str):
                    legs_data = json.loads(legs_data)
                if isinstance(legs_data, list) and len(legs_data) >= 2:
                    result = await get_multi_leg_value(ticker, legs_data, str(expiry))
                    if result and result.get("net_mark") is not None:
                        current_price = abs(result["net_mark"])
                        direction = (row.get("direction") or "").upper()
                        unrealized = _compute_unrealized_pnl(
                            entry_price, current_price, quantity, structure,
                            direction=direction,
                        )
                        greeks_json = json.dumps({
                            "leg_details": result.get("leg_details"),
                            "underlying_price": result.get("underlying_price"),
                        })
            except Exception as e:
                errors.append({"position_id": row["position_id"], "error": str(e)})
                logger.warning("Multi-leg mark-to-market failed for %s: %s", row["position_id"], e)

        # Guard: multi-leg structures without legs data must NOT fall through
        # to spread/single-leg/yfinance paths — those produce wrong prices.
        if current_price is None and structure in MULTI_LEG_STRUCTURES and not legs_data:
            logger.warning(
                "Skipping %s: structure=%s requires legs JSONB but none found",
                row["position_id"], structure,
            )
            continue

        # --- Polygon path: real spread-level pricing ---
        if current_price is None and use_options_pricing and expiry and long_strike:
            try:
                if short_strike and ("spread" in structure or "credit" in structure or "debit" in structure):
                    # Spread position — get both legs
                    result = await get_spread_value(
                        ticker, long_strike, short_strike, str(expiry), structure
                    )
                    if result and result.get("spread_value") is not None:
                        current_price = result["spread_value"]
                        long_leg_price = result.get("long_mid")
                        short_leg_price = result.get("short_mid")
                        direction = (row.get("direction") or "").upper()
                        unrealized = _compute_unrealized_pnl(
                            entry_price, current_price, quantity, structure,
                            direction=direction,
                        )

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
                        long_leg_price = result["option_value"]
                        unrealized = _compute_unrealized_pnl(
                            entry_price, current_price, quantity, structure,
                            direction=(row.get("direction") or ""),
                        )
                        greeks_json = json.dumps({
                            "greeks": result.get("greeks"),
                            "underlying_price": result.get("underlying_price"),
                        })

            except Exception as e:
                errors.append({"position_id": row["position_id"], "error": str(e)})
                logger.warning("UW mark-to-market failed for %s: %s", row["position_id"], e)

        # --- Fallback: yfinance for equity or if Polygon failed ---
        # GUARD: Never use stock price for OPTION or SPREAD positions — even if
        # structure is empty/null, asset_type tells us it's not a stock.
        at = (row.get("asset_type") or "").upper()
        is_equity_position = structure in ("stock", "stock_long", "long_stock", "stock_short", "short_stock", "") and at not in ("OPTION", "SPREAD")
        if current_price is None and is_equity_position:
            try:
                import yfinance as yf
                t = yf.Ticker(ticker)
                info = t.fast_info
                if hasattr(info, 'last_price') and info.last_price:
                    current_price = float(info.last_price)
                    unrealized = _compute_unrealized_pnl(
                        entry_price, current_price, quantity, structure,
                        direction=row.get("direction", "")
                    )
            except Exception:
                pass

        if current_price is not None and unrealized is not None:
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE unified_positions SET
                        current_price = $1, unrealized_pnl = $2,
                        long_leg_price = $3, short_leg_price = $4,
                        price_updated_at = NOW(), updated_at = NOW()
                    WHERE position_id = $5
                """, current_price, unrealized, long_leg_price, short_leg_price, row["position_id"])
            updated += 1
        elif current_price is None and at in ("OPTION", "SPREAD") and row.get("current_price") is not None:
            # Options/spread position we couldn't price — clear any stale/wrong
            # stock-level price that may have been set by a previous buggy run
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE unified_positions SET
                        current_price = NULL, unrealized_pnl = 0,
                        long_leg_price = NULL, short_leg_price = NULL,
                        updated_at = NOW()
                    WHERE position_id = $1
                """, row["position_id"])
            logger.info("Cleared stale stock-price from options position %s (%s)", row["position_id"], ticker)

    result = {"status": "updated", "updated": updated, "source": "uw" if use_options_pricing else "yfinance"}
    if errors:
        result["errors"] = errors
    return result


@router.post("/v2/positions/mark-to-market")
async def mark_to_market(_=Depends(require_api_key)):
    """HTTP wrapper for mark-to-market. Background loop calls run_mark_to_market() directly."""
    return await run_mark_to_market()


