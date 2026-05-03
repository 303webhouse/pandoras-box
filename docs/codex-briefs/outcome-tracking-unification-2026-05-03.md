# CC Build Brief: Outcome Tracking Unification (P0)

**Authored:** 2026-05-03
**Status:** Titans-reviewed, ready for CC
**Priority:** P0 — blocks every strategy promotion call until shipped
**Estimated CC effort:** 1-2 days

## Problem

The `signals.outcome*` columns and the `signal_outcomes` table both record
trade outcomes for the same signals, with ~27% disagreement on Holy_Grail
gate-typed signals (n=358 resolved). Discovered while running a 3-10 Oscillator
shadow→live promotion audit on 2026-05-03.

**Disagreement breakdown** (from `three_audits_v2.py` audit 1e):

| signals.outcome | signal_outcomes.outcome | n   |
|-----------------|-------------------------|----:|
| LOSS            | STOPPED_OUT             | 134 |
| WIN             | STOPPED_OUT             | 56  |
| WIN             | HIT_T1                  | 24  |
| LOSS            | PENDING                 | 5   |
| WIN             | PENDING                 | 5   |
| LOSS            | HIT_T1                  | 3   |

**Suspected cause:** denormalization split-brain. `signal_outcomes` is the
older, canonical, MFE/MAE-tracking table. `signals.outcome*` columns were
added later (commit `35ef4f3`, Phase 2E/3 Analytics Overhaul) as a
denormalized projection for dashboard query speed. They've drifted because
they're maintained by separate code paths.

**Impact:** Every analytics query, committee feedback loop, and Olympus
calibration that read `signals.outcome*` after commit `35ef4f3` is on
potentially-contaminated data, including:
- URSA score-band calibration (`backend/jobs/score_signals.py`)
- Olympus Pass 9 v2 percentile thresholds (commit `4d16c9b`) — likely needs re-run after fix
- All strategy comparisons in `committee_bridge.py` / `committee_history.py`
- The 3-10 promotion audit that surfaced this issue

## Goal

Make `signal_outcomes` the canonical source of truth. Make `signals.outcome*`
a strictly-projected denormalization, written *only* by the resolver as a
copy of the corresponding `signal_outcomes` row. No other writer permitted.

## Scope

### In scope
1. Audit every writer of `signals.outcome*` columns — identify any non-resolver writers
2. Refactor resolver to write `signal_outcomes` first (canonical), then
   project to `signals.outcome*` (denormalized projection)
3. One-time backfill: rebuild `signals.outcome*` for all historical rows
   from current `signal_outcomes` data, with diff report
4. Add `signal_outcome_diff_log` audit table capturing every row that
   changes during backfill (old → new)
5. Add CI/test assertion: `signals.outcome` always matches projection from
   `signal_outcomes`
6. Add HELIOS tooltip on win/loss displays: "Outcome resolved via 15m bar walk"
7. Update `PROJECT_RULES.md` with contamination window notation

