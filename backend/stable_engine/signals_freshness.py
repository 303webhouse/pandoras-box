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
from zoneinfo import ZoneInfo

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
    "STRIKE_IB_BREAK",
    # T3, R-IV.295(a). A CONSUMER job, not a producer -- see AGE_SOURCE below.
    "triton_grader",
})

# ── PLUGGABLE AGE SOURCE (T3, R-IV.295(a)) ────────────────────────────────
# This module's premise was that every class is a signal PRODUCER, so every age
# came from MAX(created_at) ON signals. The Triton grader is a signal CONSUMER:
# it UPDATEs triton_flow_shadow and never writes a signals row.
#
# Registering it without this hook would have given it age=None forever, so
# _class_status could only ever return "no_data" and THE STALENESS BRANCH COULD
# NEVER FIRE -- a sentinel that cannot fail, inside the task built to add
# supervision. Same surface, same alarm path, different age source.
AGE_SOURCE_SIGNALS = "signals"
AGE_SOURCE_JOB_RUNS = "job_runs"
AGE_SOURCES: dict[str, str] = {"triton_grader": AGE_SOURCE_JOB_RUNS}

# Classes whose work is expected once per TRADING SESSION rather than continuously.
# Their SLO is only evaluated when a pass was actually due -- see _pass_overdue().
SESSION_JOB_CLASSES = frozenset({"triton_grader"})

# The grader runs post-close; give it until 16:15 ET plus grace before a pass for
# that session is considered due.
SESSION_JOB_DUE_HOUR_ET = 17

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
    # ~1 emission/session; the per-ticker watermark in
    # jobs/strike_ib_converter.py is the REAL alarm. This is only a
    # total-death backstop, and it must not page across weekends or
    # holidays -- a 26h SLO on a weekday-only producer is a guaranteed
    # false red roughly 104 times a year.
    "STRIKE_IB_BREAK": 5 * 24 * 3600,
    # T3 (R-IV.295(a)): "pass completed within 26h".
    #
    # 26h ALONE WOULD BE A GUARANTEED WEEKEND FALSE RED -- this module already
    # says so six lines above, about a different weekday-only job. The grader runs
    # weekdays post-close, so Friday's pass is 48h+ old by Sunday and the hour
    # bound would fire every single weekend.
    #
    # So the hour bound is kept AND gated on whether a pass was DUE
    # (_pass_overdue). The declared unit is ~100% OF DUE PASSES (R-IV.298(a)
    # corrects R-IV.295(a)'s 'calendar days'); ungated, a bare 26h bound would
    # miss roughly two days in seven and the declaration could not hold.
    "triton_grader": 26 * 3600,
}

# Classes that only flow during regular trading hours. Crypto runs 24/7 and must
# not flatline overnight or at weekends (anti-fake-sick).
RTH_ONLY_CLASSES = frozenset({"tradingview", "server_scanner", "cta_scanner",
                             "footprint", "STRIKE_IB_BREAK"})

def _pass_overdue(last_session_date, now_et=None) -> bool:
    """Is a session-job pass actually DUE and missing?

    Weekday approximation, deliberately and temporarily: T7 replaces this with the
    single market-calendar utility. Until then it is a HOLIDAY false red, which is
    a smaller and rarer wrong than a weekend one -- stated so the next reader does
    not mistake it for a considered permanent choice.
    """
    from datetime import timedelta
    if now_et is None:
        now_et = datetime.now(ZoneInfo("America/New_York"))
    # Most recent TRADING day whose post-close has passed. T7 (R-IV.319(b))
    # replaces the weekday approximation this function shipped with -- it was the
    # fifth member of that family and was labelled temporary when written.
    from stable_engine.market_calendar import CalendarHorizonError, is_trading_day

    d = now_et.date()
    if now_et.hour < SESSION_JOB_DUE_HOUR_ET:
        d = d - timedelta(days=1)
    try:
        while not is_trading_day(d):
            d = d - timedelta(days=1)
    except CalendarHorizonError as exc:
        # A health read must not raise. Say so and use the old rule, which is
        # WRONG ONLY ON HOLIDAYS -- and say which, so the alarm is read correctly.
        logger.error("[signals_freshness] calendar exhausted at %s (%s) -- weekday "
                     "fallback; holiday reads may be false", d, exc)
        while d.weekday() >= 5:
            d = d - timedelta(days=1)
    if last_session_date is None:
        return True
    return last_session_date < d


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


def _class_status(cls: str, age: float | None, rejected: int,
                  last_session_date=None) -> str:
    """Rejections escalate independently of age, at any hour."""
    if rejected > 0:
        return "flatline"
    if cls in SESSION_JOB_CLASSES:
        # A session job is judged on WHETHER A DUE PASS IS MISSING, then on the
        # hour bound. Age alone cannot distinguish "no pass was due" (a weekend)
        # from "a pass was due and never came" -- and those are opposite facts.
        if not _pass_overdue(last_session_date):
            return "ok"
        if age is None:
            return "no_data"
        return "flatline" if age > SLO_SECONDS.get(cls, DEFAULT_SLO_SECONDS) else "ok"
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

    # ── pluggable age source (T3) ──────────────────────────────────────────
    # Consumer jobs do not appear in the signals query above; their age comes from
    # job_runs. Read per class so a failure on one never blanks the others.
    session_dates: dict[str, object] = {}
    for cls, src in AGE_SOURCES.items():
        if src != AGE_SOURCE_JOB_RUNS:
            continue
        try:
            from jobs.job_runs import last_completed
            row = await last_completed(cls)
            if row and row.get("finished_at") is not None:
                fin = row["finished_at"]
                if fin.tzinfo is None:
                    fin = fin.replace(tzinfo=timezone.utc)
                ages[cls] = (now - fin).total_seconds()
                session_dates[cls] = row.get("session_date")
        except Exception as e:
            # Unknown, NOT stale. Leaving the age absent renders "no_data";
            # inventing a large age would render "flatline" and fabricate an
            # outage out of a read failure.
            logger.error("[signals_freshness] job_runs age read failed for %s: %s", cls, e)

    counters = counters_snapshot()
    classes: dict[str, dict] = {}
    worst = "ok"
    oldest: float | None = None

    # Registry ∪ anything actually observed -- a class that appears but was never
    # registered must surface, not hide.
    for cls in sorted(REGISTERED_CLASSES | set(ages) | set(counters)):
        c = counters.get(cls, {"persisted": 0, "rejected": 0, "deduped": 0})
        age = ages.get(cls)
        status = _class_status(cls, age, c["rejected"],
                               last_session_date=session_dates.get(cls))
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
