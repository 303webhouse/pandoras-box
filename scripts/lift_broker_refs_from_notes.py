"""Move broker references out of `notes` and into the columns (R-IV.448(b)).

READS BY DEFAULT. It prints what it would write and exits; `--confirm` writes.

A reference in prose can be read by a human and by nothing else — it cannot be joined,
counted, or checked, and the verification stamp that depends on it cannot be enforced. This
moves what POSITIONS captured into `broker_ref` (the order that opened the row) and
`exit_broker_ref` (the order that closed it), and does NOT delete the prose: the note is the
record of how the reference was established, and the column is the field the system can use.

WHAT IT REFUSES TO DECIDE:
  * it never guesses which reference is which. The entry/exit split is taken from the words
    around each reference ("bought ... ref X", "sold ... ref Y"); where the note does not say,
    the row is listed as UNDECIDED and left alone.
  * it never stamps BROKER_VERIFIED. A reference is evidence; the verification is a separate
    transition that also records what was matched and when.
  * it writes nothing where a column already holds a value, so a second run cannot overwrite
    a reference something else set.

Usage (from backend/):
    python ../scripts/lift_broker_refs_from_notes.py              # preview
    python ../scripts/lift_broker_refs_from_notes.py --confirm    # write
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

REF = r"[0-9]{4,6}-[A-Z0-9]{5,8}"
# The reference with the words immediately before it, which is what says entry or exit.
CONTEXT = re.compile(r"(.{0,60}?)(?:ref|confirm(?:ation)?)[ :#]*(" + REF + ")",
                     re.IGNORECASE | re.DOTALL)
BUY_WORDS = ("bought", "buy", "bto", "opened", "acquired")
SELL_WORDS = ("sold", "sell", "sale", "stc", "closed", "exit")
REASON = "R-IV.448(b): broker reference moved from notes into its column"


def classify(note: str):
    """[(side, reference)] for a note. `side` is 'entry', 'exit' or None when it does not say."""
    out = []
    for lead, ref in CONTEXT.findall(note or ""):
        text = lead.lower()
        buy = max((text.rfind(w) for w in BUY_WORDS), default=-1)
        sell = max((text.rfind(w) for w in SELL_WORDS), default=-1)
        side = None
        if buy >= 0 or sell >= 0:
            side = "entry" if buy > sell else "exit"
        out.append((side, ref))
    return out


async def main(confirm: bool) -> int:
    from database.postgres_client import get_postgres_client
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT position_id, ticker, status, notes, broker_ref, exit_broker_ref
                  FROM unified_positions
                 WHERE notes ~ '{REF}'
                 ORDER BY position_id""")
        plan, undecided = [], []
        for r in rows:
            found = classify(r["notes"])
            entry = next((ref for side, ref in found if side == "entry"), None)
            exit_ref = next((ref for side, ref in found if side == "exit"), None)
            unknown = [ref for side, ref in found if side is None]
            # A single reference with no word to place it is left alone rather than assumed to
            # be the entry: half of these rows were opened and closed by different orders.
            if unknown:
                undecided.append((r, unknown))
            if (entry and not r["broker_ref"]) or (exit_ref and not r["exit_broker_ref"]):
                plan.append((r, entry, exit_ref))

        print(f"\n{len(rows)} row(s) carry a reference in notes; {len(plan)} would be written.\n")
        for r, entry, exit_ref in plan:
            print(f"  {r['position_id']:34} {r['ticker']:6} {r['status']:8} "
                  f"entry={entry or '-':14} exit={exit_ref or '-':14}")
        for r, unknown in undecided:
            print(f"  UNDECIDED {r['position_id']:26} {r['ticker']:6} {unknown} — the note does "
                  f"not say which order this is; left alone")
        if not plan:
            print("\nNothing to write.")
            return 0
        if not confirm:
            print(f"\nPREVIEW ONLY — re-run with --confirm to write. No row is stamped "
                  f"BROKER_VERIFIED by this script; a reference is evidence, not a verification.")
            return 0

        async with conn.transaction():
            await conn.execute("SELECT set_config('app.actor', $1, true)", "positions-lane")
            await conn.execute("SELECT set_config('app.reason', $1, true)", REASON)
            for r, entry, exit_ref in plan:
                await conn.execute(
                    """UPDATE unified_positions
                          SET broker_ref = COALESCE(broker_ref, $1),
                              exit_broker_ref = COALESCE(exit_broker_ref, $2),
                              updated_at = NOW()
                        WHERE position_id = $3""",
                    entry, exit_ref, r["position_id"])
        print(f"\n{len(plan)} row(s) written. The notes are unchanged — they record how each "
              f"reference was established.")
        return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--confirm", action="store_true",
                    help="write (default is a preview that changes nothing)")
    sys.exit(asyncio.run(main(ap.parse_args().confirm)))
