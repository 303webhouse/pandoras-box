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

@router.get("/balances", dependencies=[Depends(require_api_key)])
async def get_balances():
    pool = await get_postgres_client()
    rows = await pool.fetch("""
        SELECT account_name, broker, balance, cash, buying_power, margin_total, updated_at, updated_by
        FROM account_balances
        ORDER BY CASE broker WHEN 'robinhood' THEN 0 ELSE 1 END, account_name
    """)
    # R-IV.439(a)/440(a) — the canonical scope travels WITH the row, so no consumer has to
    # keep its own list of which accounts are tradeable. Same vocabulary the MCP tool uses
    # (hub_mcp/tools/portfolio_balances.py, T4): config.accounts is the one source.
    # Additive: `account_name`/`balance` are unchanged, so existing readers are unaffected.
    from config.accounts import is_in_scope, normalize_account

    out = []
    for r in rows:
        d = _row_to_dict(r)
        d["scope"] = normalize_account(d.get("account_name"))
        d["in_scope"] = is_in_scope(d.get("account_name"))
        out.append(d)
    return out


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
    qty = float(d.get("quantity") or 0)   # R-IV.458(b): NUMERIC
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


@router.get("/positions", dependencies=[Depends(require_api_key)])
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

@router.get("/positions/closed", dependencies=[Depends(require_api_key)])
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

@router.get("/trade-history", dependencies=[Depends(require_api_key)])
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

@router.get("/trade-history/stats", dependencies=[Depends(require_api_key)])
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


@router.get("/pnl", dependencies=[Depends(require_api_key)])
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
        """Total balance from the latest snapshot on or before target_date,
        restricted to CURRENTLY-ACTIVE accounts.

        DEF-DAYPNL-PHANTOM: without the active-account filter this summed every
        account that has ever HELD a snapshot, while current_total above sums
        only the accounts that still exist. The 2026-07-23 reconciliation merged
        Fidelity 401A ($11,075.62) and Fidelity 403B ($566.73) into
        BROKERAGE_LINK_401K ($11,642.35 — exactly their sum) and removed the
        originals from account_balances. balance_snapshots still holds them, so
        the merged money was counted once on the current side and again,
        unmerged, on the historical side. The board reported a fixed
        -$11,642.35 / -35.32% on daily, weekly AND monthly, every day since the
        reconciliation. The "loss" was the consolidation itself.

        The subquery is deliberately against account_balances rather than a
        hardcoded list: accounts are merged and retired over time, and this must
        stay correct the next time that happens.
        """
        rows = await pool.fetch("""
            SELECT DISTINCT ON (account_name) account_name, balance
            FROM balance_snapshots
            WHERE snapshot_date <= $1
              AND account_name IN (SELECT account_name FROM account_balances)
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


@router.get("/cash-flows", dependencies=[Depends(require_api_key)])
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


# ── 10. The cash anchor, and a balance derived from it (R-IV.542(b)) ──
#
# MONEY INTEGRITY'S STARTING POINT. `account_balances.cash` is a stored running
# total six writers mutate in place; a balance derived from an audited anchor plus
# the events after it can be reconstructed by anyone holding the same rows. These
# two routes are that path: one writes the anchor, one reads what it implies.
#
# THE ANCHOR IS EVIDENCE, NOT A NUMBER. Both `evidence_ref` and `ruling` are
# REQUIRED. An opening balance with no statement behind it and no authority for it
# is a guess wearing a timestamp, and it would be indistinguishable from the stored
# total it exists to replace.
#
# Convention #32: `evidence_ref` is the hash of the file AS RECEIVED, on its raw
# bytes. Nothing normalises a broker export before hashing it.

def _iso_instant(value: str) -> datetime:
    """Parse an ISO INSTANT, and refuse a bare date.

    `datetime.fromisoformat("2026-09-24")` succeeds and hands back midnight, which
    would silently anchor the account at 00:00 — and every event that same day would
    then count as after it, including the ones already inside the broker's figure.
    That is a double-count the caller never asked for. An anchor is a moment; the
    events are dated; the distinction is the whole reason the reader flags same-day
    rows at all.
    """
    s = (value or "").strip()
    try:
        parsed = datetime.fromisoformat(s)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400,
                            detail="as_of must be an ISO instant, e.g. "
                                   "2026-09-24T11:09:00-04:00")
    if "T" not in s and " " not in s:
        raise HTTPException(status_code=400,
                            detail="as_of must be an ISO instant with a time, not a "
                                   "bare date - an anchor is a moment, and a date "
                                   "alone would place that day's events after it")
    return parsed


class CashAnchorCreate(BaseModel):
    account_name: str
    cash: float                      # the account's cash on the statement
    as_of: str                       # ISO instant the statement was taken
    evidence_ref: str                # raw-bytes hash of the source file (#32)
    ruling: str                      # what authorised this anchor
    evidence_note: Optional[str] = None
    actor: Optional[str] = None


@router.post("/cash-anchor")
async def write_cash_anchor(body: CashAnchorCreate, _=Depends(require_api_key)):
    """Write an OPENING_BALANCE event. Idempotent; touches no stored balance.

    Deliberately does NOT update `account_balances`. The anchor's whole purpose is
    to make the balance derivable without that row, and writing both would leave two
    figures free to disagree.
    """
    from services.cash_ledger import ANCHOR, dedup_key

    if not (body.evidence_ref or "").strip():
        raise HTTPException(status_code=400,
                            detail="evidence_ref is required - an anchor with no source "
                                   "is a guess with a timestamp (convention #32: hash "
                                   "the file as received, raw bytes)")
    if not (body.ruling or "").strip():
        raise HTTPException(status_code=400,
                            detail="ruling is required - an opening balance cites what "
                                   "authorised it")
    as_of = _iso_instant(body.as_of)

    acct = body.account_name
    day = as_of.date()
    ref = body.evidence_ref.strip()
    key = dedup_key(acct, ANCHOR, body.cash, day, ref)
    desc = "OPENING BALANCE as of %s | evidence %s | %s%s" % (
        as_of.isoformat(), ref, body.ruling.strip(),
        (" | " + body.evidence_note.strip()) if body.evidence_note else "")

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO cash_flows
                   (account_name, flow_type, amount, description, activity_date,
                    imported_from, source_ref, dedup_key)
               VALUES ($1, $2, $3, $4, $5::date, 'ANCHOR', $6, $7)
               ON CONFLICT (account_name, dedup_key) WHERE dedup_key IS NOT NULL
               DO NOTHING
               RETURNING id""",
            acct, ANCHOR, body.cash, desc, day, ref, key)
        created = row is not None
        if not created:
            row = await conn.fetchrow(
                "SELECT id FROM cash_flows WHERE account_name = $1 AND dedup_key = $2",
                acct, key)

    derived = await _derived_balance(acct)
    return {
        "status": "anchored" if created else "already_anchored",
        "cash_flow_id": row["id"] if row else None,
        "account_name": acct,
        "opening_balance": body.cash,
        "as_of": as_of.isoformat(),
        "evidence_ref": ref,
        "ruling": body.ruling.strip(),
        "actor": body.actor or "unstated",
        "stored_balance_untouched": True,
        **derived,
    }


