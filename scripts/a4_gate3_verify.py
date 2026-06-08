"""
Gate 3 verification - A4 committee_passes write shape + IS-NULL guard.

A real committee pass is VPS/Claude.ai-driven and cannot be triggered locally,
so this validates the new handler SQL against prod inside a transaction that is
ROLLED BACK - nothing persists. Proves:
  1. committee_passes INSERT shape works (JSONB agent_reads, NUMERIC levels, NULL spot)
  2. IS-NULL guard sets COMMITTEE_REVIEW on a NULL-outcome_source signal
  3. IS-NULL guard does NOT touch an already-set BAR_WALK signal
  4. After rollback, outcome_source distribution is unchanged

Run from C:\trading-hub:
    python scripts\a4_gate3_verify.py
"""

from __future__ import annotations

import asyncio
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

NULL_SIGNAL = "NEAR-USD_LONG_20260507_093426"   # outcome_source IS NULL
BARWALK_SIGNAL = "HG_ITW_20260521_153750_both"  # outcome_source = BAR_WALK (guard must protect)


async def _get_conn():
    import asyncpg
    cfg = json.load(open(os.path.join(HERE, "..", ".mcp.json")))
    args = cfg["mcpServers"]["postgres"]["args"]
    url = next((a for a in reversed(args) if a.startswith("postgres")), None)
    return await asyncpg.connect(url)


async def main() -> None:
    conn = await _get_conn()
    try:
        # Pre-distribution
        pre = await conn.fetch(
            "SELECT outcome_source, COUNT(*) AS n FROM signals "
            "WHERE outcome_source IS NOT NULL GROUP BY outcome_source ORDER BY n DESC"
        )
        print("--- pre outcome_source distribution ---")
        for r in pre:
            print(f"  {r['outcome_source']}: {r['n']}")
        pre_cp_count = await conn.fetchval("SELECT COUNT(*) FROM committee_passes")
        print(f"  committee_passes rows: {pre_cp_count}")
        print()

        # Fetch ticker for the NULL signal (mirror handler's SELECT)
        cur = await conn.fetchrow(
            "SELECT status, ticker FROM signals WHERE signal_id = $1", NULL_SIGNAL
        )
        print(f"Test signal {NULL_SIGNAL}: ticker={cur['ticker']}")
        print()

        tr = conn.transaction()
        await tr.start()
        try:
            # 1. INSERT committee_passes - exact handler shape
            agent_reads = {"toro": "bull thesis text", "ursa": "bear thesis text"}
            risk = {"entry": 5.12, "stop": 4.90, "target": 5.80, "invalidation": 4.85}

            def _num(v):
                try:
                    return float(v) if v is not None else None
                except (TypeError, ValueError):
                    return None

            await conn.execute(
                """
                INSERT INTO committee_passes
                    (ticker, pass_ts, spot, agent_reads, pivot_synthesis,
                     conviction, entry, stop, target, invalidation, signal_id)
                VALUES ($1, NOW(), NULL, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                cur["ticker"],
                json.dumps(agent_reads),
                "PIVOT: TAKE - synthesis text",
                "HIGH",
                _num(risk.get("entry")),
                _num(risk.get("stop")),
                _num(risk.get("target")),
                _num(risk.get("invalidation")),
                NULL_SIGNAL,
            )

            # 2. IS-NULL guard on NULL signal -> should set COMMITTEE_REVIEW
            await conn.execute(
                "UPDATE signals SET outcome_source = 'COMMITTEE_REVIEW' "
                "WHERE signal_id = $1 AND outcome_source IS NULL",
                NULL_SIGNAL,
            )

            # 3. IS-NULL guard on BAR_WALK signal -> should be a no-op
            await conn.execute(
                "UPDATE signals SET outcome_source = 'COMMITTEE_REVIEW' "
                "WHERE signal_id = $1 AND outcome_source IS NULL",
                BARWALK_SIGNAL,
            )

            # Verify inside transaction
            cp_row = await conn.fetchrow(
                "SELECT ticker, spot, agent_reads, conviction, entry, stop, target, "
                "invalidation, signal_id FROM committee_passes WHERE signal_id = $1",
                NULL_SIGNAL,
            )
            null_after = await conn.fetchval(
                "SELECT outcome_source FROM signals WHERE signal_id = $1", NULL_SIGNAL
            )
            barwalk_after = await conn.fetchval(
                "SELECT outcome_source FROM signals WHERE signal_id = $1", BARWALK_SIGNAL
            )

            print("--- in-transaction verification ---")
            print(f"committee_passes row written:")
            print(f"  ticker={cp_row['ticker']}  spot={cp_row['spot']}  conviction={cp_row['conviction']}")
            print(f"  entry={cp_row['entry']} stop={cp_row['stop']} target={cp_row['target']} invalidation={cp_row['invalidation']}")
            print(f"  agent_reads={cp_row['agent_reads']}")
            print(f"  signal_id={cp_row['signal_id']}")
            print()
            print(f"NULL signal    -> outcome_source = {null_after!r}  (expect COMMITTEE_REVIEW)")
            print(f"BAR_WALK signal -> outcome_source = {barwalk_after!r}  (expect BAR_WALK - guard protects)")
            print()

            assert cp_row is not None, "committee_passes row not written"
            assert null_after == "COMMITTEE_REVIEW", f"NULL signal not labeled: {null_after}"
            assert barwalk_after == "BAR_WALK", f"GUARD FAILED - BAR_WALK overwritten: {barwalk_after}"
            print("ALL ASSERTIONS PASS")
        finally:
            await tr.rollback()
            print("\nTransaction ROLLED BACK - nothing persisted.")

        # Post-distribution (must equal pre)
        post = await conn.fetch(
            "SELECT outcome_source, COUNT(*) AS n FROM signals "
            "WHERE outcome_source IS NOT NULL GROUP BY outcome_source ORDER BY n DESC"
        )
        post_cp_count = await conn.fetchval("SELECT COUNT(*) FROM committee_passes")
        print("\n--- post outcome_source distribution (must equal pre) ---")
        for r in post:
            print(f"  {r['outcome_source']}: {r['n']}")
        print(f"  committee_passes rows: {post_cp_count}")

        pre_map = {r["outcome_source"]: r["n"] for r in pre}
        post_map = {r["outcome_source"]: r["n"] for r in post}
        print()
        print(f"ACTUAL_TRADE unchanged: {pre_map.get('ACTUAL_TRADE') == post_map.get('ACTUAL_TRADE')} ({pre_map.get('ACTUAL_TRADE')})")
        print(f"BAR_WALK unchanged:     {pre_map.get('BAR_WALK') == post_map.get('BAR_WALK')} ({pre_map.get('BAR_WALK')})")
        print(f"committee_passes unchanged: {pre_cp_count == post_cp_count} ({pre_cp_count})")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
