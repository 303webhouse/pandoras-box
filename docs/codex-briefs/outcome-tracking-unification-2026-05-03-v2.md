# CC Build Brief: Outcome Tracking Unification — Phase A (P0)

**Authored:** 2026-05-03 (supersedes v1 same-day)
**Status:** Investigation complete (see findings section), ready for CC
**Priority:** P0 — unblocks strategy comparison work, prerequisite for Phases B and C
**Scope this brief:** Phase A only — labeling, no value rewrites
**Estimated CC effort:** ~4-6 hours

---

## What changed from v1

The v1 brief assumed the `signals.outcome*` ↔ `signal_outcomes` divergence was a
simple denormalization-drift problem fixable by a one-shot backfill that
projected `signal_outcomes` → `signals.outcome*`. Investigation produced three
findings that invalidated that approach:

1. **`signals.outcome` carries three semantically distinct meanings**, not one.
   Different writers populate it with different intent: bar-walk hypothetical
   (resolver), actual trade close P&L (Ariadne), and what-if analysis
   (counterfactual). A unified projection from `signal_outcomes` would erase
   the actual-trade-outcome semantic.
2. **The 110 WIN/STOPPED_OUT disagreement cluster has zero `unified_positions`
   correlation** — Ariadne is not the writer. The cluster is in fact pure
   resolver-vs-`signal_outcomes` bar-walk-algorithm divergence.
3. **The resolver has a `outcome_resolved_at` timestamp bug** — 30% of LOSS
   rows and 44% of WIN rows have `outcome_resolved_at < signals.timestamp`
   (i.e., resolution timestamp predates signal creation, sometimes by 40+
   days). Counterfactual writer is clean (uses `NOW()`); resolver passes
   raw `bar_ts` from yfinance dataframe iteration which can yield bars
   outside the requested window.

The new approach splits the work into three phases. **This brief covers Phase A
only.** Phases B and C are deferred and will be authored separately.

| Phase | Scope | Why deferred |
|---|---|---|
| **A (this brief)** | Add `signals.outcome_source` enum column. Tag existing rows by writer-provenance heuristic. Patch writers to tag new writes. **Zero value changes.** | Pure-add change. Low risk. Lets analytics start filtering by source immediately. Prerequisite for B/C. |
| **B (followup)** | Fix `outcome_resolver.py` timestamp bug — `bar_ts` from yfinance can predate `signal_ts`. | Investigation pending root cause. Bad timestamps must be fixed before any backfill consumes them. |
| **C (followup)** | Project `signal_outcomes` → `signals.outcome*` for `BAR_WALK`-tagged rows only. Update value mappings. | Cannot run safely until B ships — backfilling buggy timestamps cements them. Also depends on A to know which rows are safe to project. |

---

## Investigation findings (recap, for the record)

Run against prod 2026-05-03:

### Writer enumeration (no 5th writer)

| Site | Table written | Value space |
|---|---|---|
| `backend/jobs/outcome_resolver.py:163` | `signals.outcome*` | WIN, LOSS |
| `backend/api/unified_positions.py:1366` (Ariadne) | `signals.outcome*` + `trade_outcome` + `outcome_pnl_dollars` + `outcome_options_metrics` | WIN, LOSS (mirror of `trade_outcome`) |
| `backend/analytics/api.py:2517` (counterfactual) | `signals.outcome*` | COUNTERFACTUAL_WIN, COUNTERFACTUAL_LOSS |
| `backend/jobs/score_signals.py:222` (`_update_outcome`) | `signal_outcomes.outcome` | HIT_T1, HIT_T2, STOPPED_OUT, INVALIDATED, EXPIRED, PENDING |

### Production value-space (8,863 signals total, 1,025 resolved on `signals.outcome`):

| `signals.outcome` | n | Source writer |
|---|---|---|
| LOSS | 368 | resolver |
| COUNTERFACTUAL_LOSS | 228 | counterfactual |
| WIN | 225 | resolver (NOT Ariadne — zero `unified_positions` correlation) |
| COUNTERFACTUAL_WIN | 204 | counterfactual |