async def _derived_balance(account_name: str) -> dict:
    """The ledger's answer for one account, reconciled against the stored figure."""
    from services.cash_ledger import balance_from_events, performance_inputs, reconcile

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        events = await conn.fetch(
            """SELECT id, account_name, flow_type, amount, activity_date,
                      imported_from, source_ref, description
                 FROM cash_flows WHERE account_name = $1
                ORDER BY activity_date, id""",
            account_name)
        stored = await conn.fetchval(
            "SELECT cash FROM account_balances WHERE account_name = $1", account_name)
    evs = [dict(e) for e in events]
    derived = balance_from_events(evs)
    return {
        "derived": derived,
        "reconciliation": reconcile(derived, stored),
        "flow": performance_inputs(evs),
        "event_count": len(evs),
    }


@router.get("/cash-balance", dependencies=[Depends(require_api_key)])
async def get_cash_balance(account_name: Optional[str] = Query(None)):
    """The balance the ledger derives, per account, with the stored one beside it.

    Both figures, always, and the difference between them. The stored total cannot
    be reconstructed; the derived one is only as complete as the events written
    down. Publishing one without the other would hide which.
    """
    pool = await get_postgres_client()
    if account_name:
        names = [account_name]
    else:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT account_name FROM account_balances
                   UNION SELECT DISTINCT account_name FROM cash_flows
                   ORDER BY 1""")
        names = [r["account_name"] for r in rows]
    return {"accounts": {n: await _derived_balance(n) for n in names}}


# ── 11. The principal's own two inputs (R-IV.546(a)) ──
#
# The workflow these serve: the hub tracks cash from the trades he enters, he adds
# deposits and withdrawals himself, and when the broker shows a different figure he
# re-anchors. The difference at that moment is the signal for the periodic CSV
# cleanup, so it is RETURNED and never silently absorbed.
#
# Both accept the session cookie as well as X-API-Key, because he types them on the
# page. A session-authed mutation must also carry `X-Requested-With: XMLHttpRequest`
# -- that is `require_api_key`'s CSRF rule, not a new one, and the form must send it.
#
# IDEMPOTENT ON A KEY THE FORM SENDS. A double-click must not book two deposits, and
# the client is the only party that knows the two clicks were one intent: retrying
# after a timeout looks identical to the server otherwise.

_ENTRY_KINDS = {
    "DEPOSIT": ("TRANSFER_IN", 1),      # must be positive
    "WITHDRAWAL": ("TRANSFER_OUT", -1),  # must be negative
    "OTHER": ("OTHER", 0),              # either sign, but not zero
}


class CashEntryCreate(BaseModel):
    account_name: str
    kind: str                            # DEPOSIT | WITHDRAWAL | OTHER
    amount: float                        # SIGNED: + into the account, - out of it
    event_date: str                      # ISO date the money actually moved
    idempotency_key: str                 # the form's, so a double-click collides
    note: Optional[str] = None


@router.post("/cash-entry")
async def record_principal_cash_entry(body: CashEntryCreate, _=Depends(require_api_key)):
    """The principal's own deposit / withdrawal / other. Idempotent on the form's key."""
    from services.cash_ledger import dedup_key

    kind = (body.kind or "").strip().upper()
    if kind not in _ENTRY_KINDS:
        raise HTTPException(status_code=400,
                            detail="kind must be DEPOSIT, WITHDRAWAL or OTHER")
    key_raw = (body.idempotency_key or "").strip()
    if not key_raw:
        raise HTTPException(status_code=400,
                            detail="idempotency_key is required - without one a "
                                   "double-click books the deposit twice")
    if body.amount == 0:
        raise HTTPException(status_code=400, detail="amount must be non-zero")

    ledger_type, want_sign = _ENTRY_KINDS[kind]
    # The SIGN is authoritative and the kind must agree with it. A DEPOSIT of -88.15
    # is not a withdrawal politely mislabelled: it is two statements that contradict
    # each other, and guessing which the principal meant is how money goes missing
    # in the direction nobody checks.
    if want_sign > 0 and body.amount < 0:
        raise HTTPException(status_code=400,
                            detail="a DEPOSIT is positive; use WITHDRAWAL for money "
                                   "leaving the account")
    if want_sign < 0 and body.amount > 0:
        raise HTTPException(status_code=400,
                            detail="a WITHDRAWAL is negative; use DEPOSIT for money "
                                   "entering the account")
    try:
        when = date.fromisoformat(body.event_date[:10])
    except (TypeError, ValueError, IndexError):
        raise HTTPException(status_code=400,
                            detail="event_date must be an ISO date, e.g. 2026-09-24")

    acct = body.account_name
    # Scoped to the account and to the key alone: the same key MUST collide even if
    # the payload differs, because that is a resubmission, not a second movement.
    key = dedup_key(acct, "PRINCIPAL_ENTRY", 0, "", key_raw)
    desc = "%s by principal%s | key %s" % (
        kind, (" | " + body.note.strip()) if body.note else "", key_raw)

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO cash_flows
                   (account_name, flow_type, amount, description, activity_date,
                    imported_from, source_ref, dedup_key)
               VALUES ($1, $2, $3, $4, $5::date, 'PRINCIPAL_UI', $6, $7)
               ON CONFLICT (account_name, dedup_key) WHERE dedup_key IS NOT NULL
               DO NOTHING
               RETURNING id, flow_type, amount, activity_date""",
            acct, ledger_type, body.amount, desc, when, key_raw, key)
        created = row is not None
        if not created:
            row = await conn.fetchrow(
                """SELECT id, flow_type, amount, activity_date FROM cash_flows
                    WHERE account_name = $1 AND dedup_key = $2""", acct, key)

    conflict = None
    if not created and row is not None:
        # The key came back, so this is a resubmission. If it carries a DIFFERENT
        # movement the first one stands and the difference is REPORTED -- silently
        # accepting would double the money, silently dropping would hide an edit.
        differs = {}
        if float(row["amount"]) != float(body.amount):
            differs["amount"] = {"recorded": float(row["amount"]), "sent": body.amount}
        if row["activity_date"] != when:
            differs["event_date"] = {"recorded": row["activity_date"].isoformat(),
                                     "sent": when.isoformat()}
        if row["flow_type"] != ledger_type:
            differs["kind"] = {"recorded": row["flow_type"], "sent": ledger_type}
        conflict = differs or None

    derived = await _derived_balance(acct)
    return {
        "status": "recorded" if created else "already_recorded",
        "cash_flow_id": row["id"] if row else None,
        "account_name": acct, "kind": kind, "ledger_type": ledger_type,
        "amount": body.amount, "event_date": when.isoformat(),
        "actor": "principal", "idempotency_key": key_raw,
        "conflict": conflict,
        "conflict_note": None if not conflict else
            "this key already recorded a different movement; the first one stands "
            "and nothing was changed - send a new idempotency_key to book another",
        **derived,
    }


