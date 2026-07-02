# CC Brief — Triton Track, Step 0: Flow-Feed Health RCA + Whale-Flow Forward-Edge Shadow Logger

**Date:** 2026-07-01 · **Owner:** CC (build) / Claude (verify) / Nick (greenlight gates)
**Status:** SHIPPED — see §9 ship record. Titans-light applied inline (ATLAS: budget/disk · AEGIS: key handling). Shadow-only; full Titans pass waived per scope — Nick may override.
**Parent verdicts:** Olympus system review 2026-07-01 (companion doc) · Triton decision log `committee-reviews/2026-06-16-flow-radar-investigation-and-triton-cleanup.md` · Pass-2 requirement in `strategy-reviews/olympus-edge-review-2026-06-22.md`
**Note:** body below is the original reviewed spec; **§9 Post-P0 amendments supersede the body where in conflict.**

---

## 0. Objective — what this is and is not

Triton (L2) stays PARKED as a strategy. Its **make-or-break premise has never been tested: does whale options flow LEAD price, or is it coincident?** (URSA's provenance demand, 6/16; Pass-2 refinement 6/22: the test must compare *follow-flow-long* vs *fade-exhausted-flow-short*, because whale-follow-megacap-LONG was Nick's worst personal cell.) This brief builds the evidence machine, not the strategy:

1. **Phase 0:** root-cause the flow feed going DARK on 7/1 (flow radar returned 0 events over 8h spanning full RTH) — hard blocker for everything flow-dependent.
2. **Build:** a shadow logger that captures market-wide WHALE flow prints (UW `/api/option-trades/flow-alerts`) with fire-time context, and grades each with direction-adjusted forward returns.
3. **Output:** after n≥150 graded events, a pre-registered study answers follow-vs-fade — that study is Triton's greenlight/kill gate (alongside L1a's n≥250 for the confluence half).

Plain-English framing: before spending premium on "whales move first," we sit in the tree stand and *count* whether they actually do.

## 1. Read FIRST (in order)

1. `docs/uw-integration-audit-2026-06-16-triton-detection.md` — the endpoint audit. Key finding: `/api/option-trades/flow-alerts` is MARKET-WIDE with server-side filters (`min_premium`, `is_sweep`, `is_ask_side`, `is_call`/`is_put`, `newer_than`) → **one call per cycle regardless of universe size.**
2. `docs/codex-briefs/2026-06-15-triton-build-handoff.md` + `committee-reviews/2026-06-16-flow-radar-investigation-and-triton-cleanup.md` — design decisions already locked (universe, v0/v1, provenance requirement). Do NOT re-litigate; this brief implements only the provenance/evidence layer.
3. `scripts/flow_scanner.py` — the Catalyst scanner is the REFERENCE IMPLEMENTATION for whale detection thresholds (dominance gate, premium buckets: small/mid ≥$250K, TSLA-class ≥$750K, mega/index ≥$2M). Port thresholds; do not reinvent.
4. `backend/jobs/uw_flow_poller.py` + `backend/jobs/a3_fwd_return_resolver.py` — existing poller shape and the forward-return grading pattern (batched per-ticker bar fetch, skip-and-retry, direction-adjusted signs verified 6/8).
5. `backend/integrations/uw_api.py` — regular-session `'r'` bars are the ONLY acceptable grading source (see §9.1 for the exact helper).

## 2. Phase 0 — read-only investigation (report findings BEFORE building)

**P0.1 — Flow-radar dark RCA (P1).** On 7/1, `hub_get_flow_radar(lookback_hours=8)` returned 0 events / `flow_data_available:false` across full RTH. Determine which: (a) `uw_flow_poller` loop not running (Railway logs / scheduler registration in `main.py`); (b) UW quota exhausted early (`GET /api/uw/health` history + 429 counts + governor OBSERVE `WOULD-BLOCK` lines, FOREGROUND vs BACKGROUND); (c) Redis key drift (canonical `uw:flow:*` keys empty vs stale); (d) `flow_events` table — row count for 7/1 vs the 6/23 baseline (1,371). Deliver a one-paragraph RCA + fix recommendation. **If the fix is trivial (restart/flag), apply after hours; if structural, STOP and hand back to Nick before proceeding.**

