"""
Brief 10 — Unified Positions API (v2)
One table, one API, one source of truth for all positions.
Replaces the fragmented positions + open_positions + options_positions system.
"""

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from utils.pivot_auth import require_api_key
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
import asyncio
import functools
import logging
import json
import os
import time

from database.postgres_client import get_postgres_client
from database.redis_client import get_redis_client
from websocket.broadcaster import manager
from models.position_risk import calculate_position_risk, infer_direction
from models.position_lots import (  # R-IV.441(a): the position row is the AGGREGATE
    BROKER_VERIFIED, IMPORT_PARENT_SOURCES, LOT_SOURCE_PROVENANCE, SCREEN_VERIFIED,
    derive_aggregate, fifo_plan, is_verified, outranks, provenance_for_lot, provenance_for_parent,
)
from models.accounts import (  # R-IV.445(a): one vocabulary, read by every write path
    CANONICAL_ACCOUNTS, canonical_account,
)
from models.position_status import DUPLICATE_OF  # R-IV.449(a): retired, not deleted
from services.leg_mark import (  # R-IV.458(a)/460(b): legs, not names, say what is held
    entry_orientation, mark_from_legs, prior_is_good, stale_reason,
)
from models.leg_payoff import (  # R-IV.460(c): any number of legs, no allowlist
    analyze, display_strikes, recognize,
)
from api.mark_guard import (  # R-IV.394 (T1), now reaching the mark job (R-IV.462(d))
    MARK_REJECTED, evaluate_mark, mark_is_writable,
)
from utils.audit_actor import MARK_TO_MARKET, name_actor  # R-IV.462(b)
from utils.book_time import book_instant, optional_instant  # R-IV.464(a): one date, one instant

# R-IV.454(d): each terminal status, and the path that records how a position reached it.
TERMINAL_VIA_PATH = {
    "CLOSED": "POST /v2/positions/{id}/close (or /reduce for part of it)",
    "EXPIRED": "the expiry sweep, which records the expiry date and an UNKNOWN result",
    "DUPLICATE_OF": "POST /v2/positions/{id}/retire-duplicate, which names the keeper",
}

from api._swr_cache import SWRCache
from api._position_write_scope import (  # D1 second half: allowlist prevents
    WriteScope, assert_columns_allowed, assert_derived_not_edited,
)
from utils.json_sanitize import dumps_jsonb

logger = logging.getLogger(__name__)
router = APIRouter()

# Phase 3 SWR wrapper for /v2/positions. Polling cadence is 30s from the
# dashboard, so the fresh+stale window (ttl=3 + stale_ttl=27) lines up with
# the natural cadence: most polls hit the stale-but-servable window and
# return cached data instantly while a background refresh fires.
#
# Cache key namespacing (AEGIS): the user-id placeholder is fixed for
# single-user mode today. Swap "default" for the real user_id when multi-user
# is added. The cache wrapper API supports user-scoping via the key string.
_swr_instance: Optional[SWRCache] = None


async def _get_swr() -> SWRCache:
    global _swr_instance
    if _swr_instance is None:
        redis_client = await get_redis_client()
        _swr_instance = SWRCache(redis_client, default_ttl=3, stale_ttl=27)
    return _swr_instance

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
    """Does this balance row satisfy a request for `account_filter`?

    T2 (R-IV.394): membership is LOOKED UP in config.accounts, never inferred from
    the shape of a string.

    THE DEFECT THIS REPLACES, registered at P0.1: this function matched by
    `startswith`, and the legacy `FIDELITY` filter normalised to the prefix
    `fidelity` — which matched `Fidelity Roth`, `Fidelity 401A` AND `Fidelity 403B`
    alike. A request for the ONE traded account silently summed TWO parked ones
    with it. A prefix answers "does this name begin with those letters", which is a
    question about spelling, asked on a surface where the question is about
    ownership of money.
    """
    from config.accounts import accounts_match
    return accounts_match(account_filter, balance_name)


def _entry_fill_time(req, row):
    """When the position was actually filled, for its opening lot.

    The entry DATE the principal gave, when he gave one -- his fill happened on his
    clock, not on the write's. Falling back to the row's creation stamp is a last
    resort and is the one case where the two can differ by a day: R-IV.474(b) already
    had to correct a RAMZ row whose entry_date was the write's own clock.
    """
    for candidate in (getattr(req, "entry_date", None), (row or {}).get("entry_date")):
        if candidate:
            try:
                return _when(candidate, "entry_date")
            except Exception:  # noqa: BLE001
                continue
    return (row or {}).get("created_at") or datetime.now(timezone.utc)


async def _adjust_account_cash_with_conn(conn, account: str, delta: float,
                                         *, source_ref: str = None,
                                         description: str = None,
                                         event_date=None) -> bool:
    """Move cash for a trade, and WRITE THE EVENT THAT MOVED IT.

    MONEY INTEGRITY, the part R-IV.493(f) said to fix first. This function is the
    largest mover of cash in the system — every entry and every close comes through
    it — and until now it wrote no event at all. It did `cash = cash + delta` and
    logged a line. So the ledger could not have reconstructed the balance even in
    principle: most of the movements were never written down.

    The stored total is still maintained, because six other readers depend on it and
    removing it in the same change would be two risks wearing one commit. What is
    new is that the movement is now a ROW: typed, dated, attributed to the position
    that caused it, and idempotent. A balance can be derived from those.

    The event is written on the CALLER'S connection, so it lands in the same
    transaction as the position change or not at all. Cash that moved without an
    event, or an event without the movement, are both worse than neither.
    """
    from services.cash_ledger import (TRADE_CREDIT, TRADE_DEBIT, dedup_key,
                                      stored_cash_is_retired)

    rows = await conn.fetch("SELECT account_name, cash FROM account_balances")
    for row in rows:
        if _match_account_balance(account, row["account_name"]):
            acct = row["account_name"]
            amount = round(delta, 2)
            # R-IV.551(b): once an account is anchored the stored total is read-only
            # history and the derived figure is the answer. The EVENT below is still
            # written -- that is what the derived figure is made of.
            if await stored_cash_is_retired(conn, acct):
                logger.info("cash: %s is anchored, stored total left untouched "
                            "(%+.2f recorded as an event)", acct, amount)
            else:
                await conn.execute(
                    "UPDATE account_balances SET cash = cash + $1, updated_at = NOW(), updated_by = 'auto' WHERE account_name = $2",
                    amount, acct,
                )
            etype = TRADE_CREDIT if amount >= 0 else TRADE_DEBIT
            when = event_date or date.today()
            # A key only where the movement can be attributed. Unattributed cash is
            # written WITHOUT one -- the unique index is partial, so a NULL key is
            # outside it -- because two genuine same-day, same-amount movements with
            # nothing to tell them apart would otherwise dedup into one, and losing a
            # real movement is worse than repeating one.
            key = dedup_key(acct, etype, amount, when, source_ref) if source_ref else None
            try:
                await conn.execute(
                    """INSERT INTO cash_flows
                           (account_name, flow_type, amount, description, activity_date,
                            imported_from, source_ref, dedup_key)
                       VALUES ($1, $2, $3, $4, $5::date, 'TRADE_ENTRY', $6, $7)
                       ON CONFLICT (account_name, dedup_key) WHERE dedup_key IS NOT NULL
                       DO NOTHING""",
                    acct, etype, amount,
                    description or f"trade cash movement ({source_ref or 'unattributed'})",
                    when, source_ref, key,
                )
            except Exception as exc:  # noqa: BLE001
                # LOUD, and it fails the transaction with the position change rather
                # than leaving money that moved with nothing to show for it.
                logger.error("cash event write FAILED for %s %+.2f (%s): %s",
                             acct, amount, source_ref, type(exc).__name__)
                raise
            logger.info("Cash adjusted for %s: %+.2f (%s, ref=%s)",
                        acct, amount, etype, source_ref)
            return True
    logger.error("CASH ADJUSTMENT FAILED: No matching account_balance row for account=%s (delta=%+.2f)", account, delta)
    return False


async def _adjust_account_cash(pool, account: str, delta: float, **kw) -> bool:
    """Backward-compatible pool-based cash adjustment. Use _adjust_account_cash_with_conn
    when inside a transaction to keep cash updates atomic.

    `**kw` carries `source_ref` / `description` / `event_date` through to the event,
    so a caller that knows which position moved the money can say so.
    """
    async with pool.acquire() as conn:
        return await _adjust_account_cash_with_conn(conn, account, delta, **kw)


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
    quantity: float = Field(default=1, alias="contracts")   # R-IV.458(b): fractions held
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
    # R-IV.463(b): who is asking, for the audit -- the optional actor PATCH already takes. Absent,
    # the write is recorded as legacy-ui: a request whose caller named no one.
    actor: Optional[str] = None
    reason: Optional[str] = None


class UpdatePositionRequest(BaseModel):
    # FEAT-POSITION-LIFECYCLE Phase 2, R-IV.116: OPTIONAL at the API layer. Absent ->
    # the audit trigger stamps actor='legacy-ui' and reason NULL, so the legacy caller
    # (app.js:11073) needs no coordinated change. The new lifecycle UI requires them
    # client-side and sends both.
    reason: Optional[str] = None
    actor: Optional[str] = None
    # R-IV.143(2). Documentary vocabulary, no CHECK constraint: CORE | B1_MACRO |
    # B1_C_CONVEXITY | B2_TACTICAL | B3_SCALP | HEDGE | MOMENTUM | OTHER. A semantic
    # field, so MANUAL_EDIT may write it — the D1 allowlist refuses marks and realized
    # fields, not position semantics. NULL is untagged; OTHER is a deliberate choice.
    strategy_tag: Optional[str] = None
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
    quantity: Optional[float] = None   # R-IV.458(b): the broker's quantity, fractions included
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
    quantity: Optional[float] = None  # If < total qty, partial close (reduce position, keep remainder open)
    exit_value: Optional[float] = None       # Total exit value (exit_price × multiplier × qty)
    trade_outcome: Optional[str] = None      # WIN / LOSS / BREAKEVEN (frontend-computed)
    loss_reason: Optional[str] = None        # SETUP_FAILED / EXECUTION_ERROR / MARKET_CONDITIONS
    close_reason: Optional[str] = "manual"   # profit / loss / expired / manual
    # R-IV.447(b): an exit that already happened keeps the day it happened on. The close path
    # stamped NOW() unconditionally, so a missed exit recorded weeks later read as today's —
    # and the date is what every later reconciliation joins on.
    exit_date: Optional[str] = None
    # The realized figure the caller computed, CHECKED rather than stored. When it disagrees
    # with what this row's own basis implies, the write is refused and both numbers are named:
    # a plausible-looking number from a different method is the failure mode here, and one of
    # them being 16x the other is exactly how it presents.
    expected_realized: Optional[float] = None
    realized_tolerance: float = 0.01
    # R-IV.463(b): who is asking, for the audit -- the optional actor PATCH already takes. Absent,
    # the write is recorded as legacy-ui: a request whose caller named no one.
    actor: Optional[str] = None
    reason: Optional[str] = None


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
    # R-IV.463(b): who is asking, for the audit -- the optional actor PATCH already takes. Absent,
    # the write is recorded as legacy-ui: a request whose caller named no one.
    actor: Optional[str] = None
    reason: Optional[str] = None


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
    # R-IV.463(b): who is asking, for the audit -- the optional actor PATCH already takes. Absent,
    # the write is recorded as legacy-ui: a request whose caller named no one.
    actor: Optional[str] = None
    reason: Optional[str] = None


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


def _orientation_by_name(structure: str, direction: str = "") -> int:
    """+1 debit, -1 credit, from the NAME -- for rows whose legs are not in position_legs.

    The one place the name decides a side. A position with legs is oriented by its legs
    (services.leg_mark.entry_orientation); the P&L formula below and the legacy mark path read
    this, so the two can never disagree about which way a named row was entered."""
    s = (structure or "").lower()
    d = (direction or "").upper()
    if s in CREDIT_STRUCTURES and not (s in ("iron_condor", "iron_butterfly") and d == "LONG"):
        return -1
    return 1


def _compute_unrealized_pnl(entry_price: float, current_price: float, quantity: int, structure: str, asset_type: str = "", direction: str = "", orientation: Optional[int] = None) -> float:
    """Compute unrealized P&L based on position type and credit/debit nature.

    `orientation` (R-IV.463(c)): +1 debit / -1 credit, decided from a position's legs. The mark
    is the signed net in that orientation, so P&L is orientation x (mark - entry) for every
    structure -- including one whose mark has crossed below zero."""
    # R-IV.458(b): quantity is NUMERIC now and arrives as Decimal; Decimal * float raises.
    quantity = float(quantity or 0)
    entry_price = float(entry_price) if entry_price is not None else entry_price
    current_price = float(current_price) if current_price is not None else current_price
    if orientation in (1, -1) and entry_price is not None and current_price is not None:
        return round(orientation * (current_price - entry_price) * 100 * quantity, 2)
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
    # Credit (received at open, pay to close): profit when current < entry. Debit: profit when
    # current > entry. A LONG iron condor/butterfly is a debit. One rule, _orientation_by_name.
    return round(_orientation_by_name(s, d) * (current_price - entry_price) * 100 * quantity, 2)


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
    # R-IV.445(a): the account comes from the canonical vocabulary, not from whatever arrived.
    # `.upper()` alone accepted any string spelled in capitals, which is how rows kept being
    # written under a retired alias eleven days after the remap — the path minted them. An
    # alias normalises; anything else is refused with the vocabulary and the value.
    account = canonical_account(req.account or "ROBINHOOD")

    # R-IV.75(d) ETF-only invariant, enforced AT ENTRY. Refusing here is the whole
    # point: an OPTION row on the Roth is prima facie mis-attributed, and a row admitted
    # now becomes a reconciliation problem for whoever finds it months later.
    _assert_etf_only(account, req.asset_type)
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
        old_qty = float(existing["quantity"] or 0)
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
        async with pool.acquire() as conn, conn.transaction():
            await name_actor(conn, req.actor or "legacy-ui", req.reason or None)  # R-IV.463(b)
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
                cash_ok = await _adjust_account_cash(
                    pool, account, cash_delta,
                    source_ref=existing.get("position_id"),
                    description="added to position")
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

    async with pool.acquire() as conn, conn.transaction():
        await name_actor(conn, req.actor or "legacy-ui", req.reason or None)  # R-IV.463(b)
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
            dumps_jsonb(req.legs) if req.legs else None,
            req.entry_price, req.quantity, cost_basis,
            max_loss, max_profit, req.stop_loss, req.target_1, req.target_2,
            breakeven if breakeven else None,
            expiry, dte, norm_long, norm_short,
            req.source, req.signal_id, account,
            _combine_notes(req.notes, req.thesis, req.bucket),
            req.tags if req.tags else None,
        )

        # R-IV.566(c): A POSITION IS MEASURED THE MOMENT IT EXISTS.
        #
        # Rows entered here carried no lots until a cleanup ran, so they had no open
        # remainder and no value: the loss alert was blind to a position on the day
        # it opened, and every balance went PARTIAL for it. Measured 2026-09-24, the
        # only two open rows without lots were both created through this path today.
        #
        # Same transaction as the position, because a position without its lot is
        # the state this removes -- creating one and then failing to lot it would
        # reproduce the defect with an extra step.
        #
        # `source` carries the instant; `broker_ref` stays NULL for the cleanup to
        # fill when it matches the row against the export, which is the "upgrades
        # the reference" step. `provenance` is PRINCIPAL_REPORTED -- the weakest
        # claim in the vocabulary, which is what "he said so, nothing checked it"
        # means.
        if req.entry_price is not None and req.quantity:
            from models.position_lots import PRINCIPAL_REPORTED, principal_entry_source

            try:
                await conn.execute(
                    """INSERT INTO position_lots
                           (position_id, fill_time, qty, price, fees, source, provenance)
                       VALUES ($1, $2, $3, $4, 0, $5, $6)""",
                    position_id, _entry_fill_time(req, row),
                    req.quantity, abs(float(req.entry_price)),
                    principal_entry_source(datetime.now(timezone.utc)),
                    PRINCIPAL_REPORTED)
            except Exception as exc:  # noqa: BLE001
                # LOUD, and it fails the whole create. A position that exists without
                # its lot is exactly what this is here to stop.
                logger.error("position %s: opening lot could not be written (%s)",
                             position_id, type(exc).__name__)
                raise

    # Auto-adjust cash: deduct cost for debit, add premium for credit
    # Short stock: selling shares generates cash proceeds (like a credit)
    cash_ok = True
    if cost_basis:
        s = (req.structure or "").lower()
        d = (direction or "").upper()
        is_short_equity = d == "SHORT" and s in ("stock", "stock_short", "short_stock", "")
        cash_delta = cost_basis if (s in CREDIT_STRUCTURES or is_short_equity) else -cost_basis
        try:
            cash_ok = await _adjust_account_cash(
                pool, account, cash_delta, source_ref=position_id,
                description="position opened")
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

EXPIRY_SWEEP_ACTOR = "expiry-sweep"


async def _sweep_expired_positions() -> List[Dict[str, Any]]:
    """End OPEN positions whose expiry has passed, recording the result, never leaving it absent.

    R-IV.454(d): a terminal status is reachable only through a path that records the exit. An
    expiry is a fact about the DATE (the contract ended on its expiry) and says nothing about the
    value: a spread can expire in the money, a long option worthless. So the sweep records what it
    knows, exit_date = the expiry, and writes the result as UNKNOWN explicitly, which a reader can
    tell apart from a result that was simply never written.

    AND IT RUNS ON A SCHEDULE, NEVER ON A READ. It used to be called from GET /v2/positions and
    from the portfolio summary, so a request to LOOK at the book could end positions in it. It is
    now driven by the stable-jobs loop and by the authenticated manual endpoint. Never raises.
    """
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.actor', $1, true)",
                                   EXPIRY_SWEEP_ACTOR)
                await conn.execute(
                    "SELECT set_config('app.reason', $1, true)",
                    "R-IV.454(d): expiry passed; result recorded as UNKNOWN until marked")
                rows = await conn.fetch("""
                    UPDATE unified_positions
                       SET status = 'EXPIRED',
                           -- R-IV.464(a): the day it expired, in the principal's timezone
                           exit_date = COALESCE(exit_date,
                                                expiry::timestamp AT TIME ZONE 'America/Denver'),
                           trade_outcome = COALESCE(trade_outcome, 'UNKNOWN'),
                           updated_at = NOW()
                     WHERE status = 'OPEN'
                       AND expiry IS NOT NULL
                       AND expiry < CURRENT_DATE
                    RETURNING position_id, ticker, expiry
                """)
        expired = [{"position_id": r["position_id"], "ticker": r["ticker"],
                    "expiry": str(r["expiry"])} for r in rows]
        if expired:
            logger.info("Expiry sweep ended %d position(s), result UNKNOWN: %s",
                        len(expired), [e["position_id"] for e in expired])
        return expired
    except Exception as e:
        logger.warning("Expired position sweep failed: %s", e)
        return []


