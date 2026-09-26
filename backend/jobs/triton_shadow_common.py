"""Triton Step-0 shadow — shared helpers (poller B2 + grader B3).

Triton's UW bar-fetches go through get_ohlc(caller="triton_flow_shadow") + the
'r' regular-session filter, tagged to the Triton BACKGROUND governor budget
(clean attribution; never rides ohlc_bars — so Triton can't die as collateral
when the over-quota ohlc_bars caller throttles). SHADOW-ONLY: no
scoring/pipeline coupling.

R-IV.497(d) / R-IV.485(e) — THE PIN, which overrides everything below: a row
whose `fired_at` session falls in the registered window (2026-09-15 .. 2026-10-30)
grades on yfinance WHENEVER it is graded, and `fetch_r_close_index(..., pinned=True)`
makes no UW request at all. Grading a registered population on a series that
changes vendor mid-window is not grading one population. The caller decides from
the ROW, not from the clock — an earlier form keyed on the run date and would have
reverted to UW for a run after the window closed.

R-IV.324 — THE FALLBACK, and what it does NOT change: when UW yields no
regular-session bar, `fetch_r_close_index` falls through to
`get_bars_yfinance()`, which touches NO UW endpoint and so spends NO governor
budget under any caller. The isolation above still holds exactly as written —
it is preserved deliberately, by NOT routing the fallback through `get_bars()`,
whose UW leg runs as `caller="ohlc_bars"`. Every bar the grader uses now carries
a provider, and the grade records it.
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger("triton_shadow")

TRITON_CALLER = "triton_flow_shadow"

ET = ZoneInfo("America/New_York")

# ── R-IV.497(d) / R-IV.485(e): THE PIN IS KEYED TO THE ROW, NOT THE RUN ──────
# Triton's registered window grades on yfinance, END TO END.
#
# The first form of this pin keyed on the RUN date, and QUERY found the hole: a
# grader run after the window closed would revert to UW and re-grade in-window
# rows on a vendor the registration does not name. A row's vendor is a property
# of the ROW, so it is keyed to the row's fired_at session and is true whenever
# that row is graded — today, next month, or in a backfill years from now.
#
# The window is the registration's, not the reader's: cohorts W1 (Tue 2026-09-15,
# T_clock) through W7 (ends Fri 2026-10-30) — 34 sessions, R-IV.485(b). The seven
# Friday READS run to 2026-11-06, one week behind their cohort (R-IV.485(a)); the
# last read date is not the last session, and keying on it was the earlier error.
#
# Data, not logic: two dates readable against the registration without running
# anything.
TRITON_WINDOW_FIRST_SESSION = date(2026, 9, 15)
TRITON_WINDOW_LAST_SESSION = date(2026, 10, 30)


def triton_row_pinned(fired_session) -> bool:
    """True when THIS ROW belongs to the registered window and must grade on yfinance.

    Takes the row's own session — a date, or anything with .date(). Not a clock:
    nothing here reads the current time, which is the whole point. A row outside
    the window is not pinned and takes the ordinary UW-first path.
    """
    if fired_session is None:
        return False
    d = fired_session.date() if hasattr(fired_session, "date") else fired_session
    return TRITON_WINDOW_FIRST_SESSION <= d <= TRITON_WINDOW_LAST_SESSION


# Mega/index premium bucket (flow_scanner INDEX_TICKERS — the $2M tier).
INDEX_TICKERS = {"SPY", "QQQ", "SMH", "NVDA", "AVGO", "MSFT", "GOOGL", "AMZN", "META"}
LARGE_MIN = 750_000  # flow_scanner LARGE_MIN_PREMIUM (TSLA-class)


def _f(x) -> Optional[float]:
    """float, or None — and a NON-FINITE value is None, not a number.

    `float("nan")` succeeds, so the old form admitted NaN as a price and every
    downstream guard let it through: `not nan` is False and `nan <= 0` is False, so
    an entry check of `if not entry or entry <= 0` passes a NaN entry, and a NaN
    close arithmetics into a NaN grade. That is how 62 row-horizons came to hold
    `NaN` in `triton_flow_shadow` (found 2026-09-24, in-window, horizons 09-22 and
    09-23 — the two sessions the vendor served incompletely). A NaN is not a price
    and never was; it is an ABSENT bar, and it has to be absent here, at the one
    place both vendor paths convert a number.
    """
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def classify_bucket(ticker: str, premium_usd: Optional[int]) -> str:
    """flow_scanner liquidity buckets: index (mega/ETF) / large / small_mid."""
    if (ticker or "").upper() in INDEX_TICKERS:
        return "index"
    if premium_usd is not None and premium_usd >= LARGE_MIN:
        return "large"
    return "small_mid"


def classify_direction(opt_type: Optional[str]) -> Optional[str]:
    """Ask-side is enforced by the request filter, so direction is the option
    side: call -> BULL, put -> BEAR."""
    if not opt_type:
        return None
    t = str(opt_type).lower()
    return "BULL" if t == "call" else "BEAR" if t == "put" else None


PROVIDER_NONE = "none"


async def fetch_r_close_index(
    ticker: str, lookback_days: int, *, pinned: bool
) -> Tuple[Dict[date, float], str]:
    """{date: regular-session close}, AND the provider that produced it.

    `pinned` is REQUIRED and keyword-only: the caller must decide, from the row's
    own session (`triton_row_pinned`), which vendor the registration names. There
    is deliberately no default — a default is how the run-date form got it wrong,
    by answering for rows it had never looked at. When pinned, this returns
    yfinance unconditionally and never calls UW. Everything below describes the
    unpinned path.

    R-IV.324: the grader gets the fallback. UW via `get_ohlc` is tried first and
    remains the preferred source; only when it yields NO usable regular-session
    bar do we fall through to yfinance.

    Returns (index, provider), provider in {"uw", "yfinance", "none"}.
    **The provider is RETURNED, never inferred by the caller** — a grade that
    cannot say which feed produced it is the provenance defect this build closes
    (R-IV.325). An empty index returns PROVIDER_NONE, not a guess.

    ── THE FILTER TRAP, written down because it fails silently ──────────────
    UW bars carry `market_time` and MUST be filtered to 'r'; unfiltered, a UW
    series mixes pre/post-market closes into a regular-session index.
    **yfinance daily bars have NO `market_time` field** — they are already one
    regular-session bar per day. Applying the 'r' filter to them drops EVERY
    bar and yields an empty index, which this job reports as
    `no_regular_session_bars` — i.e. the precise symptom the fallback exists to
    cure, with the fallback installed and doing nothing.

    So the 'r' filter is applied to the UW shape ONLY. Dropping it on the
    yfinance path is a consequence of a different schema, not a relaxation of
    the regular-session rule.

    Never raises.
    """
    from integrations.uw_api import (
        get_ohlc, get_bars_yfinance, PROVIDER_UW, PROVIDER_YFINANCE,
    )
    from utils.vendor_substitution import record_primary, record_substitution

    # ── The pin, BEFORE the UW call. ─────────────────────────────────────────
    # Not "try UW, fall back": yfinance IS the source for this window, so no UW
    # request is made at all and the pin cannot be defeated by UW returning
    # perfectly good bars. Recorded as PRIMARY, not as a substitution: under the
    # pin yfinance is not a fallback and this consumer's primary_ok is not a
    # statement about UW's health. R-IV.489(a) — the primary_ok=1 check applies
    # to the other consumers, never to this one.
    if pinned:
        record_primary("triton_grader.bars", PROVIDER_YFINANCE)
        idx, prov = await _yfinance_close_index(ticker)
        if not idx:
            logger.warning("triton_grader: PINNED to yfinance and it gave nothing for %s "
                           "— skipping, NOT falling through to UW", ticker)
        return idx, prov

    # ── UW first, under Triton's own governor caller. Unchanged. ──
    try:
        bars = await get_ohlc(ticker.upper(), candle_size="1d",
                              lookback_days=lookback_days, caller=TRITON_CALLER)
    except Exception as exc:
        logger.warning("triton bars fetch failed %s: %s", ticker, type(exc).__name__)
        bars = None

    out: Dict[date, float] = {}
    if bars and isinstance(bars, list):
        for b in bars:
            if not isinstance(b, dict):
                continue
            if (b.get("market_time") or "").lower() != "r":  # regular session only
                continue
            c = _f(b.get("close"))
            dd = _as_date(b.get("start_time") or b.get("date"))
            if c is not None and dd is not None:
                out[dd] = c
    if out:
        record_primary("triton_grader.bars", PROVIDER_UW)
        return out, PROVIDER_UW

    record_substitution("triton_grader.bars", PROVIDER_UW, PROVIDER_YFINANCE,
                        "no usable regular-session UW bar", ticker.upper())
    # ── The net. Reached ONLY when UW produced no usable regular-session bar. ──
    # get_bars_yfinance touches no UW endpoint: the isolation in the module
    # docstring is preserved, and we do not re-ask the query that just failed.
    logger.info(
        "triton_grader: UW gave no 'r' bars for %s (%d raw) — falling back to yfinance",
        ticker, len(bars) if isinstance(bars, list) else 0,
    )
    return await _yfinance_close_index(ticker)


async def _yfinance_close_index(ticker: str) -> Tuple[Dict[date, float], str]:
    """{date: close} from yfinance, and the provider READ OFF THE BARS.

    One implementation serves both callers — the R-IV.324 fallback and the
    R-IV.482(c) pin — so the pinned window and the fallback cannot drift apart
    and grade on subtly different series. Touches no UW endpoint, so Triton's
    governor isolation holds for both.
    """
    from integrations.uw_api import get_bars_yfinance, PROVIDER_YFINANCE

    try:
        fb = await get_bars_yfinance(ticker.upper())
    except Exception as exc:
        logger.warning("triton yfinance bars failed %s: %s", ticker, type(exc).__name__)
        return {}, PROVIDER_NONE
    if not fb or not isinstance(fb, list):
        return {}, PROVIDER_NONE

    # Polygon-shaped: c=close, t=epoch ms. NO market_time filter here — see the
    # filter trap above. Provider is READ off the bar, not assumed.
    out: Dict[date, float] = {}
    providers = set()
    for b in fb:
        if not isinstance(b, dict):
            continue
        c = _f(b.get("c"))
        dd = _as_date(b.get("t") if b.get("t") is not None else b.get("date"))
        if c is not None and dd is not None:
            out[dd] = c
            providers.add(b.get("provider"))
    if not out:
        return {}, PROVIDER_NONE

    # A stitched series would put a cross-adjustment seam inside one index
    # (uw_api.py:602-606 — never mix providers inside one measurement). This is
    # an assertion on a single-path fetch, not a merge.
    if len(providers) == 1:
        return out, (providers.pop() or PROVIDER_YFINANCE)
    logger.warning("triton_grader: MIXED providers in one series for %s: %s", ticker, providers)
    return out, "mixed"


def _as_date(v):
    """Epoch-ms, epoch-s, or an ISO-ish string -> date. None when unreadable.

    get_ohlc gives ISO strings; the yfinance shape gives epoch ms in `t`. One
    helper, so a schema difference cannot become a silent date-parse failure on
    one path and not the other.
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        secs = float(v) / 1000.0 if abs(float(v)) > 1e11 else float(v)
        try:
            return datetime.fromtimestamp(secs, tz=timezone.utc).date()
        except (OverflowError, OSError, ValueError):
            return None
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def nth_trading_day(anchor: date, n: int) -> date:
    """nth Mon-Fri strictly after anchor (mirrors a3; no holiday calendar in v0)."""
    day = anchor
    count = 0
    while count < n:
        day += timedelta(days=1)
        if day.weekday() < 5:
            count += 1
    return day


