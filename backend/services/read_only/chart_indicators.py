"""Read-only technical-indicator accessor — backs hub_get_chart_indicators (v1).

Computes daily SMA stack / EMA / RSI / MACD / ATR / ADX / volume hub-side from a
SINGLE UW daily-OHLC pull (`get_ohlc`, caller="chart_indicators"). Mirrors the
hub-side-math-on-UW-data pattern (Black-Scholes Greeks). No TradingView, no new
secret, no `/technical-indicator` endpoint.

v1 is DAILY ONLY. Any other timeframe returns an `unavailable` shell with the
"intraday timeframe pending v1.1" warning — no intraday fetch. `vwap` is always
null in v1 (correctly N/A for daily — no warning).

indicators_source="uw_computed". `as_of` = the freshest bar's UW timestamp;
`staleness_seconds` is COMPUTED (never hardcoded). Status:
  ok          all indicators computed, freshest bar current
  degraded    bars present but >=1 indicator null (e.g. <200 bars -> SMA-200) — see warnings[]
  stale       freshest daily bar is not today's session during RTH
  unavailable no bars / governor sentinel / error (never fake-fresh)
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timezone
from typing import Any, Dict, List, Optional

from indicators.adx import latest_adx
from indicators.atr import latest_atr
from indicators.macd import latest_macd
from indicators.moving_averages import latest_moving_averages
from indicators.rsi import latest_rsi

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 420  # ~290 sessions — clears SMA-200 + EMA-200 warmup + holidays


def _unavailable(tkr: str, timeframe: str, reason: str) -> Dict[str, Any]:
    """Honest unavailable shell — never fake-fresh."""
    return {
        "status": "unavailable",
        "staleness_seconds": None,
        "data": {
            "ticker": tkr, "timeframe": timeframe, "spot": None, "bar_count": 0,
            "indicators_source": "uw_computed", "as_of": None,
            "vwap": None, "warnings": [reason],
        },
    }


def _parse_ts(s: Optional[str]) -> Optional[datetime]:
    """Parse a UW bar timestamp. Daily bars carry `date` (YYYY-MM-DD); some carry
    a full `start_time`. Date-only is anchored at 20:00 UTC (~16:00 ET close)."""
    if not s:
        return None
    txt = str(s).strip()
    # Date-only ("YYYY-MM-DD") must be anchored at ~market close (20:00 UTC ≈
    # 16:00 ET), NOT midnight — midnight-UTC converts to the PRIOR ET calendar
    # day and false-flags today's daily bar as stale.
    if len(txt) == 10 and txt[4] == "-" and txt[7] == "-":
        try:
            d = datetime.strptime(txt, "%Y-%m-%d")
            return d.replace(hour=20, tzinfo=timezone.utc)
        except ValueError:
            return None
    try:
        dt = datetime.fromisoformat(txt.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _staleness(as_of: Optional[str]) -> tuple[Optional[int], bool]:
    """(staleness_seconds, is_stale). Stale = freshest daily bar is NOT today's
    ET session while the market is open/closed today (mirror quote.py's
    'no bar today during RTH' rule). Never hardcoded."""
    bar_dt = _parse_ts(as_of)
    if bar_dt is None:
        return None, False
    now = datetime.now(timezone.utc)
    staleness = max(0, int((now - bar_dt).total_seconds()))
    try:
        from zoneinfo import ZoneInfo
        et = ZoneInfo("America/New_York")
        now_et = now.astimezone(et)
        bar_et_date = bar_dt.astimezone(et).date()
        gap_days = (now_et.date() - bar_et_date).days
        # Daily-appropriate: today's bar forming mid-session is NORMAL, not stale.
        # Stale only when the feed is genuinely behind:
        #   - after today's close on a weekday and no today bar, OR
        #   - more than a long-weekend (>4 calendar days) without a bar.
        after_close = now_et.weekday() < 5 and now_et.time() >= time(16, 5)
        is_stale = (after_close and bar_et_date < now_et.date()) or gap_days > 4
    except Exception:
        is_stale = staleness > 4 * 86400  # ~4d fallback
    return staleness, is_stale


def _f(x: Any) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


#: fix-first #5. The ADX floor below which the market is a range, and the floor at or above
#: which an ALIGNED stack makes it a trend. Both are the strategy-lab §6.2 numbers, and they
#: match the `adx.trend_strength` bands this module already publishes -- deliberately, because
#: two sets of thresholds for one question is how two surfaces come to disagree about the same
#: tape.
MARKET_STATE_RANGE_BELOW = 20.0
MARKET_STATE_TREND_AT = 25.0

#: A stack that is telling you it is NOT aligned. An ADX of 30 across a tangled stack is a
#: transition, not a trend, and this is the clause that makes the state more than an ADX band.
_STACK_ALIGNED = ("bullish", "bearish")


def market_state(adx_value, stack_state, price_vs=None) -> Dict[str, Any]:
    """`{state, direction, basis, ...}` from the ADX band and the MA stack — fix-first #5.

        ADX < 20                            -> range
        ADX >= 25 AND the stack is aligned  -> trend
        anything else                       -> transition

    NO INPUT, NO STATE. A null ADX or a null stack returns `state: None` with a reason naming
    which was missing. Defaulting to "transition" would read as a measurement of a market that
    is in fact unmeasured, and would be indistinguishable from a real transition.

    `direction` is separate from `state` on purpose: a trend has one and a range does not.
    Folding "uptrend" into the state enum would make a reader parse a string for two facts and
    would leave no way to say "aligned bearish, but ADX is only 22".
    """
    out: Dict[str, Any] = {
        "state": None, "direction": None, "adx": adx_value, "stack_state": stack_state,
        "range_below": MARKET_STATE_RANGE_BELOW, "trend_at": MARKET_STATE_TREND_AT,
        "stack_aligned": stack_state in _STACK_ALIGNED if stack_state is not None else None,
        "price_vs_all": None, "basis": None, "reason": None,
    }

    # Where the price sits relative to EVERY MA, which is the phrase the book's own notes use
    # ("above all four MAs"). Reported beside the state, never folded into it: the state is the
    # §6.2 rule and nothing else.
    if price_vs:
        vals = [v for v in price_vs.values()]
        if vals and all(v == "above" for v in vals):
            out["price_vs_all"] = "above"
        elif vals and all(v == "below" for v in vals):
            out["price_vs_all"] = "below"
        elif any(v is None for v in vals):
            out["price_vs_all"] = None
        else:
            out["price_vs_all"] = "mixed"

    missing = []
    if adx_value is None:
        missing.append("adx")
    if stack_state is None:
        missing.append("stack_state")
    if missing:
        out["reason"] = ("no market state: %s %s null, and a default would read as a "
                         "measurement of an unmeasured market"
                         % (" and ".join(missing), "is" if len(missing) == 1 else "are"))
        return out

    if adx_value < MARKET_STATE_RANGE_BELOW:
        out["state"] = "range"
        out["basis"] = ("ADX %.1f is below %.0f" % (adx_value, MARKET_STATE_RANGE_BELOW))
        return out

    aligned = stack_state in _STACK_ALIGNED
    if adx_value >= MARKET_STATE_TREND_AT and aligned:
        out["state"] = "trend"
        out["direction"] = "up" if stack_state == "bullish" else "down"
        out["basis"] = ("ADX %.1f is at or above %.0f and the stack is %s"
                        % (adx_value, MARKET_STATE_TREND_AT, stack_state))
        return out

    out["state"] = "transition"
    if adx_value >= MARKET_STATE_TREND_AT:
        out["basis"] = ("ADX %.1f is at or above %.0f but the stack is %s, so it is not a "
                        "trend" % (adx_value, MARKET_STATE_TREND_AT, stack_state))
    else:
        out["basis"] = ("ADX %.1f sits between %.0f and %.0f"
                        % (adx_value, MARKET_STATE_RANGE_BELOW, MARKET_STATE_TREND_AT))
    # The stack's direction is reported even in a transition: "aligned bearish but ADX only 22"
    # is a different thing to know from "tangled stack", and the state alone cannot say which.
    if aligned:
        out["direction"] = "up" if stack_state == "bullish" else "down"
    return out


async def uw_regular_daily(ticker: str):
    """UW's REGULAR-session daily bars for `ticker`, keyed by session date (`YYYY-MM-DD`).

    Returns `(daily, None)`, or `(None, reason)` when UW cannot answer -- the reasons are the
    envelope's own strings. ONE fetch: the same call, caller tag and cache key the indicators
    have always used, so R-IV.1423(h)2's dated close verifier, which reads this, costs no call
    the card does not already make.

    BOUNDED BY ROWS, NOT BY DATE. `/ohlc/1d` is newest-first and ignores `date_from`, so the
    span is whatever the row limit reaches (measured 2026-10-24: 500 rows -> 167 dated
    sessions). A date inside the span is NOT therefore present; a reader must look it up.
    """
    from integrations.uw_api import get_ohlc
    from integrations.uw_governor import is_unavailable

    tkr = (ticker or "").upper()
    try:
        bars = await get_ohlc(tkr, candle_size="1d", lookback_days=LOOKBACK_DAYS,
                              caller="chart_indicators")
    except Exception as exc:
        logger.warning("chart_indicators(%s) bar fetch raised: %s", tkr, type(exc).__name__)
        return None, "bar fetch error"

    if is_unavailable(bars):  # governor/circuit/rate-limit sentinel — NOT no-data
        return None, "UW unavailable (quota/circuit/rate-limit)"
    if not bars or not isinstance(bars, list):
        return None, "no bars returned"

    # UW's /ohlc/1d returns SESSION-SPLIT rows per date (market_time pr/r/po).
    # Keep the REGULAR-session ('r') bar only, one per date — otherwise the
    # indicators run on premarket/postmarket partials mixed with the day's bar.
    daily: Dict[str, Dict[str, Any]] = {}
    for b in bars:
        if (b.get("market_time") or "").lower() != "r":
            continue
        d = b.get("start_time") or b.get("date")
        if d:
            daily[str(d)[:10]] = b  # one 'r' bar per date (last wins)
    return daily, None


async def get_chart_indicators(ticker: str, timeframe: str = "daily") -> Dict[str, Any]:
    """Return the chart-indicators envelope payload {status, data, staleness_seconds}."""
    tkr = (ticker or "").upper()

    if timeframe != "daily":
        shell = _unavailable(tkr, timeframe, "intraday timeframe pending v1.1")
        return shell

    daily, why = await uw_regular_daily(tkr)
    if daily is None:
        return _unavailable(tkr, "daily", why)

    highs: List[float] = []
    lows: List[float] = []
    closes: List[float] = []
    vols: List[int] = []
    times: List[Optional[str]] = []
    for key in sorted(daily):
        b = daily[key]
        h, l, c = _f(b.get("high")), _f(b.get("low")), _f(b.get("close"))
        if h is None or l is None or c is None:
            continue
        highs.append(h)
        lows.append(l)
        closes.append(c)
        v = b.get("total_volume")
        if v is None:
            v = b.get("volume")
        try:
            vols.append(int(v))
        except (TypeError, ValueError):
            vols.append(0)
        times.append(b.get("start_time") or b.get("date"))

    if len(closes) < 2:
        return _unavailable(tkr, "daily", "insufficient usable bars")

    spot = closes[-1]
    bar_count = len(closes)
    as_of = times[-1]
    staleness, is_stale = _staleness(as_of)
    warnings: List[str] = []

    ma = latest_moving_averages(closes)
    sma, ema = ma["sma"], ma["ema"]
    rsi = latest_rsi(closes)
    macd = latest_macd(closes)
    atr_val = latest_atr(highs, lows, closes)
    adx_val = latest_adx(highs, lows, closes)

    # null → warning (each missing indicator surfaced, never silently dropped)
    if sma["200"] is None:
        warnings.append(f"sma_200 null (only {bar_count} bars, need 200)")
    if ema["200"] is None:
        warnings.append(f"ema_200 null (only {bar_count} bars, need 200)")
    if sma["stack_state"] is None:
        warnings.append("stack_state null (a constituent SMA is null)")
    if rsi is None:
        warnings.append("rsi null (insufficient bars)")
    if macd is None:
        warnings.append("macd null (insufficient bars)")
    if atr_val is None:
        warnings.append("atr null (insufficient bars)")
    if adx_val is None:
        warnings.append("adx null (insufficient bars)")

    atr_pct = round(atr_val / spot * 100, 4) if (atr_val and spot) else None
    v_latest = vols[-1] if vols else None
    v_win = vols[-30:] if vols else []
    v_avg = round(sum(v_win) / len(v_win), 2) if v_win else None
    rvol = round(v_latest / v_avg, 4) if (v_latest and v_avg) else None

    if adx_val is None:
        trend = None
    elif adx_val >= 25:
        trend = "trending"
    elif adx_val >= 20:
        trend = "developing"
    else:
        trend = "ranging"

    # fix-first #5. Its own warning, because an undecidable state is exactly the case a reader
    # must not mistake for a measured one -- and `warnings` is how every other missing
    # indicator here is already surfaced rather than silently dropped.
    _ms = market_state(adx_val, sma.get("stack_state"), sma.get("price_vs"))
    if _ms["state"] is None:
        warnings.append("market_state null (%s)" % _ms["reason"])

    data = {
        "ticker": tkr, "timeframe": "daily", "spot": spot, "bar_count": bar_count,
        "indicators_source": "uw_computed", "as_of": as_of,
        "sma": sma,
        "ema": ema,
        "rsi": rsi or {"period": 14, "value": None, "state": None},
        "macd": macd or {"fast": 12, "slow": 26, "signal": 9, "macd": None,
                         "signal_line": None, "histogram": None, "hist_state": None},
        "atr": {"period": 14, "value": atr_val, "atr_pct": atr_pct},
        "adx": {"period": 14, "value": adx_val, "trend_strength": trend},
        # fix-first #5: the MA stack and the ADX band read TOGETHER, so the pairing is done
        # once here rather than by eye in each reader's notes.
        "market_state": _ms,
        "volume": {"latest": v_latest, "avg": v_avg, "rvol": rvol, "avg_window": "30d"},
        "vwap": None,
        "warnings": warnings,
    }

    if is_stale:
        status = "stale"
    elif warnings:
        status = "degraded"
    else:
        status = "ok"

    return {"status": status, "data": data, "staleness_seconds": staleness}
