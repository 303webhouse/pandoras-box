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
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

from database.postgres_client import get_postgres_client
from models.accounts import display_name          # R-IV.650(a): the name is served, never inferred
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


# ── R-IV.705: the live blocks ────────────────────────────────────────────────────────────────
# ONE read, everything derived from it. The stats, the four breakdowns and the untagged count all
# come from the same rows with the same exclusions, so they cannot disagree with each other or
# with the census -- which two reads of "the same" census would eventually do.
MT = ZoneInfo("America/Denver")

# TA-058's bucket cutoff, from C:\lane-state\POSITIONS.md (R-IV.705(f)). The lane records it as
# "rows opened on or after 2026-09-25" (POSITIONS.md:1839) and "the 2026-09-25 cutoff" (:428).
# Rows opened before it are untagged BY DESIGN -- buckets did not exist -- so counting them as a
# leak would indict the principal for a field that could not be filled.
#
# Two caveats, recorded because they bound what this figure can claim. POSITIONS.md:1825 says
# TA-058 itself never reached that lane, so 2026-09-25 is the lane's RECORDED cutoff rather than a
# quotation of the block; and :509 flags an open question for Trade Analysis about a position whose
# SECOND fill lands on the cutoff day. Neither changes the count below, which uses `entry_date`.
BUCKET_CUTOFF = date(2026, 9, 25)

# Cash events that move money IN OR OUT of an account, as opposed to money the account EARNED.
# Only these are netted out of a return: subtracting a dividend would understate the return as
# surely as leaving a deposit in overstates it. OPENING_BALANCE is a ledger anchor, not a
# movement -- Robinhood has three on one day, and netting them out would print a crater.
EXTERNAL_FLOWS = frozenset({"ACH", "DEPOSIT", "WITHDRAWAL", "TRANSFER_IN", "TRANSFER_OUT"})
INTERNAL_FLOWS = frozenset({"DIVIDEND", "INTEREST", "FEE", "TRADE_DEBIT", "TRADE_CREDIT",
                            "OPENING_BALANCE"})
# Anything else is UNCLASSIFIED and fails the coverage test by name. A new flow_type must not be
# able to join a return series silently; `ADJUSTMENT` is deliberately here rather than guessed at.
SHARPE_MIN_N = 20          # below this, the figure is served with `rough` on its face


def _census_where(first: Optional[date], last: date) -> tuple:
    """(clause, params) for the ONE census predicate. $1 is `last`, $2 is `first`.

    Extracted so every live figure on this page is drawn from the same population. The failure
    this prevents is the one ABACUS reported against the positions panel: a second reader writing
    its own predicate, which then drifts from the first and is believed because it looks the same.
    """
    conditions = ["LOWER(status) IN ('closed', 'expired')", "exit_date IS NOT NULL",
                  "exit_date::date <= $1"]
    params: list = [last]
    if first is not None:
        conditions.append("exit_date::date >= $2")
        params.append(first)
    return " AND ".join(conditions), params


def _cal_date(value) -> Optional[date]:
    """The calendar day a DAY-SEMANTIC column already denotes, with no zone conversion.

    `snapshot_date` and `activity_date` are days, not instants: the hub stores each as that day's
    midnight in Mountain Time. Running them through a timezone conversion is the bug this exists
    to avoid -- a value written as UTC midnight instead would shift back a day, and a curve would
    begin on a date the hub never recorded. Use `_mt_date` for a real instant (a fill), and this
    for a day.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def _mt_date(value) -> Optional[date]:
    """A timestamp's calendar day in the principal's timezone, not the server's.

    Railway runs in UTC, which is already tomorrow for him after 6 PM MT, so a `::date` cast puts
    an evening fill on the wrong day -- and on the wrong side of a cutoff.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(MT).date()
    return value


