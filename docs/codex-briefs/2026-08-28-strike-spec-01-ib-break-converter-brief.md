# CC BRIEF — STRIKE-SPEC-01: IB-Break → Shadow Signal Converter

**Date:** 2026-08-28 · **Lane:** 3DTE · **Authority:** R-IV.109 (scope) + R-IV.115(e) (dates) · **Destination:** `docs/codex-briefs/`
**Titans status:** Pass 1 + Pass 2 complete, Nick-approved 2026-08-28. Repo baseline reviewed: `main` @ `ad584b8`. If HEAD has moved past that, re-verify every anchor before editing.
**Spec:** `docs/strike/specs/STRIKE-SPEC-01-ib-break-feed-conversion.md` — this brief SUPERSEDES the spec where they differ (the spec's `status='SHADOW'` assumption, event-store name, and score inputs were revised in review).

---

## Purpose

PYTHIA Pine v2.4 already emits `ib_break_up` / `ib_break_down` events into `pythia_events`; nothing downstream consumes them as a trigger. This build adds a converter job that turns the first qualifying IB-break per ticker/direction/session into a **shadow row** in the existing `signals` pipeline — graded by the canonical 15-min resolver, invisible to every actionable surface — to collect the n≥50 both-direction sample gating STRIKE promotion (target ~09-18, verdict 10-01).

## Binding conditions (Titans, non-negotiable)

1. **Write via `log_signal()` directly. NEVER route through `process_signal_unified()`** — its step-4f conflict check (`backend/signals/pipeline.py:851`) dismisses live opposite-direction rows and makes the `ib_reversal` second emission structurally impossible.
2. Every emitted row carries **BOTH** `status='SHADOW'` **AND** the L0 tag `triggering_factors.l0_shadow.would_suppress=true`. Neither alone covers all read surfaces.
3. `STRIKE_IB_BREAK` is **registered** in `stable_engine/signals_freshness.py` (SLO 5 days, RTH-gated). An unregistered ~1/day source false-pages the persistence watchdog daily.
4. **Per-ticker watermarks ship with the converter** (R-IV.109(c)). Liveness reference = *any* `pythia_events` row for the ticker in the current session (all alert types), NOT IB events only — a balanced day legitimately produces zero IB breaks.
5. **Ticker allowlist is a code constant** (not env, not DB): `QQQ, IWM, SMH, DIA, XLF, XLK, XLE, TLT`. Every entry requires a verified **dedicated per-symbol TradingView alert** (R-IV.109(e)). Nick creates/verifies the five new alerts in parallel; tickers without alert flow simply never emit (watermark grace period covers onboarding).
6. Converter sets `expires_at = entry session + 3 trading sessions`. Promotion-gate analysis treats `outcome_resolved_at > expires_at` as EXPIRED, not WIN/LOSS.
7. **Validation rejects are converter-level log lines + `strike_ib_session_counts.rejects`.** They are NEVER passed to `record_attempt()` as `rejected` — that would page the persistence alarm on correct behavior. `record_attempt()` fires only on actual INSERT attempts (persisted / db-error / dedupe).
8. **No UW calls in the converter, v1.** Gap-vs-ATR and other score inputs are deferred; store raw event fields as metadata only.
9. Shadow-only. Dry-run first RTH session (`STRIKE_IB_DRY_RUN=true` in Railway), then flip off. Kill switch: `STRIKE_IB_ENABLED=false`.

## Pre-flight

1. `git fetch && git status` clean at `C:\trading-hub`; HEAD at or after `ad584b8`. Use `cmd`, not PowerShell, for git.
2. Read `PROJECT_RULES.md` (bulk-checkpoint ban, empty-safe env vars, deployment verification).
3. This change redeploys the Railway service that hosts the FastMCP hub → **prefer pushing outside 09:30–16:00 ET** (hub drops ~60–170s on restart; can interrupt a live Olympus pass).
4. No manual SQL against prod. Tables are created at boot by `init_database()`; the `migrations/*.sql` file is the human record only.
5. Commits: pathspec-only (exact file list in Output spec); message via `git commit -F C:\temp\commitmsg.txt`.

---

## Task 1 — Watermark tables: migration record + DDL mirror

**New file `migrations/027_strike_ib_shadow.sql`** (header comment per `021_triton_flow_shadow.sql` convention — note the no-runner rule and DDL mirroring):

```sql
CREATE TABLE IF NOT EXISTS strike_feed_watermarks (
    ticker              TEXT PRIMARY KEY,
    baseline_sessions   INTEGER NOT NULL DEFAULT 0,   -- distinct sessions with >=1 pythia_events row (any alert_type)
    last_event_ts       TIMESTAMPTZ,                  -- any alert_type
    last_event_session  DATE,
    last_ib_event_ts    TIMESTAMPTZ,                  -- ib_break_* only
    last_signal_ts      TIMESTAMPTZ,                  -- last converted emission
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS strike_ib_session_counts (
    ticker          TEXT NOT NULL,
    session_date    DATE NOT NULL,
    pythia_events   INTEGER NOT NULL DEFAULT 0,
    ib_events       INTEGER NOT NULL DEFAULT 0,
    signals_emitted INTEGER NOT NULL DEFAULT 0,
    rejects         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ticker, session_date)
);

-- DOWN
-- DROP TABLE IF EXISTS strike_ib_session_counts;
-- DROP TABLE IF EXISTS strike_feed_watermarks;
```

**Mirror the two CREATE TABLE statements verbatim in `backend/database/postgres_client.py::init_database()`**, each in its own `try/except` printing a `WARNING:` like the neighbors. Insert immediately **before** this anchor line:

```
        # Brief C v1.1: committee_accuracy view for Phase 4 win-rate measurement
```

## Task 2 — `log_signal()` status parameter (additive, canonical write path)

File `backend/database/postgres_client.py`. Two exact replacements.

**2a — column list + placeholders.** Find:

```
                feed_tier_v2, feed_tier_v2_path, feed_tier_diverged, confluence_badge,
                source
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31, $32,
                $33, $34, $35, $36, $37
            )
```

Replace with:

```
                feed_tier_v2, feed_tier_v2_path, feed_tier_diverged, confluence_badge,
                source, status
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31, $32,
                $33, $34, $35, $36, $37, $38
            )
```

**2b — parameter tail.** Find:

```
            signal_data.get("source") or "tradingview",
        )
```

Replace with:

```
            signal_data.get("source") or "tradingview",
            # $38 STRIKE-SPEC-01: explicit status for shadow emission. Never
            # pass NULL — explicit NULL bypasses the column DEFAULT and the
            # boot-time backfill (line ~675) flips NULL→ACTIVE anyway.
            signal_data.get("status") or "ACTIVE",
        )
```

No other emitter passes `status`, so all existing callers land `'ACTIVE'` — regression check in Done §D4.

## Task 3 — L0 defense-in-depth entry

File `backend/config/l0_routing.py`. Inside the `SUPPRESS_ALWAYS: frozenset[str] = frozenset({` block, add as the first entry:

```
    "STRIKE_IB_BREAK",  # STRIKE-SPEC-01 shadow emission — surface-suppressed, NOT a kill verdict. Converter bypasses the pipeline; this entry is defense-in-depth if anything ever routes the type through it.
```

## Task 4 — Freshness registration

File `backend/stable_engine/signals_freshness.py`, three one-line additions:

- `REGISTERED_CLASSES`: add `"STRIKE_IB_BREAK",`
- `SLO_SECONDS`: add `"STRIKE_IB_BREAK": 5 * 24 * 3600,  # ~1 emission/session; per-ticker watermark (strike_ib_converter) is the real alarm — this is only a total-death backstop that must not page across weekends/holidays`
- `RTH_ONLY_CLASSES`: add `"STRIKE_IB_BREAK"` to the frozenset.

## Task 5 — Converter module `backend/jobs/strike_ib_converter.py` (new)

Contract (CC authors the implementation; docstring must carry the binding conditions):

**Constants / env.**
- `STRIKE_TICKER_ALLOWLIST = frozenset({"QQQ","IWM","SMH","DIA","XLF","XLK","XLE","TLT"})` with comment: *every ticker here MUST hold a verified dedicated per-symbol TradingView alert (R-IV.109(e)); prey-list/watchlist coverage is never a valid upstream. Adding a ticker without a dedicated alert violates the ruling.*
- `STRIKE_IB_ENABLED` / `STRIKE_IB_DRY_RUN`: empty-safe pattern `(os.getenv("X") or "default")` — enabled default `"true"`, dry-run default `"false"`.
- `SESSION_CAP = 2 * len(STRIKE_TICKER_ALLOWLIST)` (structural max: one per ticker per direction). Emissions-this-session ≥ cap ⇒ dedup is broken ⇒ stop emitting, `send_alert` once (latched).

**Loop.** `strike_ib_converter_loop()`: sleep 300s at boot, then every 300s; run only weekdays 09:30–16:05 ET (`zoneinfo`, mirror `pythia_staleness_watchdog_loop` style). Skip everything when `STRIKE_IB_ENABLED` is false.

**Read.** `SELECT id, ticker, alert_type, price, volume_quality, ib_high, ib_low, timestamp FROM pythia_events WHERE alert_type IN ('ib_break_up','ib_break_down') AND timestamp > NOW() - INTERVAL '2 hours' AND ticker = ANY($1) ORDER BY timestamp`. (Idempotency comes from the signal_id, not from tracking a read cursor — replays and restarts are absorbed by ON CONFLICT.)

**Session math.** Reuse `_current_session_date` / `_prev_weekday` from `services/read_only/market_profile.py` — do NOT re-derive weekday arithmetic. Session date = event `timestamp` converted to `America/New_York`.

**Validation gate (AEGIS A1/A2/A3)** — reject with reason, count in `strike_ib_session_counts.rejects`, log ticker+reason only, never `record_attempt`:
- ticker not in allowlist (should be impossible given the query; keep the guard)
- `ib_high` or `ib_low` NULL; `ib_height = ib_high - ib_low <= 0`
- `price` NULL or outside `[0.8*ib_low, 1.2*ib_high]`
- `ib_height > 0.05 * price`
- direction derives from `alert_type` ONLY (`ib_break_up`→LONG, `ib_break_down`→SHORT); ignore payload `direction` field
- never copy `raw_payload` into the signal row

**Emission.** `signal_id = f"STRIKE_IB_{ticker}_{session_date:%Y%m%d}_{'UP' if long else 'DOWN'}"` — dedup (first per ticker/direction/session) and webhook-replay idempotency are the same mechanism via `log_signal()`'s `ON CONFLICT (signal_id) DO NOTHING`. Do not pre-check existence; attempt the insert and read the boolean.

signal_data fields: `timestamp` = event `timestamp`; `strategy='STRIKE_IB_BREAK'`; `signal_type='STRIKE_IB_BREAK'`; `source='STRIKE_IB_BREAK'`; `asset_class='EQUITY'`; `direction` LONG/SHORT; `entry_price=price`; `stop_loss = (ib_high+ib_low)/2`; `target_1 = entry ± 0.5*ib_height`; `target_2 = entry ± 1.0*ib_height` (sign by direction); `risk_reward` computed; `timeframe='1-3D'`; `status='SHADOW'`; `feed_tier='research_log'`; `expires_at` = 3 trading sessions after session_date at 20:00 UTC (weekday-increment loop; holidays unmodeled, same approximation as the session helpers); `notes='STRIKE-SPEC-01 shadow — not actionable'`.

`triggering_factors` (pass explicitly so `log_signal` doesn't build one):

```python
{
  "l0_shadow": {"v": 1, "mode": "enforce", "signal_type": "STRIKE_IB_BREAK",
                 "rule": "SUPPRESS", "would_suppress": True, "is_liquid": None,
                 "reason": "STRIKE shadow emission — not promoted"},
  "strike": {"pythia_event_id": id, "ib_high": ..., "ib_low": ..., "ib_height": ...,
              "volume_quality": ..., "event_ts_et": "...", 
              "stop_variant_opposite_extreme": ib_low_or_high,   # conservative-stop comparison at promotion review
              "ib_reversal": bool}   # true iff opposite-direction STRIKE signal_id already inserted this session
}
```

After a **true** insert: `record_attempt("STRIKE_IB_BREAK", True)`, call `write_signal_outcome(signal_data)` (import from `signals.pipeline`) so `signal_outcomes` gets its PENDING row, bump `signals_emitted` + `last_signal_ts`. On insert exception: `record_attempt("STRIKE_IB_BREAK", False, str(e))`. On dedupe (returned False): `record_attempt("STRIKE_IB_BREAK", False)` — counted as `deduped`, never a gap. **Dry-run:** log the fully-assembled row at INFO with prefix `STRIKE DRY-RUN would emit:` and skip insert/outcome/counters (except `ib_events`).

**Watermarks (every cycle, cheap).** For each allowlist ticker: upsert `strike_feed_watermarks` from `pythia_events` MAX(timestamp) any-type + ib-only; maintain `baseline_sessions` (increment when a new `last_event_session` is observed); upsert today's `strike_ib_session_counts.pythia_events`. **Alarm rule:** after 11:00 ET, if `baseline_sessions >= 3` AND no `pythia_events` row for the ticker in the current session ⇒ `send_alert("🚨 STRIKE watermark: {ticker} silent this session", ...)` with Redis latch `alarm:strike_watermark:{ticker}` (TTL 7200), clear-notify on recovery — mirror `pythia_staleness_watchdog_loop` latch mechanics exactly. This is intra-session and per-ticker; the existing session-day watchdog is unchanged and complementary.

## Task 6 — `main.py` wiring

- After anchor `    adx_regime_task = asyncio.create_task(adx_regime_loop())` add:
  `    strike_ib_task = asyncio.create_task(strike_ib_converter_loop())  # STRIKE-SPEC-01 shadow converter + per-ticker watermarks`
  with the import `from jobs.strike_ib_converter import strike_ib_converter_loop` placed beside the other job imports in that function.
- After anchor `    signals_freshness_task.cancel()  # DEF-SIGNAL-PERSISTENCE-COLLAPSE watchdog` add `    strike_ib_task.cancel()`.

## Task 7 — Tests

`backend/tests/jobs/test_strike_ib_converter.py` (follow existing test conventions): signal_id/dedup format; each validation reject rule; direction from alert_type (payload direction ignored); reversal tagging; stop/target math both directions; expiry Fri→Wed weekday roll; dry-run performs no insert; cap halt. Pure-function tests — no live DB.

## Task 8 — Deploy + verification (per PROJECT_RULES Deployment Verification — a brief is not complete until D3 is empirical)

1. Set `STRIKE_IB_DRY_RUN=true` in Railway BEFORE pushing.
2. Push (prefer outside RTH). `railway deployment list` → SUCCESS; deploy SHA == commit SHA.
3. Empirical: boot logs show the loop started; `/health` `signals_freshness.classes.STRIKE_IB_BREAK` present with `"registered": true`, status `ok`, no `any_flatline` regression.
4. Observe one full RTH session in dry-run: `STRIKE DRY-RUN would emit:` lines sane (levels, direction, dedup), zero rows landed.
5. Nick unsets `STRIKE_IB_DRY_RUN` (redeploy) → first live session checks in Done.

## Output spec

Files (the complete pathspec for `git add`):
```
migrations/027_strike_ib_shadow.sql
backend/database/postgres_client.py
backend/config/l0_routing.py
backend/stable_engine/signals_freshness.py
backend/jobs/strike_ib_converter.py
backend/main.py
backend/tests/jobs/test_strike_ib_converter.py
docs/codex-briefs/2026-08-28-strike-spec-01-ib-break-converter-brief.md
```
Commit message (write to `C:\temp\commitmsg.txt`):
```
feat(strike): SPEC-01 IB-break shadow converter + per-ticker watermarks

Converts first ib_break_up/down per ticker/direction/session from
pythia_events into status=SHADOW rows via log_signal (pipeline bypassed
per Titans F1). L0-tagged, freshness-registered, expires_at horizon,
dedicated-alert allowlist per R-IV.109(e), watermarks per R-IV.109(c).
Shadow-only; dry-run gated; no UW calls; no live-surface visibility.
```

## Gates / what NOT to do

- NO routing through `process_signal_unified()`; NO calls into scoring/enrichment.
- NO UW API calls anywhere in the converter.
- NO changes to `backend/webhooks/pythia_events.py`, webhook endpoints, Pine scripts, UI, or live scoring.
- NO `git add .` / `-A` — pathspec list above only; credential pattern-scan the staged paths first (counts only).
- NO manual prod SQL beyond the read-only verification queries in Done.
- Defects encountered are ticketed, not fixed (F6 duplicate pythia_events DDL, F7 HG_1H conflict exposure, AEGIS `vps_api_key` seed — all already ticketed by the review).

## Done definition

- D1. All tests green locally; deploy verified per Task 8 (steps 1–4).
- D2. Dry-run session reviewed by Nick; `STRIKE_IB_DRY_RUN` unset.
- D3. First live session, empirical: `SELECT signal_id, status, expires_at::text FROM signals WHERE source='STRIKE_IB_BREAK'` shows rows, all `status='SHADOW'`, `expires_at` populated; matching `signal_outcomes` rows `outcome='PENDING'`.
- D4. Regression: `SELECT status, count(*) FROM signals WHERE created_at > NOW() - INTERVAL '1 day' AND source <> 'STRIKE_IB_BREAK' GROUP BY 1` — distribution unchanged (no non-STRIKE SHADOW rows).
- D5. Zero-leak surface audit — each returns **zero** STRIKE rows: `/api/trade-ideas` grouped + list, feed_service Discord query, `get_active_trade_ideas`, `get_signal_queue`, board_state strip, committee-bridge queue.
- D6. Resolver pickup: within a session, at least one STRIKE row shows `outcome` populated or remains cleanly unresolved with no resolver errors in logs.
- D7. Watermark rows exist for all 8 tickers; no false watermark alarms across one weekend boundary.
- D8. Closure note in `docs/strategy-reviews/` (what shipped, deltas from brief, F-ticket references).

## Olympus Impact

**None.** No MCP tools added/changed, no committee skill or data source touched, no connector-manifest refresh needed. PYTHIA's read paths (`hub_get_market_profile`, scoring Tier-3) are untouched.

## Rollback

`STRIKE_IB_ENABLED=false` (no redeploy needed once read at next cycle — set var, restart service) → converter inert. Full removal: revert the commit; tables dropped via the migration's `-- DOWN` block when convenient (inert if left).