def _finite(v) -> Optional[float]:
    """A close, or None. NaN and infinity are ABSENT BARS, not values.

    Belt and braces with `_f`: these two lookups are Amendment 4's gate, and a gate
    that is only safe because something upstream stayed correct is not a gate.
    """
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def close_on_or_near(idx: Dict[date, float],
                     target: date) -> Tuple[Optional[float], Optional[date]]:
    """(close, THE SESSION IT CAME FROM). Target first, else ±1/±2 calendar days.

    Amendment 4(a) is this function's history. It returned a bare float, so a close
    borrowed from a neighbouring session was indistinguishable from the session's own
    — and 15 W1 rows were graded across the 2026-09-22 gap with nothing recorded to
    show it. The substitution behaviour is UNCHANGED for the callers that want it
    (R-IV.522(b)2); what changed is that it can no longer hide. The date comes back,
    and a caller that must not substitute compares it to `target` — or uses
    `close_on_session`, which cannot substitute at all.
    """
    v = _finite(idx.get(target))
    if v is not None:
        return v, target
    for delta in (1, -1, 2, -2):
        d = target + timedelta(days=delta)
        v = _finite(idx.get(d))
        if v is not None:
            return v, d
    return None, None


def close_on_session(idx: Dict[date, float], target: date) -> Optional[float]:
    """The close for EXACTLY that session, or None. Amendment 4(c): no substitution.

    Inside the registered window this is the only lookup the grader may use. A
    missing bar here is a fact to record, not a hole to paper over: a neighbour's
    close is a different session's price, and naming it as this one's is the fault
    Amendment 4 exists to close.
    """
    return _finite(idx.get(target))


