"""`GET /api/regime-sections` — B8's drawer sections, live. R-IV.1246(b).

§2 credit, §3's Zweig proxy, §4 leadership, §5 rates and cross-asset, in ONE route and ONE
payload, because the drawer opens once and four routes would be four chances for a partial
render. §§1 and 7 already ride the regime-strategy payload; §6 and §8 are added here as their
sources are wired.

A SOURCE THAT FAILS SHOWS "unavailable", NEVER A MOCK VALUE (R-IV.1246(b)). Every section
carries its own `available` flag and reason, so one dead series leaves the other three intact
and says which one died. Display only (#42); nothing here gates anything.

No book table is read, so this route is not gated.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from models import regime_sections_b8 as rs

logger = logging.getLogger("api_regime_sections")

router = APIRouter(prefix="/regime-sections", tags=["regime-sections"])

#: Enough history for a one-year percentile plus a margin.
FRED_YEARS = 2
#: Leadership needs only a couple of months, but one call serves both.
EQUITY_PERIOD = "120d"

_LEADERSHIP_SYMS = sorted({s for _, a, b, _ in
                           [(n, a, b, m) for n, a, b, m in rs.LEADERSHIP] for s in (a, b)})


def _fred(series_id: str):
    from integrations import fred_series as fred

    return fred.fetch_series(series_id, years=FRED_YEARS)


def _equity_closes() -> Dict[str, List[Optional[float]]]:
    """One batched yfinance call for every leadership leg."""
    import yfinance as yf

    frame = yf.download(_LEADERSHIP_SYMS, period=EQUITY_PERIOD, interval="1d",
                        auto_adjust=True, progress=False, threads=False, group_by="ticker")
    out: Dict[str, List[Optional[float]]] = {}
    if frame is None or getattr(frame, "empty", True):
        return out
    for sym in _LEADERSHIP_SYMS:
        try:
            sub = frame[sym] if len(_LEADERSHIP_SYMS) > 1 else frame
        except Exception:                                           # noqa: BLE001
            continue
        if sub is None or getattr(sub, "empty", True):
            continue
        vals: List[Optional[float]] = []
        for _, row in sub.sort_index().iterrows():
            try:
                v = float(row["Close"])
                vals.append(None if v != v else v)
            except Exception:                                       # noqa: BLE001
                vals.append(None)
        out[sym] = vals
    return out


# §3's breadth series comes from `jobs.regime_job.breadth_history`, NOT from a query here.
# THE SUITE'S OWN GUARD SENT ME BACK: R-IV.1195 enumerates every file allowed to name
# `regime_snapshots`, so that a new reader has to be added deliberately -- "which is the moment
# someone asks whether it is allowed to". The honest answer was not to add one. The read lives
# in the module that already owns every regime-table read, and this route calls it.


@router.get("")
async def get_regime_sections() -> Dict[str, Any]:
    out: Dict[str, Any] = {"live": True,
                           "as_of": _dt.datetime.now(_dt.timezone.utc).isoformat()}
    # §2 credit
    try:
        pts = await asyncio.to_thread(_fred, rs.HY_SERIES)
        out["credit"] = rs.credit_block(pts)
    except Exception as exc:                                        # noqa: BLE001
        out["credit"] = {"available": False, "reason": "FRED %s failed: %s"
                                                       % (rs.HY_SERIES, type(exc).__name__)}
    # §5 rates
    try:
        series = {}
        for sid in rs.RATES_SERIES.values():
            series[sid] = await asyncio.to_thread(_fred, sid)
        out["rates"] = rs.rates_block(series, move=None)
    except Exception as exc:                                        # noqa: BLE001
        out["rates"] = {"available": False, "reason": "FRED rates failed: %s"
                                                      % type(exc).__name__}
    # §4 leadership
    try:
        closes = await asyncio.to_thread(_equity_closes)
        out["leadership"] = rs.leadership_block(closes)
    except Exception as exc:                                        # noqa: BLE001
        out["leadership"] = {"available": False,
                             "reason": "yfinance failed: %s" % type(exc).__name__}
    # §3's Zweig proxy
    try:
        from database.postgres_client import get_postgres_client

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            from jobs.regime_job import breadth_history

            hist = await breadth_history(conn)
        out["zweig"] = rs.zweig_proxy(hist)
    except Exception as exc:                                        # noqa: BLE001
        out["zweig"] = {"available": False, "fired": None,
                        "reason": "the stored breadth series could not be read: %s"
                                  % type(exc).__name__,
                        "note": rs.ZWEIG_PROXY_NOTE}
    # §6 auction state, from the PYTHIA market-profile snapshot the hub already stores.
    try:
        from services.read_only.market_profile import get_market_profile

        out["auction"] = rs.auction_block(await get_market_profile("SPY"))
    except Exception as exc:                                        # noqa: BLE001
        out["auction"] = {"available": False,
                          "reason": "the market-profile read failed: %s" % type(exc).__name__}
    # §8 lamps. The kill state is NOT read here: the card already holds it, and a second
    # reader of the kill switch is a second thing that can disagree about whether it is armed.
    out["lamps"] = rs.lamps_block(kill_state=None)
    out["field_origin"] = {"credit": "derived", "rates": "derived",
                           "leadership": "derived", "zweig": "derived",
                           "auction": "stored", "lamps": "derived"}
    return out
