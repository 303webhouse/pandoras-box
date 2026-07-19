r"""L1a shadow-window measurement — review the auction+flow gate's shadow decisions.

Read-only. Queries the live `signals` table for rows carrying the L1a shadow tag
(`triggering_factors -> 'l1_shadow'`, written by process_signal_unified step-3e)
and reports, over the shadow window:

  1. gate decision distribution (pass / asterisk / flow_unavailable / fail /
     out_of_scope), overall + by ticker + direction;
  2. flow-half state distribution (fresh / missing) + flow-confirm vs unavailable;
  3. auction-half state distribution (fresh_accepted / asterisk / closed / feed_down);
  4. cross-check gate decision vs resolved outcome_pnl_pct (where available);
  5. bypass-leak fraction (triggering_factors -> 'bypass_source') — signals that
     skipped the chokepoint entirely.

Shadow only — the gate diverts nothing. Never prints the DB URL.
Run from C:\trading-hub:  python scripts\l1_shadow_measure.py
Optional window override:  python scripts\l1_shadow_measure.py 2026-06-22
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _find_mcp_config() -> str:
    for path in (os.path.join(HERE, "..", ".mcp.json"),
                 os.path.join("C:\\", "trading-hub", ".mcp.json")):
        if os.path.exists(path):
            return path
    raise RuntimeError(".mcp.json not found (run from a clone that has it).")


async def _get_pool():
    import asyncpg as _asyncpg
    cfg = json.load(open(_find_mcp_config()))
    args = cfg["mcpServers"]["postgres"]["args"]
    url = next((a for a in reversed(args) if a.startswith("postgres")), None)
    if not url:
        raise RuntimeError("postgres URL not found in .mcp.json")
    return await _asyncpg.create_pool(url, min_size=1, max_size=3)


async def main() -> int:
    since = sys.argv[1] if len(sys.argv) > 1 else "2026-06-22"  # shadow went live 2026-06-22
    pool = await _get_pool()
    try:
        async with pool.acquire() as conn:
            window = await conn.fetchrow(
                """
                SELECT COUNT(*) AS tagged, MIN(timestamp) AS first, MAX(timestamp) AS last
                FROM signals
                WHERE triggering_factors -> 'l1_shadow' IS NOT NULL
                  AND timestamp >= $1::text::date
                """,
                since,
            )
            tagged = window["tagged"] or 0
            print("=" * 66)
            print(f"L1a SHADOW WINDOW MEASUREMENT  (since {since})")
            print("=" * 66)
            print(f"Tagged signals : {tagged}")
            print(f"Window         : {window['first']} -> {window['last']}")
            print()
            if tagged == 0:
                print("No L1a-shadow-tagged signals in window.")
                print("(L1_GATE_SHADOW off, or no signals through the chokepoint since deploy.)")
                return 0

            async def dist(expr, label):
                rows = await conn.fetch(
                    f"""SELECT {expr} AS k, COUNT(*) AS n FROM signals
                        WHERE triggering_factors -> 'l1_shadow' IS NOT NULL
                          AND timestamp >= $1::text::date GROUP BY 1 ORDER BY n DESC""",
                    since,
                )
                print(f"{label}:")
                for r in rows:
                    print(f"  {str(r['k']):<28} {r['n']}")
                print()

            await dist("triggering_factors -> 'l1_shadow' ->> 'gate'", "Gate decision")
            await dist("triggering_factors -> 'l1_shadow' -> 'flow' ->> 'state'", "Flow state")
            await dist("triggering_factors -> 'l1_shadow' -> 'auction' ->> 'state'", "Auction state")

            # By ticker x direction x gate
            byt = await conn.fetch(
                """SELECT ticker, direction,
                          triggering_factors -> 'l1_shadow' ->> 'gate' AS gate, COUNT(*) AS n
                   FROM signals
                   WHERE triggering_factors -> 'l1_shadow' IS NOT NULL AND timestamp >= $1::text::date
                   GROUP BY 1,2,3 ORDER BY ticker, n DESC""",
                since,
            )
            print("By ticker | direction | gate | n:")
            for r in byt:
                print(f"  {r['ticker']:<6} {str(r['direction']):<6} {str(r['gate']):<16} {r['n']}")
            print()

            # Gate vs resolved outcome
            outc = await conn.fetch(
                """SELECT triggering_factors -> 'l1_shadow' ->> 'gate' AS gate,
                          COUNT(outcome_pnl_pct) AS resolved,
                          ROUND(AVG(outcome_pnl_pct)::numeric, 3) AS avg_pnl
                   FROM signals
                   WHERE triggering_factors -> 'l1_shadow' IS NOT NULL AND timestamp >= $1::text::date
                   GROUP BY 1 ORDER BY avg_pnl DESC NULLS LAST""",
                since,
            )
            print("Gate vs outcome (resolved only) — the edge check:")
            for r in outc:
                print(f"  {str(r['gate']):<16} resolved={r['resolved']:<5} avg_pnl={r['avg_pnl']}")
            print()

            # Bypass-leak fraction (signals that skipped the chokepoint)
            byp = await conn.fetch(
                """SELECT triggering_factors ->> 'bypass_source' AS src, COUNT(*) AS n
                   FROM signals
                   WHERE triggering_factors ->> 'bypass_source' IS NOT NULL AND timestamp >= $1::text::date
                   GROUP BY 1 ORDER BY n DESC""",
                since,
            )
            print("Bypass-leak (skipped the chokepoint, gate never saw them):")
            if not byp:
                print("  (none tagged in window)")
            for r in byp:
                print(f"  {str(r['src']):<32} {r['n']}")
            print()
            print("Reminder — enforce is still gated on: sb3 ADX-regime promote "
                  "(regime-conditioning) + full Olympus committee pass + Nick's greenlight.")
            return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
