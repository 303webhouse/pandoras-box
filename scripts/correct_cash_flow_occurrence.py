"""R-IV.557(c) — correct `cash_flows.occurrence` to describe its own key.

    python scripts/correct_cash_flow_occurrence.py --plan     (measure, write nothing)
    python scripts/correct_cash_flow_occurrence.py --apply

THE DEFECT. The column defaulted to 1 while every route keys on 0, so a route-written
row stored "this is the second occurrence" against a `dedup_key` that encodes the
first. The column's only job is to tell two identical same-day movements apart, so a
value that contradicts its own key describes nothing.

WHY EVERY ROW AND NOT ONLY THE KEYED ONES. A census over the whole table found ONE
duplicated (account_name, flow_type, amount, activity_date) group -- the two Robinhood
anchors of 2026-09-24 -- and those two are told apart by their idempotency keys, not
by a counter. So nothing in this book is a second occurrence of anything, and every
row carrying 1 is claiming to be one.

EVERY CORRECTION LEAVES A ROW. A money table that can be edited without a trace is
one nobody can audit afterwards, and "we fixed some of them" is not a statement
anyone can check. One `cash_flow_corrections` row per column changed, naming the old
value, the new value, the reason, the ruling and the actor.

IDEMPOTENT. It selects on `occurrence <> 0`, so a second run corrects nothing and
writes no audit rows. Re-running is how you verify the first run.
"""

from __future__ import annotations

import argparse
import json
import sys

RULING = "R-IV.557(c)"
ACTOR = "CC-BUILD"
REASON = ("occurrence defaulted to 1 while every route keys on 0, so the column "
          "contradicted the dedup_key that identifies the row; nothing in this book "
          "is a second occurrence of anything")


def _url() -> str:
    cfg = json.load(open(r"C:\trading-hub\.mcp.json"))
    pg = cfg["mcpServers"]["postgres"]
    for a in pg.get("args", []):
        if isinstance(a, str) and a.startswith("postgres"):
            return a
    for v in (pg.get("env") or {}).values():
        if isinstance(v, str) and v.startswith("postgres"):
            return v
    raise SystemExit("no database url")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--plan", action="store_true")
    a = ap.parse_args()
    if not (a.apply or a.plan):
        ap.error("choose --plan or --apply")

    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(_url())
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""SELECT id, account_name, flow_type, amount, activity_date,
                          imported_from, occurrence, (dedup_key IS NOT NULL) AS keyed
                     FROM cash_flows WHERE occurrence <> 0 ORDER BY id""")
    rows = cur.fetchall()
    keyed = [r for r in rows if r["keyed"]]
    print("rows with occurrence <> 0 : %d  (%d keyed, %d unkeyed)"
          % (len(rows), len(keyed), len(rows) - len(keyed)))
    for r in rows:
        print("   id=%-4s %-18s %-16s occurrence=%s%s"
              % (r["id"], r["imported_from"], r["flow_type"], r["occurrence"],
                 "  [keyed]" if r["keyed"] else ""))

    if a.plan:
        print("\nPLAN ONLY - nothing written.")
        conn.rollback()
        return 0

    corrected = 0
    for r in rows:
        cur.execute("UPDATE cash_flows SET occurrence = 0 WHERE id = %s AND occurrence <> 0",
                    (r["id"],))
        if cur.rowcount != 1:
            conn.rollback()
            print("REFUSED: id=%s did not update exactly one row" % r["id"])
            return 1
        cur.execute(
            """INSERT INTO cash_flow_corrections
                   (cash_flow_id, column_name, old_value, new_value, reason, ruling, actor)
               VALUES (%s, 'occurrence', %s, '0', %s, %s, %s)""",
            (r["id"], str(r["occurrence"]), REASON, RULING, ACTOR))
        corrected += 1

    cur.execute("SELECT count(*) AS n FROM cash_flows WHERE occurrence <> 0")
    remaining = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM cash_flow_corrections WHERE ruling = %s", (RULING,))
    audit = cur.fetchone()["n"]

    if remaining != 0 or audit != corrected:
        conn.rollback()
        print("REFUSED: remaining=%s audit=%s corrected=%s - rolled back"
              % (remaining, audit, corrected))
        return 1

    conn.commit()
    print("\ncorrected   : %d" % corrected)
    print("audit rows  : %d" % audit)
    print("remaining   : %d" % remaining)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
