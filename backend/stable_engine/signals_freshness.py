"""Signals-persistence freshness + issued-vs-persisted reconciliation.

DEF-SIGNAL-PERSISTENCE-COLLAPSE (2026-08-20). Between 2026-08-18 13:23:37Z and
2026-08-19 22:30:31Z the pipeline logged completions for 459 signals that never
reached the table. /health reported "healthy" throughout, because nothing in it
looked at the signals table at all.

Two terms, because either alone is blind to a real failure mode:

  * STALENESS -- sourced from the signals TABLE (MAX(created_at) per emitter
    class). Catches "the writer or the scanner died"; nothing is arriving.

  * REJECTION RATE -- persisted / rejected / deduped, counted per class.
    Catches the ghost case the table structurally cannot see: a rejected row
    leaves no trace to be stale about. `persisted` increments only on
    log_signal()'s boolean, which is the INSERT's own rowcount -- DB truth, not
    a self-assessment.

Age alone is disqualified on two-sided evidence: QS-03-A1 read CLEAN at 15m34s
*inside* the collapse, and a 2m36s age read green on 08-19 while throughput was
4 rows from one emitter against a ~140/day baseline. Rejections escalate
INDEPENDENTLY of the age predicate and at any hour (R-IV.44(c)) -- the overnight
webhook path is live; 04:12Z HAL was the last row before the collapse.

THREE OUTCOMES, NOT TWO (R-IV.47(b)). A dedupe is a correct no-op. Counting it as
a gap would make this alarm contradict completion_status() about the same event,
in the same commit. dedupe is counted and surfaced, never alarmed.

THE REGISTRY IS STATIC (R-IV.47(c)). Classes are never derived from the table: a
record-dependent instrument is void exactly when the record dies, which is this
module's founding lesson. A registered class with no rows in-window renders
"no_data", never absent and never ok.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from stable_engine.job_status import is_market_hours

logger = logging.getLogger(__name__)

# Mirrors postgres_client.py:1707 -- `signal_data.get("source") or "tradingview"`.
# One shared definition so the counter key and the column value cannot diverge
# (R-IV.47(d) F11: alignment by construction, not convention).
DEFAULT_SOURCE = "tradingview"


def class_key(source: str | None) -> str:
    """THE canonical emitter-class key. Used by both writer and reader."""
    return (source or DEFAULT_SOURCE).strip() or DEFAULT_SOURCE


# Static registry, authored 2026-08-20 from the observed source values on the
# live table. Deriving this list ONCE at authoring time is sound; deriving it at
# runtime is the failure (c) forbids.
REGISTERED_CLASSES: frozenset[str] = frozenset({
    "tradingview", "server_scanner", "cta_scanner",
    "crypto_scanner", "crypto_engine", "crypto_cvd_engine", "footprint",
})

# Per-class staleness SLO (seconds) -- the "nothing is arriving at all" detector.
DEFAULT_SLO_SECONDS = 4 * 3600
SLO_SECONDS: dict[str, int] = {
    "tradingview": 4 * 3600,
    "server_scanner": 4 * 3600,
    "cta_scanner": 4 * 3600,
    "footprint": 6 * 3600,
    "crypto_scanner": 12 * 3600,
    "crypto_engine": 12 * 3600,
    "crypto_cvd_engine": 12 * 3600,
}

# Classes that only flow during regular trading hours. Crypto runs 24/7 and must
# not flatline overnight or at weekends (anti-fake-sick).
RTH_ONLY_CLASSES = frozenset({"tradingview", "server_scanner", "cta_scanner", "footprint"})

_RANK = {"ok": 0, "no_data": 1, "stale": 1, "flatline": 2}

_COUNTERS: dict[str, dict[str, int]] = defaultdict(
    lambda: {"persisted": 0, "rejected": 0, "deduped": 0}
)
_LAST_ERROR: dict[str, str] = {}


def record_attempt(source: str | None, persisted: bool,
                   error: str | None = None) -> None:
    """Called once per signal at the persistence step. Never raises.

    Three outcomes: persisted (row landed) / rejected (exception) /
    deduped (ON CONFLICT DO NOTHING -- a correct no-op).
    """
    try:
        key = class_key(source)
        c = _COUNTERS[key]
        if persisted:
            c["persisted"] += 1
        elif error is not None:
            c["rejected"] += 1
            _LAST_ERROR[key] = error[:300]
        else:
            c["deduped"] += 1
    except Exception:  # metrics must never break the pipeline
        pass


def counters_snapshot() -> dict[str, dict[str, int]]:
    return {k: dict(v) for k, v in _COUNTERS.items()}


def _class_status(cls: str, age: float | None, rejected: int) -> str:
    """Rejections escalate independently of age, at any hour."""
    if rejected > 0:
        return "flatline"
    rth_gated = cls in RTH_ONLY_CLASSES and not is_market_hours()
    if age is None:
        return "ok" if rth_gated else "no_data"
    if age > SLO_SECONDS.get(cls, DEFAULT_SLO_SECONDS) and not rth_gated:
        return "flatline"
    return "ok"


async def signals_freshness_summary() -> dict:
    """The /health signals_freshness block. Mirrors health_summary()'s contract."""
    now = datetime.now(timezone.utc)
    ages: dict[str, float] = {}
    try:
        from database.postgres_client import get_postgres_client

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT source, MAX(created_at) AS last_at FROM signals "
                "WHERE created_at >= (NOW() AT TIME ZONE 'UTC') - INTERVAL '7 days' "
                "GROUP BY source"
            )
        for r in rows:
            last_at = r["last_at"]
            if last_at is None:
                continue
            if last_at.tzinfo is None:
                last_at = last_at.replace(tzinfo=timezone.utc)
            ages[class_key(r["source"])] = (now - last_at).total_seconds()
    except Exception as e:
        # A read failure is NOT health -- it is unknown, and unknown escalates.
        logger.error("[signals_freshness] table read failed: %s", e)
        return {
            "worst_status": "flatline",
            "oldest_persist_age_s": None,
            "any_flatline": True,
            "error": str(e)[:300],
            "classes": {},
        }

    counters = counters_snapshot()
    classes: dict[str, dict] = {}
    worst = "ok"
    oldest: float | None = None

    # Registry ∪ anything actually observed -- a class that appears but was never
    # registered must surface, not hide.
    for cls in sorted(REGISTERED_CLASSES | set(ages) | set(counters)):
        c = counters.get(cls, {"persisted": 0, "rejected": 0, "deduped": 0})
        age = ages.get(cls)
        status = _class_status(cls, age, c["rejected"])
        if _RANK[status] > _RANK[worst]:
            worst = status
        if age is not None and (cls not in RTH_ONLY_CLASSES or is_market_hours()):
            oldest = age if oldest is None else max(oldest, age)
        classes[cls] = {
            "status": status,
            "last_persist_age_s": round(age) if age is not None else None,
            "persisted": c["persisted"],
            "rejected": c["rejected"],
            "deduped": c["deduped"],
            "reconciliation_gap": c["rejected"],  # rejections only; dedupe is not a gap
            "registered": cls in REGISTERED_CLASSES,
            "last_error": _LAST_ERROR.get(cls),
        }

    return {
        "worst_status": worst,
        "oldest_persist_age_s": round(oldest) if oldest is not None else None,
        "any_flatline": worst == "flatline",
        "classes": classes,
    }
