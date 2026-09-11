"""Triton Step-0 shadow — shared helpers (poller B2 + grader B3).

Triton's UW bar-fetches go through get_ohlc(caller="triton_flow_shadow") + the
'r' regular-session filter, tagged to the Triton BACKGROUND governor budget
(clean attribution; never rides ohlc_bars — so Triton can't die as collateral
when the over-quota ohlc_bars caller throttles). SHADOW-ONLY: no
scoring/pipeline coupling.

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

logger = logging.getLogger("triton_shadow")

TRITON_CALLER = "triton_flow_shadow"

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
    ticker: str, lookback_days: int
) -> Tuple[Dict[date, float], str]:
    """{date: regular-session close}, AND the provider that produced it.

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
        return out, PROVIDER_UW

    # ── The net. Reached ONLY when UW produced no usable regular-session bar. ──
    # get_bars_yfinance touches no UW endpoint: the isolation in the module
    # docstring is preserved, and we do not re-ask the query that just failed.
    logger.info(
        "triton_grader: UW gave no 'r' bars for %s (%d raw) — falling back to yfinance",
        ticker, len(bars) if isinstance(bars, list) else 0,
    )
    try:
        fb = await get_bars_yfinance(ticker.upper())
    except Exception as exc:
        logger.warning("triton fallback bars failed %s: %s", ticker, type(exc).__name__)
        return {}, PROVIDER_NONE
    if not fb or not isinstance(fb, list):
        return {}, PROVIDER_NONE

    # Polygon-shaped: c=close, t=epoch ms. NO market_time filter here — see the
    # filter trap above. Provider is READ off the bar, not assumed.
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
