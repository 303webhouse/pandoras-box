#!/usr/bin/env python3
"""backfill_suppression.py — generic L0 eviction-runbook backfill (reusable).

When a strategy is evicted/decomposed AFTER rows were already scored, those
historical rows carry a stale l0_shadow tag (would_suppress=false) or no tag at
all, so L0.1a ENFORCE — which keys on the recorded tag by design — leaks them
into actionable feeds. This flips them to would_suppress=true WITH provenance,
never faking a shadow/enforce evaluation that did not happen.

Two disjoint, idempotent populations (WHERE excludes already-true rows):
  P1: l0_shadow tag exists, would_suppress=false -> preserve the original value
      inside l0_shadow.backfill.original_would_suppress, then flip.
  P2: no l0_shadow object at all -> build a fresh tag whose mode is honestly
      'backfill' (original recorded as null).

Dry-run is the DEFAULT. --execute wraps BOTH updates in ONE transaction, gated:
  A5 (phase gate): --execute is refused unless the operator has reviewed the
      dry-run counts and passes --i-have-go. Human GO is external (coordination
      lane / Nick), pre-authorized only when counts match the expectation.
  A1 (rollback): a pre-image of every affected row (signal_id + old l0_shadow)
      is written to C:\\temp\\backfill_preimage_<TYPE>_<ts>.jsonl BEFORE any write.
  A6 (invariance): asserts total row-count of signal_type is identical pre/post
      (proves tag-only mutation, zero row drops).
  A7: rule_ref is passed as a bound $n parameter — never string-interpolated.

Known accepted limitation: rows whose signal_type drifted AWAY from the target
type after gate eval are out of scope of a type-keyed backfill.

Usage:
  python scripts/backfill_suppression.py --signal-type ARTEMIS_LONG \\
      --rule-ref "cta-artemis-decompose 2026-06-16 / eviction 2026-07-10"
  # add --execute --i-have-go to apply (only after the dry-run counts are GO'd)
"""
import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def _load_db_env():
    """Local convenience: hydrate DB_* from .mcp.json when not already set.
    No-op on Railway/VPS (DB_* present, .mcp.json absent)."""
    if os.getenv("DB_HOST"):
        return
    mcp = Path(__file__).resolve().parent.parent / ".mcp.json"
    if mcp.exists():
        from urllib.parse import urlparse
        m = re.search(r'postgres(?:ql)?://[^"\\ ]+', mcp.read_text(encoding="utf-8"))
        if m:
            u = urlparse(m.group(0))
            os.environ.update(
                DB_HOST=u.hostname or "localhost",
                DB_PORT=str(u.port or 5432),
                DB_NAME=(u.path or "/").lstrip("/") or "railway",
                DB_USER=u.username or "postgres",
                DB_PASSWORD=u.password or "",
            )


_load_db_env()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from database.postgres_client import get_postgres_client  # noqa: E402

TOTAL_SQL = "SELECT COUNT(*) FROM signals WHERE signal_type=$1"

P1_COND = ("triggering_factors->'l0_shadow' IS NOT NULL "
           "AND COALESCE((triggering_factors->'l0_shadow'->>'would_suppress')::boolean,false)=false")
P2_COND = "(triggering_factors IS NULL OR triggering_factors->'l0_shadow' IS NULL)"

P1_COUNT = f"SELECT COUNT(*) FROM signals WHERE signal_type=$1 AND {P1_COND}"
P2_COUNT = f"SELECT COUNT(*) FROM signals WHERE signal_type=$1 AND {P2_COND}"

P1_UPDATE = f"""
UPDATE signals
SET triggering_factors =
    jsonb_set(
      jsonb_set(triggering_factors, '{{l0_shadow,backfill}}',
        jsonb_build_object('original_would_suppress',
                           triggering_factors->'l0_shadow'->'would_suppress',
                           'rule_ref', $2::text, 'applied_at', now()::text), true),
      '{{l0_shadow,would_suppress}}', 'true'::jsonb)
WHERE signal_type=$1 AND {P1_COND}"""

P2_UPDATE = f"""
UPDATE signals
SET triggering_factors = jsonb_set(
      COALESCE(triggering_factors, '{{}}'::jsonb), '{{l0_shadow}}',
      jsonb_build_object('v', 1, 'mode', 'backfill', 'signal_type', $1::text,
        'rule', 'SUPPRESS', 'would_suppress', true, 'is_liquid', null,
        'reason', 'backfilled — '||$1::text||' eviction postdates row',
        'backfill', jsonb_build_object('original_would_suppress', null,
                     'rule_ref', $2::text, 'applied_at', now()::text)), true)
WHERE signal_type=$1 AND {P2_COND}"""

