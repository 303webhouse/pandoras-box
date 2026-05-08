# CC Build Brief: Outcome Tracking Phase B — Resolver `bar_ts` Correctness Fix

**Authored:** 2026-05-08
**Status:** Investigation complete (mechanism empirically confirmed); ready for CC
**Priority:** P0 — unblocks 3-10 promotion re-audit re-run AND Olympus Pass 9 v2 percentile recalibration
**Predecessor:** Phase A shipped 2026-05-08 (commit `0750e44`, migration 013) — `outcome_source` enum + `signal_outcome_diff_log` + `v_outcome_drift` view
**Successor:** Phase C — `signal_outcomes` → `signals.outcome*` projection (separate brief; depends on Phase B)
**Estimated CC effort:** 4–6 hours (code fix + backfill script + verification)

---

## What changed since Phase A scoped this work

Phase A's brief framed Phase B as a **timestamp cosmetic issue** ("`bar_ts` from yfinance can predate `signals.timestamp`"). The 2026-05-08 3-10 promotion re-audit (`docs/strategy-reviews/raschke/3-10-promotion-reaudit-2026-05-08.md`) surfaced new evidence that reframed it as a **correctness bug**:

- `signals.outcome` (BAR_WALK source) and `signal_outcomes` agree on **only 28–39%** of WIN claims, but **~98%** of LOSS claims. Bias is one-sided — resolver inflates WINs.
- The single resolved 3-10-only signal that motivated promotion (`HG_NXTS_20260423_192057_3-10`) shows `signals.outcome = WIN +19.44%` against `signal_outcomes` MFE = 0.35%, MAE = 0.64%. The +19.44% is structurally impossible from post-signal price action.

The backward timestamp is not just a label problem; it is the **storage-layer footprint** of the same bar-window edge case that produces the phantom WINs. Fixing the timestamp without fixing the iteration would leave the phantom WINs in place. Phase B fixes both.

---

## Mechanism (empirically confirmed)

### Smoking gun: NXTS database state

| Field | Value |
|---|---|
| `signal_ts` | `2026-04-23 19:20:57.043 UTC` |
| `outcome_resolved_at` | `2026-04-23 19:00:00 UTC` ← **20 min before signal_ts** |
| `outcome` | `WIN` |
| `outcome_pnl_pct` | `19.44%` (= `(target − entry) / entry × 100` = `(6.02 − 5.04) / 5.04 × 100`) |
| `signal_outcomes.outcome` | `STOPPED_OUT` at $4.55, MFE = $0.35, MAE = $0.64 |

`outcome_resolved_at` matches a 15-min bar boundary (`19:00:00`) and is 20 minutes earlier than signal creation — proof the resolver wrote a yfinance `bar_ts` directly into `outcome_resolved_at` and that bar predated the signal.

### yfinance probe (today, AAPL, mid-bar test ts at `14:23:30 UTC`)

| `start=` parameter | First bar returned | Pre-signal? |
|---|---|---|
| `signal_ts - 15min` (current code) | `14:00:00` | **YES** |
| `signal_ts` exactly | `14:15:00` | **YES** |
| Next 15-min boundary (`14:30:00`) | `14:30:00` | no |

Removing the `-15min` from `start` is **not sufficient**. yfinance's bar boundaries are 15-min aligned regardless of the `start=` parameter; any signal_ts not on a boundary returns the bar that *contains* it (which is stamped at the bar's start, before `signal_ts`). The iteration loop has no `bar_ts < signal_ts` guard, so it matches on pre-signal price action and registers phantom hits.

### Three interacting bugs

| Bug | Location | Effect |
|---|---|---|
| **A — window** | `start=signal_ts - timedelta(minutes=15)` (line 56) | Deliberately reaches one extra bar earlier than necessary |
| **B — no filter** | `for bar_ts, bar in bars.iterrows():` (line 73), no guard | Iterates the bar-aligned bar that contains `signal_ts`, whose timestamp is before `signal_ts` |
| **C — timestamp** | `outcome_resolved_at = bar_ts` (line 165, via `resolved_at` param) | Records bar boundary instead of resolution wall-clock; literally stores Bug B's footprint |

Bug B is the dominant cause of phantom WINs. Bug A amplifies it. Bug C is the audit trail.

### Investigation script (committed for reproducibility)

`scripts/strategy-reviews/phase-b-mechanism-check.py` — pulls NXTS row, fetches yfinance bars exactly as the resolver does, walks the iteration to identify the pre-signal bar that matched. Re-runs idempotently from `DATABASE_PUBLIC_URL`.

