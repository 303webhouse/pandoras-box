"""The P&L dashboard's data — R-IV.1315.

ONE DEFINITION PER FIGURE, and the definition travels WITH the figure. Every block below carries
its own `n`, its window, and a `basis` string naming the columns it came from, because the whole
history of this page is captions drifting away from the fields under them (R-IV.1262, R-IV.1270).

THE RULES, as ruled in R-IV.1315(b):

  * Realized P&L is CLOSED LOTS ON `trade_date`, NET OF FEES. Fees need no separate term: they are
    already inside `cost_per_unit` and `proceeds_per_unit`. Verified rather than assumed -- closure
    1974 has an acquisition price of 0.08 with 0.04 of fees on 1 contract at multiplier 100, and
    its `cost_per_unit` is 0.0804 = (0.08 * 100 + 0.04) / 100. And `realized` reconciles to
    `qty * (proceeds_per_unit - cost_per_unit) * multiplier` to the cent on every row checked.
  * A LOSS is realized P&L BELOW zero.
  * A SCRATCH is EXACTLY zero. It is neither a win nor a loss, so it is OUT of the win-rate
    denominator and reported on its own. October 2026 has one, so this is not a hypothetical.

WHAT IS NOT HERE, and why it is not faked:

  * BY BUCKET cannot be built. `unified_positions.bucket` holds B1 (5 rows) and B2 (8) against 612
    NULLs book-wide; of the October closes, 57 of 66 have no bucket at all. The mock's
    core/tactical/lotto vocabulary does not exist in this book. The block serves its own fill rate
    and says "not available yet" (R-IV.1315(c)).
  * UNREALIZED IS A FLOOR, not a total: 6 of 28 open rows carry no price, so the sum covers 22.
  * THE MARK TIME IS NOT ONE TIME. The marks span 38.8 hours, so a single "marked 15:59" would be
    a claim about 28 rows that is true of one. The oldest is served, with the spread.

REALIZED AND UNREALIZED NEVER MIX (R-IV.1315(c)). They are separate keys, computed from separate
tables, and nothing in this module adds them.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from models.accounts import CANONICAL_ACCOUNTS, display_name
from services.position_economics import money as _money

MT = ZoneInfo("America/Denver")
PERIODS = ("week", "month", "year", "all")

#: The first closure in the book, so "all" has a left edge that is a fact rather than a guess.
_FIRST_TRADE_SQL = "SELECT MIN(trade_date) AS d FROM position_lot_closures WHERE trade_date IS NOT NULL"

#: Every closure the page can place, with the columns each figure needs. One read, because the
#: alternative is six reads that can disagree with each other about the same window.
_CLOSURES_SQL = """
    SELECT c.id, c.realized, c.trade_date, c.qty,
           p.position_id, p.account, p.ticker, p.structure, p.bucket,
           la.fill_time AS acquired_at
      FROM position_lot_closures c
      JOIN unified_positions p ON p.position_id = c.position_id
      LEFT JOIN position_lots la ON la.id = c.acquired_lot_id
     WHERE UPPER(COALESCE(p.status, '')) <> 'DUPLICATE_OF'
       AND c.trade_date IS NOT NULL
     ORDER BY c.trade_date, c.id
"""

#: The open book. `unrealized_pnl` is the hub's own lot-derived figure; this module never computes
#: one from a mark, which on a spread is wrong (R-IV.662).
_OPEN_SQL = """
    SELECT p.position_id, p.account, p.ticker, p.structure, p.bucket, p.bucket_reason,
           p.unrealized_pnl, p.current_price, p.mark_as_of, p.price_updated_at, p.mark_status
      FROM unified_positions p
     WHERE UPPER(COALESCE(p.status, '')) = 'OPEN'
"""

#: Closures with no trade date: outside every period figure here, as R-IV.1270(b) requires.
_UNDATED_SQL = """
    SELECT c.id, c.realized, p.account, p.ticker
      FROM position_lot_closures c
      JOIN unified_positions p ON p.position_id = c.position_id
     WHERE UPPER(COALESCE(p.status, '')) <> 'DUPLICATE_OF' AND c.trade_date IS NULL
     ORDER BY c.id
