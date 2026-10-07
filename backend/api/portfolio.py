"""
Portfolio API — Account balances, open positions, and trade history.

Brief 07-B: Powers the frontend dashboard and Pivot's screenshot-based sync.
Brief 10: Gap fixes — signal_id/account columns, partial sync, single create,
          closed_positions table with proper P&L, rewritten close endpoint.
"""

import json
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
        elif isinstance(v, datetime):
            # RV1 (R-IV.566(e)1): through the one helper, so a naive value carries
            # its UTC offset. A bare isoformat() emits none, and the page reads an
            # offset-less string as LOCAL -- six hours late in Mountain Time.
            from database.postgres_client import iso_utc

            d[k] = iso_utc(v)
        elif isinstance(v, date):
            d[k] = v.isoformat()
    return d


# ── 1. GET /balances ──

async def _underlying_price(ticker: str):
    """The underlying's current price, or None — R-IV.657(d).

    TWO SOURCES, IN THIS ORDER, AND THE KEY MATTERS. `get_quote` returns the spot under
    `spot`, not `price`; reading the wrong key returns None for every ticker and the
    intrinsic silently never computes. Measured: XLF's quote came back
    `{"spot": null, "status": "unavailable"}` with the market closed, so the UW leg alone
    cannot carry this.

    The fallback is the yfinance daily close on the PRICE-RETURN basis
    (`auto_adjust=False`), for the same reason Amendment 5 requires it: a strike is a raw
    price, so the price it is compared against must be one too — a dividend-adjusted close
    would shift every intrinsic by the adjustment. It spends no governor budget.

    None when neither answers. An unread underlying is not a worthless option, and the
    caller keeps the row's account PARTIAL rather than publishing a figure.
    """
    try:
        from services.read_only.quote import get_quote

        q = await get_quote(ticker)
        spot = (q or {}).get("spot") if isinstance(q, dict) else None
        if spot is not None and float(spot) > 0:
            return float(spot)
    except Exception:  # noqa: BLE001
        pass

    try:
        from integrations.uw_api import get_bars_yfinance

        bars = await get_bars_yfinance(ticker, auto_adjust=False) or []
        closes = [b.get("c") for b in bars if b.get("c") is not None]
        if closes:
            last = float(closes[-1])
            return last if last > 0 else None
    except Exception:  # noqa: BLE001
        pass
    return None


async def _intrinsic_for_unquoted_options():
    """Every OPEN option row the hub cannot quote, with its intrinsic value — R-IV.657(d).

    One row per unquoted position, each NAMED so the ceiling's face can list it: the ticker,
    the structure, the underlying price used, the figure, and how it was read. A row whose
    underlying is unknown carries `intrinsic: None` and its reason, and the account keeps its
    PARTIAL mark -- an unread underlying is not a worthless option.
    """
    from models.option_intrinsic import intrinsic_value

    pool = await get_postgres_client()
    rows = await pool.fetch(
        """SELECT position_id, account, ticker, structure, direction, quantity,
                  long_strike, short_strike, expiry, legs, mark_status, mark_reason
             FROM unified_positions
            WHERE status = 'OPEN'
              AND UPPER(COALESCE(asset_type, '')) = 'OPTION'
              AND (current_price IS NULL OR current_price <= 0)""")

    out, quotes = [], {}
    for r in rows:
        d = dict(r)
        if d.get("legs") and isinstance(d["legs"], str):
            try:
                d["legs"] = json.loads(d["legs"])
            except (ValueError, TypeError):
                d["legs"] = None
        tkr = (d.get("ticker") or "").upper()
        if tkr and tkr not in quotes:
            quotes[tkr] = await _underlying_price(tkr)
        px = quotes.get(tkr)
        value, basis = intrinsic_value(d, px)
        out.append({
            "position_id": d.get("position_id"), "account": d.get("account"),
            "ticker": tkr, "structure": d.get("structure"),
            "quantity": float(d["quantity"]) if d.get("quantity") is not None else None,
            "underlying_price": px, "intrinsic": value, "basis": basis,
            "why_unquoted": d.get("mark_reason") or d.get("mark_status"),
        })
    return out


