"""Triton Step-0 shadow — shared helpers (poller B2 + grader B3).

Triton's UW bar-fetches go through get_ohlc(caller="triton_flow_shadow") + the
'r' regular-session filter, tagged to the Triton BACKGROUND governor budget
(clean attribution; never rides ohlc_bars — so Triton can't die as collateral
when the over-quota ohlc_bars caller throttles). SHADOW-ONLY: no
scoring/pipeline coupling.

R-IV.482(c) / R-IV.485(e) — THE PIN, which overrides everything below: while
Triton's registered window is open (through 2026-11-06, `TRITON_BARS_PIN_UNTIL`)
`fetch_r_close_index` returns yfinance UNCONDITIONALLY and makes no UW request
at all. Grading a registered population on a series that changes vendor
mid-window is not grading one population. Read the pin before reading the
fallback: from 2026-09-14 the two produced the same outcome by accident, and
04f6480 ended that by repairing UW for every consumer.

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
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger("triton_shadow")

TRITON_CALLER = "triton_flow_shadow"

ET = ZoneInfo("America/New_York")

# ── R-IV.482(c) / R-IV.485(e): THE TRITON BAR PIN ────────────────────────────
# Triton's registered window grades on yfinance, END TO END. Until 04f6480 that
# happened by accident: UW yielded no usable regular-session bar, so every row
# from 2026-09-14 took the fallback. 04f6480 repaired the UW path for every
# consumer, which silently UN-PINNED Triton — measured 2026-09-23 19:1xZ,
# `triton_grader.bars` read state=primary primary_ok=27 subs=0, i.e. back on UW
# with the window still open.
#
# A population whose bar vendor changes mid-window is not one population. The
# hypothesis was registered against a yfinance series and must be graded against
# a yfinance series, whatever UW returns and however healthy UW is.
#
# Expressed as DATA — a date anyone can read against the registration without
# running anything — and INCLUSIVE of its last day. It lapses on its own: a pin
# that needs a second deploy to remove is a pin that outlives its window.
TRITON_BARS_PIN_UNTIL = date(2026, 11, 6)


def triton_bars_pinned(session_date: Optional[date] = None) -> bool:
    """True while Triton's bars are held on yfinance by ruling.

    The session date is the EXCHANGE's, not the server's: the grader runs at
    20:00 ET, which is already the next UTC day, and a pin that lapses a day
    early on a UTC clock would hand the last session of the window to UW.
    """
    d = session_date or datetime.now(ET).date()
    return d <= TRITON_BARS_PIN_UNTIL

# Mega/index premium bucket (flow_scanner INDEX_TICKERS — the $2M tier).
INDEX_TICKERS = {"SPY", "QQQ", "SMH", "NVDA", "AVGO", "MSFT", "GOOGL", "AMZN", "META"}
LARGE_MIN = 750_000  # flow_scanner LARGE_MIN_PREMIUM (TSLA-class)


def _f(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


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
    ticker: str, lookback_days: int, session_date: Optional[date] = None
) -> Tuple[Dict[date, float], str]:
    """{date: regular-session close}, AND the provider that produced it.

    R-IV.482(c)/R-IV.485(e): while the Triton window is open this returns
    yfinance UNCONDITIONALLY and never calls UW — see TRITON_BARS_PIN_UNTIL.
    Everything below describes the path taken once the pin lapses.

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
    if triton_bars_pinned(session_date):
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


def close_on_or_near(idx: Dict[date, float], target: date) -> Optional[float]:
    """Close at target, else ±1/±2 calendar-day tolerance (holiday/missing bar)."""
    if target in idx:
        return idx[target]
    for delta in (1, -1, 2, -2):
        v = idx.get(target + timedelta(days=delta))
        if v is not None:
            return v
    return None