| `signal_outcomes.outcome` | n |
|---|---|
| STOPPED_OUT | 4,551 |
| HIT_T1 | 1,561 |
| EXPIRED | 1,436 |
| HIT_T2 | 478 |
| PENDING | 272 |
| INVALIDATED | 157 |

### Backward-timestamp footprint:

| outcome | total rows | with `outcome_resolved_at < signals.timestamp` | % |
|---|---|---|---|
| LOSS | 368 | 110 | **29.9%** |
| WIN | 225 | 98 | **43.6%** |
| COUNTERFACTUAL_WIN | 204 | 0 | 0.0% |
| COUNTERFACTUAL_LOSS | 228 | 0 | 0.0% |

This is the Phase B fix.

---

## Phase A goal

Add a single column `signals.outcome_source` that records **which writer
produced each `signals.outcome` value**. Tag all existing rows via heuristic
backfill. Patch all writers to tag new writes correctly. Make zero changes to
`outcome`, `outcome_pnl_pct`, or `outcome_resolved_at` values.

This unlocks:
- Strategy-vs-strategy win-rate comparisons can filter to `outcome_source = 'BAR_WALK'` for apples-to-apples (no Ariadne actual-trade overrides, no counterfactuals).
- Olympus / URSA calibration queries can be explicit about which semantic they want.
- Drift-detection view can scope correctly to bar-walk semantics only.
- Lays the groundwork for Phase B (fix bar_ts) and Phase C (unified projection).

---

## Scope

### In scope
1. **Migration `013_outcome_source_phase_a.sql`** — adds `signals.outcome_source` column with CHECK constraint, adds `signal_outcome_diff_log` (stub for Phase C), adds `v_outcome_drift` view scoped to bar-walk semantics.
2. **Backfill script `scripts/backfill_outcome_source.py`** — labels existing rows with `outcome_source` based on writer-provenance heuristics. Pure UPDATE; no value rewrites.
3. **Writer patches** for the three writers that touch `signals.outcome*`:
   - `backend/jobs/outcome_resolver.py` → tags writes with `'BAR_WALK'`
   - `backend/api/unified_positions.py` → tags writes with `'ACTUAL_TRADE'`
   - `backend/analytics/api.py` (counterfactual) → tags writes with `'COUNTERFACTUAL'`
   - `backend/jobs/score_signals.py` writes to `signal_outcomes`, not `signals.outcome`, so no patch needed in Phase A (its writes will be projected to `signals.outcome` with `'PROJECTED_FROM_BAR_WALK'` source in Phase C).
4. **`PROJECT_RULES.md` addition** — three-semantics explanation, query rules.

### Out of scope
- Resolver `bar_ts` timestamp bug → **Phase B**
- Projecting `signal_outcomes` → `signals.outcome*` → **Phase C**
- Reconciling/rewriting any outcome values
- Reconciling `outcome_pnl_pct` or `outcome_resolved_at` values
- Updating analytics queries to use the new column (they can opt in incrementally; no consumer is forced to change)
- Adding `outcome_source` to `signal_outcomes` table (only `signals` gets it for now)
- HELIOS tooltip work (was in v1 — defer to follow-up UX brief)

---

## Implementation

### Migration `migrations/013_outcome_source_phase_a.sql`

