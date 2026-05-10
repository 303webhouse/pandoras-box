"""Phase C: re-walk every resolved signal_outcomes row against current yfinance.

Purpose:
  signal_outcomes was originally written by score_signals.py walking yfinance
  daily bars at resolution time. yfinance silently drifts (Phase B's 28
  phantom-WIN investigation showed this). This script re-walks each row
  against TODAY's yfinance data, refreshes max_favorable / max_adverse /
  days_to_outcome / outcome_price / outcome verdict, and logs every change to
  signal_outcome_diff_log.

Granularity:
  Uses DAILY bars to mirror score_signals.py's walker exactly. The brief's
  early script-spec section says "15m bars" but the same brief's CC note says
  "use the same data source the original walk used or the comparison is
  meaningless" — we go with the latter. Comparing daily-walked verdicts
  against fresh daily bars is the apples-to-apples drift detection.

Scope:
  outcome IN ('STOPPED_OUT', 'HIT_T1', 'HIT_T2', 'EXPIRED', 'PENDING')
  EXCLUDES 'INVALIDATED' per Phase C Gate 2 sign-off (re-walk can't restate
  a non-price-based contradiction signal).

Resume:
  Checkpoint file at <tmpdir>/phase-c-rewalk-state.json holds processed
  signal_ids and a runtime tally. --resume re-reads the file and skips
  anything already done. Crash mid-batch is safe.

Skipped report:
  Rows that yfinance can't supply data for, or that error during walk, are
  appended to <tmpdir>/phase-c-rewalk-skipped.jsonl as one JSON object per
  line. No DB writes for these — operator inspects after run.

Usage:
  python scripts/rewalk_signal_outcomes.py                   # dry-run, full scope
  python scripts/rewalk_signal_outcomes.py --apply           # writes
  python scripts/rewalk_signal_outcomes.py --since 2026-04-25 --dry-run
  python scripts/rewalk_signal_outcomes.py --signal-id HG_NXTS_20260423_192057_3-10
  python scripts/rewalk_signal_outcomes.py --resume --max-runtime 8 --apply

See docs/codex-briefs/outcome-tracking-phase-c-projection-2026-05-09.md
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import signal as signal_module
import sys
import tempfile
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

# Pull MAX_SIGNAL_AGE_DAYS from score_signals.py so the EXPIRED age-cap
# stays in lockstep with the canonical writer. Without this, any
# stored-EXPIRED row whose age still exceeds the cap re-walks to PENDING
# and registers as a false-positive verdict_change.
sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"),
)
from jobs.score_signals import MAX_SIGNAL_AGE_DAYS  # noqa: E402

DB_URL = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DB_URL:
    sys.exit("FATAL: DATABASE_PUBLIC_URL/DATABASE_URL not set")

CHECKPOINT_PATH = Path(tempfile.gettempdir()) / "phase-c-rewalk-state.json"
SKIPPED_REPORT_PATH = Path(tempfile.gettempdir()) / "phase-c-rewalk-skipped.jsonl"

SCOPE_OUTCOMES = ("STOPPED_OUT", "HIT_T1", "HIT_T2", "EXPIRED", "PENDING")
FRESHNESS_HOURS = 24  # skip rows resolved within last N hours
MAX_FETCH_ATTEMPTS = 3
JITTER_RANGE_S = (0.2, 0.7)


def _to_utc(ts):
    if ts is None:
        return None
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts


def load_checkpoint(run_id: str | None) -> dict:
    if not CHECKPOINT_PATH.exists():
        return {"run_id": run_id or f"phase_c_rewalk_{uuid.uuid4().hex[:12]}",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "processed_ids": []}
    state = json.loads(CHECKPOINT_PATH.read_text())
    if run_id and state.get("run_id") != run_id:
        sys.exit(f"FATAL: checkpoint run_id mismatch (requested {run_id}, file {state.get('run_id')})")
    return state


def save_checkpoint(state: dict) -> None:
    CHECKPOINT_PATH.write_text(json.dumps(state, indent=2))


def append_skipped(record: dict) -> None:
    with SKIPPED_REPORT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def fetch_history(symbol: str, start: datetime):
    """Daily yfinance pull. Mirrors score_signals.py._fetch_history."""
    import yfinance as yf
    ticker = yf.Ticker(symbol)
    return ticker.history(start=start.strftime("%Y-%m-%d"))


def walk_daily_bars(df, direction: str, entry: float, stop: float | None,
                    t1: float | None, t2: float | None,
                    invalidation: float | None,
                    created_at: datetime, outcome_at_cap: datetime):
    """First-terminal-touch walk semantics (Phase C fix #3).

    Returns (outcome, outcome_price, max_favorable, max_adverse, days_to_outcome).

    Semantics:
      Walk bars chronologically up to outcome_at_cap + 1 day. On each bar,
      check terminal touches in same-bar priority order:
          invalidation > stop > T2 > T1
      The FIRST bar with ANY terminal touch terminates the walk — including
      T1. This mirrors score_signals.py's emergent "frozen at first-walk
      window with terminal touch" behavior (because score_signals never
      re-walks rows once outcome != PENDING).
      MFE/MAE are tracked incrementally and bounded to the bars actually
      walked through (NOT the full df range), so they reflect the held
      period rather than post-termination price action.
      If the walk exits without any terminal: outcome = PENDING
      (caller's age-cap fix may then promote PENDING -> EXPIRED).
    """
    if df is None or df.empty:
        return None, None, None, None, None

    outcome = None
    outcome_price = None
    matched_at = None
    max_favorable = 0.0
    max_adverse = 0.0

    for ts, bar in df.iterrows():
        bar_dt = _to_utc(ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts)
        if bar_dt > outcome_at_cap + timedelta(days=1):
            break  # don't walk past the original outcome window

        try:
            high = float(bar["High"])
            low = float(bar["Low"])
            close = float(bar["Close"])
        except (KeyError, ValueError, TypeError):
            continue

        # Accumulate MFE/MAE for this bar BEFORE the terminal check, so
        # MFE/MAE on the terminal bar includes the terminal bar's range.
        if direction == "LONG":
            day_fav = high - entry
            day_adv = entry - low
        else:
            day_fav = entry - low
            day_adv = high - entry
        if day_fav > max_favorable:
            max_favorable = day_fav
        if day_adv > max_adverse:
            max_adverse = day_adv

        # Same-bar terminal priority: invalidation > stop > T2 > T1
        # T1 now breaks the loop. The first bar with any terminal touch wins.
        if direction == "LONG":
            inval_hit = invalidation is not None and close < invalidation
            stop_hit = stop is not None and low <= stop
            t2_hit = t2 is not None and high >= t2
            t1_hit = t1 is not None and high >= t1
        else:  # SHORT
            inval_hit = invalidation is not None and close > invalidation
            stop_hit = stop is not None and high >= stop
            t2_hit = t2 is not None and low <= t2
            t1_hit = t1 is not None and low <= t1

        if inval_hit:
            outcome, outcome_price, matched_at = "INVALIDATED", round(close, 2), bar_dt
            break
        if stop_hit:
            outcome, outcome_price, matched_at = "STOPPED_OUT", stop, bar_dt
            break
        if t2_hit:
            outcome, outcome_price, matched_at = "HIT_T2", t2, bar_dt
            break
        if t1_hit:
            outcome, outcome_price, matched_at = "HIT_T1", t1, bar_dt
            break

    if outcome is None:
        outcome = "PENDING"

    days_to_outcome = (matched_at - created_at).days if matched_at else None
    return (outcome, outcome_price,
            round(max_favorable, 2), round(max_adverse, 2),
            days_to_outcome)


def fetch_with_retry(symbol: str, created_at: datetime):
    """yfinance pull with backoff. Returns (df, error_str_or_None)."""
    delay = 1.0
    for attempt in range(MAX_FETCH_ATTEMPTS):
        try:
            df = fetch_history(symbol, created_at)
            if df is None or df.empty:
                return df, "empty_payload"
            return df, None
        except Exception as e:
            if attempt == MAX_FETCH_ATTEMPTS - 1:
                return None, f"yfinance_error: {e}"
            time.sleep(delay + random.uniform(*JITTER_RANGE_S))
            delay *= 2
    return None, "exhausted_retries"


def fetch_rows(cur, since: datetime | None, signal_id: str | None):
    """Fetch resolved signal_outcomes rows in scope, excluding:
      - orphans (no matching signals row -> FK violation on diff_log INSERT)
      - NULL outcome_at (crashes walk_daily_bars's outcome_at_cap arithmetic)
    Returns (rows, exclusion_counts).
    """
    base_where = ["so.outcome IS NOT NULL",
                  "so.outcome != 'INVALIDATED'",
                  "so.outcome = ANY(%s)"]
    base_params: list = [list(SCOPE_OUTCOMES)]
    if since:
        base_where.append("so.outcome_at >= %s")
        base_params.append(since)
    if signal_id:
        base_where.append("so.signal_id = %s")
        base_params.append(signal_id)

    base_where_sql = " AND ".join(base_where)

    # Count rows excluded by each filter, for visibility in run log
    cur.execute(
        f"""
        SELECT
          COUNT(*) AS in_scope,
          COUNT(*) FILTER (WHERE NOT EXISTS (
              SELECT 1 FROM signals s WHERE s.signal_id = so.signal_id))
            AS orphan_excluded,
          COUNT(*) FILTER (WHERE so.outcome_at IS NULL) AS null_outcome_at_excluded
        FROM signal_outcomes so
        WHERE {base_where_sql}
        """,
        base_params,
    )
    in_scope, orphan_n, null_ts_n = cur.fetchone()
    exclusion_counts = {
        "in_scope_total": in_scope,
        "orphan_excluded": orphan_n,
        "null_outcome_at_excluded": null_ts_n,
    }

    # Real fetch: apply both filters at source so excluded rows never enter
    # the processing loop.
    full_where = base_where + [
        "so.outcome_at IS NOT NULL",
        "EXISTS (SELECT 1 FROM signals s WHERE s.signal_id = so.signal_id)",
    ]
    sql = f"""
        SELECT so.id, so.signal_id, so.symbol, so.signal_type, so.direction,
               so.entry, so.stop, so.t1, so.t2, so.invalidation_level,
               so.created_at, so.outcome, so.outcome_at, so.outcome_price,
               so.max_favorable, so.max_adverse, so.days_to_outcome
        FROM signal_outcomes so
        WHERE {' AND '.join(full_where)}
        ORDER BY so.outcome_at DESC
    """
    cur.execute(sql, base_params)
    rows = cur.fetchall()
    exclusion_counts["fetched_after_exclusion"] = len(rows)
    return rows, exclusion_counts


def main():
    ap = argparse.ArgumentParser(description="Phase C re-walk (signal_outcomes refresh)")
    ap.add_argument("--apply", action="store_true", help="Apply changes (default: dry-run)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Explicit dry-run flag (no-op; dry-run is the default behavior)")
    ap.add_argument("--batch-size", type=int, default=200)
    ap.add_argument("--resume", action="store_true", help="Continue from checkpoint file")
    ap.add_argument("--max-runtime", type=float, default=None,
                    help="Max wall-clock hours; checkpoint and exit cleanly when reached")
    ap.add_argument("--since", type=str, default=None,
                    help="Only re-walk rows resolved on/after this date (YYYY-MM-DD)")
    ap.add_argument("--signal-id", type=str, default=None, help="Re-walk one specific row")
    ap.add_argument("--run-id", type=str, default=None,
                    help="Override run_id (must match checkpoint if --resume)")
    args = ap.parse_args()

    apply_mode = args.apply
    state = load_checkpoint(args.run_id) if args.resume else {
        "run_id": args.run_id or f"phase_c_rewalk_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "processed_ids": [],
    }
    processed = set(state["processed_ids"])

    print(f"run_id     = {state['run_id']}")
    print(f"mode       = {'APPLY (writes)' if apply_mode else 'DRY RUN (no writes)'}")
    print(f"checkpoint = {CHECKPOINT_PATH}")
    print(f"skipped    = {SKIPPED_REPORT_PATH}")
    if args.resume:
        print(f"resume: {len(processed)} rows already processed")
    print()

    since_dt = None
    if args.since:
        since_dt = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)

    runtime_deadline = None
    if args.max_runtime:
        runtime_deadline = time.time() + args.max_runtime * 3600

    conn = psycopg2.connect(DB_URL, connect_timeout=15)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    rows, exclusion_counts = fetch_rows(cur, since_dt, args.signal_id)
    total = len(rows)
    print(f"in-scope before exclusions:    {exclusion_counts['in_scope_total']}")
    print(f"  - orphan rows excluded:      {exclusion_counts['orphan_excluded']}   (no matching signals row)")
    print(f"  - NULL outcome_at excluded:  {exclusion_counts['null_outcome_at_excluded']}")
    print(f"loaded {total} signal_outcomes rows in scope (post-exclusion)")
    print()

    counters = Counter()
    verdict_change_samples: list = []  # capture up to N for surfacing
    SAMPLE_CAP = 10
    freshness_cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESHNESS_HOURS)

    for i, row in enumerate(rows, 1):
        if row["signal_id"] in processed:
            counters["already_processed"] += 1
            continue

        if runtime_deadline and time.time() > runtime_deadline:
            print(f"[{i}/{total}] max-runtime reached — checkpointing and exiting")
            state["processed_ids"] = list(processed)
            save_checkpoint(state)
            cur.close(); conn.close()
            return

        outcome_at = _to_utc(row["outcome_at"])
        if outcome_at and outcome_at > freshness_cutoff:
            counters["skipped_recent"] += 1
            processed.add(row["signal_id"])
            continue

        created_at = _to_utc(row["created_at"])
        df, err = fetch_with_retry(row["symbol"], created_at)
        if err:
            counters[f"skipped_{err.split(':')[0]}"] += 1
            append_skipped({
                "signal_id": row["signal_id"], "symbol": row["symbol"],
                "reason": err, "run_id": state["run_id"],
                "checked_at": datetime.now(timezone.utc).isoformat(),
            })
            processed.add(row["signal_id"])
            continue

        try:
            entry = float(row["entry"]) if row["entry"] is not None else None
            stop = float(row["stop"]) if row["stop"] is not None else None
            t1 = float(row["t1"]) if row["t1"] is not None else None
            t2 = float(row["t2"]) if row["t2"] is not None else None
            inval = float(row["invalidation_level"]) if row["invalidation_level"] is not None else None
            if entry is None or row["direction"] not in ("LONG", "SHORT"):
                counters["skipped_missing_fields"] += 1
                processed.add(row["signal_id"])
                continue

            new_outcome, new_price, new_mfe, new_mae, new_days = walk_daily_bars(
                df, row["direction"], entry, stop, t1, t2, inval,
                created_at, outcome_at,
            )
            # Mirror score_signals.py's EXPIRED age-cap. Applied AFTER the
            # walk so terminal verdicts that landed within the cap window
            # still surface — only PENDING rows past the cap get folded
            # to EXPIRED.
            age_days = (datetime.now(timezone.utc) - created_at).days
            if new_outcome == "PENDING" and age_days > MAX_SIGNAL_AGE_DAYS:
                new_outcome = "EXPIRED"
                new_price = None
                new_days = age_days
        except Exception as e:
            counters["walk_error"] += 1
            append_skipped({
                "signal_id": row["signal_id"], "symbol": row["symbol"],
                "reason": f"walk_error: {e}", "run_id": state["run_id"],
            })
            processed.add(row["signal_id"])
            continue

        old_outcome = row["outcome"]
        old_mfe = float(row["max_favorable"]) if row["max_favorable"] is not None else None
        old_mae = float(row["max_adverse"]) if row["max_adverse"] is not None else None
        old_price = float(row["outcome_price"]) if row["outcome_price"] is not None else None
        old_days = row["days_to_outcome"]

        verdict_changed = (old_outcome != new_outcome)
        snapshot_changed = (
            old_mfe is None or old_mae is None or new_mfe is None or new_mae is None or
            abs(old_mfe - new_mfe) > 0.01 or abs(old_mae - new_mae) > 0.01
        )

        if not verdict_changed and not snapshot_changed:
            counters["unchanged"] += 1
            processed.add(row["signal_id"])
        else:
            reason = "rewalk_verdict_change" if verdict_changed else "rewalk_snapshot_drift"
            counters[reason] += 1
            if verdict_changed and len(verdict_change_samples) < SAMPLE_CAP:
                verdict_change_samples.append({
                    "signal_id": row["signal_id"],
                    "ticker": row["symbol"],
                    "signal_ts": str(row.get("created_at")),
                    "outcome_at": str(outcome_at),
                    "old_outcome": old_outcome,
                    "new_outcome": new_outcome,
                    "old_mfe": old_mfe,
                    "new_mfe": new_mfe,
                    "old_mae": old_mae,
                    "new_mae": new_mae,
                })

            if apply_mode:
                cur.execute("""
                    INSERT INTO signal_outcome_diff_log
                        (signal_id, old_outcome, new_outcome,
                         old_outcome_source, new_outcome_source,
                         old_pnl_pct, new_pnl_pct,
                         old_resolved_at, new_resolved_at,
                         backfill_run_id)
                    VALUES (%s, %s, %s, NULL, NULL, %s, %s, %s, NOW(), %s)
                """, (
                    row["signal_id"], old_outcome, new_outcome,
                    old_mfe, new_mfe,  # repurpose pnl_pct columns to record MFE drift
                    outcome_at, state["run_id"] + ":" + reason,
                ))
                cur.execute("""
                    UPDATE signal_outcomes
                    SET outcome = %s,
                        outcome_price = %s,
                        max_favorable = %s,
                        max_adverse = %s,
                        days_to_outcome = COALESCE(%s, days_to_outcome)
                    WHERE id = %s
                """, (new_outcome, new_price, new_mfe, new_mae, new_days, row["id"]))
            processed.add(row["signal_id"])

        if i % args.batch_size == 0:
            if apply_mode:
                conn.commit()
            state["processed_ids"] = list(processed)
            save_checkpoint(state)
            print(f"  [{i}/{total}] processed={len(processed)} "
                  f"verdict_changes={counters.get('rewalk_verdict_change', 0)} "
                  f"snapshot_drift={counters.get('rewalk_snapshot_drift', 0)} "
                  f"skipped={sum(v for k, v in counters.items() if k.startswith('skipped'))}")
            time.sleep(random.uniform(*JITTER_RANGE_S))

    if apply_mode:
        conn.commit()
    state["processed_ids"] = list(processed)
    state["finished_at"] = datetime.now(timezone.utc).isoformat()
    save_checkpoint(state)

    # tz-aware ISO -> correct UTC epoch (time.mktime treats struct_time as
    # local, which produces a 6h offset on MDT hosts).
    elapsed = time.time() - datetime.fromisoformat(state["started_at"]).timestamp()
    print()
    print("=" * 78)
    print("Re-walk summary")
    print("=" * 78)
    print(f"  total scanned:     {total}")
    for k in sorted(counters.keys()):
        print(f"  {k:<30s} {counters[k]}")
    print(f"  runtime:           {elapsed/60:.1f} min")
    print(f"  skipped report:    {SKIPPED_REPORT_PATH}")
    print(f"  checkpoint:        {CHECKPOINT_PATH}")

    if verdict_change_samples:
        print()
        print("=" * 78)
        print(f"Sample verdict_change rows (up to {SAMPLE_CAP}, for spot-check pick)")
        print("=" * 78)
        for s in verdict_change_samples:
            print(f"  {s['signal_id']:<46s} {s['ticker']:<8s} "
                  f"signal_ts={s['signal_ts'][:19]} outcome_at={s['outcome_at'][:19]}")
            print(f"    {s['old_outcome']:<14s} -> {s['new_outcome']:<14s}  "
                  f"MFE {s['old_mfe']} -> {s['new_mfe']}  MAE {s['old_mae']} -> {s['new_mae']}")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