---

## Phase B goal

1. **Fix `_walk_bars`** to never iterate bars stamped before `signal_ts`.
2. **Fix `resolve_signal_outcomes`** to write `outcome_resolved_at = NOW()` instead of the matched bar's timestamp.
3. **Backfill** every existing `outcome_source = 'BAR_WALK'` row by re-running corrected logic, with full diff capture in `signal_outcome_diff_log`.
4. **Empirical acceptance:** WIN-claim agreement with `signal_outcomes` ≥ 95% (currently 28–39%); zero BAR_WALK rows with `outcome_resolved_at < signals.timestamp`.

This unblocks:
- 3-10 Oscillator promotion re-audit re-run (was gated on Phase B + sample size).
- Olympus Pass 9 v2 percentile-threshold recalibration (gated on clean BAR_WALK data).
- Phase C (projection of `signal_outcomes` → `signals.outcome*` for BAR_WALK rows) is now safe to author.

---

## Scope

### In scope

1. Patch `backend/jobs/outcome_resolver.py`:
   - `_walk_bars`: tighten `start=` and add `bar_ts < signal_ts: continue` guard at top of loop.
   - `resolve_signal_outcomes`: write `outcome_resolved_at = NOW()` in the UPDATE; matched bar_ts retained only for logging.
2. New script `scripts/backfill_resolver_outcomes_phase_b.py`:
   - Re-resolves every `outcome_source = 'BAR_WALK'` row using the patched `_walk_bars`.
   - Writes diff entries to `signal_outcome_diff_log` keyed by a single `backfill_run_id`.
   - `--dry-run` (default) prints transition histogram; `--apply` performs writes in a single transaction.
3. Test fixture `tests/test_outcome_resolver_phase_b.py`:
   - Synthetic bar DataFrame with deliberate pre-signal and post-signal bars.
   - Verifies the loop filter excludes the pre-signal bar and matches only post-signal bars.
4. Update `PROJECT_RULES.md` "Outcome Tracking Semantics" section: replace the Phase-B "Known gap" paragraph with a "Phase B shipped" note linking this brief and the migration backfill_run_id.
5. Move investigation scripts into the repo at `scripts/strategy-reviews/`:
   - `phase-b-mechanism-check.py`
   - `clean_audit_3_10.py` (referenced in 5/8 audit appendix)
   - `stress_test_3_10.py` (referenced in 5/8 audit appendix)

### Out of scope

- **Phase C** — `signal_outcomes` → `signals.outcome*` projection (separate brief, depends on Phase B landing cleanly).
- **3-10 promotion re-audit re-run** — separate work, runs after Phase C.
- **Olympus Pass 9 v2 recalibration** — separate work, runs after Phase C.
- **Optional `outcome_match_bar_ts` audit column** — Titans recommended deferring; not required for correctness. If forensics matter later, one-line `ALTER TABLE` follow-up.
- **Modifying `signal_outcomes` or `score_signals.py`** — that's the canonical comparison standard, not the broken thing. Leave it alone.
- **Pausing the resolver during backfill** — not needed: row-level disjointness (resolver writes `WHERE outcome IS NULL`; backfill writes `WHERE outcome_source = 'BAR_WALK' AND outcome IS NOT NULL`) plus running backfill outside market hours is sufficient.

---

## Implementation

### Patch 1: `backend/jobs/outcome_resolver.py` — `_walk_bars` start parameter

**Find (exact):**

```python
    try:
        bars = yf.download(
            ticker,
            start=signal_ts - timedelta(minutes=15),  # include the signal bar
            interval=interval,
            progress=False,
            auto_adjust=False,
            prepost=False,
        )
```

**Replace with:**

```python
    try:
        # Phase B: do not subtract 15min — would deliberately reach pre-signal bars.
        # Note: yfinance still returns the bar-aligned bar that *contains* signal_ts
        # (whose bar_ts is before signal_ts), so the loop below has an explicit
        # bar_ts < signal_ts guard. See docs/codex-briefs/outcome-tracking-phase-b-resolver-fix-2026-05-08.md
        bars = yf.download(
            ticker,
            start=signal_ts,
            interval=interval,
            progress=False,
            auto_adjust=False,
            prepost=False,
        )
```

### Patch 2: `backend/jobs/outcome_resolver.py` — pre-signal bar filter

**Find (exact):**

