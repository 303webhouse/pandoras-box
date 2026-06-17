r"""L0.1a shadow-measurement — report what the suppression gate WOULD drop.

Read-only. Queries the live `signals` table for rows carrying the L0 shadow
tag (`triggering_factors -> 'l0_shadow'`, written by process_signal_unified)
and reports, over the shadow window:

  1. how many signals were tagged would-suppress, broken down by signal_type;
  2. the full tag distribution (signal_type x rule x would_suppress);
  3. an ASSERTION that ZERO keepers were tagged would-suppress — i.e. every
     would-suppress signal_type is in the expected suppress set. Exits non-zero
     if a keeper leaked into the suppress set (the headline shadow safety check).

Never prints the DB URL. Run from C:\trading-hub (or the L0 worktree):
    python scripts\l0_shadow_measure.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# Expected suppress set — imported from the gate so this script can never drift
# from the live rule table.
from config.l0_routing import SUPPRESS_ALWAYS, SUPPRESS_IF_NON_LIQUID  # noqa: E402

EXPECTED_SUPPRESS = set(SUPPRESS_ALWAYS) | set(SUPPRESS_IF_NON_LIQUID)


def _find_mcp_config() -> str:
    """Locate .mcp.json (gitignored; lives in the main clone root)."""
    candidates = [
        os.path.join(HERE, "..", ".mcp.json"),          # current worktree root
        os.path.join("C:\\", "trading-hub", ".mcp.json"),  # canonical main clone
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise RuntimeError(
        ".mcp.json not found (looked in worktree root + C:\\trading-hub). "
        "Run from a clone that has it."
    )


async def _get_pool():
    """Build an asyncpg pool from .mcp.json (URL not printed)."""
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
            # Window of tagged rows
            window = await conn.fetchrow(
                """
                SELECT COUNT(*) AS tagged,
                       MIN(timestamp) AS first_tagged,
                       MAX(timestamp) AS last_tagged
                FROM signals
                WHERE triggering_factors -> 'l0_shadow' IS NOT NULL
                """
            )
            tagged = window["tagged"] or 0
            print("=" * 64)
            print("L0.1a SHADOW MEASUREMENT")
            print("=" * 64)
            print(f"Tagged signals total : {tagged}")
            print(f"Window               : {window['first_tagged']} -> {window['last_tagged']}")
            print()

            if tagged == 0:
                print("No L0-shadow-tagged signals yet.")
                print("(Gate not deployed, or no NEW signals have flowed since deploy.)")
                return 0

            # Full distribution: signal_type x rule x would_suppress
            dist = await conn.fetch(
                """
                SELECT
                    signal_type,
                    triggering_factors -> 'l0_shadow' ->> 'rule'           AS rule,
                    triggering_factors -> 'l0_shadow' ->> 'would_suppress'  AS would_suppress,
                    COUNT(*)                                               AS n
                FROM signals
                WHERE triggering_factors -> 'l0_shadow' IS NOT NULL
                GROUP BY 1, 2, 3
                ORDER BY would_suppress DESC, n DESC
                """
            )
            print("Tag distribution (signal_type | rule | would_suppress | n):")
            for r in dist:
                print(f"  {r['signal_type']:<22} {r['rule']:<24} "
                      f"{str(r['would_suppress']):<6} {r['n']}")
            print()

            # Would-suppress counts by signal_type
            wsupp = await conn.fetch(
                """
                SELECT signal_type, COUNT(*) AS n
                FROM signals
                WHERE triggering_factors -> 'l0_shadow' ->> 'would_suppress' = 'true'
                GROUP BY signal_type
                ORDER BY n DESC
                """
            )
            print("Would-SUPPRESS by signal_type:")
            total_supp = 0
            flagged_types = set()
            for r in wsupp:
                total_supp += r["n"]
                flagged_types.add(r["signal_type"])
                print(f"  {r['signal_type']:<22} {r['n']}")
            print(f"  {'TOTAL':<22} {total_supp}")
            print()

            # Safety assertion: zero keepers tagged would-suppress
            leaked = sorted(flagged_types - EXPECTED_SUPPRESS)
            print(f"Expected suppress set : {sorted(EXPECTED_SUPPRESS)}")
            if leaked:
                print()
                print("!!! FAIL: KEEPER signal_type(s) tagged would-suppress: "
                      f"{leaked}")
                print("    The gate flagged a signal_type that should be KEPT. "
                      "Investigate before any enforce.")
                return 1

            print()
            print("PASS: every would-suppress signal_type is in the expected "
                  "suppress set (zero keepers tagged).")
            return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
