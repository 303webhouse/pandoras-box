"""`GET /api/crowd` — B6's Crowd gauge. Two rows live, one deliberately still a mock.

SOURCES AND THEIR STANDING, which is the whole shape of this route:
  * CFTC TFF, futures only: Socrata view `gpe5-46if` on publicreporting.cftc.gov. The dataset
    id and the two contract names were read FROM THE PORTAL'S OWN API, not guessed -- "NASDAQ
    MINI" is the E-mini Nasdaq-100 and "NASDAQ-100 Consolidated" is a different series.
    US-government public domain, wired live under R-IV.1239(d)1.
  * PUT/CALL: `flow_events`, already pulled from UW. NO NEW UW CALLS -- this is a read of rows
    the hub has already paid for. Labelled as the universe proxy it is.
  * FINRA short interest: NOT WIRED. See `crowd_b6.short_interest_row`.

It reads `flow_events`, which is hub market data rather than Nick's book, so it is NOT gated --
`/api/event-strip` and `/api/position-watch` read `unified_positions` and ARE.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from models import crowd_b6 as cb

logger = logging.getLogger("api_crowd")

router = APIRouter(prefix="/crowd", tags=["crowd"])

CFTC_VIEW = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
#: A year of weekly observations for the percentile, plus a margin.
CFTC_WEEKS = 60
#: The put/call average window, in sessions.
PC_SESSIONS = 5

_cftc_cache: Dict[str, Any] = {}


async def _cftc() -> Dict[str, Any]:
    """ES and NQ leveraged-money nets, newest first, with the history for the percentile.

    One HTTP call a day: the report changes weekly, so polling it harder spends a request to
    receive the same numbers. Cached on the UTC date.
    """
    today = _dt.date.today().isoformat()
    if _cftc_cache.get("day") == today:
        return _cftc_cache["data"]
    import httpx

    names = list(cb.CFTC_CONTRACTS.values())
    where = " OR ".join("contract_market_name='%s'" % n for n in names)
    params = {
        "$select": ("contract_market_name,report_date_as_yyyy_mm_dd,"
                    "lev_money_positions_long,lev_money_positions_short,open_interest_all"),
        "$where": where,
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": str(CFTC_WEEKS * len(names)),
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(CFTC_VIEW, params=params)
    resp.raise_for_status()
    rows = resp.json()
    out = {"rows": rows}
    _cftc_cache.update({"day": today, "data": out})
    return out


def _f(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return None if f != f else f
    except Exception:                                               # noqa: BLE001
        return None


def _cftc_block(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Nets per contract per report date, newest date first."""
    by_date: Dict[str, Dict[str, Optional[float]]] = {}
    for r in rows:
        d = str(r.get("report_date_as_yyyy_mm_dd", ""))[:10]
        name = r.get("contract_market_name")
        key = next((k for k, v in cb.CFTC_CONTRACTS.items() if v == name), None)
        if not d or key is None:
            continue
        by_date.setdefault(d, {})[key] = cb.cftc_net(
            _f(r.get("lev_money_positions_long")), _f(r.get("lev_money_positions_short")))
    dates = sorted(by_date, reverse=True)
    if not dates:
        return {"nets": {k: None for k in cb.CFTC_CONTRACTS}, "history": [], "as_of": None}
    newest = by_date[dates[0]]
    # The history is each EARLIER week's total, so today's reading is ranked against weeks
    # that are complete rather than against itself.
    history: List[Optional[float]] = []
    for d in dates[1:]:
        vals = [v for v in by_date[d].values() if v is not None]
        history.append(sum(vals) if vals else None)
    try:
        as_of = _dt.date.fromisoformat(dates[0])
    except ValueError:
        as_of = None
    return {"nets": {k: newest.get(k) for k in cb.CFTC_CONTRACTS},
            "history": history, "as_of": as_of}


