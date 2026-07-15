"""Stater Swap v2 S-1 Phase 4 (F-4) — crypto L0 routing dual-write shadow.

`bias_scheduler.py`'s "Crypto Scanner" (`run_crypto_scan_scheduled`) is the
one crypto signal path Phase 0 found bypassing `process_signal_unified`
(writes via `log_signal` directly — see
docs/strategy-reviews/stater-swap-redesign/s1-phase0-findings.md). This
module runs that same signal through `process_signal_unified(shadow=True)`
on a COPY with a distinct signal_id, and records what the real governance
chokepoint would have decided into the dedicated `crypto_dual_write_shadow`
table (migration 024) — never the real `signals` table, never Discord/
WebSocket/committee/cache. The real (bypass) path's behavior is completely
unchanged; this is pure additional observation.

Hard rule (brief F-4.2): no live cutover without Nick's written greenlight
on the diff report produced by `scripts/crypto_dual_write_diff_report.py`
after >=48h of 24/7 operation or n>=30 shadow rows, whichever comes first.
This module only writes evidence — it never disables or replaces the real
`log_signal` call.

Hot-reload (brief F-4.3): the dual-write can be disabled without a redeploy
via the Redis flag below, mirroring `uw_budget_watchdog.py`'s
`quota_shed:triton` pattern (a proven no-redeploy-needed runtime toggle;
`system_config` in Postgres is unused/aspirational schema, not a working
pattern — see Phase 4 investigation notes in the findings doc).
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DUAL_WRITE_TOGGLE_KEY = "crypto_dual_write:enabled"
COMMITTEE_SCORE_THRESHOLD = 85.0  # mirrors signals/pipeline.py's constant of the same name


async def is_dual_write_enabled() -> bool:
    """Redis-backed hot toggle. Fail-open to enabled on Redis error (this is
    an observation-only shadow write; failing open just means we keep
    collecting evidence, never a live-path risk)."""
    try:
        from database.redis_client import get_redis_client
        r = await get_redis_client()
        if not r:
            return True
        val = await r.get(DUAL_WRITE_TOGGLE_KEY)
        if val is None:
            return True
        return str(val).strip().lower() not in ("0", "false", "off", "disabled")
    except Exception as exc:
        logger.debug("crypto_dual_write toggle check failed (fail-open, enabled): %s", exc)
        return True


async def shadow_write_crypto_signal(trade_signal: dict, real_signal_id: str) -> None:
    """Run `trade_signal` through process_signal_unified(shadow=True) on a
    copy and record the result in crypto_dual_write_shadow. Swallows all
    errors — a shadow-write failure must never affect the real (bypass)
    signal path that already completed before this is called.
    """
    if not await is_dual_write_enabled():
        return

    try:
        from signals.pipeline import process_signal_unified
        from database.postgres_client import get_postgres_client

        shadow_signal = copy.deepcopy(trade_signal)
        shadow_signal["signal_id"] = f"SHADOW_{real_signal_id}"
        # Clear any real-path-specific state that shouldn't leak into the
        # shadow eval's own scoring/classification pass.
        shadow_signal.pop("score", None)
        shadow_signal.pop("bias_alignment", None)
        shadow_signal.pop("triggering_factors", None)

        result = await process_signal_unified(
            shadow_signal, source="crypto_scanner_shadow", shadow=True
        )

        tf = result.get("triggering_factors") or {}
        score = result.get("score")
        score_v2 = result.get("score_v2")
        committee_score = score_v2 if score_v2 is not None else (score or 0)
        would_flag_committee = bool(committee_score and committee_score >= COMMITTEE_SCORE_THRESHOLD)

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO crypto_dual_write_shadow
                    (shadow_signal_id, real_signal_id, ticker, direction, signal_type,
                     fired_at, real_score, real_status, shadow_score, shadow_score_v2,
                     shadow_status, l0_shadow_decision, l1_shadow_decision, feed_tier_v1,
                     feed_tier_v2, feed_tier_v2_path, confluence_badge, would_flag_committee,
                     raw_shadow_signal_data)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
                ON CONFLICT (shadow_signal_id) DO NOTHING
                """,
                shadow_signal["signal_id"],
                real_signal_id,
                trade_signal.get("ticker"),
                trade_signal.get("direction"),
                trade_signal.get("signal_type"),
                datetime.now(timezone.utc),
                trade_signal.get("score"),
                trade_signal.get("status"),
                score,
                score_v2,
                result.get("status"),
                _to_jsonable(tf.get("l0_shadow")),
                _to_jsonable(tf.get("l1_shadow")),
                result.get("feed_tier"),
                result.get("feed_tier_v2"),
                result.get("feed_tier_v2_path"),
                result.get("confluence_badge"),
                would_flag_committee,
                _to_jsonable(result),
            )
        logger.debug("Crypto dual-write shadow recorded for %s", real_signal_id)
    except Exception as exc:
        logger.warning("Crypto dual-write shadow failed for %s (non-blocking): %s", real_signal_id, exc)


def _to_jsonable(value):
    """asyncpg needs JSONB params pre-serialized (no type codec registered on
    this pool) -- mirrors postgres_client.py's log_signal/update_signal_with_score
    convention exactly (json.dumps(_sanitize_for_json(value)))."""
    import json
    from database.postgres_client import _sanitize_for_json

    if value is None:
        return None
    try:
        return json.dumps(_sanitize_for_json(value))
    except (TypeError, ValueError):
        return json.dumps(str(value))
