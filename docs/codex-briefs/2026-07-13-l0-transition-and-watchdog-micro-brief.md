# CC MICRO-BRIEF — L0 transition-window fixes + watchdog 24/7
**Target: Monday 2026-07-13, pre-market. Push window closes 07:15 MT.**
Drafted 2026-07-10 evening by the coordination lane (Fable), Nick GO on record.
**GATE: SATISFIED — ATLAS Pass 1 logged 2026-07-10 evening (coordination lane). Verdict: one phase-gate veto raised and CLEARED via amendment A5; APPROVE FOR CC with amendments A1–A7 incorporated below. Conviction HIGH.**

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

**ATLAS amendments to Item 1 (2026-07-10):**
- **A5 (phase gate — veto-clearing, mandatory):** `--execute` requires an explicit GO. Sequence: run dry-run → post the FULL output to the coordination chat → WAIT. The coordination lane is pre-authorized by Nick to issue GO if and only if counts are exactly P1=307, P2=1,132, total=1,439 AND the 3 sample rows render correctly. Any deviation → Nick decides.
- **A1 (rollback path — mandatory):** before `--execute`, the script exports a pre-image of every affected row (`signal_id`, old `triggering_factors->'l0_shadow'`) to `C:\temp\backfill_preimage_ARTEMIS_LONG_<timestamp>.jsonl`. This plus in-row `backfill.original_would_suppress` is the documented rollback path.
- **A6 (row-count invariance):** assert `SELECT COUNT(*) FROM signals WHERE signal_type='ARTEMIS_LONG'` is IDENTICAL before and after `--execute` (proves tag-only mutation, zero row drops). Include both numbers in the report.
- **A7 (implementation note):** the `$RULE_REF` in the SQL sketches above is spec pseudocode, not valid asyncpg syntax — implement as a proper `$n` parameter or a validated constant; never raw string-interpolate user-supplied args into SQL.

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

## Item 3 — legacy trio in `backend/database/postgres_client.py` (ATLAS-read 2026-07-10; line refs on 788d466)
The trio backs `/api/signals/active`, `/active/paged`, `/queue` via `backend/api/positions.py` — name-collision twins of the filtered feed_service versions. **ATLAS finding A2: it is FIVE SQL statements, not three** — two functions carry FALLBACK queries in `except` branches; patching only primaries leaves the leak alive on exactly the resilience path. Patch ALL of:
1. `get_active_trade_ideas` (~line 1577): primary query (~1589) **and** fallback query (~1607) — static `"""` strings → Pattern A (`_l0_and` f-string; note `"""`→`f"""`).
2. `get_active_trade_ideas_paginated` (~line 1663): composes a `filters` list → **Pattern B**: `filters.append(_l0)` when non-empty (covers both the COUNT and the page query, which share `where_clause`).
3. `get_signal_queue` (~line 1722): primary (~1730) **and** fallback (~1740) — Pattern A, same as (1).
Compute `_l0 = l0_enforce_where_clause()` once per function; import at function top matching house style. These queries filter on `user_action IS NULL` (not `status='ACTIVE'`) — do NOT reconcile that here; leak-patch only. Do NOT retire the endpoints — they die with the day-7 legacy removal post-flip. Include all five before/after diffs in the completion report.

## Item 4 — watchdog alert path goes 24/7 (`backend/main.py` ~line 726; ATLAS-read 2026-07-10, exact anchors)
**ATLAS correction A4: the gate is weekday+hour, not hour-only** — `et.weekday() < 5 and 9 <= et.hour < 16`. Both conditions go (weekend ticks read one Redis key, cost nothing, and eliminate the assumption class entirely). Dead imports (`pytz`, `_dt`) go with it. FIND (verbatim):
```python
    async def uw_budget_watchdog_loop():
        import pytz
        from datetime import datetime as _dt
        await asyncio.sleep(160)
        while True:
            try:
                et = _dt.now(pytz.timezone("America/New_York"))
                if et.weekday() < 5 and 9 <= et.hour < 16:
                    from jobs.uw_budget_watchdog import run_budget_watchdog
                    await run_budget_watchdog()
            except Exception as e:
                logger.warning("uw_budget_watchdog loop error: %s", e)
            await asyncio.sleep(300)  # 5 min
```
REPLACE:
```python
    async def uw_budget_watchdog_loop():
        await asyncio.sleep(160)
        while True:
            try:
                from jobs.uw_budget_watchdog import run_budget_watchdog
                await run_budget_watchdog()
            except Exception as e:
                logger.warning("uw_budget_watchdog loop error: %s", e)
            await asyncio.sleep(300)  # 5 min
```
Also update the block comment above the function — FIND: `in-hub runtime circuit breaker. RTH-gated` / REPLACE: `in-hub runtime circuit breaker. 24/7 as of 2026-07-13 (7/10 lesson: first real 17K crossing landed AFTER the close; the counter accumulates on the UTC day). Formerly RTH-gated` — keep the rest of the comment intact. `jobs/uw_budget_watchdog.py` (`run_budget_watchdog`, shed logic, thresholds, TTLs) is UNCHANGED — shed-while-Triton-idles is harmless and self-clears at rollover. `uw_daily_burn_snapshot_loop` untouched. Tests: `tests/test_uw_budget_watchdog.py` targets the tick, not the loop — expect ZERO test changes; if any test references the gate, stop and flag before modifying.

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
3. `/board/ticker-context?tickers=JPM,GS,EMR,RSP,SNAP,LI,LYFT,XLF` — kairos badges, full 7/10 leak set (was leaking)
4. `/api/signals/active`, paged variant, `/queue` (was 3 leaking)
5. Backfill assertion query = 0; updated-row count reported vs the 1,439 expectation; A6 row-count invariance (total ARTEMIS_LONG rows identical before/after); A1 pre-image JSONL path reported
6. Test suite green with the same 3 known pre-existing failures ONLY (footprint_long, session_sweep, pullback_entry ceiling — already ledgered)
7. Gate-removal proof: a `uw_budget_watchdog` success tick in `stable_job_status` with `last_run` AFTER 20:00 UTC Monday (end-of-day check — pre-market deploy lands inside RTH, so the proof is the evening tick)
8. Rider (part (b) from 7/10): first fresh ARTEMIS_LONG signal Monday RTH carries `would_suppress=true` and appears in NO feed — closes the PENDING-MONDAY verification + empirically confirms the single write path

## Commit & deploy plan
Commit 1 (step 0): this brief → `docs/codex-briefs/`. Commit 2: items 2+3+5a (L0 read surfaces + Artemis comment). Commit 3: items 4+5b (watchdog loop + its docstring — thematic unit). **ONE push carrying all commits = one Railway redeploy**, complete before 07:15 MT; confirm deploy healthy + `/mcp/v1/health` shows new SHA. Then item 1: dry-run → post FULL output to the coordination chat → WAIT for explicit GO (A5) → `--execute` → assertions (A6, A1 path) → acceptance sweep. Report in the standard format: per-item status, all five Item-3 diffs, sweep table, deviations flagged BEFORE improvising. The working tree is NOISY (50+ untracked files as of 7/10) — pathspec discipline is load-bearing.
