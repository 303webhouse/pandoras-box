"""Abacus summary: the data contract behind the v2 Abacus page (R-IV.429).

STUB. Every metric is served from the mocked fixture below, with `source: "mock"` on each
block and `mock: true` at the top, so the page shows its mock banner. Live data replaces
one block at a time as sources land (R-IV.429(a)). A block turns live by changing its own
`source` to "live" and carrying a real `computed_at`; the page drops the banner only when
no block is still mock.

Gated like every book read (R-IV.417): the same dependency as /api/analytics and
/api/portfolio, because what this route returns once live is the principal's book.

Contract (every block):
  source       "mock" | "live"
  computed_at  ISO-8601 UTC, when the figure was computed. For the fixture this is the
               instant it was AUTHORED, never "now": a mock stamped with the request time
               would read as fresh.
Rates carry their n. Unknown is null, never 0.
"""

from __future__ import annotations

import copy
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

from utils.pivot_auth import require_api_key

router = APIRouter(prefix="/abacus", tags=["abacus"])

RANGES = ("30d", "90d", "ytd", "all")

# When the fixture was written. Not a data vintage: nothing here was computed from trades.
FIXTURE_AUTHORED_AT = "2026-09-17T05:30:00Z"

_S = {"source": "mock", "computed_at": FIXTURE_AUTHORED_AT}

# Values are the published build-from mockup's ("Abacus · v2 skin · build-from mockup").
# Money is USD, signed. Rates are fractions 0..1.
FIXTURE = {
    "mock": True,
    "scope": {"label": "Both accounts", "closed_positions": 249, **_S},
    "stats": [
        {"key": "net_profit", "label": "Net profit", "format": "usd", "value": 1573,
         "meaning": "Realized gains minus losses, after fees, for closes in this range.", **_S},
        {"key": "expectancy", "label": "Expectancy per trade", "format": "usd_cents", "value": 6.30,
         "meaning": "What one average trade is worth. The single number to grow.", **_S},
        {"key": "win_rate", "label": "Win rate", "format": "pct", "value": 0.54, "n": 249,
         "meaning": "Share of closed positions that made money. Only useful beside the next two.", **_S},
        {"key": "profit_factor", "label": "Profit factor", "format": "ratio", "value": 1.4,
         "meaning": "Dollars won per dollar lost. Above 1.5 is healthy.", **_S},
        {"key": "avg_win_loss", "label": "Avg win / avg loss", "format": "usd_pair", "value": [48, -52],
         "meaning": "Losers slightly bigger than winners — the tails book does this.", **_S},
        {"key": "max_drawdown", "label": "Max drawdown", "format": "usd", "value": -1140,
         "meaning": "Largest peak-to-trough fall. −9%, late July.", **_S},
        {"key": "sharpe", "label": "Sharpe ratio", "format": "ratio", "value": 0.8,
         "qualifier": {"state": "unknown", "label": "rough"},
         "meaning": "Gain per unit of volatility. Needs many more trades to be precise — read it as direction, not a grade.", **_S},
        {"key": "loss_vs_risk", "label": "Loss vs risk defined", "format": "pct", "value": 0.31,
         "meaning": "On losing defined-risk trades you give back 31% of the max. You cut rather than ride to zero.", **_S},
    ],
    "equity": {
        # Shape of the mockup's curve; start-to-end = net profit, and the marked fall = max drawdown.
        "points": [10900, 11010, 10930, 11420, 11300, 11860, 12050, 11330,
                   10910, 11380, 11760, 11610, 12010, 12160, 12400, 12473],
        "drawdown": {"from_index": 6, "to_index": 8, "amount": -1140},
        **_S,
    },
    "leaks": {
        "items": [
            {"label": "Adding to losers", "amount": -612, "detail": "6 adds against an open loss; 5 lost more."},
            {"label": "Far-OTM tails", "amount": -480, "detail": "11 bought, 0 paid, avg 41 days held."},
            {"label": "Overridden time stops", "amount": -318, "detail": "4 held past exit; the rule would have paid +$95."},
            {"label": "Untagged trades", "amount": -141, "detail": "9 with no bucket or thesis."},
            {"label": "Index ETF verticals", "amount": 1020, "detail": "Your edge. 58% win, PF 1.9, n=38."},
            {"label": "Commodity sleeve", "amount": 744, "detail": "Under cap; harvested twice. n=9."},
        ],
        **_S,
    },
    "breakdowns": [
        {"key": "structure", "label": "By structure",
         "columns": [["Structure", "text"], ["n", "int"], ["Win", "pct"], ["Net", "usd"], ["PF", "ratio"], ["Share of losses", "bar"]],
         "rows": [
             ["Index ETF verticals", 38, 0.58, 1020, 1.9, 0.12],
             ["Commodity sleeve", 9, 0.67, 744, 2.4, 0.04],
             ["Single-name verticals", 61, 0.49, 210, 1.1, 0.31],
             ["Butterflies", 7, 0.43, -61, 0.8, 0.06],
             ["Inverse / leveraged ETFs", 12, 0.42, -118, 0.7, 0.14],
             ["Far-OTM tails", 11, 0.0, -480, 0.0, 0.33],
         ], **_S},
        {"key": "ticker", "label": "By ticker",
         "columns": [["Ticker", "text"], ["n", "int"], ["Win", "pct"], ["Net", "usd"], ["PF", "ratio"]],
         "rows": [
             ["QQQ", 31, 0.55, 412, 1.6],
             ["SPY", 22, 0.64, 388, 2.1],
             ["IEO / XLE / USO", 14, 0.64, 602, 2.8],
             ["SOXS / SQQQ", 12, 0.42, -118, 0.7],
             ["NVDA", 9, 0.33, -97, 0.5],
             ["UVXY", 6, 0.0, -188, 0.0],
         ], **_S},
        {"key": "hold", "label": "By hold time",
         "columns": [["Held", "text"], ["n", "int"], ["Win", "pct"], ["Net", "usd"], ["Expectancy", "usd_cents"]],
         "rows": [
             ["Same day", 18, 0.39, -96, -5.30],
             ["2–7 days", 71, 0.52, 301, 4.20],
             ["8–21 days", 96, 0.60, 1340, 14.00],
             ["22–45 days", 48, 0.52, 390, 8.10],
             ["Over 45 days", 16, 0.25, -362, -22.60],
         ], **_S},
        {"key": "weekday", "label": "By weekday",
         "columns": [["Entered on", "text"], ["n", "int"], ["Win", "pct"], ["Net", "usd"]],
         "rows": [
             ["Monday", 41, 0.49, 120],
             ["Tuesday", 58, 0.57, 610],
             ["Wednesday", 55, 0.56, 505],
             ["Thursday", 52, 0.54, 402],
             ["Friday", 43, 0.47, -64],
         ], **_S},
        {"key": "discipline", "label": "Discipline",
         "columns": [["Rule", "text"], ["Set", "int"], ["Honoured", "pct"], ["Cost of overrides", "usd"], ["Source", "chip"]],
         "rows": [
             ["Hard stops", 24, 0.71, -204, {"state": "fresh", "label": "rules"}],
             ["Time stops", 10, 0.60, -318, {"state": "fresh", "label": "rules"}],
             ["Harvest at target", 14, 0.86, -40, {"state": "fresh", "label": "rules"}],
             ["Committee REDUCE verdicts", 5, 0.40, -276, {"state": "unknown", "label": "from notes"}],
             ["Bucket tag on open", 249, 0.96, -141, {"state": "fresh", "label": "rules"}],
         ], **_S},
    ],
    "strategies": {
        "note": "Fills once Triton, STRIKE and PYTHIA have graded populations. Same range control, columns fixed now.",
        "columns": [["Strategy", "text"], ["n", "int"], ["Hit rate", "pct"], ["Expectancy", "usd_cents"],
                    ["Drawdown", "usd"], ["By class / regime", "chip"]],
        "rows": [
            ["Triton sweep-following", None, None, None, None, {"state": "unknown", "label": "window open"}],
            ["STRIKE IB-break", None, None, None, None, {"state": "unknown", "label": "collecting"}],
            ["PYTHIA value-area", None, None, None, None, {"state": "unknown", "label": "collecting"}],
        ],
        **_S,
    },
}