```sql
-- Phase A of outcome tracking unification.
-- Adds outcome_source column to signals, supporting view + diff-log stub.
-- See docs/codex-briefs/outcome-tracking-unification-2026-05-03-v2.md

-- 1. outcome_source column on signals
ALTER TABLE signals
    ADD COLUMN IF NOT EXISTS outcome_source VARCHAR(30);

-- Allowed values:
--   NULL                       — unresolved (no outcome yet)
--   BAR_WALK                   — resolver wrote this (yfinance forward bar walk)
--   ACTUAL_TRADE               — Ariadne wrote this (real position close)
--   COUNTERFACTUAL             — counterfactual analysis writer
--   EXPIRED                    — signal time-window elapsed (from signal_outcomes)
--   INVALIDATED                — signal contradicted before resolution (from signal_outcomes)
--   PROJECTED_FROM_BAR_WALK    — reserved for Phase C (signal_outcomes projection)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'outcome_source_valid' AND table_name = 'signals'
    ) THEN
        ALTER TABLE signals
            ADD CONSTRAINT outcome_source_valid CHECK (
                outcome_source IS NULL
                OR outcome_source IN (
                    'BAR_WALK',
                    'ACTUAL_TRADE',
                    'COUNTERFACTUAL',
                    'EXPIRED',
                    'INVALIDATED',
                    'PROJECTED_FROM_BAR_WALK'
                )
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_signals_outcome_source
    ON signals(outcome_source) WHERE outcome_source IS NOT NULL;

-- 2. signal_outcome_diff_log — stub for Phase C
CREATE TABLE IF NOT EXISTS signal_outcome_diff_log (
    id SERIAL PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES signals(signal_id),
    old_outcome VARCHAR,
    new_outcome VARCHAR,
    old_outcome_source VARCHAR(30),
    new_outcome_source VARCHAR(30),
    old_pnl_pct DOUBLE PRECISION,
    new_pnl_pct DOUBLE PRECISION,
    old_resolved_at TIMESTAMPTZ,
    new_resolved_at TIMESTAMPTZ,
    backfill_run_id TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_diff_log_run ON signal_outcome_diff_log(backfill_run_id);
CREATE INDEX IF NOT EXISTS idx_diff_log_signal ON signal_outcome_diff_log(signal_id);

-- 3. v_outcome_drift — bar-walk-only drift detection
-- Scoped to BAR_WALK and PROJECTED_FROM_BAR_WALK so we don't false-positive
-- on Ariadne (ACTUAL_TRADE legitimately disagrees with bar walk) or
-- counterfactual rows (different semantic entirely).
CREATE OR REPLACE VIEW v_outcome_drift AS
SELECT s.signal_id,
       s.outcome AS signals_outcome,
       s.outcome_source,
       so.outcome AS signal_outcomes_outcome,
       s.outcome_pnl_pct AS signals_pnl,
       so.max_favorable AS so_mfe,
       so.max_adverse AS so_mae,
       s.outcome_resolved_at AS signals_resolved_at,
       so.outcome_at AS signal_outcomes_resolved_at
FROM signals s
JOIN signal_outcomes so ON so.signal_id = s.signal_id
WHERE s.outcome IS NOT NULL
  AND so.outcome IS NOT NULL
  AND s.outcome_source IN ('BAR_WALK', 'PROJECTED_FROM_BAR_WALK')
  AND (
        (s.outcome = 'WIN'  AND so.outcome NOT IN ('HIT_T1','HIT_T2'))
     OR (s.outcome = 'LOSS' AND so.outcome != 'STOPPED_OUT')
  );
```

### Backfill `scripts/backfill_outcome_source.py`

Pure label-only backfill. Five `UPDATE … SET outcome_source = …` statements,
applied in priority order (counterfactual → actual_trade → bar_walk →
expired → invalidated). Each guards with `WHERE outcome_source IS NULL` so
re-running is idempotent.