@router.get("/v2/positions", dependencies=[Depends(require_api_key)])
async def list_positions(
    status: str = Query("OPEN", description="Filter by status: OPEN, CLOSED, EXPIRED, or ALL"),
    ticker: Optional[str] = Query(None),
    account: Optional[str] = Query(None),
    asset_type: Optional[str] = Query(None, description="Filter by asset type: OPTION, EQUITY, SPREAD"),
):
    """List positions, filtered by status.

    Phase 3 (perf-architecture brief): wrapped in SWR. Repeat hits within the
    3s fresh window return sub-200ms server-side; hits in the 3-30s
    stale-but-servable window return cached data immediately and schedule a
    background refresh. Response gains `as_of` + `cache_age_seconds`.
    """
    swr = await _get_swr()
    status_upper = status.upper()
    ticker_upper = ticker.upper() if ticker else None
    account_upper = account.upper() if account else None
    asset_type_upper = asset_type.upper() if asset_type else None

    cache_key = (
        f"positions:v1:default:{status_upper}:"
        f"{ticker_upper or '*'}:{asset_type_upper or '*'}:{account_upper or '*'}"
    )

    async def _do_compute():
        return await _compute_positions(status_upper, ticker_upper, account_upper, asset_type_upper)

    data, age = await swr.get_or_refresh(cache_key, compute_fn=_do_compute)
    return {
        **data,
        "as_of": int(time.time() - age),
        "cache_age_seconds": age,
    }


async def _compute_positions(
    status_upper: str,
    ticker_upper: Optional[str],
    account_upper: Optional[str],
    asset_type_upper: Optional[str],
) -> Dict[str, Any]:
    """Heavy assembly path for /v2/positions — pulled out of the handler so SWR can wrap it."""
    # R-IV.454(d): the expiry sweep used to run HERE, so a request to look at the book could end
    # positions in it. It runs on the stable-jobs schedule now; a read writes nothing.

    pool = await get_postgres_client()

    conditions = []
    params = []
    idx = 1

    if status_upper != "ALL":
        conditions.append(f"status = ${idx}")
        params.append(status_upper)
        idx += 1

    if ticker_upper:
        conditions.append(f"ticker = ${idx}")
        params.append(ticker_upper)
        idx += 1

    if asset_type_upper:
        conditions.append(f"asset_type = ${idx}")
        params.append(asset_type_upper)
        idx += 1

    if account_upper:
        if account_upper == "FIDELITY":
            conditions.append("account LIKE 'FIDELITY%'")
        else:
            conditions.append(f"account = ${idx}")
            params.append(account_upper)
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

    # Gap 1 (R-IV.526(b), R-IV.522(a)): the money this route serves is derived from
    # the lots that are still open, in one place, by one author. `max_loss` and
    # `unrealized_pnl` carry the lot-derived figures; what the table holds moves to
    # `max_loss_stored` / `unrealized_pnl_stored` so the divergence stays readable
    # rather than being overwritten in flight. A row with no lots reads None with a
    # `basis_reason`, because a stand-in figure is the fault being removed.
    #
    # A read still writes nothing (R-IV.454(d)): this derives, it does not repair.
    try:
        from services.read_only.positions import attach_economics, fetch_lots_by_position

        async with pool.acquire() as conn:
            _lots = await fetch_lots_by_position(
                conn, [p.get("position_id") for p in positions])
        attach_economics(positions, _lots)
    except Exception as e:
        # Loud, and the row keeps its stored values rather than losing them: a
        # failure here must not make the screen think the book is empty.
        logger.error("gap 1: lot-derived money unavailable this cycle (%s) — rows "
                     "carry their STORED figures, which may hold the wrong scope",
                     type(e).__name__)

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
    if status_upper == "OPEN":
        try:
            from database.redis_client import get_redis_client
            redis = await get_redis_client()
            if redis:
                position_tickers = []
                keys = []
                for p in positions:
                    ticker = (p.get("ticker") or "").upper()
                    if ticker:
                        position_tickers.append((p, ticker))
                        keys.extend([
                            f"counter_signal:{ticker}",
                            f"confirming_signal:{ticker}",
                            f"uw:flow:{ticker}",
                        ])

                raw_values = await redis.mget(keys) if keys else []

                for i, (p, ticker) in enumerate(position_tickers):
                    base = i * 3
                    raw = raw_values[base]
                    raw_conf = raw_values[base + 1]
                    raw_flow = raw_values[base + 2]
                    if raw:
                        p["counter_signal"] = json.loads(raw)
                    if raw_conf:
                        p["confirming_signal"] = json.loads(raw_conf)
                    # UW flow badge — compare flow sentiment to position direction
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
    """Manually trigger the expiry sweep. Same function as the schedule, so both record the
    same result: exit_date = the expiry, outcome UNKNOWN until marked (R-IV.454(d))."""
    expired = await _sweep_expired_positions()
    return {"status": "ok", "expired_count": len(expired), "expired": expired}


