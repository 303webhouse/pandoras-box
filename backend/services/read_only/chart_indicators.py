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


async def get_chart_indicators(ticker: str, timeframe: str = "daily") -> Dict[str, Any]:
    """Return the chart-indicators envelope payload {status, data, staleness_seconds}."""
    tkr = (ticker or "").upper()

    if timeframe != "daily":
        shell = _unavailable(tkr, timeframe, "intraday timeframe pending v1.1")
        return shell

    from integrations.uw_api import get_ohlc
    from integrations.uw_governor import is_unavailable

    try:
        bars = await get_ohlc(tkr, candle_size="1d", lookback_days=LOOKBACK_DAYS,
                              caller="chart_indicators")
    except Exception as exc:
        logger.warning("chart_indicators(%s) bar fetch raised: %s", tkr, type(exc).__name__)
        return _unavailable(tkr, "daily", "bar fetch error")

    if is_unavailable(bars):  # governor/circuit/rate-limit sentinel — NOT no-data
        return _unavailable(tkr, "daily", "UW unavailable (quota/circuit/rate-limit)")
    if not bars or not isinstance(bars, list):
        return _unavailable(tkr, "daily", "no bars returned")

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