```python
"""Phase A: backfill signals.outcome_source via writer-provenance heuristics.

Pure labeling — does NOT modify outcome, outcome_pnl_pct, or outcome_resolved_at.
Re-runs are idempotent (each step guards on outcome_source IS NULL).
"""
import asyncio
import sys
import os
import psycopg2

DB_URL = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DB_URL:
    sys.exit("FATAL: DATABASE_PUBLIC_URL/DATABASE_URL not set")


STEPS = [
    ("counterfactual", """
        UPDATE signals
        SET outcome_source = 'COUNTERFACTUAL'
        WHERE outcome IN ('COUNTERFACTUAL_WIN', 'COUNTERFACTUAL_LOSS')
          AND outcome_source IS NULL;
    """),
    ("actual_trade", """
        UPDATE signals s
        SET outcome_source = 'ACTUAL_TRADE'
        FROM unified_positions up
        WHERE up.signal_id = s.signal_id
          AND up.status IN ('CLOSED', 'EXPIRED')
          AND s.outcome IN ('WIN', 'LOSS')
          AND s.outcome_source IS NULL;
    """),
    ("bar_walk", """
        UPDATE signals
        SET outcome_source = 'BAR_WALK'
        WHERE outcome IN ('WIN', 'LOSS')
          AND outcome_source IS NULL;
    """),
    ("expired", """
        UPDATE signals s
        SET outcome_source = 'EXPIRED'
        FROM signal_outcomes so
        WHERE so.signal_id = s.signal_id
          AND so.outcome = 'EXPIRED'
          AND s.outcome IS NULL
          AND s.outcome_source IS NULL;
    """),
    ("invalidated", """
        UPDATE signals s
        SET outcome_source = 'INVALIDATED'
        FROM signal_outcomes so
        WHERE so.signal_id = s.signal_id
          AND so.outcome = 'INVALIDATED'
          AND s.outcome IS NULL
          AND s.outcome_source IS NULL;
    """),
]

DRY_RUN_SELECTS = [
    ("counterfactual", "SELECT COUNT(*) FROM signals WHERE outcome IN ('COUNTERFACTUAL_WIN','COUNTERFACTUAL_LOSS') AND outcome_source IS NULL"),
    ("actual_trade",   "SELECT COUNT(*) FROM signals s JOIN unified_positions up ON up.signal_id = s.signal_id WHERE up.status IN ('CLOSED','EXPIRED') AND s.outcome IN ('WIN','LOSS') AND s.outcome_source IS NULL"),
    ("bar_walk",       "SELECT COUNT(*) FROM signals WHERE outcome IN ('WIN','LOSS') AND outcome_source IS NULL"),
    ("expired",        "SELECT COUNT(*) FROM signals s JOIN signal_outcomes so ON so.signal_id = s.signal_id WHERE so.outcome = 'EXPIRED' AND s.outcome IS NULL AND s.outcome_source IS NULL"),
    ("invalidated",    "SELECT COUNT(*) FROM signals s JOIN signal_outcomes so ON so.signal_id = s.signal_id WHERE so.outcome = 'INVALIDATED' AND s.outcome IS NULL AND s.outcome_source IS NULL"),
]


def main(dry_run: bool):
    conn = psycopg2.connect(DB_URL, connect_timeout=10)
    cur = conn.cursor()

    if dry_run:
        print("DRY RUN — counts only, no writes")
        total = 0
        for label, sql in DRY_RUN_SELECTS:
            cur.execute(sql)
            n = cur.fetchone()[0]
            total += n
            print(f"  {label:15s} would tag {n:6d} rows")
        print(f"  ---")
        print(f"  TOTAL would tag {total:6d} rows")
        cur.close()
        conn.close()
        return

    for label, sql in STEPS:
        cur.execute(sql)
        n = cur.rowcount
        print(f"  {label:15s} tagged {n:6d} rows")
    conn.commit()

    # Final state
    cur.execute("""
        SELECT outcome_source, COUNT(*)
        FROM signals
        GROUP BY outcome_source
        ORDER BY 2 DESC NULLS LAST;
    """)
    print()
    print("Final outcome_source distribution:")
    for source, n in cur.fetchall():
        print(f"  {(source or 'NULL'):30s} {n}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    dry = "--apply" not in sys.argv
    main(dry)
```

**Run order:**
- `python scripts/backfill_outcome_source.py` → dry-run, prints expected counts
- `python scripts/backfill_outcome_source.py --apply` → applies labels

### Writer patches

#### Patch 1: `backend/jobs/outcome_resolver.py:163-169`

Add `outcome_source = 'BAR_WALK'` to the UPDATE.

```python
# BEFORE
await conn.execute("""
    UPDATE signals
    SET outcome = $1,
        outcome_pnl_pct = $2,
        outcome_resolved_at = $3
    WHERE signal_id = $4
""", outcome, pnl_pct, resolved_at, sig["signal_id"])

# AFTER
await conn.execute("""
    UPDATE signals
    SET outcome = $1,
        outcome_pnl_pct = $2,
        outcome_resolved_at = $3,
        outcome_source = 'BAR_WALK'
    WHERE signal_id = $4
""", outcome, pnl_pct, resolved_at, sig["signal_id"])
```