ASSERT_SQL = (f"SELECT COUNT(*) FROM signals WHERE signal_type=$1 "
              f"AND COALESCE((triggering_factors->'l0_shadow'->>'would_suppress')::boolean,false)=false")

AFFECTED_SQL = (f"SELECT signal_id, triggering_factors->'l0_shadow' AS l0 "
                f"FROM signals WHERE signal_type=$1 AND ({P1_COND} OR {P2_COND})")


async def main():
    ap = argparse.ArgumentParser(description="L0 eviction-runbook suppression backfill")
    ap.add_argument("--signal-type", required=True)
    ap.add_argument("--rule-ref", required=True)
    ap.add_argument("--execute", action="store_true", help="apply (default is dry-run)")
    ap.add_argument("--i-have-go", action="store_true",
                    help="A5 phase-gate acknowledgement; required alongside --execute")
    args = ap.parse_args()
    st, rr = args.signal_type, args.rule_ref

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        total_before = await conn.fetchval(TOTAL_SQL, st)
        p1 = await conn.fetchval(P1_COUNT, st)
        p2 = await conn.fetchval(P2_COUNT, st)

        print(f"=== backfill_suppression {'EXECUTE' if args.execute else 'DRY-RUN'} — {st} ===")
        print(f"rule_ref            : {rr}")
        print(f"total {st} rows : {total_before}")
        print(f"P1 (tag, ws=false)  : {p1}")
        print(f"P2 (no l0_shadow)   : {p2}")
        print(f"TOTAL to flip       : {p1 + p2}")

        # 3 sample rows rendered before -> after, for each population
        print("\n--- P1 samples (tag exists, would_suppress=false) ---")
        for r in await conn.fetch(
                f"SELECT signal_id, triggering_factors->'l0_shadow' AS l0 "
                f"FROM signals WHERE signal_type=$1 AND {P1_COND} LIMIT 3", st):
            before = json.loads(r["l0"]) if r["l0"] else None
            print(f"  {r['signal_id']}")
            print(f"    before: would_suppress={before.get('would_suppress') if before else None}")
            print(f"    after : would_suppress=true, "
                  f"backfill.original_would_suppress={before.get('would_suppress') if before else None}, "
                  f"rule_ref set")
        print("\n--- P2 samples (no l0_shadow object) ---")
        for r in await conn.fetch(
                f"SELECT signal_id, triggering_factors->'l0_shadow' AS l0 "
                f"FROM signals WHERE signal_type=$1 AND {P2_COND} LIMIT 3", st):
            print(f"  {r['signal_id']}")
            print(f"    before: l0_shadow=None")
            print(f"    after : mode='backfill', would_suppress=true, "
                  f"backfill.original_would_suppress=null, rule_ref set")

        if not args.execute:
            print("\nDRY-RUN only — nothing written. Re-run with "
                  "--execute --i-have-go after the counts are GO'd (A5).")
            return

        if not args.i_have_go:
            print("\nA5 REFUSED: --execute requires --i-have-go (phase-gate "
                  "acknowledgement). Post the dry-run counts, get GO, then re-run.")
            return

        # A1 — pre-image export BEFORE any write
        affected = await conn.fetch(AFFECTED_SQL, st)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        pre_path = Path(r"C:\temp") / f"backfill_preimage_{st}_{ts}.jsonl"
        pre_path.parent.mkdir(parents=True, exist_ok=True)
        with pre_path.open("w", encoding="utf-8") as f:
            for r in affected:
                f.write(json.dumps({
                    "signal_id": r["signal_id"],
                    "l0_shadow": json.loads(r["l0"]) if r["l0"] else None,
                }) + "\n")
        print(f"\nA1 pre-image: {len(affected)} rows -> {pre_path}")

        # both updates in ONE transaction
        async with conn.transaction():
            n1 = await conn.execute(P1_UPDATE, st, rr)
            n2 = await conn.execute(P2_UPDATE, st, rr)
        print(f"P1 update: {n1} | P2 update: {n2}")

        # A6 invariance + post-run assertion
        total_after = await conn.fetchval(TOTAL_SQL, st)
        remaining = await conn.fetchval(ASSERT_SQL, st)
        print(f"A6 row-count invariance: before={total_before} after={total_after} -> "
              f"{'OK' if total_before == total_after else 'FAIL — INVESTIGATE'}")
        print(f"post-run assertion (must be 0): {remaining} -> "
              f"{'OK' if remaining == 0 else 'FAIL — INVESTIGATE'}")


if __name__ == "__main__":
    asyncio.run(main())
