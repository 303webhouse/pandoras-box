"""FRED daily series, fetched once and cached for the session. B3's only vendor call.

THE KEY IS NEVER PRINTED, NEVER LOGGED AND NEVER SERVED. R-IV.1210(c)/1212(c) confirm it
exists; this module reports only whether it is PRESENT. Every log line here says
"FRED_API_KEY present/missing", never a value, never a length, never a prefix -- a prefix is
enough to confirm a guess.

A SHORT TTL, NOT ONE CALL PER UTC DAY -- and the original rule is worth stating because it
read as obviously right. It was: "these are daily series, so polling them more often spends a
call to receive the same number", with the cache keyed on the series id plus the UTC date.
The premise is FALSE for the two hours a day that matter. FRED's H.15 Treasury series publish
session D's value on the NEXT business day, late in the ET afternoon, so a process that fetches
before that release caches a copy whose newest observation is a session old -- and a key of
(series, UTC date) then pins that copy until the UTC date rolls at 20:00 ET.

MEASURED 2026-10-22 22:22Z, which is why this changed. The hub started 19:03:00Z, about 75
minutes before FRED published 10-21. Asked directly at 22:22Z, FRED served DGS10 10-21=5.13
and T10Y2Y 10-22=0.31; the hub's own /api/yield-curve served 10Y as of 10-20=5.12 and 2s10s as
of 10-21=0.32. Every figure in the yield box was EXACTLY ONE SESSION behind its own source,
with no error anywhere and nothing blank -- the box looked healthy and was wrong.

THE OTHER HALF OF THIS BOX ALREADY LEARNED THIS. `models/yield_intraday.py` carries
`CACHE_SECONDS = 15 * 60` and a test named `test_the_cache_is_one_bar_long_and_not_one_day`,
whose reason -- "a day-long cache on an intraday series serves the open all afternoon" -- is
the same fault one tier up. A daily series does not need a 15-minute window, but it does need
one shorter than the gap between a release and the end of the UTC day.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import time as _time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("fred_series")

SOURCE = "FRED (Federal Reserve Bank of St. Louis), series/observations"
#: Public-domain US government data. FRED's terms permit automated retrieval with a key and ask
#: that the source be attributed, which the payload does on every read.
TERMS = ("FRED's API terms permit automated retrieval with a registered key; the Treasury "
         "series are US government public-domain data and are attributed on every payload")

#: 6 years is enough for the fire-rate measurement to span several rate regimes, which is the
#: point: a rate measured only over 2024-2026 would describe one regime and be quoted as the
#: series' nature.
HISTORY_YEARS = 6

#: How long a fetched series is reused, in seconds. 30 minutes bounds the post-release lag to
#: half an hour while keeping the call count trivial: six series at 48 refreshes a day is 288
#: requests, against a FRED allowance of 120 a MINUTE. The old rule spent 6 calls a day and
#: was wrong for four hours of it, which is not a trade worth having.
CACHE_SECONDS = 30 * 60


def _now() -> float:
    """The cache's clock, as a seam. A test advances THIS rather than patching the stdlib
    `time.monotonic`, which pytest and asyncio also read -- and more importantly, a test that
    reaches into `_cache` to fake an expiry proves nothing about the fix, because the old
    day-keyed predicate never looked at the stored number at all. Advancing the clock is what
    distinguishes the two rules."""
    return _time.monotonic()

#: series id -> (monotonic seconds at fetch, points). NOT keyed on the date: see the module
#: docstring. `time.monotonic` rather than wall clock so a clock correction cannot make an
#: entry look fresh for hours.
_cache: Dict[str, Tuple[float, List[Tuple[_dt.date, Optional[float]]]]] = {}


def key_present() -> bool:
    """Whether FRED_API_KEY is set. The ONLY thing this module says about the key."""
    return bool((os.environ.get("FRED_API_KEY") or "").strip())


def fetch_series(series_id: str, *,
                 years: int = HISTORY_YEARS,
                 today: Optional[_dt.date] = None) -> List[Tuple[_dt.date, Optional[float]]]:
    """[(date, value or None)] ascending. Cached per series per day.

    Raises nothing: an unavailable series returns an EMPTY list, and the caller reports the
    absence rather than serving a stale number as current. A missing key likewise returns
    empty, with a log line naming the variable and not its value.
    """
    today = today or _dt.datetime.now(_dt.timezone.utc).date()
    hit = _cache.get(series_id)
    if hit and (_now() - hit[0]) < CACHE_SECONDS:
        return hit[1]
    if not key_present():
        logger.warning("[fred] FRED_API_KEY is missing; %s not fetched", series_id)
        return []
    start = today - _dt.timedelta(days=int(365.25 * years))
    try:
        from fredapi import Fred

        fred = Fred(api_key=os.environ["FRED_API_KEY"])
        s = fred.get_series(series_id, observation_start=start.isoformat())
    except Exception as exc:                                        # noqa: BLE001
        # The exception TYPE, never the message: fredapi puts the request URL -- and therefore
        # the key -- in some error strings.
        logger.error("[fred] %s failed: %s (FRED_API_KEY present)", series_id,
                     type(exc).__name__)
        return []
    if s is None or getattr(s, "empty", True):
        logger.warning("[fred] %s returned no observations", series_id)
        return []
    out: List[Tuple[_dt.date, Optional[float]]] = []
    for idx, val in s.items():
        d = idx.date() if hasattr(idx, "date") else idx
        try:
            f = float(val)
            f = None if f != f else f                                # NaN is a hole, not a 0
        except Exception:                                           # noqa: BLE001
            f = None
        out.append((d, f))
    out.sort(key=lambda p: p[0])
    _cache[series_id] = (_now(), out)
    logger.info("[fred] %s: %d observations %s..%s", series_id, len(out),
                out[0][0].isoformat(), out[-1][0].isoformat())
    return out


def latest(points: List[Tuple[_dt.date, Optional[float]]]) -> Tuple[Optional[_dt.date],
                                                                    Optional[float]]:
    """The newest observation that HAS a value, with its own date.

    Its own date, not today's: FRED's series lag by a day or more, and stamping a reading with
    the date it was READ rather than the date it IS is how a stale number passes for fresh.
    """
    for d, v in reversed(points):
        if v is not None:
            return d, v
    return None, None


def cache_state() -> Dict[str, Any]:
    """What is held, and how old it is. R-IV.1343(c).

    THE POINT IS THAT STALENESS BE VISIBLE. A one-session-stale series and a current one look
    identical in the payload -- same shape, no error, nothing blank -- which is how the yield
    box served a full set of numbers that were all a session behind their own source and
    nobody could tell. The age and the newest observation date together make it readable.

    NAMES NO KEY AND NO VALUE, like everything else here: series ids, ages and observation
    DATES only.
    """
    now = _now()
    series: Dict[str, Any] = {}
    for sid, (at, pts) in _cache.items():
        newest = None
        for d, v in reversed(pts):
            if v is not None:
                newest = d.isoformat()
                break
        series[sid] = {"age_seconds": int(now - at), "newest_observation": newest,
                       "observations": len(pts)}
    return {"ttl_seconds": CACHE_SECONDS, "key_present": key_present(),
            "basis": ("a fetched series is reused for at most ttl_seconds; it is NOT one call "
                      "per UTC day, which pinned a pre-release copy for the rest of the day"),
            "series": series}
