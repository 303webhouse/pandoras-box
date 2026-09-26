"""R-IV.571 / gap 3 — move each open row's exit plan out of prose and into fields.

`notes` IS LEFT EXACTLY AS IT IS. The sentence stays the record of what Trade Analysis wrote; the
fields become what code reads. Nothing is deleted, so a disagreement between the two is always
resolvable afterwards.

IDEMPOTENT. It writes only where a parsed value differs from what is stored, so a second run
changes nothing. Re-running is how you check the first run.

IT REPORTS THE ROWS IT DID NOT TOUCH, by name. R-IV.597(b)2: "List any open row without the line;
infer nothing from other prose." A row whose notes mention an exit in some other wording is listed
as unplanned, not guessed at — twelve of the twenty-three open rows mention "exit" somewhere and
only four carry the line, so guessing from prose would have invented plans for eight of them.

`--dry-run` prints what it would write and changes nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

RULING = "R-IV.571 / gap 3 (R-IV.597(b))"
ACTOR = "exit-plan-migration"


async def _pool():
    import asyncpg
    cfg = json.load(open(os.path.join(HERE, "..", ".mcp.json")))
    args = cfg["mcpServers"]["postgres"]["args"]
    url = next((a for a in reversed(args) if a.startswith("postgres")), None)
    if not url:
        raise RuntimeError("postgres URL not found in .mcp.json")
    return await asyncpg.create_pool(url, min_size=1, max_size=3)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from models.exit_plan import has_exit_line, parse_exit_line
    from utils.audit_actor import name_actor

    pool = await _pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT position_id, ticker, quantity, notes,
                   invalidation, time_stop, stop_type
              FROM unified_positions
             WHERE status = 'OPEN'
             ORDER BY position_id
        """)

        planned, unplanned, mentions_exit = [], [], []
        for r in rows:
            if has_exit_line(r["notes"]):
                planned.append(r)
            else:
                unplanned.append(r)
                if "exit" in (r["notes"] or "").lower():
                    mentions_exit.append(r["position_id"])

        print("open rows                 : %d" % len(rows))
        print("carrying the EXIT line    : %d" % len(planned))
        print("without it                : %d" % len(unplanned))
        print("  ...of which mention 'exit' in some OTHER wording: %d" % len(mentions_exit))

        print("\nPARSED:")
        writes, refusals = [], []
        for r in planned:
            parsed = parse_exit_line(r["notes"])
            print("  %-30s %-6s inval=%-46s time_stop=%-11s stop=%s" % (
                r["position_id"], r["ticker"], (parsed["invalidation"] or "-")[:46],
                parsed["time_stop"], parsed["stop_type"]))
            if parsed["unparsed"]:
                print("       COULD NOT READ: %s" % parsed["unparsed"])
                refusals.append((r["position_id"], parsed["unparsed"]))
                continue
            if (r["invalidation"] == parsed["invalidation"]
                    and r["time_stop"] == parsed["time_stop"]
                    and r["stop_type"] == parsed["stop_type"]):
                continue                       # already migrated
            writes.append((r["position_id"], parsed))

        print("\nWITHOUT THE LINE (left exactly as they are):")
        for r in unplanned:
            flag = "  [notes mention 'exit' in other words]" if r["position_id"] in mentions_exit else ""
            print("  %-30s %-6s qty=%s%s" % (r["position_id"], r["ticker"], r["quantity"], flag))

        if refusals:
            print("\nREFUSED (%d) — a partial line is not migrated at all:" % len(refusals))
            for pid, why in refusals:
                print("  %s — %s" % (pid, why))

        if args.dry_run:
            print("\n--dry-run: %d row(s) would be written. Nothing changed." % len(writes))
            return 0

        for pid, parsed in writes:
            async with conn.transaction():
                await name_actor(conn, ACTOR, RULING)
                await conn.execute(
                    """UPDATE unified_positions
                          SET invalidation = $2, time_stop = $3, stop_type = $4
                        WHERE position_id = $1""",
                    pid, parsed["invalidation"], parsed["time_stop"], parsed["stop_type"])
        print("\nwritten: %d row(s)" % len(writes))

        after = await conn.fetch("""
            SELECT position_id, ticker, invalidation, time_stop, stop_type, notes
              FROM unified_positions WHERE status='OPEN' AND invalidation IS NOT NULL
             ORDER BY position_id
        """)
        print("open rows now carrying fields: %d" % len(after))
        # The check that matters: the sentence is still there.
        kept = sum(1 for r in after if has_exit_line(r["notes"]))
        print("...and all %d still carry the original line in notes: %s"
              % (len(after), kept == len(after)))
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
