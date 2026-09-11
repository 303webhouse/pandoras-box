#!/usr/bin/env python
"""PHASE B of the R-IV.325(b) provider backfill. Seal-gated. Run AT THE DEPLOY.

    python scripts/backfill_029_provider.py            # dry run, writes NOTHING
    python scripts/backfill_029_provider.py --commit    # takes the seal and writes

WHAT IT DOES
    Sets `provider = 'uw'` on every row that was graded before the fallback
    shipped. That is certainty, not assumption: before the fallback, get_ohlc
    was the only path to a Triton close, so no third possibility existed.

THE DISCIPLINE, and why each step is here rather than remembered
    A  seal BEFORE      count(id <= 377783 AND fired_at >= '2026-08-17') == 843
    -  expected count   DECLARED BEFORE THE WRITE, measured in the same
                        transaction that performs it -- the grader can run
                        between measuring and writing, and a count taken an
                        hour early is a different population
    B  write            the new column ONLY. Not graded_at, not the returns.
                        A backfill that edits a second column is no longer
                        auditable by a count.
    -  rows == expected exact match or ROLLBACK
    C  seal AFTER       the same seal, unchanged
    -  invariant        provider IS NULL <-> graded_at IS NULL, asserted BOTH
                        ways, on the whole table

ANY failure rolls the whole thing back. There is no partial success state:
a half-backfilled column is worse than an empty one, because it looks finished.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

SEAL_MAX_ID = 377783
SEAL_FROM = "2026-08-17"
SEAL_EXPECTED = 843


async def main(commit: bool) -> int:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    if not pool:
        print("FAIL: no database pool")
        return 2

    async with pool.acquire() as conn:
        async with conn.transaction():
            seal_before = await conn.fetchval(
                "SELECT count(*) FROM triton_flow_shadow "
                "WHERE id <= $1 AND fired_at >= $2::date",
                SEAL_MAX_ID, SEAL_FROM,
            )
            print("A  seal BEFORE        : %s (expected %s)" % (seal_before, SEAL_EXPECTED))
            if seal_before != SEAL_EXPECTED:
                print("   HALT — the sealed population moved. Nothing written.")
                raise RuntimeError("seal mismatch before")

            # Declared before the write, inside the same transaction that writes.
            expected = await conn.fetchval(
                "SELECT count(*) FROM triton_flow_shadow "
                "WHERE graded_at IS NOT NULL AND provider IS NULL"
            )
            print("   expected rows      : %s   <- DECLARED BEFORE THE WRITE" % expected)

            already = await conn.fetchval(
                "SELECT count(*) FROM triton_flow_shadow WHERE provider IS NOT NULL"
            )
            print("   already stamped    : %s" % already)

            if not commit:
                print("\nDRY RUN — nothing written. Re-run with --commit at the deploy.")
                raise _DryRun()

            # PHASE B. The new column ONLY.
            status = await conn.execute(
                "UPDATE triton_flow_shadow SET provider = 'uw' "
                "WHERE graded_at IS NOT NULL AND provider IS NULL"
            )
            written = int(status.split()[-1])
            print("B  rows written       : %s" % written)
            if written != expected:
                print("   HALT — written != expected. Rolling back.")
                raise RuntimeError("count mismatch: %s != %s" % (written, expected))

            seal_after = await conn.fetchval(
                "SELECT count(*) FROM triton_flow_shadow "
                "WHERE id <= $1 AND fired_at >= $2::date",
                SEAL_MAX_ID, SEAL_FROM,
            )
            print("C  seal AFTER         : %s (expected %s)" % (seal_after, SEAL_EXPECTED))
            if seal_after != SEAL_EXPECTED:
                print("   HALT — the seal moved across the write. Rolling back.")
                raise RuntimeError("seal mismatch after")

            # The invariant, both directions, on the WHOLE table.
            graded_without = await conn.fetchval(
                "SELECT count(*) FROM triton_flow_shadow "
                "WHERE graded_at IS NOT NULL AND provider IS NULL"
            )
            ungraded_with = await conn.fetchval(
                "SELECT count(*) FROM triton_flow_shadow "
                "WHERE graded_at IS NULL AND provider IS NOT NULL"
            )
            print("   graded w/o provider: %s (must be 0)" % graded_without)
            print("   ungraded w/ provider: %s (must be 0)" % ungraded_with)
            if graded_without or ungraded_with:
                print("   HALT — invariant violated. Rolling back.")
                raise RuntimeError("invariant violated")

            print("\nPASS — provider IS NULL <-> graded_at IS NULL holds. Committed.")
    return 0


class _DryRun(Exception):
    """Aborts the transaction so a dry run cannot write."""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true",
                    help="actually write; without it this is a dry run")
    args = ap.parse_args()
    try:
        raise SystemExit(asyncio.run(main(args.commit)))
    except _DryRun:
        raise SystemExit(0)