@router.get("/v2/positions/summary", dependencies=[Depends(require_api_key)])
async def portfolio_summary(account: Optional[str] = Query(None)):
    """
    Portfolio summary for the bias row widget and committee context.
    Returns: total positions, capital at risk, net direction, nearest expiry.
    Optional account filter: ?account=ROBINHOOD or ?account=FIDELITY
    """
    # R-IV.454(d): no sweep on a read — see _sweep_expired_positions.

    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM unified_positions WHERE status = 'OPEN' ORDER BY COALESCE(expiry, '2099-12-31'::date) ASC"
        )

    positions = [_row_to_dict(r) for r in rows]

    # Filter by account if specified
    if account:
        account_upper = account.upper()
        # T2: one vocabulary. `FIDELITY` is an ALIAS of FIDELITY_ROTH, not a
        # prefix family — the 401A/403B rows are parked money and out of scope.
        from config.accounts import accounts_match
        positions = [p for p in positions
                     if accounts_match(account, p.get("account") or "ROBINHOOD")]

    # Fetch cash + stored balance from account_balances.
    # Path A: stored `balance` is the headline source of truth. `cash` continues
    # as the running auto-adjusted cash. Both are returned; drift between
    # `stored_balance` and `cash + position_value` triggers the frontend's
    # reconcile banner.
    cash = 0.0
    stored_balance = 0.0
    balance_updated_at = None
    try:
        async with pool.acquire() as conn:
            if account:
                bal_rows = await conn.fetch(
                    "SELECT account_name, cash, balance, updated_at FROM account_balances"
                )
                if account.upper() == "FIDELITY":
                    # T2: an alias resolves to ONE account, not a prefix family.
                    from config.accounts import accounts_match as _am
                    fid_rows = [br for br in bal_rows
                                if _am(account, br["account_name"])]
                    cash = sum(float(br["cash"] or 0) for br in fid_rows)
                    stored_balance = sum(float(br["balance"] or 0) for br in fid_rows)
                    ts = [br["updated_at"] for br in fid_rows if br["updated_at"]]
                    balance_updated_at = min(ts) if ts else None
                else:
                    for br in bal_rows:
                        if _match_account_balance(account, br["account_name"]):
                            cash = float(br["cash"] or 0)
                            stored_balance = float(br["balance"] or 0)
                            balance_updated_at = br["updated_at"]
                            break
            else:
                bal_rows = await conn.fetch(
                    "SELECT cash, balance, updated_at FROM account_balances"
                )
                cash = sum(float(br["cash"] or 0) for br in bal_rows)
                stored_balance = sum(float(br["balance"] or 0) for br in bal_rows)
                ts = [br["updated_at"] for br in bal_rows if br["updated_at"]]
                balance_updated_at = min(ts) if ts else None
    except Exception:
        pass

    if not positions:
        computed_empty = round(cash, 2)
        return {
            "account_balance": round(stored_balance, 2),
            "computed_balance": computed_empty,
            "drift_dollars": round(stored_balance - computed_empty, 2),
            "balance_updated_at": balance_updated_at.isoformat() if balance_updated_at else None,
            "cash": cash,
            "position_value": 0.0,
            "position_count": 0,
            "unpriced_count": 0,
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
    # Skip unpriced positions — market value can't be computed without current_price.
    # Previously the `unrealized_pnl or 0` fallback let NULL-pnl rows contribute their
    # full cost_basis to the total, silently inflating position_value. The frontend
    # already renders an em-dash ("—") for these rows per-position; the aggregate
    # total matches that semantic by excluding them. Count surfaced as unpriced_count
    # in the response so consumers can show "X of Y priced".
    total_position_value = 0.0
    unpriced_count = 0
    for p in positions:
        if p.get("current_price") is None:
            unpriced_count += 1
            continue

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
                qty = float(p.get("quantity") or 0)
                cost = ep * qty * 100
            pnl = p.get("unrealized_pnl") or 0
            total_position_value += cost + pnl
    total_position_value = round(total_position_value, 2)
    # Path A: stored balance is the headline. computed_balance is what cash + MTM
    # implies; drift between them triggers the reconcile banner.
    computed_balance = round(cash + total_position_value, 2)
    account_balance = round(stored_balance, 2)
    drift_dollars = round(stored_balance - computed_balance, 2)
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
        "computed_balance": computed_balance,
        "drift_dollars": drift_dollars,
        "balance_updated_at": balance_updated_at.isoformat() if balance_updated_at else None,
        "cash": cash,
        "position_value": total_position_value,
        "position_count": len(positions),
        "unpriced_count": unpriced_count,
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

    from services.cash_ledger import stored_cash_is_retired

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        # R-IV.551(b): an anchored account's stored total is read-only history.
        # Setting a number here would put a figure nobody derives back in front of
        # readers who are now served the derived one.
        if await stored_cash_is_retired(conn, account_name):
            return {"status": "not_applied", "account": account_name,
                    "cash_unchanged": True,
                    "reason": "this account is anchored, so its stored cash total is "
                              "read-only history (R-IV.551(b)). To set cash to what "
                              "the broker shows, use POST /api/portfolio/cash-reanchor, "
                              "which records the difference instead of hiding it."}
        result = await conn.execute(
            "UPDATE account_balances SET cash = $1, updated_at = NOW(), updated_by = 'dashboard' WHERE account_name = $2",
            float(new_cash), account_name,
        )

    logger.info("Cash balance updated for %s to %.2f", account_name, float(new_cash))
    return {"status": "ok", "account": account_name, "cash": float(new_cash)}


_GREEK_NAMES = ("delta", "gamma", "theta", "vega")


def _empty_coverage(complete: bool) -> dict:
    return {
        "legs_expected": 0,
        "legs_priced": 0,
        "complete": complete,
        "tickers_unavailable": 0,
        "per_greek": {n: {"priced": 0, "expected": 0} for n in _GREEK_NAMES},
    }


def _greeks_unknown(status: str, **extra) -> dict:
    """Failure envelope. Greeks are UNKNOWN — never zero.

    DEF-GREEKS-ZERO: every one of these paths used to emit
    {"delta": 0, "gamma": 0, ...}, so an API outage, a missing key, or a DB error
    rendered as a flat book. Zero is a measurement; these states have no
    measurement to report.
    """
    return {
        "status": status,
        "tickers": {},
        "totals": {n: None for n in _GREEK_NAMES},
        "coverage": _empty_coverage(False),
        "portfolio": {f"net_{n}": None for n in _GREEK_NAMES},
        **extra,
    }


def _greeks_flat(status: str) -> dict:
    """No open positions => genuinely flat. Zero IS the fact here, and complete."""
    return {
        "status": status,
        "tickers": {},
        "totals": {n: 0 for n in _GREEK_NAMES},
        "coverage": _empty_coverage(True),
        "portfolio": {f"net_{n}": 0 for n in _GREEK_NAMES},
    }


@router.get("/v2/positions/greeks", dependencies=[Depends(require_api_key)])
async def portfolio_greeks():
    """
    Aggregate portfolio greeks from the UW options snapshot.

    Reports COVERAGE alongside the numbers: a sum built from some of the legs is
    a floor, not a total, and is labelled as such. Unavailable greeks report None,
    never 0 — an understated delta tells the operator he carries less risk than
    he does, which is the dangerous direction.
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
            return _greeks_unknown("no_api_key")
    except ImportError:
        return _greeks_unknown("unavailable")

    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM unified_positions WHERE status = 'OPEN'"
            )
    except Exception as e:
        logger.error("Greeks: DB query failed: %s", e)
        return _greeks_unknown("db_error")

    if not rows:
        return _greeks_flat("no_positions")

    try:
        positions = [_row_to_dict(r) for r in rows]

        # Group positions by ticker
        by_ticker: Dict[str, list] = {}
        for p in positions:
            by_ticker.setdefault(p["ticker"], []).append(p)

        ticker_greeks = {}
        # Sum only known values; carry coverage so the renderer can present a
        # partial sum as a FLOOR rather than a total (R1).
        greek_sums = {n: 0.0 for n in _GREEK_NAMES}
        greek_priced = {n: 0 for n in _GREEK_NAMES}
        legs_expected_total = 0
        tickers_unavailable = 0

        for ticker, pos_list in by_ticker.items():
            try:
                logger.info("Greeks: fetching for %s (%d positions). Strikes: %s",
                           ticker, len(pos_list),
                           [(p.get("long_strike"), p.get("short_strike"), p.get("expiry")) for p in pos_list])
                greeks_result = await get_ticker_greeks_summary(ticker, pos_list)
                if greeks_result:
                    logger.info("Greeks: %s delta=%s gamma=%s theta=%s vega=%s (%s/%s legs priced)",
                               ticker,
                               greeks_result.get("net_delta"),
                               greeks_result.get("net_gamma"),
                               greeks_result.get("net_theta"),
                               greeks_result.get("net_vega"),
                               greeks_result.get("legs_priced"),
                               greeks_result.get("legs_expected"))
                    ticker_greeks[ticker] = greeks_result

                    # BRANCH BUG FIX. These four lines previously sat in the `else`
                    # arm — the arm where greeks_result is falsy — so the portfolio
                    # totals never accumulated on the success path and were
                    # structurally always zero, while the failure path called
                    # .get() on None and raised straight into the outer handler.
                    # This is the "all zeros" the defect was registered under.
                    legs_expected_total += greeks_result.get("legs_expected", 0) or 0
                    cov = greeks_result.get("coverage") or {}
                    for name in _GREEK_NAMES:
                        v = greeks_result.get(f"net_{name}")
                        if v is None:
                            continue
                        greek_sums[name] += v
                        greek_priced[name] += ((cov.get(name) or {}).get("priced") or 0)
                else:
                    logger.warning("Greeks: %s returned no result (ticker skipped entirely)", ticker)
                    tickers_unavailable += 1
            except Exception as e:
                logger.warning("Greeks fetch failed for %s: %s", ticker, e)
                ticker_greeks[ticker] = {"error": str(e)}

        _places = {"delta": 2, "gamma": 4, "theta": 2, "vega": 2}

        def _total(name: str):
            # No priced legs for this greek => UNKNOWN. Never 0.
            return round(greek_sums[name], _places[name]) if greek_priced[name] else None

        totals = {n: _total(n) for n in _GREEK_NAMES}
        complete = (
            tickers_unavailable == 0
            and legs_expected_total > 0
            and all(greek_priced[n] == legs_expected_total for n in _GREEK_NAMES)
        )
        coverage = {
            "legs_expected": legs_expected_total,
            "legs_priced": min(greek_priced.values()) if greek_priced else 0,
            "complete": complete,
            "tickers_unavailable": tickers_unavailable,
            "per_greek": {n: {"priced": greek_priced[n], "expected": legs_expected_total}
                          for n in _GREEK_NAMES},
        }

        result = {
            "status": "ok",
            "tickers": ticker_greeks,
            "totals": totals,
            "coverage": coverage,
            "portfolio": {f"net_{n}": totals[n] for n in _GREEK_NAMES},
        }

    except Exception as e:
        logger.error("Greeks computation failed: %s", e)
        return _greeks_unknown("computation_error", error=str(e))

    # Cache for 60 seconds + stale cache for 24 hours (after-hours fallback)
    if redis:
        try:
            result_json = json.dumps(result)
            await redis.set("portfolio:greeks:cache", result_json, ex=60)
            await redis.set("portfolio:greeks:stale", result_json, ex=86400)
        except Exception:
            pass

    return result


@router.get("/v2/positions/{position_id}", dependencies=[Depends(require_api_key)])
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
        # R-IV.454(d): a terminal status is reachable only through a path that records the exit.
        # The PATCH records nothing about one, so it cannot end a position; it names the doors
        # that can. (Reopening, a move AWAY from terminal, is not what the rule governs.)
        target = req.status.strip().upper()
        if target in TERMINAL_VIA_PATH:
            raise HTTPException(
                status_code=400,
                detail=(f"status {target} is not set by an edit — it needs "
                        f"{TERMINAL_VIA_PATH[target]}, which records how the position ended. "
                        f"An edit that ends a position leaves a closed row with no result, "
                        f"and nothing downstream can tell that from a real flat trade."))
        sets.append(f"status = ${idx}")
        params.append(target)
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
        # R-IV.456(a): quantity that grows with no price beside it is UNPRICED. The basis is not
        # recomputed -- it was right for everything priced -- and the row says what it does not
        # cover, so a later reader cannot mistake a partial basis for a whole one.
        old_q = float(old_pos.get("quantity") or 0)
        if (req.quantity > old_q and req.cost_basis is None and req.entry_price is None):
            sets.append(f"basis_incomplete_reason = ${idx}")
            params.append(f"R-IV.456(a): quantity {old_q} -> {req.quantity} with no price for "
                          f"the {req.quantity - old_q} added unit(s); basis covers {old_q}")
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
        # R-IV.463(f): a relabelled source re-derives provenance from it -- a row relabelled as
        # landed from a broker record must not go on saying the principal reported it. A
        # BROKER_VERIFIED row keeps its verification: relabelling a source is not un-verifying.
        sets.append(f"provenance = CASE WHEN provenance = ${idx} THEN provenance "
                    f"WHEN entry_price IS NULL THEN 'UNKNOWN' ELSE ${idx + 1} END")
        params.append(BROKER_VERIFIED)      # compared, never assigned: a relabel is not a verification
        params.append(provenance_for_parent(req.source, 0))
        idx += 2
    if req.strategy_tag is not None:
        sets.append(f"strategy_tag = ${idx}")
        params.append(req.strategy_tag)
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
        params.append(_when(req.closed_at, "closed_at"))       # R-IV.464(a)
        idx += 1

    if len(sets) <= 1:
        raise HTTPException(status_code=400, detail="No fields to update")

    # D1 allowlist. A manual edit may write neither mark nor realized fields.
    # Checked against the columns actually entering the SET clause, not against the
    # request model's declared fields, so a column reaching SQL by any route is caught.
    touched = [s.split("=")[0].strip() for s in sets]
    assert_columns_allowed(touched, WriteScope.MANUAL_EDIT)

    # R-IV.444(c): and it may not overwrite what the lots compute. Read against THIS position's
    # evidence — a row with fills behind it has a derived quantity and basis; a row without any
    # has nothing to derive from, and the edit is still the only way to state it.
    async with pool.acquire() as conn:
        has_lots = bool(await conn.fetchval(
            "SELECT 1 FROM position_lots WHERE position_id = $1 LIMIT 1", position_id))
    assert_derived_not_edited(touched, has_lots)

    params.append(position_id)
    set_clause = ", ".join(sets)

    # SET LOCAL only takes effect inside a transaction; without one the audit trigger
    # reads an empty setting and falls back to 'legacy-ui'. Both settings are scoped to
    # this transaction, so concurrent requests cannot see each other's actor.
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.actor', $1, true)",
                               (req.actor or "legacy-ui"))
            await conn.execute("SELECT set_config('app.reason', $1, true)",
                               (req.reason or ""))
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
        # ── T1 MARK GUARD (R-IV.394) ───────────────────────────────────────
        # On any non-OK verdict this writes NOTHING to unrealized_pnl. It does not
        # write zero: a zero P&L is a CLAIM that the position is flat, and it is
        # indistinguishable from a real flat position on every surface downstream.
        # The previous value is left standing, stamped with the reason.
        _mark_status, _mark_reason = evaluate_mark(
            result.get("current_price"), result.get("entry_price"))
        # R-IV.462(b): the recompute belongs to the same request, so it carries the request's
        # actor. It ran after the edit's transaction had closed and was recorded as legacy-ui.
        async with pool.acquire() as conn, conn.transaction():
            await name_actor(conn, req.actor or "legacy-ui", req.reason or None)
            if mark_is_writable(_mark_status):
                await conn.execute(
                    "UPDATE unified_positions SET unrealized_pnl = $1, "
                    "mark_status = $2, mark_checked_at = NOW() WHERE position_id = $3",
                    unrealized, _mark_status, position_id
                )
                result["unrealized_pnl"] = unrealized
            else:
                await conn.execute(
                    "UPDATE unified_positions SET mark_status = $1, "
                    "mark_checked_at = NOW() WHERE position_id = $2",
                    _mark_status, position_id
                )
                logger.warning(
                    "T1 mark guard: %s for position %s — unrealized_pnl NOT written (%s)",
                    _mark_status, position_id, _mark_reason)
        result["mark_status"] = _mark_status

    # BUG 3: If entry_price or quantity changed on an OPEN position, adjust cash for the cost_basis delta
    cash_ok = None
    # R-IV.453/454: A RECORD CORRECTION IS NOT A FILL. This block used to recompute cost_basis
    # and ADJUST THE ACCOUNT'S CASH whenever an edit touched entry_price or quantity, so
    # correcting a mistyped quantity moved money in the book that never moved at the broker.
    # Measured 2026-09-18: correcting NVDA 415's quantity from 2 to 3 debited ROBINHOOD cash by
    # 16.00 and rewrote the recorded basis 32.00 to 48.00, neither of which the edit asked for.
    # Cash moves belong to fills (add-lot, reduce, close); an edit writes exactly what it names.

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
            dumps_jsonb(options_metrics) if options_metrics else None,
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

    # R-IV.447(b): an exit that already happened keeps its own date. A close recorded weeks
    # later used to read as today's, and the date is what every later reconciliation joins on.
    # Bounded on both sides: a future exit has not happened, and an exit before the position
    # existed is a typo rather than a correction.
    if req.exit_date:
        # R-IV.464(a): a bare date is the principal's day, 00:00 in Denver -- not 00:00 UTC,
        # which rendered a close as the day before on every surface he reads.
        now = _when(req.exit_date, "exit_date")

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
                await name_actor(conn, req.actor or "legacy-ui", req.reason or None)  # R-IV.463(b)
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
                total_qty = float(pos["quantity"] or 0)

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

                # R-IV.447(b): the caller's figure is CHECKED, never stored in place of this
                # one. Two methods that disagree produce two defensible numbers, and the one
                # computed elsewhere is the one nothing here can re-derive — so the write is
                # refused with both named rather than silently preferring either. The danger
                # this guards is specific and measured: a figure from the wrong walk can land
                # 16x too large and still look reasonable on the screen.
                if req.expected_realized is not None:
                    delta = abs(realized_pnl - float(req.expected_realized))
                    if delta > abs(float(req.realized_tolerance)):
                        raise HTTPException(
                            status_code=409,
                            detail=(f"realized disagreement: this row's basis implies "
                                    f"{realized_pnl:+.2f} (entry {entry_price} x {close_qty}), "
                                    f"the caller expected {float(req.expected_realized):+.2f} — "
                                    f"a difference of {delta:.2f}. Nothing was written. Settle "
                                    f"which basis is right before closing the row."))

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

                # R-IV.566(c): THE CLOSE WRITES ITS DISPOSAL LOT, partial or full.
                #
                # Without it the open remainder never falls: 308 closures in this
                # book have lots that still sum to a positive quantity, which is how
                # $88,016.87 of phantom risk came to be published (R-IV.548(b)). The
                # status filter stops that being read as risk; the disposal is what
                # makes the remainder true.
                #
                # It also gives R-IV.517(e) its close date -- the fill_time of the
                # disposal that takes the remainder to zero -- on rows created from
                # here on, rather than leaving it derivable for 24 closures of 432.
                #
                # Negative qty, because a disposal is a movement out. Only where the
                # position already carries lots: writing a disposal against a row
                # with no acquisitions would make the remainder negative, and the
                # legs constraint would refuse the whole close.
                _has_lots = await conn.fetchval(
                    "SELECT 1 FROM position_lots WHERE position_id = $1 LIMIT 1",
                    position_id)
                if _has_lots and close_qty:
                    from models.position_lots import (PRINCIPAL_REPORTED,
                                                      principal_entry_source)

                    try:
                        await conn.execute(
                            """INSERT INTO position_lots
                                   (position_id, fill_time, qty, price, fees, source,
                                    provenance)
                               VALUES ($1, $2, $3, $4, 0, $5, $6)""",
                            position_id, now, -abs(float(close_qty)),
                            abs(float(req.exit_price or 0)),
                            principal_entry_source(datetime.now(timezone.utc)),
                            PRINCIPAL_REPORTED)
                    except Exception as exc:  # noqa: BLE001
                        logger.error("position %s: disposal lot could not be written "
                                     "(%s)", position_id, type(exc).__name__)
                        raise

                if not is_partial:
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
                        close_cash_ok = await _adjust_account_cash_with_conn(
                            conn, pos.get("account", "ROBINHOOD"), cash_delta,
                            source_ref=pos.get("position_id"),
                            description="closed position")
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
async def delete_position(position_id: str, _=Depends(require_api_key),
                          actor: Optional[str] = Query(None),     # R-IV.463(b)
                          reason: Optional[str] = Query(None)):
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
            cash_ok = await _adjust_account_cash(
                pool, pos.get("account", "ROBINHOOD"), cash_delta,
                source_ref=pos.get("position_id"),
                description="position removed")
        except Exception as e:
            logger.error("Cash reversal failed on delete: %s", e)
            cash_ok = False

    async with pool.acquire() as conn, conn.transaction():
        await name_actor(conn, actor or "legacy-ui", reason or None)  # R-IV.463(b)
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
                # R-IV.464(a): one convention. An unreadable date is refused, not replaced with
                # today -- a row stamped today for a close that happened months ago is the
                # defect R-IV.447(b) closed on the close path.
                exit_date_val = (_when(item.exit_date, "exit_date") if item.exit_date
                                 else datetime.now(timezone.utc))

            async with pool.acquire() as conn, conn.transaction():
                await name_actor(conn, req.actor or "legacy-ui", req.reason or None)  # R-IV.463(b)
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
                    dumps_jsonb(item.legs) if item.legs else None,
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
                    await _adjust_account_cash(
                        pool, "ROBINHOOD", cash_delta, source_ref=position_id,
                        description="bulk import")
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
                from services.cash_ledger import stored_cash_is_retired

                if await stored_cash_is_retired(conn, row["account_name"]):
                    return {"status": "not_applied", "account": row["account_name"],
                            "old_cash": old_cash, "drift": drift,
                            "reason": "this account is anchored, so its stored cash "
                                      "total is read-only history (R-IV.551(b)). "
                                      "Re-anchor through POST /api/portfolio/"
                                      "cash-reanchor, which reports the difference."}
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
                # D1 allowlist. The mark path may write mark fields only; a realized
                # field arriving here would mean the reconcile route had started
                # closing positions as a side effect.
                assert_columns_allowed(updates.keys(), WriteScope.MARK_JOB)
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
                async with pool.acquire() as conn, conn.transaction():
                    await name_actor(conn, req.actor or "legacy-ui", req.reason or None)  # R-IV.463(b)
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

            async with pool.acquire() as conn, conn.transaction():
                await name_actor(conn, req.actor or "legacy-ui", req.reason or None)  # R-IV.463(b)
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

    # R-IV.458(a)/460(b): legs are read from the table they live in, once, for every open row.
    legs_by_position: Dict[str, List[Dict[str, Any]]] = {}
    try:
        async with pool.acquire() as conn:
            leg_rows = await conn.fetch(
                "SELECT position_id, leg_seq, option_type, side, strike, expiry, qty, price "
                "FROM position_legs WHERE position_id = ANY($1::text[]) "
                "ORDER BY position_id, leg_seq",
                [r["position_id"] for r in rows])
        for lr in leg_rows:
            legs_by_position.setdefault(lr["position_id"], []).append(dict(lr))
    except Exception as e:
        logger.warning("position_legs read failed; legs positions will read UNAVAILABLE: %s", e)
        legs_by_position = None

    # Cache chain snapshots per ticker to avoid duplicate API calls
    for row in rows:
        ticker = row["ticker"]
        structure = (row.get("structure") or "").lower()
        at = (row.get("asset_type") or "").upper()
        entry_price = float(row["entry_price"]) if row["entry_price"] else None
        quantity = float(row["quantity"]) if row["quantity"] is not None else 0.0
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
        refused = None          # a reading that is not a price, and why (R-IV.462(d))
        unpriced = None         # the vendor answered, and a leg has no mark (R-IV.463(a))

        # ── R-IV.458(a)/460(b): A POSITION WITH LEGS IS MARKED FROM ITS LEGS ─────────────
        # Any structure name, no allowlist. It NEVER falls through to the spread or single-leg
        # paths below: those choose their method from the name, and a name-chosen method is
        # how a three-leg butterfly came to be priced as its 100P alone.
        table_legs = (legs_by_position or {}).get(row["position_id"])
        if table_legs or legs_by_position is None:
            if legs_by_position is None:
                outcome = {"ok": False, "reason": "position_legs could not be read this cycle"}
            elif not (use_options_pricing and get_multi_leg_value is not None):
                outcome = {"ok": False, "reason": "no options pricer configured"}
            else:
                # R-IV.463(a): a mark takes a two-sided quote or a trade this session, nothing
                # older; chains and greeks keep the wider fallback.
                outcome = await mark_from_legs(ticker, table_legs, quantity, structure,
                                               functools.partial(get_multi_leg_value,
                                                                 for_mark=True))
            orientation, oriented_by = entry_orientation(table_legs or [],
                                                         row.get("entry_side"))
            if outcome.get("ok") and orientation is None:
                outcome = {"ok": False, "reason": (
                    "which way this position was entered is not recorded -- no leg prices and "
                    "no entry side -- and its legs can be worth either sign, so a mark cannot "
                    "say whether it is value held or a cost to close")}
            if outcome.get("ok") and oriented_by == "payoff":
                # R-IV.394 (T1) reaches the mark job (R-IV.462(d)). Its floor -- at or below zero
                # is not a price -- holds for a set whose value cannot change sign. A set that
                # CAN has the payoff range as floor and ceiling (checked in mark_from_legs):
                # T1's floor would refuse the very sign R-IV.463(c) keeps.
                _verdict, _why = evaluate_mark(orientation * float(outcome["net_mark"]),
                                               entry_price)
                if not mark_is_writable(_verdict):
                    outcome = {"ok": False, "reason": f"T1 mark guard (R-IV.394): {_why}"}
            async with pool.acquire() as conn, conn.transaction():
                await name_actor(conn, MARK_TO_MARKET)                       # R-IV.462(b)
                if outcome.get("ok"):
                    # R-IV.463(c): the SIGNED net in the entry's orientation -- the value held
                    # for a debit, the cost to close for a credit. Never folded by abs(): a set
                    # that has crossed zero reads negative, and that sign is the information.
                    mark = orientation * float(outcome["net_mark"])
                    unreal = _compute_unrealized_pnl(entry_price, mark, quantity, structure,
                                                     direction=(row.get("direction") or ""),
                                                     orientation=orientation)
                    await conn.execute("""
                        UPDATE unified_positions SET
                            current_price = $1, unrealized_pnl = $2,
                            mark_status = 'OK', mark_reason = $3,
                            price_updated_at = NOW(), mark_checked_at = NOW(),
                            updated_at = NOW()
                        WHERE position_id = $4
                    """, mark, unreal, outcome["reason"], row["position_id"])
                    updated += 1
                elif prior_is_good(row.get("mark_reason"), table_legs, structure, expiry,
                                   long_strike, short_strike, quantity,
                                   row.get("current_price")):
                    # The mark guard's rule: a failed cycle writes nothing over a GOOD value.
                    # This prior is good -- legs produced it, or the two-strike path priced
                    # exactly the contracts the legs hold -- so it stands, stamped.
                    # It says why it was not refreshed (R-IV.462): a STALE mark with no cause
                    # cannot be told from one whose legs were refused as impossible.
                    await conn.execute(
                        "UPDATE unified_positions SET mark_checked_at = NOW(), "
                        "mark_status = 'STALE', mark_reason = $2 WHERE position_id = $1",
                        row["position_id"],
                        stale_reason(row.get("mark_reason"), outcome.get("reason")))
                else:
                    # A prior mark from a name-chosen method on any wider leg set priced a
                    # DIFFERENT structure (or is negative, which nothing it priced can be).
                    # Keeping it would keep the invented number, so it is cleared and the row
                    # says why it cannot be priced. NULL is not zero: it claims nothing.
                    await conn.execute("""
                        UPDATE unified_positions SET
                            current_price = NULL, unrealized_pnl = NULL,
                            mark_status = 'UNAVAILABLE', mark_reason = $1,
                            mark_checked_at = NOW(), updated_at = NOW()
                        WHERE position_id = $2
                    """, outcome.get("reason"), row["position_id"])
            continue

        # --- Multi-leg path: iron condors, straddles, etc. via legs JSONB ---
        # (Legacy: rows with NO legs in position_legs. The allowlist below no longer decides
        # anything for a position whose legs are in the table.)
        legs_data = row.get("legs")

        # Auto-infer legs from notes if missing for multi-leg structures
        if not legs_data and structure in MULTI_LEG_STRUCTURES:
            inferred = _infer_legs_from_notes(row.get("notes") or "")
            if inferred:
                legs_data = inferred
                # Persist inferred legs back to DB so future MTM runs don't re-parse
                try:
                    legs_json_str = dumps_jsonb(inferred)
                    async with pool.acquire() as conn, conn.transaction():
                        await name_actor(conn, MARK_TO_MARKET, "legs inferred from notes")
                        await conn.execute(
                            "UPDATE unified_positions SET legs = $1 WHERE position_id = $2",
                            legs_json_str, row["position_id"],
                        )
                    logger.info("Auto-populated legs for %s from notes", row["position_id"])
                except Exception as e:
                    logger.warning("Failed to persist inferred legs for %s: %s", row["position_id"], e)

        jsonb_attempted = False
        if use_options_pricing and expiry and legs_data:
            try:
                if isinstance(legs_data, str):
                    legs_data = json.loads(legs_data)
                if isinstance(legs_data, list) and len(legs_data) >= 2:
                    jsonb_attempted = True
                    result = await get_multi_leg_value(ticker, legs_data, str(expiry),
                                                       for_mark=True)
                    if result and result.get("unpriced"):
                        unpriced = "; ".join(result["unpriced"])
                    if result and result.get("net_mark") is not None:
                        # R-IV.463(c): no abs(). These legacy legs carry no entry side, so the
                        # orientation is the name's -- the rule the P&L formula itself uses.
                        current_price = (_orientation_by_name(structure, row.get("direction") or "")
                                         * float(result["net_mark"]))
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
        # Legs that were priced and failed never fall through to a two-strike or single-leg
        # method: those price a different structure (the R-IV.458 defect, on the legacy path).
        if current_price is None and jsonb_attempted:
            continue

        # --- Polygon path: real spread-level pricing ---
        if current_price is None and use_options_pricing and expiry and long_strike:
            try:
                if short_strike and ("spread" in structure or "credit" in structure or "debit" in structure):
                    # Spread position — get both legs
                    result = await get_spread_value(
                        ticker, long_strike, short_strike, str(expiry), structure,
                        for_mark=True,                                  # R-IV.463(a)
                    )
                    if result and result.get("unpriced"):
                        unpriced = "; ".join(result["unpriced"])
                    if result and result.get("spread_value") is not None:
                        current_price = result["spread_value"]
                        # R-IV.462(d): a vertical is worth between zero and its width. T1
                        # refuses the floor; the ceiling is refused here. Either way it is two
                        # leg quotes from different moments, not a price.
                        _width = abs(long_strike - short_strike)
                        if current_price > _width + 1e-6:
                            refused = (f"quotes price this vertical at {current_price:.4f}, "
                                       f"above its width {_width:g}; a leg's quote is from "
                                       f"another moment")
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
                        ticker, long_strike, str(expiry), opt_type,
                        for_mark=True,                                  # R-IV.463(a)
                    )
                    if result and result.get("unpriced"):
                        unpriced = "; ".join(result["unpriced"])
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
                    # R-IV.463(e): the vendor hands over a float32 -- 45.71 arrives as
                    # 45.709999084472656 -- and a share price is quoted to at most 4 decimals,
                    # so rounding there recovers the price instead of storing its noise.
                    current_price = round(float(info.last_price), 4)
                    unrealized = _compute_unrealized_pnl(
                        entry_price, current_price, quantity, structure,
                        direction=row.get("direction", "")
                    )
            except Exception:
                pass

        if current_price is not None and unrealized is not None:
            # R-IV.394 (T1) reaches the mark job (R-IV.462(d)). It was wired only into the PATCH
            # recompute, so the writer behind nearly every mark stored negative values on debit
            # spreads for weeks. A mark it rejects writes NOTHING to the price or the P&L: the
            # prior stands, stamped with the reason.
            _verdict, _why = ((MARK_REJECTED, refused) if refused
                              else evaluate_mark(current_price, entry_price))
            async with pool.acquire() as conn, conn.transaction():
                await name_actor(conn, MARK_TO_MARKET)                       # R-IV.462(b)
                if mark_is_writable(_verdict):
                    await conn.execute("""
                        UPDATE unified_positions SET
                            current_price = $1, unrealized_pnl = $2,
                            long_leg_price = $3, short_leg_price = $4,
                            mark_status = 'OK', mark_reason = NULL, mark_checked_at = NOW(),
                            price_updated_at = NOW(), updated_at = NOW()
                        WHERE position_id = $5
                    """, current_price, unrealized, long_leg_price, short_leg_price,
                        row["position_id"])
                    updated += 1
                else:
                    await conn.execute("""
                        UPDATE unified_positions SET
                            mark_status = $1, mark_reason = $2, mark_checked_at = NOW()
                        WHERE position_id = $3
                    """, _verdict, _why, row["position_id"])
                    logger.warning("T1 mark guard (mark job): %s for %s -- nothing written (%s)",
                                   _verdict, row["position_id"], _why)
        elif unpriced:
            # R-IV.463(a): the vendor answered and a leg has no mark -- no two-sided quote and
            # no trade this session. Not an outage, so it is said: the prior stands as STALE
            # (the two-strike path wrote it on these same contracts), with the reason.
            async with pool.acquire() as conn, conn.transaction():
                await name_actor(conn, MARK_TO_MARKET)                       # R-IV.462(b)
                await conn.execute(
                    "UPDATE unified_positions SET mark_status = $1, mark_reason = $2, "
                    "mark_checked_at = NOW() WHERE position_id = $3",
                    "STALE" if row.get("current_price") is not None else "UNAVAILABLE",
                    stale_reason(row.get("mark_reason"), f"no mark: {unpriced}")
                    if row.get("current_price") is not None else f"no mark: {unpriced}",
                    row["position_id"])
        # NOTE: prior versions had an elif that wiped current_price/unrealized_pnl
        # to NULL/0 for OPTION/SPREAD rows whose current cycle failed to price.
        # That branch defended against a historical "stock price written to options
        # row" bug already prevented by the is_equity_position guard above. The wipe
        # caused legitimate prior prices to be erased on every UW 429 rate-limit
        # cycle. Removed 2026-05-14 — outage behavior is now "retain prior price"
        # rather than "wipe to NULL." Staleness is detected via price_updated_at
        # downstream in portfolio_summary, not by clearing the field here.

    result = {"status": "updated", "updated": updated, "source": "uw" if use_options_pricing else "yfinance"}
    if errors:
        result["errors"] = errors
    return result


@router.post("/v2/positions/mark-to-market")
async def mark_to_market(_=Depends(require_api_key)):
    """HTTP wrapper for mark-to-market. Background loop calls run_mark_to_market() directly."""
    return await run_mark_to_market()


# ── FEAT-POSITION-LIFECYCLE Phase 2 ────────────────────────────────────────────
# Three endpoints, one invariant. The audit trigger records every mutation; the
# allowlist refuses the ones a caller may not make. These add lots, manual edits with
# a reason, and cash events — and the cash path deliberately touches no position row.

# R-IV.75(d) ETF-only invariant. An option structure on the Roth is prima facie
# mis-attributed, so it is refused at entry rather than corrected later.
_ETF_ONLY_ACCOUNTS = {"FIDELITY_ROTH"}


def _assert_etf_only(account: Optional[str], asset_type: Optional[str]) -> None:
    acct = (account or "").strip().upper()
    at = (asset_type or "").strip().upper()
    if acct in _ETF_ONLY_ACCOUNTS and at == "OPTION":
        raise HTTPException(
            status_code=400,
            detail=(f"{acct} is an ETF-only account (R-IV.75(d)): option structures are "
                    f"not permitted. An OPTION row on this account is prima facie "
                    f"mis-attributed — check the account before retrying."),
        )


class AddLotRequest(BaseModel):
    """A fill, in the ruled vocabulary (R-IV.310(b) / migration 037).

    `fill_time` and `qty` were `fill_date` and `quantity` until 2026-09-17. The old names are
    NOT accepted as aliases: a stale caller gets a 422 naming the field it sent, which is the
    loud failure this register keeps asking for, where an alias would quietly accept a body
    written against a schema that no longer exists.
    """
    fill_time: str
    qty: float
    price: Optional[float] = None
    fees: float = 0.0
    source: str = "MANUAL"
    broker_ref: Optional[str] = None
    reason: Optional[str] = None
    actor: Optional[str] = None


@router.post("/v2/positions/{position_id}/lots")
async def add_position_lot(position_id: str, req: AddLotRequest,
                           _=Depends(require_api_key)):
    """Add a fill to an existing position and DERIVE its figures from the lot set.

    Quantity, entry price and cost basis are computed from the lots on every add, so the
    position row stops being a hand-maintained aggregate that can drift from the fills behind
    it. Never writes a mark or a realized field — adding to a position is not a valuation
    event and not a close.

    Three things this route now refuses to do quietly:
      * fold fees into the per-unit price (the basis is GROSS; fees are reported beside it),
      * drop the 100x contract multiplier on an option row,
      * store a cost basis for a lot set that contains an unpriced lot.
    """
    if req.qty == 0:
        raise HTTPException(status_code=400, detail="qty must be non-zero")
    if req.source not in ("MANUAL", "IMPORT"):
        raise HTTPException(status_code=400,
                            detail="source must be MANUAL or IMPORT; LEGACY-SINGLE-LOT is "
                                   "reserved for the Phase-1 backfill")
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        pos = await conn.fetchrow(
            "SELECT position_id, ticker, structure, asset_type, account, status "
            "FROM unified_positions WHERE position_id = $1", position_id)
        if not pos:
            raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
        if pos["status"] != "OPEN":
            raise HTTPException(
                status_code=400,
                detail=f"Position {position_id} is {pos['status']}, not OPEN — a lot cannot "
                       f"be added to a position that is already closed or expired.")
        _assert_etf_only(pos["account"], pos["asset_type"])

        async with conn.transaction():
            await conn.execute("SELECT set_config('app.actor', $1, true)",
                               (req.actor or "lifecycle-ui"))
            await conn.execute(
                "SELECT set_config('app.reason', $1, true)",
                (req.reason or f"add lot {req.qty} @ {req.price} on {req.fill_time}"))
            # R-IV.444(c): the same broker reference twice is the same fill twice. Refused with
            # the lot it already is, so the caller learns WHICH record they are duplicating and
            # not merely that they are. The database carries the same rule as a unique index —
            # this check exists to make the refusal legible, not to be the only one.
            if req.broker_ref:
                dup = await conn.fetchrow(
                    "SELECT id, position_id FROM position_lots WHERE broker_ref = $1",
                    req.broker_ref)
                if dup:
                    raise HTTPException(
                        status_code=409,
                        detail=(f"broker_ref {req.broker_ref} is already lot {dup['id']} on "
                                f"position {dup['position_id']} — a confirmation number is the "
                                f"broker's own identity for one fill."))
            # Provenance is derived from HOW THE LOT ARRIVED and is never defaulted by the
            # database: MANUAL is PRINCIPAL_REPORTED, IMPORT is IMPORTED, an unpriced lot is
            # UNKNOWN. BROKER_VERIFIED is unreachable from here by design — it requires a
            # broker record to have been matched, which no path in this build performs.
            await conn.execute(
                """INSERT INTO position_lots
                       (position_id, fill_time, qty, price, fees, source, provenance,
                        broker_ref)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                position_id, _when(req.fill_time, "fill_time"),      # R-IV.464(a)
                req.qty, req.price, req.fees, req.source,
                provenance_for_lot(req.source, req.price), req.broker_ref)

            lots = await conn.fetch(
                "SELECT qty, price, fees FROM position_lots WHERE position_id = $1",
                position_id)
            agg = derive_aggregate([dict(l) for l in lots], pos["asset_type"])

            # R-IV.458(b): the book matches the broker including fractions. quantity is NUMERIC,
            # so the lots' exact sum is stored -- the refusal that stood here protected an
            # INTEGER column from losing shares, and the column no longer loses them.
            stored_qty = agg["qty"]

            # The aggregate is WRITTEN, not merged. An add changes the quantity, so a basis
            # kept from before the add describes a position that no longer exists. When the lot
            # set contains an unpriced lot the basis is genuinely unknown and is stored as
            # NULL — representable, rather than extrapolated over the priced lots at a number
            # nothing measured.
            await conn.execute(
                """UPDATE unified_positions
                   SET quantity = $1, entry_price = $2, cost_basis = $3,
                       basis_incomplete_reason = $4, updated_at = NOW()
                   WHERE position_id = $5""",
                stored_qty, agg["entry_price"], agg["cost_basis"],
                (f"R-IV.456(a): {agg['unknown_reason']}" if agg["unknown_reason"] else None),
                position_id)

        rows = await conn.fetch(
            "SELECT id, fill_time, qty, price, fees, source, provenance, broker_ref "
            "FROM position_lots WHERE position_id = $1 ORDER BY fill_time, id", position_id)

    return {"status": "lot_added", "position_id": position_id,
            "quantity": stored_qty, "entry_price": agg["entry_price"],
            "cost_basis": agg["cost_basis"], "basis_known": agg["basis_known"],
            "basis_unknown_reason": agg["unknown_reason"], "fees_total": agg["fees"],
            "multiplier": agg["multiplier"], "unpriced_lots": agg["unpriced_lots"],
            "lots": [dict(r) for r in rows]}