class CashReanchorCreate(BaseModel):
    account_name: str
    cash: float                          # what the broker shows right now
    idempotency_key: str
    as_of: Optional[str] = None          # ISO instant; defaults to now
    note: Optional[str] = None


@router.post("/cash-reanchor")
async def principal_reanchor(body: CashReanchorCreate, _=Depends(require_api_key)):
    """"Set cash to what my broker shows now." Returns the difference it revealed.

    THE DIFFERENCE IS THE PRODUCT. It is what the periodic CSV cleanup goes looking
    for: the gap between what the hub derived from its own events and what the broker
    actually holds. Absorbing it silently would make a re-anchor a way of hiding
    exactly the drift it exists to surface.
    """
    from services.cash_ledger import ANCHOR, dedup_key

    key_raw = (body.idempotency_key or "").strip()
    if not key_raw:
        raise HTTPException(status_code=400,
                            detail="idempotency_key is required - without one a "
                                   "double-click writes two anchors")
    as_of = _iso_instant(body.as_of) if body.as_of else datetime.now().astimezone()

    acct = body.account_name
    # What the hub believed BEFORE this anchor. Read first: afterwards the new anchor
    # is the opening balance and the old answer is unrecoverable.
    before = await _derived_balance(acct)
    derived_before = before["derived"]["balance"]

    # The evidence IS the principal's entry and its instant (R-IV.546(a)2). There is
    # no file here, so the reference says so plainly rather than borrowing the shape
    # of a hash it does not have.
    ref = "principal-entry@%s" % as_of.isoformat()
    key = dedup_key(acct, ANCHOR, 0, "", key_raw)
    desc = "OPENING BALANCE as of %s | evidence %s | R-IV.546(a)2 principal re-anchor%s" % (
        as_of.isoformat(), ref, (" | " + body.note.strip()) if body.note else "")

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO cash_flows
                   (account_name, flow_type, amount, description, activity_date,
                    imported_from, source_ref, dedup_key)
               VALUES ($1, $2, $3, $4, $5::date, 'PRINCIPAL_ANCHOR', $6, $7)
               ON CONFLICT (account_name, dedup_key) WHERE dedup_key IS NOT NULL
               DO NOTHING
               RETURNING id""",
            acct, ANCHOR, body.cash, desc, as_of.date(), ref, key)
        created = row is not None
        if not created:
            row = await conn.fetchrow(
                "SELECT id FROM cash_flows WHERE account_name = $1 AND dedup_key = $2",
                acct, key)

    if derived_before is None:
        difference = None
        note = ("the hub could not derive a balance before this anchor, so there is "
                "no difference to report - this is a first anchor, not a correction")
    else:
        difference = round(float(body.cash) - float(derived_before), 2)
        note = ("the hub derived %.2f and the broker shows %.2f; this gap is what the "
                "CSV cleanup should account for" % (derived_before, body.cash)
                if difference else "the hub and the broker already agreed")

    after = await _derived_balance(acct)
    return {
        "status": "reanchored" if created else "already_reanchored",
        "cash_flow_id": row["id"] if row else None,
        "account_name": acct,
        "entered": body.cash,
        "derived_before": derived_before,
        "difference": difference,
        "difference_note": note,
        "as_of": as_of.isoformat(),
        "evidence_ref": ref,
        "actor": "principal",
        "idempotency_key": key_raw,
        "stored_balance_untouched": True,
        **after,
    }
