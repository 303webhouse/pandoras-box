#!/usr/bin/env python
"""T5b PHASE B — classification backfill. Seal-gated. (R-IV.360(2))

    python scripts/backfill_030_class.py            # dry run, writes NOTHING
    python scripts/backfill_030_class.py --commit    # takes the seal and writes

WHAT IT WRITES
    `instrument_class` for every row, from `instrument_class.classify()`.

    issue_type is passed as None, and that is not a shortcut. The cash-settled
    branch is checked FIRST and does not consult issue_type, so the ONE class the
    grader acts on is determined exactly. Every other ticker yields `unmapped` —
    the classifier's own word for "not determinable from what we have" — because
    resolving them needs a per-ticker vendor call this backfill deliberately does
    not make. UNKNOWN IS NEVER GUESSED (instrument_class.py's own rule).

THE EXPECTED COUNTS, DECLARED BEFORE THE WRITE
    total classified      == rows in the table
    cash_settled_index    == rows whose ticker is in CASH_SETTLED_INDEX_SYMBOLS
    ...of those, in seal  == 15     <- the brief's gate, R-IV.287(1)

    A stated non-zero count that is MET, not merely non-empty. "Some rows were
    classified" passes trivially and proves nothing.

THE SEAL, before and after
    count(id <= 377783 AND fired_at >= '2026-08-17') == 843

ONE transaction. Any mismatch rolls everything back.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from jobs.instrument_class import (                       # noqa: E402
    CASH_SETTLED_INDEX_SYMBOLS, CLASS_CASH_SETTLED_INDEX, classify,
)

SEAL_MAX_ID = 377783
SEAL_FROM = "2026-08-17"
SEAL_EXPECTED = 843
SEAL_CLASS_EXPECTED = 15
MCP_CONFIG = r"C:\trading-hub\.mcp.json"


def dsn() -> str:
    host = os.getenv("DB_HOST") or ""
    if host:
        return "postgresql://%s:%s@%s:%s/%s" % (
            os.getenv("DB_USER") or "postgres", os.getenv("DB_PASSWORD") or "",
            host, os.getenv("DB_PORT") or "5432", os.getenv("DB_NAME") or "railway")
    cfg = json.load(open(MCP_CONFIG))
    for a in cfg["mcpServers"]["postgres"]["args"]:
        if isinstance(a, str) and a.startswith("postgres"):
            return a
    raise SystemExit("no connection available")


def seal(cur) -> int:
    cur.execute("SELECT count(*) n FROM triton_flow_shadow "
                "WHERE id <= %s AND fired_at >= %s::date", (SEAL_MAX_ID, SEAL_FROM))
    return cur.fetchone()["n"]


def main(commit: bool) -> int:
    conn = psycopg2.connect(dsn())
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        s_before = seal(cur)
        print("A  seal BEFORE          : %s (expected %s)" % (s_before, SEAL_EXPECTED))
        if s_before != SEAL_EXPECTED:
            raise RuntimeError("seal mismatch before")

        cur.execute("SELECT count(*) n FROM triton_flow_shadow")
        total = cur.fetchone()["n"]
        idx_syms = sorted(CASH_SETTLED_INDEX_SYMBOLS)
        cur.execute("SELECT count(*) n FROM triton_flow_shadow "
                    "WHERE upper(ticker) = ANY(%s)", (idx_syms,))
        exp_index = cur.fetchone()["n"]
        cur.execute("SELECT count(*) n FROM triton_flow_shadow "
                    "WHERE id <= %s AND fired_at >= %s::date AND upper(ticker) = ANY(%s)",
                    (SEAL_MAX_ID, SEAL_FROM, idx_syms))
        exp_seal_index = cur.fetchone()["n"]

        print("   EXPECTED, declared before the write:")
        print("     rows to classify     : %s" % total)
        print("     cash_settled_index   : %s" % exp_index)
        print("     ...inside the seal   : %s (gate expects %s)" % (exp_seal_index, SEAL_CLASS_EXPECTED))
        if exp_seal_index != SEAL_CLASS_EXPECTED:
            raise RuntimeError("seal-class gate: %s != %s — HALT, not a note"
                               % (exp_seal_index, SEAL_CLASS_EXPECTED))

        if not commit:
            conn.rollback()
            print()
            print("DRY RUN - nothing written. Re-run with --commit.")
            return 0

        # Classify in Python so the STORED value is literally classify()'s output,
        # not a SQL re-implementation of it that could drift from the module.
        cur.execute("SELECT DISTINCT ticker FROM triton_flow_shadow")
        tickers = [r["ticker"] for r in cur.fetchall()]
        by_class: dict[str, list] = {}
        for tk in tickers:
            by_class.setdefault(classify(tk, None), []).append(tk)

        written = 0
        for cls, syms in sorted(by_class.items()):
            cur.execute("UPDATE triton_flow_shadow SET instrument_class = %s "
                        "WHERE ticker = ANY(%s)", (cls, syms))
            print("B  %-22s %5s rows  (%s tickers)" % (cls, cur.rowcount, len(syms)))
            written += cur.rowcount

        print("   total written        : %s (expected %s)" % (written, total))
        if written != total:
            raise RuntimeError("count mismatch: %s != %s" % (written, total))

        cur.execute("SELECT count(*) n FROM triton_flow_shadow WHERE instrument_class = %s",
                    (CLASS_CASH_SETTLED_INDEX,))
        got_index = cur.fetchone()["n"]
        cur.execute("SELECT count(*) n FROM triton_flow_shadow "
                    "WHERE id <= %s AND fired_at >= %s::date AND instrument_class = %s",
                    (SEAL_MAX_ID, SEAL_FROM, CLASS_CASH_SETTLED_INDEX))
        got_seal_index = cur.fetchone()["n"]
        print("   cash_settled_index   : %s (expected %s)" % (got_index, exp_index))
        print("   ...inside the seal   : %s (expected %s)" % (got_seal_index, SEAL_CLASS_EXPECTED))
        if got_index != exp_index or got_seal_index != SEAL_CLASS_EXPECTED:
            raise RuntimeError("classification counts do not match the declaration")

        s_after = seal(cur)
        print("C  seal AFTER           : %s (expected %s)" % (s_after, SEAL_EXPECTED))
        if s_after != SEAL_EXPECTED:
            raise RuntimeError("seal moved across the write")

        # The invariant, both directions.
        cur.execute("SELECT count(*) n FROM triton_flow_shadow WHERE instrument_class IS NULL")
        unclassified = cur.fetchone()["n"]
        cur.execute("SELECT count(*) n FROM triton_flow_shadow "
                    "WHERE (instrument_class = %s) <> (upper(ticker) = ANY(%s))",
                    (CLASS_CASH_SETTLED_INDEX, idx_syms))
        disagree = cur.fetchone()["n"]
        print("   unclassified rows    : %s (must be 0)" % unclassified)
        print("   class<->symbol disagr: %s (must be 0)" % disagree)
        if unclassified or disagree:
            raise RuntimeError("invariant violated")

        conn.commit()
        print()
        print("PASS - instrument_class = 'cash_settled_index' <-> ticker in the set. COMMITTED.")
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
    ap.add_argument("--commit", action="store_true")
    raise SystemExit(main(ap.parse_args().commit))
