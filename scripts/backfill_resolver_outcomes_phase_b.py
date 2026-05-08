"""Phase B backfill — re-resolve every BAR_WALK row with corrected resolver logic.

PRECONDITION: outcome_resolver.py Phase B patches must already be deployed and
running cleanly (one resolver tick observed writing outcome_resolved_at >= signal_ts).

Operation:
  1. Generate a unique backfill_run_id.
  2. SELECT every signal where outcome_source = 'BAR_WALK' AND outcome IS NOT NULL.
  3. For each row, re-run _walk_bars (corrected) with current yfinance data.
  4. Compare new (outcome, pnl_pct) to current. If changed, log diff.
  5. --dry-run (default): print transition histogram only; no writes.
  6. --apply: single transaction; writes diff_log entries + UPDATE signals rows.

Concurrency: row-disjoint with the live resolver (resolver writes outcome IS NULL;
backfill writes outcome_source='BAR_WALK' rows that already have outcome set).
Recommended to run outside market hours (post-4 PM ET weekday or any weekend) for
belt-and-braces, but not required for correctness.

yfinance non-determinism: yfinance data may have been corrected since original
resolution. The corrected resolver running today on TODAY's data is the new
source of truth; we accept that some rows will produce different outcomes than
their original (buggy) resolution. The acceptance test is agreement with
signal_outcomes (canonical bar-walk source), not reproduction of original values.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

# Add backend/ to path so we can import the patched _walk_bars
sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"),
)
from jobs.outcome_resolver import _walk_bars  # noqa: E402

DB_URL = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DB_URL:
    sys.exit("FATAL: DATABASE_PUBLIC_URL/DATABASE_URL not set")


def fetch_bar_walk_rows(cur):
    cur.execute("""
        SELECT signal_id, ticker, direction, entry_price,
               stop_loss, target_1, timestamp,
               outcome, outcome_pnl_pct, outcome_resolved_at
        FROM signals
        WHERE outcome_source = 'BAR_WALK'
          AND outcome IS NOT NULL
        ORDER BY timestamp ASC
    """)
    return cur.fetchall()


def reresolve_row(row):
    """Returns (new_outcome, new_pnl_pct, matched_bar_ts) on corrected logic."""
    signal_ts = row["timestamp"]
    if signal_ts.tzinfo is None:
        signal_ts = signal_ts.replace(tzinfo=timezone.utc)
    direction = (row["direction"] or "").upper()
    if direction not in ("LONG", "SHORT"):
        return None, None, None
    return _walk_bars(
        row["ticker"],
        direction,
        float(row["entry_price"]),
        float(row["target_1"]),
        float(row["stop_loss"]),
        signal_ts,
    )


def transition_label(old, new):
    """Classify the (old → new) outcome transition for the histogram."""
    if old == new:
        return f"{old or 'NULL'} -> unchanged"
    return f"{old or 'NULL'} -> {new or 'NULL'}"


def main(apply: bool):
    backfill_run_id = f"phase_b_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    print(f"backfill_run_id = {backfill_run_id}")
    print(f"mode            = {'APPLY (writes)' if apply else 'DRY RUN (no writes)'}")
    print()

    conn = psycopg2.connect(DB_URL, connect_timeout=15)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    rows = fetch_bar_walk_rows(cur)
    print(f"Loaded {len(rows)} BAR_WALK rows")
    print()

    transitions = Counter()
    diffs = []  # list of dicts for diff_log inserts (apply mode)

    for i, row in enumerate(rows, 1):
        try:
            new_outcome, new_pnl, matched_bar_ts = reresolve_row(row)
        except Exception as e:
            print(f"  [{i}/{len(rows)}] {row['signal_id']}: ERROR {e}")
            transitions[f"{row['outcome']} -> ERROR"] += 1
            continue

        old_outcome = row["outcome"]
        old_pnl = float(row["outcome_pnl_pct"]) if row["outcome_pnl_pct"] is not None else None
        old_resolved_at = row["outcome_resolved_at"]

        label = transition_label(old_outcome, new_outcome)
        transitions[label] += 1

        if i % 25 == 0:
            print(f"  ... {i}/{len(rows)} processed")

        if old_outcome != new_outcome or (
            old_pnl is not None and new_pnl is not None and abs(old_pnl - (new_pnl or 0)) > 0.01
        ):
            diffs.append({
                "signal_id": row["signal_id"],
                "old_outcome": old_outcome,
                "new_outcome": new_outcome,
                "old_pnl_pct": old_pnl,
                "new_pnl_pct": new_pnl,
                "old_resolved_at": old_resolved_at,
                "backfill_run_id": backfill_run_id,
            })

    print()
    print("=" * 78)
    print("Transition histogram")
    print("=" * 78)
    for label, n in sorted(transitions.items(), key=lambda x: -x[1]):
        print(f"  {label:<40s} {n:>5d}")
    print()
    print(f"Total rows processed: {len(rows)}")
    print(f"Rows that would change: {len(diffs)}")
    print()

    if not apply:
        print("DRY RUN — no writes performed. Re-run with --apply to commit.")
        cur.close()
        conn.close()
        return

    # APPLY mode: single transaction
    print("APPLY mode: writing diff_log entries and updating signals rows...")
    try:
        for diff in diffs:
            cur.execute("""
                INSERT INTO signal_outcome_diff_log
                    (signal_id, old_outcome, new_outcome,
                     old_outcome_source, new_outcome_source,
                     old_pnl_pct, new_pnl_pct,
                     old_resolved_at, new_resolved_at,
                     backfill_run_id)
                VALUES (%(signal_id)s, %(old_outcome)s, %(new_outcome)s,
                        'BAR_WALK', 'BAR_WALK',
                        %(old_pnl_pct)s, %(new_pnl_pct)s,
                        %(old_resolved_at)s, NOW(),
                        %(backfill_run_id)s)
            """, diff)

            if diff["new_outcome"] is None:
                # No touch on corrected logic — clear outcome
                cur.execute("""
                    UPDATE signals
                    SET outcome = NULL,
                        outcome_pnl_pct = NULL,
                        outcome_resolved_at = NULL
                    WHERE signal_id = %s
                """, (diff["signal_id"],))
            else:
                cur.execute("""
                    UPDATE signals
                    SET outcome = %s,
                        outcome_pnl_pct = %s,
                        outcome_resolved_at = NOW()
                    WHERE signal_id = %s
                """, (diff["new_outcome"], diff["new_pnl_pct"], diff["signal_id"]))

        conn.commit()
        print(f"COMMITTED {len(diffs)} diff_log entries and signals updates.")
        print(f"Rollback handle: backfill_run_id = {backfill_run_id}")
    except Exception as e:
        conn.rollback()
        print(f"FAILED: {e}")
        print("Transaction rolled back. No changes persisted.")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase B resolver backfill")
    parser.add_argument("--apply", action="store_true",
                        help="Apply changes (default: dry-run only)")
    args = parser.parse_args()
    main(apply=args.apply)
