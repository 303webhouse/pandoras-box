"""
Chronos Earnings Ingestion
Runs daily at 6 AM ET. Pulls 21 days of earnings from FMP,
cross-references with positions and watchlist, upserts to DB.
"""
import logging
import json
from datetime import date, timedelta

from database.postgres_client import get_postgres_client
from integrations.fmp_client import fetch_earnings_calendar
from utils.position_overlap import ETF_COMPONENTS

logger = logging.getLogger("chronos_ingest")


async def run_chronos_earnings_ingest():
    """Main ingestion function called by the background loop."""
    logger.info("📅 Chronos: starting earnings ingestion...")

    today = date.today()
    date_from = today
    date_to = today + timedelta(days=21)

    # 1. Fetch earnings from FMP
    earnings = await fetch_earnings_calendar(date_from, date_to)
    if not earnings:
        logger.warning("Chronos: FMP returned no earnings data")
        return

    logger.info("Chronos: fetched %d earnings entries from FMP", len(earnings))

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        # 2. Get current positions and watchlist tickers for overlap checking
        position_rows = await conn.fetch(
            "SELECT ticker FROM unified_positions WHERE status = 'OPEN'"
        )
        position_tickers = set(r["ticker"] for r in position_rows)

        watchlist_rows = await conn.fetch(
            "SELECT ticker FROM trade_watchlist WHERE is_active = TRUE"
        )
        watchlist_tickers = set(r["ticker"] for r in watchlist_rows)

        # Build a set of all component tickers from held ETFs
        etf_component_set = set()
        etf_overlap_map = {}  # ticker -> [list of ETF positions it belongs to]
        for pos_ticker in position_tickers:
            components = ETF_COMPONENTS.get(pos_ticker, [])
            for comp in components:
                etf_component_set.add(comp)
                etf_overlap_map.setdefault(comp, []).append(pos_ticker)

        # 3. Upsert each earnings entry
        upserted = 0
        for entry in earnings:
            ticker = (entry.get("symbol") or "").upper()
            if not ticker:
                continue

            report_date_str = entry.get("date")
            if not report_date_str:
                continue

            # Convert string date to Python date object (asyncpg requires this)
            try:
                report_date = date.fromisoformat(report_date_str)
            except (ValueError, TypeError):
                logger.debug("Chronos: skipping %s — bad date %s", ticker, report_date_str)
                continue

            # Check overlaps
            in_book = ticker in position_tickers or ticker in etf_component_set
            in_wl = ticker in watchlist_tickers
            overlap_details = None
            if ticker in etf_overlap_map:
                overlap_details = json.dumps({"etf_positions": etf_overlap_map[ticker]})

            # Coerce numeric fields — FMP can return strings, None, or numbers
            def _to_float(v):
                try:
                    return float(v) if v is not None else None
                except (ValueError, TypeError):
                    return None

            def _to_int(v):
                try:
                    return int(v) if v is not None else None
                except (ValueError, TypeError):
                    return None

            try:
                await conn.execute("""
                INSERT INTO earnings_calendar
                    (ticker, company_name, report_date, fiscal_period, fiscal_year,
                     timing, eps_estimate, revenue_estimate, market_cap,
                     in_position_book, in_watchlist, position_overlap_details, last_updated)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
                ON CONFLICT (ticker, report_date) DO UPDATE SET
                    timing = EXCLUDED.timing,
                    eps_estimate = EXCLUDED.eps_estimate,
                    revenue_estimate = EXCLUDED.revenue_estimate,
                    in_position_book = EXCLUDED.in_position_book,
                    in_watchlist = EXCLUDED.in_watchlist,
                    position_overlap_details = EXCLUDED.position_overlap_details,
                    last_updated = NOW()
            """,
                ticker,
                entry.get("name") or entry.get("company_name"),
                report_date,
                entry.get("fiscalDateEnding"),
                _to_int(entry.get("fiscal_year")),
                entry.get("_timing"),
                _to_float(entry.get("epsEstimated")),
                _to_int(entry.get("revenueEstimated")),
                _to_int(entry.get("marketCap")),
                in_book,
                in_wl,
                overlap_details
            )
                upserted += 1
            except Exception as row_err:
                logger.debug("Chronos: skipping %s on %s — %s", ticker, report_date, row_err)

        # 4. Also update trade_watchlist entries with next earnings dates
        for wl_ticker in watchlist_tickers:
            next_earn = await conn.fetchrow("""
                SELECT report_date, timing FROM earnings_calendar
                WHERE ticker = $1 AND report_date >= $2
                ORDER BY report_date ASC LIMIT 1
            """, wl_ticker, today)

            if next_earn:
                await conn.execute("""
                    UPDATE trade_watchlist
                    SET next_earnings_date = $1, earnings_timing = $2, updated_at = NOW()
                    WHERE ticker = $3 AND is_active = TRUE
                """, next_earn["report_date"], next_earn["timing"], wl_ticker)

    logger.info("📅 Chronos: upserted %d earnings entries, updated watchlist dates", upserted)