# ── Amendment 4(c): a horizon session is a weekday THE EXCHANGE TRADED ──────────
#
# `nth_trading_day` walks Mon-Fri with no holiday calendar (it mirrors a3, v0). That
# is only safe while no exchange holiday falls inside the window, which R-IV.522(b)4
# required be confirmed before deploying: measured 2026-09-24, there is NONE between
# 2026-09-15 and 2026-09-15's last read horizon 2026-11-06. So the weekday walk and
# the calendar agree across the whole window, and no grade moves.
#
# This guard is what makes that a checked fact rather than a remembered one. It does
# NOT change any horizon — it refuses to grade one that is not a session, loudly,
# which is what an extended window would need.

# A HORIZON IS REACHED ONLY ONCE ITS SESSION IS OVER.
#
# The grader asked `tgt > today` against the UTC date. At 02:30 ET the UTC date is
# already tomorrow's while tomorrow's session has not opened, so a horizon landing on
# it read as REACHED. That was survivable before Amendment 4 -- the row just retried
# -- but 4(c) now counts failed requests toward a PERMANENT gap, so an unopened
# session would be named UNGRADEABLE. The first control run did exactly that: KLAC's
# 5d horizon, 2026-09-24, called a gap at 02:30 ET that morning.
#
# So: strictly BEFORE the current ET session date. A horizon grades from the next
# session onward, never from its own. The alternative -- same day past the close --
# saves a day of latency and buys the risk of three attempts landing in the hour
# before the vendor publishes the bar. Reads lag their cohort by a week (A3(a)), so
# the day costs nothing and the risk is not worth taking.
def horizon_reached(tgt: date, now: Optional[datetime] = None) -> bool:
    """True when tgt's session has finished, measured on the EXCHANGE's clock."""
    now = now or datetime.now(timezone.utc)
    return tgt < now.astimezone(ET).date()


