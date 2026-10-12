"""Signals that failed to persist, counted where we already look — R-IV.839(b).

WHY A LEDGER AND NOT A LOG LINE. Every emitter wraps its `log_signal` call in
`except Exception`, so a failed write has always produced at most a WARNING in a stream nobody
reads, and the absence of rows for a signal type was indistinguishable from that type never
firing. Four Nemesis defects and three more cases (Scout Sniper, STRIKE_IB_BREAK, the grader's
SCOUT_ALERT) were all found by someone noticing an empty table, which is the slowest possible
detector.

A COUNT BY TYPE IS THE RIGHT SHAPE. "Writes are failing" is not actionable; "every SCOUT_ALERT
write failed and nothing else did" names the emitter. So the ledger keys on signal_type and
/health serves the last 24 hours grouped by it.

AND A FAILURE THAT COULD NOT BE RECORDED IS WORSE EVIDENCE THAN ONE THAT COULD. If Postgres is
the reason the signal did not persist, it is also the reason this row will not persist -- so the
ledger would read clean at exactly the moment it matters most. The in-process counter below
exists for that case and is reported alongside, following the precedent job_status set with
`unrecorded_failures` (R-IV.360(1)): the row's absence is not evidence of health.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, Optional

logger = logging.getLogger("signals.persist_failures")

TABLE = "signal_persist_failures"

DDL = """
CREATE TABLE IF NOT EXISTS signal_persist_failures (
    id           BIGSERIAL PRIMARY KEY,
    occurred_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    signal_type  TEXT,
    strategy     TEXT,
    ticker       TEXT,
    signal_id    TEXT,
    source       TEXT,
    error_class  TEXT NOT NULL,
    error_detail TEXT,
    missing      TEXT[]
)
"""

DDL_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_signal_persist_failures_recent "
    "ON signal_persist_failures (occurred_at DESC)"
)

# Failures Postgres itself could not record. Process-local and therefore lost on restart, which
# is acceptable only because it is reported as its own number and never folded into the ledger's
# count -- a reader must be able to tell "nothing failed" from "nothing could be written down".
_unrecorded: Counter = Counter()


def reset_for_tests() -> None:
    _unrecorded.clear()


def unrecorded() -> Dict[str, int]:
    return dict(_unrecorded)


async def ensure_table(conn) -> None:
    await conn.execute(DDL)
    await conn.execute(DDL_INDEX)


async def record(signal_data: Optional[Dict[str, Any]], exc: BaseException, *,
                 pool=None) -> bool:
    """Write one failure. NEVER RAISES — it is called from an error path, and an exception here
    would replace a reported failure with an unreported one."""
    sd = signal_data or {}
    missing = list(getattr(exc, "missing", []) or [])
    sig_type = sd.get("signal_type")
    try:
        if pool is None:
            from database.postgres_client import get_postgres_client
            pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await ensure_table(conn)
            await conn.execute(
                "INSERT INTO signal_persist_failures (signal_type, strategy, ticker, signal_id,"
                " source, error_class, error_detail, missing)"
                " VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                sig_type, sd.get("strategy"), sd.get("ticker"), sd.get("signal_id"),
                sd.get("source"), type(exc).__name__, str(exc)[:2000],
                missing or None,
            )
        return True
    except Exception as inner:                                      # noqa: BLE001
        _unrecorded[sig_type or "UNKNOWN"] += 1
        # ERROR, and distinct wording: this is the case where the surface cannot be trusted.
        logger.error("[persist_failures] UNRECORDED failure for %s (%s) — ledger write also "
                     "failed: %s", sig_type, type(exc).__name__, inner)
        return False


async def summary_24h(pool=None) -> Dict[str, Any]:
    """{total, by_type, unrecorded}. Fail-safe: an error here degrades /health, never breaks it.

    An empty ledger is reported as zero WITH the unrecorded counter beside it, so a clean sheet
    can be distinguished from a ledger that could not be written.
    """
    out: Dict[str, Any] = {"total_24h": 0, "by_type_24h": {}, "unrecorded": unrecorded()}
    try:
        if pool is None:
            from database.postgres_client import get_postgres_client
            pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await ensure_table(conn)
            rows = await conn.fetch(
                "SELECT COALESCE(signal_type, 'UNKNOWN') AS t, COUNT(*) AS n"
                " FROM signal_persist_failures"
                " WHERE occurred_at > NOW() - INTERVAL '24 hours'"
                " GROUP BY 1 ORDER BY n DESC"
            )
        by_type = {r["t"]: int(r["n"]) for r in rows}
        out["by_type_24h"] = by_type
        out["total_24h"] = sum(by_type.values())
    except Exception as exc:                                        # noqa: BLE001
        out["error"] = "%s: %s" % (type(exc).__name__, exc)
    return out
