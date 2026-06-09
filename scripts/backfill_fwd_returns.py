"""FWD_RETURN historical backfill (A3).

Drives the forward-return resolver over explicit signal_id batches (the
signal_ids branch — NOT the looped full-run path, which re-selects the same
most-recent N and dedups to zero).

Candidate set:
  - entry_price present
  - timestamp older than 8 days (old enough that BOTH T+1 and T+5 bars exist,
    so a signal isn't half-graded and then skipped forever by per-signal dedup)
  - no existing signal_forward_returns row (LEFT JOIN ... IS NULL)

Shadow safety: A3_SHADOW_MODE defaults true (compute + log, no writes).
Dry-run with BACKFILL_SLICE=50 (shadow on) first; then A3_SHADOW_MODE=false for
the real run. This shadow-off applies to THIS manual process only — the deployed
Railway env var is untouched.

Resumable: per-row commits + ungraded-list re-derivation on each run mean a
re-run only refetches bars for un-done tickers.
"""

import asyncio
import os
import sys

sys.path.insert(0, r"C:\trading-hub\backend")

from database.postgres_client import get_postgres_client, close_postgres_client
from jobs.a3_fwd_return_resolver import resolve_fwd_returns

CHUNK = 300
DIRS = ["LONG", "BUY", "BULLISH", "SHORT", "SELL", "BEARISH"]


async def main():
    shadow = os.getenv("A3_SHADOW_MODE", "true").lower() != "false"
    slice_n = os.getenv("BACKFILL_SLICE")  # set to e.g. "50" for a dry-run slice

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT current_database()") == "railway", "not prod"
        ids = [r["signal_id"] for r in await conn.fetch(
            """
            SELECT s.signal_id
            FROM signals s
            LEFT JOIN signal_forward_returns f ON f.signal_id = s.signal_id
            WHERE s.entry_price IS NOT NULL
              AND s.timestamp < NOW() - INTERVAL '8 days'
              AND UPPER(s.direction) = ANY($1::text[])
              AND f.signal_id IS NULL
            ORDER BY s.ticker, s.timestamp DESC
            """, DIRS)]

    if slice_n:
        ids = ids[:int(slice_n)]

    print(f"WRITES={'OFF (shadow)' if shadow else 'ON'}  to_backfill={len(ids)}"
          + (f"  (SLICE={slice_n})" if slice_n else ""))

    wtot = stot = 0
    for i in range(0, len(ids), CHUNK):
        batch = ids[i:i + CHUNK]
        r = await resolve_fwd_returns(pool, signal_ids=batch, limit=len(batch))
        wtot += r.get("written", 0)
        stot += r.get("skipped", 0)
        print(f"  batch {i // CHUNK + 1}: written={r.get('written')} "
              f"skipped={r.get('skipped')}  cum w={wtot} s={stot}")

    await close_postgres_client()
    print(f"DONE written={wtot} skipped={stot}")


asyncio.run(main())
