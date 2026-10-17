"""Find and repair unsettled captures in `stable_daily_bars`. R-IV.1203(c).

THE DEFECT. A session's row could be written while that session was still trading, so the
stored "close" was an intraday price and the stored high/low were a partial range. Measured on
2026-10-16: SPY stored 764.29 where the settled close was 763.25, and 764.29 is not any
session's close (10-14 was 769.60, 10-15 771.79) but does sit inside 10-16's intraday range.

WHY A CLOSE MISMATCH IS NOT ENOUGH TO CONVICT, and this is the whole difficulty.
`stable_daily_bars` is FULLY ADJUSTED -- `bars_yf` passes `auto_adjust=True`, so splits AND
dividends -- and R-IV.1203(c) rules that basis CORRECT for moving averages and breadth, so it
stays. Polygon's `adjusted=true` is split-only. The two bases therefore DISAGREE BY DESIGN on
every bar before a dividend, and calling that an unsettled capture would be a repair that
corrupts a correct row.

THE DISCRIMINATOR, which is about the shape of the disagreement rather than its size:

  A DIVIDEND (or split) ADJUSTMENT SCALES ALL FOUR PRICES BY ONE FACTOR. So stored/true is the
  same ratio for open, high, low and close. The bar is the same shape, moved.

  AN UNSETTLED CAPTURE TRUNCATES THE SESSION. The stored range sits INSIDE the true range --
  the high had not yet been made, or the low had not -- and the four ratios do not agree,
  because a partial session is a different shape and not a scaled one.

So a row is convicted only when its range is strictly inside the true range AND the four ratios
disagree. Anything else is reported as a basis difference and left alone. A repair that cannot
tell the two apart is worse than the defect.

NO SUBSTITUTION, and nothing is repaired on a vendor that would not answer.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bars_audit")

#: The census. Eight names, from api/darkpool_backfill_status.py's CENSUS -- the only 8-ticker
#: "core" set defined in this repo, and the one the lane record's "core-8" entries name
#: (SPY, SMH, IWM and QQQ all appear there). Cited rather than restated so the two cannot drift.
try:
    from api.darkpool_backfill_status import CENSUS as CORE8
except Exception:                                                # pragma: no cover
    CORE8 = ("SPY", "QQQ", "IWM", "SMH", "NVDA", "AAPL", "MSFT", "TSLA")

#: How far two prices may sit apart and still be the same number. These are 2-decimal quotes.
PRICE_TOL = 0.005

#: How far the four stored/true ratios may spread and still be called one scaling factor.
#: A dividend adjustment is exact to rounding; a truncated session is not close.
RATIO_SPREAD_TOL = 0.0008


def _ratio(stored: Optional[float], true: Optional[float]) -> Optional[float]:
    if stored is None or true in (None, 0):
        return None
    return stored / true


def classify_row(stored: Dict[str, Any], true: Dict[str, Any]) -> Dict[str, Any]:
    """Is this stored bar a match, a basis difference, or an unsettled capture?

    Pure, so the decision that authorises a WRITE is testable without a database or a vendor.
    """
    out: Dict[str, Any] = {"verdict": None, "why": None}
    sc, tc = stored.get("c"), true.get("c")
    if sc is None or tc is None:
        out.update(verdict="unreadable", why="a close is missing on one side")
        return out

    if abs(sc - tc) <= PRICE_TOL:
        out.update(verdict="match", why="close %.4f agrees" % tc)
        return out

    ratios = [r for r in (_ratio(stored.get(k), true.get(k)) for k in ("o", "h", "l", "c"))
              if r is not None]
    spread = (max(ratios) - min(ratios)) if len(ratios) >= 2 else None

    sh, sl, th, tl = stored.get("h"), stored.get("l"), true.get("h"), true.get("l")
    inside = (sh is not None and sl is not None and th is not None and tl is not None
              and sh <= th + PRICE_TOL and sl >= tl - PRICE_TOL
              and (sh < th - PRICE_TOL or sl > tl + PRICE_TOL))

    if spread is not None and spread <= RATIO_SPREAD_TOL:
        # One factor across all four: the bar is the same shape, moved. That is the adjustment
        # basis differing, which R-IV.1203(c) keeps.
        out.update(verdict="basis_difference",
                   why=("all four prices scale by ~%.6f (spread %.6f), so this is the "
                        "fully-adjusted basis differing from split-only -- left alone"
                        % (sum(ratios) / len(ratios), spread)))
        return out

    if inside:
        out.update(verdict="unsettled_capture",
                   why=("stored range [%.2f, %.2f] sits inside the settled range [%.2f, %.2f] "
                        "and the four ratios disagree (spread %s): the row was written before "
                        "the session finished"
                        % (sl, sh, tl, th, "n/a" if spread is None else "%.6f" % spread)))
        return out

    out.update(verdict="mismatch_unexplained",
               why=("close %.4f vs %.4f, ratios spread %s, stored range not inside the settled "
                    "range -- NOT repaired, because nothing here establishes which is right"
                    % (sc, tc, "n/a" if spread is None else "%.6f" % spread)))
    return out


async def audit(conn, tickers=CORE8, sessions: int = 5) -> Dict[str, Any]:
    """Compare the last `sessions` stored rows per ticker against Polygon. Reads only.

    R-IV.1203(c): "Re-fetch the last 5 sessions for the CORE8 and compare them to Polygon."
    """
    from stable_engine import bars_polygon

    findings: List[Dict[str, Any]] = []
    errors: List[str] = []
    first = True
    for t in tickers:
        rows = await conn.fetch(
            """SELECT date, o, h, l, c FROM stable_daily_bars
                WHERE ticker = $1 ORDER BY date DESC LIMIT $2""", t, int(sessions))
        if not rows:
            errors.append("%s: no stored rows" % t)
            continue
        days = sorted(str(r["date"])[:10] for r in rows)
        if not first:
            import asyncio
            await asyncio.sleep(bars_polygon.CALL_GAP_S)
        first = False
        try:
            bars = await bars_polygon.fetch_daily(
                t, _dt.date.fromisoformat(days[0]), _dt.date.fromisoformat(days[-1]))
        except Exception as exc:                                 # noqa: BLE001
            errors.append("%s: %s" % (t, exc))
            continue
        truth = {b["date"].isoformat(): b for b in bars}
        for r in rows:
            day = str(r["date"])[:10]
            tb = truth.get(day)
            if tb is None:
                findings.append({"ticker": t, "date": day, "verdict": "no_vendor_bar",
                                 "why": "Polygon has no bar for this session"})
                continue
            stored = {"o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"]}
            v = classify_row(stored, tb)
            # THE STORED OHLC RIDES ALONG, not just the close. Without it an unexplained
            # mismatch cannot be adjudicated by anyone reading the report -- which is exactly
            # what happened to TSLA on 2026-10-16: its stored CLOSE sits inside the settled
            # range, so it looks like its seven convicted siblings, but its stored RANGE does
            # not, and the four numbers are what tell those two cases apart.
            findings.append({"ticker": t, "date": day, "verdict": v["verdict"],
                             "why": v["why"], "stored_c": r["c"], "vendor_c": tb["c"],
                             "stored": stored,
                             "vendor": {k: tb[k] for k in ("o", "h", "l", "c", "v")}})

    counts: Dict[str, int] = {}
    for f in findings:
        counts[f["verdict"]] = counts.get(f["verdict"], 0) + 1
    return {"checked": len(findings), "counts": counts, "findings": findings,
            "errors": errors, "tickers": list(tickers), "sessions": sessions}


async def repair(conn, report: Dict[str, Any]) -> Dict[str, Any]:
    """Rewrite only the rows convicted as unsettled captures. R-IV.1203(c): "Repair those rows."

    ONLY THAT VERDICT. A basis difference is correct data on a different basis and must not be
    touched; an unexplained mismatch is not understood, and repairing what you do not understand
    is how a correct row becomes a wrong one.

    THE REPAIR WRITES THE SPLIT-ONLY FIGURES INTO A FULLY-ADJUSTED TABLE, which is a real seam
    and is why it is restricted to the newest sessions: for a session before any dividend has
    gone ex, the two bases are the same number, so for the last few sessions the figures are
    interchangeable. That is exactly the window R-IV.1203(c) names (the last 5), and it is not
    a licence to repair deep history this way.
    """
    fixed, skipped = [], []
    for f in report.get("findings") or []:
        if f.get("verdict") != "unsettled_capture":
            if f.get("verdict") not in ("match",):
                skipped.append({"ticker": f["ticker"], "date": f["date"],
                                "verdict": f["verdict"]})
            continue
        v = f.get("vendor") or {}
        if any(v.get(k) is None for k in ("o", "h", "l", "c")):
            skipped.append({"ticker": f["ticker"], "date": f["date"],
                            "verdict": "vendor_bar_incomplete"})
            continue
        await conn.execute(
            """UPDATE stable_daily_bars
                  SET o = $3, h = $4, l = $5, c = $6, v = $7
                WHERE ticker = $1 AND date = $2""",
            f["ticker"], _dt.date.fromisoformat(f["date"]),
            v["o"], v["h"], v["l"], v["c"], int(v.get("v") or 0))
        fixed.append({"ticker": f["ticker"], "date": f["date"],
                      "was": f.get("stored_c"), "now": v["c"]})
    logger.info("[bars_audit] repaired %d row(s), skipped %d", len(fixed), len(skipped))
    return {"repaired": fixed, "repaired_count": len(fixed), "skipped": skipped}