#### Patch 2: `backend/api/unified_positions.py:1365-1386` (Ariadne)

Add `outcome_source = 'ACTUAL_TRADE'` to the UPDATE. Note this is the
multi-column UPDATE that also writes `trade_outcome`, `actual_exit_price`,
`outcome_pnl_dollars`, `outcome_options_metrics`, `notes`. Add the new column
in the same SET clause.

```python
# BEFORE
await conn.execute("""
    UPDATE signals SET
        trade_outcome = $2,
        actual_exit_price = $3,
        outcome = $4,
        outcome_pnl_pct = $5,
        outcome_pnl_dollars = $6,
        outcome_resolved_at = $7,
        outcome_options_metrics = $8,
        notes = COALESCE(notes || ' | ', '') || $9
    WHERE signal_id = $1
""", signal_id, ...)

# AFTER (add outcome_source to the SET clause; no new param needed)
await conn.execute("""
    UPDATE signals SET
        trade_outcome = $2,
        actual_exit_price = $3,
        outcome = $4,
        outcome_pnl_pct = $5,
        outcome_pnl_dollars = $6,
        outcome_resolved_at = $7,
        outcome_options_metrics = $8,
        notes = COALESCE(notes || ' | ', '') || $9,
        outcome_source = 'ACTUAL_TRADE'
    WHERE signal_id = $1
""", signal_id, ...)
```

#### Patch 3: `backend/analytics/api.py:2517-2523` (counterfactual)

Add `outcome_source = 'COUNTERFACTUAL'` to the UPDATE.

```python
# BEFORE
await conn.execute("""
    UPDATE signals SET
        outcome = $2,
        outcome_pnl_pct = $3,
        outcome_resolved_at = NOW()
    WHERE signal_id = $1
""", row["signal_id"], outcome, round(pnl_pct, 2))

# AFTER
await conn.execute("""
    UPDATE signals SET
        outcome = $2,
        outcome_pnl_pct = $3,
        outcome_resolved_at = NOW(),
        outcome_source = 'COUNTERFACTUAL'
    WHERE signal_id = $1
""", row["signal_id"], outcome, round(pnl_pct, 2))
```

#### `score_signals.py` — no patch in Phase A

Writes to `signal_outcomes`, not `signals.outcome`. When Phase C projects
`signal_outcomes` → `signals.outcome`, those writes get tagged
`PROJECTED_FROM_BAR_WALK`. Phase A leaves it alone.

### `PROJECT_RULES.md` addition

New section after existing rules. Use this exact text or a close variant:

