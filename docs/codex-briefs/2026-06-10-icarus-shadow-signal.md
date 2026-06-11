# ICARUS — B3 0DTE Shadow Signal (v1)

**Date:** 2026-06-10
**Status:** Approved by Titans pass (no vetoes). BUILD GATED on: B4 Chunk D
regression complete + webhook-hardening brief shipped.
**Bucket:** Tactical (short-cycle). Defers Sub-brief 3 start by one cycle
(Nick-approved 2026-06-10).
**Mode:** SHADOW ONLY. No production trades, no Insights rows, no UI, no
execution path. INSERT-only writes.

## Context / Validation

Olympus double pass (2026-06-10) on 0DTE strategy concept returned
WAIT-FOR-SHADOW-VALIDATION. Live worked example same day: PYTHIA webhook
fired ib_break_down @ 731.39 (SPY); session closed 722.92 (low 721.23).
Titans Pass 1+2: ATLAS HIGH (conditional), AEGIS HIGH (conditional),
HELIOS HIGH, ATHENA HIGH / PROCEED.

## Phase 0 — Read-only gates (ALL must pass before any code)

1. **signal_outcomes constraint check.** Inspect schema: does a CHECK
   constraint or enum restrict `outcome_source` values? Record allowed
   values. If constrained, the migration in Phase 1 must extend it.
   Also check whether a JSONB context/metadata column exists for the
   feature snapshot; if not, Phase 1 adds one.
2. **pythia_events data quality.** Run `scripts/phase0_events_verify.py`
   against pythia_events: row counts by day, event types present,
   per-session event cadence. Specifically resolve the 2026-06-10
   single-event-then-quiet question (one ib_break_down at 15:10 UTC,
   nothing after). Determine: event-driven by design, or dropped alerts.
   (Overlaps B4 Chunk D regression — run once, use for both.)
3. **UW endpoint verification.** Against the UW OpenAPI spec, confirm
   exact paths + payload shapes for (kebab-case convention):
   - GEX by strike / spot exposures (gamma flip level, call/put walls)
   - market tide (aggregate net call/put premium)
   - net premium ticks (SPY)
   - flow alerts (SPY sweeps)
   - dark pool prints (SPY)
   Record verified paths in this brief before Phase 1. Do NOT guess
   endpoints. Respect /option-contracts 500-cap rules where relevant.

## Phase 1 — Build scope

### New job: `backend/jobs/icarus_signal.py`
Railway-side, following the `backend/jobs/outcome_resolver.py` pattern
(get_postgres_client(), envelope/error conventions). Scheduled during RTH
only; evaluation window 10:00–11:30 ET. SPY ONLY in v1.

### Signal gates (ALL must pass to emit)
1. **Regime:** bias composite gex_regime == MOMENTUM at evaluation time.
2. **Structural trigger:** new pythia_events row for SPY with event type
   ib_break_up or ib_break_down (current session).
3. **Confirmation:** no IB re-entry within 15 minutes of the break
   (price has not crossed back inside ib_low..ib_high). Direction = break
   direction.
4. **Volume pacing (time-normalized):**
   session_volume / (avg_volume_30d * elapsed_session_fraction) >= 1.0
   where elapsed_session_fraction = minutes since 09:30 ET / 390.
5. **Time window:** confirmed trigger lands 10:00–11:30 ET. Outside = no
   signal, log gate state.
6. **Calendar gate (fail-closed):** query Hermes alerts for same-day
   CPI/FOMC/NFP/major scheduled releases. Release later today and not yet
   out = no signal. Hermes unreachable = NO SIGNALS TODAY (fail closed).
   OpEx Friday = emit allowed but tag mechanical_flow_risk=true.

Flow-radar gate: EXPLICITLY DEFERRED TO v2 (radar dark on SPY as of
2026-06-10).

### Emission (INSERT-only)
- Write to `signal_outcomes` with `outcome_source = 'SHADOW_0DTE'`
  (final value pending Phase 0 constraint check; follow the
  PROJECTED_FROM_BAR_WALK precedent of distinct source values —
  see backend/jobs/score_signals.py:221-222 overwrite-guard pattern).