@router.get("/sleeve-ceiling", dependencies=[Depends(require_api_key)])
async def get_sleeve_ceiling():
    """The Robinhood sleeve ceiling — R-IV.644(d) / TA-070.

    FIRST READ ENDPOINT FOR IT. The figure lived as prose in the committee parameters and as
    a hardcoded `ceiling: 968` mock in `frontend/v2.js`, whose own note says it has no read
    endpoint. Both written forms name TWO accounts, so a third tracked account silently
    dropped out of the base; this sums over the REGISTRY, so the next one cannot.
    """
    from services.read_only.balances import get_account_balances
    from services.sleeve_ceiling import ceiling_from_balances

    # THE BASE IS EACH ACCOUNT'S VALUE AS THE BALANCES SERVICE SERVES IT — R-IV.647(b).
    #
    # This route read `account_balances.balance` directly, which is the RETIRED stored
    # figure: the Roth's 8,842.09 and Robinhood's 835.69 are numbers typed from a
    # statement, not broker figures (R-IV.642(e)). That is also why the old mock's 968
    # matched my first computation exactly — both read the same two stale numbers, so the
    # agreement proved nothing about either.
    #
    # The service's `balance` is derived: cash from the ledger plus that account's open
    # positions at their marks, through the SAME `account_value` arithmetic the loss
    # alert's threshold uses — so a committee sizing off the ceiling and an alert firing
    # off the threshold cannot disagree about what an account is worth. It is None with a
    # reason when the ledger cannot be read, and `balance_partial` is True when a position
    # in scope has no mark.
    rows = await get_account_balances() or []

    # ── R-IV.657(d): AN UNQUOTED OPTION ROW COUNTS AT ITS INTRINSIC VALUE ──────────────
    #
    # "A limit set slightly low is safe; one that never publishes limits nothing." The
    # ceiling had stopped publishing because Robinhood -- the options sleeve it governs --
    # holds rows the hub cannot quote: there is no options pricer, so `mark_status` reads
    # UNAVAILABLE and the account stays PARTIAL indefinitely. A capability gap, not a delay.
    #
    # Each such row is topped up at what its legs are worth at the underlying's current
    # price, zero out of the money, and NAMED on the face. Intrinsic is a FLOOR -- it
    # omits all time value -- so the base understates in one direction, which is the safe
    # one for a cap.
    intrinsic_rows, intrinsic_by_account = [], {}
    try:
        unvalued = await _intrinsic_for_unquoted_options()
        for item in unvalued:
            intrinsic_rows.append(item)
            if item["intrinsic"] is not None and item["account"]:
                intrinsic_by_account[item["account"]] = (
                    intrinsic_by_account.get(item["account"], 0.0) + item["intrinsic"])
    except Exception as exc:  # noqa: BLE001
        # Loud, and the ceiling falls back to publishing nothing rather than a base that
        # silently omits the top-up it was meant to include.
        logger.error("sleeve ceiling: intrinsic top-up unavailable (%s)", type(exc).__name__)
        intrinsic_rows = [{"error": type(exc).__name__}]

    balances, understated, notes = {}, set(), []
    for r in rows:
        name = r.get("account_name")
        if not name:
            continue
        value = r.get("balance")
        topped = False
        if value is not None and r.get("balance_partial") and name in intrinsic_by_account:
            # Every unvalued row in this account had an intrinsic computed, so the value is
            # no longer partial-with-a-hole: it is complete at a floor.
            holes = len(r.get("balance_positions_unvalued") or [])
            priced = sum(1 for i in intrinsic_rows
                         if i.get("account") == name and i.get("intrinsic") is not None)
            if priced >= holes:
                value = round(float(value) + intrinsic_by_account[name], 2)
                topped = True
        balances[name] = value                     # None stays None: UNKNOWN, not zero
        if value is not None and r.get("balance_partial") and not topped:
            understated.add(name)
        if value is None or (r.get("balance_partial") and not topped):
            notes.append(f"{name}: {r.get('balance_reason') or 'no derived value this cycle'}"
                         + (f" ({len(r.get('balance_positions_unvalued') or [])} unvalued)"
                            if r.get("balance_partial") else ""))

    out = ceiling_from_balances(balances, understated=understated)
    out["intrinsic_rows"] = intrinsic_rows or None
    out["intrinsic_added"] = {k: round(v, 2) for k, v in intrinsic_by_account.items()} or None
    out["base_source"] = ("derived: cash from the ledger plus open positions at their marks "
                          "(R-IV.647(b)) — not account_balances' retired stored total")
    out["base_stored_for_contrast"] = {
        r.get("account_name"): r.get("balance_stored") for r in rows if r.get("account_name")}
    if notes:
        out["partial_detail"] = notes
    return out


@router.get("/balances", dependencies=[Depends(require_api_key)])
async def get_balances():
    """Account balances, THROUGH THE ONE READ SERVICE.

    This route used to run its own query and attach its own derived figures, which
    is how it came to serve the STORED balance (835.69) while the MCP tool served
    the derived one (1,308.99) from the same database in the same minute. Two
    surfaces answering differently about one account is the failure the single
    author exists to prevent, and it had been reintroduced here by a route that
    merely looked like it was doing the same thing.

    `services.read_only.balances` now owns it: derived cash, the derived balance,
    partial where a position cannot be valued, and buying power served as null with
    its reason (R-IV.559(c)).
    """
    from config.accounts import is_in_scope, normalize_account
    from services.read_only.balances import get_account_balances

    rows = await get_account_balances()
    if rows is None:
        raise HTTPException(status_code=503,
                            detail="account balances are unavailable this cycle")
    # R-IV.439(a)/440(a) -- the canonical scope travels WITH the row, so no consumer
    # has to keep its own list of which accounts are tradeable.
    for d in rows:
        d["scope"] = normalize_account(d.get("account_name"))
        d["in_scope"] = is_in_scope(d.get("account_name"))
    return rows