"""

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _day_of(value):
    """The R-IV.726 rule, for `position_lots.fill_time`: midnight UTC is a DAY taken as written,
    anything else is a MOMENT converted to the principal's calendar."""
    if value is None:
        return None
    if not isinstance(value, datetime):
        return value
    v = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    utc = v.astimezone(timezone.utc)
    if (utc.hour, utc.minute, utc.second, utc.microsecond) == (0, 0, 0, 0):
        return utc.date()
    return v.astimezone(MT).date()


def resolve_period(key: str, today: date, first: Optional[date]) -> dict:
    """The window, and the one BEFORE it for the comparison.

    THE CALENDAR IS THE PRINCIPAL'S, not the server's. `trade_date` is a bare DATE, so it is
    compared against Mountain-Time boundaries -- the server runs UTC and is already "tomorrow"
    every evening after 6 PM MT, which would roll a month a day early.
    """
    key = key if key in PERIODS else "month"
    if key == "week":                                    # Monday-anchored, the trading week
        start = today - timedelta(days=today.weekday())
        prior_start, prior_end = start - timedelta(days=7), start - timedelta(days=1)
        label, prior_label = "This week", "Prior week"
    elif key == "month":
        start = today.replace(day=1)
        prior_end = start - timedelta(days=1)
        prior_start = prior_end.replace(day=1)
        label, prior_label = MONTHS[start.month - 1], MONTHS[prior_start.month - 1]
    elif key == "year":
        start = date(today.year, 1, 1)
        prior_start, prior_end = date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
        label, prior_label = str(today.year), str(today.year - 1)
    else:
        start = first or today
        prior_start = prior_end = None
        label, prior_label = "All time", None
    return {
        "key": key, "label": label,
        "from": start.isoformat(), "to": today.isoformat(),
        "prior": ({"label": prior_label, "from": prior_start.isoformat(),
                   "to": prior_end.isoformat()} if prior_start else None),
        "calendar": "America/Denver, the principal's calendar day",
    }


def _agg(rows: List[dict]) -> dict:
    """Wins, losses and SCRATCHES, each counted as its own thing.

    The win rate's denominator is wins + losses. A scratch is excluded from it and reported beside
    it: folding scratches into the denominator quietly lowers the rate for trades that neither won
    nor lost, and folding them into either side is worse.
    """
    wins = [r["realized"] for r in rows if r["realized"] > 0]
    losses = [r["realized"] for r in rows if r["realized"] < 0]
    scratches = [r for r in rows if r["realized"] == 0]
    decided = len(wins) + len(losses)
    gross_w = sum(wins, Decimal("0"))
    gross_l = sum(losses, Decimal("0"))
    return {
        "realized": _money(sum((r["realized"] for r in rows), Decimal("0"))) if rows else None,
        "closes": len(rows),
        "wins": len(wins), "losses": len(losses), "scratches": len(scratches),
        # NULL, never 0: "nothing was decided" is not "everything lost".
        "win_rate": (round(len(wins) / decided, 4) if decided else None),
        "win_rate_n": decided,
        "avg_win": _money(gross_w / len(wins)) if wins else None,
        "avg_loss": _money(gross_l / len(losses)) if losses else None,
        "avg_win_n": len(wins), "avg_loss_n": len(losses),
        # The payoff ratio, and NULL when there is no loser to divide by -- not a large number.
        "payoff": (round(float(gross_w / len(wins)) / abs(float(gross_l / len(losses))), 2)
                   if wins and losses else None),
        "gross_wins": _money(gross_w) if wins else None,
        "gross_losses": _money(gross_l) if losses else None,
        "profit_factor": (round(float(gross_w / -gross_l), 3) if losses and gross_l != 0 else None),
        "profit_factor_note": (None if losses else
                               "no losing close in this window, so there is no ratio to divide by"),
    }


def _what(r: dict) -> str:
    """The "what" column: the structure, and the account that holds it."""
    struct = str(r.get("structure") or "").replace("_", " ").strip() or "position"
    acct = display_name(r.get("account")) if r.get("account") else None
    return struct + ((" · " + acct) if acct else "")


