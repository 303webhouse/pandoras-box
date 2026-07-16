# Brief S-3 — Stater Swap v2: Keep-List Upgrades (R-2)

**Date:** 2026-07-16 | **Executor:** Claude Code | **Coordination:** Fable (Nick's coordination lane)
**Repo path for this brief:** `docs/codex-briefs/2026-07-16-stater-swap-s3-keep-list-upgrades-brief.md`
**Predecessor:** S-2 (R-1 Regime & Session) — CLOSED. Completion report: `docs/strategy-reviews/stater-swap-redesign/s2-phase1-5-completion-report.md` (14/14 Done). Independent cross-lane verification: `s2-crosslane-verification.md` (commit `b8149c6`) — live REST corroboration, scheduler autonomy confirmed.
**Sources (binding, in priority order):**
1. `docs/strategy-reviews/stater-swap-redesign/2026-07-12-stater-swap-v2-committee-brief.md` — Part 4 R-2 + Addendum A (D3 clarification, A-2 tiers, A-4 risk flags, A-5 Cycle Extremes scope)
2. Titans Review Record 2026-07-13 (`docs/strategy-reviews/stater-swap-redesign/2026-07-13-titans-review-stater-swap-v2.md`) — S-3 carry-forward row + standing rows, quoted verbatim in §A1
3. `PROJECT_RULES.md` — Data Source Hierarchy (crypto rows), Deployment Verification, Development Principles, Anti-Bloat Framework
4. `docs/strategy-reviews/stater-swap-redesign/symbol-capability-matrix.md` + `backend/config/crypto_symbol_matrix.py` — per-symbol coverage is the authority for every cell this brief ships
5. `s2-phase1-5-completion-report.md` §Standing items — inherited obligations (bypass-retirement tracker, §10 shadow bar)

**Titans status:** Full Pass 1 / Pass 2 / ATHENA Overview completed 2026-07-13 (no vetoes, PROCEED, HIGH). This brief received its Titans **final review** in the coordination lane on 2026-07-16 — verdicts and amendments FA-1..FA-6 embedded in §11. No further review gate before CC execution.

## Mission

R-2 upgrades the two keep-list features Nick named, on top of the S-1/S-2 foundation: (1) **Bottom Signals become the Cycle Extremes dial** — two-sided positioning thermometer (CAPITULATION ⟷ FROTH), per-symbol under the capability matrix, every cell carrying an honest staleness contract; (2) **CVD gets event-ized** — spot-vs-perp split, tape-health state, and divergence/absorption events anchored to profile levels, landing in the signal feed as governed, shadow-tagged, outcome-tracked signals. Plus the two items S-1 slotted for R-2: **canonical ticker normalization at pipeline ingress** and the **MATIC/UNI/APT delisting cleanup**. Data layer only — S-6 renders; this brief ships payloads.

---

## §A1 — Binding carry-forwards & inherited obligations (verbatim where quoted)

**Titans S-3 carry-forward (HELIOS lane, binding):**
> Cycle Extremes: staleness contract on every signal cell; FROTH copy reads "reduce new risk," never "sell"; dial rendered as single-axis marker, not two tables (mockup decision)

S-3 ships the *payload* side of that obligation: per-cell staleness fields, canonical copy strings, and a single-axis composite value in the payload contract. S-6 renders; the UI never authors copy or computes time.

**Titans standing rows that fire on this brief:**
> Post-R-2 checkpoint: reassess rebuild-stack L1 vs. R-3/R-4 before proceeding (ATHENA)
> Olympus Impact section + connector re-toggle + BTC/SPY committee re-test on every brief that ships hub MCP tools (ATHENA)

This brief ships one hub MCP tool (§6.3) → the second row fires in full (§10). The first row fires at completion: **no S-4 authoring until the checkpoint is recorded** (§7.4).

**Committee Addendum A, D3 clarification (binding semantics):** the dial measures **positioning extremes in both directions** — a thermometer (crowding), deliberately separate from the speedometer (momentum = S-2's regime classifier + the R-4 OI×price chip). CAPITULATION = B1 accumulation-timing context; FROTH = risk-reduction/sizing context; **neither column auto-generates scalp signals.** The dial writes zero rows to the signal feed — asserted by test (§9 Done-9).

**Committee Addendum A-5 (per-symbol scope):** full two-column dial for BTC/ETH; partial dials elsewhere only where inputs exist per the capability matrix (funding/OI/liquidation-class cells compute for all six; skew/basis cells N/A outside coverage). The payload's per-symbol header states its coverage. **Never fake-neutral, never silently blank** — N/A is an explicit state with a reason.

**A-4 risk flags that shape staleness states:** HYPE's single-venue concentration means venue outage must surface as a visible staleness/degraded state, not a stale-but-confident value. ZEC/FARTCOIN Tier-3 constraints are unchanged by this brief (no new strategy enrollment here — that's S-4).

**Inherited from S-2's completion report (standing items):**
- **Bypass-retirement tracker:** before touching `backend/scheduler/bias_scheduler.py`, run `scripts/crypto_dual_write_diff_report.py` and record its output in the Phase-0 findings (S-1 standing instruction; 3 test-only rows as of S-2).
- **§10 shadow-validation bar is untouched:** `gating_enabled` stays `false`; nothing in S-3 modifies gate behavior, thresholds, or the S-2 shadow dataset's accrual. S-3's shadow CVD events will *themselves* accrue `crypto_gate_shadow` rows — that is expected and desirable.

**Hierarchy hard rules (PROJECT_RULES):** sanctioned crypto vendors only (Coinalyze / Deribit / OKX-fallback / DeFiLlama per the S-1 matrix decisions) — **zero new vendors, zero new UW polling in S-3** (signal #10's UW ETF-flow feed is explicitly deferred, §4.6). yfinance never enters a hot path; Polygon/FMP banned.

---

## §1 — Phase 0: read-only reconnaissance (no code changes; findings committed first)

Commit findings as `docs/strategy-reviews/stater-swap-redesign/s3-phase0-findings.md` with **file:line evidence** for every item. If any finding contradicts this brief's assumptions, STOP and flag to Fable before Phase 1.

- **1.1** `backend/bias_filters/btc_bottom_signals.py` + `backend/api/btc_signals.py`: enumerate all 9 signal computations, their data clients, current compute cadence/trigger, current staleness handling (if any), and the exact response shape the legacy frontend consumes today.
- **1.2** Locate the froth-side inputs already present in existing client logic (quarterly basis, 25Δ call-skew, funding, OI) — exact functions/fields per client, per symbol, cross-checked against the capability matrix. Record which froth cells are computable per symbol *today* with zero new polling.
- **1.3** `backend/strategies/btc_market_structure.py`: CVD gate internals, spot/perp data sources actually live from Railway (matrix is authority; Binance geo-block → OKX decisions from S-1 apply), profile computation (POC/VAH/VAL), and the −45..+35 score coupling (which S-3 must NOT alter).
- **1.4** Session-extreme availability: can current-partition session high/low be derived from existing bars + `backend/utils/crypto_sessions.py` without new plumbing? Record yes/no — §5.3 adapts.
- **1.5** Ticker ingress sites: re-verify the three crypto signal sources' `ticker` write points (`crypto_setups.py` → `BTCUSDT`, Crypto Scanner → `BTC-USD`, TradingView webhook → raw alert format) and the `normalize_crypto_ticker()` signature in `backend/jobs/crypto_bars.py`. Confirm the TV webhook's HMAC verification point relative to where normalization would apply (FA-3).
- **1.6** `CRYPTO_TICKERS` blast radius: every usage site; then run the FA-1 pre-flight — `SELECT` for open positions and unresolved signals referencing MATIC-USD / UNI-USD / APT-USD. Record counts.
- **1.7** Known-red baseline: record the current FAILED test names + count (expected: the same 18 environmental reds S-2 recorded, byte-for-byte).
- **1.8** Bypass-retirement tracker: run `scripts/crypto_dual_write_diff_report.py`, record row count and composition before any `bias_scheduler.py` touch.
- **1.9** Hub MCP registry pattern: how the v2.0 envelope tools register (S-2/Brief-3 precedents), where the equity `hub_get_market_profile` lives, and what the asset-class guard consistency requires for §6.3.
- **1.10** `/api/crypto/state/{symbol}`: the exact `_NOT_YET_BUILT_R1` placeholder fields and where real regime/session/cycle references wire in (§6.2).

## §2 — Docs tasks

- **D-1 (at completion, not before):** append one line to `docs/strategy-reviews/stater-swap-redesign/helios-mockup-track.md` Log. Exact anchor — find:
  `- 2026-07-15 — Track opened; charter committed; seed directions C1–C3 recorded. Next entry: concept session scheduled.`
  append after it: `- <ship date> — S-3 payload contracts live (/api/crypto/cycle-extremes, /tape-health, hub_get_crypto_market_profile, /state wiring). Concept-session prerequisite met per charter timing; session may be scheduled.`
- **D-2:** `docs/build-backlog.md` — mark Tier 2 #6 (`is_crypto_ticker()` hyphen miss) CLOSED with this brief's Phase-1 commit ref; add one line under S-5 scope noting Cycle Extremes signal #10 (UW ETF-flow exhaustion) is deferred there pending ATLAS budget sizing against the 17K/18K watchdog thresholds.

---

## §3 — Phase 1: canonical ticker normalization at ingress + delisting cleanup

- **3.1** Apply `normalize_crypto_ticker()` (reuse as-is from `backend/jobs/crypto_bars.py` — proven in F-2; do not fork a second normalizer) at the point each of the three crypto signal sources writes its `ticker` field. Normalization happens at **ingress**, upstream of `is_crypto_ticker()` and all downstream consumers.
- **3.2** TV webhook path (FA-3, AEGIS): normalization applies **strictly after** HMAC signature verification succeeds. The signature/verification code path is untouched — Done-4 carries a grep-proof.
- **3.3** **No historical mutation.** Existing `signals` rows keep their as-written tickers; conflict-dismissal correctness is go-forward only. No backfill migration ships in S-3.
- **3.4** MATIC/UNI/APT resolution: if the FA-1 pre-flight (§1.6) returns **zero** open positions and zero unresolved signals → remove the three from `CRYPTO_TICKERS` (they are yfinance-delisted and outside the six-symbol v2 universe), recording the prune + rationale in the findings doc. If pre-flight returns **nonzero** → STOP, flag to Fable with the rows; do not prune.
- **3.5** Tests: normalization idempotence; three-source same-coin canonical equality (constructed rows — no live emissions needed); a cross-source conflict-dismissal unit test proving `_check_and_clear_conflicting_signals()`'s exact-string match now catches the same coin across engines *given canonical tickers* (the function itself is not modified).
- **3.6** `bias_scheduler.py` may only be touched after §1.8's tracker output is recorded in the findings doc.

## §4 — Phase 2: Cycle Extremes engine (data layer; no UI; no feed writes)

- **4.1** Migration `migrations/026_crypto_cycle_cvd.sql` (explicit `-- DOWN` block): `crypto_cycle_config` (append-only version rows — INSERT new versions with `created_by`, never UPDATE, matching `crypto_gate_config` precedent, FA-6), `crypto_cycle_log` (per-evaluation composite + cells, mirrors `crypto_regime_log` shape), `crypto_tape_health_log` (§5). Mirror DDL + idempotent seed in `postgres_client.py` per S-2 precedent; seed row `created_by='SEED_S3'`.
- **4.2** Per-cell staleness contract — **every** cell in the payload carries: `{value, state, as_of, stale, source, reason?}` where `state ∈ {LIVE, STALE, NA, DEGRADED}`. Staleness thresholds per source cadence live in `crypto_cycle_config` (hot-reloadable via a `crypto_cycle_loader.py` mirroring `crypto_gate_loader.py` — mirror, don't refactor the S-2 loader). N/A cells carry a stated `reason` (e.g., `NO_DERIBIT_COVERAGE`), never zeros or nulls.
- **4.3** CAPITULATION column: the existing 9 bottom signals, computations **unchanged** — wrapped with the §4.2 contract. No retunes in S-3 (retunes are S-4).
- **4.4** FROTH column: four signals from data already flowing — quarterly basis extreme (config default: >10%, per matrix coverage), 25Δ call-skew extreme (Deribit, BTC/ETH), positive funding blowout, OI extreme. All thresholds config-driven in `crypto_cycle_config`. Per-symbol per the matrix; honest N/A elsewhere.
- **4.5** Composite: single-axis score (−100 CAPITULATION ⟷ +100 FROTH) per symbol, computed from active LIVE cells only; payload documents the method (`composite_method` field) and flags `degraded=true` when fewer than a config-set minimum of cells are LIVE. Per-symbol coverage statement in the payload header (A-5).
- **4.6** Signal #10 (ETF-flow exhaustion, UW-fed): **deferred to S-5** per the Titans S-5 carry-forward (UW ETF-flow polling must be budget-sized by ATLAS before enablement). The payload ships the structural slot as `state=NA, reason=DEFERRED_S5_BUDGET_SIZING`. Zero UW polling ships in S-3.
- **4.7** Canonical copy strings as module constants, carried in the payload: FROTH context copy = "reduce new risk" (the string "sell" must not appear in any FROTH copy — Done-8 greps for it); CAPITULATION context copy = "B1 accumulation-timing context". The UI renders these; it never authors them.
- **4.8** Cadence: hourly evaluation job registered alongside the S-2 regime slot pattern (own job id, own status entry); writes `crypto_cycle_log`; the endpoint serves the latest row with its staleness contract. Failure isolation: an evaluator exception never breaks the scheduler loop (mirror the S-2 failure-injection test pattern).
- **4.9** The dial writes **zero** rows to `signals` (D3 rule). Assertion test + Done-9 live check.

---

## §5 — Phase 3: CVD split, tape-health, and event detection (shadow-first)

- **5.1** Spot-vs-perp CVD split per symbol, computed from **already-sanctioned, already-flowing** feeds only (matrix + §1.3 findings decide the exact sources; Binance-geo-block → OKX decisions from S-1 apply). Coverage follows the matrix: symbols lacking a live spot or perp flow feed get explicit N/A tape-health states, no events. **Hard stop:** if Phase 0 finds no live spot-flow source for BTC itself from Railway, halt Phase 3 and flag to Fable — do not improvise a new vendor.
- **5.2** Tape-health state per covered symbol: `SPOT_LED / PERP_LED / MIXED` + slope, persisted to `crypto_tape_health_log` on the 5-minute crypto scan cadence, with the §4.2 staleness contract on the payload. Classification thresholds live in `crypto_cycle_config` (hot-reloadable).
- **5.3** Event detection — divergence and absorption events, anchored **only** at structural levels: the Market Structure Filter's POC/VAH/VAL plus current-partition session extremes if §1.4 found them derivable without new plumbing (if not: profile levels only in S-3, session-extreme anchoring recorded as a one-line follow-up in D-2 — no scope invention). Event types and thresholds enumerated in config; no free-floating "CVD moved a lot" events.
- **5.4** Events land in the signal feed **through the real pipeline**: `process_signal_unified()` only — no `log_signal` side door (L0 is settled law post-F-4). Shadow-tagged signal types (`CVD_DIVERGENCE`, `CVD_ABSORPTION`), `asset_class=CRYPTO`, canonical ticker (Phase 1 dependency — Phase 3 does not start until Phase 1 lands).
- **5.5** FA-2 (ATLAS): every event signal carries the BAR_WALK-resolvable field set (canonical ticker, direction, reference price, config-driven expiry — default 24h) so the S-1 F-2 outcome machinery grades them automatically. Validation accrues from day one; these events will also correctly accrue S-2 `crypto_gate_shadow` rows — expected, desirable, untouched.
- **5.6** The existing −45..+35 Market Structure Filter score coupling is **not modified** in S-3. Retunes are R-3/S-4 territory.
- **5.7** Dedup/cooldown: per-symbol, per-event-type, per-level cooldown window (config-driven) using a `signals` lookback — no new dedup table.

---

## §6 — Phase 4: surfaces (REST + hub MCP)

- **6.1** REST (unauthenticated read-only, per the S-2 Amendment-E precedent), added to `backend/api/crypto_market.py`:
  - `GET /api/crypto/cycle-extremes` (all six symbols; optional `?symbol=`) — per-symbol composite + full cell set with staleness contracts + coverage header + canonical copy strings.
  - `GET /api/crypto/tape-health` (optional `?symbol=`) — tape state + slope + staleness; N/A states for uncovered symbols.
- **6.2** Wire `/api/crypto/state/{symbol}`'s `_NOT_YET_BUILT_R1` placeholder fields to the real S-2 regime/session data plus a reference to the new cycle payload. **Scope note (FA-5, ATHENA):** this is the absorbed micro-item S-2's completion report explicitly flagged as the obvious follow-up — acknowledged here as a named delta, not silent creep.
- **6.3** Hub MCP tool `hub_get_crypto_market_profile`: exposes the Market Structure Filter's levels (POC/VAH/VAL + session extremes where available) per crypto symbol — PYTHIA parity per the committee brief. v2.0 envelope, staleness/degraded states, asset-class guard behavior consistent with `hub_get_crypto_quote` (bare ambiguous tickers error with candidates, never silently resolve). Registered in the v2.0 registry; **no new UW draw** — the tool serves internally computed levels.
- **6.4** FA-4 (HELIOS): **zero breaking changes** to existing `/api/btc/signals` (legacy Stater tab keeps working until S-6 ports it). All new payloads are new endpoints. Payload contract examples (one real captured response per new endpoint + the MCP tool) go into the completion report — the HELIOS mockup session draws from committed contracts, not imagined shapes.

## §7 — Phase 5: verification, completion, and the checkpoint gate

- **7.1** Tests: everything in §3.5/§4.8/§4.9/§5.5 plus the known-red baseline byte-diff (§1.7 baseline unchanged post-build; new tests added on top are counted).
- **7.2** Deployment verification, all 4 PROJECT_RULES steps: (1) Railway deploy SUCCESS; (2) direct evidence the new code is live; (3) empirical side effects — tables exist via `information_schema`, config seeded, one live cycle evaluation with distinct per-symbol values + honest N/A cells, one hot-reload proof (benign config version bump picked up without redeploy), one shadow CVD event through the deployed pipeline, MCP tool returning real levels; `/health=OK` alone is never sufficient; (4) logs clean of new-path exceptions.
- **7.3** Completion report (`s3-phase1-5-completion-report.md`) + ACK, then hand to the coordination lane for independent cross-lane verification (the S-2 `b8149c6` pattern).
- **7.4** **Post-R-2 checkpoint gate (ATHENA, standing):** the completion report's final line formally requests the checkpoint — reassess rebuild-stack L1 vs. proceeding to R-3/R-4. **No S-4 authoring until the checkpoint decision is recorded.** The HELIOS mockup concept session also unlocks at this point per the charter's timing rule.

## §8 — Hard rules (violations = stop and flag, not improvise)

Shadow-first everywhere; `gating_enabled` untouched; the dial writes zero feed rows; L0 only (no `log_signal` side door); $0 incremental spend; sanctioned vendors only, zero new vendors, zero new UW polling; all new thresholds config-driven + hot-reloadable, config tables append-only; every migration carries `-- DOWN`; pathspec-only commits, message via `C:\temp\commitmsg.txt`; no historical `signals` mutation; HMAC path untouched; Railway blackout 07:30–14:00 MT applies to pushes on trading days — **Nick's explicit override stands for 2026-07-16 only** ("not actively using the hub"); after today, hold pushes to outside the window unless re-authorized.

---

## §9 — Done Definition (all 15 required; evidence = commits, committed docs, or live reads)

1. Phase-0 findings committed (`s3-phase0-findings.md`) with file:line evidence for every §1 item, including the known-red baseline (names + count) and the bypass-tracker output.
2. D-1 mockup-track log entry live via the exact §2 anchor.
3. D-2 backlog updates live (Tier-2 #6 closed with commit ref; signal-#10 deferral recorded under S-5).
4. Canonical ticker normalization live at all three ingress sites; tests prove cross-source canonical equality; grep-proof that the TV webhook HMAC verification path is byte-identical; no historical-row mutation shipped.
5. FA-1 pre-flight run and recorded; MATIC/UNI/APT pruned (zero-reference case) **or** stop-and-flag recorded with the offending rows (nonzero case).
6. Migration 026 applied; all three tables confirmed on the live DB via `information_schema`; `-- DOWN` present; seed row `created_by='SEED_S3'`; config tables demonstrated append-only.
7. Cycle Extremes payload live for all six symbols: every cell carries the §4.2 contract; BTC/ETH full columns; N/A cells explicit with reasons (never zeros/nulls); composite present with `composite_method`; anti-fake-healthy check passes (distinct per-symbol values where computed, not identical or zeroed).
8. Canonical copy strings present in the live payload; automated check proves FROTH copy contains "reduce new risk" and the string "sell" appears nowhere in FROTH copy.
9. Dial-to-feed isolation proven: assertion test green + a post-deploy live check window shows zero `signals` rows sourced from the cycle engine.
10. Hot-reload proven live: one benign `crypto_cycle_config` version bump picked up with zero redeploys; served `config_version` increments in the payload.
11. Tape-health + CVD split live for matrix-covered symbols; uncovered symbols return explicit N/A; one shadow CVD event fired through the real deployed `process_signal_unified()` with canonical ticker + FA-2 resolvable fields; its `crypto_gate_shadow` row observed (S-2 apparatus intact); zero live impact — `gating_enabled=false` unchanged, no new dismissals attributable to S-3.
12. `hub_get_crypto_market_profile` live and empirically verified (real levels cross-checked against the internal computation and one independent sanity reference); v2.0 envelope + staleness states; registry reflects the tool; Nick's connector re-toggle flagged in the completion report.
13. §6.2 `/state/{symbol}` wiring live; `_NOT_YET_BUILT_R1` markers gone; existing consumers unbroken.
14. Deployment verification: all 4 steps recorded with evidence per §7.2.
15. Known-red baseline unchanged byte-for-byte; completion report + ACK committed; final line formally requests the post-R-2 checkpoint (§7.4).

---

## §10 — Olympus Impact (standing ATHENA rule — fires because §6.3 ships a hub MCP tool)

- **Connector re-toggle:** after this brief's deploy, Nick toggles the Pandora connector so `hub_get_crypto_market_profile` enters the tool manifest. This is a separate toggle event from this morning's Brief-3 deploy (six `hub_get_stable_*` / board-state tools) — each deploy that changes the registry needs its own toggle.
- **BTC/SPY committee smoke re-test:** run in a fresh coordination-lane session post-re-toggle — BTC-USD exercising the new tool + SPY as the equity control, real skill files + live MCP. Zero-regression bar, results logged to the backlog update-log per the S-1 item-10 precedent.
- **Skill beneficiary:** PYTHIA gains crypto Market Profile parity — her `references/crypto.md` stub finally has a real tool behind it. Post-S-3, authoring the seven Olympus `references/crypto.md` stubs (from the committee brief + now-validated data) unlocks as a **coordination-lane** task per the committee brief's governance note — not CC scope, not this brief.

## §11 — Titans final review (2026-07-16, coordination lane) — verdicts + amendments

**Amendments applied during final review (all incorporated above):**
- **FA-1 (ATLAS):** delisting prune gated by a pre-flight `SELECT` for open positions / unresolved signals on the three tickers; nonzero → stop-and-flag (§1.6, §3.4).
- **FA-2 (ATLAS):** CVD shadow events must carry the full BAR_WALK-resolvable field set so F-2 machinery grades them from day one (§5.5).
- **FA-3 (AEGIS):** TV-webhook normalization applies strictly after HMAC verification; signature path byte-identical, grep-proven (§3.2, Done-4).
- **FA-4 (HELIOS):** zero breaking changes to `/api/btc/signals`; new payloads = new endpoints; captured payload-contract examples in the completion report feed the mockup session (§6.4).
- **FA-5 (ATHENA):** §6.2 `/state` wiring recorded as a named absorbed micro-item (S-2's disclosed follow-up), and signal #10 explicitly deferred to S-5 per the carry-forward — scope deltas acknowledged, not silent (§6.2, §4.6).
- **FA-6 (ATLAS):** config tables append-only (INSERT version rows, never UPDATE), matching `crypto_gate_config` precedent (§4.1).

**ATLAS — BRIEF FINAL REVIEW** · BRIEF: this file · CC-ACTIONABLE: **YES** (file-anchored tasks, findings-first, stop conditions) · GATES PRESENT: **YES** (Phase-0 pre-flight, FA-1 gate, shadow-only posture, explicit Done Definition) · SCOPE MATCHES PASS 2 AGREEMENT: **YES** — deltas named (FA-5) · OLYMPUS IMPACT SECTION: **Present + accurate** · **APPROVE FOR CC: YES**

**HELIOS — BRIEF FINAL REVIEW** · BRIEF: this file · CC-ACTIONABLE: **YES** · DESIGN SYSTEM COMPLIANCE ADDRESSED: **Not applicable** (no UI ships; legacy surface protected by FA-4) · ADHD-FRIENDLY HEURISTICS HONORED: **YES** (decisive canonical copy, single-axis composite, no hidden state — every cell self-declares staleness) · STALENESS / REAL-TIME PATTERNS ADDRESSED: **YES** (§4.2 contract) · PERFORMANCE BUDGET ADDRESSED: **YES** (hourly + existing 5-min cadence; no market-hours frontend path touched) · BACKEND DEPENDENCIES NOTED: **YES** (payload contracts gate the mockup session) · **APPROVE FOR CC: YES**

**AEGIS — BRIEF FINAL REVIEW** · BRIEF: this file · CC-ACTIONABLE: **YES** · SECRET HANDLING ADDRESSED: **YES** (zero new credentials; sanctioned clients reused; MCP bearer + unauthenticated-read-only REST per settled precedent; payloads carry market data only) · AUDIT LOGGING ADDRESSED: **YES** (append-only config versions with `created_by`; vendor-health audit untouched; no new security-relevant actions) · ROTATION GUIDANCE ADDRESSED: **Not applicable** (no new credentials) · OVERRIDE-ACCEPTED FINDINGS RECORDED: **None** · **APPROVE FOR CC: YES**

**ATHENA — BRIEF FINAL REVIEW** · BRIEF: this file · CC-ACTIONABLE: **YES** · SCOPE MATCHES PASS 2 AGREEMENT: **YES** — named deltas only (FA-5) · OLYMPUS IMPACT SECTION: **Present + accurate** · SEQUENCING REFLECTED IN BRIEF: **YES** (defers #10 → S-5 and all retunes → S-4; no new displacement beyond the program-level ZEUS record; post-R-2 checkpoint hard-gates S-4) · **APPROVE FOR CC: YES**

*Prepared and final-reviewed in the coordination lane, 2026-07-16. Execution: CC from repo root, Phase 0 first, findings committed before any code.*
