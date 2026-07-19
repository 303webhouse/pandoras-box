# CC MICRO-BRIEF — L0 transition-window fixes + watchdog 24/7
**Target: Monday 2026-07-13, pre-market. Push window closes 07:15 MT.**
Drafted 2026-07-10 evening by the coordination lane (Fable), Nick GO on record.
**GATE: Do NOT execute until an ATLAS review pass is logged on this brief.**

## Preconditions & constraints
- `git fetch && git status` first — confirm local `C:\trading-hub` matches `origin/main` at `788d466` or a verified descendant. Cross-machine drift is a documented risk; abort and report if diverged.
- Commit THIS brief file to `docs/codex-briefs/` as step 0 (pathspec commit) before any code work.
- Pathspec-only commits, messages via `C:\temp\commitmsg.txt`, never `git add .`.
- All pushes complete before 07:15 MT. If the window is missed, everything holds to after 14:00 MT — do not push into the 07:30–14:00 blackout.
- Item 1 (backfill) is a DATA operation run after the deploy is healthy; items 2–5 are the code push.

## Context (compressed)
7/10 sweep findings: (1) L0 enforce predicate keys on the write-time `l0_shadow.would_suppress` tag by design (drift protection + validated by the shadow window), so 1,439 historical `ARTEMIS_LONG` rows (1,132 tag-null pre-gate, 307 tagged-false under the pre-eviction rule) leak through even correctly-wired endpoints — 8 live in `/api/trade-ideas` tonight. (2) `board_state.py` kairos sub-query never wired to L0 (owed since 817649c). (3) Legacy trio in `postgres_client.py` is a separate unfiltered implementation. (4) Watchdog missed a real 17K crossing at 7/10 after-hours (final 17,394) because the alert loop was RTH-gated while the counter accumulates on the UTC day. Decisions on record (Nick GO 7/10): backfill-with-provenance, NOT a predicate change (one source of truth: the tag); watchdog alert path goes 24/7, gate deleted, shed logic unchanged and also ungated.

## Item 1 — `scripts/backfill_suppression.py` (new, reusable)
Generic eviction-runbook script: `python scripts/backfill_suppression.py --signal-type ARTEMIS_LONG --rule-ref "cta-artemis-decompose 2026-06-16 / eviction 2026-07-10" [--execute]`. Dry-run is the DEFAULT: print live counts per population + 3 sample rows rendered before/after; `--execute` wraps both UPDATEs in one transaction. Uses `get_postgres_client()` like everything else.

Two disjoint populations, both idempotent (WHERE excludes already-true rows):

**P1 — tag exists, `would_suppress=false` (expect ~307):** preserve the original evaluation inside the tag, then flip:
```sql
UPDATE signals
SET triggering_factors =
    jsonb_set(
      jsonb_set(triggering_factors, '{l0_shadow,backfill}',
        jsonb_build_object('original_would_suppress',
                           triggering_factors->'l0_shadow'->'would_suppress',
                           'rule_ref', $RULE_REF, 'applied_at', now()::text), true),
      '{l0_shadow,would_suppress}', 'true'::jsonb)
WHERE signal_type = 'ARTEMIS_LONG'
  AND triggering_factors->'l0_shadow' IS NOT NULL
  AND COALESCE((triggering_factors->'l0_shadow'->>'would_suppress')::boolean, false) = false;
```