def _recent(rows: List[dict], limit: int = 12) -> List[dict]:
    """One row per CLOSE EVENT -- a position closed on a day -- not one per lot.

    DAYS HELD IS PER LOT, and a multi-lot close has no single answer: 20 of October's 66 closes are
    multi-lot and 13 of those hold their lots for DIFFERENT lengths. So the range is served
    whenever the lots disagree, and a single number only when they agree. Collapsing a 3-to-22-day
    spread into one figure would be an invented average presented as a fact.
    """
    by: Dict[tuple, dict] = {}
    for r in rows:
        k = (r["position_id"], r["trade_date"])
        g = by.setdefault(k, {"trade_date": r["trade_date"], "ticker": r["ticker"],
                              "what": _what(r), "account": r["account"],
                              "account_display": display_name(r["account"]) if r["account"] else None,
                              "realized": Decimal("0"), "lots": 0, "days": []})
        g["realized"] += r["realized"]
        g["lots"] += 1
        held = _day_of(r.get("acquired_at"))
        if held is not None and r["trade_date"] is not None:
            g["days"].append((r["trade_date"] - held).days)
    out = []
    for g in sorted(by.values(), key=lambda x: (x["trade_date"], x["ticker"]), reverse=True)[:limit]:
        days = sorted(d for d in g["days"] if d is not None)
        out.append({
            "trade_date": g["trade_date"].isoformat(),
            "ticker": g["ticker"], "what": g["what"],
            "account_display": g["account_display"],
            "realized": _money(g["realized"]),
            "lots": g["lots"],
            "days": (days[0] if days and days[0] == days[-1] else None),
            "days_range": ([days[0], days[-1]] if days and days[0] != days[-1] else None),
            "days_unavailable": (None if days else
                                 "no acquisition fill time on this close's lots"),
        })
    return out


def _curve(rows: List[dict], year: int) -> dict:
    """The year-to-date cumulative realized line, with one bar per ISO week.

    Weeks with no close are PRESENT with a zero bar rather than skipped: a gap drawn as a
    continuous line implies trading that did not happen.
    """
    ytd = [r for r in rows if r["trade_date"].year == year]
    weeks: Dict[tuple, Decimal] = {}
    for r in ytd:
        iso = r["trade_date"].isocalendar()
        weeks[(iso[0], iso[1])] = weeks.get((iso[0], iso[1]), Decimal("0")) + r["realized"]
    if not ytd:
        return {"points": [], "ytd_net": None, "year": year,
                "empty_reason": "no closure in %d carries a trade date" % year}
    first_iso = min(r["trade_date"] for r in ytd).isocalendar()
    last_iso = max(r["trade_date"] for r in ytd).isocalendar()
    pts, run = [], Decimal("0")
    for w in range(first_iso[1], last_iso[1] + 1):
        net = weeks.get((first_iso[0], w), Decimal("0"))
        run += net
        pts.append({"week": "%d-W%02d" % (first_iso[0], w),
                    "net": _money(net), "cumulative": _money(run),
                    "closes": sum(1 for r in ytd if r["trade_date"].isocalendar()[1] == w)})
    return {"points": pts, "ytd_net": _money(run), "year": year,
            "basis": "position_lot_closures.realized, grouped by ISO week of trade_date"}