def _resolve_range(key: str, start: Optional[date], end: Optional[date], today: date) -> dict:
    """Echo the requested window. Explicit dates win over the preset key."""
    if start and end:
        return {"key": "custom", "from": start.isoformat(), "to": end.isoformat()}
    if key == "30d":
        frm = today - timedelta(days=30)
    elif key == "ytd":
        frm = date(today.year, 1, 1)
    elif key == "all":
        frm = None
    else:
        key, frm = "90d", today - timedelta(days=90)
    return {"key": key, "from": frm.isoformat() if frm else None, "to": today.isoformat()}


@router.get("/summary")
async def abacus_summary(
    range: str = Query("90d", pattern="^(30d|90d|ytd|all)$"),
    start: Optional[date] = Query(None, alias="from"),
    end: Optional[date] = Query(None, alias="to"),
    _=Depends(require_api_key),
):
    """The Abacus page's payload. STUB: the mocked fixture, with the requested range echoed.

    The figures do NOT change with the range while the source is mock. The page says so via
    the banner, and `range_applied: false` says it in the data.
    """
    out = copy.deepcopy(FIXTURE)
    # The market's calendar day, not the server's: Railway runs in UTC, which is already
    # "tomorrow" for the principal every evening after 6 PM MT.
    today_et = datetime.now(ZoneInfo("America/New_York")).date()
    out["range"] = _resolve_range(range, start, end, today_et)
    out["range_applied"] = False
    return out
