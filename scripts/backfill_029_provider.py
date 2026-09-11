#!/usr/bin/env python
"""PHASE B of the R-IV.325(b) provider backfill. Seal-gated. Run AT THE DEPLOY.

    python scripts/backfill_029_provider.py            # dry run, writes NOTHING
    python scripts/backfill_029_provider.py --commit    # takes the seal and writes

WHAT IT DOES
    Sets `provider = 'uw'` on every row graded before the fallback shipped. That
    is certainty, not assumption: before the fallback, get_ohlc was the only path
    to a Triton close, so no third possibility existed.

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

ONE transaction. Any failure rolls the whole thing back: there is no partial
success state, because a half-backfilled column is worse than an empty one --
it looks finished.
"""
from __future__ import annotations

import argparse
import json
import os

import psycopg2
import psycopg2.extras

SEAL_MAX_ID = 377783
SEAL_FROM = "2026-08-17"
SEAL_EXPECTED = 843
MCP_CONFIG = r"C:\trading-hub\.mcp.json"


def dsn() -> str:
    """Backend env vars when running IN the container; the operator's configured
    connection otherwise. Same database either way -- the phases below are what
    make this safe, not where it is run from."""
    host = os.getenv("DB_HOST") or ""
    if host:
        return "postgresql://%s:%s@%s:%s/%s" % (
            os.getenv("DB_USER") or "postgres",
            os.getenv("DB_PASSWORD") or "",
            host,
            os.getenv("DB_PORT") or "5432",
            os.getenv("DB_NAME") or "railway",
        )
    cfg = json.load(open(MCP_CONFIG))
    for a in cfg["mcpServers"]["postgres"]["args"]:
        if isinstance(a, str) and a.startswith("postgres"):
            return a
    raise SystemExit("no connection available")


def main(commit: bool) -> int:
    conn = psycopg2.connect(dsn())
    conn.autocommit = False          # ONE transaction; any HALT rolls it all back
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT count(*) n FROM triton_flow_shadow "
            "WHERE id <= %s AND fired_at >= %s::date", (SEAL_MAX_ID, SEAL_FROM))
        seal_before = cur.fetchone()["n"]
        print("A  seal BEFORE         : %s (expected %s)" % (seal_before, SEAL_EXPECTED))
        if seal_before != SEAL_EXPECTED:
            raise RuntimeError("seal mismatch before")

        cur.execute("SELECT count(*) n FROM triton_flow_shadow "
                    "WHERE graded_at IS NOT NULL AND provider IS NULL")
        expected = cur.fetchone()["n"]
        print("   expected rows       : %s   <- DECLARED BEFORE THE WRITE" % expected)
        cur.execute("SELECT count(*) n FROM triton_flow_shadow WHERE provider IS NOT NULL")
        print("   already stamped     : %s" % cur.fetchone()["n"])

        if not commit:
            conn.rollback()
            print()
            print("DRY RUN - nothing written. Re-run with --commit.")
            return 0

        cur.execute("UPDATE triton_flow_shadow SET provider = 'uw' "
                    "WHERE graded_at IS NOT NULL AND provider IS NULL")
        written = cur.rowcount
        print("B  rows written        : %s" % written)
        if written != expected:
            raise RuntimeError("count mismatch: %s != %s" % (written, expected))

        cur.execute(
            "SELECT count(*) n FROM triton_flow_shadow "
            "WHERE id <= %s AND fired_at >= %s::date", (SEAL_MAX_ID, SEAL_FROM))
        seal_after = cur.fetchone()["n"]
        print("C  seal AFTER          : %s (expected %s)" % (seal_after, SEAL_EXPECTED))
        if seal_after != SEAL_EXPECTED:
            raise RuntimeError("seal moved across the write")

        cur.execute("SELECT count(*) n FROM triton_flow_shadow "
                    "WHERE graded_at IS NOT NULL AND provider IS NULL")
        graded_without = cur.fetchone()["n"]
        cur.execute("SELECT count(*) n FROM triton_flow_shadow "
                    "WHERE graded_at IS NULL AND provider IS NOT NULL")
        ungraded_with = cur.fetchone()["n"]
        print("   graded w/o provider : %s (must be 0)" % graded_without)
        print("   ungraded w/ provider: %s (must be 0)" % ungraded_with)
        if graded_without or ungraded_with:
            raise RuntimeError("invariant violated")

        conn.commit()
        print()
        print("PASS - provider IS NULL <-> graded_at IS NULL holds. COMMITTED.")
        return 0
    except Exception as exc:
        conn.rollback()
        print()
        print("HALT - %s. Rolled back; nothing written." % exc)
        return 1
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true",
                    help="actually write; without it this is a dry run")
    raise SystemExit(main(ap.parse_args().commit))
