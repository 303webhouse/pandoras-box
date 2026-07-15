r"""Crypto dual-write diff report — S-1 Phase 4 (F-4.1/F-4.2).

Read-only. Summarizes crypto_dual_write_shadow (migration 024) so Nick can
decide whether to greenlight retiring the bias_scheduler.py "Crypto
Scanner" log_signal bypass in favor of routing through
process_signal_unified for real.

HARD RULE (brief F-4.2): this script does NOT gate or auto-approve
anything. It reports. Cutover requires Nick's WRITTEN greenlight on what
this prints — no automated pass/fail exit code drives that decision (unlike
l0_shadow_measure.py / l1_shadow_measure.py, which do assert a safety
invariant). The brief's own readiness bar (>=48h of 24/7 operation OR n>=30
shadow rows, whichever comes first) is reported so Nick knows whether it's
too early to review yet.

Never prints the DB URL. Run from C:\trading-hub:
    python scripts\crypto_dual_write_diff_report.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

READINESS_HOURS = 48
READINESS_N = 30


def _find_mcp_config() -> str:
    candidates = [
        os.path.join(HERE, "..", ".mcp.json"),
        os.path.join("C:\\", "trading-hub", ".mcp.json"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise RuntimeError(
        ".mcp.json not found (looked in worktree root + C:\\trading-hub). "
        "Run from a clone that has it."
    )


async def _get_pool():
    import asyncpg as _asyncpg
    cfg = json.load(open(_find_mcp_config()))
    args = cfg["mcpServers"]["postgres"]["args"]
    url = next((a for a in reversed(args) if a.startswith("postgres")), None)
    if not url:
        raise RuntimeError("postgres URL not found in .mcp.json")
    return await _asyncpg.create_pool(url, min_size=1, max_size=3)


async def main() -> int:
    pool = await _get_pool()
    try:
        async with pool.acquire() as conn:
            window = await conn.fetchrow(
                """
                SELECT COUNT(*) AS n, MIN(fired_at) AS first_fired, MAX(fired_at) AS last_fired
                FROM crypto_dual_write_shadow
                """
            )
            n = window["n"] or 0
            print("=" * 72)
            print("CRYPTO DUAL-WRITE DIFF REPORT (S-1 F-4)")
            print("=" * 72)
            print(f"Shadow rows total : {n}")
            print(f"Window            : {window['first_fired']} -> {window['last_fired']}")

            if n == 0:
                print()
                print("No shadow rows yet. Nothing to review — the crypto scanner hasn't")
                print("fired since the dual-write deployed, or the toggle is disabled.")
                return 0

            hours_elapsed = None
            if window["first_fired"]:
                first = window["first_fired"]
                if first.tzinfo is None:
                    first = first.replace(tzinfo=timezone.utc)
                hours_elapsed = (datetime.now(timezone.utc) - first).total_seconds() / 3600.0

            ready = (hours_elapsed is not None and hours_elapsed >= READINESS_HOURS) or n >= READINESS_N
            print(f"Hours since first shadow row : {hours_elapsed:.1f}" if hours_elapsed is not None else "Hours since first shadow row : n/a")
            print(f"Readiness bar (brief F-4.1)  : >= {READINESS_HOURS}h OR n >= {READINESS_N} — "
                  f"{'MET' if ready else 'NOT YET MET'}")
            print()
            if not ready:
                print("Too early to review for a cutover decision per the brief's own bar.")
                print("Reporting what's collected so far anyway (informational only).")
                print()

            # Real vs shadow score comparison
            scores = await conn.fetch(
                """
                SELECT shadow_signal_id, ticker, real_score, real_status,
                       shadow_score, shadow_score_v2, shadow_status
                FROM crypto_dual_write_shadow
                ORDER BY fired_at DESC
                """
            )
            print(f"Real vs shadow score/status (all {n} rows):")
            print(f"  {'ticker':<10} {'real_score':>10} {'real_status':<12} {'shadow_score':>12} {'shadow_v2':>10} {'shadow_status':<14}")
            for r in scores:
                print(
                    f"  {r['ticker']:<10} {str(r['real_score']):>10} {str(r['real_status']):<12} "
                    f"{str(r['shadow_score']):>12} {str(r['shadow_score_v2']):>10} {str(r['shadow_status']):<14}"
                )
            print()

            # L0 shadow verdicts
            l0 = await conn.fetch(
                """
                SELECT l0_shadow_decision ->> 'would_suppress' AS would_suppress, COUNT(*) AS n
                FROM crypto_dual_write_shadow
                WHERE l0_shadow_decision IS NOT NULL
                GROUP BY 1
                """
            )
            print("L0 shadow gate — would_suppress distribution:")
            if not l0:
                print("  (no L0 shadow decisions recorded — evaluate_l0_gate may not apply to these signal_types)")
            for r in l0:
                print(f"  would_suppress={r['would_suppress']:<6} n={r['n']}")
            print()

            # Feed tier v1 vs v2 divergence
            tiers = await conn.fetch(
                """
                SELECT feed_tier_v1, feed_tier_v2, COUNT(*) AS n
                FROM crypto_dual_write_shadow
                GROUP BY 1, 2
                ORDER BY n DESC
                """
            )
            print("Feed tier v1 vs v2 (what the real chokepoint would classify):")
            for r in tiers:
                print(f"  v1={str(r['feed_tier_v1']):<14} v2={str(r['feed_tier_v2']):<14} n={r['n']}")
            print()

            # Would-flag-committee count
            committee = await conn.fetchval(
                "SELECT COUNT(*) FROM crypto_dual_write_shadow WHERE would_flag_committee = true"
            )
            print(f"Would have flagged for committee review: {committee}/{n}")
            print()

            print("-" * 72)
            print("This script does not gate anything. Cutover (retiring the log_signal")
            print("bypass) requires Nick's WRITTEN greenlight on this report — see brief")
            print("F-4.2. No greenlight, no cutover; the dual-write may outlive the brief.")
            print("-" * 72)
            return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