@router.get("/v2/positions/lots/coverage", dependencies=[Depends(require_api_key)])
async def get_lots_coverage(limit: int = Query(50, ge=0, le=500)):
    """How much of the book actually has lots behind it — the lots invariant, read live.

    Two claims are checked per position: that it has at least one lot, and that its lots sum to
    its stored quantity. Both are FALSE on part of the book today, and this surface exists so
    that stays visible rather than being asserted away. It is not a display that has never been
    seen to move: the counts are non-zero on the live book, and they move when a lot is added
    or removed.

    Every population is counted and named — a position with no stored quantity cannot be
    checked against its lots and is its own line, never folded into either answer.
    """
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT p.status,
                      COUNT(*)                                             AS positions,
                      COUNT(*) FILTER (WHERE a.lots > 0)                   AS with_lots,
                      COUNT(*) FILTER (WHERE a.lots = 0)                   AS without_lots,
                      COUNT(*) FILTER (WHERE p.quantity IS NULL)           AS unquantified,
                      COUNT(*) FILTER (WHERE a.lots > 0 AND p.quantity IS NOT NULL
                                         AND a.lot_qty <> p.quantity)      AS qty_mismatch,
                      COUNT(*) FILTER (WHERE a.unpriced > 0)               AS with_unpriced_lot
                 FROM unified_positions p
                 JOIN LATERAL (
                        SELECT COUNT(*) AS lots,
                               COALESCE(SUM(l.qty), 0) AS lot_qty,
                               COUNT(*) FILTER (WHERE l.price IS NULL) AS unpriced
                          FROM position_lots l WHERE l.position_id = p.position_id
                      ) a ON TRUE
                GROUP BY p.status ORDER BY p.status""")
        open_gaps = await conn.fetch(
            """SELECT p.position_id, p.ticker, p.quantity,
                      COALESCE(SUM(l.qty), 0) AS lot_qty, COUNT(l.id) AS lots
                 FROM unified_positions p
                 LEFT JOIN position_lots l ON l.position_id = p.position_id
                WHERE p.status = 'OPEN'
                GROUP BY p.position_id, p.ticker, p.quantity
               HAVING COUNT(l.id) = 0
                   OR (p.quantity IS NOT NULL AND COALESCE(SUM(l.qty), 0) <> p.quantity)
                ORDER BY p.position_id LIMIT $1""", limit)
        prov = await conn.fetch(
            "SELECT provenance, COUNT(*) AS lots, "
            "COUNT(*) FILTER (WHERE broker_ref IS NOT NULL) AS with_broker_ref "
            "FROM position_lots GROUP BY provenance ORDER BY provenance")

    keys = ("positions", "with_lots", "without_lots", "unquantified", "qty_mismatch",
            "with_unpriced_lot")
    by_status = {r["status"]: {k: r[k] for k in keys} for r in rows}
    totals = {k: sum(v[k] for v in by_status.values()) for k in keys}
    return {
        "invariant": "every position has >= 1 lot and SUM(lot qty) == row qty",
        "holds": totals["without_lots"] == 0 and totals["qty_mismatch"] == 0,
        "totals": totals,
        "by_status": by_status,
        "provenance": {r["provenance"]: {"lots": r["lots"],
                                         "with_broker_ref": r["with_broker_ref"]}
                       for r in prov},
        "open_gaps": [dict(r) for r in open_gaps],
        "open_gaps_truncated": len(open_gaps) == limit,
    }


class ReducePositionRequest(BaseModel):
    """A reduction or a close, priced and dated like the fill it is.

    `confirm` defaults to FALSE: the first call is a question. R-IV.444(c) requires the
    realized amount to be SEEN before it is real, and a preview that has to be asked for in a
    special way is a preview nobody runs.
    """
    qty: float
    price: Optional[float] = None
    fill_time: Optional[str] = None
    fees: float = 0.0
    broker_ref: Optional[str] = None
    confirm: bool = False
    reason: Optional[str] = None
    actor: Optional[str] = None


@router.post("/v2/positions/{position_id}/reduce")
async def reduce_position(position_id: str, req: ReducePositionRequest,
                          _=Depends(require_api_key)):
    """Sell part or all of a position, FIFO, showing the realized result before it is real.

    A reduction NEVER edits the lots it consumes. It is its own event — a negative-quantity
    lot — allocated oldest-first against the acquisitions it sells out of, so the ledger still
    answers "what was bought, and when" after the selling is done, and SUM(qty) still equals
    the position.

    With `confirm` false (the default) nothing is written and the plan comes back: which lots
    would be consumed, at what cost, and what the whole thing realizes. With `confirm` true
    the same plan is recomputed inside the transaction and then written — recomputed, because
    a plan shown a minute ago describes a lot set that may have changed since.
    """
    if req.qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be positive — a reduction's "
                                                    "direction is the endpoint, not its sign")
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        pos = await conn.fetchrow(
            "SELECT position_id, ticker, asset_type, account, status "
            "FROM unified_positions WHERE position_id = $1", position_id)
        if not pos:
            raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
        if pos["status"] != "OPEN":
            raise HTTPException(status_code=400,
                                detail=f"Position {position_id} is {pos['status']}, not OPEN")

        lots = await conn.fetch(
            "SELECT id, fill_time, qty, price, fees FROM position_lots "
            "WHERE position_id = $1 ORDER BY fill_time, id", position_id)
        plan = fifo_plan([dict(l) for l in lots], req.qty, req.price, pos["asset_type"],
                         req.fees)

        if not plan["sufficient"]:
            raise HTTPException(
                status_code=400,
                detail=(f"lots hold {plan['available_qty']} and the reduction asks for "
                        f"{plan['requested_qty']} — short by {plan['shortfall']}. The book "
                        f"cannot sell what it has no record of buying."))
        if not req.confirm:
            return {"status": "preview", "position_id": position_id, "written": False,
                    **plan,
                    "note": "nothing was written; send the same body with confirm=true"}

        if req.broker_ref:
            dup = await conn.fetchrow(
                "SELECT id, position_id FROM position_lots WHERE broker_ref = $1",
                req.broker_ref)
            if dup:
                raise HTTPException(
                    status_code=409,
                    detail=(f"broker_ref {req.broker_ref} is already lot {dup['id']} on "
                            f"position {dup['position_id']}"))

        async with conn.transaction():
            await conn.execute("SELECT set_config('app.actor', $1, true)",
                               (req.actor or "lifecycle-ui"))
            await conn.execute("SELECT set_config('app.reason', $1, true)",
                               (req.reason or f"reduce {req.qty} @ {req.price}"))
            # Recomputed under the transaction: the plan the caller saw described the lot set
            # as it was, and a confirmation is not a licence to write yesterday's arithmetic.
            fresh = await conn.fetch(
                "SELECT id, fill_time, qty, price, fees FROM position_lots "
                "WHERE position_id = $1 ORDER BY fill_time, id FOR UPDATE", position_id)
            plan = fifo_plan([dict(l) for l in fresh], req.qty, req.price, pos["asset_type"],
                             req.fees)
            if not plan["sufficient"]:
                raise HTTPException(
                    status_code=409,
                    detail=("the lot set changed between the preview and the confirmation; "
                            "re-run the preview"))
            disposal_id = await conn.fetchval(
                """INSERT INTO position_lots
                       (position_id, fill_time, qty, price, fees, source, provenance,
                        broker_ref)
                   VALUES ($1, COALESCE($2, NOW()), $3, $4, $5, 'MANUAL', $6, $7)
                   RETURNING id""",
                position_id, optional_instant(req.fill_time, "fill_time"),   # R-IV.464(a)
                -abs(req.qty), req.price, req.fees,
                provenance_for_lot("MANUAL", req.price), req.broker_ref)
            for a in plan["allocations"]:
                await conn.execute(
                    """INSERT INTO position_lot_closures
                           (position_id, disposal_lot_id, acquired_lot_id, qty, cost_per_unit,
                            proceeds_per_unit, realized, multiplier)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                    position_id, disposal_id, a["lot_id"], a["qty"], a["cost_per_unit"],
                    a["proceeds_per_unit"], a["realized"], plan["multiplier"])

            remaining = await conn.fetch(
                "SELECT qty, price, fees FROM position_lots WHERE position_id = $1",
                position_id)
            agg = derive_aggregate([dict(r) for r in remaining], pos["asset_type"])
            stored_qty = agg["qty"]   # R-IV.458(b): exact, fractions included
            # The position's own realized field is NOT written here. Realized belongs to the
            # close path and its allocations live in position_lot_closures; writing it from two
            # places is how a figure comes to have two owners and no author.
            await conn.execute(
                """UPDATE unified_positions
                   SET quantity = $1, entry_price = $2, cost_basis = $3,
                       basis_incomplete_reason = $4, updated_at = NOW()
                   WHERE position_id = $5""",
                stored_qty, agg["entry_price"], agg["cost_basis"],
                (f"R-IV.456(a): {agg['unknown_reason']}" if agg["unknown_reason"] else None),
                position_id)

    return {"status": "reduced", "position_id": position_id, "written": True,
            "disposal_lot_id": disposal_id, "quantity_after": stored_qty,
            "entry_price_after": agg["entry_price"], "cost_basis_after": agg["cost_basis"],
            "basis_known": agg["basis_known"], **plan}