**P2 — no `l0_shadow` object at all (expect ~1,132):** build a fresh tag whose `mode` is honestly `'backfill'` (never fake a `shadow`/`enforce` evaluation that didn't happen), original recorded as null:
```sql
UPDATE signals
SET triggering_factors = jsonb_set(
      COALESCE(triggering_factors, '{}'::jsonb), '{l0_shadow}',
      jsonb_build_object('v', 1, 'mode', 'backfill', 'signal_type', 'ARTEMIS_LONG',
        'rule', 'SUPPRESS', 'would_suppress', true, 'is_liquid', null,
        'reason', 'backfilled — ARTEMIS_LONG eviction postdates row',
        'backfill', jsonb_build_object('original_would_suppress', null,
                     'rule_ref', $RULE_REF, 'applied_at', now()::text)), true)
WHERE signal_type = 'ARTEMIS_LONG'
  AND (triggering_factors IS NULL OR triggering_factors->'l0_shadow' IS NULL);
```
Measure live counts FIRST; expect 307 + 1,132 = 1,439. If materially different, stop and report before `--execute`. Post-run assertion (must be zero): `SELECT COUNT(*) FROM signals WHERE signal_type='ARTEMIS_LONG' AND COALESCE((triggering_factors->'l0_shadow'->>'would_suppress')::boolean,false)=false;` Paste dry-run output + post-run assertion in the completion report. Known accepted limitation (document in script docstring): rows whose `signal_type` drifted AWAY from ARTEMIS_LONG after eval are out of scope of a type-keyed backfill.

## Item 2 — `backend/api/board_state.py` kairos sub-query (exact anchor)
In `get_ticker_context`, FIND (verbatim, verified on `788d466`):
```python
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT ticker, signal_id, signal_type, strategy, direction,
                          COALESCE(adjusted_score, score_v2, score) AS best_score
                   FROM signals WHERE status = 'ACTIVE' AND ticker = ANY($1::text[])
                   ORDER BY ticker, best_score DESC NULLS LAST""",
                tks,
            )
```
REPLACE with (house Pattern A, mirrors `_query_tier_groups` in trade_ideas.py — note `"""` becomes `f"""`; safe, the fragment is static with no user input):
```python
        from config.l0_routing import l0_enforce_where_clause
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        # L0.1a ENFORCE (2026-07-13): kairos badge is an actionable read surface —
        # exclude gate-suppressed rows (dashboard forensics item 1, owed since 817649c).
        _l0 = l0_enforce_where_clause()
        _l0_and = f" AND {_l0}" if _l0 else ""
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT ticker, signal_id, signal_type, strategy, direction,
                          COALESCE(adjusted_score, score_v2, score) AS best_score
                   FROM signals WHERE status = 'ACTIVE' AND ticker = ANY($1::text[]){_l0_and}
                   ORDER BY ticker, best_score DESC NULLS LAST""",
                tks,
            )
```

## Item 3 — legacy trio in `backend/database/postgres_client.py`
Functions confirmed present: `get_active_trade_ideas`, `get_active_trade_ideas_paginated`, `get_signal_queue` (the name-collision twins of the filtered feed_service versions; they back `/api/signals/active`, `/active/paged`, `/queue` via `backend/api/positions.py`). **Mandatory pre-edit read of each function** (file not fully recon'd remotely — anchor by signature). Apply the same Pattern A injection to each `signals` query's WHERE clause. Do NOT retire the endpoints — they die with the day-7 legacy removal post-flip; filtering is the cheap honest bridge. Include each function's before/after diff in the completion report.

## Item 4 — watchdog alert path goes 24/7 (`backend/main.py`)
`uw_budget_watchdog_loop()` in `backend/main.py` (single occurrence) wraps `run_budget_watchdog()` with an ET-hour RTH gate (`9 <= ET hour < 16`). **Mandatory pre-edit read of the full loop function.** DELETE the RTH conditional so the tick runs on its ~5-min cadence around the clock (keep the `await asyncio.sleep(160)` boot delay and the cadence sleep). Rationale on record: the counter accumulates on the UTC day, so the watchdog watches the UTC day; the loop reads one Redis key and makes zero UW calls — always-on costs nothing. `jobs/uw_budget_watchdog.py` (`run_budget_watchdog`, shed logic, thresholds, TTLs) is UNCHANGED — shed-while-Triton-idles is harmless and self-clears at rollover. `uw_daily_burn_snapshot_loop` untouched. Tests: `tests/test_uw_budget_watchdog.py` targets the tick, not the loop — expect ZERO test changes; if any test references the gate, stop and flag before modifying.

## Item 5 — doc-rot fixes (exact anchors)
**5a — `backend/config/l0_routing.py`** (stale since 788d466), FIND:
```python
# Everything not named above is KEPT untouched (GOLDEN_TOUCH, TRAPPED_SHORTS,
# TWO_CLOSE_VOLUME, APIS_CALL, sell_the_rip*, Artemis*, footprint, etc.).
```
REPLACE:
```python
# Everything not named above is KEPT untouched (GOLDEN_TOUCH, TRAPPED_SHORTS,
# TWO_CLOSE_VOLUME, APIS_CALL, sell_the_rip*, ARTEMIS_SHORT, footprint, etc.).
```
**5b — `backend/jobs/uw_budget_watchdog.py` module docstring**, FIND:
```
  1. RTH-gated ~5-min job reads the running daily UW total (get_daily_count).
```
REPLACE:
```
  1. 24/7 ~5-min job reads the running daily UW total (get_daily_count).
     (2026-07-10 lesson: the first real 17K crossing happened AFTER the close —
     the counter accumulates on the UTC day, so the watchdog watches the UTC day.)
```

## Acceptance — re-run the 7/10 sweep, all must return ZERO `ARTEMIS_LONG` (historical included)
1. `/api/trade-ideas` flat feed (was 8 leaking: JPM, GS, EMR, RSP, SNAP, LI, LYFT, XLF)
2. `/api/trade-ideas/grouped` and `/trade-ideas/main-feed`
3. `/board/ticker-context?tickers=JPM,GS,SNAP` — kairos badges (was leaking)
4. `/api/signals/active`, paged variant, `/queue` (was 3 leaking)
5. Backfill assertion query = 0; updated-row count reported vs the 1,439 expectation
6. Test suite green with the same 3 known pre-existing failures ONLY (footprint_long, session_sweep, pullback_entry ceiling — already ledgered)
7. Gate-removal proof: a `uw_budget_watchdog` success tick in `stable_job_status` with `last_run` AFTER 20:00 UTC Monday (end-of-day check — pre-market deploy lands inside RTH, so the proof is the evening tick)
8. Rider (part (b) from 7/10): first fresh ARTEMIS_LONG signal Monday RTH carries `would_suppress=true` and appears in NO feed — closes the PENDING-MONDAY verification + empirically confirms the single write path

## Commit & deploy plan
Commit 1 (step 0): this brief → `docs/codex-briefs/`. Commit 2: items 2+3+5 (L0 read surfaces + doc rot). Commit 3: item 4 (main.py loop). Push before 07:15 MT; confirm Railway deploy healthy + `/mcp/v1/health` shows new SHA. Then item 1 dry-run → paste output → `--execute` → assertions → sweep. Report back in the standard format: per-item status, diffs for pre-edit-read items, sweep table, deviations flagged BEFORE improvising.
