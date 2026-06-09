# Phase 0 Findings — A3 (Outcome Self-Scoring) + A4 (Committee-Review Logging)

**Date:** 2026-06-07 | **Analyst:** Claude Code | **Status:** Awaiting Nick greenlight before Phase 1  
**Master brief ref:** `docs/codex-briefs/2026-06-05-master-brief-edge-consolidation.md` §4, §9  
**Mode:** Read-only investigation. No schema, no code, no migration, no deploy.

---

## Summary (TL;DR for gate review)

1. `outcome_source` lives on `signals`, not `signal_outcomes`. `signal_outcomes` is a bar-walk companion table with binary outcomes (HIT_T1/STOPPED_OUT) and no P&L $ column. The two tables serve different purposes and A3 writes to `signals.outcome_source`, not `signal_outcomes`.
2. The `outcome_source_valid` CHECK on `signals` doesn't include `FWD_RETURN` or `COMMITTEE_REVIEW` yet — both require a constraint extension (migration) before A3/A4 can write them.
3. `OPTIONS_PNL` as an `outcome_source` value on `signals` is also blocked by the constraint — migration 016 added it only to `signal_options_expressions.outcome_source`. The constraint extension to `signals` was intentionally deferred to Phase 2 (per migration 016 design). A3 must include this migration.
4. Forward-return logic does not exist in backend — only in backtesting scripts. Must be built on UW bars.
5. A4 already has a REST write path (`POST /api/committee/results`) that the VPS bridge calls today. A4 extends this path — it does not add a net-new write surface. Hub MCP is read-only; no write scaffolding exists.
6. A4's architecture is **passive capture** (VPS calls the REST endpoint without committee agents knowing). No committee skill regression pass required.

---

## A3 — Outcome Self-Scoring

### Finding 1: `signal_outcomes` schema

`signal_outcomes` is a **bar-walk companion table**, not the outcome_source table.

| Column | Type | Notes |
|---|---|---|
| `id` | integer | PK |
| `signal_id` | varchar NOT NULL | join key to signals (no FK constraint) |
| `symbol` | varchar NOT NULL | ticker |
| `signal_type` | varchar NOT NULL | |
| `direction` | varchar NOT NULL | |
| `cta_zone` | varchar | nullable |
| `entry` | numeric | entry price at signal time |
| `stop` | numeric | stop level |
| `t1` / `t2` | numeric | targets |
| `invalidation_level` | numeric | |
| `created_at` | timestamp | |
| `outcome` | varchar | **STOPPED_OUT, HIT_T1, HIT_T2, EXPIRED, INVALIDATED, PENDING** |
| `outcome_at` | timestamp | when outcome was reached |
| `outcome_price` | numeric | price at resolution |
| `max_favorable` | numeric | MFE |
| `max_adverse` | numeric | MAE |
| `days_to_outcome` | integer | |

**No `outcome_source` column.** No P&L % or $ column. The `outcome` column is a varchar (free text, not a Postgres enum).

**Row counts:**

| outcome | count |
|---|---|
| STOPPED_OUT | 6,352 |
| HIT_T1 | 2,297 |
| EXPIRED | 1,716 |
| HIT_T2 | 770 |
| INVALIDATED | 246 |
| PENDING | 154 |
| **Total** | **11,535** |

### Finding 2: `outcome_source` lives on `signals`

`outcome_source` is a column on the `signals` table, not `signal_outcomes`. The `outcome_source_valid` CHECK constraint currently allows:

```
BAR_WALK | ACTUAL_TRADE | COUNTERFACTUAL | EXPIRED | INVALIDATED | PROJECTED_FROM_BAR_WALK
```

**Current `signals.outcome_source` distribution:**

| value | count |
|---|---|
| PROJECTED_FROM_BAR_WALK | 7,349 |
| BAR_WALK | 1,852 |
| EXPIRED | 1,585 |
| COUNTERFACTUAL | 432 |
| INVALIDATED | 212 |
| ACTUAL_TRADE | 2 |

`FWD_RETURN`, `OPTIONS_PNL`, and `COMMITTEE_REVIEW` are **not in the constraint** — all three require a migration to extend it before A3/A4 can write.

Note: `OPTIONS_PNL` as a `signals.outcome_source` value was blocked by migration 016 by design (constraint extension deferred). Migration 016 added it only to `signal_options_expressions.outcome_source` (its own column). A3's migration must include all three new values in one extension.

### Finding 3: Writers — exact locations

| outcome_source value | Writer function | File |
|---|---|---|
| `BAR_WALK` | (no named function — inline UPDATE in loop) | `backend/jobs/outcome_resolver.py:195` |
| `PROJECTED_FROM_BAR_WALK` / `EXPIRED` / `INVALIDATED` | `_update_signal_outcomes_from_bar_walk()` | `backend/jobs/score_signals.py:252–257` |
| `ACTUAL_TRADE` | `_resolve_signal_outcome()` | `backend/api/unified_positions.py:1484` |
| `COUNTERFACTUAL` | `resolve_counterfactuals()` (endpoint) | `backend/analytics/api.py:2522` |

