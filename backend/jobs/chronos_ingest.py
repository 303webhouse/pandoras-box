"""
Chronos Earnings Ingestion
Runs daily at 6 AM ET. Pulls earnings from UW API (primary) or FMP (fallback),
cross-references with positions and watchlist, upserts to DB.
"""
import logging
import json
from datetime import date, timedelta

from database.postgres_client import get_postgres_client
from utils.position_overlap import ETF_COMPONENTS

logger = logging.getLogger("chronos_ingest")


async def _fetch_uw_earnings() -> list:
    """Fetch earnings from UW API — premarket and afterhours combined."""
    try:
        from integrations.uw_api import get_earnings_premarket
        pre = await get_earnings_premarket() or []
        # UW returns rich data per entry; normalize to our schema
        results = []
        for e in pre:
            results.append({
                "symbol": e.get("symbol", ""),
                "date": e.get("report_date", ""),
                "_timing": e.get("report_time", ""),  # "premarket" or "afterhours"
                "epsEstimated": e.get("street_mean_est"),
                "revenueEstimated": None,  # UW premarket doesn't include revenue est
                "_company_name": e.get("full_name"),
                "_market_cap": e.get("marketcap"),
                "_sector": e.get("sector"),
                "_fiscal_quarter": e.get("ending_fiscal_quarter"),
            })
        return results
    except Exception as ex:
        logger.warning("Chronos: UW earnings fetch failed: %s", ex)
        return []


async def _fetch_fmp_earnings(date_from, date_to) -> list:
    """Fallback: fetch earnings from FMP."""
    try:
        from integrations.fmp_client import fetch_earnings_calendar
        return await fetch_earnings_calendar(date_from, date_to) or []
    except ImportError:
        logger.debug("Chronos: fmp_client not available")
        return []
    except Exception as ex:
        logger.warning("Chronos: FMP earnings fetch failed: %s", ex)
        return []


async def run_chronos_earnings_ingest():
    """Main ingestion function called by the background loop."""
    logger.info("📅 Chronos: starting earnings ingestion...")

    today = date.today()
    date_from = today
    date_to = today + timedelta(days=21)

    # 1. Fetch earnings — UW API primary, FMP fallback
    earnings = await _fetch_uw_earnings()
    source = "uw_api"
    if not earnings:
        earnings = await _fetch_fmp_earnings(date_from, date_to)
        source = "fmp"
    if not earnings:
        logger.warning("Chronos: no earnings data from any source")
        return

    logger.info("Chronos: fetched %d earnings entries from %s", len(earnings), source)

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
                # UW provides company_name, market_cap, timing, fiscal_quarter
                # FMP free tier returns None for these — UW fills the gaps
                company_name = entry.get("_company_name")
                timing = entry.get("_timing")
                fiscal_quarter = entry.get("_fiscal_quarter")
                market_cap_val = _to_int(entry.get("_market_cap"))

                await conn.execute("""
                INSERT INTO earnings_calendar
                    (ticker, company_name, report_date, fiscal_period, fiscal_year,
                     timing, eps_estimate, revenue_estimate, market_cap,
                     in_position_book, in_watchlist, position_overlap_details, last_updated)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
                ON CONFLICT (ticker, report_date) DO UPDATE SET
                    company_name = COALESCE(EXCLUDED.company_name, earnings_calendar.company_name),
                    timing = COALESCE(EXCLUDED.timing, earnings_calendar.timing),
                    eps_estimate = COALESCE(EXCLUDED.eps_estimate, earnings_calendar.eps_estimate),
                    revenue_estimate = COALESCE(EXCLUDED.revenue_estimate, earnings_calendar.revenue_estimate),
                    market_cap = COALESCE(EXCLUDED.market_cap, earnings_calendar.market_cap),
                    in_position_book = EXCLUDED.in_position_book,
                    in_watchlist = EXCLUDED.in_watchlist,
                    position_overlap_details = EXCLUDED.position_overlap_details,
                    last_updated = NOW()
            """,
                ticker,
                company_name,
                report_date,
                fiscal_quarter,  # fiscal_period
                None,            # fiscal_year
                timing,
                _to_float(entry.get("epsEstimated")),
                _to_int(entry.get("revenueEstimated")),
                market_cap_val,
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