def horizon_is_session(d: date) -> Optional[bool]:
    """True/False/None (the calendar cannot answer for that date)."""
    try:
        from stable_engine.market_calendar import is_trading_day_or_none
        return is_trading_day_or_none(d)
    except Exception:
        return None


# Cohort boundaries, read off the registration rather than stored: W1 starts at
# T_clock (Tue 2026-09-15) and each later cohort is that Mon-Fri week, through W7
# ending 2026-10-30. 4 + 5*6 = 34 sessions, which is R-IV.485(b)'s figure — the
# arithmetic is the check.
def cohort_bounds(name: str) -> Optional[Tuple[date, date]]:
    """(first_session, last_session) for W1..W7, or None."""
    n = str(name or "").strip().upper()
    if not (len(n) == 2 and n[0] == "W" and n[1].isdigit()):
        return None
    k = int(n[1])
    if not 1 <= k <= 7:
        return None
    if k == 1:
        return TRITON_WINDOW_FIRST_SESSION, date(2026, 9, 18)
    monday = date(2026, 9, 21) + timedelta(days=7 * (k - 2))
    return monday, monday + timedelta(days=4)


def cohort_of(session) -> Optional[str]:
    """Which cohort a session belongs to, or None when it is outside the window."""
    if session is None:
        return None
    d = session.date() if hasattr(session, "date") else session
    for k in range(1, 8):
        lo, hi = cohort_bounds("W%d" % k)
        if lo <= d <= hi:
            return "W%d" % k
    return None