**P0.2 — Endpoint probe.** One manual `/api/option-trades/flow-alerts` call with `min_premium=250000`, ask-side, sweeps-only, `newer_than=<today>`. Record: response shape, alert id field (dedup key), typical result count for one RTH day (row-volume estimate), and quota cost (should be 1 request).

**P0.3 — Disk + migrations.** ATLAS flagged Railway Postgres ~94% full (6/23). Check current usage and confirm the next migration number (last known: 020). **If disk >90%, cap retention at 30d instead of 90d and flag to Nick.**

**P0.4 — Bias-snapshot helper.** Confirm `utils/bias_snapshot.py` (from `36afa09`) can be reused to stamp `bias_level` + `gex_regime` at fire-time as a drop-in. If not drop-in, store nulls in v0 — do NOT scope-creep.

## 3. Build (after P0 findings; small chunks, one commit each)

**B1 — Migration N: `triton_flow_shadow` table.** Columns: `id`, `uw_alert_id` (UNIQUE — dedup/idempotency), `fired_at` (UW timestamp), `ticker`, `direction` ('BULL' = ask-side calls / 'BEAR' = ask-side puts), `premium_usd`, `is_sweep`, `liquidity_bucket` (per flow_scanner buckets), `spot_at_fire`, `chg_pct_day`, `prior_5d_ret`, `is_liquid20` (vs `config/liquid_universe`), `is_megacap_ai` (the 6/16 tight strip list — REQUIRED for the Pass-2 split), `bias_level_at_fire` (nullable), `gex_regime_at_fire` (nullable), `fwd_ret_1d`, `fwd_ret_3d`, `fwd_ret_5d` (nullable until graded), `graded_at` (nullable), `raw` (small jsonb, selected fields only — no full payload dumps), `created_at`. Retention: purge job for UNGRADED rows only; graded rows exempt until the forward-edge doc ships. Daily insert cap 500 rows (disk guard; log + skip beyond cap).

**B2 — Poller: `backend/jobs/triton_shadow_poller.py`.** RTH-only (09:30–16:00 ET gate, same pattern as the b2 resolver), 120s cadence (~195 calls/day), ONE market-wide `/option-trades/flow-alerts` call per tick with server-side filters (`min_premium=250000`, ask-side, sweeps). Tag the call-site **BACKGROUND governor tier** — this must never compete with the committee's FOREGROUND path. Fail-open: any UW error → log WARNING, skip tick, never raise. Dedup via `uw_alert_id` ON CONFLICT DO NOTHING. Compute context fields at insert (spot/chg from the alert payload where present; `prior_5d_ret` from daily bars, cached 1/day/ticker).

**B3 — Grader: NEW module `triton_shadow_grader.py` (extend the a3 PATTERN, do NOT modify a3).** Daily post-close pass: for rows with `graded_at IS NULL` and the horizon bar available, compute direction-adjusted `fwd_ret_{1,3,5}d` from `'r'`-filtered daily closes (BULL = raw return; BEAR = −raw). Batched one bar-fetch per unique ticker. Skip-and-retry when the horizon bar doesn't exist yet. **Writes ONLY to `triton_flow_shadow` columns — the `signals` table is UNTOUCHED. No `outcome_source` writes anywhere.**

**B4 — Health line (the PYTHIA-decay lesson).** Add `triton_shadow: {events_today, last_event_age_seconds}` to `GET /api/uw/health` so THIS feed cannot silently die for 12 days like the MP feed did.

## 4. Guardrails (Titans-light, inline)

- **ATLAS:** BACKGROUND tier only; row cap + retention purge; migration reviewed against disk headroom (P0.3) before apply; budget per §9.2.
- **AEGIS:** `UW_API_KEY` via the existing env-var path only; never logged, never in `raw` jsonb; no new endpoints exposed; poller is outbound-only.
- **Scope:** shadow-only — zero coupling to scoring, pipeline, feed tiers, L1a, committee tools, or UI. No TradingView/Pine work. No Mode A/B strategy logic. No intraday horizons (v1 note only).
- **Repo discipline:** explicit pathspecs, commit msg via `C:\temp\commitmsg.txt`, no push to main 07:30–14:00 MT on trading days. Deploy window: 7/1 after hours or Fri 7/3 (market closed) are both clean.

## 5. Verification (CC runs, Claude independently re-verifies)

