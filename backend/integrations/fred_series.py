"""FRED daily series, fetched once and cached for the session. B3's only vendor call.

THE KEY IS NEVER PRINTED, NEVER LOGGED AND NEVER SERVED. R-IV.1210(c)/1212(c) confirm it
exists; this module reports only whether it is PRESENT. Every log line here says
"FRED_API_KEY present/missing", never a value, never a length, never a prefix -- a prefix is
enough to confirm a guess.

ONE CALL PER SERIES PER DAY. These are daily series: FRED publishes one observation a session,
so polling them more often spends a call to receive the same number. The cache key is the
series id plus the UTC date, and a miss is the only thing that reaches the network.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
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

_cache: Dict[str, Tuple[_dt.date, List[Tuple[_dt.date, Optional[float]]]]] = {}


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
    if hit and hit[0] == today:
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
    _cache[series_id] = (today, out)
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