```python
    for bar_ts, bar in bars.iterrows():
        try:
            high = float(bar["High"])
            low = float(bar["Low"])
        except (KeyError, ValueError, TypeError):
            continue

        if direction == "LONG":
```

**Replace with:**

```python
    for bar_ts, bar in bars.iterrows():
        try:
            high = float(bar["High"])
            low = float(bar["Low"])
        except (KeyError, ValueError, TypeError):
            continue

        # Phase B: skip bars stamped before signal creation. yfinance's bar-aligned
        # start parameter cannot prevent the bar containing signal_ts (which is
        # timestamped at the bar's start, before signal_ts) from being returned.
        # Without this guard the resolver matches on pre-signal price action and
        # registers phantom WINs.
        try:
            if hasattr(bar_ts, "tz_convert"):
                bar_ts_utc = (
                    bar_ts.tz_convert("UTC")
                    if getattr(bar_ts, "tzinfo", None) is not None
                    else bar_ts.tz_localize("UTC")
                )
            else:
                bar_ts_utc = (
                    bar_ts
                    if getattr(bar_ts, "tzinfo", None) is not None
                    else bar_ts.replace(tzinfo=timezone.utc)
                )
        except Exception:
            bar_ts_utc = bar_ts
        if bar_ts_utc < signal_ts:
            continue

        if direction == "LONG":
```

### Patch 3: `backend/jobs/outcome_resolver.py` — UPDATE `outcome_resolved_at = NOW()`

**Find (exact):**

```python
        if outcome:
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE signals
                    SET outcome = $1,
                        outcome_pnl_pct = $2,
                        outcome_resolved_at = $3,
                        outcome_source = 'BAR_WALK'
                    WHERE signal_id = $4
                """, outcome, pnl_pct, resolved_at, sig["signal_id"])
            logger.info(
                "Resolved %s %s %s: %s (%.2f%%) at %s",
                ticker, direction, sig["signal_id"], outcome, pnl_pct or 0, resolved_at,
            )
```

**Replace with:**

```python
        if outcome:
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE signals
                    SET outcome = $1,
                        outcome_pnl_pct = $2,
                        outcome_resolved_at = NOW(),
                        outcome_source = 'BAR_WALK'
                    WHERE signal_id = $3
                """, outcome, pnl_pct, sig["signal_id"])
            logger.info(
                "Resolved %s %s %s: %s (%.2f%%) — matched bar at %s",
                ticker, direction, sig["signal_id"], outcome, pnl_pct or 0, resolved_at,
            )
```

The matched bar's timestamp (`resolved_at` returned from `_walk_bars`) is now used **only for the log line**, not stored in DB. `outcome_resolved_at` becomes wall-clock resolution time — semantically what the column name implies.

### Patch 4: `tests/test_outcome_resolver_phase_b.py` (new file)