# ── 2. POST /balances/update ──

class BalanceUpdate(BaseModel):
    account_name: str
    balance: float
    cash: Optional[float] = None
    buying_power: Optional[float] = None
    margin_total: Optional[float] = None


@router.post("/balances/update")
async def update_balance(body: BalanceUpdate, _=Depends(require_api_key)):
    from services.cash_ledger import stored_cash_is_retired

    pool = await _pool()
    # R-IV.551(b): an anchored account's stored CASH is read-only history. The rest
    # of the row -- balance, buying power, margin -- is still the screenshot's to
    # set, so only the cash field is dropped, and the response says it was.
    cash_retired = False
    if body.cash is not None:
        async with pool.acquire() as conn:
            cash_retired = await stored_cash_is_retired(conn, body.account_name)
    if cash_retired:
        body.cash = None
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
    out = _row_to_dict(row)
    if cash_retired:
        out["cash_not_applied"] = True
        out["cash_not_applied_reason"] = (
            "this account is anchored, so its stored cash total is read-only history "
            "(R-IV.551(b)). The cash figure served everywhere is derived from the "
            "ledger; to set it to what the broker shows, use "
            "POST /api/portfolio/cash-reanchor, which reports the difference.")
    return out


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
    #
    # R-IV.660(b)3 CENSUS. This multiplied the price by `quantity` -- the size OPENED (#29) --
    # so a partially-closed position was valued at the size it started with. On money, in the
    # direction that overstates. `open_quantity` is what is still held.
    #
    # A row whose remainder is UNKNOWN (no lots) gets current_value None, not a value computed
    # off the opened size: this route's own convention is that an unpriced row reads None, and
    # an unknown SIZE makes a value just as unknowable as an unknown price. Zero open rows are
    # in that state today (measured 2026-10-06, 28 of 28 have lots).
    cp = d.get("current_price")
    qty = d.get("open_quantity")
    qty = float(qty) if qty is not None else None
    multiplier = 1 if is_stock else 100
    current_value = (round(cp * multiplier * qty, 2)
                     if cp is not None and qty is not None else None)

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
        # R-IV.660(b)3: this field has always MEANT the live size to its consumers, and now
        # carries it. The size opened rides along under its own name so nothing is lost.
        "quantity": qty,
        "quantity_opened": d.get("quantity"),
        "open_quantity": qty,
        "open_quantity_basis": d.get("open_quantity_basis"),
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
    # R-IV.660(b)2/3: stamped BEFORE shaping, because the shaper multiplies a price by the
    # size. One lot query for the whole response.
    from services.open_quantity import stamp_open_quantity

    # This module's own serialiser, the one `_v2_to_legacy_dict` already calls -- not a second
    # one imported for the occasion.
    dicts = [_row_to_dict(r) for r in rows]
    await stamp_open_quantity(pool, dicts)
    return [_v2_to_legacy_dict(d) for d in dicts]


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
    # R-IV.548(c): DEFAULT FLIPPED TO NO MUTATION, and `true` no longer mutates
    # either. `account_balances.cash` is a stored running total six writers maintain
    # and nobody can reconstruct; money integrity is replacing it with a figure
    # derived from this very ledger. A route that appends an event AND edits the
    # total keeps the two free to disagree, which is the fault. The field stays so
    # an old caller is answered rather than rejected, and the response says plainly
    # that nothing was adjusted and why.
    adjust_balance: bool = False


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

    if row is None:
        # An INSERT ... RETURNING that returns nothing is not a success with an empty
        # body; it means the row did not land. Said plainly rather than raising a
        # TypeError three lines later on a None the caller never sees.
        raise HTTPException(status_code=500,
                            detail="the cash flow was not written and the database "
                                   "returned no row")
    result = _row_to_dict(row)
    result["balance_adjusted"] = False
    if body.adjust_balance:
        # Answered, not obeyed, and not silently either. Ignoring the flag without
        # saying so would be a different kind of lie from mutating the total.
        result["note"] = (
            "adjust_balance was requested and NOT applied: account_balances.cash is a "
            "stored running total under replacement (R-IV.548(c)). The balance is "
            "derived from this ledger - see GET /api/portfolio/cash-balance - and a "
            "route that both appended an event and edited the total would leave two "
            "figures free to disagree.")
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

    # CURRENT VALUE, DERIVED — R-IV.647(b). This read `account_balances.balance`, whose
    # only writer is the manual POST /balances route, so it had not moved since 09-24 and
    # every P&L window read 0.00 for eleven days.
    from services.read_only.balances import get_account_balances

    _bal_rows = await get_account_balances() or []
    current, current_partial, current_unavailable = {}, set(), {}
    for r in _bal_rows:
        name = r.get("account_name")
        if not name:
            continue
        if r.get("balance") is None:
            current_unavailable[name] = r.get("balance_reason") or "no derived value"
            continue
        current[name] = float(r["balance"])
        if r.get("balance_partial"):
            current_partial.add(name)
    current_total = sum(current.values())

    # Every cash event from the earliest window start, read ONCE. Classified in Python
    # rather than filtered in SQL, because `cash_ledger.normalise_type` is the one author
    # of this vocabulary -- `ACH` is 22 of the rows and means money IN or OUT depending on
    # its sign, which a `flow_type IN (...)` clause cannot know.
    _earliest = min(yesterday, last_friday, first_of_month)
    _flow_rows = await pool.fetch(
        """SELECT account_name, flow_type, amount, activity_date
             FROM cash_flows
            WHERE activity_date > $1""", _earliest)

    def funding_since(after, names):
        """Net non-performance money that entered these accounts after `after`.

        Subtracted from the balance difference so a deposit, a transfer or a correction
        cannot read as a gain. Scoped to the SAME accounts the comparison uses, or an
        account excluded from both balances would still have its funding removed.
        """
        from services.cash_ledger import moves_balance_without_performing

        total = 0.0
        for r in _flow_rows:
            if r["activity_date"] is None or r["activity_date"] <= after:
                continue
            if names is not None and r["account_name"] not in names:
                continue
            if not moves_balance_without_performing(dict(r)):
                continue
            total += float(r["amount"] or 0)
        return round(total, 2)

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
        # LIKE AGAINST LIKE, OR NOTHING — R-IV.647(b). `basis = 'derived'` is required on
        # BOTH sides: the 600 pre-existing rows are stored-basis, and comparing today's
        # derived value against one of them would book the gap between the two bases as a
        # day's gain (+1,129.83 on 2026-10-05). `partial IS NOT TRUE` for the same reason
        # in a smaller key: a value missing a mark understates, and the difference of an
        # understated figure and a complete one is not performance.
        rows = await pool.fetch("""
            SELECT DISTINCT ON (account_name) account_name, balance
            FROM balance_snapshots
            WHERE snapshot_date <= $1
              AND basis = 'derived'
              AND partial IS NOT TRUE
              AND account_name = ANY($2::text[])
            ORDER BY account_name, snapshot_date DESC
        """, target_date, [n for n in current if n not in current_partial])
        if not rows:
            return None, set()
        names = {r["account_name"] for r in rows}
        return sum(float(r["balance"] or 0) for r in rows), names

    daily_snap, daily_names = await get_snapshot_total(yesterday)
    weekly_snap, weekly_names = await get_snapshot_total(last_friday)
    monthly_snap, monthly_names = await get_snapshot_total(first_of_month)

    def calc_pnl(prev_total, prev_names, after):
        """THE MIRROR OF DEF-DAYPNL-PHANTOM — R-IV.638(b)2.

        The filter above handles an account being RETIRED: a name no longer in
        account_balances drops off the historical side, matching the current side.
        ADDING an account breaks it the other way. A new account is in
        account_balances today and has no snapshot before the date it was created,
        so `current_total` carries its balance and `prev_total` cannot. The whole
        balance then reads as one day's profit.

        FIDELITY_401A was registered 2026-10-01 at 0.00, so nothing is wrong today
        -- the error appears the moment the principal enters its real cash, which is
        the next thing he does. Both sides are therefore compared over the SAME set
        of accounts: the ones that have a snapshot at or before the date. An account
        with no history yet is in neither total, which is honest -- there is no prior
        figure to compare it against, and inventing one is the fault either way.

        FUNDING IS NOT PERFORMANCE — R-IV.644(c). This differenced two BALANCES, so
        every deposit, every transfer and every correction to a past entry read as that
        day's profit. `cash_ledger` has said so since R-IV.539(d) -- *"money walking in
        the door is not a gain, and an account value that grew by a deposit has not
        performed"* -- and this computation simply never asked it. With POSITIONS booking
        the 401(a)'s funding and rebuilding the Roth's past entries (R-IV.642), all three
        were about to land at once.

        So the window's non-performance flows are subtracted, and reported beside the
        figure as `funding_excluded` rather than silently applied: a day that reads flat
        after $2,000 walked in is a different fact from a day that was flat.
        """
        if prev_total is None or prev_total == 0:
            return None, None
        comparable = sum(v for k, v in current.items() if k in prev_names)
        funded = funding_since(after, prev_names)
        dollar = round(comparable - prev_total - funded, 2)
        # The denominator carries the funding too: money that arrived mid-window was
        # capital for part of it, and dividing a flow-adjusted gain by the un-adjusted
        # opening balance overstates the percentage on exactly the days funding lands.
        base = prev_total + funded
        pct = round((dollar / base) * 100, 2) if base else None
        return dollar, pct

    daily_dollar, daily_pct = calc_pnl(daily_snap, daily_names, yesterday)
    weekly_dollar, weekly_pct = calc_pnl(weekly_snap, weekly_names, last_friday)
    monthly_dollar, monthly_pct = calc_pnl(monthly_snap, monthly_names, first_of_month)

    return {
        "current_total": current_total,
        # R-IV.647(b): say which basis produced this, and what is missing from it. A
        # figure whose basis a reader cannot see is a figure they cannot check.
        "basis": "derived (cash ledger + open positions at marks)",
        "accounts_counted": sorted(current),
        "accounts_partial": sorted(current_partial) or None,
        "accounts_unavailable": current_unavailable or None,
        "comparison_rule": ("both sides must be derived-basis and complete; an account that "
                            "is partial, unavailable, or has only stored-basis history is "
                            "excluded from BOTH sides rather than compared across bases"),
        "daily": {"dollar": daily_dollar, "pct": daily_pct, "compare_date": yesterday.isoformat(),
                  "funding_excluded": funding_since(yesterday, daily_names)},
        "weekly": {"dollar": weekly_dollar, "pct": weekly_pct, "compare_date": last_friday.isoformat(),
                   "funding_excluded": funding_since(last_friday, weekly_names)},
        "monthly": {"dollar": monthly_dollar, "pct": monthly_pct,
                    "compare_date": first_of_month.isoformat(),
                    "funding_excluded": funding_since(first_of_month, monthly_names)},
    }