class VerifyRequest(BaseModel):
    """A match against a broker record, with the evidence that makes it re-checkable."""
    broker_ref: str
    verified_event: str
    actor: Optional[str] = None
    reason: Optional[str] = None


async def _verify_row(table: str, position_id: str, row_id: int, req: VerifyRequest,
                      key_column: str = "id"):
    """Stamp one lot or leg BROKER_VERIFIED. The only path to that value anywhere.

    A verification is a TRANSITION, not a field. It records what was matched and when the match
    was made, and the database refuses the value without both — `verified_at` is the time of
    the MATCH, never the fill's, which would make a row look as though it was confirmed on the
    day it traded.
    """
    if not req.broker_ref.strip() or not req.verified_event.strip():
        raise HTTPException(
            status_code=400,
            detail="broker_ref and verified_event are both required — a verification naming "
                   "neither what was matched nor its reference cannot be re-checked, which is "
                   "the condition BROKER_VERIFIED exists to escape")
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT r.*, p.ticker FROM {table} r "
            f"JOIN unified_positions p ON p.position_id = r.position_id "
            f"WHERE r.position_id = $1 AND r.{key_column} = $2", position_id, row_id)
        if not row:
            raise HTTPException(status_code=404,
                                detail=f"{table} {row_id} not found on {position_id}")
        held = await conn.fetchval(
            f"SELECT position_id FROM {table} WHERE broker_ref = $1 AND {key_column} <> $2",
            req.broker_ref, row_id)
        if held:
            raise HTTPException(status_code=409,
                                detail=f"broker_ref {req.broker_ref} is already on {held}")
        async with conn.transaction():
            await conn.execute(
                f"""UPDATE {table}
                       SET provenance = 'BROKER_VERIFIED', broker_ref = $1,
                           verified_event = $2, verified_at = NOW()
                     WHERE position_id = $3 AND {key_column} = $4""",
                req.broker_ref, req.verified_event, position_id, row_id)
            await _audit_leg(conn, position_id, row["ticker"], "VERIFY",
                             f"{table}:{row_id}:provenance",
                             {"provenance": row["provenance"], "broker_ref": row["broker_ref"]},
                             {"provenance": "BROKER_VERIFIED", "broker_ref": req.broker_ref,
                              "verified_event": req.verified_event},
                             req.actor, req.reason or req.verified_event)
    return {"status": "verified", "position_id": position_id, "table": table, "id": row_id,
            "provenance": "BROKER_VERIFIED", "broker_ref": req.broker_ref,
            "verified_event": req.verified_event}


class EntryLeg(BaseModel):
    option_type: str               # CALL | PUT
    side: str                      # LONG | SHORT
    strike: float
    expiry: str
    ratio: float = 1               # contracts per structure
    price: Optional[float] = None  # this leg's fill, when known


class LegsPreviewRequest(BaseModel):
    legs: List[EntryLeg]
    quantity: float = 1            # structures


class WithLegsRequest(BaseModel):
    """A position entered from its legs — any number of them (R-IV.460(c))."""
    ticker: str
    account: str
    legs: List[EntryLeg]
    quantity: float = 1                  # structures
    # Per structure, when the legs are not priced one by one. SIGNED (R-IV.463(c)): positive =
    # paid (a debit), negative = received (a credit). The sign is what a ratio or a risk reversal
    # loses when only the magnitude is kept.
    net_price: Optional[float] = None
    structure: Optional[str] = None      # a label; the legs are what is held regardless
    direction: Optional[str] = None
    entry_date: Optional[str] = None
    notes: Optional[str] = None
    broker_ref: Optional[str] = None
    reason: Optional[str] = None
    actor: Optional[str] = None
    # R-IV.463(e): MANUAL (entered by hand) or IMPORT (read from a broker export or statement).
    source: str = "MANUAL"


def _validated_legs(legs: List[EntryLeg], quantity: float) -> List[Dict[str, Any]]:
    if not legs:
        raise HTTPException(status_code=400, detail="at least one leg is required")
    if quantity is None or quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity (structures) must be positive")
    out = []
    for i, leg in enumerate(legs, 1):
        ot, sd = _leg_values(leg.option_type, leg.side)
        if leg.strike is None or leg.strike <= 0:
            raise HTTPException(status_code=400, detail=f"leg {i}: strike must be positive")
        if leg.ratio is None or leg.ratio <= 0:
            raise HTTPException(status_code=400, detail=f"leg {i}: ratio must be positive")
        try:
            exp = date.fromisoformat(str(leg.expiry)[:10])
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail=f"leg {i}: expiry must be a date")
        out.append({"option_type": ot, "side": sd, "strike": float(leg.strike),
                    "expiry": exp, "qty": float(leg.ratio) * float(quantity),
                    "ratio": float(leg.ratio), "price": leg.price})
    return out


@router.post("/v2/positions/legs/preview", dependencies=[Depends(require_api_key)])
async def preview_legs(req: LegsPreviewRequest):
    """What a set of legs IS and what it can make or lose — computed before anything is saved.

    Any number of legs (R-IV.460(c) lifted the old ceiling of four). Names the structure where it
    recognizes one and says CUSTOM where it does not; a CUSTOM set is enterable all the same.
    """
    legs = _validated_legs(req.legs, req.quantity)
    analysis = analyze(legs)
    scale = float(req.quantity)
    for k in ("max_profit", "max_loss"):
        if isinstance(analysis.get(k), (int, float)):
            analysis[f"{k}_position"] = round(analysis[k] * scale, 2)
    return {"structure": recognize(legs), "legs": len(legs), "quantity": req.quantity,
            "analysis": analysis, "display_strikes": display_strikes(legs)}


@router.post("/v2/positions/with-legs")
async def create_position_with_legs(req: WithLegsRequest, _=Depends(require_api_key)):
    """Enter a position from its legs, atomically: the row, every leg, and its first lot.

    The legs are the source. The two strike columns are written as a DERIVED summary for display
    (R-IV.460(d)); nothing prices or marks from them for a position that has legs. The entry is
    the legs' net when every leg is priced, else `net_price`, else unknown — and an unknown entry
    marks the row basis-incomplete rather than inventing one.
    """
    account = canonical_account(req.account)
    _assert_etf_only(account, "OPTION")
    leg_source = _leg_source(req.source)            # R-IV.463(e)
    row_source = "MANUAL" if leg_source == "MANUAL" else "BROKER_EXPORT"
    legs = _validated_legs(req.legs, req.quantity)
    analysis = analyze(legs)
    recognized = recognize(legs)
    structure = (req.structure or recognized).strip().lower()
    net = analysis.get("net_premium")          # signed: + paid (debit), - received (credit)
    if net is None and req.net_price is not None:
        net = float(req.net_price)             # signed the same way
    qty = float(req.quantity)
    # R-IV.463(c): the entry is kept as a magnitude WITH its side beside it. A set that cannot
    # change sign has its side fixed by its payoff, and a stated net that contradicts it is a
    # typo in the sign -- refused, not stored.
    by_payoff, how = entry_orientation(legs)
    stated = None if not net else (1 if net > 0 else -1)
    if how == "payoff" and stated is not None and stated != by_payoff:
        raise HTTPException(status_code=400, detail=(
            f"these legs can only be entered for a {'debit' if by_payoff > 0 else 'credit'} "
            f"(their payoff is never {'negative' if by_payoff > 0 else 'positive'}); the net "
            f"{'implied by the leg prices' if analysis.get('net_premium') is not None else 'given'}"
            f" is a {'debit' if stated > 0 else 'credit'} -- check the prices or the sign"))
    side = stated if stated is not None else (by_payoff if how == "payoff" else None)
    entry_side = {1: "DEBIT", -1: "CREDIT"}.get(side)
    entry = abs(net) if net is not None else None
    basis = round(entry * qty * 100, 2) if entry is not None else None
    max_loss = analysis.get("max_loss")
    max_profit = analysis.get("max_profit")
    if isinstance(max_loss, (int, float)):
        max_loss = round(max_loss * qty, 2)
    if isinstance(max_profit, (int, float)):
        max_profit = round(max_profit * qty, 2)
    shown = display_strikes(legs)
    expiries = sorted({l["expiry"] for l in legs})
    now = datetime.now(timezone.utc)
    pid = f"POS_{req.ticker.upper()}_{now.strftime('%Y%m%d_%H%M%S')}_L{len(legs)}"
    incomplete = (None if entry is not None else
                  "R-IV.460(c): entered with no leg prices and no net price; basis unknown")

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.actor', $1, true)",
                               (req.actor or "lifecycle-ui"))
            await conn.execute("SELECT set_config('app.reason', $1, true)",
                               (req.reason or f"entered with {len(legs)} leg(s) as {structure}"))
            await conn.execute("""
                INSERT INTO unified_positions
                    (position_id, ticker, asset_type, structure, direction, quantity,
                     entry_price, cost_basis, max_loss, max_profit, breakeven, entry_date,
                     expiry, long_strike, short_strike, account, source, status, provenance,
                     broker_ref, basis_incomplete_reason, notes, entry_side, created_at,
                     updated_at)
                VALUES ($1, $2, 'OPTION', $3, $4, $5, $6, $7, $8, $9, $10,
                        COALESCE($11, NOW()), $12, $13, $14, $15, $20, 'OPEN',
                        $21, $16, $17, $18, $19, NOW(), NOW())""",
                pid, req.ticker.upper(), structure, (req.direction or "").upper() or None,
                qty, entry, basis,
                max_loss if isinstance(max_loss, (int, float)) else None,
                max_profit if isinstance(max_profit, (int, float)) else None,
                analysis.get("breakevens"),
                optional_instant(req.entry_date, "entry_date"),      # R-IV.464(a)
                expiries[0],
                shown["long_strike"], shown["short_strike"], account, req.broker_ref,
                incomplete, req.notes, entry_side, row_source,
                provenance_for_parent(row_source, entry))
            for seq, leg in enumerate(legs, 1):
                await conn.execute("""
                    INSERT INTO position_legs
                        (position_id, leg_seq, option_type, side, strike, expiry, qty, price,
                         provenance, migrated_from)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'entered-with-legs')""",
                    pid, seq, leg["option_type"], leg["side"], leg["strike"], leg["expiry"],
                    leg["qty"], leg["price"], provenance_for_lot(leg_source, leg["price"]))
            await conn.execute("""
                INSERT INTO position_lots
                    (position_id, fill_time, qty, price, fees, source, provenance, broker_ref)
                VALUES ($1, COALESCE($2, NOW()), $3, $4, 0, $7, $5, $6)""",
                pid, optional_instant(req.entry_date, "entry_date"), qty, entry,
                provenance_for_lot(leg_source, entry),
                req.broker_ref, leg_source)
            await conn.execute("""
                INSERT INTO position_legs_migration
                    (position_id, outcome, detail, legs_written)
                VALUES ($1, 'ENTERED_WITH_LEGS', $2, $3)""",
                pid, f"entered from {len(legs)} leg(s); recognized as {recognized}", len(legs))

    return {"status": "created", "position_id": pid, "structure": structure,
            "recognized_as": recognized, "legs": len(legs), "quantity": qty,
            "entry_price": entry, "entry_side": entry_side, "cost_basis": basis,
            "analysis": analysis,
            "display_strikes": shown, "basis_incomplete_reason": incomplete}


class CorrectRealizedRequest(BaseModel):
    """An adjudicated correction to an ENDED row's recorded figures (R-IV.457(d), R-IV.458).

    Every figure is optional; at least one is required. quantity, entry_price and cost_basis
    were added for R-IV.458(b)(c): GUSH 358's fractional share and TSLA 352's gross entry had no
    path, because the PATCH refuses lot-derived fields and the close path refuses a closed row.
    """
    realized_pnl: Optional[float] = None
    exit_price: Optional[float] = None
    quantity: Optional[float] = None
    entry_price: Optional[float] = None
    cost_basis: Optional[float] = None
    # R-IV.463(e): the day the exit happened. A date alone is that day in Denver, the
    # principal's day -- the convention of the rows already corrected by hand.
    exit_date: Optional[str] = None
    # max_loss is NOT an input: it derives from the corrected row and the path writes it.
    evidence: str                  # the lines that support the verdict, shown beside it (#23)
    reason: str
    ruling: str
    actor: Optional[str] = None


@router.post("/v2/positions/{position_id}/correct-realized")
async def correct_realized(position_id: str, req: CorrectRealizedRequest,
                           _=Depends(require_api_key)):
    """Correct the realized result of a row that has already ended — with its evidence.

    There was no path for this at all: the PATCH refuses realized fields (they belong to the
    close path) and the close path refuses a row that is not OPEN. So an adjudicated correction
    to a closed trade had nowhere to go but raw SQL.

    CONVENTIONS #23: an adjudication shows its evidence lines beside its verdict. `evidence` is
    REQUIRED and is written onto the row with the verdict and the value it replaces, so a later
    reader sees the lines that support the number rather than a number alone. The prior figure is
    kept on the row too — a correction that erases what it corrected cannot be checked.
    """
    for name in ("evidence", "reason", "ruling"):
        if not str(getattr(req, name) or "").strip():
            raise HTTPException(
                status_code=400,
                detail=f"{name} is required — a corrected result with no {name} beside it is "
                       f"a verdict alone, which is what conventions #23 exists to stop")
    fields = {f: getattr(req, f) for f in
              ("realized_pnl", "exit_price", "quantity", "entry_price", "cost_basis", "exit_date")
              if getattr(req, f) is not None}
    if "exit_date" in fields:
        fields["exit_date"] = _when(fields["exit_date"], "exit_date")
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT position_id, status, realized_pnl, exit_price, quantity, entry_price, "
            "cost_basis, notes, exit_date, max_loss, structure, long_strike, short_strike, "
            "legs, entry_side FROM unified_positions WHERE position_id = $1", position_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
        if (row["status"] or "").upper() not in ("CLOSED", "EXPIRED"):
            raise HTTPException(
                status_code=400,
                detail=f"{position_id} is {row['status']}; a correction here applies to a row "
                       f"that has ended (an open row closes through /close)")
        lot_sources = [r["source"] for r in await conn.fetch(
            "SELECT source FROM position_lots WHERE position_id = $1", position_id)]
        shape = {"quantity", "entry_price", "cost_basis"} & set(fields)
        real_lots = [s for s in lot_sources if s != "LEGACY-SINGLE-LOT"]
        if shape and real_lots:
            raise HTTPException(
                status_code=400,
                detail=(f"{sorted(shape)} derive from this row's {len(real_lots)} recorded fill(s); "
                        f"correct the fills, not the aggregate they compute"))

        changes = []
        for f, v in fields.items():
            before = row.get(f)
            if f == "exit_date":
                after = v
            else:
                after = round(float(v), 2) if f in ("realized_pnl", "cost_basis") else float(v)
            fields[f] = after
            changes.append(f"{f} {'NULL' if before is None else before} -> {after}")
        # R-IV.463(e): max_loss DERIVES from the row as corrected and the path writes it. A shape
        # corrected without it left 352 and 358 carrying the figure of the shape they no longer
        # have. A correction with no figure at all is how a stale one is brought into line.
        derived = await _derive_max_loss(conn, row, fields)
        if derived is not None and (row.get("max_loss") is None
                                    or abs(float(row["max_loss"]) - derived) > 0.005):
            changes.append(f"max_loss {row.get('max_loss')} -> {derived} (derived)")
            fields["max_loss"] = derived
        if not fields:
            raise HTTPException(status_code=400, detail="no figure to correct")
        outcome = None
        if "realized_pnl" in fields:
            r = fields["realized_pnl"]
            outcome = "WIN" if r > 0 else "LOSS" if r < 0 else "BREAKEVEN"
        note = (f" || {req.ruling} CORRECTION: " + "; ".join(changes)
                + f". EVIDENCE: {req.evidence.strip()} REASON: {req.reason.strip()}")
        sets, params = [], []
        for f, v in fields.items():
            params.append(v)
            sets.append(f"{f} = ${len(params)}")
        if outcome:
            params.append(outcome)
            sets.append(f"trade_outcome = ${len(params)}")
        params.append(note)
        sets.append(f"notes = COALESCE(notes, '') || ${len(params)}")
        params.append(position_id)
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.actor', $1, true)",
                               (req.actor or "lifecycle-ui"))
            await conn.execute("SELECT set_config('app.reason', $1, true)",
                               f"{req.ruling}: correction with evidence")
            await conn.execute(
                f"UPDATE unified_positions SET {', '.join(sets)}, updated_at = NOW() "
                f"WHERE position_id = ${len(params)}", *params)
            # A LEGACY-SINGLE-LOT is a COPY of the row, backfilled from it -- not a fill. When
            # the row it copied is corrected, the copy is regenerated from the corrected row so
            # the two cannot drift; a real fill is never touched here (refused above).
            if shape and lot_sources and not real_lots:
                await conn.execute(
                    """UPDATE position_lots l
                          SET qty = p.quantity, price = p.entry_price
                         FROM unified_positions p
                        WHERE p.position_id = l.position_id AND l.position_id = $1
                          AND l.source = 'LEGACY-SINGLE-LOT'""", position_id)
    return {"status": "corrected", "position_id": position_id,
            "realized_before": None if row["realized_pnl"] is None else float(row["realized_pnl"]),
            "realized_after": fields.get("realized_pnl"),
            "changes": changes, "trade_outcome": outcome, "evidence_recorded": True,
            "max_loss_derived": fields.get("max_loss"),
            "legacy_lot_regenerated": bool(shape and lot_sources and not real_lots)}


