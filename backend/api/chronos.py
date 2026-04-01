"""
Chronos Earnings Calendar API

Endpoints:
- GET /chronos/calendar          — Earnings for date range
- GET /chronos/book-impact       — Earnings affecting current positions
- GET /chronos/this-week         — This week's earnings summary
- GET /chronos/market-movers     — Top 15 by market cap reporting this week
- POST /chronos/refresh          — Manually trigger earnings refresh
"""
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Query, HTTPException, Request

from database.postgres_client import get_postgres_client
from utils.position_overlap import ETF_COMPONENTS

logger = logging.getLogger("chronos_api")
router = APIRouter(prefix="/chronos")


def _monday_friday(ref: date = None):
    """Return (Monday, Friday) of the week containing ref (default: today)."""
    d = ref or date.today()
    monday = d - timedelta(days=d.weekday())
    friday = monday + timedelta(days=4)
    return monday, friday


async def init_chronos_table():
    """Create earnings_calendar table if it doesn't exist."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS earnings_calendar (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                ticker TEXT NOT NULL,
                company_name TEXT,
                report_date DATE NOT NULL,
                fiscal_period TEXT,
                fiscal_year INTEGER,
                timing TEXT CHECK (timing IN ('BMO', 'AMC', 'TNS', NULL)),
                eps_estimate NUMERIC(10,4),
                eps_actual NUMERIC(10,4),
                revenue_estimate BIGINT,
                revenue_actual BIGINT,
                market_cap BIGINT,
                in_position_book BOOLEAN DEFAULT FALSE,
                in_watchlist BOOLEAN DEFAULT FALSE,
                position_overlap_details JSONB,
                last_updated TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT uq_earnings_ticker_date UNIQUE (ticker, report_date)
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_earnings_date ON earnings_calendar (report_date)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_earnings_book ON earnings_calendar (in_position_book) WHERE in_position_book = TRUE")
    logger.info("earnings_calendar table ready")


# ── GET /chronos/calendar ──────────────────────────────────────────
@router.get("/calendar")
async def get_earnings_calendar(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    ticker: Optional[str] = Query(None),
):
    """Earnings for date range (default: today + 14 days)."""
    today = date.today()
    d_from = date.fromisoformat(date_from) if date_from else today
    d_to = date.fromisoformat(date_to) if date_to else today + timedelta(days=14)

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        if ticker:
            rows = await conn.fetch(
                "SELECT * FROM earnings_calendar WHERE report_date BETWEEN $1 AND $2 AND ticker = $3 ORDER BY report_date ASC",
                d_from, d_to, ticker.upper()
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM earnings_calendar WHERE report_date BETWEEN $1 AND $2 ORDER BY report_date ASC",
                d_from, d_to
            )

    return {"count": len(rows), "earnings": [dict(r) for r in rows]}


# ── GET /chronos/book-impact ───────────────────────────────────────
@router.get("/book-impact")
async def get_book_impact():
    """Earnings affecting current positions (next 14 days)."""
    today = date.today()
    d_to = today + timedelta(days=14)

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM earnings_calendar WHERE in_position_book = TRUE AND report_date BETWEEN $1 AND $2 ORDER BY report_date ASC",
            today, d_to
        )

        # Get position tickers for grouping
        pos_rows = await conn.fetch(
            "SELECT ticker FROM unified_positions WHERE status = 'OPEN'"
        )
    position_tickers = set(r["ticker"] for r in pos_rows)

    # Group by position ticker
    grouped = {}
    for row in rows:
        r = dict(row)
        ticker = r["ticker"]
        # Find which position(s) this earnings ticker maps to
        if ticker in position_tickers:
            grouped.setdefault(ticker, []).append(r)
        else:
            # Check ETF component mapping
            for pos_ticker in position_tickers:
                if ticker in ETF_COMPONENTS.get(pos_ticker, []):
                    grouped.setdefault(pos_ticker, []).append(r)

    # Calculate earnings_density per position
    result = {}
    for pos_ticker, earnings_list in grouped.items():
        total_components = len(ETF_COMPONENTS.get(pos_ticker, []))
        reporting_count = len(earnings_list)
        density = round(reporting_count / max(total_components, 1), 2)
        result[pos_ticker] = {
            "earnings": earnings_list,
            "reporting_count": reporting_count,
            "total_components": total_components,
            "earnings_density": density,
        }

    return {"positions_affected": len(result), "impact": result}


# ── GET /chronos/this-week ─────────────────────────────────────────
@router.get("/this-week")
async def get_this_week():
    """This week's earnings summary."""
    monday, friday = _monday_friday()

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM earnings_calendar WHERE report_date BETWEEN $1 AND $2 ORDER BY report_date ASC",
            monday, friday
        )

    all_entries = [dict(r) for r in rows]
    book_impact = [e for e in all_entries if e.get("in_position_book")]
    watchlist = [e for e in all_entries if e.get("in_watchlist")]
    # Top 15 by market cap
    by_mcap = sorted(all_entries, key=lambda e: e.get("market_cap") or 0, reverse=True)
    market_movers = by_mcap[:15]

    return {
        "week": f"{monday.isoformat()} to {friday.isoformat()}",
        "total_earnings": len(all_entries),
        "book_impact": book_impact,
        "watchlist": watchlist,
        "market_movers": market_movers,
    }


# ── GET /chronos/market-movers ─────────────────────────────────────
@router.get("/market-movers")
async def get_market_movers(
    period: str = Query("this_week", regex="^(this_week|next_week)$"),
):
    """Top 15 earnings by market cap for the period."""
    today = date.today()
    if period == "next_week":
        next_monday = today + timedelta(days=(7 - today.weekday()))
        monday, friday = _monday_friday(next_monday)
    else:
        monday, friday = _monday_friday()

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM earnings_calendar WHERE report_date BETWEEN $1 AND $2 AND market_cap IS NOT NULL ORDER BY market_cap DESC LIMIT 15",
            monday, friday
        )

    return {"period": period, "movers": [dict(r) for r in rows]}


# ── POST /chronos/refresh ─────────────────────────────────────────
@router.post("/refresh")
async def refresh_earnings(request: Request):
    """Manually trigger earnings refresh."""
    api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    import os
    expected = os.getenv("PIVOT_API_KEY") or ""
    if not api_key or api_key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from jobs.chronos_ingest import run_chronos_earnings_ingest
    await run_chronos_earnings_ingest()
    return {"status": "ok", "message": "Earnings refresh complete"}