async def snapshot_account_balances():
    """Save a daily snapshot of each account's DERIVED value, for P&L — R-IV.647(b).

    IT USED TO SNAPSHOT THE STORED FIGURE, AND THE STORED FIGURE DOES NOT MOVE. The only
    writer of `account_balances.balance` is the manual POST /balances route; nothing
    automatic updates it. Measured 2026-10-05: FIDELITY_ROTH 8,842.09 and ROBINHOOD 835.69
    in EVERY snapshot from 09-24 to 10-05 — eleven identical days. P&L differences two
    snapshots, and the difference of a constant is zero, so **day, weekly and monthly P&L
    had all read 0.00 for eleven days**. Not a quiet book: a frozen input, reported as flat.

    So the snapshot records the value the balances service derives — cash from the ledger
    plus that account's open positions at their marks — and says which BASIS it used and
    whether that value was PARTIAL. Both are needed by the reader: comparing a derived
    endpoint against a stored one would fabricate the whole gap between them as one day's
    gain, which here is +1,129.83.

    The row is written even when partial, because the history is worth keeping; it is the
    P&L's job to refuse a comparison that rests on one.
    """
    import logging

    from services.read_only.balances import get_account_balances

    pool = await get_postgres_client()
    logger = logging.getLogger(__name__)

    try:
        rows = await get_account_balances() or []
        today = date.today()
        written, skipped = 0, []
        for r in rows:
            name = r.get("account_name")
            value = r.get("balance")
            if not name:
                continue
            if value is None:
                # No derived value at all. A row here would be a number standing in for
                # one that does not exist, and the P&L would difference it.
                skipped.append(f"{name}: {r.get('balance_reason') or 'no derived value'}")
                continue
            cash = r.get("balance_cash")
            await pool.execute("""
                INSERT INTO balance_snapshots
                       (snapshot_date, account_name, balance, cash, position_value,
                        basis, partial)
                VALUES ($1, $2, $3, $4, $5, 'derived', $6)
                ON CONFLICT (snapshot_date, account_name)
                DO UPDATE SET balance = $3, cash = $4, position_value = $5,
                              basis = 'derived', partial = $6, created_at = NOW()
            """, today, name, float(value),
                 float(cash) if cash is not None else None,
                 r.get("balance_positions_value"),
                 bool(r.get("balance_partial")))
            written += 1
        logger.info("Balance snapshot (derived basis) saved for %d account(s)", written)
        for why in skipped:
            logger.warning("Balance snapshot SKIPPED — %s", why)
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