async def _put_call(conn) -> Dict[str, Any]:
    """The put/call proxy from `flow_events`, and the universe it covers.

    AGGREGATED FROM VOLUMES, not averaged from each ticker's own ratio: a mean of ratios
    weights a thin ticker the same as SPY, which is a different and worse statistic. Sum the
    puts, sum the calls, divide.
    """
    rows = await conn.fetch(
        """
        SELECT (captured_at AT TIME ZONE 'America/New_York')::date AS d,
               SUM(put_volume)  AS puts,
               SUM(call_volume) AS calls,
               COUNT(DISTINCT ticker) AS tickers
          FROM flow_events
         WHERE captured_at >= NOW() - INTERVAL '400 days'
           AND put_volume IS NOT NULL AND call_volume IS NOT NULL
         GROUP BY 1 ORDER BY 1 DESC
        """)
    daily: List[Dict[str, Any]] = []
    for r in rows:
        calls = _f(r["calls"]) or 0.0
        puts = _f(r["puts"]) or 0.0
        if calls <= 0:
            continue
        daily.append({"d": r["d"], "ratio": puts / calls, "tickers": int(r["tickers"] or 0)})
    if not daily:
        return {"ratio": None, "history": [], "universe": None, "as_of": None}
    window = daily[:PC_SESSIONS]
    ratio = sum(x["ratio"] for x in window) / len(window)
    # The history is each earlier session's own ratio, not a rolling mean of means.
    history = [x["ratio"] for x in daily[PC_SESSIONS:]]
    return {"ratio": ratio, "history": history,
            "universe": max(x["tickers"] for x in window),
            "as_of": daily[0]["d"].isoformat() if daily[0]["d"] else None}


@router.get("")
async def get_crowd() -> Dict[str, Any]:
    degraded: List[str] = []
    rows: List[Dict[str, Any]] = []
    pc_as_of = None
    try:
        from database.postgres_client import get_postgres_client

        pc = {"ratio": None, "history": [], "universe": None, "as_of": None}
        try:
            pool = await get_postgres_client()
            async with pool.acquire() as conn:
                pc = await _put_call(conn)
        except Exception as exc:                                    # noqa: BLE001
            degraded.append("put/call from flow_events: %s" % type(exc).__name__)
        pc_as_of = pc["as_of"]
        rows.append(cb.put_call_row(pc["ratio"], pc["history"], universe_size=pc["universe"],
                                    sessions=PC_SESSIONS, as_of=pc["as_of"]))

        try:
            raw = await _cftc()
            blk = _cftc_block(raw["rows"])
            rows.append(cb.cftc_row(blk["nets"], blk["history"], blk["as_of"]))
        except Exception as exc:                                    # noqa: BLE001
            degraded.append("CFTC TFF: %s" % type(exc).__name__)
            rows.append(cb.cftc_row({k: None for k in cb.CFTC_CONTRACTS}, [], None))

        # R-IV.1318(b): LIVE, from FINRA's free twice-monthly file. Guarded like its
        # siblings -- a failed fetch costs this ROW its value and says so, never the panel.
        try:
            from integrations.finra_short_interest import short_interest as _finra_si

            _si = await _finra_si("SPY")
        except Exception as exc:                                    # noqa: BLE001
            degraded.append("FINRA short interest: %s" % type(exc).__name__)
            _si = None
        rows.append(cb.short_interest_row(_si))
        word, lean, basis = cb.headline(rows)
        return {
            "live": True,
            "headline": word,
            "headline_lean": lean,
            "headline_basis": basis,
            "rows": rows,
            "settled_close": pc_as_of,
            "footnotes": [r["source"] for r in rows if r.get("source")],
            "caption": "percentile · display only",
            "degraded": degraded,
            "as_of": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "field_origin": {"rows": "derived", "headline": "derived"},
        }
    except Exception as exc:                                        # noqa: BLE001
        logger.error("[crowd] failed: %s", type(exc).__name__)
        return {"live": True, "error": "%s" % type(exc).__name__, "rows": [],
                "note": "the Crowd read failed; no mock is substituted for the live rows"}