```markdown
## Outcome Tracking Semantics

`signals.outcome` carries three distinct meanings depending on which writer
produced it. The `signals.outcome_source` column (added 2026-05-03 via
migration 013) records the producer.

| outcome_source | Meaning | Writer |
|---|---|---|
| `BAR_WALK` | Hypothetical: "if you'd held to target/stop, what happened?" | `outcome_resolver.py` (yfinance forward bar walk) |
| `ACTUAL_TRADE` | Realized: "what did the trade actually return when closed?" | `unified_positions.py` Ariadne path |
| `COUNTERFACTUAL` | What-if: "if this dismissed signal hadn't been dismissed, what would have happened?" | `analytics/api.py` `/resolve-counterfactuals` endpoint |
| `EXPIRED` | Signal time-window elapsed without target or stop touch (label only; outcome stays NULL) | Phase A backfill from `signal_outcomes` |
| `INVALIDATED` | Signal was contradicted before resolution (label only; outcome stays NULL) | Phase A backfill from `signal_outcomes` |
| `PROJECTED_FROM_BAR_WALK` | Reserved for Phase C — `signal_outcomes`-projected values | (not yet used) |
| `NULL` | Unresolved | — |

**Query rules:**

1. **Strategy-vs-strategy comparisons (win-rate calibration, score-band tuning)**
   must use `signal_outcomes` directly, OR filter `signals` to
   `outcome_source = 'BAR_WALK'`. Mixing semantics (especially Ariadne
   actual-trade outcomes) corrupts the comparison.
2. **P&L reporting (real money)** should use `signals.outcome` filtered to
   `outcome_source = 'ACTUAL_TRADE'`, joined to `unified_positions` /
   `closed_positions` for full context.
3. **Counterfactual analysis** (what-if dashboards, missed-opportunity audits)
   should use `outcome_source = 'COUNTERFACTUAL'` exclusively.
4. **Drift detection** uses `v_outcome_drift` view, which is scoped to
   bar-walk semantics only.

**Known gap (Phase B):** the resolver's `outcome_resolved_at` is currently
populated from yfinance `bar_ts`, which can predate `signals.timestamp` for
~30-44% of resolver-written rows due to a bar-window edge case. **Do not rely
on `outcome_resolved_at` for time-series analysis until Phase B ships.** Use
`signal_outcomes.outcome_at` instead, which is correct.

**Phase C (deferred):** `signal_outcomes` → `signals.outcome*` value
projection backfill. Until Phase C ships, the existing 27% disagreement
between the two tables persists. Use the appropriate source per query rules
above; do not assume agreement.
```

---

## Test plan

### Pre-deploy on Railway branch DB

1. Create branch DB from prod
2. Apply migration 013 → confirm column exists, constraint installed, view + diff-log table created
3. Run backfill `--dry-run` → expect approximately:
   - counterfactual: 432 rows (228 + 204)
   - actual_trade: ~0 rows (Q1b confirmed zero `unified_positions` correlation in disputed cluster — full census may show small n)
   - bar_walk: ~593 rows (368 + 225 minus any actual_trade hits)
   - expired: depends on signal_outcomes coverage (≤1,436)
   - invalidated: ≤157
4. Run backfill `--apply`
5. Verify zero changes to `outcome`, `outcome_pnl_pct`, `outcome_resolved_at`:
   ```sql
   -- Snapshot before, then after, diff. Counts must match.
   SELECT COUNT(*) FROM signals WHERE outcome IS NOT NULL;
   SELECT outcome, COUNT(*) FROM signals WHERE outcome IS NOT NULL GROUP BY outcome;
   ```
6. Verify `v_outcome_drift` returns ~212 rows (after the `outcome_source IN
   ('BAR_WALK', 'PROJECTED_FROM_BAR_WALK')` filter is applied — counterfactuals
   are excluded). Breakdown from Q1a investigation:
   - WIN / STOPPED_OUT: 110
   - WIN / PENDING: 31
   - WIN / INVALIDATED: 2
   - LOSS / PENDING: 33
   - LOSS / HIT_T1: 10
   - LOSS / HIT_T2: 20
   - LOSS / INVALIDATED: 6
   - **Total: 212 rows**

   Phase C will reconcile these. Phase A only labels.
7. Deploy writer code change (resolver + Ariadne + counterfactual). Run one
   resolver pass; confirm new rows have `outcome_source = 'BAR_WALK'`.

### Production deploy

1. `git push origin main` → Railway auto-deploys migration 013 + writer code
2. Run backfill on prod: `railway run -s Postgres -- python3 scripts/backfill_outcome_source.py` (dry run)
3. **Nick reviews dry-run counts.** Approve or halt.
4. If approved: `railway run -s Postgres -- python3 scripts/backfill_outcome_source.py --apply`
5. Verify final distribution + zero value changes
6. Confirm next resolver tick (~15 min) tags new writes with `outcome_source = 'BAR_WALK'`

---

## Acceptance criteria

✅ Migration 013 applied to prod (`signals.outcome_source` column, `signal_outcome_diff_log` table, `v_outcome_drift` view)
✅ All three Python writers patched and tagging new writes
✅ Existing rows backfilled with `outcome_source` labels (label-only — verified by snapshot diff)
✅ `v_outcome_drift` view returns rows representing the existing disagreement (it should — Phase C is what cleans it up)
✅ **Zero changes to `outcome`, `outcome_pnl_pct`, `outcome_resolved_at` values** (this is the canonical assertion — Phase A is pure labeling)
✅ `PROJECT_RULES.md` updated with three-semantics + query rules + Phase B/C notes

