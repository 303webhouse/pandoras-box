"""
Chronos Earnings Ingestion

R-IV.1461(f)1: runs once on deploy, then nightly at 20:15 ET Sunday-Thursday. For the last
completed session and each of the next 10 sessions it reads UW's premarket and afterhours
lists BY DATE, every page (R-IV.1464(c)), cross-references positions and the watchlist, and
upserts earnings_calendar. Each run leaves one job_runs row whose skip_reason carries the
per-date counts.

Why every page: the old fetch asked for TODAY's lists with UW's default limit of 50, so busy
dates stored exactly 100 rows (50 + 50) and everything past the first page was never seen.

F.4: FMP fallback removed — UW API is sole source. position_overlap.py still
uses FMP for ETF holdings (separate decision, not changed here).
"""
import logging
from datetime import date, datetime, timezone
from typing import Optional

from database.postgres_client import get_postgres_client
from utils.position_overlap import ETF_COMPONENTS
from utils.json_sanitize import dumps_jsonb

logger = logging.getLogger("chronos_ingest")

SIDES = ("premarket", "afterhours")
#: How many sessions ahead the calendar reaches (R-IV.1461(f)1).
SESSIONS_AHEAD = 10
#: A date-side with more pages than this is a runaway, not an earnings list.
MAX_PAGES = 20


def _to_float(v):
    try:
        return float(v) if v is not None and v != "" else None
    except (ValueError, TypeError):
        return None


def _to_int(v):
    try:
        return int(float(v)) if v is not None and v != "" else None
    except (ValueError, TypeError):
        return None


def _day(v) -> str:
    """UW's report_date as YYYY-MM-DD. Its docs show '2023-02-14T00:00:00.000Z' as well as
    plain dates, and date.fromisoformat refuses the former."""
    return str(v or "")[:10]


