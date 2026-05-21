"""Read-only real-time quote accessor.

Wraps UW's /stock-state (live spot + OHLCV + tape_time) and /info (avg
volume, etc.) into the canonical hub_get_quote envelope.

UW does not expose a dedicated 52-week-stats endpoint — 52w high/low are
computed best-effort from /ohlc/1d (1-year daily bars). If that call fails
the 52w fields are returned as None; the rest of the quote is still valid.

Staleness rule: if the UW tape_time is more than 5 minutes old during
regular market hours, the quote is flagged status="stale". UW errors map
to status="unavailable".
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from integrations.uw_api import _uw_request

logger = logging.getLogger(__name__)


STALE_THRESHOLD_SECONDS = 5 * 60


def _to_float(value: Any) -> Optional[float]:
    """UW returns numeric values as strings. Parse defensively."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None


def _normalize_market_state(uw_market_time: Optional[str]) -> str:
    """Map UW's market_time to the canonical hub_get_quote market_state enum.

    UW values seen: "premarket", "regular", "postmarket", and sometimes
    "closed". We surface them as: pre_market | open | post_market | closed.
    """
    if not uw_market_time:
        return "closed"
    mapping = {
        "premarket": "pre_market",
        "regular": "open",
        "postmarket": "post_market",
        "closed": "closed",
        "halted": "halted",
    }
    return mapping.get(uw_market_time.lower(), uw_market_time.lower())


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


async def _compute_52w(ticker: str) -> Dict[str, Optional[float]]:
    """Best-effort 52-week high/low from /ohlc/1d. Returns {None, None} on failure."""
    try:
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=380)  # ~53 weeks of calendar to be safe
        path = f"/api/stock/{ticker.upper()}/ohlc/1d"
        resp = await _uw_request(
            path,
            params={"date_from": start.isoformat(), "date_to": today.isoformat()},
        )
        if not resp or "data" not in resp:
            return {"high": None, "low": None}
        bars = resp["data"]
        if not isinstance(bars, list) or not bars:
            return {"high": None, "low": None}

        cutoff = today - timedelta(days=365)
        highs: list[float] = []
        lows: list[float] = []
        for bar in bars:
            ts_raw = bar.get("market_time") or bar.get("date") or bar.get("start_time")
            if ts_raw:
                try:
                    bar_date = datetime.fromisoformat(
                        str(ts_raw).replace("Z", "+00:00")
                    ).date()
                except (ValueError, TypeError):
                    bar_date = None
                if bar_date and bar_date < cutoff:
                    continue
            h = _to_float(bar.get("high"))
            l = _to_float(bar.get("low"))
            if h is not None:
                highs.append(h)
            if l is not None:
                lows.append(l)
        return {
            "high": max(highs) if highs else None,
            "low": min(lows) if lows else None,
        }
    except Exception as exc:
        logger.warning("52w calc failed for %s: %s", ticker, exc)
        return {"high": None, "low": None}


async def get_quote(ticker: str) -> Optional[Dict[str, Any]]:
    """Return real-time quote envelope, or a status='unavailable' shell on error.

    Always returns a dict with the canonical schema (never None) so the
    MCP tool layer can wrap it consistently. Errors surface as status fields.
    """
    if not ticker or not isinstance(ticker, str):
        return None

    tkr = ticker.strip().upper()
    base_shell = {
        "ticker": tkr,
        "spot": None,
        "prior_close": None,
        "open": None,
        "high": None,
        "low": None,
        "volume": None,
        "avg_volume_30d": None,
        "pct_change": None,
        "wk52_high": None,
        "wk52_low": None,
        "market_state": "closed",
        "source": "UW",
        "uw_timestamp": None,
        "status": "unavailable",
    }

    try:
        state_resp = await _uw_request(f"/api/stock/{tkr}/stock-state")
    except Exception as exc:
        logger.warning("UW /stock-state errored for %s: %s", tkr, exc)
        return base_shell

    if not state_resp or "data" not in state_resp:
        return base_shell

    state = state_resp["data"]
    spot = _to_float(state.get("close"))
    prior_close = _to_float(state.get("prev_close"))
    open_px = _to_float(state.get("open"))
    high = _to_float(state.get("high"))
    low = _to_float(state.get("low"))
    volume = _to_int(state.get("total_volume") or state.get("volume"))
    uw_ts_raw = state.get("tape_time")
    market_state = _normalize_market_state(state.get("market_time"))

    pct_change: Optional[float] = None
    if spot is not None and prior_close not in (None, 0):
        pct_change = round(((spot - prior_close) / prior_close) * 100, 4)

    # Determine live vs stale based on tape_time freshness during regular hours.
    status = "live"
    if uw_ts_raw:
        ts = _parse_iso(uw_ts_raw)
        if ts is not None:
            age_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
            if market_state == "open" and age_seconds > STALE_THRESHOLD_SECONDS:
                status = "stale"

    # Secondary calls: /info (avg30_volume) and 52w bars. Both best-effort.
    avg_vol_30d: Optional[float] = None
    try:
        info_resp = await _uw_request(f"/api/stock/{tkr}/info")
        if info_resp and "data" in info_resp:
            avg_vol_30d = _to_float(info_resp["data"].get("avg30_volume"))
    except Exception as exc:
        logger.warning("UW /info errored for %s: %s (continuing)", tkr, exc)

    wk52 = await _compute_52w(tkr)

    return {
        "ticker": tkr,
        "spot": spot,
        "prior_close": prior_close,
        "open": open_px,
        "high": high,
        "low": low,
        "volume": volume,
        "avg_volume_30d": avg_vol_30d,
        "pct_change": pct_change,
        "wk52_high": wk52["high"],
        "wk52_low": wk52["low"],
        "market_state": market_state,
        "source": "UW",
        "uw_timestamp": uw_ts_raw,
        "status": status,
    }