---

## Rollback plan

Phase A is purely additive — fully reversible:

1. **Drop the column:**
   ```sql
   ALTER TABLE signals DROP CONSTRAINT IF EXISTS outcome_source_valid;
   DROP INDEX IF EXISTS idx_signals_outcome_source;
   ALTER TABLE signals DROP COLUMN IF EXISTS outcome_source;
   ```
2. **Drop the view + table:**
   ```sql
   DROP VIEW IF EXISTS v_outcome_drift;
   DROP TABLE IF EXISTS signal_outcome_diff_log;
   ```
3. **Revert writer code:** `git revert <phase-a-sha>` and re-push.

No data loss possible because Phase A doesn't modify any existing column values.

---

## Followup briefs (logged as TODO, NOT this brief)

1. **Phase B: `outcome_resolver.py` timestamp bug fix.** Root-cause the
   `bar_ts` backward-timestamp issue (yfinance start-window edge case suspected,
   confirm with debug-logged resolver run on a known-bad signal). Likely fix:
   set `outcome_resolved_at = NOW()` and use `bar_ts` only for an audit
   field if needed. Must ship before Phase C.
2. **Phase C: unification backfill projecting `signal_outcomes` → `signals.outcome*`.**
   For rows tagged `BAR_WALK`, project the canonical `signal_outcomes` outcome
   into `signals.outcome` using the mapping (`HIT_T1`/`HIT_T2` → `WIN`,
   `STOPPED_OUT` → `LOSS`). Tag the resulting rows `PROJECTED_FROM_BAR_WALK`.
   Use `signal_outcome_diff_log` to record every change with a backfill_run_id
   so reversal is one SQL statement.
3. **Re-run 3-10 Oscillator promotion audit** on `signal_outcomes` data
   directly (or `outcome_source = 'BAR_WALK'`), now that semantics are
   filterable. The original audit that surfaced this whole problem.
4. **Re-run Olympus Pass 9 v2 percentile threshold calibration** with
   `outcome_source = 'BAR_WALK'` filter applied. Original calibration may
   have been on contaminated mixed-semantic data.
5. **HELIOS tooltip on win/loss displays.** Was in v1 brief; defer to a
   followup UX brief — needs HELIOS team review to pick the right placement
   and copy.
6. **Audit other denormalization candidates:** `unified_positions` ↔
   `closed_positions`, `committee_data` JSONB cached fields. Same pattern,
   probably same problems.

---

## Notes for CC

- **Investigation-first principle still applies.** Even though Phase A is small,
  re-verify the writer enumeration on the current commit before patching —
  active work since 2026-04-22 (when v1's investigation queries last ran)
  could have added a new writer. A 1-line `grep -rE "UPDATE.*signals.*outcome"
  backend/` before each patch is cheap insurance.
- **The `actual_trade` heuristic is provisional.** Q1b found zero
  `unified_positions` correlation in the WIN/STOPPED_OUT cluster, suggesting
  Ariadne hasn't been writing many of these in production. The full backfill
  may tag few or zero rows as ACTUAL_TRADE. That's expected — going forward
  the writer patch ensures all NEW Ariadne writes are tagged correctly.
- **The 5% guardrail from v1 is dropped** — Phase A makes no value changes,
  so there's nothing to guard against. The dry-run output is informational.
- **`signal_outcomes` orphans** (141 rows with no matching `signals` row)
  are not addressed in Phase A. Phase C will need to decide: ignore, or
  emit a warning during projection?
- **All DB ops via `railway run -s Postgres -- python3 …`** for prod, or via
  asyncpg/psycopg2 with `DATABASE_PUBLIC_URL` env var (NOT `DATABASE_URL` —
  the latter uses Railway-internal hostname, unreachable from VPS).
