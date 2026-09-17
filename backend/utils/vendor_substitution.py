"""A substituted vendor is announced (R-IV.433(c), conventions #21).

A fallback that works is indistinguishable from the primary working -- until the day the two
vendors disagree and nobody can say which one a figure came from. That was the nine-day UW
diagnosis. So every consumer that swaps vendors calls `record_substitution`, every success on
the primary calls `record_primary`, and /health publishes `summary()` as `vendor_substitution`.

STATE, not a stream: a consumer serving many tickers can be on the primary for one and the
fallback for the next, so "the last call" would flap. A consumer is SUBSTITUTING while its most
recent substitution is younger than RECENT_S; it logs once when an episode starts (the first
swap after a quiet RECENT_S) and once when it ends.

In-process, since boot. A restart clears it, and the summary says so.

A fallback that is the primary BY DESIGN (yfinance for Yahoo-style indices UW does not carry)
is not a substitution and is not recorded as one.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

RECENT_S = 3600

_STATE: Dict[str, Dict[str, Any]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _entry(consumer: str, primary: str, fallback: Optional[str]) -> Dict[str, Any]:
    s = _STATE.get(consumer)
    if s is None:
        s = _STATE[consumer] = {"primary": primary, "fallback": fallback, "substitutions": 0,
                                "primary_ok": 0, "last_substituted_at": None,
                                "last_primary_at": None, "last_reason": None,
                                "last_subject": None, "episode_open": False}
    s["primary"] = primary
    if fallback:
        s["fallback"] = fallback
    return s


def _recent(ts: Optional[datetime], now: datetime) -> bool:
    return ts is not None and (now - ts) < timedelta(seconds=RECENT_S)


def record_substitution(consumer: str, primary: str, fallback: str, reason: str,
                        subject: Optional[str] = None) -> None:
    """Never raises."""
    try:
        now = _now()
        s = _entry(consumer, primary, fallback)
        opening = not s["episode_open"] or not _recent(s["last_substituted_at"], now)
        s["substitutions"] += 1
        s["last_substituted_at"] = now
        s["last_reason"] = str(reason)[:200]
        s["last_subject"] = subject
        if opening:
            s["episode_open"] = True
            logger.warning("VENDOR SUBSTITUTION %s: %s -> %s (%s)%s", consumer, primary, fallback,
                           s["last_reason"], f" [{subject}]" if subject else "")
    except Exception:  # a supervision write must never break the consumer
        pass


def record_primary(consumer: str, primary: str) -> None:
    """Never raises."""
    try:
        now = _now()
        s = _entry(consumer, primary, None)
        s["primary_ok"] += 1
        s["last_primary_at"] = now
        if s["episode_open"] and not _recent(s["last_substituted_at"], now):
            s["episode_open"] = False
            logger.info("VENDOR RESTORED %s: back on %s", consumer, primary)
    except Exception:
        pass


def summary(now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or _now()
    consumers = {}
    for name, s in sorted(_STATE.items()):
        substituting = _recent(s["last_substituted_at"], now)
        consumers[name] = {
            "state": "substituting" if substituting else "primary",
            "primary": s["primary"], "fallback": s["fallback"],
            "substitutions": s["substitutions"], "primary_ok": s["primary_ok"],
            "last_substituted_at": s["last_substituted_at"].isoformat() if s["last_substituted_at"] else None,
            "last_primary_at": s["last_primary_at"].isoformat() if s["last_primary_at"] else None,
            "last_reason": s["last_reason"], "last_subject": s["last_subject"],
        }
    return {"any_substituting": any(c["state"] == "substituting" for c in consumers.values()),
            "recent_window_s": RECENT_S, "scope": "in-process, since this process started",
            "consumers": consumers}