```python
"""Phase B regression test — pre-signal bar filter in _walk_bars."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd
import pytest

from backend.jobs.outcome_resolver import _walk_bars


def _make_bars(rows):
    """rows: list of (bar_ts_iso, high, low). Returns DataFrame indexed by ts."""
    idx = pd.DatetimeIndex([pd.Timestamp(ts, tz="UTC") for ts, _, _ in rows])
    return pd.DataFrame(
        {"High": [h for _, h, _ in rows], "Low": [l for _, _, l in rows]},
        index=idx,
    )


def test_pre_signal_bar_does_not_match_target():
    """Pre-signal bar high above target must NOT register a WIN."""
    signal_ts = datetime(2026, 4, 23, 19, 20, 57, tzinfo=timezone.utc)
    bars = _make_bars([
        ("2026-04-23T19:00:00+00:00", 6.50, 5.00),  # PRE-SIGNAL: high above target
        ("2026-04-23T19:30:00+00:00", 5.05, 4.95),  # post-signal: no touch
    ])
    with patch("yfinance.download", return_value=bars):
        outcome, pnl, _ = _walk_bars("TEST", "LONG", 5.04, 6.02, 4.55, signal_ts)
    assert outcome is None, "Resolver matched on pre-signal bar (Phase B regression)"


def test_post_signal_bar_matches_correctly():
    """Post-signal bar that hits target must register WIN."""
    signal_ts = datetime(2026, 4, 23, 19, 20, 57, tzinfo=timezone.utc)
    bars = _make_bars([
        ("2026-04-23T19:00:00+00:00", 5.00, 5.00),  # PRE-SIGNAL: ignored
        ("2026-04-23T19:30:00+00:00", 6.10, 5.05),  # post-signal: HIGH ≥ target
    ])
    with patch("yfinance.download", return_value=bars):
        outcome, pnl, ts = _walk_bars("TEST", "LONG", 5.04, 6.02, 4.55, signal_ts)
    assert outcome == "WIN"
    assert abs(pnl - 19.44) < 0.01


def test_post_signal_stop_hit_returns_loss():
    signal_ts = datetime(2026, 4, 23, 19, 20, 57, tzinfo=timezone.utc)
    bars = _make_bars([
        ("2026-04-23T19:30:00+00:00", 5.05, 4.50),  # post-signal: LOW ≤ stop
    ])
    with patch("yfinance.download", return_value=bars):
        outcome, pnl, _ = _walk_bars("TEST", "LONG", 5.04, 6.02, 4.55, signal_ts)
    assert outcome == "LOSS"


def test_same_bar_target_and_stop_is_conservative_loss():
    signal_ts = datetime(2026, 4, 23, 19, 20, 57, tzinfo=timezone.utc)
    bars = _make_bars([
        ("2026-04-23T19:30:00+00:00", 6.10, 4.50),  # both hit in one bar
    ])
    with patch("yfinance.download", return_value=bars):
        outcome, _, _ = _walk_bars("TEST", "LONG", 5.04, 6.02, 4.55, signal_ts)
    assert outcome == "LOSS", "Same-bar target+stop must be conservative LOSS"


def test_short_direction_pre_signal_bar_does_not_match():
    signal_ts = datetime(2026, 4, 23, 19, 20, 57, tzinfo=timezone.utc)
    bars = _make_bars([
        ("2026-04-23T19:00:00+00:00", 5.00, 4.00),  # PRE-SIGNAL: low below target
        ("2026-04-23T19:30:00+00:00", 5.05, 4.95),  # post-signal: no touch
    ])
    with patch("yfinance.download", return_value=bars):
        outcome, _, _ = _walk_bars("TEST", "SHORT", 5.04, 4.20, 5.50, signal_ts)
    assert outcome is None
```

### Patch 5: `scripts/backfill_resolver_outcomes_phase_b.py` (new file)

```python
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
```

### Patch 6: `PROJECT_RULES.md` — replace Phase-B "Known gap" paragraph

**Find (exact):**

```markdown
**Known gap (Phase B):** the resolver's `outcome_resolved_at` is currently
populated from yfinance `bar_ts`, which can predate `signals.timestamp` for
~30-44% of resolver-written rows due to a bar-window edge case. **Do not rely
on `outcome_resolved_at` for time-series analysis until Phase B ships.** Use
`signal_outcomes.outcome_at` instead, which is correct.
```

**Replace with:**

```markdown
**Phase B (shipped 2026-05-08):** resolver `outcome_resolved_at` is now
wall-clock `NOW()` at write time (no longer derived from yfinance `bar_ts`),
and the bar-walk loop now skips bars stamped before `signal_ts`. All
existing BAR_WALK rows have been backfilled on corrected logic (see
`signal_outcome_diff_log` for the full diff, keyed by backfill_run_id).
Brief: `docs/codex-briefs/outcome-tracking-phase-b-resolver-fix-2026-05-08.md`.
```

### Patch 7: Move investigation scripts into the repo

```
mkdir -p scripts/strategy-reviews
cp C:\temp\phase_b_mechanism_check.py scripts/strategy-reviews/phase-b-mechanism-check.py
cp C:\temp\clean_audit_3_10.py        scripts/strategy-reviews/clean-audit-3-10-2026-05-08.py
cp C:\temp\stress_test_3_10.py        scripts/strategy-reviews/stress-test-3-10-2026-05-08.py
```

DSN at top of each script must be replaced with `os.environ.get("DATABASE_PUBLIC_URL")` before commit (do not commit prod credentials). Each script should fail fast with the same `sys.exit("FATAL: ...")` pattern as the backfill script if the env var is missing.

---

## Test plan

### Pre-deploy (local)

1. Run `pytest tests/test_outcome_resolver_phase_b.py -v` — all 5 tests pass.
2. Sanity-check the live resolver still imports cleanly: `python -c "from backend.jobs.outcome_resolver import _walk_bars, resolve_signal_outcomes"`.

### Step 1: Ship code fix