HOLD_BUCKETS = (("Same day", 0, 0), ("2–7 days", 1, 7), ("8–21 days", 8, 21),
                ("22–45 days", 22, 45), ("Over 45 days", 46, 10 ** 6))
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _agg(rows: list) -> dict:
    """n, win rate, net and profit factor over counted rows. Pooled, never averaged."""
    pnls = [r["pnl"] for r in rows]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_loss = abs(sum(losses))
    return {
        "n": len(pnls),
        "win": round(len(wins) / len(pnls), 4) if pnls else None,
        "net": round(sum(pnls), 2) if pnls else None,
        # None, never a sentinel: an account with no losing trade has no ratio of won to lost,
        # and a large number in its place reads as a measured edge.
        "pf": round(sum(wins) / gross_loss, 2) if gross_loss else None,
        "expectancy": round(sum(pnls) / len(pnls), 2) if pnls else None,
        "gross_loss": gross_loss,
    }


def _breakdown(key: str, label: str, columns: list, groups: list, note: str, stamp: dict) -> dict:
    return {"key": key, "label": label, "columns": columns, "rows": groups, "note": note, **stamp}


async def _load_book_live(pool, first: Optional[date], last: date) -> dict:
    """Every live figure on the page except the equity curve, from one read (R-IV.705(b)).

    The exclusions are the census's own: a row with `basis_incomplete_reason`, a return past
    -100% of basis, or no recorded `realized_pnl` is COUNTED and never averaged in. So each
    breakdown row's n is the counted population of that row, and the scope count is the whole
    census -- two different numbers on purpose, each saying which it is.
    """
    where, params = _census_where(first, last)
    rows = await pool.fetch(
        "SELECT realized_pnl, cost_basis, basis_incomplete_reason, max_loss, structure, ticker, "
        "entry_date, exit_date, strategy_tag, signal_id, account FROM unified_positions "
        f"WHERE {where}", *params)

    counted, total, linked = [], 0, 0
    opened_after_cutoff, untagged_after_cutoff = 0, 0
    for r in rows:
        total += 1
        # R-IV.705(e): how many closes can be traced back to the signal that produced them. The
        # strategies slot is empty because of THIS, not because the signals are ungraded.
        if r["signal_id"]:
            linked += 1
        opened = _mt_date(r["entry_date"])
        if opened is not None and opened >= BUCKET_CUTOFF:
            opened_after_cutoff += 1
            if not r["strategy_tag"]:
                untagged_after_cutoff += 1
        if r["basis_incomplete_reason"]:
            continue
        pnl, basis = r["realized_pnl"], r["cost_basis"]
        if pnl is not None and basis and float(basis) != 0 and float(pnl) / abs(float(basis)) < -1:
            continue
        if pnl is None:
            continue
        closed = _mt_date(r["exit_date"])
        counted.append({
            "pnl": float(pnl),
            "max_loss": float(r["max_loss"]) if r["max_loss"] is not None else None,
            "structure": (r["structure"] or "unrecorded").replace("_", " "),
            "ticker": r["ticker"] or "unrecorded",
            "opened": opened, "closed": closed,
            "held": (closed - opened).days if (opened and closed) else None,
        })

    whole = _agg(counted)
    dates = sorted(r["closed"] for r in counted if r["closed"])
    span = {"from": dates[0].isoformat(), "to": dates[-1].isoformat()} if dates else None

    # loss_vs_risk: of the max they had defined, how much they actually gave back. POOLED over the
    # losers that carry a max loss -- and its n is NOT the loser count, because `max_loss` is on
    # a minority of them. A rate quoting the wider n would be quoting a sample it was not drawn from.
    losers = [r for r in counted if r["pnl"] < 0]
    defined = [r for r in losers if r["max_loss"] and r["max_loss"] > 0]
    loss_vs_risk = (round(sum(abs(r["pnl"]) for r in defined) / sum(r["max_loss"] for r in defined), 4)
                    if defined else None)

    def _group(get) -> Dict[object, list]:
        out: Dict[object, list] = {}
        for r in counted:
            k = get(r)
            if k is None:
                continue
            out.setdefault(k, []).append(r)
        return out

    def _hold_bucket(r):
        if r["held"] is None:
            return None
        for name, lo, hi in HOLD_BUCKETS:
            if lo <= r["held"] <= hi:
                return name
        return None

    by_structure = _group(lambda r: r["structure"])
    by_ticker = _group(lambda r: r["ticker"])
    by_hold = _group(_hold_bucket)
    by_weekday = _group(lambda r: WEEKDAYS[r["opened"].weekday()] if r["opened"] else None)
    gross_loss_all = whole["gross_loss"] or 0

    def _rows(groups, cols, order=None):
        keys = order if order else sorted(groups, key=lambda k: -_agg(groups[k])["n"])
        out = []
        for k in keys:
            if k not in groups:
                continue
            a = _agg(groups[k])
            row = [k]
            for c in cols:
                if c == "n":
                    row.append(a["n"])
                elif c == "win":
                    row.append(a["win"])
                elif c == "net":
                    row.append(a["net"])
                elif c == "pf":
                    row.append(a["pf"])
                elif c == "expectancy":
                    row.append(a["expectancy"])
                elif c == "share_of_losses":
                    row.append(round(a["gross_loss"] / gross_loss_all, 4) if gross_loss_all else None)
            out.append(row)
        return out

    return {
        "span": span,
        "counted": len(counted),
        "total": total,
        "expectancy": whole["expectancy"],
        "profit_factor": whole["pf"],
        "avg_win_loss": ([round(sum(p["pnl"] for p in counted if p["pnl"] > 0)
                                / max(len([p for p in counted if p["pnl"] > 0]), 1), 2),
                          round(sum(p["pnl"] for p in counted if p["pnl"] < 0)
                                / max(len([p for p in counted if p["pnl"] < 0]), 1), 2)]
                         if counted else None),
        "avg_win_n": len([p for p in counted if p["pnl"] > 0]),
        "avg_loss_n": len([p for p in counted if p["pnl"] < 0]),
        "loss_vs_risk": loss_vs_risk,
        "loss_vs_risk_n": len(defined),
        "losers": len(losers),
        "linked_to_signal": linked,
        "untagged_after_cutoff": untagged_after_cutoff,
        "opened_after_cutoff": opened_after_cutoff,
        "breakdowns": {
            "structure": _rows(by_structure, ["n", "win", "net", "pf", "share_of_losses"]),
            "ticker": _rows(by_ticker, ["n", "win", "net", "pf"]),
            "hold": _rows(by_hold, ["n", "win", "net", "expectancy"],
                          order=[b[0] for b in HOLD_BUCKETS]),
            "weekday": _rows(by_weekday, ["n", "win", "net"], order=list(WEEKDAYS)),
        },
    }


