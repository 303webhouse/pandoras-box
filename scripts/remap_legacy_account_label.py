"""Remap rows written under a retired account alias (R-IV.445(a)).

READS BY DEFAULT. It prints what it would change and exits. `--confirm` is the principal's
word, and nothing else in this file writes.

WHAT IT DOES NOT DO, deliberately:
  * it does not invent a mapping. Only aliases the canonical module already resolves are
    remapped, so this script cannot decide what an unknown label meant.
  * it does not touch the disputed label. BROKERAGE_LINK_401K is under an open question about
    which plan it names; resolving it here would take a side in that question by writing.
  * it does not re-run silently. Every row it changes is printed with its before and after.

Usage (from backend/):
    python ../scripts/remap_legacy_account_label.py                # preview
    python ../scripts/remap_legacy_account_label.py --confirm      # write
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from models.accounts import CANONICAL_ACCOUNTS, DISPUTED, normalize_account  # noqa: E402

REASON = "R-IV.445(a): retired account alias remapped to the canonical label"

# CORRECTED 2026-09-18 (R-IV.450). The first run was scoped to unified_positions, because that
# is the table the defect was noticed in — and the alias survived in every other table that
# stores the label. That is the same shape as an account-scoped inventory that cannot see a row
# filed elsewhere, committed here one ruling later: A VOCABULARY FIX IS SCOPED TO EVERY TABLE
# THAT STORES THE VOCABULARY, not to the table where someone happened to see the problem.
#
# cash_flows and account_balances are listed rather than assumed clean, because "assumed clean"
# is exactly how the first scope was chosen.
TABLES = (
    ("unified_positions", "account", "position_id"),
    ("closed_positions", "account", "id"),
    ("trades", "account", "id"),
    ("cash_flows", "account_name", "id"),
    ("account_balances", "account_name", "id"),
)


async def main(confirm: bool) -> int:
    from database.postgres_client import get_postgres_client
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        plan, skipped = [], []
        for table, column, key in TABLES:
            rows = await conn.fetch(
                f"""SELECT {key} AS key, {column} AS label FROM {table}
                     WHERE {column} IS NOT NULL AND {column} <> ALL($1::text[])
                     ORDER BY {key}""", list(CANONICAL_ACCOUNTS))
            for r in rows:
                target = normalize_account(r["label"])
                if not target or r["label"] in DISPUTED:
                    skipped.append((table, key, r,
                                    "no canonical meaning — needs a ruling, not a guess"))
                else:
                    plan.append((table, column, key, r, target))

        print(f"\n{len(plan) + len(skipped)} row(s) across {len(TABLES)} table(s) carry a "
              f"non-canonical label.\n")
        for table, column, key, r, target in plan:
            print(f"  {table:20} {key}={str(r['key']):30} {r['label']} -> {target}")
        for table, key, r, why in skipped:
            print(f"  SKIP {table:16} {key}={str(r['key']):30} {r['label']}: {why}")

        if not plan:
            print("\nNothing to remap.")
            return 0
        if not confirm:
            print(f"\nPREVIEW ONLY — {len(plan)} row(s) would change. Re-run with --confirm "
                  f"to write.")
            return 0

        async with conn.transaction():
            await conn.execute("SELECT set_config('app.actor', $1, true)", "principal")
            await conn.execute("SELECT set_config('app.reason', $1, true)", REASON)
            for table, column, key, r, target in plan:
                await conn.execute(
                    f"UPDATE {table} SET {column} = $1 WHERE {key} = $2 AND {column} = $3",
                    target, r["key"], r["label"])
        print(f"\n{len(plan)} row(s) remapped across {len({t for t, *_ in plan})} table(s). "
              f"Only the label column was written; unified_positions also carries the "
              f"before/after on its audit timeline.")
        return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--confirm", action="store_true",
                    help="write the remap (default is a preview that changes nothing)")
    sys.exit(asyncio.run(main(ap.parse_args().confirm)))
