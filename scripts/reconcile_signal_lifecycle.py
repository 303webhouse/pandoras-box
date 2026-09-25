"""R-IV.584(c) — put every signal that is in no state into the state it belongs in.

THE ROWS. `signals.status` and `signals.user_action` record one fact, and five writers each
updated only the half they cared about. `models.signal_lifecycle.state_of` returns None for a row
whose two columns agree on no state, and measured 2026-09-25 that was 761 rows:

    754 at COMMITTEE_REVIEW, of which
        697 the principal had already DISMISSED  -> DISMISSED
         53 the age sweep had already EXPIRED    -> EXPIRED
          4 genuinely unattended                 -> ACTIVE if inside its TTL, else EXPIRED
      7 at DISMISSED with no user_action, every one written by the conflict rule -> WITHHELD

The counts are read at run time, not taken from here — the table is live and they will have
moved. What this file fixes is the CLASSIFICATION, which does not move.

EVERY MOVE LEAVES AN AUDIT ROW. It goes through `services.signal_lifecycle.set_state`, the same
author the live code now uses, so this script cannot reconcile a row into a state the running
system could not have produced. A repair that used its own writer would be the sixth writer.

IDEMPOTENT. It selects on rows that are in no state, so a second run finds nothing and writes no
audit rows. Re-running is how you check the first run.

`--dry-run` prints the classification and changes nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

RULING = "R-IV.584(c)"
ACTOR = "reconcile"


async def _pool():
    import asyncpg
    cfg = json.load(open(os.path.join(HERE, "..", ".mcp.json")))
    args = cfg["mcpServers"]["postgres"]["args"]
    url = next((a for a in reversed(args) if a.startswith("postgres")), None)
    if not url:
        raise RuntimeError("postgres URL not found in .mcp.json")
    return await asyncpg.create_pool(url, min_size=1, max_size=3)


def classify(row) -> tuple:
    """(state, reason) for a row that is in no state. Returns (None, why) if it is not ours.

    The classification reads the columns, never the notes. Prose is not a field: the conflict
    rule's own sentence was reworded in this same ruling, and a repair that matched on it would
    have silently skipped every row written after the rewording.
    """
    from models.signal_lifecycle import (ACTIVE, DISMISSED, EXPIRED, WITHHELD,
                                         COMMITTEE_REVIEW, normalize)

    status = normalize(row["status"])
    action = normalize(row["user_action"]) or None
    expired = row["is_expired"]

    if status == COMMITTEE_REVIEW:
        if action == "DISMISSED":
            return DISMISSED, "the principal dismissed it; the status never moved"
        if action == "EXPIRED":
            return EXPIRED, "the age sweep expired it; the status never moved"
        if action is None:
            # Unattended, and the committee that was meant to review it was retired. Inside its
            # own TTL it goes back on the feed; past it, it is simply over. Deciding by the TTL
            # rather than by a fixed date is what keeps this correct whenever it is run.
            if expired:
                return EXPIRED, "unattended past its expiry; the committee was retired"
            return ACTIVE, "unattended and still inside its expiry; the committee was retired"
        return None, "COMMITTEE_REVIEW with user_action=%s, not a case this handles" % action

    if status == DISMISSED and action is None:
        return WITHHELD, "withheld by the conflict rule, recorded as a bare DISMISSED"

    return None, "status=%s user_action=%s, not a case this handles" % (status, action)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from models.signal_lifecycle import state_of
    from services.signal_lifecycle import set_state

    pool = await _pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT signal_id, status, user_action, created_at,
                   (expires_at IS NOT NULL AND expires_at < NOW())
                     OR (expires_at IS NULL AND created_at < NOW() - INTERVAL '24 hours')
                   AS is_expired
              FROM signals
             ORDER BY created_at
        """)
        # THE SET, chosen the way R-IV.584(c) names it, NOT by "is this row stateless".
        #
        # A stateless scan misses the four rows that matter most. `COMMITTEE_REVIEW` with no
        # user_action is a perfectly COHERENT state -- `state_of` returns it -- so a scan for
        # incoherence walks straight past the only rows genuinely waiting on a committee that
        # no longer exists. Coherent and correct are different questions, and this ruling is
        # about the second one.
        stateless = [r for r in rows if state_of(r["status"], r["user_action"]) is None]
        parked = [r for r in rows if (r["status"] or "").upper() == "COMMITTEE_REVIEW"]
        by_id = {r["signal_id"]: r for r in stateless + parked}
        candidates = list(by_id.values())

        print("rows in the table       : %d" % len(rows))
        print("rows in NO state        : %d" % len(stateless))
        print("rows at COMMITTEE_REVIEW: %d" % len(parked))
        print("candidates              : %d" % len(candidates))

        plan = Counter()
        skipped = Counter()
        work = []
        for r in candidates:
            state, reason = classify(r)
            if state is None:
                skipped["%s / %s" % (r["status"], r["user_action"])] += 1
                continue
            plan["%s -> %s" % (r["status"] or "(null)", state)] += 1
            work.append((r["signal_id"], state, reason))

        print("\nplanned:")
        for k, v in sorted(plan.items()):
            print("  %-42s %d" % (k, v))
        if skipped:
            print("\nNOT HANDLED (left exactly as they are):")
            for k, v in sorted(skipped.items()):
                print("  %-42s %d" % (k, v))

        if args.dry_run:
            print("\n--dry-run: nothing written.")
            return 0

        done, refused = Counter(), []
        for signal_id, state, reason in work:
            result = await set_state(conn, signal_id, state, reason=reason,
                                     actor=ACTOR, ruling=RULING)
            if result.get("changed"):
                done[state] += 1
            else:
                refused.append((signal_id, result.get("reason")))

        print("\nwritten:")
        for k, v in sorted(done.items()):
            print("  %-42s %d" % (k, v))
        if refused:
            print("\nrefused (%d):" % len(refused))
            for sid, why in refused[:10]:
                print("  %s — %s" % (sid, why))

        # The checks that matter. NOT "nothing is in no state any more" -- 17,677 rows predate
        # R-IV.434(b), when a system expiry wrote the principal's own word 'DISMISSED', and
        # that ruling said in terms that they keep what they were written with. Rewriting them
        # would be a history rewrite. So the checks are the two this ruling is about.
        after = await conn.fetch("SELECT status, user_action FROM signals")
        left_parked = sum(1 for r in after
                          if (r["status"] or "").upper() == "COMMITTEE_REVIEW")
        left_bare = sum(1 for r in after
                        if (r["status"] or "").upper() == "DISMISSED" and not r["user_action"])
        historical = sum(1 for r in after if state_of(r["status"], r["user_action"]) is None)
        print("")
        print("still at COMMITTEE_REVIEW : %d" % left_parked)
        print("still a bare DISMISSED    : %d" % left_bare)
        print("in no state (pre-R-IV.434(b) history, out of scope): %d" % historical)
        audit = await conn.fetchval(
            "SELECT COUNT(*) FROM signal_lifecycle_events WHERE ruling = $1", RULING)
        print("audit rows written     : %d" % audit)
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