### Out of scope
- Redesigning the resolver walk-forward logic (it's sound)
- Changing 15m bar walking, target/stop semantics, tiebreak rules
- UI overhaul of analytics widgets beyond the tooltip
- Any rollback of decisions made on contaminated data
  (will re-run affected calibrations as separate task after this ships)
- Migration to UW for resolver OHLCV (currently uses yfinance per `outcome_resolver.py`;
  TODO migration is separate)

## Investigation Steps (CC must do these BEFORE writing migration code)

### Step 1: Find every writer of `signals.outcome*`

```
findstr /S /I /N "outcome_pnl_pct\|outcome_resolved_at\|outcome =" backend\*.py
```

Expected writers (these are OK):
- `backend/jobs/outcome_resolver.py` — the resolver
- `backend/jobs/score_signals.py` — has `_update_outcome` helper, may UPDATE signals

UNEXPECTED writers = root cause. Document and flag to Nick before
proceeding.

### Step 2: Determine why disagreements occur

Likely candidates (verify which):
- Different target levels (`target_1` vs `t1`/`t2`/`invalidation_level`)
- Different time windows / backfill horizons
- Same-bar tiebreak asymmetry
- One table updated, other not (most likely — denormalization drift)

Run a ticker-level diff on 5-10 disagreement rows, walk the bars manually,
identify which resolver matches the actual price action. That's the
canonical one. **Hypothesis: signal_outcomes is correct.** Verify, don't assume.

### Step 3: Compare schema definitions

`signals.outcome` is `varchar` with values WIN/LOSS.
`signal_outcomes.outcome` is `varchar` with values STOPPED_OUT/HIT_T1/HIT_T2/PENDING.

The projection must define a clean mapping:
- `STOPPED_OUT` → `LOSS`
- `HIT_T1` / `HIT_T2` → `WIN`
- `PENDING` → NULL (signals.outcome stays unresolved)

Confirm this mapping with Nick before backfill runs.

## Implementation

### Migration `013_outcome_projection_unification.sql`

```sql
-- Audit log table for the backfill diff report
CREATE TABLE IF NOT EXISTS signal_outcome_diff_log (
    id SERIAL PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES signals(signal_id),
    old_outcome VARCHAR,
    new_outcome VARCHAR,
    old_pnl_pct DOUBLE PRECISION,
    new_pnl_pct DOUBLE PRECISION,
    old_resolved_at TIMESTAMPTZ,
    new_resolved_at TIMESTAMPTZ,
    backfill_run_id TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_diff_log_run ON signal_outcome_diff_log(backfill_run_id);
CREATE INDEX idx_diff_log_signal ON signal_outcome_diff_log(signal_id);

-- Add CI assertion view (queryable for nightly drift check)
CREATE OR REPLACE VIEW v_outcome_drift AS
SELECT s.signal_id,
       s.outcome AS signals_outcome,
       so.outcome AS signal_outcomes_outcome,
       s.outcome_pnl_pct AS signals_pnl,
       so.max_favorable AS so_mfe,
       so.max_adverse AS so_mae
FROM signals s
JOIN signal_outcomes so ON so.signal_id = s.signal_id
WHERE s.outcome IS NOT NULL
  AND so.outcome IS NOT NULL
  AND (
    -- Drift detection mapping
    (s.outcome = 'WIN'  AND so.outcome NOT IN ('HIT_T1','HIT_T2'))
    OR
    (s.outcome = 'LOSS' AND so.outcome != 'STOPPED_OUT')
  );
```

### Code changes in `backend/jobs/outcome_resolver.py`

**Find anchor:**
```python
        if outcome:
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE signals
                    SET outcome = $1,
                        outcome_pnl_pct = $2,
                        outcome_resolved_at = $3
                    WHERE signal_id = $4
                """, outcome, pnl_pct, resolved_at, sig["signal_id"])
```

**Replace with:**
```python
        if outcome:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    # Canonical write: signal_outcomes
                    await conn.execute("""
                        INSERT INTO signal_outcomes (
                            signal_id, symbol, signal_type, direction,
                            entry, stop, t1, outcome, outcome_at, outcome_price
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        ON CONFLICT (signal_id) DO UPDATE
                          SET outcome = EXCLUDED.outcome,
                              outcome_at = EXCLUDED.outcome_at,
                              outcome_price = EXCLUDED.outcome_price
                    """,
                        sig["signal_id"], ticker,
                        sig.get("signal_type"), direction,
                        entry, stop, target,
                        # signal_outcomes uses HIT_T1/STOPPED_OUT
                        "HIT_T1" if outcome == "WIN" else "STOPPED_OUT",
                        resolved_at,
                        target if outcome == "WIN" else stop,
                    )
                    # Denormalized projection: signals.outcome*
                    await conn.execute("""
                        UPDATE signals
                        SET outcome = $1,
                            outcome_pnl_pct = $2,
                            outcome_resolved_at = $3
                        WHERE signal_id = $4
                    """, outcome, pnl_pct, resolved_at, sig["signal_id"])
```

### Backfill script `scripts/backfill_outcome_projection.py`

Rebuild `signals.outcome*` for all rows where `signal_outcomes` has a
resolved outcome but the projection on `signals` differs.

```python
"""Backfill signals.outcome* projection from signal_outcomes (canonical)."""
import asyncio, uuid
from datetime import datetime
from database.postgres_client import get_postgres_client

MAPPING = {
    "HIT_T1": "WIN", "HIT_T2": "WIN",
    "STOPPED_OUT": "LOSS",
    "PENDING": None,
}

async def main(dry_run: bool = True):
    run_id = f"backfill_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT s.signal_id, s.outcome AS old_outcome, s.outcome_pnl_pct AS old_pnl,
                   s.outcome_resolved_at AS old_resolved,
                   so.outcome AS so_outcome, so.outcome_at, so.outcome_price,
                   s.entry_price, s.stop_loss, s.target_1, s.direction
            FROM signals s
            JOIN signal_outcomes so ON so.signal_id = s.signal_id
            WHERE so.outcome IS NOT NULL AND so.outcome != 'PENDING'
        """)

        diffs = []
        for r in rows:
            new_outcome = MAPPING.get(r["so_outcome"])
            entry = float(r["entry_price"] or 0)
            if r["direction"] == "LONG":
                if new_outcome == "WIN":
                    new_pnl = (float(r["target_1"]) - entry) / entry * 100
                else:
                    new_pnl = (float(r["stop_loss"]) - entry) / entry * 100
            else:
                if new_outcome == "WIN":
                    new_pnl = (entry - float(r["target_1"])) / entry * 100
                else:
                    new_pnl = (entry - float(r["stop_loss"])) / entry * 100

            new_resolved = r["outcome_at"]

            if (r["old_outcome"] != new_outcome
                or abs((r["old_pnl"] or 0) - new_pnl) > 0.01
                or r["old_resolved"] != new_resolved):
                diffs.append((r, new_outcome, new_pnl, new_resolved))

        print(f"[{run_id}] {len(diffs)} rows would change of {len(rows)} examined")
        print(f"[{run_id}] dry_run={dry_run}")

        if dry_run:
            for r, no, np, nr in diffs[:20]:
                print(f"  {r['signal_id']}: {r['old_outcome']}({r['old_pnl']}) -> {no}({np:.2f})")
            print(f"  ... ({len(diffs)} total)")
            return

        # GUARDRAIL: if >5% of rows would change, halt and require approval
        if len(diffs) / max(len(rows), 1) > 0.05:
            print(f"HALT: {len(diffs)/len(rows)*100:.1f}% drift exceeds 5% threshold.")
            print("Re-run with --force after explicit approval.")
            return

        async with conn.transaction():
            for r, no, np, nr in diffs:
                await conn.execute("""
                    INSERT INTO signal_outcome_diff_log
                      (signal_id, old_outcome, new_outcome, old_pnl_pct, new_pnl_pct,
                       old_resolved_at, new_resolved_at, backfill_run_id)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                """, r["signal_id"], r["old_outcome"], no,
                    r["old_pnl"], np, r["old_resolved"], nr, run_id)

                await conn.execute("""
                    UPDATE signals SET outcome=$1, outcome_pnl_pct=$2,
                                       outcome_resolved_at=$3
                    WHERE signal_id=$4
                """, no, np, nr, r["signal_id"])

        print(f"[{run_id}] applied {len(diffs)} updates")

if __name__ == "__main__":
    import sys
    dry_run = "--apply" not in sys.argv
    asyncio.run(main(dry_run=dry_run))
```

### Frontend tooltip in `frontend/app.js`

CC: search for the win-rate or outcome display component (likely in the
analytics or strategy-performance section). Add a tooltip:

```
"Outcome resolved via 15m forward bar walk to first touch of target/stop"
```

This is additive and shouldn't break anything. If unclear where to place it,
flag for HELIOS review rather than guessing.

### `PROJECT_RULES.md` addition

Add new section "Outcome Tracking" with:
- `signal_outcomes` is canonical
- `signals.outcome*` is a denormalized projection only
- Only `outcome_resolver.py` writes either
- Contamination window: commit `35ef4f3` through this fix
- All strategy promotion comparisons must use `signal_outcomes` as primary,
  with `signals.outcome*` allowed only for dashboard performance queries

## Test Plan

### Pre-deploy on Railway branch DB
1. Create branch DB from prod
2. Run migration 013 → confirm tables/views created
3. Run backfill in `--dry-run` → confirm diff count matches audit
   (~96 rows expected based on Audit 1e disagreement analysis)
4. Verify diff distribution: most should be `signals.WIN → LOSS` reversion
5. Run backfill `--apply` on branch DB
6. Verify `v_outcome_drift` view returns 0 rows
7. Re-run `three_audits_v2.py` on branch DB → confirm rsi vs both delta
   either holds or changes (this is the actual datapoint we need for the
   3-10 promotion re-audit)

### Production deploy
1. Merge migration 013 to main → Railway auto-deploys schema
2. Deploy resolver code change
3. Run backfill `--dry-run` on prod, capture report
4. **Nick reviews diff report.** Approve or halt.
5. If approved: backfill `--apply`
6. Verify `v_outcome_drift` clean
7. Resume normal resolver operation

## Rollback Plan

If anything goes sideways:

1. **During migration:** drop `signal_outcome_diff_log` and `v_outcome_drift`,
   no harm done — these are additive
2. **During resolver code change:** revert resolver commit, redeploy, signals
   resume as before. `signal_outcomes` may have new ON CONFLICT updates that
   are harmless to retain.
3. **During backfill:** every change is logged in `signal_outcome_diff_log`
   with `backfill_run_id`. Reversal SQL:
   ```sql
   UPDATE signals s
   SET outcome = d.old_outcome,
       outcome_pnl_pct = d.old_pnl_pct,
       outcome_resolved_at = d.old_resolved_at
   FROM signal_outcome_diff_log d
   WHERE d.signal_id = s.signal_id
     AND d.backfill_run_id = '<run_id>';
   ```
4. **Post-deploy regret:** the contamination notation in PROJECT_RULES is
   permanent regardless. We don't pretend it didn't happen.

## Acceptance Criteria

✅ Migration 013 applied to prod
✅ Resolver writes both tables in transaction
✅ Backfill dry-run report reviewed and approved by Nick
✅ Backfill applied; `v_outcome_drift` returns 0 rows
✅ `three_audits_v2.py` re-run on cleaned data; results documented
✅ HELIOS tooltip live on win/loss displays
✅ `PROJECT_RULES.md` updated with outcome-tracking section + contamination window
✅ Olympus Pass 9 v2 percentile thresholds flagged for re-run (separate task)

## Followup tasks (NOT this brief — log to TODO)

1. **Re-run 3-10 Oscillator promotion audit** on cleaned data.
2. **Re-run Olympus Pass 9 v2 percentile threshold calibration** if any
   inputs touched `signals.outcome_pnl_pct`.
3. **Migrate resolver OHLCV from yfinance to UW API** (per memory #10 data
   source hierarchy).
4. **Audit other places that may have denormalization drift** — `unified_positions`,
   `closed_positions`, `committee_data` JSONB cached fields.

## Notes for CC

- This brief is structured around investigation FIRST, code change SECOND.
  Do not skip investigation steps. The 27% disagreement might have a cause
  this brief didn't anticipate, and the projection-mapping assumes specific
  semantics that need verification.
- The 5% guardrail in the backfill is intentional. If diff exceeds 5%, halt
  and surface to Nick. AEGIS hard line: no silent rewrites.
- All DB ops via `get_postgres_client()` from `backend/database/postgres_client.py`
  per project rules.
- yfinance fallback is acceptable in the resolver for now (separate followup
  to migrate to UW).
