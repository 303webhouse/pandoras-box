"""
Poller pause flags — R-IV.273(c) / R-IV.274(a).

The dark-pool and market-tide pollers spend UW quota on data that currently has no
database sink (the compute-then-discard family). The sinks build ships at position 2
with backfill from UW history, so nothing is lost by pausing the spend until then.

FORM. Environment variables, read at the TOP OF EACH CYCLE — not at task creation.
Two consequences follow from per-cycle reads and both are deliberate:

  1. The paused state is provable from the RUNNING PROCESS (`/health.paused_pollers`),
     which is what R-IV.274(a) requires. A flag consumed once at startup can be read
     from the Railway dashboard and nowhere else, and a dashboard value is a claim
     about configuration, not evidence about behaviour.
  2. Lifting the pause requires a restart to change the variable, but no code change.

FAIL-OPEN, deliberately. Only the exact string "true" pauses. Unset, empty, or any
other value runs the poller. A pause that could happen by ACCIDENT — a typo, a
dropped variable, a bad default — would silently stop data collection, which is the
failure this board keeps finding under other names. Stopping collection must be an
act, never an omission.

Railway returns '' rather than None for an unset reference, so `os.getenv(X) or ""`
is the required idiom here; `os.getenv(X, default)` does NOT return the default.
"""

import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# poller name -> environment variable that pauses it
PAUSE_FLAGS: Dict[str, str] = {
    "darkpool": "PAUSE_DARKPOOL_POLLER",
    "tide": "PAUSE_TIDE_POLLER",
}

# Last observed state per poller, for transition logging. Deliberately NOT used to
# decide anything — only to keep the log to events rather than a per-cycle heartbeat.
# The 500-line Railway buffer is a diagnostic resource; a 5-minute heartbeat would
# consume it in under two days and cost the next diagnosis its evidence.
_last_seen: Dict[str, Optional[bool]] = {name: None for name in PAUSE_FLAGS}


def is_paused(poller: str) -> bool:
    """True only when this poller's flag is exactly "true" (case-insensitive)."""
    var = PAUSE_FLAGS[poller]
    return (os.getenv(var) or "").strip().lower() == "true"


def check_paused(poller: str) -> bool:
    """is_paused(), logging only on a state CHANGE — including the first observation
    after a restart, so a process that boots already paused still says so once."""
    paused = is_paused(poller)
    if _last_seen[poller] != paused:
        logger.info(
            "[poller_pause] %s poller %s (%s=%s)",
            poller,
            "PAUSED — skipping cycle, no UW spend" if paused else "RUNNING",
            PAUSE_FLAGS[poller],
            "true" if paused else (os.getenv(PAUSE_FLAGS[poller]) or "<unset>"),
        )
        _last_seen[poller] = paused
    return paused


def pause_status() -> Dict[str, object]:
    """Reported on /health so the paused state is readable from the running process.

    Does NOT participate in the overall health verdict: a pause is an intended state,
    and an intended state that degrades health teaches readers to discount the health
    signal — the mechanism already registered as DEF-PYTHIA-ALARM-NOT-ACTIONED.
    """
    paused = {name: is_paused(name) for name in PAUSE_FLAGS}
    return {
        "pollers": paused,
        "any_paused": any(paused.values()),
        "authority": "R-IV.273(c) — spend paused until the sinks build ships",
    }