async def _pool():
    """The pool, resolved on the MODULE at call time.

    `from database.postgres_client import get_postgres_client` at the top of this
    file binds the real function into this namespace at import time, so a test that
    patches `database.postgres_client.get_postgres_client` never reaches it -- the
    routes below then opened REAL connections from a mocked test run, which showed up
    as "password authentication failed" 500s only when these files ran beside their
    neighbours. Resolving the attribute here, per call, is what makes the patch land.
    """
    from database import postgres_client

    return await postgres_client.get_postgres_client()


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

    pool = await _pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO cash_flows
                   (account_name, flow_type, amount, description, activity_date,
                    imported_from, source_ref, dedup_key, meta)
               VALUES ($1, $2, $3, $4, $5::date, 'ANCHOR', $6, $7, $8::jsonb)
               ON CONFLICT (account_name, dedup_key) WHERE dedup_key IS NOT NULL
               DO NOTHING
               RETURNING id""",
            acct, ANCHOR, body.cash, desc, day, ref, key,
            # R-IV.566(d): the instant as a FIELD, not only inside the sentence. A
            # card that has to parse a log line to print a time is one reworded
            # message away from printing the wrong one.
            json.dumps({"as_of": as_of.isoformat(), "evidence_ref": ref,
                        "kind": "statement", "ruling": body.ruling.strip(),
                        "actor": body.actor or "unstated"}))
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

    pool = await _pool()
    async with pool.acquire() as conn:
        events = await conn.fetch(
            """SELECT id, account_name, flow_type, amount, activity_date,
                      imported_from, source_ref, description, meta
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
    pool = await _pool()
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

    pool = await _pool()
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