1. P0.2 probe row lands in `triton_flow_shadow` via a manual one-shot insert path; re-running the same tick is idempotent (dedup proven).
2. After the first RTH session: `events_today` > 0 in the health line; spot-check 3 rows against the UW web UI (ticker/direction/premium match).
3. Grader sign check on 2 known movers (e.g., a BEAR alert on a name that fell = positive `fwd_ret_1d`) — same discipline as the 6/8 CRCL/PLD gate.
4. `GET /api/uw/health` shows total daily burn within the §9.2 caller quota; zero FOREGROUND contention.

## 6. Success gate — pre-registered analysis (locked NOW so it can't be softened later)

At **n≥150 graded events** (est. 2–4 weeks at 20–100 whale prints/day post-filter), Claude writes `docs/strategy-reviews/triton-forward-edge-<date>.md` testing, on the graded set:
- **H1 (follow):** mean direction-adjusted `fwd_ret_1d/3d/5d` > 0 with t-stats; overall and by liquidity bucket.
- **H2 (fade-exhaustion):** on the subset where `prior_5d_ret` is top-quintile in the alert direction, does FADING beat following?
- **Mandatory splits:** `is_liquid20` vs other · `is_megacap_ai` isolated (Pass-2 6/22: whale-follow-megacap-LONG was Nick's documented worst cell — it must be separated, never blended into the headline number).
- **Verdict semantics:** H1 and H2 both dead → Triton premise KILLED, L2 re-scoped. Either alive → Triton v0 strategy brief is unblocked (still behind the L1a gates per the locked 6/29 verdict).

## 7. Rollback

Single env flag `TRITON_SHADOW_ENABLED` (default true post-deploy) kills the poller; the table is inert data; the grader no-ops on an empty queue. No other system reads this table.

## 8. Out of scope (explicit)

TV alerts / Pine changes · Triton Mode A/B logic · any scoring or pipeline change · L1a modifications · `signals` table writes · intraday forward horizons · dashboards/UI beyond the one health line.

---

## 9. Post-P0 amendments (2026-07-01, applied in the B1–B4 build — SUPERSEDE the body where in conflict)

1. **Grader bar source (supersedes §1.5, §3 B3):** `fetch_daily_ohlc` returns undated arrays — unusable for fire-date → T+N mapping. Built on `get_ohlc("1d")` + the same regular-session `'r'` filter + a `{date: close}` index mirroring a3's `close_index`/`_nth_trading_day` (±1-day tolerance). Same bars, dates attached.
2. **Budget attribution (supersedes §3 B2, §4 ATLAS):** ALL Triton bar-fetches (poller `prior_5d_ret` + grader) tagged to the `triton_flow_shadow` BACKGROUND caller — NOT `ohlc_bars` (already 3,681/1,500 over quota; riding it would break attribution, create enforce-day coupling, and pollute the observe-log evidence). Caller quota **450/day**; QUOTAS sum 17,950, strictly under 18,000. The `ohlc_bars` overage remains a separate, already-owed rebalance ticket.
3. **Retention (supersedes §3 B1 / P0.3):** shipped at 30d ungraded-only (disk unverified at build time). Post-verification via Railway CLI — **postgres-volume 816/5000 MB (16% used); the 6/23 "~94% full" flag was stale** — retention bumped to **90d** (one-line purge-constant change), graded rows exempt until `docs/strategy-reviews/triton-forward-edge-*.md` ships. `pg_database_size` 358 MB at B1.
4. **P0.1 RCA outcome (flow_radar dark 7/1):** transient Upstash/Redis write failure during RTH — poller, UW quota, and `flow_events` all healthy. Not restart-fixable; durable fix routed to `docs/codex-briefs/2026-07-01-flow-radar-db-fallback-minibrief.md` with the locked labeling contract: `source:"db_fallback"` + data age, never fake-fresh.
5. **Ship record:** B1 `d1a1f52` (mig 021 + `init_database()` DDL — repo has no migration runner, tables boot via CREATE TABLE IF NOT EXISTS) · B2 `ecbe7e3` (poller; 50-alert live test) · B3 `2a2ee07` (grader; signs unit-checked) · B4 `e841d56` (health line). Rollback: `TRITON_SHADOW_ENABLED`. Governor sum verified 17,950.