class LinkTradeRequest(BaseModel):
    """Link a book row to the `trades` row recording the same event (R-IV.464(e))."""
    trade_id: int
    evidence: str                # what makes them the same event, beside the verdict (#23)
    reason: str
    ruling: str
    actor: Optional[str] = None


@router.post("/v2/positions/{position_id}/link-trade")
async def link_trade(position_id: str, req: LinkTradeRequest, _=Depends(require_api_key)):
    """Record that a book row and a `trades` row are the same event.

    There was no path: `trade_id` is written by the close endpoint when IT creates the trade, and
    an adjudicated pair -- a book row and a ledger row that match on ticker, day and figure --
    had nowhere to be recorded. Analytics reads the book now (R-IV.463(h)), so a link changes no
    figure; what it changes is the coverage chip, which counts every closed trade the book is not
    linked to. Refuses a link that would contradict one already recorded, in either direction.
    """
    for name in ("evidence", "reason", "ruling"):
        if not str(getattr(req, name) or "").strip():
            raise HTTPException(status_code=400, detail=(
                f"{name} is required -- a link is an adjudication (conventions #23)"))
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT position_id, ticker, trade_id, realized_pnl, exit_date FROM "
            "unified_positions WHERE position_id = $1", position_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
        if row["trade_id"] is not None and int(row["trade_id"]) != int(req.trade_id):
            raise HTTPException(status_code=409, detail=(
                f"{position_id} is already linked to trades id {row['trade_id']}"))
        trade = await conn.fetchrow(
            "SELECT id, ticker, pnl_dollars, closed_at FROM trades WHERE id = $1", req.trade_id)
        if not trade:
            raise HTTPException(status_code=404, detail=f"trades id {req.trade_id} not found")
        held_by = await conn.fetchrow(
            "SELECT position_id, status, duplicate_of FROM unified_positions "
            "WHERE trade_id = $1 AND position_id <> $2", req.trade_id, position_id)
        follows = None
        if held_by:
            # R-IV.465(c): a link recorded against a row later retired points at its keeper. The
            # trade happened once; taking it up here is the follow, not a second link.
            if (held_by["status"] == DUPLICATE_OF
                    and held_by["duplicate_of"] == position_id):
                follows = held_by["position_id"]
            else:
                raise HTTPException(status_code=409, detail=(
                    f"trades id {req.trade_id} is already linked to {held_by['position_id']}"))
        note = (f" || {req.ruling} LINKED to trades id {req.trade_id} "
                f"({trade['ticker']}, {str(trade['closed_at'])[:10]}, "
                f"{trade['pnl_dollars']}). EVIDENCE: {req.evidence.strip()} "
                f"REASON: {req.reason.strip()}")
        if follows:
            note += (f" FOLLOWED from retired {follows} (R-IV.465(c)): the retirement was a "
                     f"bookkeeping act, not a change of fact.")
        async with conn.transaction():
            await name_actor(conn, req.actor or "lifecycle-ui",
                             f"{req.ruling}: linked to trades id {req.trade_id}")
            if follows:
                await conn.execute(
                    "UPDATE unified_positions SET trade_id = NULL, "
                    "notes = COALESCE(notes, '') || $1, updated_at = NOW() "
                    "WHERE position_id = $2",
                    f" || R-IV.465(c) LINK MOVED to keeper {position_id}: trades id "
                    f"{req.trade_id}", follows)
            await conn.execute(
                "UPDATE unified_positions SET trade_id = $1, notes = COALESCE(notes, '') || $2, "
                "updated_at = NOW() WHERE position_id = $3", req.trade_id, note, position_id)
    return {"status": "linked", "position_id": position_id, "trade_id": req.trade_id,
            "followed_from_retired": follows,
            "book_realized": None if row["realized_pnl"] is None else float(row["realized_pnl"]),
            "trades_realized": None if trade["pnl_dollars"] is None else float(trade["pnl_dollars"]),
            "figures_agree": (row["realized_pnl"] is not None and trade["pnl_dollars"] is not None
                              and abs(float(row["realized_pnl"]) - float(trade["pnl_dollars"])) < 0.005)}


class ClosedFromEvidenceRequest(BaseModel):
    """A position that ENDED before the book recorded it, entered from its evidence (R-IV.463(g)).

    The shape the import will need: a closed row, its legs, its opening fill, and the lines
    that support it -- with no cash moved, because the cash moved when the trade happened.
    """
    ticker: str
    account: str
    asset_type: str = "OPTION"                 # OPTION | EQUITY
    structure: str
    direction: Optional[str] = None
    quantity: float
    entry_price: float                         # per structure / per share, as the record gives it
    entry_date: str
    exit_date: str
    exit_price: Optional[float] = None
    realized_pnl: Optional[float] = None       # the record's figure; derived gross when absent
    trade_outcome: Optional[str] = None        # WIN | LOSS | BREAKEVEN | UNKNOWN
    status: str = "CLOSED"                     # CLOSED | EXPIRED
    expiry: Optional[str] = None
    long_strike: Optional[float] = None
    short_strike: Optional[float] = None
    legs: Optional[List[EntryLeg]] = None      # per structure, as POST /v2/positions/with-legs
    source: str = "BROKER_EXPORT"              # an import source: the row landed from a record
    broker_ref: Optional[str] = None
    exit_broker_ref: Optional[str] = None
    trade_id: Optional[int] = None             # the trades row recording the same event, if any
    evidence: str
    reason: str
    ruling: str
    actor: Optional[str] = None


@router.post("/v2/positions/closed-from-evidence")
async def create_closed_from_evidence(req: ClosedFromEvidenceRequest,
                                      _=Depends(require_api_key)):
    """Record a position that ended before the book held it -- from its evidence (R-IV.463(g)).

    There was no path: every create opens a row and credits or debits cash, and every close
    ends an OPEN row. So a real event the book had missed -- ids 512/513 -- could be recorded
    only by direct SQL, bypassing every guard. A reconciliation that must bypass every guarded
    path to record a real event is a missing capability, not a workaround.

    One transaction, named for the audit: the row (CLOSED or EXPIRED, provenance IMPORTED from
    its import source -- never BROKER_VERIFIED, which is its own path), its legs when given, and
    its opening fill as an IMPORT lot. The exit lives on the row, as the close path leaves it.
    NO CASH MOVES: the trade already moved it, and the balance already holds it. max_loss and
    cost_basis derive; realized is the record's figure, or the gross from entry and exit when
    the record gives none. Evidence, reason and ruling are required and written onto the row.
    """
    for name in ("evidence", "reason", "ruling"):
        if not str(getattr(req, name) or "").strip():
            raise HTTPException(status_code=400, detail=(
                f"{name} is required -- a row created from evidence with no {name} beside it "
                f"is a number alone (conventions #23)"))
    status = (req.status or "").strip().upper()
    if status not in ("CLOSED", "EXPIRED"):
        raise HTTPException(status_code=400, detail=(
            f"status {req.status!r}: this path records a position that has ENDED -- CLOSED or "
            f"EXPIRED. An open position is entered through POST /v2/positions or /with-legs"))
    source = (req.source or "").strip()
    if source not in IMPORT_PARENT_SOURCES:
        raise HTTPException(status_code=400, detail=(
            f"source {req.source!r}: a row from evidence landed from a record, so its source is "
            f"an import source: {sorted(IMPORT_PARENT_SOURCES)}"))
    if req.quantity is None or req.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be positive")
    if req.entry_price is None or req.entry_price < 0:
        raise HTTPException(status_code=400, detail=(
            "entry_price is the magnitude paid or received; its side comes from the legs or the "
            "structure"))
    if req.exit_price is None and req.realized_pnl is None and not req.trade_outcome:
        raise HTTPException(status_code=400, detail=(
            "R-IV.454(d): an ended row needs its exit -- an exit price, a realized figure, or "
            "the outcome (UNKNOWN is a valid one)"))
    entered = _when(req.entry_date, "entry_date")
    exited = _when(req.exit_date, "exit_date")
    if exited < entered:
        raise HTTPException(status_code=400, detail="exit_date is before entry_date")

    account = canonical_account(req.account)
    asset_type = (req.asset_type or "OPTION").strip().upper()
    _assert_etf_only(account, asset_type)
    structure = req.structure.strip().lower()
    qty = float(req.quantity)
    entry = float(req.entry_price)
    mult = 100 if asset_type in ("OPTION", "SPREAD") else 1

    legs = _validated_legs(req.legs, qty) if req.legs else []
    expiry = None
    if legs:
        side, _how = entry_orientation(legs)
        if side is None:
            side = _orientation_by_name(structure, req.direction or "")
        shown = display_strikes(legs)
        long_k, short_k = shown["long_strike"], shown["short_strike"]
        expiry = sorted({l["expiry"] for l in legs})[0]
    else:
        long_k, short_k = normalize_spread_strikes(req.long_strike, req.short_strike, structure)
        if asset_type in ("OPTION", "SPREAD"):
            side = _orientation_by_name(structure, req.direction or "")
        else:
            short_stock = structure in ("stock_short", "short_stock") or \
                (req.direction or "").upper() == "SHORT"
            side = -1 if short_stock else 1
        if req.expiry:
            try:
                expiry = date.fromisoformat(str(req.expiry)[:10])
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail="expiry must be a date")

    realized = req.realized_pnl
    realized_note = "the record's figure"
    if realized is None and req.exit_price is not None:
        realized = round(side * (float(req.exit_price) - entry) * qty * mult, 2)
        realized_note = "derived gross from entry and exit (the record gave no realized figure)"
    outcome = (req.trade_outcome or "").strip().upper() or (
        None if realized is None else "WIN" if realized > 0 else "LOSS" if realized < 0
        else "BREAKEVEN") or "UNKNOWN"
    cost_basis = round(entry * qty * mult, 2)
    entry_side = {1: "DEBIT", -1: "CREDIT"}.get(side) if asset_type in ("OPTION", "SPREAD") else None
    now = datetime.now(timezone.utc)
    pid = f"POS_{req.ticker.upper()}_{entered.strftime('%Y%m%d')}_EV{now.strftime('%H%M%S%f')[:10]}"
    note = (f"{req.ruling} CREATED FROM EVIDENCE: {status} {qty:g} {structure} "
            f"{req.entry_date} -> {req.exit_date}; realized {realized} ({realized_note}). "
            f"EVIDENCE: {req.evidence.strip()} REASON: {req.reason.strip()}")

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        for ref in (req.broker_ref, req.exit_broker_ref):
            if not ref:
                continue
            dup = await conn.fetchval(
                "SELECT position_id FROM unified_positions WHERE broker_ref = $1 "
                "OR exit_broker_ref = $1 UNION SELECT position_id FROM position_lots "
                "WHERE broker_ref = $1 LIMIT 1", ref)
            if dup:
                raise HTTPException(status_code=409, detail=(
                    f"broker_ref {ref} is already recorded on {dup} -- the event is in the book"))
        if req.trade_id is not None:
            linked = await conn.fetchval(
                "SELECT position_id FROM unified_positions WHERE trade_id = $1", req.trade_id)
            if linked:
                raise HTTPException(status_code=409, detail=(
                    f"trades id {req.trade_id} is already linked to {linked}"))
        max_loss = _max_loss_for(legs, side, entry, qty, structure, long_k, short_k, None)
        async with conn.transaction():
            await name_actor(conn, req.actor or "lifecycle-ui",                  # R-IV.463(b)
                             f"{req.ruling}: created from evidence")
            await conn.execute("""
                INSERT INTO unified_positions
                    (position_id, ticker, asset_type, structure, direction, quantity,
                     entry_price, cost_basis, entry_date, exit_date, exit_price, realized_pnl,
                     trade_outcome, status, expiry, long_strike, short_strike, account, source,
                     provenance, broker_ref, exit_broker_ref, trade_id, entry_side, notes,
                     max_loss, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
                        $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, NOW(), NOW())""",
                pid, req.ticker.upper(), asset_type, structure,
                (req.direction or "").upper() or None, qty, entry, cost_basis, entered, exited,
                req.exit_price, realized, outcome, status, expiry, long_k, short_k, account,
                source, provenance_for_parent(source, entry), req.broker_ref,
                req.exit_broker_ref, req.trade_id, entry_side, note, max_loss)
            for seq, leg in enumerate(legs, 1):
                await conn.execute("""
                    INSERT INTO position_legs
                        (position_id, leg_seq, option_type, side, strike, expiry, qty, price,
                         provenance, migrated_from)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'closed-from-evidence')""",
                    pid, seq, leg["option_type"], leg["side"], leg["strike"], leg["expiry"],
                    leg["qty"], leg["price"], provenance_for_lot("IMPORT", leg["price"]))
            lot_id = await conn.fetchval("""
                INSERT INTO position_lots
                    (position_id, fill_time, qty, price, fees, source, provenance, broker_ref)
                VALUES ($1, $2, $3, $4, 0, 'IMPORT', $5, $6) RETURNING id""",
                pid, entered, qty, entry, provenance_for_lot("IMPORT", entry), req.broker_ref)

    return {"status": "created", "position_id": pid, "row_status": status,
            "realized_pnl": realized, "realized_basis": realized_note, "trade_outcome": outcome,
            "cost_basis": cost_basis, "max_loss": max_loss, "legs": len(legs),
            "opening_lot_id": lot_id, "provenance": provenance_for_parent(source, entry),
            "cash_moved": False}


class RetireDuplicateRequest(BaseModel):
    """Retire a row that records a trade the book already holds under another id."""
    duplicate_of: str            # the keeper's position_id
    reason: str                  # required — why this row is the duplicate and that one the keeper
    actor: Optional[str] = None


@router.post("/v2/positions/{position_id}/retire-duplicate")
async def retire_duplicate_position(position_id: str, req: RetireDuplicateRequest,
                                    _=Depends(require_api_key)):
    """Mark a row as a duplicate of another. It is never deleted (R-IV.449(a)).

    The duplicate is the only record that the duplication happened, and the only evidence of
    what caused it — here, a row filed under a retired account alias that an account-scoped
    inventory could not see, so the reconciliation reported absence where there was duplication.

    Its notes are untouched. Its money stops counting because every rollup asks for CLOSED or
    EXPIRED rather than for "not open"; the keeper already carries the realized figure.
    """
    if req.duplicate_of == position_id:
        raise HTTPException(status_code=400, detail="a row cannot be a duplicate of itself")
    if not req.reason.strip():
        raise HTTPException(
            status_code=400,
            detail="reason is required — a retirement with no stated cause is indistinguishable "
                   "from a row quietly removed from the totals")
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT position_id, ticker, status, realized_pnl, trade_id FROM unified_positions "
            "WHERE position_id = $1", position_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
        keeper = await conn.fetchrow(
            "SELECT position_id, ticker, status, trade_id FROM unified_positions "
            "WHERE position_id = $1", req.duplicate_of)
        if not keeper:
            raise HTTPException(
                status_code=404,
                detail=f"keeper {req.duplicate_of} not found — a duplicate must point at a row "
                       f"that exists, or the trade it stops carrying is carried by nothing")
        if keeper["status"] == DUPLICATE_OF:
            raise HTTPException(
                status_code=400,
                detail=f"{req.duplicate_of} is itself retired as a duplicate; point at the row "
                       f"that actually holds the trade")
        # R-IV.465(c): A LINK FOLLOWS THE KEEPER. A `trades` row linked to this one records an
        # event that happened ONCE; the retirement is a bookkeeping act, not a change of fact,
        # so the link moves to the row that now carries the trade. The retired row keeps the
        # record of where it pointed, in its note and in the audit.
        link_moved = None
        link_conflict = None
        if row["trade_id"] is not None:
            if keeper["trade_id"] is None:
                link_moved = int(row["trade_id"])
            elif int(keeper["trade_id"]) != int(row["trade_id"]):
                link_conflict = (f"this row is linked to trades id {row['trade_id']} and the "
                                 f"keeper to {keeper['trade_id']}; the link stays here and the "
                                 f"disagreement is for adjudication")
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.actor', $1, true)",
                               (req.actor or "lifecycle-ui"))
            await conn.execute("SELECT set_config('app.reason', $1, true)", req.reason)
            note = (f" || R-IV.465(c) LINK MOVED to keeper {req.duplicate_of}: trades id "
                    f"{link_moved}") if link_moved else (
                f" || R-IV.465(c) LINK NOT MOVED: {link_conflict}" if link_conflict else "")
            # The duplicate's own notes are the record of what caused the duplication, so they
            # are never overwritten. A link that moves appends its line; nothing else writes here.
            await conn.execute(
                f"""UPDATE unified_positions
                       SET status = $1, duplicate_of = $2,
                           trade_id = CASE WHEN $4::bigint IS NULL THEN trade_id ELSE NULL END,
                           {"notes = COALESCE(notes, '') || $5," if note else ""}
                           updated_at = NOW()
                     WHERE position_id = $3""",
                *((DUPLICATE_OF, req.duplicate_of, position_id, link_moved, note) if note
                  else (DUPLICATE_OF, req.duplicate_of, position_id, link_moved)))
            if link_moved is not None:
                await conn.execute(
                    """UPDATE unified_positions
                          SET trade_id = $1,
                              notes = COALESCE(notes, '') || $2, updated_at = NOW()
                        WHERE position_id = $3""",
                    link_moved,
                    f" || R-IV.465(c) LINK FOLLOWED from retired {position_id}: trades id "
                    f"{link_moved}", req.duplicate_of)
    return {"status": "retired", "position_id": position_id, "marked": DUPLICATE_OF,
            "duplicate_of": req.duplicate_of, "keeper_ticker": keeper["ticker"],
            "realized_no_longer_counted": (float(row["realized_pnl"])
                                           if row["realized_pnl"] is not None else None),
            "notes_preserved": True, "link_moved_to_keeper": link_moved,
            "link_conflict": link_conflict}


