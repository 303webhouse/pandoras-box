"""Stater Swap v2 S-1 Phase 4 (F-4) — crypto L0 routing dual-write, INVERTED.

Original shape (through 2026-07-14): `bias_scheduler.py`'s "Crypto Scanner"
(`run_crypto_scan_scheduled`) wrote via `log_signal` directly (the real,
bypass path) while this module ran the same signal through
`process_signal_unified(shadow=True)` on a copy, purely for comparison.

CUTOVER (2026-07-15, Fable-directed "inverted shadow" ruling): roles
swapped. `process_signal_unified` (no `shadow=True`) is now the PRIMARY
writer — persistence, Discord, WebSocket, committee flagging, and
cross-strategy conflict-dismissal all run for real, same as every other
signal source. The original ad hoc scorer is demoted to a shadow-logger:
`log_bypass_shadow_comparison()` records what that old scoring path would
have produced, for comparison only, into the SAME `crypto_dual_write_shadow`
table (migration 024, reused — no schema change). It never persists to the
real `signals` table and never triggers Discord/WebSocket/committee.

Retirement bar (per Fable's ruling): the diff report
(`scripts/crypto_dual_write_diff_report.py`) keeps running until n>=30 REAL
(unified-path) signals accumulate, at which point the bypass shadow-logger
retires entirely — no more ad hoc scoring, no more comparison rows. See
docs/strategy-reviews/stater-swap-redesign/s1-phase4-findings.md for the
full cutover record and the pre-deploy fan-out/Discord behavior review.

Hot-reload: the shadow-logger can be disabled without a redeploy via the
Redis flag below, mirroring `uw_budget_watchdog.py`'s `quota_shed:triton`
pattern (a proven no-redeploy-needed runtime toggle; `system_config` in
Postgres is unused/aspirational schema, not a working pattern — see Phase 4
investigation notes in the findings doc).
"""

from __future__ import annotations

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


async def log_bypass_shadow_comparison(
    unified_result: dict,
    bypass_score: float,
    bypass_bias_alignment: str,
    bypass_triggering_factors: dict,
) -> None:
    """Record the demoted bypass scorer's output for comparison against the
    now-REAL unified-pipeline result already persisted by the caller.

    `unified_result` is the dict returned by `process_signal_unified()` for
    the REAL, already-committed signal (persistence/Discord/broadcast/
    committee-flagging all already happened before this is called). This
    function only INSERTs a comparison row — it never touches the real
    `signals` table and never triggers any further side effect. Swallows
    all errors, same as the pre-cutover version: a shadow-logger failure
    must never affect the real signal path that already completed.
    """
    if not await is_dual_write_enabled():
        return

    real_signal_id = unified_result.get("signal_id")
    if not real_signal_id:
        return

    try:
        from database.postgres_client import get_postgres_client

        shadow_signal_id = f"BYPASS_{real_signal_id}"
        tf = unified_result.get("triggering_factors") or {}
        real_score = unified_result.get("score_v2")
        if real_score is None:
            real_score = unified_result.get("score")
        committee_score = real_score or 0
        would_flag_committee = bool(
            unified_result.get("status") == "COMMITTEE_REVIEW"
            or (committee_score and committee_score >= COMMITTEE_SCORE_THRESHOLD)
        )

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
                shadow_signal_id,
                real_signal_id,
                unified_result.get("ticker"),
                unified_result.get("direction"),
                unified_result.get("signal_type"),
                datetime.now(timezone.utc),
                real_score,
                unified_result.get("status"),
                bypass_score,
                None,
                "ACTIVE",  # the bypass scorer never gated status
                _to_jsonable(tf.get("l0_shadow")),
                _to_jsonable(tf.get("l1_shadow")),
                unified_result.get("feed_tier"),
                unified_result.get("feed_tier_v2"),
                unified_result.get("feed_tier_v2_path"),
                unified_result.get("confluence_badge"),
                would_flag_committee,
                _to_jsonable({
                    "bypass_score": bypass_score,
                    "bypass_bias_alignment": bypass_bias_alignment,
                    "bypass_triggering_factors": bypass_triggering_factors,
                }),
            )
        logger.debug("Bypass shadow comparison recorded for %s", real_signal_id)
    except Exception as exc:
        logger.warning("Bypass shadow-logger failed for %s (non-blocking): %s", real_signal_id, exc)


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