- NEVER UPDATE existing rows. Never overwrite ACTUAL_TRADE. New source
  value must be excluded from all BAR_WALK-filtered aggregate queries.
- NO rows written to `signals` / Insights feed. Hard constraint
  (HELIOS/ATLAS agreed): shadow signals must not surface on the
  dashboard pre-promotion.

### Feature snapshot at trigger (logged, NOT gated — Nick injection)
Per-signal JSONB snapshot from UW at emission time:
- gamma flip (zero-gamma) level; nearest call wall and put wall strikes
  + distance from spot
- market tide direction; SPY net premium ticks (recent window)
- recent SPY sweep/flow alerts summary
- dark pool prints near trigger level (count + notional)
Purpose: at n>=30, promotion analysis tests which features separate
winners from losers; v2 reversal trigger is designed from this evidence.
3-5 UW calls per signal max — trivial vs 120 req/min Basic-plan limit.

### Outcome walk (v1 = underlying points, not option pricing)
- Walk trigger price -> RTH close. Record close-vs-trigger points,
  MFE, MAE (in underlying points, direction-signed).
- Modeled exit: IB re-entry after confirmation = exit at that price,
  outcome capped there (failed-break rule). Record exit_reason.

### Migration (if Phase 0 shows schema gaps)
Single migration: extend outcome_source constraint + add nullable JSONB
feature_snapshot column. MUST include explicit -- DOWN rollback block
(ATLAS hard rule).

### Audit logging (AEGIS requirement)
Append-only log line per evaluation cycle AND per emission: timestamp,
all six gate states, source pythia_events row id, emitted yes/no.
Pattern-consistent with committee_audit.log.

## Hard constraints
- SPY only. No QQQ in v1.
- Shadow only: no execution, no sizing automation, no UI, no Insights.
- Deploy outside market hours (7:30 AM–2:00 PM MT blackout); verify
  post-deploy with hub_get_bias_composite retry after 70-170s.
- No new credentials. Reuses UW_API_KEY (Railway env var). No new
  webhook surface — consumes existing pythia_events table only.
- Sequencing: do NOT start until B4 Chunk D regression is confirmed
  and the webhook-hardening brief has shipped (AEGIS: spoofed events
  must not be able to feed the signal log).

## Done definition
- Phase 0 results recorded in this brief (constraint values, feed
  cadence answer, verified UW endpoint paths).
- icarus_signal.py deployed and running on RTH schedule.
- Either: first SHADOW_0DTE rows present in signal_outcomes with
  feature snapshots, OR zero-signal days logged with full gate states
  in the audit log (a no-signal day with clean logs counts as working).
- Migration applied with rollback path documented (if needed).

## Olympus impact
PYTHIA-adjacent consumer (reads pythia_events). Post-build: full
Olympus committee pass on SPY required (standing rule for anything
touching PYTHIA/Insights-adjacent surfaces). PYTHIA SKILL.md gains a
B3-0DTE cross-reference at PROMOTION, not v1. PIVOT/B3 sizing rules
unchanged until promotion.

## Promotion gate (out of build scope; recorded for the record)
n >= 30 emitted signals; positive expectancy after modeled spreads;
leave-one-out robustness spirit per 3-10 precedent. Until then ICARUS
produces zero trades.

## v2 candidates (NOT in scope)
- Reversal trigger class: sweep+reclaim at GEX wall + tide divergence
  (design from v1 feature-snapshot evidence).
- QQQ. Option-proxy pricing for outcome realism. Flow-radar gate once
  SPY radar feed is fixed. Native day-type from Pine when computed.

## Changelog
- 2026-06-10: Drafted from Olympus double pass + Titans pass.
- 2026-06-10 (Nick injections): name = ICARUS; feature-snapshot
  logging added (UW dark pool / GEX-by-strike / tide / net prem /
  sweeps); calendar gate = Hermes, fail-closed (default, changeable).