@router.post("/v2/positions/{position_id}/verify")
async def verify_position(position_id: str, req: VerifyRequest, _=Depends(require_api_key)):
    """Match a POSITION row to a broker record (R-IV.448(b)).

    The row carries the same three pieces of evidence as a lot or a leg. What it does NOT
    carry is a uniqueness rule on the reference: one fill can close several positions — the
    60-share SOXS sale covers three rows — so a reference is EXPECTED to repeat here, and a
    constraint forbidding it would reject the correction set's own evidence.
    """
    if not req.broker_ref.strip() or not req.verified_event.strip():
        raise HTTPException(
            status_code=400,
            detail="broker_ref and verified_event are both required — a verification naming "
                   "neither what was matched nor its reference cannot be re-checked")
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT position_id, ticker, provenance, broker_ref FROM unified_positions "
            "WHERE position_id = $1", position_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.actor', $1, true)",
                               (req.actor or "lifecycle-ui"))
            await conn.execute("SELECT set_config('app.reason', $1, true)",
                               (req.reason or req.verified_event))
            await conn.execute(
                """UPDATE unified_positions
                      SET provenance = 'BROKER_VERIFIED', broker_ref = $1,
                          verified_event = $2, verified_at = NOW(), updated_at = NOW()
                    WHERE position_id = $3""",
                req.broker_ref, req.verified_event, position_id)
            await _audit_leg(conn, position_id, row["ticker"], "VERIFY", "provenance",
                             {"provenance": row["provenance"], "broker_ref": row["broker_ref"]},
                             {"provenance": "BROKER_VERIFIED", "broker_ref": req.broker_ref,
                              "verified_event": req.verified_event},
                             req.actor, req.reason or req.verified_event)
    return {"status": "verified", "position_id": position_id, "provenance": "BROKER_VERIFIED",
            "broker_ref": req.broker_ref, "verified_event": req.verified_event}


@router.post("/v2/positions/{position_id}/lots/{lot_id}/verify")
async def verify_position_lot(position_id: str, lot_id: int, req: VerifyRequest,
                              _=Depends(require_api_key)):
    """Match a lot to a broker record — the only route to BROKER_VERIFIED for a lot."""
    return await _verify_row("position_lots", position_id, lot_id, req)


@router.post("/v2/positions/{position_id}/legs/{leg_seq}/verify")
async def verify_position_leg(position_id: str, leg_seq: int, req: VerifyRequest,
                              _=Depends(require_api_key)):
    """Match a leg to a broker record — the only route to BROKER_VERIFIED for a leg."""
    return await _verify_row("position_legs", position_id, leg_seq, req, key_column="leg_seq")


class ScreenVerifyRequest(BaseModel):
    """What a broker SCREEN showed, with the evidence that makes it re-checkable (R-IV.470(a))."""
    fields_read: List[str]         # the fields actually read off the screen, named
    captured_at: str               # when the screen was captured -- not the fill, not now
    transcribed_by: str            # who read it across
    reason: Optional[str] = None
    ruling: Optional[str] = None


def _screen_evidence(req: "ScreenVerifyRequest") -> Tuple[str, datetime]:
    """The evidence line the database stores, and the instant it was captured."""
    fields = [str(f).strip() for f in (req.fields_read or []) if str(f).strip()]
    if not fields:
        raise HTTPException(status_code=400, detail=(
            "fields_read is required -- a screen verification that does not name the fields it "
            "read cannot be re-checked against the screen, which is what this rung is for"))
    if not str(req.transcribed_by or "").strip():
        raise HTTPException(status_code=400, detail=(
            "transcribed_by is required -- a reading has a reader"))
    captured = _when(req.captured_at, "captured_at")
    return (f"SCREEN: {', '.join(fields)}; captured {captured.isoformat()}; "
            f"transcribed by {req.transcribed_by.strip()}"), captured


def _screen_refusal(current: Optional[str]) -> None:
    """A screen never overwrites a stronger claim (R-IV.470(a))."""
    if outranks(current, SCREEN_VERIFIED):
        raise HTTPException(status_code=409, detail=(
            f"this record is already {current}, which supersedes a screen reading: an export "
            f"line is the broker's own file and a verification is a matched reference. Correct "
            f"the stronger record through its own path, or leave it."))


async def _screen_verify_row(table: str, position_id: str, row_id: int,
                             req: ScreenVerifyRequest, key_column: str = "id"):
    """Stamp one lot or leg SCREEN_VERIFIED -- the only path to that value (R-IV.470(a))."""
    evidence, captured = _screen_evidence(req)
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT r.*, p.ticker FROM {table} r "
            f"JOIN unified_positions p ON p.position_id = r.position_id "
            f"WHERE r.position_id = $1 AND r.{key_column} = $2", position_id, row_id)
        if not row:
            raise HTTPException(status_code=404,
                                detail=f"{table} {row_id} not found on {position_id}")
        _screen_refusal(row["provenance"])
        async with conn.transaction():
            await conn.execute(
                f"""UPDATE {table}
                       SET provenance = $1, verified_event = $2, verified_at = $3
                     WHERE position_id = $4 AND {key_column} = $5""",
                SCREEN_VERIFIED, evidence, captured, position_id, row_id)
            await _audit_leg(conn, position_id, row["ticker"], "SCREEN_VERIFY",
                             f"{table}:{row_id}:provenance",
                             {"provenance": row["provenance"]},
                             {"provenance": SCREEN_VERIFIED, "verified_event": evidence},
                             req.transcribed_by, req.reason or (req.ruling or "R-IV.470(a)"))
    return {"status": "screen_verified", "position_id": position_id, "table": table,
            "id": row_id, "provenance": SCREEN_VERIFIED, "verified_event": evidence,
            "captured_at": captured.isoformat(), "was": row["provenance"]}


@router.post("/v2/positions/{position_id}/screen-verify")
async def screen_verify_position(position_id: str, req: ScreenVerifyRequest,
                                 _=Depends(require_api_key)):
    """Record that a broker SCREEN showed this row's figures (R-IV.470(a)).

    Its own rung, with its own evidence. `verified_at` is when the SCREEN WAS CAPTURED -- not the
    fill's time, and not now: a screen read a week later is evidence about the day it was taken.
    The path refuses to overwrite IMPORTED or BROKER_VERIFIED, because an export line and a
    matched reference are both stronger than a reading of a picture.
    """
    evidence, captured = _screen_evidence(req)
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT position_id, ticker, provenance FROM unified_positions WHERE position_id = $1",
            position_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
        _screen_refusal(row["provenance"])
        async with conn.transaction():
            await name_actor(conn, req.transcribed_by,
                             req.reason or f"{req.ruling or 'R-IV.470(a)'}: screen verification")
            await conn.execute(
                """UPDATE unified_positions
                      SET provenance = $1, verified_event = $2, verified_at = $3,
                          updated_at = NOW()
                    WHERE position_id = $4""",
                SCREEN_VERIFIED, evidence, captured, position_id)
            await _audit_leg(conn, position_id, row["ticker"], "SCREEN_VERIFY", "provenance",
                             {"provenance": row["provenance"]},
                             {"provenance": SCREEN_VERIFIED, "verified_event": evidence},
                             req.transcribed_by, req.reason or (req.ruling or "R-IV.470(a)"))
    return {"status": "screen_verified", "position_id": position_id,
            "provenance": SCREEN_VERIFIED, "verified_event": evidence,
            "captured_at": captured.isoformat(), "was": row["provenance"]}


@router.post("/v2/positions/{position_id}/lots/{lot_id}/screen-verify")
async def screen_verify_lot(position_id: str, lot_id: int, req: ScreenVerifyRequest,
                            _=Depends(require_api_key)):
    """A lot whose figures a broker screen showed -- the only route to SCREEN_VERIFIED for a lot."""
    return await _screen_verify_row("position_lots", position_id, lot_id, req)


@router.post("/v2/positions/{position_id}/legs/{leg_seq}/screen-verify")
async def screen_verify_leg(position_id: str, leg_seq: int, req: ScreenVerifyRequest,
                            _=Depends(require_api_key)):
    """A leg whose figures a broker screen showed -- the only route to SCREEN_VERIFIED for a leg."""
    return await _screen_verify_row("position_legs", position_id, leg_seq, req,
                                    key_column="leg_seq")


class CorrectTerminalStatusRequest(BaseModel):
    """A wrong terminal status, corrected with its evidence (R-IV.470(b))."""
    status: str                    # CLOSED | EXPIRED | OPEN
    evidence: str
    reason: str
    ruling: str
    actor: Optional[str] = None


@router.post("/v2/positions/{position_id}/correct-terminal-status")
async def correct_terminal_status(position_id: str, req: CorrectTerminalStatusRequest,
                                  _=Depends(require_api_key)):
    """Correct a terminal status that is wrong -- with its evidence (R-IV.470(b)).

    The sweep wrote EXPIRED/UNKNOWN over HYG 218 before the ruling that it had been ROLLED
    arrived, and nothing could fix it: the PATCH refuses terminal statuses (R-IV.454(d)), the
    close path takes only OPEN rows, and the retire path is for duplicates. So a wrong status
    could be corrected only by SQL straight into the table.

    **The race is inherent -- a sweep and a ruling can always cross -- so correctability is the
    fix, not timing.** A row moved back to OPEN cannot keep an exit it did not have: the exit
    date, exit price, realized figure and outcome are cleared, and the response says what went.
    A row moved between terminal statuses keeps its exit and must have one (R-IV.454(d)).
    """
    for name in ("evidence", "reason", "ruling"):
        if not str(getattr(req, name) or "").strip():
            raise HTTPException(status_code=400, detail=(
                f"{name} is required -- a status corrected with no {name} beside it is a verdict "
                f"alone (conventions #23)"))
    target = (req.status or "").strip().upper()
    if target not in ("CLOSED", "EXPIRED", "OPEN"):
        raise HTTPException(status_code=400, detail=(
            f"status {req.status!r}: CLOSED, EXPIRED or OPEN. A duplicate is retired through "
            f"/retire-duplicate, which records its keeper."))
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT position_id, ticker, status, exit_date, exit_price, realized_pnl, "
            "trade_outcome FROM unified_positions WHERE position_id = $1", position_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
        was = (row["status"] or "").upper()
        if was not in ("CLOSED", "EXPIRED"):
            raise HTTPException(status_code=400, detail=(
                f"{position_id} is {row['status']}, not terminal: this path corrects a status "
                f"that ended the row wrongly. An OPEN row ends through /close or /reduce."))
        if was == target:
            raise HTTPException(status_code=400, detail=f"{position_id} is already {target}")
        cleared = {}
        if target == "OPEN":
            cleared = {k: (float(row[k]) if isinstance(row[k], (int, float)) else
                           (row[k].isoformat() if hasattr(row[k], "isoformat") else row[k]))
                       for k in ("exit_date", "exit_price", "realized_pnl", "trade_outcome")
                       if row[k] is not None}
        elif not any(row[k] is not None for k in ("exit_price", "realized_pnl", "trade_outcome")):
            raise HTTPException(status_code=400, detail=(
                "R-IV.454(d): a terminal status needs its exit -- an exit price, a realized "
                "figure, or the outcome (UNKNOWN is a valid one). Record it through "
                "/correct-realized first."))
        note = (f" || {req.ruling} TERMINAL STATUS CORRECTED: {was} -> {target}"
                + (f"; cleared {', '.join(sorted(cleared))}" if cleared else "")
                + f". EVIDENCE: {req.evidence.strip()} REASON: {req.reason.strip()}")
        async with conn.transaction():
            await name_actor(conn, req.actor or "lifecycle-ui",
                             f"{req.ruling}: terminal status corrected with evidence")
            if target == "OPEN":
                await conn.execute(
                    """UPDATE unified_positions
                          SET status = 'OPEN', exit_date = NULL, exit_price = NULL,
                              realized_pnl = NULL, trade_outcome = NULL,
                              notes = COALESCE(notes, '') || $1, updated_at = NOW()
                        WHERE position_id = $2""", note, position_id)
            else:
                await conn.execute(
                    """UPDATE unified_positions
                          SET status = $1, notes = COALESCE(notes, '') || $2, updated_at = NOW()
                        WHERE position_id = $3""", target, note, position_id)
    return {"status": "corrected", "position_id": position_id, "was": was, "now": target,
            "cleared": cleared or None, "evidence_recorded": True}


class LegRequest(BaseModel):
    """One leg of a structure, entered or corrected by hand (R-IV.445(c))."""
    option_type: str                      # CALL | PUT
    side: str                             # LONG | SHORT
    strike: float
    expiry: str
    qty: float
    price: Optional[float] = None
    broker_ref: Optional[str] = None
    # R-IV.463(e): where the leg came from. MANUAL = entered by hand (PRINCIPAL_REPORTED);
    # IMPORT = read from a broker export or statement (IMPORTED). Never BROKER_VERIFIED here.
    source: str = "MANUAL"
    reason: Optional[str] = None
    actor: Optional[str] = None


class LegPatchRequest(BaseModel):
    """A correction to one leg. Every field optional; at least one required."""
    option_type: Optional[str] = None
    side: Optional[str] = None
    strike: Optional[float] = None
    expiry: Optional[str] = None
    qty: Optional[float] = None
    price: Optional[float] = None
    broker_ref: Optional[str] = None
    source: Optional[str] = None      # R-IV.463(e): relabel where the leg came from
    reason: Optional[str] = None
    actor: Optional[str] = None


_LEG_FIELDS = ("option_type", "side", "strike", "expiry", "qty", "price", "broker_ref")


def _leg_source(source: Optional[str]) -> str:
    """MANUAL or IMPORT -- the lots vocabulary, so a leg and a fill say where they came from the
    same way. Anything else is refused rather than read as MANUAL."""
    s = (source or "MANUAL").strip().upper()
    if s not in LOT_SOURCE_PROVENANCE:
        raise HTTPException(status_code=400, detail=(
            f"source {source!r}: MANUAL (entered by hand) or IMPORT (read from a broker export "
            f"or statement)"))
    return s


def _when(value: Any, name: str, *, allow_future: bool = False) -> datetime:
    """A caller's date or timestamp, as the instant the book stores (R-IV.464(a)).

    utils.book_time holds the convention -- a bare date is that day at 00:00 in DENVER, the
    principal's day -- and every path into the book reads dates through here, so one date cannot
    mean two instants depending on which door it came through."""
    try:
        when = book_instant(value, name)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{name} must be a date or a timestamp; "
                                                    f"got {value!r}")
    if not allow_future and when > datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail=f"{name} {value} is in the future")
    return when


async def _derive_max_loss(conn, row, corrected: Dict[str, Any]) -> Optional[float]:
    """max_loss of the row AS CORRECTED -- never an input (R-IV.463(e)).

    From its legs when it has them (R-IV.460: the legs say what is held), with the row's entry as
    the signed net in the side it was entered on; else by the derivation the create path uses.
    None when the row does not carry enough to derive it, or its loss has no bound."""
    entry = corrected.get("entry_price", row.get("entry_price"))
    qty = corrected.get("quantity", row.get("quantity"))
    if entry is None or qty is None:
        return None
    legs = [dict(l) for l in await conn.fetch(
        "SELECT option_type, side, strike, expiry, qty, price FROM position_legs "
        "WHERE position_id = $1 ORDER BY leg_seq", row.get("position_id"))]
    side = entry_orientation(legs, row.get("entry_side"))[0] if legs else None
    return _max_loss_for(legs, side, entry, qty, row.get("structure"), row.get("long_strike"),
                         row.get("short_strike"), row.get("legs"))


def _max_loss_for(legs, side, entry, qty, structure, long_strike, short_strike,
                  raw_legs) -> Optional[float]:
    """The derivation itself, pure: legs and their side when there are legs, else the create
    path's calculate_position_risk. None when it cannot be derived or has no bound."""
    import math
    if legs:
        if side is None:
            return None
        loss = analyze(legs, net_premium_override=side * float(entry)).get("max_loss")
        return round(float(loss) * float(qty), 2) if isinstance(loss, (int, float)) else None
    if not structure:
        return None
    ls, ss = normalize_spread_strikes(
        float(long_strike) if long_strike is not None else None,
        float(short_strike) if short_strike is not None else None, structure)
    if isinstance(raw_legs, str):
        try:
            raw_legs = json.loads(raw_legs)
        except ValueError:
            raw_legs = None
    try:
        loss = calculate_position_risk(structure=structure, entry_price=float(entry),
                                       quantity=float(qty), long_strike=ls, short_strike=ss,
                                       legs=raw_legs).get("max_loss")
    except Exception:
        return None
    if loss is None or not math.isfinite(float(loss)):
        return None
    return round(float(loss), 2)


def _leg_values(option_type: str, side: str) -> tuple:
    ot, sd = (option_type or "").strip().upper(), (side or "").strip().upper()
    if ot not in ("CALL", "PUT"):
        raise HTTPException(status_code=400, detail="option_type must be CALL or PUT")
    if sd not in ("LONG", "SHORT"):
        raise HTTPException(status_code=400,
                            detail="side must be LONG or SHORT — a leg is bought or sold, and "
                                   "the sign of a quantity is not a substitute for saying which")
    return ot, sd


async def _audit_leg(conn, position_id: str, ticker: str, operation: str, field: str,
                     before, after, actor: Optional[str], reason: Optional[str]) -> None:
    """One timeline per position (Phase-1 D2) — leg writes append to it, not to a new table."""
    await conn.execute(
        """INSERT INTO position_sync_audit
               (operation, position_id, ticker, field, before_state, after_state, actor, reason,
                executed_at)
           VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, NOW())""",
        operation, position_id, ticker, field,
        dumps_jsonb(before) if before is not None else None,
        dumps_jsonb(after) if after is not None else None,
        actor or "lifecycle-ui", reason)