async def load_pnl(pool, period: str = "month", account: str = "ALL") -> dict:
    first_row = await pool.fetchrow(_FIRST_TRADE_SQL)
    first = first_row["d"] if first_row else None
    rows = [dict(r) for r in await pool.fetch(_CLOSURES_SQL)]
    for r in rows:
        r["realized"] = Decimal(str(r["realized"] or 0))
    open_rows = [dict(r) for r in await pool.fetch(_OPEN_SQL)]
    undated = [dict(r) for r in await pool.fetch(_UNDATED_SQL)]

    today = datetime.now(MT).date()
    win = resolve_period(period, today, first)
    acct = (account or "ALL").upper()
    in_scope = (lambda r: True) if acct == "ALL" else (lambda r: (r["account"] or "") == acct)

    f, t = date.fromisoformat(win["from"]), date.fromisoformat(win["to"])
    cur = [r for r in rows if in_scope(r) and f <= r["trade_date"] <= t]
    out = {"period": win, "account": acct,
           "accounts": [{"key": "ALL", "label": "All accounts"}]
                       + [{"key": a, "label": display_name(a) or a} for a in CANONICAL_ACCOUNTS],
           "realized_basis": ("position_lot_closures.realized, windowed on trade_date, "
                              "DUPLICATE_OF excluded. Already NET OF FEES: fees are inside "
                              "cost_per_unit and proceeds_per_unit."),
           **_agg(cur)}

    if win["prior"]:
        pf, pt = date.fromisoformat(win["prior"]["from"]), date.fromisoformat(win["prior"]["to"])
        prior = [r for r in rows if in_scope(r) and pf <= r["trade_date"] <= pt]
        out["prior"] = {**win["prior"], "realized": _money(sum((r["realized"] for r in prior),
                                                               Decimal("0"))) if prior else None,
                        "closes": len(prior)}
    else:
        out["prior"] = None

    out["by_account"] = [
        {"account": a, "account_display": display_name(a) or a,
         **{k: v for k, v in _agg([r for r in cur if (r["account"] or "") == a]).items()
            if k in ("realized", "closes", "wins", "losses", "scratches", "win_rate", "win_rate_n")}}
        for a in CANONICAL_ACCOUNTS]

    # BY BUCKET: served as its own fill rate and a refusal, never as a chart of 9 rows out of 66.
    filled = [r for r in cur if r["bucket"]]
    buckets: Dict[str, Decimal] = {}
    for r in filled:
        buckets[r["bucket"]] = buckets.get(r["bucket"], Decimal("0")) + r["realized"]
    out["by_bucket"] = {
        "unavailable": ("not available yet" if len(filled) * 2 < len(cur) else None),
        "closes_with_a_bucket": len(filled), "closes_total": len(cur),
        "vocabulary": sorted(buckets),
        "rows": [{"bucket": k, "realized": _money(v),
                  "closes": sum(1 for r in filled if r["bucket"] == k)}
                 for k, v in sorted(buckets.items())],
        # Prose for a page, so no backticks: they are markdown and render as literal ticks in
        # HTML, which is how a careful sentence ends up looking like a typo.
        "why": ("The bucket field is recorded on a minority of rows, so a split by it would "
                "describe the tagged few and read as the whole book. The values in use are B1 "
                "and B2; the mock's core/tactical/lotto are not vocabulary this book has."),
    }

    out["curve"] = _curve([r for r in rows if in_scope(r)], today.year)

    # UNREALIZED. Its own keys, its own table, never added to anything above.
    o = [r for r in open_rows if in_scope(r)]
    priced = [r for r in o if r["unrealized_pnl"] is not None]
    marks = [r["mark_as_of"] or r["price_updated_at"] for r in o
             if (r["mark_as_of"] or r["price_updated_at"])]
    now = datetime.now(timezone.utc)
    oldest = min(marks) if marks else None
    newest = max(marks) if marks else None
    out["unrealized"] = {
        "value": _money(sum((Decimal(str(r["unrealized_pnl"])) for r in priced), Decimal("0")))
                 if priced else None,
        "positions": len(o), "priced": len(priced), "unpriced": len(o) - len(priced),
        # A SUM OVER SOME OF THE ROWS IS A FLOOR. Named as one, as the Book tile's greeks are.
        "partial": len(priced) != len(o),
        "oldest_mark": oldest.isoformat() if oldest else None,
        "newest_mark": newest.isoformat() if newest else None,
        "oldest_mark_age_hours": (round((now - oldest).total_seconds() / 3600, 1)
                                  if oldest else None),
        "mark_source": ("mark_as_of where recorded, else price_updated_at"),
        "mark_as_of_n": sum(1 for r in o if r["mark_as_of"]),
        "unavailable": (None if priced else "no open position carries a price"),
        "why_oldest": ("the marks do not share one time, so the OLDEST is shown: a single "
                       "timestamp would be true of one row and claimed for all of them"),
        "basis": "unified_positions.unrealized_pnl on OPEN rows -- the hub's lot-derived figure",
    }

    out["recent"] = _recent(cur)
    out["date_unknown"] = {
        "count": len(undated),
        "total": _money(sum((Decimal(str(r["realized"] or 0)) for r in undated), Decimal("0")))
                 if undated else None,
        "rows": [{"closure_id": r["id"], "ticker": r["ticker"],
                  "account_display": display_name(r["account"]) if r["account"] else None,
                  "realized": _money(Decimal(str(r["realized"] or 0)))} for r in undated],
        "in_any_total": False,
        "note": ("closures with no trade_date, so no window can place them. Outside every figure "
                 "on this page, in every period (R-IV.1270(b))"),
    }
    out["computed_at"] = now.isoformat().replace("+00:00", "Z")
    out["preview"] = "pnl=v1"
    return out
