"""Set B's 15-minute bars, in ONE batched yfinance call per cycle. R-IV.1215(b).

THE SOURCE IS RULED, not chosen here: yfinance 15m, Set B, 26 calls a session, and NO UW
calls (R-IV.1215(b)1). 26 is one batched call per 15-minute bar across a 6.5-hour session, not
26 per ticker -- `yf.download` takes a LIST and returns every ticker in one request, which is
why a 12-ticker Set B costs the same as a 1-ticker one.

THREE THINGS THIS FILE EXISTS TO GET RIGHT, each a landmine this repo has already stepped on:

  1. BAR ORDER. A vendor's bars are not guaranteed ascending, and this repo has a filed
     landmine for exactly that (`fetch_crypto_ohlc` returns vendor order; positional slices
     assumed ascending). Every series here is sorted by its index before it is returned, and
     the sort is not conditional on what the vendor appeared to do today.

  2. THE PRIOR-DAY LEVEL COMES FROM THE 15m SERIES, NOT FROM A DAILY BAR. Yahoo's /1d can drop
     a whole session that the intraday endpoint still has -- also filed. A prior-day high taken
     from a dropped session would be the day BEFORE yesterday's, and every level test for that
     ticker would silently be measured against the wrong number. Deriving it from the same 15m
     bars the detector reads means the two can never disagree about which session was
     yesterday, and it costs no extra call.

  3. THE SESSION LIST MUST START AT THE OPEN. R-IV.1224(c) made the session's FIRST closed bar
     a break event in its own right, so a truncated list no longer merely under-reports -- it
     MANUFACTURES a gap break that never happened. `session_bars` therefore asserts that the
     first bar it returns is the session's opening bar, and raises rather than returning a list
     that would be read as a gap.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("yf_15m")

SOURCE = "yfinance"
INTERVAL = "15m"

#: US equity RTH, in Eastern. The session's first 15m bar opens at 09:30 and the last one
#: opens at 15:45.
RTH_OPEN = _dt.time(9, 30)
RTH_CLOSE = _dt.time(16, 0)
FIRST_BAR_OPEN = RTH_OPEN
BAR_MINUTES = 15
#: 09:30 to 16:00 is 26 bars of 15 minutes. Stated as a derived constant rather than typed as
#: 26, so the ruling's call budget and this number cannot drift apart.
BARS_PER_SESSION = int(
    ((RTH_CLOSE.hour * 60 + RTH_CLOSE.minute) - (RTH_OPEN.hour * 60 + RTH_OPEN.minute))
    / BAR_MINUTES)

_EASTERN = "America/New_York"


class SessionTruncated(ValueError):
    """The bars handed over do not start at the session's open.

    Raised rather than returned, because the caller cannot tell a truncated list from a short
    session by looking at it, and R-IV.1224(c) makes the difference a phantom alert.
    """


def _eastern(ts: Any) -> _dt.datetime:
    """A pandas timestamp as an Eastern-zone datetime.

    yfinance returns intraday bars tz-aware in the exchange's zone, but a naive index has been
    seen, so a naive stamp is LOCALISED rather than assumed to be Eastern already -- assuming
    would shift every bar by the machine's offset and move the session's first bar.
    """
    from zoneinfo import ZoneInfo

    t = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
    if t.tzinfo is None:
        return t.replace(tzinfo=ZoneInfo(_EASTERN))
    return t.astimezone(ZoneInfo(_EASTERN))


def fetch(tickers: Sequence[str], *, days: int = 2) -> Dict[str, List[Dict[str, Any]]]:
    """ONE call for every ticker. Returns {ticker: [bar, ...]} ascending by bar start.

    `days=2` is the minimum that covers yesterday (for the prior-day level) and today. A bar is
    {"start": datetime (Eastern), "open": float, "high": float, "low": float, "close": float}.

    A ticker the vendor returns nothing for is ABSENT from the result rather than present with
    an empty list, so "no data for CRM" and "CRM had a quiet session" cannot be confused.
    """
    import yfinance as yf

    syms = [str(t).upper() for t in tickers if str(t).strip()]
    if not syms:
        return {}
    frame = yf.download(syms, period="%dd" % days, interval=INTERVAL, group_by="ticker",
                        auto_adjust=False, prepost=False, progress=False, threads=False)
    if frame is None or getattr(frame, "empty", True):
        logger.warning("[yf_15m] empty frame for %d tickers", len(syms))
        return {}

    out: Dict[str, List[Dict[str, Any]]] = {}
    for sym in syms:
        try:
            sub = frame[sym] if len(syms) > 1 else frame
        except Exception:                                           # noqa: BLE001
            continue
        if sub is None or getattr(sub, "empty", True):
            continue
        # SORTED, ALWAYS. Not "sorted if it looks unsorted".
        sub = sub.sort_index()
        bars: List[Dict[str, Any]] = []
        for idx, row in sub.iterrows():
            try:
                c = float(row["Close"])
            except Exception:                                       # noqa: BLE001
                continue
            if c != c:                                              # NaN, the one value that
                continue                                            # passes a float() check
            bars.append({"start": _eastern(idx), "open": _f(row.get("Open")),
                         "high": _f(row.get("High")), "low": _f(row.get("Low")), "close": c})
        if bars:
            out[sym] = bars
    return out


def _f(v: Any) -> Optional[float]:
    """float or None, with NaN treated as None.

    One definition, because a `_need`/`_f` pair that disagreed about what "present" means is a
    fault this lane has already shipped once: NaN passed the missing check and then compared
    None to a float.
    """
    try:
        f = float(v)
    except Exception:                                               # noqa: BLE001
        return None
    return None if f != f else f


def session_of(bar: Dict[str, Any]) -> _dt.date:
    """The Eastern calendar date of a bar. The one place a bar becomes a session."""
    return bar["start"].date()


def split_sessions(bars: Sequence[Dict[str, Any]]) -> List[Tuple[_dt.date, List[Dict]]]:
    """Ascending [(session_date, bars)], grouped on the Eastern date."""
    groups: Dict[_dt.date, List[Dict]] = {}
    for b in bars:
        groups.setdefault(session_of(b), []).append(b)
    return [(d, groups[d]) for d in sorted(groups)]


def prior_day_level(bars: Sequence[Dict[str, Any]],
                    today: _dt.date) -> Tuple[Optional[float], Optional[float], str]:
    """(prior_high, prior_low, basis) from the 15m bars of the LAST session before `today`.

    (None, None, reason) when there is no earlier session in the data -- never a zero and never
    a fallback to today's own range, which would make every level test trivially true.
    """
    earlier = [(d, bs) for d, bs in split_sessions(bars) if d < today]
    if not earlier:
        return None, None, "no session before %s in the 15m data" % today.isoformat()
    day, bs = earlier[-1]
    highs = [b["high"] for b in bs if b["high"] is not None]
    lows = [b["low"] for b in bs if b["low"] is not None]
    if not highs or not lows:
        return None, None, "the %s session's 15m bars carry no high/low" % day.isoformat()
    return max(highs), min(lows), ("prior session %s, from its own 15m bars (%d of them)"
                                   % (day.isoformat(), len(bs)))


def session_bars(bars: Sequence[Dict[str, Any]], today: _dt.date, *,
                 require_open: bool = True) -> List[Dict[str, Any]]:
    """Today's bars, ascending, STARTING AT THE OPEN.

    R-IV.1224(c)'s sharp edge lives here. A list that does not begin at 09:30 is refused rather
    than returned, because the detector reads a one-element list as a gap-open break and cannot
    tell a truncated window from a session that genuinely has one bar so far.
    """
    mine = [b for b in bars if session_of(b) == today]
    mine.sort(key=lambda b: b["start"])
    if require_open and mine and mine[0]["start"].time() != FIRST_BAR_OPEN:
        raise SessionTruncated(
            "the first bar of %s starts at %s, not the %s open: a list that does not begin at "
            "the open would be read as a gap-open break (R-IV.1224(c))"
            % (today.isoformat(), mine[0]["start"].time().isoformat(),
               FIRST_BAR_OPEN.isoformat()))
    return mine


def closed_bars(session: Sequence[Dict[str, Any]], *, now: _dt.datetime,
                session_closed: bool) -> Tuple[List[Dict[str, Any]], str]:
    """(the bars that are CLOSED, why the last one counts or does not). R-IV.1215(b)4.

    Delegates the decision to `models.position_watch.bar_is_closed`, which owns the two-ways-
    only rule, rather than re-deriving it from the clock here. Two implementations of "is this
    bar finished" is two answers.
    """
    from models.position_watch import bar_is_closed

    if not session:
        return [], "no bars for this session yet"
    newest = session[-1]["start"]
    ok, why = bar_is_closed(newest, newest_bar_start=newest, session_closed=session_closed,
                            now=now)
    if ok:
        return list(session), why
    return list(session[:-1]), why
