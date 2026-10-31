"""Read-only access to earnings_calendar (R-IV.1461(f)3, (f)5, (h)).

One place that turns UW's stored rows into what the readers show: Hermes' catalyst list, the
Event Strip's earnings chips and the evening push. Dates, times and the market's own numbers
only -- no beat/miss call and no trade language.

UW sends `expected_move_perc` and `reaction` as decimal fractions ("0.0359" = 3.59%, per its
docs' example); `pct()` turns them into percent for display.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

#: UW's report_time values (and the older BMO/AMC rows) -> the label a reader sees.
_TIMING = {"premarket": "BMO", "bmo": "BMO", "postmarket": "AMC", "afterhours": "AMC",
           "amc": "AMC"}


def timing_label(raw: Optional[str]) -> str:
    """'BMO', 'AMC', or '' when UW does not say (report_time 'unknown')."""
    return _TIMING.get(str(raw or "").strip().lower(), "")


def scheduled_at(d: date, label: str) -> datetime:
    """The session edge the report sits on: BMO = before the 09:30 ET open, AMC = after the
    16:00 ET close. With no timing, the start of the day. Always ET-aware."""
    from zoneinfo import ZoneInfo
    hh = {"BMO": time(9, 30), "AMC": time(16, 0)}.get(label, time(0, 0))
    return datetime.combine(d, hh, tzinfo=ZoneInfo("America/New_York"))


def pct(v) -> Optional[float]:
    """A stored decimal fraction as a percent, rounded to 0.1; None stays None."""
    try:
        return None if v is None else round(float(v) * 100.0, 1)
    except (TypeError, ValueError):
        return None


#: How the readers order names: YOURS first, then S&P 500 members by market cap, then the
#: rest by market cap. There is no SPY-weight source in the hub; SPY is float-adjusted
#: market-cap weighted, so membership + market cap is the stand-in, and it is labelled so.
ORDER_RULE = ("held names first, then S&P 500 members by market cap (stand-in for SPY "
              "weight), then the rest by market cap")


def rank_key(row: Dict[str, Any]):
    return (not row.get("yours"), not row.get("sp500"), -(row.get("market_cap") or 0),
            row.get("ticker") or "")


async def fetch_earnings(start: date, end: date, ticker: Optional[str] = None
                         ) -> Optional[List[Dict[str, Any]]]:
    """Rows reporting between start and end (inclusive), each with `yours` = an OPEN
    position in that ticker in any account. None when the table cannot be read."""
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT e.ticker, e.company_name, e.report_date, e.timing, e.market_cap,
                       e.expected_move, e.expected_move_perc, e.reaction, e.is_sp500,
                       EXISTS (SELECT 1 FROM unified_positions p
                               WHERE p.ticker = e.ticker AND p.status = 'OPEN') AS yours
                FROM earnings_calendar e
                WHERE e.report_date BETWEEN $1 AND $2
                  AND ($3::text IS NULL OR e.ticker = $3)
                ORDER BY e.report_date, e.market_cap DESC NULLS LAST, e.ticker
                """, start, end, ticker.upper() if ticker else None)
    except Exception as exc:                                          # noqa: BLE001
        logger.warning("earnings_calendar read failed: %s", exc)
        return None
    out = []
    for r in rows:
        label = timing_label(r["timing"])
        out.append({
            "ticker": r["ticker"], "company_name": r["company_name"],
            "report_date": r["report_date"], "timing": label,
            "market_cap": r["market_cap"],
            "expected_move": float(r["expected_move"]) if r["expected_move"] is not None else None,
            "implied_move_pct": pct(r["expected_move_perc"]),
            "reaction_pct": pct(r["reaction"]),
            "yours": bool(r["yours"]),
            "sp500": bool(r["is_sp500"]),
        })
    return out
