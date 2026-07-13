"""Stater Swap v2 S-1 Phase 1 (F-1 task 1.5, AEGIS A3) — crypto vendor
health-state tracking (LIVE / DEGRADED / DEAD) with an audit trail on every
transition.

Design notes:
  - State is tracked in-process (module-level dict), matching the existing
    convention in this same package (crypto_setups.py's _can_fire/_mark_fired
    cooldown is documented as process-local, lost on restart — same
    tradeoff, not a new weaker pattern).
  - Audit rows are written ONLY on a status transition, not on every call —
    this is an event log (mirrors triton_flow_shadow's shadow-logging
    style), not a per-poll snapshot table. A vendor that stays LIVE forever
    produces zero audit rows; that's correct.
  - Callers report every read attempt via record_observation(), regardless
    of outcome. A failed bounds check (see crypto_sanity_bounds.py) is
    reported as success=True, value_valid=False — the request succeeded but
    the payload was implausible, which is a distinct failure mode from "the
    vendor didn't respond" and should read distinctly in `reason`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# (vendor, feed_type, symbol) -> {"status": str, "last_success_at": datetime|None, "reason": str|None}
_STATE: dict[tuple, dict] = {}

# feed_type -> (degraded_after_seconds, dead_after_seconds). Set relative to
# each client's existing cache TTL (Phase 0 findings: 300s for
# funding/OI/liq/term/skew/basis, 60s for orderbook, 900s for stablecoin
# APRs) — degrade at ~3x TTL, dead at ~12x TTL, so a couple of missed polls
# don't flip status but a genuinely stuck feed does.
_STALENESS_THRESHOLDS_SECONDS: dict[str, tuple[int, int]] = {
    "funding_rate": (900, 3600),
    "open_interest": (900, 3600),
    "liquidations": (900, 3600),
    "term_structure": (900, 3600),
    "skew_25d": (900, 3600),
    "orderbook_skew": (180, 900),
    "quarterly_basis": (900, 3600),
    "stablecoin_aprs": (2700, 10800),
}
_DEFAULT_THRESHOLDS = (900, 3600)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_current_status(vendor: str, feed_type: str, symbol: str) -> Optional[str]:
    """Read-only lookup, e.g. for the F-3 state envelope. Returns None if never observed."""
    key = (vendor, feed_type, (symbol or "").upper())
    entry = _STATE.get(key)
    return entry["status"] if entry else None


async def record_observation(
    vendor: str,
    feed_type: str,
    symbol: str,
    success: bool,
    value_valid: bool = True,
    reason: Optional[str] = None,
) -> str:
    """Report one read attempt. Returns the resulting status ('LIVE'/'DEGRADED'/'DEAD').

    Writes an audit row to crypto_vendor_health_audit iff status changed.
    Never raises — a failure to write the audit row is logged and swallowed,
    since losing an audit entry must not take down the caller's data path.
    """
    key = (vendor, feed_type, (symbol or "").upper())
    now = _now()
    prev = _STATE.get(key, {"status": None, "last_success_at": None, "reason": None})
    degraded_after, dead_after = _STALENESS_THRESHOLDS_SECONDS.get(feed_type, _DEFAULT_THRESHOLDS)

    if success and value_valid:
        new_status = "LIVE"
        last_success_at = now
        new_reason = None
    else:
        last_success_at = prev["last_success_at"]
        age = (now - last_success_at).total_seconds() if last_success_at else None
        if age is None:
            new_status = "DEAD"
            new_reason = reason or "no_successful_read_yet"
        elif age > dead_after:
            new_status = "DEAD"
            new_reason = reason or f"no_valid_read_in_{int(age)}s"
        elif age > degraded_after:
            new_status = "DEGRADED"
            new_reason = reason or f"stale_or_invalid_read, last good data {int(age)}s old"
        else:
            # Recent enough that one bad attempt doesn't flip a healthy feed yet.
            new_status = prev["status"] or "DEGRADED"
            new_reason = reason or f"transient failure, last good data {int(age)}s old"

    transitioned = prev["status"] != new_status
    _STATE[key] = {"status": new_status, "last_success_at": last_success_at, "reason": new_reason}

    if transitioned:
        data_age = (now - last_success_at).total_seconds() if last_success_at else None
        await _write_audit_row(
            vendor=vendor, feed_type=feed_type, symbol=(symbol or "").upper(),
            status=new_status, previous_status=prev["status"], reason=new_reason,
            as_of=last_success_at, data_age_seconds=data_age,
        )
        logger.info(
            "crypto vendor health transition: %s/%s/%s %s -> %s (%s)",
            vendor, feed_type, symbol, prev["status"], new_status, new_reason,
        )

    return new_status


async def _write_audit_row(
    vendor: str, feed_type: str, symbol: str, status: str,
    previous_status: Optional[str], reason: Optional[str],
    as_of: Optional[datetime], data_age_seconds: Optional[float],
    sanction_decision: Optional[str] = None,
) -> None:
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO crypto_vendor_health_audit
                    (vendor, feed_type, symbol, status, previous_status, reason,
                     as_of, data_age_seconds, sanction_decision)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                vendor, feed_type, symbol, status, previous_status, reason,
                as_of, data_age_seconds, sanction_decision,
            )
    except Exception as exc:
        logger.warning("crypto_vendor_health_audit write failed (non-fatal): %s", exc)


async def record_sanction_decision(vendor: str, decision: str, reason: str) -> None:
    """One-off audit entry for a vendor-level sanction/replace/not-sanction
    decision (F-1 tasks 1.1/1.3), distinct from routine per-feed health
    transitions. `decision` is one of SANCTIONED / REPLACED / NOT_SANCTIONED.
    """
    await _write_audit_row(
        vendor=vendor, feed_type="_vendor_decision", symbol="_ALL",
        status="N/A", previous_status=None, reason=reason,
        as_of=_now(), data_age_seconds=0, sanction_decision=decision,
    )