```
git add backend/jobs/outcome_resolver.py tests/test_outcome_resolver_phase_b.py \
        scripts/backfill_resolver_outcomes_phase_b.py \
        scripts/strategy-reviews/ PROJECT_RULES.md \
        docs/codex-briefs/outcome-tracking-phase-b-resolver-fix-2026-05-08.md
git commit -m "Phase B: resolver bar_ts correctness fix + backfill script"
git push origin main
```

### Step 2: Deployment verification (per `PROJECT_RULES.md`)

1. `railway deployment list -s backend` → most recent must be `SUCCESS`.
2. Confirm deploy SHA matches the commit just pushed.
3. **Empirical verification** — wait one resolver tick (~15 min during market hours), then run:

   ```sql
   -- Count NEW BAR_WALK writes since deploy. Expect zero with backward timestamps.
   SELECT COUNT(*) AS new_writes,
          COUNT(*) FILTER (WHERE outcome_resolved_at < timestamp) AS backward_ts_count
   FROM signals
   WHERE outcome_source = 'BAR_WALK'
     AND outcome_resolved_at > NOW() - INTERVAL '20 minutes';
   ```

   Expected: `backward_ts_count = 0`. If any `> 0` after deploy, **STOP** — patch did not deploy correctly; re-investigate before backfill.

### Step 3: Backfill (post-4 PM ET weekday or any weekend)

1. Dry-run:

   ```
   railway run -s Postgres -- python3 scripts/backfill_resolver_outcomes_phase_b.py
   ```

   Output prints transition histogram. **Expected pattern** (high-confidence prediction based on 5/8 audit data):
   - `WIN -> unchanged`: small (~30–40% of original WINs that were genuine)
   - `WIN -> LOSS`: large (the phantom WINs that were really stops)
   - `WIN -> NULL` (unresolved on corrected logic, no real touch yet): some
   - `LOSS -> unchanged`: dominant (~98% of LOSS rows agree pre/post per audit)
   - `LOSS -> WIN`: very rare or zero
   - `LOSS -> NULL`: rare

2. **Nick reviews dry-run output. Approve or halt.**
3. If approved:

   ```
   railway run -s Postgres -- python3 scripts/backfill_resolver_outcomes_phase_b.py --apply
   ```

4. Confirm transaction commit; record `backfill_run_id` for rollback handle.

### Step 4: Acceptance verification

```sql
-- A. WIN-claim agreement with signal_outcomes (the headline metric)
WITH bar_walk_wins AS (
    SELECT s.signal_id, so.outcome AS so_outcome
    FROM signals s
    JOIN signal_outcomes so ON so.signal_id = s.signal_id
    WHERE s.outcome_source = 'BAR_WALK'
      AND s.outcome = 'WIN'
)
SELECT COUNT(*) AS total_wins,
       COUNT(*) FILTER (WHERE so_outcome IN ('HIT_T1', 'HIT_T2')) AS agreeing_wins,
       ROUND(100.0 * COUNT(*) FILTER (WHERE so_outcome IN ('HIT_T1', 'HIT_T2'))
             / NULLIF(COUNT(*), 0), 1) AS agreement_pct
FROM bar_walk_wins;
```
**Pass criterion:** `agreement_pct >= 95`.

```sql
-- B. Zero backward timestamps among BAR_WALK rows
SELECT COUNT(*) AS backward_ts_count
FROM signals
WHERE outcome_source = 'BAR_WALK'
  AND outcome_resolved_at < timestamp;
```
**Pass criterion:** `backward_ts_count = 0`.

```sql
-- C. v_outcome_drift dropoff (bar-walk-only disagreement view from Phase A)
SELECT COUNT(*) AS drift_rows FROM v_outcome_drift;
```
**Pass criterion:** drift_rows materially lower than the 212 rows Phase A reported. (Not zero — `signal_outcomes` itself may have its own behavior; we only require WIN-claim parity ≥ 95%, not perfect outcome parity. Phase C is what reconciles values.)

