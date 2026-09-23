"""Abacus summary: the data contract behind the v2 Abacus page (R-IV.429).

Most of the payload is still the mocked fixture below, with `source: "mock"` on each block
and `mock: true` at the top, so the page shows its mock banner. The fixture responds to the
range SERVER-SIDE (charter D2: the range changes the figures, and nothing is recomputed in
the browser). Counts and dollars scale with the window's length, rates stay put, and every
range stays internally consistent.

Live data replaces one block at a time as sources land (R-IV.429(a)). A block turns live by
changing its own `source` to "live" and carrying a real `computed_at`; the page drops the
banner only when no block is still mock.

LIVE, since R-IV.484(c): the `net_profit` and `win_rate` stats, read from `unified_positions`
via `_load_book_realized()`. The unit is the position lifecycle, and the window filters on
CLOSE date (`exit_date`) -- /api/analytics/trade-stats windows on `opened_at` over the
`trades` rows instead, so it is not a drop-in source. Each of the two carries a `coverage`
object beside it: the census (`LOWER(status) IN ('closed','expired')`, windowed the same way),
how many rows were counted, and why the rest were not (basis-incomplete, return below -100%
of cost basis, or a `realized_pnl` the book never recorded). Everything else -- equity,
leaks, breakdowns including discipline, strategies -- stays mock, and its `source` field says
so; discipline metrics have no source columns yet (no stop/time-stop/override/tag columns) and
are not wired.

Gated like every book read (R-IV.417): the same dependency as /api/analytics and
/api/portfolio, because what this route returns once live is the principal's book.

Contract (every block):
  source       "mock" | "live"
  computed_at  ISO-8601 UTC, when the figure was computed. For the fixture this is the
               instant it was AUTHORED, never "now": a mock stamped with the request time
               would read as fresh.
Rates carry their n. Unknown is null, never 0. `version` is the contract's version (R9).
"""

from __future__ import annotations

import copy
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

from database.postgres_client import get_postgres_client
from utils.pivot_auth import require_api_key

router = APIRouter(prefix="/abacus", tags=["abacus"])

RANGES = ("30d", "90d", "ytd", "all")
SUMMARY_VERSION = 1

# The mock book's first day, so "All" has a length. Not a real date from the book.
MOCK_BOOK_START = date(2025, 10, 1)
# The fixture's figures below are the 90-day window's.
FIXTURE_BASE_DAYS = 90
MIN_SCALE = 0.05

# When the fixture was written. Not a data vintage: nothing here was computed from trades.
FIXTURE_AUTHORED_AT = "2026-09-17T05:30:00Z"

_S = {"source": "mock", "computed_at": FIXTURE_AUTHORED_AT}

