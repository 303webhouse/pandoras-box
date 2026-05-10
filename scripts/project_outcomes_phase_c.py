"""Phase C: project signal_outcomes (canonical bar-walk truth) onto
signals.outcome* with outcome_source = 'PROJECTED_FROM_BAR_WALK'.

Hard guard: never overwrites rows where signals.outcome_source IN
('ACTUAL_TRADE', 'COUNTERFACTUAL'). These have non-bar-walk semantics.

Mapping (Gate 5 sign-off, 2026-05-09):
  STOPPED_OUT  → signals.outcome = 'LOSS',  outcome_source = 'PROJECTED_FROM_BAR_WALK'
  HIT_T1       → signals.outcome = 'WIN',   outcome_source = 'PROJECTED_FROM_BAR_WALK'
  HIT_T2       → signals.outcome = 'WIN',   outcome_source = 'PROJECTED_FROM_BAR_WALK'
  EXPIRED      → outcome stays NULL,        outcome_source = 'EXPIRED' (label only)
  INVALIDATED  → outcome stays NULL,        outcome_source = 'INVALIDATED' (label only)
  PENDING      → skipped (still walking)

PnL formula (Gate 5 Q&A: target_1 always, never target_2 — keeps pnl_pct
apples-to-apples with resolver semantics):
  LONG  WIN  : (target_1 - entry) / entry * 100
  LONG  LOSS : (stop_loss - entry) / entry * 100
  SHORT WIN  : (entry - target_1) / entry * 100
  SHORT LOSS : (entry - stop_loss) / entry * 100

Granularity reconciliation:
  When signals.outcome_source = 'BAR_WALK' (15m resolver wrote it directly)
  and signal_outcomes disagrees, the canonical-walker policy decides:
    - daily canonical (default for all current production strategies): daily
      walker (signal_outcomes) wins; signals row gets re-projected to
      PROJECTED_FROM_BAR_WALK with daily verdict. Diff logged with
      reason='granularity_reconciliation'.
    - 15m canonical: signals (BAR_WALK) keeps its value. Diff logged with
      reason='granularity_reconciliation' note that 15m won.

INVALIDATED override (Gate 3 carve-out):
  IF signals.outcome_source = 'BAR_WALK'
  AND signal_outcomes.outcome = 'INVALIDATED'
  AND (so.max_adverse crossed stop_loss OR so.max_favorable crossed target_1)
  → keep signals.outcome (BAR_WALK price-based verdict wins)
  → diff logged with reason='granularity_reconciliation_invalidated_override'
  Rationale: 15m saw a real price-level cross that score_signals' INVALIDATED
  contradiction logic missed. Distinct reason makes these queryable for
  later score_signals tuning.

Orphans:
  signal_outcomes rows with no matching signals row (Phase A flagged 141)
  are written to <tmpdir>/phase-c-orphans.jsonl, never projected.

Usage:
  python scripts/project_outcomes_phase_c.py            # dry-run
  python scripts/project_outcomes_phase_c.py --apply    # writes (single tx)

See docs/codex-briefs/outcome-tracking-phase-c-projection-2026-05-09.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

DB_URL = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DB_URL:
    sys.exit("FATAL: DATABASE_PUBLIC_URL/DATABASE_URL not set")

ORPHAN_REPORT_PATH = Path(tempfile.gettempdir()) / "phase-c-orphans.jsonl"

# Strategies whose canonical walker is the 15-minute resolver. Empty by
# default per Gate 5 sign-off — all current production strategies are
# swing-class (Holy_Grail, sell_the_rip, Artemis, CTA Scanner, etc.) and
# default to daily canonical. Add explicit names here if/when 15m-canonical
# scalp strategies appear.
_15M_CANONICAL_STRATEGIES: set[str] = set()


def canonical_walker(strategy: str | None) -> str:
    """Return '15m' or 'daily'."""
    if strategy and strategy in _15M_CANONICAL_STRATEGIES:
        return "15m"
    return "daily"


def map_outcome(so_outcome: str) -> str | None:
    """signal_outcomes.outcome → signals.outcome value (None means label only / skip)."""
    if so_outcome in ("HIT_T1", "HIT_T2"):
        return "WIN"
    if so_outcome == "STOPPED_OUT":
        return "LOSS"
    return None  # EXPIRED, INVALIDATED, PENDING


def map_outcome_source(so_outcome: str) -> str | None:
    """signal_outcomes.outcome → signals.outcome_source value."""
    if so_outcome in ("HIT_T1", "HIT_T2", "STOPPED_OUT"):
        return "PROJECTED_FROM_BAR_WALK"
    if so_outcome == "EXPIRED":
        return "EXPIRED"
    if so_outcome == "INVALIDATED":
        return "INVALIDATED"
    return None  # PENDING


def compute_pnl_pct(direction: str, mapped_outcome: str | None,
                    entry: float | None, target_1: float | None,
                    stop_loss: float | None) -> float | None:
    if mapped_outcome is None or entry is None or entry == 0:
        return None
    direction = (direction or "").upper()
    if mapped_outcome == "WIN" and target_1 is not None:
        if direction == "LONG":
            return (target_1 - entry) / entry * 100
        if direction == "SHORT":
            return (entry - target_1) / entry * 100
    if mapped_outcome == "LOSS" and stop_loss is not None:
        if direction == "LONG":
            return (stop_loss - entry) / entry * 100
        if direction == "SHORT":
            return (entry - stop_loss) / entry * 100
    return None


def invalidated_override_applies(direction: str, entry: float | None,
                                  stop_loss: float | None, target_1: float | None,
                                  max_adverse: float | None,
                                  max_favorable: float | None) -> bool:
    """Returns True if price actually crossed stop or target despite the
    INVALIDATED verdict. max_adverse/max_favorable are stored as POSITIVE
    distances from entry (per score_signals.py convention).
    """
    direction = (direction or "").upper()
    if entry is None or direction not in ("LONG", "SHORT"):
        return False
    if max_adverse is not None and stop_loss is not None:
        # Stop crossed?
        stop_distance = abs(entry - stop_loss)
        if max_adverse >= stop_distance:
            return True
    if max_favorable is not None and target_1 is not None:
        # Target crossed?
        target_distance = abs(target_1 - entry)
        if max_favorable >= target_distance:
            return True
    return False


def fetch_join_rows(cur):
    """Pull every signal_outcomes row that's eligible for projection
    (terminal verdicts only — PENDING is never projected) along with its
    matching signals row. LEFT JOIN so orphans are visible.
    """
    cur.execute("""
        SELECT
          so.signal_id,
          so.outcome           AS so_outcome,
          so.outcome_at        AS so_outcome_at,
          so.max_favorable,
          so.max_adverse,
          s.signal_id          AS signals_signal_id,
          s.outcome            AS signals_outcome,
          s.outcome_pnl_pct    AS signals_pnl_pct,
          s.outcome_resolved_at,
          s.outcome_source,
          s.entry_price,
          s.target_1,
          s.stop_loss,
          s.direction,
          s.strategy
        FROM signal_outcomes so
        LEFT JOIN signals s USING (signal_id)
        WHERE so.outcome IS NOT NULL
          AND so.outcome != 'PENDING'
        ORDER BY so.outcome_at DESC NULLS LAST
    """)
    return cur.fetchall()


def main():
    ap = argparse.ArgumentParser(description="Phase C projection")
    ap.add_argument("--apply", action="store_true",
                    help="Apply changes in one transaction (default: dry-run)")
    ap.add_argument("--orphan-report", type=str, default=str(ORPHAN_REPORT_PATH))
    args = ap.parse_args()

    apply_mode = args.apply
    run_id = f"phase_c_proj_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    orphan_path = Path(args.orphan_report)

    print(f"run_id        = {run_id}")
    print(f"mode          = {'APPLY (single tx)' if apply_mode else 'DRY RUN (no writes)'}")
    print(f"orphan report = {orphan_path}")
    print()

    conn = psycopg2.connect(DB_URL, connect_timeout=15)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    rows = fetch_join_rows(cur)
    total = len(rows)
    print(f"loaded {total} signal_outcomes rows (terminal, non-PENDING)")
    print()

    counters = Counter()
    write_actions: list[dict] = []
    orphan_records: list[dict] = []

    for row in rows:
        # Orphan check
        if row["signals_signal_id"] is None:
            counters["orphan"] += 1
            orphan_records.append({
                "signal_id": row["signal_id"],
                "so_outcome": row["so_outcome"],
                "so_outcome_at": str(row["so_outcome_at"]),
            })
            continue

        # Hard guard: protected sources
        if row["outcome_source"] in ("ACTUAL_TRADE", "COUNTERFACTUAL"):
            counters[f"protected_{row['outcome_source'].lower()}"] += 1
            continue

        mapped_outcome = map_outcome(row["so_outcome"])  # 'WIN' | 'LOSS' | None
        mapped_source = map_outcome_source(row["so_outcome"])  # tag

        entry = float(row["entry_price"]) if row["entry_price"] is not None else None
        t1 = float(row["target_1"]) if row["target_1"] is not None else None
        stop = float(row["stop_loss"]) if row["stop_loss"] is not None else None
        new_pnl = compute_pnl_pct(row["direction"], mapped_outcome, entry, t1, stop)
        new_resolved_at = row["so_outcome_at"]

        cur_outcome = row["signals_outcome"]
        cur_source = row["outcome_source"]
        cur_pnl = float(row["signals_pnl_pct"]) if row["signals_pnl_pct"] is not None else None
        cur_resolved_at = row["outcome_resolved_at"]

        # Decide write action by current state
        action = None
        reason = None
        new_outcome_to_write = mapped_outcome
        new_source_to_write = mapped_source
        new_pnl_to_write = new_pnl
        new_resolved_to_write = new_resolved_at

        if cur_source is None:
            # Case A: initial projection
            action = "write"
            reason = "projection_initial"
            counters["projection_initial"] += 1

        elif cur_source == "BAR_WALK":
            # Case B: resolver wrote first; check agreement
            if cur_outcome == mapped_outcome and mapped_outcome is not None:
                # Agree on terminal verdict — just refresh timestamp/pnl if drifted
                action = None
                counters["barwalk_agree"] += 1
            else:
                # Disagreement
                if row["so_outcome"] == "INVALIDATED" and cur_outcome in ("WIN", "LOSS"):
                    # INVALIDATED override check
                    max_adv = float(row["max_adverse"]) if row["max_adverse"] is not None else None
                    max_fav = float(row["max_favorable"]) if row["max_favorable"] is not None else None
                    if invalidated_override_applies(row["direction"], entry, stop, t1, max_adv, max_fav):
                        # Keep BAR_WALK; log override
                        action = "log_only"
                        reason = "granularity_reconciliation_invalidated_override"
                        counters["invalidated_override_applied"] += 1
                    else:
                        # No override — reconcile to label-only INVALIDATED
                        action = "write"
                        reason = "granularity_reconciliation"
                        new_outcome_to_write = None
                        new_source_to_write = "INVALIDATED"
                        new_pnl_to_write = None
                        new_resolved_to_write = None
                        counters["invalidated_no_override_reconcile"] += 1
                else:
                    # Standard granularity disagreement
                    walker = canonical_walker(row["strategy"])
                    if walker == "daily":
                        # Daily wins — overwrite signals
                        action = "write"
                        reason = "granularity_reconciliation"
                        counters["granularity_reconcile_daily_wins"] += 1
                    else:
                        # 15m wins — keep BAR_WALK
                        action = "log_only"
                        reason = "granularity_reconciliation"
                        counters["granularity_reconcile_15m_wins"] += 1

        elif cur_source == "PROJECTED_FROM_BAR_WALK":
            # Case C: already projected — refresh if values changed (re-walk drift)
            values_changed = (
                cur_outcome != mapped_outcome
                or (cur_pnl is None) != (new_pnl is None)
                or (cur_pnl is not None and new_pnl is not None and abs(cur_pnl - new_pnl) > 0.01)
            )
            if values_changed:
                action = "write"
                reason = "projection_rewalk_refresh"
                counters["projection_rewalk_refresh"] += 1
            else:
                counters["already_projected_unchanged"] += 1

        elif cur_source in ("EXPIRED", "INVALIDATED"):
            # Case E: Phase A label only. If signal_outcomes verdict is now
            # WIN/LOSS-able, upgrade. If still EXPIRED/INVALIDATED, no-op.
            if mapped_outcome is not None:
                action = "write"
                reason = "projection_initial"  # treat as initial — first time we write outcome
                counters["projection_label_to_verdict"] += 1
            elif mapped_source != cur_source:
                # Switched between EXPIRED ↔ INVALIDATED labels
                action = "write"
                reason = "projection_label_refresh"
                counters["projection_label_refresh"] += 1
            else:
                counters["label_unchanged"] += 1

        else:
            counters[f"unhandled_source_{cur_source}"] += 1

        if action is None:
            continue

        write_actions.append({
            "signal_id": row["signal_id"],
            "action": action,
            "reason": reason,
            "old_outcome": cur_outcome,
            "new_outcome": new_outcome_to_write,
            "old_source": cur_source,
            "new_source": new_source_to_write if action == "write" else cur_source,
            "old_pnl": cur_pnl,
            "new_pnl": new_pnl_to_write if action == "write" else cur_pnl,
            "old_resolved_at": cur_resolved_at,
            "new_resolved_at": new_resolved_to_write if action == "write" else cur_resolved_at,
        })

    # Dump orphans regardless of mode
    if orphan_records:
        with orphan_path.open("w", encoding="utf-8") as f:
            for o in orphan_records:
                f.write(json.dumps(o, default=str) + "\n")

    print("=" * 78)
    print("Action counters")
    print("=" * 78)
    for k in sorted(counters.keys(), key=lambda x: (-counters[x], x)):
        print(f"  {k:<42s} {counters[k]:>6}")
    print()
    print(f"Total actions queued: {len(write_actions)}")
    print(f"  writes:              {sum(1 for a in write_actions if a['action'] == 'write')}")
    print(f"  log-only diffs:      {sum(1 for a in write_actions if a['action'] == 'log_only')}")
    print(f"Orphans (signal_outcomes without matching signals): {len(orphan_records)} -> {orphan_path}")
    print()

    if not apply_mode:
        print("DRY RUN — no DB writes. Re-run with --apply to commit.")
        cur.close(); conn.close()
        return

    # APPLY: single transaction
    print(f"APPLY: writing in a single transaction. run_id = {run_id}")
    try:
        for a in write_actions:
            cur.execute("""
                INSERT INTO signal_outcome_diff_log
                    (signal_id, old_outcome, new_outcome,
                     old_outcome_source, new_outcome_source,
                     old_pnl_pct, new_pnl_pct,
                     old_resolved_at, new_resolved_at,
                     backfill_run_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                a["signal_id"], a["old_outcome"], a["new_outcome"],
                a["old_source"], a["new_source"],
                a["old_pnl"], a["new_pnl"],
                a["old_resolved_at"], a["new_resolved_at"],
                f"{run_id}:{a['reason']}",
            ))

            if a["action"] == "write":
                cur.execute("""
                    UPDATE signals
                    SET outcome = %s,
                        outcome_pnl_pct = %s,
                        outcome_resolved_at = %s,
                        outcome_source = %s
                    WHERE signal_id = %s
                """, (
                    a["new_outcome"], a["new_pnl"], a["new_resolved_at"],
                    a["new_source"], a["signal_id"],
                ))

        conn.commit()
        print(f"COMMITTED. backfill_run_id = {run_id}")
    except Exception as e:
        conn.rollback()
        print(f"FAILED: {e}")
        print("Rolled back. No changes persisted.")
        raise
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    main()
