"""GET /api/b9/world — B9 · global markets, live (SPEC-B9.md Monday's cut, R-IV.1431).

ONE yfinance batch for 13 tickers, ~2.1 years of daily Adj Close, computed by
`services.b9_live.build_world` and cached PER SETTLED SESSION. The data only changes once a
session, so the cache key carries the session: a new session can never be served under the old
key, and a restart does not re-fetch.

THE RIGHT EDGE IS THE LAST SETTLED SESSION (R-IV.1176(b)1). yfinance serves an in-progress bar
during market hours; computing a trend or a z off a session that has not finished is the fault
that rule closed for the stable engine, and this route inherits the clamp.

FAILURE IS SAID, NOT HIDDEN. When the fetch fails the route answers `status: "unavailable"` with
the reason, and remembers that for five minutes so a vendor throttle cannot turn every card open
into another request. It never falls back to the mock (R-IV.1371(c)3 / R-IV.1364(c)).

MARKET DATA, NOT THE BOOK: unauthenticated like the other market reads.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import date, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/b9", tags=["b9"])

# The version moves whenever the payload's SHAPE does, or a session cached before a deploy keeps
# serving the old shape for up to CACHE_TTL_S: v2 = the Recovery Race (R-IV.1436(e)3), whose first
# deploy served 10-23's v1 entry with no race in it.
# v3 = R-IV.1441(b)1: the race's ties (`places`, `ties`, `back200_status`, leaders as lists).
CACHE_PREFIX = "b9:world:v3:"
CACHE_TTL_S = 20 * 3600
FAIL_HOLD_S = 300
HISTORY_DAYS = 770            # ~2.1y: 252 sparkline + 220 for the trend test, with holidays
_fail: Dict[str, Any] = {}    # {"session": iso, "at": monotonic, "reason": str}
_lock = asyncio.Lock()


def _fetch(start: date, end: date) -> Dict[str, Dict[date, float]]:
    """{ticker: {date: adj_close}} from the stable engine's batched, auto-adjusted fetch."""
    from services.b9_live import ALL_TICKERS
    from stable_engine.bars_yf import fetch_batch

    frames = fetch_batch(list(ALL_TICKERS), start, end)
    out: Dict[str, Dict[date, float]] = {}
    for t, frame in (frames or {}).items():
        if frame is None or getattr(frame, "empty", True):
            continue
        series: Dict[date, float] = {}
        for r in frame.itertuples(index=False, name=None):
            d, c = r[0], r[4]                                   # (date, o, h, l, c, v)
            try:
                c = float(c)
            except (TypeError, ValueError):
                continue
            if c == c:                                          # drop NaN, never default
                series[d if isinstance(d, date) else date.fromisoformat(str(d)[:10])] = c
        if series:
            out[t] = series
    return out


async def compute(settled: date) -> Dict[str, Any]:
    from services.b9_live import build_world
    end = settled + timedelta(days=1)                       # yfinance's end is exclusive
    series = await asyncio.to_thread(_fetch, end - timedelta(days=HISTORY_DAYS), end)
    # CLAMP AGAIN ON THE DATA: nothing after the settled session survives, whatever was served.
    series = {t: {d: c for d, c in s.items() if d <= settled} for t, s in series.items()}
    return build_world(series, as_of=settled.isoformat())


@router.get("/world")
async def get_world() -> Dict[str, Any]:
    from stable_engine.market_calendar import CalendarHorizonError, last_settled_session
    try:
        settled = last_settled_session()
    except CalendarHorizonError as exc:
        return {"status": "unavailable", "reason": "no settled session (%s)" % exc, "data": None}
    key = CACHE_PREFIX + settled.isoformat()

    redis = None
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            hit = await redis.get(key)
            if hit:
                return {"status": "ok", "cached": True, "data": json.loads(hit)}
    except Exception as exc:                                    # noqa: BLE001
        logger.warning("[b9] redis read failed: %s", type(exc).__name__)

    if (_fail.get("session") == settled.isoformat()
            and time.monotonic() - _fail.get("at", 0) < FAIL_HOLD_S):
        return {"status": "unavailable", "reason": _fail["reason"], "data": None}

    async with _lock:
        try:
            data = await compute(settled)
        except Exception as exc:                                # noqa: BLE001
            reason = "B9 data could not be built for %s (%s)" % (settled, type(exc).__name__)
            logger.error("[b9] %s: %s", reason, exc)
            _fail.update(session=settled.isoformat(), at=time.monotonic(), reason=reason)
            return {"status": "unavailable", "reason": reason, "data": None}
    if redis:
        # A PARTIAL payload (some ticker missing) is held only briefly, so it is retried soon
        # without every card open re-fetching while the vendor is short.
        try:
            await redis.set(key, json.dumps(data),
                            ex=FAIL_HOLD_S if data.get("missing") else CACHE_TTL_S)
        except Exception as exc:                                # noqa: BLE001
            logger.warning("[b9] redis write failed: %s", type(exc).__name__)
    return {"status": "ok", "cached": False, "data": data}