def _to_bool(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    return str(v).strip().lower() in ("true", "1", "t", "yes")


def _normalize_uw_entry(e: dict) -> dict:
    return {
        "symbol": e.get("symbol", ""),
        "date": _day(e.get("report_date")),
        "_timing": e.get("report_time", ""),  # premarket / postmarket / unknown, as UW sends it
        "epsEstimated": e.get("street_mean_est"),
        "revenueEstimated": None,
        "_company_name": e.get("full_name"),
        "_market_cap": e.get("marketcap"),
        "_sector": e.get("sector"),
        "_fiscal_quarter": e.get("ending_fiscal_quarter"),
        # R-IV.1461(f)2: the market's own numbers, kept as UW sends them.
        "_expected_move": e.get("expected_move"),
        "_expected_move_perc": e.get("expected_move_perc"),
        "_reaction": e.get("reaction"),
        # Index membership: the Event Strip's stand-in for SPY weight (with market cap).
        "_is_sp500": e.get("is_s_p_500"),
    }


#: Nightly at 20:15 ET, Sunday-Thursday (R-IV.1461(f)1). Python weekday(): Mon=0 .. Sun=6.
NIGHTLY_AT = (20, 15)
NIGHTLY_WEEKDAYS = (6, 0, 1, 2, 3)


def nightly_due(now_et: datetime, last_nightly: Optional[date]) -> bool:
    """True once per qualifying evening, at or after 20:15 ET."""
    if now_et.weekday() not in NIGHTLY_WEEKDAYS:
        return False
    if (now_et.hour, now_et.minute) < NIGHTLY_AT:
        return False
    return last_nightly != now_et.date()


def ingest_dates(now: Optional[datetime] = None) -> list:
    """The last TWO completed sessions, then the next SESSIONS_AHEAD sessions after today (ET).

    The completed sessions are there for the day-after reaction row: a reporter's `reaction`
    exists only after the session that reacts to it has closed, and for an after-the-close
    reporter that is the NEXT session -- so the last session alone would never see it."""
    from stable_engine import market_calendar as mc
    now = now or datetime.now(timezone.utc)
    today = mc._now_et(now).date()
    last = mc.last_settled_session(now)
    out = [mc.previous_trading_day(last), last]
    cur = today
    for _ in range(SESSIONS_AHEAD):
        cur = mc.next_trading_day(cur)
        if cur not in out:
            out.append(cur)
    return out


def _totals(resp) -> dict:
    """Any count UW puts beside `data` (a total, a page count). Recorded, never assumed."""
    if not isinstance(resp, dict):
        return {}
    return {k: v for k, v in resp.items()
            if k != "data" and isinstance(v, (int, float)) and not isinstance(v, bool)}


async def fetch_date_side(side: str, on: date, get_page=None) -> dict:
    """Every page of one list for one date. `complete` is True only when a page came back
    shorter than the limit -- the one proof that nothing is left."""
    if get_page is None:
        from integrations.uw_api import get_earnings_page as get_page
    from integrations.uw_api import EARNINGS_PAGE_LIMIT as limit
    rows, pages, totals, reason = [], 0, {}, None
    complete = False
    for page in range(MAX_PAGES):
        resp = await get_page(side, on, page)
        if not resp or not isinstance(resp, dict) or not isinstance(resp.get("data"), list):
            reason = "page %d unreadable (%s)" % (page, getattr(resp, "reason", None) or
                                                  type(resp).__name__)
            break
        pages += 1
        if page == 0:
            totals = _totals(resp)
        data = resp["data"]
        rows.extend(data)
        if len(data) < limit:
            complete = True
            break
    else:
        reason = "stopped at %d pages" % MAX_PAGES
    return {"side": side, "date": on.isoformat(), "rows": rows, "n": len(rows),
            "pages": pages, "complete": complete, "uw_totals": totals, "reason": reason}


async def _fetch_uw_earnings(dates: list, get_page=None):
    """Both lists for every date. Returns (normalized entries, per-date report)."""
    seen, results, report = set(), [], []
    for d in dates:
        for side in SIDES:
            got = await fetch_date_side(side, d, get_page)
            other = 0
            for e in got["rows"]:
                if _day(e.get("report_date")) != d.isoformat():
                    other += 1
                key = (e.get("symbol", ""), _day(e.get("report_date")))
                if key in seen:
                    continue
                seen.add(key)
                results.append(_normalize_uw_entry(e))
            got["other_date"] = other
            del got["rows"]
            report.append(got)
    return results, report


def summarize(report: list) -> str:
    """One line per date: 'YYYY-MM-DD pre N/Pp ah N/Pp', '!' marking a list not proven
    complete, plus anything UW said its total was."""
    by_date = {}
    for r in report:
        mark = "" if r["complete"] else "!"
        tot = (" uw%s" % r["uw_totals"]) if r["uw_totals"] else ""
        by_date.setdefault(r["date"], []).append(
            "%s %d/%dp%s%s" % ("pre" if r["side"] == "premarket" else "ah",
                               r["n"], r["pages"], mark, tot))
    return "; ".join("%s %s" % (d, " ".join(v)) for d, v in sorted(by_date.items()))


async def run_chronos_earnings_ingest(now: Optional[datetime] = None, get_page=None) -> dict:
    """Main ingestion function called by the background loop."""
    from jobs import job_runs
    from stable_engine import market_calendar as mc
    now = now or datetime.now(timezone.utc)
    today = mc._now_et(now).date()
    logger.info("📅 Chronos: starting earnings ingestion...")
    run_id = await job_runs.start_run(job_runs.JOB_EARNINGS_INGEST, today)
    try:
        dates = ingest_dates(now)
        earnings, report = await _fetch_uw_earnings(dates, get_page)
    except Exception as exc:                                          # noqa: BLE001
        logger.warning("Chronos: UW earnings fetch failed: %s", exc)
        await job_runs.finish_run(run_id, "error", error="fetch: %s" % exc)
        return {"status": "error", "upserted": 0, "report": []}

    line = summarize(report)
    incomplete = [r for r in report if not r["complete"]]
    if not earnings:
        status = "error" if incomplete else "ok"
        logger.warning("Chronos: no earnings rows from UW (%s)", line)
        await job_runs.finish_run(run_id, status, rows_touched=0,
                                  skip_reason="0 rows; " + line)
        return {"status": status, "upserted": 0, "report": report}

    logger.info("Chronos: fetched %d earnings entries from uw_api: %s", len(earnings), line)
    upserted = await _upsert(earnings, today)
    status = "partial" if incomplete else "ok"
    await job_runs.finish_run(run_id, status, rows_touched=upserted,
                              skip_reason="%d upserted over %d dates; %s"
                              % (upserted, len(dates), line))
    logger.info("📅 Chronos: upserted %d earnings entries (%s)", upserted, status)
    return {"status": status, "upserted": upserted, "report": report}


async def _upsert(earnings: list, today: date) -> int:
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        # Current positions and watchlist tickers for overlap checking
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

            in_book = ticker in position_tickers or ticker in etf_component_set
            in_wl = ticker in watchlist_tickers
            overlap_details = None
            if ticker in etf_overlap_map:
                overlap_details = dumps_jsonb({"etf_positions": etf_overlap_map[ticker]})

            try:
                await conn.execute("""
                INSERT INTO earnings_calendar
                    (ticker, company_name, report_date, fiscal_period, fiscal_year,
                     timing, eps_estimate, revenue_estimate, market_cap,
                     in_position_book, in_watchlist, position_overlap_details,
                     expected_move, expected_move_perc, reaction, is_sp500, last_updated)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, NOW())
                ON CONFLICT (ticker, report_date) DO UPDATE SET
                    company_name = COALESCE(EXCLUDED.company_name, earnings_calendar.company_name),
                    timing = COALESCE(EXCLUDED.timing, earnings_calendar.timing),
                    eps_estimate = COALESCE(EXCLUDED.eps_estimate, earnings_calendar.eps_estimate),
                    revenue_estimate = COALESCE(EXCLUDED.revenue_estimate, earnings_calendar.revenue_estimate),
                    market_cap = COALESCE(EXCLUDED.market_cap, earnings_calendar.market_cap),
                    in_position_book = EXCLUDED.in_position_book,
                    in_watchlist = EXCLUDED.in_watchlist,
                    position_overlap_details = EXCLUDED.position_overlap_details,
                    expected_move = COALESCE(EXCLUDED.expected_move, earnings_calendar.expected_move),
                    expected_move_perc = COALESCE(EXCLUDED.expected_move_perc, earnings_calendar.expected_move_perc),
                    reaction = COALESCE(EXCLUDED.reaction, earnings_calendar.reaction),
                    is_sp500 = COALESCE(EXCLUDED.is_sp500, earnings_calendar.is_sp500),
                    last_updated = NOW()
            """,
                ticker,
                entry.get("_company_name"),
                report_date,
                entry.get("_fiscal_quarter"),  # fiscal_period
                None,                          # fiscal_year
                entry.get("_timing"),
                _to_float(entry.get("epsEstimated")),
                _to_int(entry.get("revenueEstimated")),
                _to_int(entry.get("_market_cap")),
                in_book,
                in_wl,
                overlap_details,
                _to_float(entry.get("_expected_move")),
                _to_float(entry.get("_expected_move_perc")),
                _to_float(entry.get("_reaction")),
                _to_bool(entry.get("_is_sp500")),
            )
                upserted += 1
            except Exception as row_err:
                logger.debug("Chronos: skipping %s on %s — %s", ticker, report_date, row_err)

        # Also update trade_watchlist entries with next earnings dates
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
    return upserted