# Values are the published build-from mockup's ("Abacus · v2 skin · build-from mockup").
# Money is USD, signed. Rates are fractions 0..1.
FIXTURE = {
    "mock": True,
    "version": SUMMARY_VERSION,
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
         "date": None,  # the trough's date, set per range
         "meaning": "Largest peak-to-trough fall in the range. The date is the trough.", **_S},
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
        "drawdown": {"from_index": 6, "to_index": 8, "amount": -1140, "date": None},
        **_S,
    },
    "leaks": {
        "items": [
            # Counts live in `n` (charter R2), never inside the prose, so they scale with the range.
            {"label": "Adding to losers", "amount": -612, "n": 6, "detail": "Adds against an open loss that went on to lose more."},
            {"label": "Far-OTM tails", "amount": -480, "n": 11, "detail": "Bought far out of the money; none paid. Avg 41 days held."},
            {"label": "Overridden time stops", "amount": -318, "n": 4, "detail": "Held past the time-stop exit."},
            {"label": "Untagged trades", "amount": -141, "n": 9, "detail": "No bucket or thesis recorded."},
            {"label": "Index ETF verticals", "amount": 1020, "n": 38, "detail": "Your edge. 58% win, PF 1.9."},
            {"label": "Commodity sleeve", "amount": 744, "n": 9, "detail": "Under cap; harvested at target."},
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
        if start > end:
            raise HTTPException(status_code=422, detail="from must not be after to")
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


def _span(rng: dict) -> tuple:
    """(first day, last day) of the window. "All" starts at the mock book's first day."""
    last = date.fromisoformat(rng["to"])
    first = date.fromisoformat(rng["from"]) if rng["from"] else MOCK_BOOK_START
    return min(max(first, MOCK_BOOK_START), last), last


def _cnt(v, scale: float):
    """Scale a positive count; never below 1, never a fraction. None and 0 pass through."""
    if v is None or isinstance(v, bool) or not isinstance(v, int) or v <= 0:
        return v
    return max(1, round(v * scale))


def _usd(v, scale: float):
    return v if v is None else round(v * scale)


def _scaled(scale: float) -> dict:
    """The fixture for a window `scale` times the base window's length.

    Counts and dollars scale; rates, ratios and per-trade figures do not. The equity curve is
    stretched about its first point, and net profit and max drawdown are READ BACK from the
    rounded curve, so start-to-end == net profit and the marked fall == max drawdown hold
    exactly for every range.
    """
    out = copy.deepcopy(FIXTURE)
    closed = _cnt(out["scope"]["closed_positions"], scale)
    out["scope"]["closed_positions"] = closed

    eq = out["equity"]
    p0 = eq["points"][0]
    eq["points"] = [round(p0 + (p - p0) * scale) for p in eq["points"]]
    dd = eq["drawdown"]
    dd["amount"] = eq["points"][dd["to_index"]] - eq["points"][dd["from_index"]]
    net = eq["points"][-1] - eq["points"][0]

    for st in out["stats"]:
        if st["key"] == "net_profit":
            st["value"] = net
        elif st["key"] == "max_drawdown":
            st["value"] = dd["amount"]
        elif st["key"] == "win_rate":
            st["n"] = closed

    for it in out["leaks"]["items"]:
        it["amount"] = _usd(it["amount"], scale)
        it["n"] = _cnt(it["n"], scale)

    for table in out["breakdowns"]:
        kinds = [c[1] for c in table["columns"]]
        for row in table["rows"]:
            for i, kind in enumerate(kinds):
                if kind == "int":
                    row[i] = _cnt(row[i], scale)
                elif kind == "usd":
                    row[i] = _usd(row[i], scale)
    return out


async def _load_book_realized(pool, first: Optional[date], last: date) -> dict:
    """Realized P&L and win rate, live, per R-IV.464(h).

    Census predicate (R-IV.484(c)): LOWER(status) IN ('closed','expired'), windowed on
    exit_date (the CLOSE, not the open -- /api/analytics/trade-stats windows on opened_at,
    which is why it is not a drop-in source here). A row with basis_incomplete_reason set, or
    whose realized return computes below -100% of its cost basis (a data-integrity signal, not
    a real result), is counted in the census but never averaged into net profit or win rate. A
    row the book never recorded a realized_pnl for is excluded the same way -- never treated as
    a $0 trade.
    """
    conditions = ["LOWER(status) IN ('closed', 'expired')", "exit_date IS NOT NULL", "exit_date::date <= $1"]
    params: list = [last]
    if first is not None:
        conditions.append("exit_date::date >= $2")
        params.append(first)
    rows = await pool.fetch(
        f"SELECT realized_pnl, cost_basis, basis_incomplete_reason FROM unified_positions "
        f"WHERE {' AND '.join(conditions)}",
        *params,
    )

    excl_basis = excl_return = excl_unrecorded = 0
    counted_pnls: list = []
    for r in rows:
        if r["basis_incomplete_reason"]:
            excl_basis += 1
            continue
        pnl = r["realized_pnl"]
        basis = r["cost_basis"]
        if pnl is not None and basis and float(basis) != 0:
            if (float(pnl) / abs(float(basis))) < -1:
                excl_return += 1
                continue
        if pnl is None:
            excl_unrecorded += 1
            continue
        counted_pnls.append(float(pnl))

    counted = len(counted_pnls)
    wins = sum(1 for p in counted_pnls if p > 0)
    return {
        "net_profit": round(sum(counted_pnls), 2) if counted else None,
        "win_rate": round(wins / counted, 4) if counted else None,
        "coverage": {
            "predicate": "LOWER(status) IN ('closed','expired'), windowed on exit_date",
            "total": len(rows),
            "counted": counted,
            "excluded": {
                "basis_incomplete": excl_basis,
                "return_below_neg100pct": excl_return,
                "no_realized_pnl": excl_unrecorded,
            },
        },
    }


@router.get("/summary")
async def abacus_summary(
    range: str = Query("90d", pattern="^(30d|90d|ytd|all)$"),
    start: Optional[date] = Query(None, alias="from"),
    end: Optional[date] = Query(None, alias="to"),
    _=Depends(require_api_key),
):
    """The Abacus page's payload. STUB: the mocked fixture, scaled to the requested range."""
    # The market's calendar day, not the server's: Railway runs in UTC, which is already
    # "tomorrow" for the principal every evening after 6 PM MT.
    today_et = datetime.now(ZoneInfo("America/New_York")).date()
    rng = _resolve_range(range, start, end, today_et)
    first, last = _span(rng)
    span_days = (last - first).days
    out = _scaled(max(max(span_days, 1) / FIXTURE_BASE_DAYS, MIN_SCALE))

    # The curve's points are evenly spaced across the window, which dates the trough. The
    # real span (possibly 0) is used here, so the date can never fall outside the window.
    eq = out["equity"]
    n_pts = len(eq["points"])
    trough_i = eq["drawdown"]["to_index"]
    trough = (first + timedelta(days=round(span_days * trough_i / (n_pts - 1)))).isoformat()
    eq["from"], eq["to"] = first.isoformat(), last.isoformat()
    eq["drawdown"]["date"] = trough
    for st in out["stats"]:
        if st["key"] == "max_drawdown":
            st["date"] = trough

    # R-IV.484(c) — net profit and win rate go live off the book; the window is the RAW
    # requested range, not `first` above (that clamps "all" to the mock book's fake start
    # date, which has no place gating a real query).
    live_first = date.fromisoformat(rng["from"]) if rng["from"] else None
    live_last = date.fromisoformat(rng["to"])
    pool = await get_postgres_client()
    book = await _load_book_realized(pool, live_first, live_last)
    live_stamp = {"source": "live", "computed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    for st in out["stats"]:
        if st["key"] == "net_profit":
            st["value"] = book["net_profit"]
            st["coverage"] = book["coverage"]
            st.update(live_stamp)
        elif st["key"] == "win_rate":
            st["value"] = book["win_rate"]
            st["n"] = book["coverage"]["counted"]
            st["coverage"] = book["coverage"]
            st.update(live_stamp)

    out["range"] = rng
    out["range_applied"] = True
    return out