```sql
-- D. NXTS smoking-gun row specifically
SELECT signal_id, outcome, outcome_pnl_pct, outcome_resolved_at, timestamp
FROM signals
WHERE signal_id = 'HG_NXTS_20260423_192057_3-10';
```
**Pass criterion:** outcome is no longer `WIN +19.44%`. Either `LOSS` (matches `signal_outcomes.STOPPED_OUT` if yfinance still shows the stop touch) or `NULL`/unresolved (if today's yfinance no longer shows a touch). Either is correct.

---

## Acceptance criteria (consolidated)

- ✅ All 5 tests in `tests/test_outcome_resolver_phase_b.py` pass.
- ✅ Railway deployment confirmed SUCCESS, SHA matches pushed commit.
- ✅ One post-deploy resolver tick observed; **no new BAR_WALK row** has `outcome_resolved_at < timestamp`.
- ✅ Backfill executed; `backfill_run_id` recorded; transaction committed.
- ✅ **WIN-claim agreement with `signal_outcomes` ≥ 95%** (was 28–39% per 5/8 audit).
- ✅ **Zero BAR_WALK rows** with `outcome_resolved_at < timestamp`.
- ✅ NXTS row (`HG_NXTS_20260423_192057_3-10`) is no longer WIN +19.44%.
- ✅ `PROJECT_RULES.md` "Outcome Tracking Semantics" updated to reflect Phase B shipped.

---

## Rollback plan

Phase B's code patch is reversible by `git revert`. The backfill is reversible from `signal_outcome_diff_log`:

```sql
-- Replay original outcomes from diff log, keyed by backfill_run_id.
-- Replace 'phase_b_YYYYMMDD_HHMMSS_xxxxxxxx' with the actual run id.
BEGIN;

UPDATE signals s
SET outcome = d.old_outcome,
    outcome_pnl_pct = d.old_pnl_pct,
    outcome_resolved_at = d.old_resolved_at
FROM signal_outcome_diff_log d
WHERE d.signal_id = s.signal_id
  AND d.backfill_run_id = 'phase_b_YYYYMMDD_HHMMSS_xxxxxxxx';

-- Verify count matches diff_log entry count for that run before COMMIT
SELECT COUNT(*) FROM signal_outcome_diff_log
WHERE backfill_run_id = 'phase_b_YYYYMMDD_HHMMSS_xxxxxxxx';

COMMIT;  -- or ROLLBACK if count mismatch
```

If post-rollback the resolver code is also reverted, `git revert` the Phase B commit on `main` and let Railway redeploy.

---

## yfinance non-determinism note (read this)

yfinance data shifts over time. The NXTS investigation showed today's yfinance no longer reproduces the original WIN match — current data shows a clean LOSS at the stop. This is a feature, not a bug, of the backfill: **we want corrected logic running on today's (more correct) yfinance data**, not a faithful reproduction of original buggy outcomes.

Consequences:
- Some original WINs become LOSSES on backfill (phantom WINs, now correctly stopped).
- Some original WINs become NULL on backfill (no real touch yet on today's data).
- Some original LOSSES might become NULL or WIN if yfinance corrected adverse data, but the audit shows ~98% LOSS-side agreement, so this should be rare.

The acceptance test is **agreement with `signal_outcomes`**, not reproduction. `signal_outcomes` is itself running on yfinance (via `score_signals.py` daily-bar walk) and is already the canonical source per Phase A. Aligning to it is the goal.

---

## Notes for CC

- **Read PROJECT_RULES.md before patching.** "Outcome Tracking Semantics" section is the contract; do not modify the three-semantics table or query rules during this brief — only the "Known gap" paragraph (Patch 6).
- **Do not modify `score_signals.py` or `signal_outcomes` table.** That is the comparison standard, not the broken thing. Out of scope.
- **Do not add new outcome columns** (e.g., `outcome_match_bar_ts`). Titans deliberately deferred this.
- **Sequencing matters.** Code patches → deploy → verify resolver tick is clean → backfill. Do **not** run backfill before confirming deploy. Failure mode: backfill produces "correct" values, but live resolver still writes buggy ones for any newly-eligible signals during the gap.
- **Backfill mid-day on a weekday is acceptable** (no row-level race) but **not recommended** — run it post-4 PM ET or weekend so resolver is naturally idle.
- **Empty-safe env vars per PROJECT_RULES dev principle 6.** Backfill script uses `os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")` — already correct in the implementation above.
- **Investigation scripts being committed (Patch 7)** must have their hardcoded DSN stripped and replaced with env-var lookup before commit. Do not commit production credentials.
- **The Holy Grail signal name format** in NXTS is `HG_<TICKER>_<YYYYMMDD>_<HHMMSS>_<gate_type>`. The audit references this format; Patch 4 test fixture and Patch 5 backfill iterate by signal_id without parsing it, so format changes downstream are not a risk.
- **Run `pytest` once before commit** to confirm the test fixture works against your local yfinance (no network call should happen — the test mocks `yfinance.download`). If pytest fails on import resolution for `from backend.jobs.outcome_resolver import _walk_bars`, ensure the test invocation runs from the repo root or adjust the import path.