Initial `signal_outcomes` INSERT (status='PENDING'): `write_signal_outcome()` in `backend/signals/pipeline.py:207`.

All writers use `WHERE outcome_source IS NULL` guards to prevent overwriting — confirmed in `score_signals.py:260`. A3's new writers must follow the same pattern.

### Finding 4: `signal_options_expressions` → outcome join path for `OPTIONS_PNL`

Schema confirmed (migration 016, deployed):

| Column | Type | Notes |
|---|---|---|
| `signal_id` | text NOT NULL | FK to signals |
| `b2_status` | varchar | PENDING/ENTERED/EXITED/NO_CHAIN/NO_EXPIRY/NO_SHORT_LEG/EXPIRED_UNRESOLVED |
| `entry_mark` | numeric | spread debit at entry |
| `exit_mark` | numeric | spread value at resolution |
| `options_pnl` | numeric | (exit_mark − entry_mark) × 100 — dollar P&L per contract |
| `max_profit` | numeric | (width − entry_mark) × 100 |
| `max_loss` | numeric | entry_mark × 100 |
| `exit_trigger` | varchar | TARGET_1 or STOP_LOSS |
| `outcome_source` | varchar NOT NULL | always 'OPTIONS_PNL' (this table's own column) |

**Join path for A3 OPTIONS_PNL:** `signals.signal_id = signal_options_expressions.signal_id` where `signal_options_expressions.b2_status = 'EXITED'`. A3 reads `options_pnl`, `exit_trigger`, `entry_mark`, and `max_profit`/`max_loss` from this table, then writes to `signals.outcome_source = 'OPTIONS_PNL'` with a pct equivalent.

**Blocker:** As noted, `outcome_source_valid` CHECK on `signals` must be extended to include 'OPTIONS_PNL' before A3's OPTIONS_PNL writer can fire.

### Finding 5: Forward-return status

**Does not exist in `backend/`.** All references to T+1/T+3/T+5 are in backtesting scripts:

- `scripts/earnings_gap_backtest.py` — T+1..T+5 drift windows
- `scripts/gap_convexity_options_validation.py` — T+3/T+5/T+10 exit marks

A3 must build forward-return from scratch. Per data hierarchy: **UW bars primary** (`get_bars()` or `get_ohlc()`). yfinance is fallback only. Never Polygon/FMP.

**Horizon decision deferred to Nick.** Options from the backtesting evidence:

| Horizon | Use case | Notes |
|---|---|---|
| T+1 | Day-trade grading; intraday signal validity | Fast feedback; noisy |
| T+3 | Swing signal default | Matches brief's "responsive entry at structural extremes" thesis |
| T+5 | Swing confirmation | Allows multi-day resolution before calling STOPPED_OUT |
| All three | Multi-horizon view | More data per signal; higher DB volume |

Recommendation: propose T+1 and T+5 as the bracketing horizons (captures fast misses and sustained moves). Nick decides.

### Finding 6: Prior context — 2026-04-22 outcome-tracking-fix brief

- Root cause was resolver only operating on `status = 'ACCEPTED_*'` signals → broadened to all non-DISMISSED
- Fix was shipping via `outcome_resolver.py` (the 15-min intraday bar-walk resolver)
- **Key trap:** A3's `FWD_RETURN` resolver is conceptually different from `BAR_WALK` — BAR_WALK fires when the signal's explicit target or stop is touched; FWD_RETURN fires at a fixed calendar horizon regardless. They must remain separate writers with separate `outcome_source` values. **Do not merge them.**
- The brief used yfinance for bars — superseded by current data hierarchy (UW primary).

---

## A4 — Committee-Review Logging

### Finding 7: Existing write paths

**Two partial paths already exist — this is NOT a greenfield build.**

**Path 1 — `committee_bridge.py`:**  
`POST /api/committee/results` (auth-gated with `require_api_key`)  
Writes to `signals.committee_data` JSONB column on the signal row. Also sets `signals.committee_completed_at`, `signals.decision_source = 'committee'`, and updates `signals.status`.  
Called by the **VPS pivot2-interactions service** when a committee pass completes.

**Path 2 — `committee_history.py`:**  
`POST /committee/history` (implied, router prefix `/committee`)  
Writes to `committee_recommendations` table — but **this table does not exist in the DB** (`information_schema.columns` returned no rows for it). The endpoint code exists; the migration was never run. This is dead code in its current state.

### Finding 8: Hub-side committee representation today

The VPS (`pivot2-interactions`) already sends structured committee output to Railway via `POST /api/committee/results`. The payload is written to `signals.committee_data` (JSONB). Querying `signals.committee_data` shows each pass captures: action, conviction, toro/ursa analysis, risk parameters, cost, duration — most of what A4 spec requires.

**What's missing from the current capture:**
- Per-agent read (currently stored as a blob, not individually addressable columns)
- Spot price at committee time
- Entry/stop/target/invalidation at committee time
- `outcome_source = 'COMMITTEE_REVIEW'` on `signals` (for the learning-loop close)
- A durable, query-friendly row (current JSON blob is opaque to analytics)

### Finding 9: MCP write capability

All 12 Hub MCP tools are **read-only**. No write-tool scaffolding exists in `backend/hub_mcp/`. The AEGIS whitelist (`REGISTERED_TOOL_NAMES`) has no write tools; adding one would require a new entry and a new tool file.

**Recommended write path: extend existing REST endpoint (`POST /api/committee/results`).**

Rationale: The VPS bridge already calls this endpoint on every committee pass. Extending it to also write a `COMMITTEE_REVIEW` outcome row (to a dedicated table or as a `signals.outcome_source` update) requires only server-side changes — no change to VPS scripts or committee skill behavior. Hub MCP write tools would require the VPS to call the MCP API (different auth layer, more complexity, and an AEGIS review for a new write surface that doesn't yet exist). REST extension is narrower.

### Finding 10: Olympus Impact — passive capture vs skill-side call

**Architecture is passive capture.** The committee agents (TORO/URSA/PYTHIA/etc.) run in Claude.ai skills. Their outputs flow to the VPS (`pivot2-interactions`) which calls `POST /api/committee/results`. Committee agents never directly call any backend API — the VPS bridge handles that transparently.

A4's logging would extend the VPS bridge call on the server side. **Committee agents see no change.** Their behavior, output format, and skill code are unaffected.

**AEGIS pre-flag:** The existing `POST /api/committee/results` endpoint is already an auth-gated write surface. A4 extends it — it does not create a net-new attack surface. A dedicated structured-log table (`committee_passes` or similar) is a new table but not a new endpoint. This is a lower-risk AEGIS surface than a new MCP write tool would be.

**Olympus Impact verdict: PASSIVE CAPTURE — no committee skill regression pass required for A4's logging capability.** A regression pass would only be needed if A4 adds a skill-side call (e.g., PIVOT skill directly calls a logging tool). Per current architecture, it does not.

---

## Schema mapping note (A4 row shape — for reference only, not building)

The `committee_recommendations` table exists in code but not in DB. Its schema from the code:

```
signal_id, ticker, action, conviction, synthesis, invalidation, structure, levels, size, raw_json
```

The spec for a `COMMITTEE_REVIEW` row adds: spot at committee time, per-agent reads (toro_read, ursa_read, pythia_read, pythagoras_read, thales_read, daedalus_read), pivot_synthesis, entry_level, stop_level, target_level. This fits in an extended `committee_passes` table alongside the existing `committee_recommendations` shape, or by extending the dead table after running its migration.

**Whether to extend `committee_recommendations` vs create `committee_passes` is a design decision for Phase 1.** Just noting here that `committee_recommendations` table code exists, is already registered as a router, but its backing table was never created.

---

## Pre-flags

### AEGIS
- **REST extension (`POST /api/committee/results`):** Existing auth-gated surface. Extending payload/side-effects is a bounded scope change, not a new attack surface. Lower risk than MCP write tool.
- **`committee_recommendations` table:** Migration never ran. Creating it is additive; if the endpoint has been called against a non-existent table, those calls silently failed (no data was lost, just not captured). Needs verification.
- **A3 writers:** Three new `outcome_source` writers (FWD_RETURN, OPTIONS_PNL, COMMITTEE_REVIEW) all follow the existing guard pattern (`WHERE outcome_source IS NULL`). Not idempotency-breaking.

### Known traps
- **Constraint extension must cover all three new values in one migration.** If two migrations run out of order, a writer firing before the constraint covers its value will cause a CHECK violation. Single migration for all three: `OPTIONS_PNL`, `FWD_RETURN`, `COMMITTEE_REVIEW`.
- **A3's OPTIONS_PNL writer must wait for `b2_status = 'EXITED'`.** The B2 resolver (15-min tick) sets this when BAR_WALK resolves the underlying signal. A3's poller must join on this condition, not just on `options_pnl IS NOT NULL`.
- **`signal_outcomes` is not A3's target table.** It's a bar-walk binary-outcome companion. A3 writes to `signals.outcome_source` + `signals.outcome*` columns, same as the existing BAR_WALK/ACTUAL_TRADE writers. A3 does NOT add rows to `signal_outcomes` — that table is owned by the BAR_WALK resolver.
- **FWD_RETURN horizon choice is locked-in at build time.** Once data starts accumulating, changing the horizon retroactively requires backfill. Nick chooses before code is written.