async def _load_equity(pool) -> dict:
    """One balance curve per tracked account, each carrying its own span (R-IV.705(c)/(d)).

    THE SPELLINGS ARE THE WHOLE PROBLEM. `balance_snapshots.account_name` changed vocabulary on
    2026-08-27: the Roth's 144 days are stored as 'Fidelity Roth' and then 'FIDELITY_ROTH', and a
    read on the canonical key alone returns 30 of them while looking complete. `scope_sql` matches
    every spelling an account was stored under, EXACTLY -- which is also why
    `config.accounts.normalize_account` must not be used here: its `_key()` folds underscores into
    spaces, so the parked 'Fidelity 401A' mutual-fund rows (to 2026-07-23, a different pot) would
    resolve to FIDELITY_401A and join a curve they are not part of. FIDELITY_401A has no historical
    spellings by design (models/accounts.py:77-83).
    """
    from models.accounts import CANONICAL_ACCOUNTS, display_name as _display, scope_sql

    out = []
    for acct in CANONICAL_ACCOUNTS:
        clause, sparams = scope_sql(acct, column="account_name")
        snaps = await pool.fetch(
            f"SELECT snapshot_date, balance, account_name FROM balance_snapshots WHERE {clause} "
            "ORDER BY snapshot_date", *sparams)
        if not snaps:
            out.append({"account": acct, "account_display": _display(acct), "points": [],
                        "days": 0, "off_reason": "the hub holds no balance snapshots for this account."})
            continue
        cash = await pool.fetch(
            f"SELECT activity_date, amount, flow_type FROM cash_flows WHERE {clause.replace('account_name', 'account_name')} "
            "ORDER BY activity_date", *sparams)

        points = [{"d": _cal_date(r["snapshot_date"]).isoformat(), "v": float(r["balance"])}
                  for r in snaps if r["balance"] is not None]
        spellings = sorted({(r["account_name"] or "") for r in snaps})
        first_day = points[0]["d"] if points else None
        last_day = points[-1]["d"] if points else None

        ext_by_day: Dict[str, float] = {}
        ext_first, ext_count, unclassified = None, 0, set()
        for c in cash:
            kind = (c["flow_type"] or "").upper()
            day = _cal_date(c["activity_date"])
            if kind in EXTERNAL_FLOWS:
                ext_count += 1
                if ext_first is None or day < ext_first:
                    ext_first = day
                ext_by_day[day.isoformat()] = ext_by_day.get(day.isoformat(), 0.0) + float(c["amount"] or 0)
            elif kind not in INTERNAL_FLOWS and day and first_day and day.isoformat() >= first_day:
                unclassified.add(kind or "(blank)")

        # Coverage, as R-IV.705(d) defines it: the recorded cash events must begin at or before the
        # curve does, or the earlier days' returns cannot be told from deposits.
        off = None
        if unclassified:
            off = ("the ledger holds cash events this page cannot classify as deposits or earnings ("
                   + ", ".join(sorted(unclassified)) + "), so a return net of deposits cannot be trusted.")
        elif ext_first is None:
            off = ("the hub has no recorded deposit or withdrawal for this account, so a change in "
                   "balance cannot be told from money moving in or out.")
        elif first_day and ext_first.isoformat() > first_day:
            off = ("recorded cash events begin " + ext_first.isoformat() + ", after this curve begins "
                   + first_day + ", so the earlier days' returns cannot be told from deposits.")

        rets, ret_days = [], []
        if off is None:
            for i in range(1, len(points)):
                prev, cur = points[i - 1]["v"], points[i]["v"]
                if prev <= 0:
                    continue
                flow = ext_by_day.get(points[i]["d"], 0.0)
                rets.append((cur - prev - flow) / prev)
                ret_days.append(points[i]["d"])

        drawdown, sharpe = None, None
        if rets:
            # Drawdown on the NET-OF-CASH index, in percent. A dollar figure would need a base, and
            # every base available here is a deposit away from being wrong.
            idx, peak, worst = 1.0, 1.0, 0.0
            peak_i, from_i, to_i = 0, 0, 0
            for i, r in enumerate(rets):
                idx *= (1 + r)
                if idx > peak:
                    peak, peak_i = idx, i + 1
                fall = idx / peak - 1
                if fall < worst:
                    worst, from_i, to_i = fall, peak_i, i + 1
            if worst < 0:
                drawdown = {"pct": round(worst, 4), "from_index": from_i, "to_index": to_i,
                            "from": points[from_i]["d"], "to": points[to_i]["d"]}
            if len(rets) >= 2:
                mean = sum(rets) / len(rets)
                var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
                sd = var ** 0.5
                sharpe = ({"value": round(mean / sd * (252 ** 0.5), 2), "n": len(rets),
                           "rough": len(rets) < SHARPE_MIN_N}
                          if sd > 0 else {"value": None, "n": len(rets), "rough": True})

        out.append({
            "account": acct, "account_display": _display(acct),
            "points": points, "from": first_day, "to": last_day, "days": len(points),
            "spellings_read": spellings,
            # True of every line here, so it is said on every line: a balance rises when money is
            # paid in, and this page never lets that read as a gain.
            "line_label": "balance — includes deposits/withdrawals",
            "cash": {"events": ext_count,
                     "first": ext_first.isoformat() if ext_first else None,
                     "spans": off is None},
            "drawdown": drawdown, "sharpe": sharpe, "off_reason": off,
        })
    return {"accounts": out}


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
    # R-IV.705: through the ONE predicate helper, so every live figure on the page is drawn from
    # the same population. A second reader writing the same WHERE clause by hand is the drift
    # ABACUS reported against the positions panel.
    where, params = _census_where(first, last)
    rows = await pool.fetch(
        f"SELECT realized_pnl, cost_basis, basis_incomplete_reason, account FROM unified_positions "
        f"WHERE {where}",
        *params,
    )

    # R-IV.650(b)3 — the same census, kept PER ACCOUNT and pooled. Every exclusion is counted
    # against the account whose row it was, so a per-account coverage line is answerable and a
    # reader can see which book the excluded rows came from.
    def _blank():
        return {"pnls": [], "returns": [], "total": 0,
                "basis_incomplete": 0, "return_below_neg100pct": 0, "no_realized_pnl": 0}
    by: Dict[Optional[str], dict] = {}

    for r in rows:
        # `.get`, not `r["account"]`: a row from a source that does not carry the column is an
        # UNATTRIBUTED trade, not a crash. It lands in its own bucket and says so.
        key = (r.get("account") if hasattr(r, "get") else r["account"]) or None
        acct = by.setdefault(key, _blank())
        acct["total"] += 1
        if r["basis_incomplete_reason"]:
            acct["basis_incomplete"] += 1
            continue
        pnl = r["realized_pnl"]
        basis = r["cost_basis"]
        ret = None
        if pnl is not None and basis and float(basis) != 0:
            ret = float(pnl) / abs(float(basis))
            if ret < -1:
                acct["return_below_neg100pct"] += 1
                continue
        if pnl is None:
            acct["no_realized_pnl"] += 1
            continue
        acct["pnls"].append(float(pnl))
        # The expected return carries its OWN n: a trade whose basis is unknown has a P&L but
        # no return, so averaging it in at zero would quietly drag the mean toward nothing.
        if ret is not None:
            acct["returns"].append(ret)

    def _block(acc: dict, account: Optional[str]) -> dict:
        counted = len(acc["pnls"])
        wins = sum(1 for p in acc["pnls"] if p > 0)
        rets = acc["returns"]
        return {
            "account": account,
            # A key is not a label: the display name is served, never inferred by a reader.
            "account_display": display_name(account) if account else None,
            "net_profit": round(sum(acc["pnls"]), 2) if counted else None,
            "win_rate": round(wins / counted, 4) if counted else None,
            "win_rate_n": counted,
            # Mean realised return per trade. NULL, never 0, when nothing in this book has a
            # usable basis -- "no trade here can be measured" is not "the average is nothing".
            "expected_return": round(sum(rets) / len(rets), 4) if rets else None,
            "expected_return_n": len(rets),
            "coverage": {
                "predicate": "LOWER(status) IN ('closed','expired'), windowed on exit_date",
                "total": acc["total"],
                "counted": counted,
                "excluded": {
                    "basis_incomplete": acc["basis_incomplete"],
                    "return_below_neg100pct": acc["return_below_neg100pct"],
                    "no_realized_pnl": acc["no_realized_pnl"],
                },
            },
        }

    # COMBINED IS POOLED, NOT AVERAGED. Pooling every counted trade IS the figure weighted by
    # trade count; averaging the three per-account rates would weight a six-trade book the same
    # as a forty-trade one and quietly answer a different question.
    pooled = _blank()
    for acc in by.values():
        pooled["pnls"].extend(acc["pnls"])
        pooled["returns"].extend(acc["returns"])
        for k in ("total", "basis_incomplete", "return_below_neg100pct", "no_realized_pnl"):
            pooled[k] += acc[k]

    combined = _block(pooled, None)
    accounts = [_block(by[k], k) for k in sorted(by, key=lambda x: (x is None, x or ""))]
    out = dict(combined)
    out["accounts"] = accounts
    out["combined_is_pooled"] = True
    return out


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
    # R-IV.705(b): the rest of the arithmetic, off the same census, each figure with its own n and
    # the span of closes it was drawn from -- because a rate without its n and a figure without its
    # window are the two ways this page could still mislead while being technically live.
    live = await _load_book_live(pool, live_first, live_last)
    span = live["span"]
    for st in out["stats"]:
        if st["key"] == "net_profit":
            st["value"] = book["net_profit"]
            st["coverage"] = book["coverage"]
            st["span"] = span
            st.update(live_stamp)
        elif st["key"] == "win_rate":
            st["value"] = book["win_rate"]
            st["n"] = book["win_rate_n"]
            st["coverage"] = book["coverage"]
            st["span"] = span
            st.update(live_stamp)
        elif st["key"] == "expectancy":
            st["value"] = live["expectancy"]
            st["n"] = live["counted"]
            st["span"] = span
            st["coverage"] = book["coverage"]
            st["meaning"] = ("The mean realized result of one counted close in this window. Rows the "
                             "census excludes -- no recorded P&L, incomplete basis, a return past "
                             "-100% of basis -- are counted in the census and are not in this mean.")
            st.update(live_stamp)
        elif st["key"] == "profit_factor":
            st["value"] = live["profit_factor"]
            st["n"] = live["counted"]
            st["span"] = span
            st["coverage"] = book["coverage"]
            st["meaning"] = ("Dollars won per dollar lost, pooled over the counted closes. Null, not "
                             "a large number, when nothing lost: there is no ratio to a zero.")
            st.update(live_stamp)
        elif st["key"] == "avg_win_loss":
            st["value"] = live["avg_win_loss"]
            st["n"] = live["counted"]
            st["span"] = span
            st["coverage"] = book["coverage"]
            st["meaning"] = ("The average winner beside the average loser, over %d winners and %d "
                             "losers." % (live["avg_win_n"], live["avg_loss_n"]))
            st.update(live_stamp)
        elif st["key"] == "loss_vs_risk":
            # R-IV.705(g): live ONLY with its n, because `max_loss` is recorded on a minority of
            # the losers and a rate over 43% of them reads as a rate over all of them.
            st["value"] = live["loss_vs_risk"]
            st["n"] = live["loss_vs_risk_n"]
            st["span"] = span
            st["coverage"] = {"predicate": "losing counted closes that carry a max loss",
                              "total": live["losers"], "counted": live["loss_vs_risk_n"],
                              "excluded": {"no_max_loss_recorded": live["losers"] - live["loss_vs_risk_n"]}}
            st["meaning"] = ("Of the maximum loss these trades had defined, the share actually given "
                             "back. Drawn from the %d of %d losing closes that carry a max loss; the "
                             "rest record none." % (live["loss_vs_risk_n"], live["losers"]))
            st.update(live_stamp)

    # Drawdown and Sharpe are NOT tiles any more (R-IV.705(d)). They are properties of a CURVE, and
    # the curves are per account with different spans and different cash-event coverage -- so a
    # single top-level figure has no denominator, and a fixture one beside a live band would be two
    # numbers for one fact. They live on the equity card, next to the span they were measured over.
    out["stats"] = [st for st in out["stats"] if st["key"] not in ("max_drawdown", "sharpe")]

    # The scope line names the accounts rather than counting them: "Both accounts" was written when
    # there were two, and there are three (R-IV.705(b)).
    from models.accounts import CANONICAL_ACCOUNTS as _CANON, display_name as _disp
    out["scope"] = {"label": " · ".join([_disp(a) or a for a in _CANON]),
                    "closed_positions": live["total"], "accounts": len(_CANON), **live_stamp}

    # The four breakdowns, live. `discipline` is left on the fixture and says so: on these closed
    # rows `time_stop` is recorded 1 time, `stop_type` 2 and `invalidation` 2, so every line of it
    # but one is unmeasurable until the capture path exists (BUILD gap 3).
    _BD = {
        "structure": ("By structure",
                      [["Structure", "text"], ["n", "int"], ["Win", "pct"], ["Net", "usd"],
                       ["PF", "ratio"], ["Share of losses", "bar"]]),
        "ticker": ("By ticker", [["Ticker", "text"], ["n", "int"], ["Win", "pct"], ["Net", "usd"],
                                 ["PF", "ratio"]]),
        "hold": ("By hold time", [["Held", "text"], ["n", "int"], ["Win", "pct"], ["Net", "usd"],
                                  ["Expectancy", "usd_cents"]]),
        "weekday": ("By weekday", [["Entered on", "text"], ["n", "int"], ["Win", "pct"],
                                   ["Net", "usd"]]),
    }
    _note = ("Every row's n is the counted closes in it, over %s. Hold time is calendar days from "
             "entry to exit; the weekday is the day it was OPENED, both in Mountain Time."
             % (span["from"] + " to " + span["to"] if span else "this window"))
    live_bd = [_breakdown(k, _BD[k][0], _BD[k][1], live["breakdowns"][k], _note, live_stamp)
               for k in ("structure", "ticker", "hold", "weekday")]
    out["breakdowns"] = live_bd + [b for b in out["breakdowns"] if b["key"] == "discipline"]
    for b in out["breakdowns"]:
        if b["key"] == "discipline":
            b["note"] = ("Sample data. On the closed rows in this window the hub holds a time stop on "
                         "1, a stop type on 2 and an invalidation on 2, because nothing can write "
                         "those fields yet (BUILD gap 3). Every line here but the bucket tag is "
                         "unmeasurable until it can.")

    # The leaks: ONE of the six is measurable today, and it is not the one the fixture made it.
    _leak_note = {
        "Adding to losers": "Sample data. Needs the position's mark at the moment a later lot was added; the hub keeps one current price and no per-position price history.",
        "Far-OTM tails": "Sample data. Needs the spot price at entry: daily bars cover 92 of the book's 173 tickers.",
        "Overridden time stops": "Sample data. A time stop is recorded on 1 of the closed rows in this window (BUILD gap 3).",
        "Index ETF verticals": "Sample data. Waits on a ticker classification the principal has not made; nothing maps a ticker to this category.",
        "Commodity sleeve": "Sample data. Same classification as above.",
    }
    for it in out["leaks"]["items"]:
        if it["label"] == "Untagged trades":
            # R-IV.705(f). Buckets began at TA-058's cutoff, so a row closed before it is untagged
            # BY DESIGN -- counting those would indict the principal for a field that did not exist.
            it["label"] = "Untagged trades, opened since the bucket cutoff"
            it["n"] = live["untagged_after_cutoff"]
            # The population it is counted against goes in a FIELD, not into the prose: a count
            # inside a sentence does not change with the range, and this one does (charter R2).
            it["of_n"] = live["opened_after_cutoff"]
            it["amount"] = None
            it["detail"] = ("No bucket recorded, among the closes in this window opened on or after "
                            + BUCKET_CUTOFF.isoformat() + " — TA-058's cutoff, per "
                            "C:/lane-state/POSITIONS.md:1839 and :428. Rows opened before it had no "
                            "bucket field to fill and are not counted here. No dollar figure: a "
                            "missing tag has no cost of its own.")
            it.update(live_stamp)
        else:
            it["source"] = "mock"
            it["detail"] = _leak_note.get(it["label"], it.get("detail") or "")
    out["leaks"]["partly_live"] = True

    # R-IV.705(e): no figure from `signal_outcomes` reaches this page -- that table holds Triton
    # rows from the sealed holdout and from the forward window's blind weeks, so a per-signal hit
    # rate here would expose both. What is actually missing is the LINK.
    out["strategies"]["note"] = (
        "No figures yet, and the reason is not that the signals are ungraded. Trades are not linked "
        "to the signals that produced them: a signal id is recorded on %d of the %d closed positions "
        "in this window, so there is no population to put money against. Revisited after the Triton "
        "look-back, not before." % (live["linked_to_signal"], live["total"]))

    out["equity"] = {**(await _load_equity(pool)), **live_stamp}

    # R-IV.650(b)3: expected return per trade, LIVE, with its own n -- which is not the win
    # rate's n. A trade whose basis is unknown has a P&L but no return, so the two counts differ
    # and a rate that borrowed the other's n would be quoting a sample it was not drawn from.
    out["stats"].append({
        "key": "expected_return", "label": "Expected return per trade", "format": "pct",
        "value": book["expected_return"], "n": book["expected_return_n"],
        "coverage": book["coverage"],
        "meaning": ("The mean realised return of the closed trades in this window, as a share of "
                    "each trade's own cost basis. Trades whose basis the book never recorded have "
                    "no return and are left out, which is why this count can be lower than the "
                    "win rate's."),
        **live_stamp,
    })

    # Per account, beside the combined figures. The combined row is POOLED over every counted
    # trade, so it is weighted by trade count rather than being an average of the three rates.
    out["accounts"] = book["accounts"]
    out["combined_is_pooled"] = book["combined_is_pooled"]

    out["range"] = rng
    out["range_applied"] = True
    return out
