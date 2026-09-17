"""A second vendor for any row whose window spans a calendar event (R-IV.432(e)).

THE MODULE'S FIRST LAW 2 INSTANCE. basis.resolve_entry verifies a conversion against the fire
session's own bar -- but the bar and the calendar are the SAME vendor's domain, so a vendor
that adjusts wrongly also "verifies" its own wrong adjustment. HON is the case: CC-QUERY
measured the fresh yfinance series INFLATING pre-ex prices on a 0.9535 factor. Same-vendor
verification cannot detect a same-vendor error.

So a row whose basis resolution considered ANY calendar event (an ex-date after its anchor)
is checked against UW's daily closes before it is written:
  * anchor agreement  the two vendors' anchor-session closes are on the same basis;
  * window agreement  the two vendors' anchor -> exit close ratios agree.
Both within AGREE_TOL, or the row is HELD -- flagged, never graded. A hold is recorded
(store.shadow_grade_holds) so the check is not re-paid every day.

When UW cannot answer (no key, quota, circuit, no bar for a date) the row is neither graded
nor held: it is counted `independent_unavailable` and tried again next pass. UNKNOWN is not
agreement.

What this cannot see: an error BOTH vendors share, and an action neither vendor's calendar
lists (the seam detector and the entry-anomaly check are the net for those).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

VENDOR = "uw"
UW_CALLER = "ohlc_grader"             # its own governor tag (STANDARD), like Triton's
AGREE_TOL = 0.01
MAX_TICKERS_PER_PASS = 40             # under the tag's after-hours allowance (200 x 0.25)
LOOKBACK_SLACK_DAYS = 7


def spans_event(grade) -> bool:
    res = (grade.basis or {}).get("resolution") or {}
    return bool(res.get("events_considered"))


def _as_date(v) -> Optional[date]:
    from jobs.triton_shadow_common import _as_date as parse
    return parse(v)


async def fetch_uw_closes(ticker: str, since: date, today: Optional[date] = None
                          ) -> Optional[Dict[date, float]]:
    """{date: regular-session close} from UW, or None when UW cannot answer."""
    from integrations.uw_api import get_ohlc

    today = today or date.today()
    lookback = max(10, (today - since).days + LOOKBACK_SLACK_DAYS)
    try:
        bars = await get_ohlc(ticker.upper(), candle_size="1d", lookback_days=lookback,
                              caller=UW_CALLER)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[backtest.independent] UW bars failed for %s: %s", ticker, type(exc).__name__)
        return None
    if not bars or not isinstance(bars, list):
        return None                                   # includes the governor's falsy sentinel
    out: Dict[date, float] = {}
    for b in bars:
        if not isinstance(b, dict) or (b.get("market_time") or "").lower() != "r":
            continue
        d = _as_date(b.get("start_time") or b.get("date"))
        try:
            c = float(b.get("close"))
        except (TypeError, ValueError):
            continue
        if d is not None and c > 0:
            out[d] = c
    return out or None


def compare(grade, series, uw: Optional[Dict[date, float]]) -> Dict[str, Any]:
    """{'verdict': agree|disagree|unavailable, ...} for one graded row."""
    a, x = grade.anchor_session, grade.target_session
    detail: Dict[str, Any] = {"vendor": VENDOR, "tolerance": AGREE_TOL,
                              "anchor": a.isoformat() if a else None,
                              "exit": x.isoformat() if x else None}
    if not uw or a not in uw or x not in uw:
        detail["verdict"] = "unavailable"
        detail["missing"] = [d.isoformat() for d in (a, x) if d and (not uw or d not in uw)]
        return detail
    yf_a, yf_x = series.close(a), series.close(x)
    anchor_ratio = yf_a / uw[a]
    window_ratio = (yf_x / yf_a) / (uw[x] / uw[a])
    detail.update({"primary_anchor_close": yf_a, "uw_anchor_close": uw[a],
                   "primary_exit_close": yf_x, "uw_exit_close": uw[x],
                   "anchor_ratio": round(anchor_ratio, 6), "window_ratio": round(window_ratio, 6)})
    ok = abs(anchor_ratio - 1) <= AGREE_TOL and abs(window_ratio - 1) <= AGREE_TOL
    detail["verdict"] = "agree" if ok else "disagree"
    return detail


def fetch_start(grades) -> date:
    return min(g.anchor_session for g in grades) - timedelta(days=LOOKBACK_SLACK_DAYS)