# ── 12. The evidence-backed ledger event (R-IV.548(c)) ──
#
# POSITIONS had to write the Roth's six events by audited SQL, because no route took
# a dated event with a source_ref. That is a gap in the path, not in POSITIONS: a
# lane reaching for raw SQL to record money is the signal that the route it needed
# does not exist. This is that route.
#
# It differs from `/cash-entry` in what it is FOR. `/cash-entry` is the principal
# typing a deposit, and its idempotency key comes from the form. This one carries a
# movement read out of a document -- a broker CSV, a confirmation -- so the evidence
# is REQUIRED, the actor is named, and dedup runs on the service's own key over the
# movement itself, which is what makes re-importing the same file safe.

class CashLedgerEventCreate(BaseModel):
    account_name: str
    event_type: str                      # the ledger vocabulary, not ANCHOR
    amount: float                        # SIGNED
    event_date: str                      # ISO date the money moved
    source_ref: str                      # the document this was read out of (#32)
    actor: str                           # who read it
    note: Optional[str] = None
    occurrence: int = 0                  # two identical same-day movements


@router.post("/cash-event")
async def record_evidence_backed_event(body: CashLedgerEventCreate,
                                       _=Depends(require_api_key)):
    """A typed, dated, evidence-backed ledger event. Writes no stored balance."""
    from services.cash_ledger import ALL_TYPES, ANCHOR, dedup_key, normalise_type

    etype = (body.event_type or "").strip().upper()
    if etype == ANCHOR:
        raise HTTPException(status_code=400,
                            detail="an opening balance goes through /cash-anchor or "
                                   "/cash-reanchor, which require their own evidence")
    resolved = normalise_type(etype, body.amount)
    if resolved is None or resolved not in ALL_TYPES:
        raise HTTPException(
            status_code=400,
            detail="event_type must be one of: %s" % ", ".join(sorted(ALL_TYPES - {ANCHOR})))
    if not (body.source_ref or "").strip():
        raise HTTPException(status_code=400,
                            detail="source_ref is required - an evidence-backed event "
                                   "names the document it was read out of "
                                   "(convention #32: hash the file as received)")
    if not (body.actor or "").strip():
        raise HTTPException(status_code=400,
                            detail="actor is required - a movement recorded by nobody "
                                   "cannot be asked about later")
    if body.amount == 0:
        raise HTTPException(status_code=400, detail="amount must be non-zero")
    try:
        when = date.fromisoformat((body.event_date or "")[:10])
    except (TypeError, ValueError, IndexError):
        raise HTTPException(status_code=400,
                            detail="event_date must be an ISO date, e.g. 2026-08-31")

    acct = body.account_name
    ref = body.source_ref.strip()
    # The SERVICE's key, over the movement itself: same file re-imported, same rows,
    # nothing doubled. `occurrence` is the last resort for two genuinely identical
    # same-day movements, which this book already contains.
    key = dedup_key(acct, resolved, body.amount, when, ref, body.occurrence)
    desc = "%s | evidence %s | by %s%s" % (
        resolved, ref, body.actor.strip(),
        (" | " + body.note.strip()) if body.note else "")

    pool = await _pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO cash_flows
                   (account_name, flow_type, amount, description, activity_date,
                    imported_from, source_ref, dedup_key, occurrence)
               VALUES ($1, $2, $3, $4, $5::date, 'EVIDENCE', $6, $7, $8)
               ON CONFLICT (account_name, dedup_key) WHERE dedup_key IS NOT NULL
               DO NOTHING
               RETURNING id""",
            acct, resolved, body.amount, desc, when, ref, key, body.occurrence)
        created = row is not None
        if not created:
            row = await conn.fetchrow(
                "SELECT id FROM cash_flows WHERE account_name = $1 AND dedup_key = $2",
                acct, key)

    derived = await _derived_balance(acct)
    return {
        "status": "recorded" if created else "already_recorded",
        "cash_flow_id": row["id"] if row else None,
        "account_name": acct, "event_type": resolved, "amount": body.amount,
        "event_date": when.isoformat(), "source_ref": ref,
        "actor": body.actor.strip(), "occurrence": body.occurrence,
        "stored_balance_untouched": True,
        **derived,
    }


class CashReanchorCreate(BaseModel):
    account_name: str
    cash: float                          # what the broker shows right now
    idempotency_key: str
    as_of: Optional[str] = None          # ISO instant; defaults to now
    note: Optional[str] = None



# ── R-IV.667(b) · ONE correction route for a cash event ────────────────────────────────────
class CashFlowCorrection(BaseModel):
    """A cash event corrected to its export line, and nothing else.

    THE PROBLEM IT CLOSES. A UI-entered trade writes its cash BEFORE fees are known -- the fee
    only arrives with the broker export -- and until R-IV.660(c)2 it also dated the movement on
    the day it was typed. CC-POSITIONS holds the confirmed case: event 144, BX, reads -38.00 on
    10-06 where the export says -38.18 on 09-30. Weekly cleanups will find more, because the fee
    is never knowable at entry time.

    ONLY `amount` AND `activity_date` ARE ACCEPTABLE. The model carries no other mutable field,
    so "refuses any other change" is enforced by what a caller can even express, not by a check
    it might forget. The account, the type, the source_ref and the occurrence are the event's
    IDENTITY -- correcting those would not be a correction, it would be a different event wearing
    this one's id.
    """
    amount: Optional[float] = None
    activity_date: Optional[str] = None
    # Required. An unevidenced correction to money is indistinguishable from a typo with a
    # confident tone, and this route exists precisely because the first figure was wrong.
    evidence_ref: str
    reason: str
    ruling: str
    actor: str


@router.post("/cash-flows/{event_id}/correct", dependencies=[Depends(require_api_key)])
async def correct_cash_flow(event_id: int, body: CashFlowCorrection):
    """Correct one cash event's amount and/or date to its export line. R-IV.667(b).

    Writes the before-state to `cash_flow_corrections`, one row per column changed, in the SAME
    transaction as the update -- a correction whose audit row could be lost separately is not an
    audited correction. R-IV.552(b) stands: this is the route so that nobody needs direct SQL.
    """
    from datetime import date as _date

    from services.cash_ledger import dedup_key

    for field in ("evidence_ref", "reason", "ruling", "actor"):
        if not (getattr(body, field) or "").strip():
            raise HTTPException(
                status_code=400,
                detail="%s is required: a correction to money that cannot say what it was read "
                       "out of, why, under which ruling, and by whom is not auditable" % field)
    if body.amount is None and body.activity_date is None:
        raise HTTPException(status_code=400,
                            detail="give amount, activity_date, or both - there is nothing to "
                                   "correct otherwise")
    if body.amount is not None and body.amount == 0:
        raise HTTPException(status_code=400,
                            detail="amount must be non-zero; a movement of zero is not a "
                                   "correction, it is a deletion wearing one")

    new_date = None
    if body.activity_date is not None:
        try:
            new_date = _date.fromisoformat(body.activity_date[:10])
        except (TypeError, ValueError, IndexError):
            raise HTTPException(status_code=400,
                                detail="activity_date must be an ISO date, e.g. 2026-09-30")
        if new_date > _date.today():
            raise HTTPException(status_code=400,
                                detail="activity_date %s is in the future; an export line "
                                       "describes something that already happened"
                                       % new_date.isoformat())

    pool = await get_postgres_client()
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "SELECT id, account_name, flow_type, amount, description, activity_date, "
            "imported_from, occurrence, source_ref, dedup_key FROM cash_flows "
            "WHERE id = $1 FOR UPDATE", event_id)
        if not row:
            raise HTTPException(status_code=404, detail="cash event %s not found" % event_id)

        before = dict(row)
        amount = Decimal(str(body.amount)) if body.amount is not None else before["amount"]
        when = new_date or before["activity_date"]

        changes = []
        if amount != before["amount"]:
            changes.append(("amount", str(before["amount"]), str(amount)))
        if when != before["activity_date"]:
            changes.append(("activity_date", before["activity_date"].isoformat(),
                            when.isoformat()))
        if not changes:
            # NOT an error, and NOT an audit row either: re-sending the values a row already
            # holds is idempotent, and recording it as a correction would put a change in the
            # ledger that never happened.
            return {"status": "unchanged", "event_id": event_id,
                    "amount": float(before["amount"]),
                    "activity_date": before["activity_date"].isoformat(),
                    "note": "the event already holds these values; nothing written"}

        # THE DEDUP KEY IS DERIVED, SO IT IS RECOMPUTED. It is built from the account, type,
        # AMOUNT, DATE, source_ref and occurrence. Leaving it alone would leave a row whose key
        # describes values the row no longer holds -- so a genuinely new movement with the
        # corrected amount and date would dedup against this row and be silently dropped, and a
        # re-import of the original would not. Same shape as a stored total that no longer
        # matches its ledger, and as the cached age fixed under R-IV.699.
        new_key = dedup_key(before["account_name"], before["flow_type"], amount, when,
                            before["source_ref"], before["occurrence"]) if before["dedup_key"] \
            else None
        if new_key and new_key != before["dedup_key"]:
            clash = await conn.fetchrow(
                "SELECT id FROM cash_flows WHERE account_name = $1 AND dedup_key = $2 "
                "AND id <> $3", before["account_name"], new_key, event_id)
            if clash:
                raise HTTPException(
                    status_code=409,
                    detail=("the corrected values already exist as event %s. Correcting this one "
                            "would make two rows for one movement; reconcile them instead."
                            % clash["id"]))
            changes.append(("dedup_key", before["dedup_key"], new_key))

        for column, old, new in changes:
            await conn.execute(
                "INSERT INTO cash_flow_corrections (cash_flow_id, column_name, old_value, "
                "new_value, reason, ruling, actor) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                event_id, column, old, new,
                "%s | evidence %s" % (body.reason.strip(), body.evidence_ref.strip()),
                body.ruling.strip(), body.actor.strip())

        try:
            await conn.execute(
                "UPDATE cash_flows SET amount = $2, activity_date = $3, dedup_key = $4 "
                "WHERE id = $1", event_id, amount, when, new_key or before["dedup_key"])
        except Exception as exc:
            # The natural-key index (account, type, amount, description, date, imported_from,
            # occurrence) can also collide, and NULLS NOT DISTINCT means a null description does
            # not excuse it. Named rather than surfaced as a 500.
            raise HTTPException(
                status_code=409,
                detail=("the corrected row collides with an existing cash event on the natural "
                        "key (%s). Reconcile the two rather than correcting into a duplicate."
                        % type(exc).__name__))

    return {"status": "corrected", "event_id": event_id,
            "before": {"amount": float(before["amount"]),
                       "activity_date": before["activity_date"].isoformat()},
            "after": {"amount": float(amount), "activity_date": when.isoformat()},
            "columns_changed": [c[0] for c in changes],
            "audit_rows_written": len(changes),
            "evidence_ref": body.evidence_ref.strip(),
            "ruling": body.ruling.strip()}

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

    if derived_before is None:
        difference = None
        note = ("the hub could not derive a balance before this anchor, so there is "
                "no difference to report - this is a first anchor, not a correction")
    else:
        difference = round(float(body.cash) - float(derived_before), 2)
        note = ("the hub derived %.2f and the broker shows %.2f; this gap is what the "
                "CSV cleanup should account for" % (derived_before, body.cash)
                if difference else "the hub and the broker already agreed")

    # R-IV.551(d)2: the result travels WITH the row. `entered` is the row's own
    # amount, but `derived_before` and `difference` are computed here and gone by the
    # next read -- so a repeat key could only have answered with a fresh zero, which
    # is a different claim from "you asked this before and here is what it said".
    meta = json.dumps({"derived_before": derived_before, "entered": body.cash,
                       "difference": difference, "difference_note": note,
                       "as_of": as_of.isoformat(), "actor": "principal",
                       "kind": "broker_figure"})

    pool = await _pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO cash_flows
                   (account_name, flow_type, amount, description, activity_date,
                    imported_from, source_ref, dedup_key, meta)
               VALUES ($1, $2, $3, $4, $5::date, 'PRINCIPAL_ANCHOR', $6, $7, $8::jsonb)
               ON CONFLICT (account_name, dedup_key) WHERE dedup_key IS NOT NULL
               DO NOTHING
               RETURNING id, amount, meta""",
            acct, ANCHOR, body.cash, desc, as_of.date(), ref, key, meta)
        created = row is not None
        if not created:
            row = await conn.fetchrow(
                """SELECT id, amount, meta FROM cash_flows
                    WHERE account_name = $1 AND dedup_key = $2""", acct, key)

    conflict = None
    if not created and row is not None:
        # R-IV.551(d)3: the same key with a DIFFERENT figure is a conflict, reported
        # the way /cash-entry reports one -- never a silent no-op. The first anchor
        # stands; re-anchoring to a new figure is a new key.
        original = row["meta"]
        if isinstance(original, str):
            original = json.loads(original)
        original = original or {}
        if float(row["amount"]) != float(body.cash):
            conflict = {"cash": {"recorded": float(row["amount"]), "sent": body.cash}}
        # The ORIGINAL answer, not a fresh one computed against a ledger this very
        # anchor has since changed.
        derived_before = original.get("derived_before", derived_before)
        difference = original.get("difference", difference)
        note = original.get("difference_note", note)

    after = await _derived_balance(acct)
    return {
        "status": "reanchored" if created else "already_reanchored",
        "cash_flow_id": row["id"] if row else None,
        "account_name": acct,
        "entered": float(row["amount"]) if (not created and row) else body.cash,
        "derived_before": derived_before,
        "difference": difference,
        "difference_note": note,
        "conflict": conflict,
        "conflict_note": None if not conflict else
            "this key already anchored a different figure; the first one stands and "
            "nothing was changed - send a new idempotency_key to re-anchor again",
        "as_of": as_of.isoformat(),
        "evidence_ref": ref,
        "actor": "principal",
        "idempotency_key": key_raw,
        "stored_balance_untouched": True,
        **after,
    }