# ── IV at fire time (R-IV.597(c)) ────────────────────────────────────────────────────────────
#
# WHY THIS IS URGENT AND CANNOT WAIT. Implied volatility at the moment a whale print fired is
# not recoverable afterwards -- QUERY has shown no history exists -- so every session without it
# is lost for good. That is the whole reason it ships before the exit-plan migration.
#
# ONE READER, NOT A THIRD. Two callers already parse this payload and they disagree about which
# end of the series is current:
#
#     enrichment/signal_enricher.py   latest = data[-1]   # "series is ascending"
#     jobs/b2_options_resolver.py     latest = iv_data[0]
#
# One of them is reading a year-old reading as today's. I cannot settle it here -- there is no UW
# key in this environment and `signal_options_expressions` holds ZERO rows, so the `[0]` reader
# has never actually written anything to compare against. So this delegates to the `[-1]` reader,
# which has 7,383 rows of operating history behind it, rather than adding a third opinion. If the
# order is wrong it is wrong in one place, and fixing it fixes both.
#
# AND IT RECORDS WHAT THE PAYLOAD ACTUALLY CONTAINS, once per ticker per day, so the next
# decision about this data is made on measured keys instead of my guess about them. `iv_rank_1y`
# is the only field this codebase reads, and a RANK is not an expected move -- it says where
# today's IV sits in its own one-year range. Whether the response also carries an IV LEVEL is
# unknown from here, so `iv_at_fire` exists and stays NULL until the log says otherwise.

_IV_SHAPE_LOGGED: set = set()


async def iv_at_fire(ticker: str) -> dict:
    """`{iv_rank_at_fire, iv_at_fire, iv_source}` for a ticker, now. Never raises.

    Tagged to the `triton_flow_shadow` BACKGROUND lane, so it is shed before anything the
    principal trades on. Returns None values on any failure -- never a fake 0, which would read
    as "volatility is at its one-year low" rather than "we did not get an answer".
    """
    import logging as _logging
    from datetime import date as _date

    log = _logging.getLogger("triton_shadow")
    out = {"iv_rank_at_fire": None, "iv_at_fire": None, "iv_source": None}
    try:
        from integrations.uw_api import get_iv_rank

        data = await get_iv_rank(ticker, caller="triton_flow_shadow")
        if not data:
            return out
        latest = data[-1] if isinstance(data, list) and data else data
        if not isinstance(latest, dict):
            return out

        key = (ticker.upper(), _date.today())
        if key not in _IV_SHAPE_LOGGED:
            _IV_SHAPE_LOGGED.add(key)
            log.info("triton iv payload keys for %s: %s (series len=%s, first=%s, last=%s)",
                     ticker, sorted(latest.keys()),
                     len(data) if isinstance(data, list) else 1,
                     (data[0].get("date") if isinstance(data, list) and data
                      and isinstance(data[0], dict) else None),
                     latest.get("date"))

        from scoring.sb3_iv_units import iv_rank_1y_to_100

        out["iv_rank_at_fire"] = iv_rank_1y_to_100(latest.get("iv_rank_1y"))
        # An IV LEVEL if the payload carries one under any of the names UW uses elsewhere in this
        # codebase. Tried in order, and `iv_source` records WHICH -- so a value is never
        # anonymous, and a NULL is distinguishable from a field we never looked for.
        for name in ("implied_volatility", "iv", "iv_30d", "implied_move"):
            raw = latest.get(name)
            if raw is None:
                continue
            try:
                out["iv_at_fire"] = float(raw)
                out["iv_source"] = name
                break
            except (TypeError, ValueError):
                continue
        if out["iv_source"] is None and out["iv_rank_at_fire"] is not None:
            out["iv_source"] = "iv_rank_1y"
    except Exception as exc:  # noqa: BLE001
        log.debug("triton iv_at_fire failed for %s: %s", ticker, exc)
    return out