async def _settle_pending_capability(conn, position_id: str) -> None:
    """A position waiting on hand-entry stops waiting once its legs exist.

    The row was never a failed migration — the shape was beyond what two strike columns could
    hold. When the legs are entered the record says so rather than staying filed under a
    capability that has since arrived.
    """
    await conn.execute(
        """UPDATE position_legs_migration
              SET outcome = 'ENTERED_BY_HAND',
                  detail = COALESCE(detail, '') || ' | legs entered by hand (R-IV.445(c))',
                  legs_written = (SELECT COUNT(*) FROM position_legs l
                                   WHERE l.position_id = $1),
                  migrated_at = NOW()
            WHERE position_id = $1 AND outcome LIKE 'PENDING_CAPABILITY%'""",
        position_id)


@router.post("/v2/positions/{position_id}/legs")
async def add_position_leg(position_id: str, req: LegRequest, _=Depends(require_api_key)):
    """Enter one leg of a structure by hand.

    This is the capability the three- and four-leg rows have been waiting on: a structure whose
    shape exceeded two strike columns could not be recorded at all, so it was left unmigrated
    rather than published as a smaller position than it is.

    A leg is appended, never renumbered: `leg_seq` is the order legs were entered, and reusing
    a sequence number would silently rewrite a different leg than the caller named.
    """
    ot, sd = _leg_values(req.option_type, req.side)
    if req.qty == 0:
        raise HTTPException(status_code=400, detail="qty must be non-zero")
    try:
        exp = date.fromisoformat(str(req.expiry)[:10])
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"expiry must be a date; got '{req.expiry}'")
    leg_source = _leg_source(req.source)          # R-IV.463(e): refused before anything is read

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        pos = await conn.fetchrow(
            "SELECT position_id, ticker, asset_type FROM unified_positions "
            "WHERE position_id = $1", position_id)
        if not pos:
            raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
        if (pos["asset_type"] or "").upper() not in ("OPTION", "SPREAD"):
            raise HTTPException(
                status_code=400,
                detail=f"{position_id} is {pos['asset_type']}; legs belong to option structures")
        if req.broker_ref:
            dup = await conn.fetchval(
                "SELECT position_id FROM position_legs WHERE broker_ref = $1", req.broker_ref)
            if dup:
                raise HTTPException(status_code=409,
                                    detail=f"broker_ref {req.broker_ref} is already on {dup}")

        async with conn.transaction():
            seq = await conn.fetchval(
                "SELECT COALESCE(MAX(leg_seq), 0) + 1 FROM position_legs WHERE position_id = $1",
                position_id)
            leg_id = await conn.fetchval(
                """INSERT INTO position_legs
                       (position_id, leg_seq, option_type, side, strike, expiry, qty, price,
                        provenance, broker_ref, migrated_from)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                   RETURNING id""",
                position_id, seq, ot, sd, req.strike, exp, req.qty, req.price,
                provenance_for_lot(leg_source, req.price), req.broker_ref,
                "hand-entered" if leg_source == "MANUAL" else "broker-export")
            after = {"leg_seq": seq, "option_type": ot, "side": sd, "strike": req.strike,
                     "expiry": str(exp), "qty": req.qty, "price": req.price}
            await _audit_leg(conn, position_id, pos["ticker"], "LEG_ADD", f"leg:{seq}",
                             None, after, req.actor, req.reason)
            await _settle_pending_capability(conn, position_id)

        legs = await conn.fetch(
            "SELECT id, leg_seq, option_type, side, strike, expiry, qty, price, provenance, "
            "broker_ref FROM position_legs WHERE position_id = $1 ORDER BY leg_seq", position_id)
    return {"status": "leg_added", "position_id": position_id, "leg_id": leg_id, "leg_seq": seq,
            "legs": [dict(r) for r in legs], "count": len(legs)}


@router.patch("/v2/positions/{position_id}/legs/{leg_seq}")
async def update_position_leg(position_id: str, leg_seq: int, req: LegPatchRequest,
                              _=Depends(require_api_key)):
    """Correct one leg, with the trail on the position's own timeline.

    Every change records the field, what it was, what it became, who did it and why. A leg
    entered wrong is corrected here rather than deleted and re-added, because a delete and an
    add are two events and a correction is one.
    """
    changes = {f: getattr(req, f) for f in _LEG_FIELDS if getattr(req, f) is not None}
    relabel = _leg_source(req.source) if req.source is not None else None   # R-IV.463(e)
    if not changes and relabel is None:
        raise HTTPException(status_code=400, detail="no fields to update")
    if "option_type" in changes or "side" in changes:
        ot, sd = _leg_values(changes.get("option_type", "CALL"), changes.get("side", "LONG"))
        if "option_type" in changes:
            changes["option_type"] = ot
        if "side" in changes:
            changes["side"] = sd
    if "expiry" in changes:
        try:
            changes["expiry"] = date.fromisoformat(str(changes["expiry"])[:10])
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="expiry must be a date")

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        leg = await conn.fetchrow(
            "SELECT l.*, p.ticker FROM position_legs l "
            "JOIN unified_positions p ON p.position_id = l.position_id "
            "WHERE l.position_id = $1 AND l.leg_seq = $2", position_id, leg_seq)
        if not leg:
            raise HTTPException(status_code=404,
                                detail=f"leg {leg_seq} not found on {position_id}")
        async with conn.transaction():
            for field, value in changes.items():
                before, after = leg[field], value
                if str(before) == str(after):
                    continue
                await conn.execute(
                    f"UPDATE position_legs SET {field} = $1 WHERE id = $2", value, leg["id"])
                await _audit_leg(conn, position_id, leg["ticker"], "LEG_EDIT",
                                 f"leg:{leg_seq}:{field}",
                                 {"value": str(before)}, {"value": str(after)},
                                 req.actor, req.reason)
            # A price arriving makes the leg's provenance a reported one -- or an imported one,
            # when the edit says it was read from a broker record (R-IV.463(e)); it never makes
            # it verified, which needs a broker record matched and is not what an edit is. A
            # source relabel alone never un-verifies a verified leg.
            if "price" in changes or (relabel is not None
                                      and not is_verified(leg["provenance"])):
                new_prov = provenance_for_lot(relabel or "MANUAL",
                                              changes.get("price", leg["price"]))
                if new_prov != leg["provenance"]:
                    await conn.execute(
                        "UPDATE position_legs SET provenance = $1 WHERE id = $2",
                        new_prov, leg["id"])
                    await _audit_leg(conn, position_id, leg["ticker"], "LEG_EDIT",
                                     f"leg:{leg_seq}:provenance",
                                     {"value": str(leg["provenance"])}, {"value": new_prov},
                                     req.actor, req.reason)
                    changes["provenance"] = new_prov

        legs = await conn.fetch(
            "SELECT id, leg_seq, option_type, side, strike, expiry, qty, price, provenance, "
            "broker_ref FROM position_legs WHERE position_id = $1 ORDER BY leg_seq", position_id)
    return {"status": "leg_updated", "position_id": position_id, "leg_seq": leg_seq,
            "changed": sorted(changes), "legs": [dict(r) for r in legs]}


@router.delete("/v2/positions/{position_id}/legs/{leg_seq}")
async def delete_position_leg(position_id: str, leg_seq: int, reason: str = Query(...),
                              actor: Optional[str] = Query(None),
                              _=Depends(require_api_key)):
    """Remove a leg entered in error. `reason` is required — a structure losing a leg with no
    stated cause is indistinguishable from a structure that never had it."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        leg = await conn.fetchrow(
            "SELECT l.*, p.ticker FROM position_legs l "
            "JOIN unified_positions p ON p.position_id = l.position_id "
            "WHERE l.position_id = $1 AND l.leg_seq = $2", position_id, leg_seq)
        if not leg:
            raise HTTPException(status_code=404,
                                detail=f"leg {leg_seq} not found on {position_id}")
        async with conn.transaction():
            await conn.execute("DELETE FROM position_legs WHERE id = $1", leg["id"])
            await _audit_leg(conn, position_id, leg["ticker"], "LEG_DELETE", f"leg:{leg_seq}",
                             {"option_type": leg["option_type"], "side": leg["side"],
                              "strike": str(leg["strike"]), "expiry": str(leg["expiry"]),
                              "qty": str(leg["qty"])}, None, actor, reason)
    return {"status": "leg_deleted", "position_id": position_id, "leg_seq": leg_seq}


@router.get("/v2/positions/legs/coverage", dependencies=[Depends(require_api_key)])
async def get_legs_coverage(limit: int = Query(100, ge=0, le=500)):
    """What became of every option row when legs were expanded (R-IV.444(b)).

    The migrated rows are the boring half. This surface exists for the other half: each row
    that could NOT become legs, with the reason, because a row quietly left behind renders as
    a position whose structure the screen will silently mis-state.
    """
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        by_outcome = await conn.fetch(
            "SELECT outcome, COUNT(*) AS positions, SUM(legs_written) AS legs "
            "FROM position_legs_migration GROUP BY outcome ORDER BY outcome")
        unmigrated = await conn.fetch(
            """SELECT m.position_id, p.ticker, p.status, p.structure, m.outcome, m.detail,
                      m.merged_into
                 FROM position_legs_migration m
                 JOIN unified_positions p ON p.position_id = m.position_id
                WHERE m.outcome <> 'MIGRATED'
                ORDER BY m.outcome, m.position_id LIMIT $1""", limit)
        pending = await conn.fetchval(
            """SELECT COUNT(*) FROM unified_positions p
                WHERE p.asset_type IN ('OPTION', 'SPREAD')
                  AND NOT EXISTS (SELECT 1 FROM position_legs_migration m
                                   WHERE m.position_id = p.position_id)""")
    return {
        "by_outcome": {r["outcome"]: {"positions": r["positions"], "legs": r["legs"]}
                       for r in by_outcome},
        # An option row with no outcome at all is the one population this table cannot explain,
        # so it is counted separately rather than folded into a total that looks complete.
        "option_rows_without_an_outcome": pending,
        "not_migrated": [dict(r) for r in unmigrated],
        "not_migrated_truncated": len(unmigrated) == limit,
    }


@router.get("/v2/positions/{position_id}/legs", dependencies=[Depends(require_api_key)])
async def get_position_legs(position_id: str):
    """What this position actually holds, one row per leg.

    A position whose legs live on another row says so through `merged_into` rather than
    rendering as an empty structure.
    """
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        legs = await conn.fetch(
            "SELECT id, leg_seq, option_type, side, strike, expiry, qty, price, provenance, "
            "broker_ref, migrated_from FROM position_legs WHERE position_id = $1 "
            "ORDER BY leg_seq", position_id)
        rec = await conn.fetchrow(
            "SELECT outcome, detail, legs_written, merged_into, migrated_at "
            "FROM position_legs_migration WHERE position_id = $1", position_id)
    return {"position_id": position_id, "legs": [dict(r) for r in legs], "count": len(legs),
            "migration": dict(rec) if rec else None}


@router.get("/v2/positions/{position_id}/lots", dependencies=[Depends(require_api_key)])
async def get_position_lots(position_id: str):
    """Lot breakdown behind a position's basis, with each lot's provenance."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, fill_time, qty, price, fees, source, provenance, broker_ref, "
            "created_at FROM position_lots WHERE position_id = $1 ORDER BY fill_time, id",
            position_id)
        pos = await conn.fetchrow(
            "SELECT asset_type, quantity FROM unified_positions WHERE position_id = $1",
            position_id)
    agg = derive_aggregate([dict(r) for r in rows], pos["asset_type"] if pos else None)
    return {"position_id": position_id, "lots": [dict(r) for r in rows], "count": len(rows),
            "derived": agg,
            # The stored quantity beside the one the lots imply. Where they disagree the row is
            # an aggregate that has drifted from its own fills, and saying so here is the
            # difference between a screen that shows a number and one that shows a claim.
            "stored_quantity": pos["quantity"] if pos else None,
            "agrees_with_stored": (pos is not None and pos["quantity"] is not None
                                   and float(pos["quantity"]) == agg["qty"])}


class CashEventRequest(BaseModel):
    account: str
    direction: str            # DEPOSIT | WITHDRAWAL
    amount: float             # positive; direction carries the sign
    event_date: str
    description: Optional[str] = None


# Kept as a name for the phase-2 contract test; the vocabulary itself now lives in
# models/accounts.py so that every write path reads the same one (R-IV.445(a)).
_CANONICAL_ACCOUNTS = set(CANONICAL_ACCOUNTS)


class CashAdjustmentRequest(BaseModel):
    """A correction to the hub's own cash snapshot. Not money moving (R-IV.456(b))."""
    account: str
    amount: float                 # signed: +16.00 restores a 16.00 debit
    reason: str
    ruling: str                   # the ruling that authorises this correction, e.g. "R-IV.456(b)"
    actor: Optional[str] = None


@router.post("/v2/cash-adjustments")
async def record_cash_adjustment(req: CashAdjustmentRequest, _=Depends(require_api_key)):
    """Correct the cash SNAPSHOT when the hub itself moved it wrongly. Labelled, never disguised.

    Not a deposit: /v2/cash-events records money crossing the account boundary, and every
    return figure reads it as such. Not raw SQL: that leaves no reason and no author. This writes
    the snapshot and a `cash_adjustments` row in one transaction -- amount, balance before and
    after, reason, the ruling that authorised it, and who ran it.

    Both the reason and the ruling are REQUIRED. A correction to money with no stated cause and
    no authority behind it is indistinguishable from the error it claims to repair.
    """
    acct = canonical_account(req.account)
    if not req.reason.strip():
        raise HTTPException(status_code=400, detail="reason is required")
    if not req.ruling.strip():
        raise HTTPException(status_code=400,
                            detail="ruling is required — a correction to cash cites what "
                                   "authorised it")
    if req.amount == 0:
        raise HTTPException(status_code=400, detail="amount must be non-zero")
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT account_name, cash FROM account_balances WHERE account_name = $1 "
                "FOR UPDATE", acct)
            if not row:
                raise HTTPException(status_code=404,
                                    detail=f"no account_balances row for {acct}")
            before = float(row["cash"] or 0)
            after = round(before + float(req.amount), 2)
            from services.cash_ledger import stored_cash_is_retired

            # R-IV.551(b): the adjustment is still RECORDED below -- it is evidence
            # either way -- but on an anchored account it no longer moves a total
            # that nothing reads.
            _retired = await stored_cash_is_retired(conn, acct)
            if not _retired:
                await conn.execute(
                    "UPDATE account_balances SET cash = $1, updated_at = NOW(), "
                    "updated_by = $2 WHERE account_name = $3",
                    after, f"adjustment ({req.ruling})", acct)
            else:
                after = before
            adj_id = await conn.fetchval(
                """INSERT INTO cash_adjustments
                       (account, amount, cash_before, cash_after, reason, ruling, actor)
                   VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
                acct, float(req.amount), before, after, req.reason, req.ruling,
                req.actor or "lifecycle-ui")
    logger.info("Cash ADJUSTMENT %s %+.2f (%s -> %s) per %s: %s",
                acct, req.amount, before, after, req.ruling, req.reason)
    return {"status": "adjusted", "id": adj_id, "account": acct, "amount": req.amount,
            "cash_before": before, "cash_after": after, "ruling": req.ruling,
            "not_a_deposit": True}


@router.post("/v2/cash-events")
async def record_cash_event(req: CashEventRequest, _=Depends(require_api_key)):
    """Record a deposit or withdrawal and adjust that account's cash snapshot.

    Touches NO position row and NO realized field — this is the contract Phase 4's
    insulation test is written against. DEF-CASH-EVENTS-UNTRACKED's remedy: cash flows
    have had no write path from the UI, so deposits and withdrawals never entered the
    system and every return computed against account value was unverifiable.
    """
    acct = canonical_account(req.account)
    direction = req.direction.strip().upper()
    if direction not in ("DEPOSIT", "WITHDRAWAL"):
        raise HTTPException(status_code=400, detail="direction must be DEPOSIT or WITHDRAWAL")
    if req.amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="amount must be positive; direction carries the sign. A negative amount "
                   "with direction=WITHDRAWAL would double-negate.")

    signed = req.amount if direction == "DEPOSIT" else -req.amount
    desc = req.description or direction.title()
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # occurrence is part of the dedup key (Phase-1 D4): two genuine same-day,
            # same-amount, same-description events are distinct, not a duplicate.
            occ = await conn.fetchval(
                """SELECT COALESCE(MAX(occurrence), 0) + 1 FROM cash_flows
                   WHERE account_name = $1 AND flow_type = $2 AND amount = $3
                     AND description = $4 AND activity_date = $5::date
                     AND imported_from = 'MANUAL_UI'""",
                acct, direction, signed, desc, req.event_date)
            row = await conn.fetchrow(
                """INSERT INTO cash_flows
                       (account_name, flow_type, amount, description, activity_date,
                        imported_from, occurrence)
                   VALUES ($1, $2, $3, $4, $5::date, 'MANUAL_UI', $6)
                   RETURNING id, occurrence""",
                acct, direction, signed, desc, req.event_date, occ)
            from services.cash_ledger import stored_cash_is_retired

            bal = None
            if not await stored_cash_is_retired(conn, acct):
                bal = await conn.fetchrow(
                    """UPDATE account_balances
                       SET cash = COALESCE(cash, 0) + $1, updated_at = NOW(),
                           updated_by = 'lifecycle-ui'
                       WHERE account_name = $2
                       RETURNING account_name, cash, balance""", signed, acct)

    if not bal:
        # The cash_flow is recorded; the snapshot simply has no row for this account.
        # Reported, not silently swallowed — a missing snapshot is a finding.
        return {"status": "recorded_no_snapshot", "cash_flow_id": row["id"],
                "occurrence": row["occurrence"], "amount": signed,
                "warning": f"no account_balances row for {acct}; cash snapshot not adjusted"}
    return {"status": "recorded", "cash_flow_id": row["id"], "occurrence": row["occurrence"],
            "account": acct, "direction": direction, "amount": signed,
            "cash_after": float(bal["cash"]), "balance_unchanged": float(bal["balance"])}
