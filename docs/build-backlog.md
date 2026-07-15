# Build Backlog

Authoritative queue of in-flight, near-term, and deferred build work for Pandora's Box. Maintained as ATHENA's canonical reference for priority arbitration during Titans review passes.

**Last updated:** 2026-07-15 (v4 — ZEUS Phase II / Stater Swap v2 (S-1) promoted to top-of-queue; rebuild-stack L1/L2 + Outcome Tracking Phase C + committee review logging + Phase B `get_bars` displaced; S-1 defect items absorbed; post-R-2 checkpoint + HELIOS mockup parallel-track recorded; Olympus crypto specialist Tier-3 item added; Crypto Scanner dormancy root-caused + flatline watchdog item added; F-4 cut over to unified pipeline as primary writer)
**Maintained by:** ATHENA (Olympus Titans synthesis lane). Nick or CC may update directly when items are added, promoted, demoted, or closed.

---

## Project context — ZEUS

ZEUS is the meta-project name for the multi-phase overhaul currently in progress. Phase labels (II, III, IV) are for tracking and grouping; exact execution order between phases is not strict — phases can interleave when scope warrants. **Phase I is the only phase formally in scope right now.**

| Phase | Scope | Status |
|---|---|---|
| **I** | Full Unusual Whales API integration into Pandora's Box (Phase A heatmap popup shipped; Phase B `get_bars` migration and the rest of Phase C now displaced behind Phase II — see below) | IN_FLIGHT (displaced) |
| **II** | Stater Swap (crypto account) complete strategy revision around UW + TV MCPs. **PROMOTED TO TOP-OF-QUEUE 2026-07-14** — Brief S-1 (foundation) in progress: F-1/F-2/F-3 shipped + deployed, F-4 (dual-write, no cutover) shipped, F-5 (this update) in progress | **IN_FLIGHT — TOP OF QUEUE** |
| **III** | Analytics functionality and dashboard overhaul (includes Trading hub UI v3, Abacus widget overhaul, related analytics surfaces) | QUEUED |
| **IV** | Great Library update / revision | QUEUED — scope TBD, recovery via codebase grep + Nick recall pending |

Items deeper in Tier 2 / Tier 3 that previously anchored on "post-ZEUS" now anchor on the specific Phase that fits them.

---

## How to use this file

**Tier definitions:**
- **Tier 1 — Foundation / High-leverage / Gated.** Items currently in scope or immediately next. Foundational architecture, critical reliability, or items that unblock multiple Tier 2 builds. ATHENA pulls from this list when arbitrating "what's next."
- **Tier 2 — Tactical / Queued.** Items waiting for Tier 1 dependencies or for capacity. Typically days of work each. ATHENA can promote items to Tier 1 when gates clear.
- **Tier 3 — Research / Speculative / Cross-Phase.** Lower-priority builds, exploratory work, or items in future ZEUS phases. Reviewed periodically; not actively scheduled.

**Status conventions per item:** `QUEUED` (default), `IN_FLIGHT` (build active), `BLOCKED: <reason>` (gated), `CLOSED: <commit>` (shipped, link to closure note).

**Update protocol:**
- New items added at the bottom of their tier with a one-line problem statement + initial bucket fit (foundation / tactical / quick win).
- Promotions/demotions noted in the **Update log** at the bottom with date and reason.
- Closure: move to **Recent closures** with commit SHA and closure note path. Do not delete history.
- Cross-cutting framework debt lives in its own section, not the tiers.

---

## Top of queue (active scope)

**ZEUS PHASE II — STATER SWAP v2 (crypto foundation rebuild), promoted 2026-07-14.**
Forced by the committee brief's P0 finding (2026-07-12): `hub_get_quote("BTC")` silently resolved to a $28 NYSE ETF instead of Bitcoin, plus the crypto signal write-path bypassing L0/L1 governance entirely. Committee brief: `docs/strategy-reviews/stater-swap-redesign/2026-07-12-stater-swap-v2-committee-brief.md`. Build brief: `docs/codex-briefs/2026-07-13-stater-swap-s1-foundation-brief.md` (Brief S-1, R-0 foundation).

- **F-1 — Vendor verification + Symbol Capability Matrix.** SHIPPED + deployed (`1aae39e`, `222f452`). Six-symbol matrix (BTC/ETH/SOL/HYPE/ZEC/FARTCOIN), sanity bounds, LIVE/DEGRADED/DEAD health tracking, TV ticker classifier fix.
- **F-2 — Outcome-tracking parity.** SHIPPED + deployed (`3b91328`). Asset-class-aware `outcome_resolver.py`, per-symbol bar sources, 24/7 crypto resolver loop.
- **F-3 — Crypto data path on the hub.** SHIPPED + deployed (`90f9d10`). `hub_get_crypto_quote`, asset-class guard on `hub_get_quote` (P0 CLOSED), `/api/crypto/state/{symbol}` envelope. Countersigned by independent price-anchor check 2026-07-14.
- **F-4 — L0 routing dual-write.** SHIPPED, then CUT OVER 2026-07-15 (Fable-directed "inverted shadow" ruling). `process_signal_unified` gained a `shadow` param (still used elsewhere); `bias_scheduler.py`'s Crypto Scanner bypass now calls the unified pipeline for REAL (persistence, Discord, broadcast, committee flagging, conflict-dismissal all live) — the original ad hoc scorer is demoted to a comparison-only shadow-logger in the same `crypto_dual_write_shadow` table. Diff report (`scripts/crypto_dual_write_diff_report.py`) now tracks RETIREMENT of the demoted logger (n>=30 real signals), not cutover — cutover already happened. Full pre-deploy Discord/fan-out review in `docs/strategy-reviews/stater-swap-redesign/s1-phase4-findings.md`.
- **F-5 — Hygiene + bookkeeping.** IN PROGRESS (this update): Drogen framework note recovered, `session_sweep` known-red test fixed (root cause: stale hardcoded score predating an Olympus floor retune, not a classifier bug), this backlog v4 pass.
- **R-1 through R-5** (regime/session, keep-list upgrades, strategy portfolio, new surfaces, UI port) — **QUEUED behind S-1's Done Definition**, per the brief's own "R-4/R-5 forbidden before R-0 ships" rule. **Post-R-2 checkpoint recorded as a sequencing gate below.** **S-6 (UI port) now has a named blocking dependency**: Tier 1 item #3 below (`breakout_prop` balance fake-healthy fix) must ship before S-6's distance-to-floor chip can be built correctly.

**Displaced by this promotion (still real, real work — just no longer top-of-queue):**
- **Rebuild stack L1 (Signal Quality) and L2 (Options Expression)** — L0 foundation work already shipped stays shipped; L1/L2 move behind ZEUS Phase II. Master brief `docs/codex-briefs/2026-06-16-rebuild-stack-master-brief.md` unchanged, just resequenced.
- **Outcome Tracking Phase C** — partially self-paying via F-2's resolver-core work, but the full daily-walker re-walk project stays queued behind S-1.
- **Committee review logging** — queued behind S-1.
- **Phase B — `get_bars` migration off yfinance** — queued behind S-1 (closes ZEUS Phase I when it eventually ships).

**Sequencing gate — Post-R-2 checkpoint (Titans review carry-forward, 2026-07-13):** before R-3/R-4 begin, ATHENA reassesses rebuild-stack L1 against Stater Swap's R-3/R-4 scope to decide relative priority. Standing obligation — do not skip.

**Parallel track approved (not gated on R-0/R-1 build sequencing):** HELIOS concept-mockup production for the eventual R-5 UI port runs DURING R-0/R-1 build work. Design work ≠ build work — the "R-5 forbidden before R-0 ships" rule binds code, not HELIOS's mockup drafting. Mockup gate (>=3 approved concepts, multi-symbol switcher, per-symbol N/A states, tier badges, >=1 Tier-3 view) still applies before any R-5 build.

**Parallel tracks in flight (NOT part of the rebuild stack — coordinate worktrees, never `git add .`):**
- **sb3 (scoring correctness)** — three fixes (dead ADX regime gate, double-counted/false-bearish flow, iv_rank dispersion proxy) shadow-staged on `sb3-work` (C:/th-scoring); promote pending UW-recovery confirm. Handoff: `docs/sb3-handoff-for-strategy-overhaul.md`. **Rebuild-stack L0.1b depends on this promote** (unaffected by the Phase II promotion — L0 itself already shipped).
- **sec-work (Fable security)** — plaintext Postgres pw rotation + move to env. Branch `sec-work` (C:/th-security).

---

## Tier 1 — Foundation / High-leverage / Gated

### 0. `process_signal_unified()` — Redis cache + WebSocket broadcast silently fail for every signal (platform-wide)
**Bucket:** Foundation / reliability. **Added 2026-07-15**, surfaced during the F-4 crypto cutover's live smoke test (not caused by it — pre-existing, newly *observed*).
**Why:** `backend/signals/pipeline.py:1200` sets `signal_data["expires_at"] = calculate_expiry(...)`, which returns a raw Python `datetime` object, for every signal from every source (confirmed via grep: no signal source anywhere in the repo pre-populates `expires_at` as a string). `cache_signal()` (`database/redis_client.py`) and `broadcast_signal_smart()` (`websocket/broadcaster.py`) each carry their own duplicate, incomplete `sanitize_for_json()` that only converts numpy types, never `datetime` — `json.dumps()` throws `TypeError: Object of type datetime is not JSON serializable`, caught by the pipeline's own try/except, logged as a warning only (`Failed to cache signal`/`Failed to broadcast signal`), never surfaced further. Persistence is unaffected (`postgres_client.py`'s own `_sanitize_for_json()` correctly handles `datetime`, and `expires_at` isn't even in `log_signal`'s INSERT column list) — so this has been silently degrading real-time delivery (Redis `signal:{id}` cache + the live WebSocket "new signal" push) for every signal ever routed through `process_signal_unified()`, likely since it was written, without crashing or otherwise drawing attention.
**Crypto-specific consequence:** the pre-cutover Crypto Scanner bypass built its own signal dict and called `cache_signal`/`broadcast_signal_smart` directly, with no `expires_at` field — so crypto signals' cache/broadcast almost certainly worked fine before F-4's cutover. Post-cutover, crypto signals inherit this same platform-wide bug for the first time, a real (if pre-existing-root-cause) regression for that specific asset class.
**Suggested fix (small, not applied yet):** add `datetime`/`Decimal` handling to the two incomplete `sanitize_for_json()` copies in `redis_client.py`/`broadcaster.py`, mirroring the already-correct implementation in `postgres_client.py`. Touches shared infra used by every signal source — needs sign-off and its own verification pass, not a drive-by fix inside the crypto cutover.
**Gates:** None blocking S-1 or the cutover itself (persistence/scoring/feed-tier/committee-gating all confirmed working regardless). High-leverage given blast radius — affects every strategy, not just crypto.

### 1. Phase C bundle — Olympus enrichment + Phase A.5 + OAuth (ZEUS Phase I)
**Bucket:** Foundation. Large multi-day build.
**Status:** QUEUED, top of Tier 1. Brief not yet authored.
**Why:** This bundle finally closes the committee data gap that has been hurting trade reviews (documented in the 2026-05-20 TSLA pass and 2026-05-22 HAL pass — three Olympus agents at half-power without chain/Greeks/IV/MP data). Also closes the Phase A.5 ticker-info sub-card UX gap and the MCP auth-reliability issue that hit this session.

**Bundle contents:**
- **Olympus enrichment wrappers (~12):** `stock/{ticker}/greeks`, `stock/{ticker}/flow-alerts`, `stock/{ticker}/oi-change`, `stock/{ticker}/expiry-breakdown`, `stock/{ticker}/spot-exposures`, `stock/{ticker}/volatility/term-structure`, `market/{ticker}/etf-tide`, `market/{sector}/sector-tide`, `option-trades/flow-alerts`, `institution/{ticker}/ownership`, `companies/{ticker}/profile`, `companies/{ticker}/earnings-estimates`. Use Phase A's Redis envelope cache pattern.
- **Three v2 hub MCP tools** (per memory #29): `hub_get_options_chain` (DAEDALUS — lowest effort), `hub_get_chart_indicators` (PYTHAGORAS via TV webhook), `hub_get_market_profile` (PYTHIA via TV MP webhook — hardest).
- **Phase A.5 — Ticker info sub-card.** Inline sub-card expansion under heatmap row, on-demand. UX decided 2026-05-22: inline expansion, NOT route to existing ticker-profile popup. Backend: `companies/{ticker}/profile` wrapper (shares with Olympus enrichment list above — single implementation serves both).
- **OAuth state persistence on `backend/hub_mcp/`** — ✅ **SHIPPED 2026-05-27 (`3d6dd94`, Brief D rev2 Layer 2).** rev1 + rev2 (Redis-backed) both reverted same-day; the rev3 "investigation-first" track is superseded. Root cause sat below FastMCP, in the `key_value` library's `RedisStore(client=...)` write-read path (NOT multi-worker isolation, the rev2 closure note's hypothesis). Fix sidestepped Redis entirely: a Railway persistent volume mounted at `/data` with `FASTMCP_HOME=/data`, so FastMCP's file-backed `client_storage` survives container restarts — zero application code, Railway config only. JTI mappings / DCR clients / refresh tokens now persist across redeploys; the manual reconnect cycle is gone. Closure: `docs/strategy-reviews/brief-d-rev2-layer2-closure-note-2026-05-27.md`. Known residual (minor, future): quarterly GitHub OAuth secret rotation re-derives the Fernet key → cache-miss → manual reconnect (`docs/observations/mcp-client-401-behavior-2026-05-24.md`).

**Gates:** None blocking. Titans final review on the bundled brief is where scope-too-big risk gets evaluated — if the bundle is genuinely unwieldy, Titans split OAuth and/or A.5 into separate briefs.
**Unblocks:** DAEDALUS / PYTHAGORAS / PYTHIA full-power committee passes; reliable MCP availability across sessions; ticker drill-down UX in the heatmap.

### 3. `hub_get_portfolio_balances(account="breakout_prop")` — P1 fake-healthy defect
**Bucket:** Foundation / trading-safety. **Added 2026-07-15**, surfaced by the S-1 F-3 closure Olympus smoke pass (BTC-USD + SPY control, 14 agents).
**Why:** The tool returns an **empty account list tagged `staleness=60s` ("fresh")** rather than `stale`/`unavailable` for the Breakout Prop account — DAEDALUS found it independently on the BTC-USD pass, PIVOT independently re-ran the identical call and got the same result. This is the same failure class as the original P0 (hub_get_quote("BTC") silently resolving to the wrong ETF): **the tool reports success while the underlying data doesn't exist**, which is worse than an honest error because nothing downstream knows to distrust it. Consequence observed live: DAEDALUS issued a portfolio-level SIZING VETO on BTC-USD because Breakout Prop — the only account structurally able to hold a crypto trade — could not be verified to have any balance at all.
**Named S-6 dependency:** the committee brief's R-5/S-6 UI port spec calls for a "distance-to-floor" hard chip driven by Breakout Prop's trailing drawdown floor (DAEDALUS, committee brief Part 2: "distance-to-floor is existential... belongs on the UI as a hard chip"). **That chip cannot be built correctly until this defect is fixed** — S-6 should treat this as a blocking prerequisite, not a parallel nice-to-have.
**Also noted:** the unfiltered `hub_get_portfolio_balances()` call returns a 5-account list that doesn't match the documented 4-account structure (missing `breakout_prop` entirely, an unexplained "interactive brokers" row present, `fidelity 401a`/`403b` in place of the documented `brokerage_link_401k`) — likely the same root cause, needs the same investigation.
**Gates:** None blocking S-1 closure (S-1's Done Definition doesn't depend on this). Blocking S-6 (UI port) specifically for the distance-to-floor chip.

### 4. `hub_get_flow_radar` crypto-blindness — P1 fake-healthy defect
**Bucket:** Tactical / data-integrity. **Added 2026-07-15**, surfaced by the same smoke pass.
**Why:** For a crypto ticker (BTC-USD tested), `hub_get_flow_radar` returns `status: ok` with options-premium-shaped data (`source: db_fallback`, `event_count: 0`, ~9.9h stale against a claimed 4h lookback) instead of a clean `unavailable` the way `hub_get_market_profile`/`hub_get_options_chain`/`hub_get_chart_indicators` correctly do for crypto tickers (all three of those were touched or reasoned about during Stater Swap S-1 and fail honestly). All 6 BTC-USD committee analysts independently flagged and discounted this data in the smoke pass; THALES: "a quieter, riskier failure mode than the quote guard's explicit error — worth a P1 look." Not a Stater Swap S-1 regression (flow_radar was never crypto-aware and S-1 didn't touch it) — newly *visible* now that real crypto committee passes are running against it.
**Gates:** None blocking S-1. Natural fit for R-4 (new context surfaces) or a standalone hygiene fix — needs its own scoping pass, not assumed to be small.

### 2. Phase B — `get_bars` migration off yfinance to UW (ZEUS Phase I)
**Bucket:** Foundation hygiene. Smaller scope than original estimate.
**Status:** QUEUED.
**Why:** Closes the last yfinance dependency in the hot path per Data Source Hierarchy (memory #10). Phase A delivered the `get_ohlc` wrapper that Phase B consumes.
**Gates:** Phase A's `get_ohlc` wrapper shipped (✓ in `363cde6`). Independent of Phase C — can ship in parallel or after.
**Unblocks:** Cleaner downstream consumers (sectors fallback, market_data, scanners, correlation_monitor, trip_wire_monitor). Closes ZEUS Phase I.

---

## Tier 2 — Tactical / Queued

### Outcome tracking and strategy promotion

- **Outcome Tracking Phase C** — re-walk projection onto `signals.outcome*` columns using current yfinance; canonical-walker policy (daily resolver for B1/B2, 15-min for B3). Per memory #23 and #26. Brief not yet authored. NOTE: distinct from ZEUS Phase C above (which is Olympus enrichment). Naming collision worth resolving in the brief — always reference as "Outcome Tracking Phase C" explicitly.
- **3-10 oscillator promotion re-audit.** Gated on Outcome Tracking Phase C ship + n≥250 post-Outcome-Tracking-Phase-B `both`-gate signals with leave-one-out robustness. Current verdict: NOT YET per `docs/strategy-reviews/raschke/3-10-promotion-reaudit-2026-05-08.md`.
- **URSA stop-tightness recalibration.** Bounded MFE/MAE semantic shift post-Outcome-Tracking-Phase-B. Sequencing: after Outcome Tracking Phase C ships.
- **`score_signals` pre-walk age cap remediation.** Specific scope TBD on first ATHENA review.
- ~~**BTCUSDT crypto ticker support.**~~ — **ABSORBED into ZEUS Phase II / Stater Swap S-1, CLOSED 2026-07-14.** Turned out to be far more than "quick-win bucket": Symbol Capability Matrix (F-1), asset-class-aware outcome resolver with per-symbol bar sources (F-2), `hub_get_crypto_quote` + asset-class guard (F-3), and the underlying ticker-normalization layer (`crypto_bars.normalize_crypto_ticker`) all trace back to this line item. See `docs/strategy-reviews/stater-swap-redesign/` for the full S-1 findings trail.

### Olympus / committee infrastructure

- **Committee review logging.** Every Olympus pass persisted (ticker, ts, spot, per-agent read, PIVOT synthesis, conviction, entry/stop/target/invalidation) for outcome attribution. `outcome_source='COMMITTEE_REVIEW'`. Requires MCP v2 write-tool gates OR direct `/api/committee/log` endpoint. Per memory #24. At n≥250: PIVOT calibration, per-agent edge, B.06 hit rate, regime conditioning. Should ship after PIVOT skill and before Outcome Tracking Phase C runs at scale.

### 5. Strategy-emission flatline watchdog
**Bucket:** Tactical / reliability. **Added 2026-07-15**, surfaced by the F-4 dual-write dormancy investigation (Fable-directed).
**Why:** The `Crypto Scanner` strategy (`bias_scheduler.py::run_crypto_scan_scheduled()`) produced **zero signals for 12 consecutive days** (2026-07-03 → 2026-07-15) with no alert anywhere — the scheduler ran every 30 minutes exactly as designed, logged `"completed"` each cycle, and nothing downstream noticed a scanner that's supposed to produce occasional signals had gone fully silent. Root cause turned out to be benign (12 of 15 tracked tickers are in `CAPITULATION`/`WATERFALL` CTA zones — a genuine bearish market structure — combined with the scanner being long-only by default, so zero qualifying setups is the *correct* output right now, not a bug). But the absence of any signal is indistinguishable from a silent failure (dead data feed, broken indicator calc, API key expiry) without this kind of manual archaeology. This exact blind spot delayed the F-4 dual-write diff report's readiness clock with no visibility into why.
**Proposal:** A watchdog analogous to the existing `flow_deadfeed_watchdog_loop` (`backend/main.py`) pattern — alert (Discord or dashboard chip) when a scheduled strategy has run N times successfully but produced zero signals for longer than some threshold (e.g. 5-7 days), so a genuine dormancy (market condition) is at least visibly flagged as "known, explained" rather than silently invisible, and a *real* break (feed died, exception swallowed) gets caught fast instead of 12 days later.
**Also found in the same pass (quick-fix, separate from the watchdog):** 3 of the 15 `CRYPTO_TICKERS` entries in `bias_scheduler.py` — `MATIC-USD`, `UNI-USD`, `APT-USD` — return `"possibly delisted; no price data found"` from yfinance on every cycle and have been silently dead weight (20% of the universe) with no escalation. Needs live tickers substituted or yfinance's current symbol for each confirmed before any redeploy.
**Gates:** None blocking S-1. Independent hygiene/reliability item — small build once scoped.

### 6. `tradingview.py::is_crypto_ticker()` misses hyphenated tickers
**Bucket:** Quick-fix / data-integrity. **Added 2026-07-15**, surfaced incidentally during the F-4 cutover's pre-deploy Discord/fan-out research pass.
**Why:** `CRYPTO_TICKERS` (`backend/webhooks/tradingview.py:56-69`) contains `'BTCUSD'` (no hyphen) and `is_crypto_ticker()` only strips `.P`/`PERP`/`-PERP` suffixes — a TradingView alert sending a hyphenated ticker like `"BTC-USD"` is not recognized, so `asset_class` gets silently miscomputed as `"EQUITY"` instead of `"CRYPTO"` for that signal. Live DB query confirmed 79 existing signals already mistagged this way (none have crossed the committee threshold, so no known downstream harm yet). Does not affect the Crypto Scanner path (`bias_scheduler.py` sets `asset_class` explicitly, bypassing this classifier).
**Gates:** None blocking. Small, isolated fix (extend suffix/format handling) once scoped — not done here to keep the F-4 cutover change surface minimal.

### Framework / housekeeping

- **Titans reference docs authoring** (~20 references across the four Titans). Currently all `SKILL.md` files reference docs that do not exist; the "authoring status note" convention tells future agents to work from `PROJECT_RULES.md` + codebase in the interim. Recommended sequence: ATLAS first (backend-architecture, database-schema, phase-gate-playbook, uw-integration-playbook, mcp-server-patterns), then ATHENA (bucket-framework-builds, priority-decision-framework, olympus-impact-checklist, arbitration-precedent-log), then AEGIS + HELIOS in parallel.
- **Hub MCP tool-descriptions spec is stale (5 tools missing).** `docs/specs/hub-mcp-tool-descriptions-2026-05-14.md` and `backend/hub_mcp/README.md`'s tool table both document only 9 of the 14 tools actually registered in `backend/hub_mcp/decorators.py`'s `REGISTERED_TOOL_NAMES` — `hub_get_quote`, `hub_get_options_chain`, `hub_get_trade_ideas`, `hub_get_market_profile`, and `hub_get_chart_indicators` were added without a doc update. Surfaced during Stater Swap S-1 Phase 3 (2026-07-14) when adding `hub_get_crypto_quote` (tool #15) — flagged inline in both docs at the time rather than backfilled, since backfilling 5 tools' worth of description-authoring is its own scoped task, not an S-1 side effect. Quick-win bucket: mostly transcription from each tool's existing docstring/`DESCRIPTION` constant into the doc's established per-tool section format.

### Radar feature (UI)

- **Radar feature review.** Currently broken or useless per Nick injection 2026-05-22. Diagnose first, then fix or replace. Queued post-ZEUS-Phase-I per Nick's deferral.

---

## Tier 3 — Research / Speculative / Cross-Phase

### ZEUS Phase II — Stater Swap

**MOVED to Top of queue (active scope), 2026-07-14 — see above.** This Tier 3 entry predates the 2026-07-12 committee brief; kept here only as a pointer so old links don't 404. Do not re-derive scope from this line — the committee brief + Brief S-1 are now canonical.

### ZEUS Phase III — Analytics + dashboard overhaul

- **Abacus widget overhaul.** Display strategies in use post-tier-routing. Current shows stale bias/factor data not matching flow-led pipeline. Per memory #27.
- **Trading hub UI v3.** Real-time UW + TV MCP streams, actionable flow/DP/GEX/profile at a glance. Per memory #27. Anchored on Phase III dashboard work itself rather than as a Phase-III-prerequisite-gated item.

### ZEUS Phase IV — Great Library

- **Great Library update / revision.** Scope TBD. Recovery via codebase grep + Nick recall pending. ATHENA flag: this should be defined before scheduling any Phase IV work. Suggested next step: small CC task to grep `C:\trading-hub` for "Great Library" references and surface any closure notes or briefs that clarify scope.

### Post-ZEUS or unphased

- **HG Tier 1, 80-20, Anti HG, News Reversal strategies.** Queued after 3-10 oscillator cleared. Not strictly tied to a ZEUS phase.
- **THALES module deployment.** Currently THALES exists only as committee persona invoked manually. Module would deploy cross-sectional sector RS, narrow-leadership detection, sector divergence alerts on schedule with pushed notifications. Closest existing infra: `/api/watchlist/sector-strength`. Could fit into Phase III dashboard work or be its own thing.
- **X API Bookmark Intel Stream.** ~$3/mo. Titans one-pager required before any build commitment. Per memory #27. Post-ZEUS or Phase IV-adjacent.
- **Olympus crypto specialist — permanent committee seat (MIDAS-class skill).** Added 2026-07-14 per Brief S-1 F-5.3 / Titans review carry-forward. Guest-seat precedent: the 2026-07-12 Stater Swap v2 committee pass used MIDAS (crypto derivatives & flows) and OCEANUS (FX/commodities) as one-off guest seats — both remain one-off per the 2026-07-13 Titans review decision. This item is the standing ask to make a MIDAS-class seat permanent. **Requires a Titans one-pager before any build** — no skill authoring, no committee-roster change, until that one-pager exists and is reviewed.

---

## Cross-cutting concerns

- **Diagnostic queue (low-priority):**
  - `hub_get_quote` returns `unavailable` for SPY after-hours (UW `/stock-state` behavior, not Phase A regression). Surfaced 2026-05-22 smoke-test. Diagnose separately during RTH next session.
  - `sector_strength.rs_10d` returning 0.0 for all sectors after-hours. Surfaced 2026-05-22 smoke-test. Likely data refresh quirk; verify behavior during RTH and document. — ✅ **CLOSED 2026-07-11.** Corrected root cause (it was **NOT after-hours-only** — the bug ran 24/7 since the tool shipped ~2026-05-14): the writer (`bias_filters/sector_momentum.py`) computed `rs_10d` for the acceleration calc but never stored it, and the reader (`hub_mcp/tools/sector_strength.py`) did `entry.get("rs_10d") or 0.0`, so every sector reported `rs_10d=0.0` and `rank_10d` collapsed to the `SECTOR_ETFS` declaration order (deterministic proof: 2026-07-11 23:23Z payload matched dict order exactly). Fix: writer now stores `rs_10d`+`rank_10d` (rank only over non-null); reader uses is-None chaining (a legit 0.0 no longer eaten) + honest-null/degraded + real staleness from per-entry `updated_at`. Mini-brief `docs/codex-briefs/2026-07-11-sector-rs10d-contract-fix-mini-brief.md`; tests T1–T4. Cleanup note: `scanners/sector_rs.py` (Achilles) is a **separate, healthy** sector-RS pipeline (`sector_rs:{ETF}` cache) — dual-pipeline consolidation is a future backlog item, not built here.

- **Memory hygiene observation.** Nick's memory snapshot contained one ghost reference (ZEUS, ultimately recovered via Nick recall on 2026-05-22). There may be others. Not urgent, but worth a slow review pass through memory items #27, #29, and anywhere project names appear, to confirm current intent vs. memory residue. Cheap to do in a low-energy session; reduces future arbitration friction.

- **Comprehensive security review.** Future activity per AEGIS SKILL.md pre-production override mechanic. Triggers when (a) any broker trading API is connected, OR (b) Nick formally schedules it. AEGIS maintains the override-accepted findings backlog in the interim (currently empty; first entries will come as builds run).

---

## Recent closures

| Build | SHA | Closure note | Closed date |
|---|---|---|---|
| Brief D rev2 Layer 2 — Hub MCP OAuth state persistence (`FASTMCP_HOME=/data` on Railway persistent volume) | `3d6dd94` | `docs/strategy-reviews/brief-d-rev2-layer2-closure-note-2026-05-27.md` | 2026-05-27 |
| Brief E — Titans skills cleanup (Ship 1 + Ship 2) | `9540abd` + closure `0fdedfb` | `docs/codex-briefs/brief-e-titans-cleanup-2026-05-24.md` (Closure section appended inline) | 2026-05-25 |
| PIVOT skill — seventh and final Olympus committee agent | `fd0419b` | (no formal closure — skill file at `skills/pivot/SKILL.md`; 789c4a0 hygiene commit confirms "all 7 agents shipped") | (shipped earlier; verified 2026-05-24) |
| Phase C.1-rev2 — pre-built redis client w/ health-check + retry (idle-drop fix) | `d0b5400` then reverted `b6f2082` | `docs/strategy-reviews/phase-c.1-rev2-closure-note-2026-05-24.md` | 2026-05-24 |
| Phase C.1-rev1 — Redis-backed OAuth state persistence (initial attempt) | `21983bf` then reverted `8072c5c` | `docs/strategy-reviews/phase-c.1-rev1-closure-note-2026-05-24.md` | 2026-05-24 |
| Phase A.3 — UW overdraw remediation + close-state annotations | `5a5b8be` + smoke-test update `3703cec` | `docs/strategy-reviews/phase-a3-uw-overdraw-remediation-closure-note-2026-05-22.md` | 2026-05-22 |
| Build backlog v1 (this file's initial version) | `b700cc4` | (no formal closure — superseded by v2 this update) | 2026-05-22 |
| Phase A — Sector heatmap popup completeness via scheduled UW refresh | `363cde6` | `docs/strategy-reviews/phase-a-sector-heatmap-closure-note-2026-05-22.md` | 2026-05-22 |
| Titans framework — four `SKILL.md` files committed | `0d80f57` | (no formal closure — framework infrastructure) | 2026-05-22 |
| Titans framework — `_shared/TITANS_RULES.md` shipped | `12a6936` | (no formal closure — framework infrastructure) | 2026-05-22 |
| UW Integration Audit | `4ce3fd4` | (audit doc itself: `docs/uw-integration-audit-2026-05-22.md`) | 2026-05-22 |
| Outcome tracking Phase B | `e81d8a8` + `730ccfa` | `docs/strategy-reviews/phase-b-closure-note-2026-05-08.md` | 2026-05-08 |
| Outcome tracking Phase A | `0750e44` | (see Phase B closure note for context) | 2026-05-08 |

---

## Arbitration precedents

Recording priority calls made during ATHENA workflow passes that may set future precedent:

- **2026-05-22, Phase A review:** Phase A displaces PIVOT skill by 3-5 days. Displacement deemed worth it because Phase A closed a user-visible operational gap and was the canonical first test for the new Titans framework. Precedent: user-visible operational gaps in active dashboard surfaces can displace foundational committee work for short windows when displacement is bounded.

- **2026-05-22, Phase A Pass 2:** ATHENA arbitrated Nick injection vs. ATLAS finding on yfinance scope. Nick proposed yfinance for ticker popup non-critical fields. ATLAS pushed back: UW already wraps `/info`. ATHENA ruled for ATLAS — UW first for everything UW covers; yfinance reserved for indices/breadth (`^VIX`, `^GSPC`). Precedent: Nick injection is input, not instruction; Titans can correct directional inputs when codebase audit data contradicts them.

- **2026-05-22, Phase A.5 UX:** ATHENA arbitrated inline-sub-card vs. route-to-existing-ticker-profile-popup (audit Open Question 1). Nick had no opinion. HELIOS recommended inline sub-card. ATHENA ratified HELIOS. Precedent: when Nick defers a UX decision, ATHENA defers to the lane-owning Titan.

- **2026-05-22, ZEUS recovery:** ZEUS surfaced as a phantom memory reference, recovered via Nick recall as the meta-project name for the multi-phase overhaul. Phase I = UW integration (in-flight), Phase II = Stater Swap revision, Phase III = analytics/dashboard overhaul, Phase IV = Great Library. Precedent: memory snapshot can contain ghost references to past or partially-defined concepts; recovery path is Nick recall first, codebase grep second.

- **2026-05-22, Tier 1 ordering:** Nick ruled "UW integration first" → revised order is Phase C bundle → Phase B → PIVOT. Precedent: when multiple Tier 1 items compete, Nick can set ordering preference even if dependency graphs don't strictly require it.

- **2026-05-22, OAuth bundling:** OAuth on `backend/hub_mcp/` bundled into Phase C brief. Titans final review will catch if the bundle is too big and split it. Precedent: when an operational reliability fix is adjacent to a high-value build, default to bundling and let Titans final review arbitrate scope size.

- **2026-05-22, Phase C + Phase A.5 bundling:** Bundled because both share the `companies/{ticker}/profile` wrapper and the ticker popup UI is small enough to ride along. Tradeoff accepted: heatmap popup ticker sub-card waits longer. Precedent: when two builds share a non-trivial backend dependency, bundle by default unless the UX dimension is genuinely independent.

---

## Update log

| Date | Event | Details |
|---|---|---|
| 2026-05-22 | File created | Initial backlog authored from Nick's memory snapshot + this session's surfaces. Approved by ATHENA Pass 1 for canonical use. Committed as `b700cc4`. |
| 2026-05-22 | Closure | Phase A closed as `363cde6`. Moved to Recent closures. |
| 2026-05-22 | New Tier 1 item | OAuth on `backend/hub_mcp/` added; surfaced during smoke-test. |
| 2026-05-22 | New Tier 2 item | Phase A.5 (ticker info sub-card) entered backlog with UX decision recorded. |
| 2026-05-22 | New Tier 2 item | Radar feature review added; deferred post-ZEUS-Phase-I per Nick injection. |
| 2026-05-22 | Promotion | PIVOT skill promoted to top of Tier 1 (was queued, now top-of-queue after Phase A closure). |
| 2026-05-22 | v2 restructure | ZEUS phase context added. Phases I-IV labeled. Tier 1 reordered per Nick "UW integration first" call: Phase C bundle (Phase C + A.5 + OAuth) → Phase B → PIVOT. Stater Swap moved from Tier 3 → ZEUS Phase II. Dashboard items re-anchored on ZEUS Phase III. Great Library added as Phase IV with scope TBD. Six new arbitration precedents recorded. |
| 2026-05-22 | Closure | Phase A.3 (UW overdraw remediation + close-state annotations) shipped as `5a5b8be`; smoke-test outcomes appended via `3703cec`. Moved to Recent closures. |
| 2026-05-24 | Closure | Phase C.1-rev1 (Redis-backed OAuth state via `RedisStore(url=...)`) shipped as `21983bf`, smoke failed (Redis idle-drop → ConnectionError on /register), reverted as `8072c5c`. Closure note `phase-c.1-rev1-closure-note-2026-05-24.md`. Discovered via Task 0 dual discovery that OAuth was already live via FastMCP OAuthProxy + GitHub upstream; brief scope reframed mid-cycle. |
| 2026-05-24 | Closure | Phase C.1-rev2 (rev1 fix + idle-drop resilience via `health_check_interval=30` + `retry_on_timeout` + `socket_keepalive` + `decode_responses=False` on a pre-built redis-py client) shipped as `d0b5400`, smoke failed differently — write-read consistency bug on Redis-backed store (POST /register → 201 with client_id, immediate GET /authorize with same client_id → 400 "not registered"). Reverted as `b6f2082`. Closure note `phase-c.1-rev2-closure-note-2026-05-24.md`. |
| 2026-05-24 | Scope sharpened | OAuth-on-hub_mcp Tier 1 item rewritten: the build is OAuth STATE PERSISTENCE, not OAuth itself (OAuth is already live). rev3 attempt explicitly backlogged as investigation-first (no code until reproducer outside FastMCP confirms root cause). Higher-leverage Phase C / Phase B / PIVOT work takes precedence. |
| 2026-05-24 | Backlog hygiene | PIVOT skill confirmed shipped (commit `fd0419b`); Tier 1 item #3 removed and moved to Recent closures. Originally queued "post-ZEUS-Phase-I" per the 2026-05-22 v2 restructure; verified 2026-05-24 via git log on `skills/pivot/SKILL.md` and the "all 7 agents shipped" line in commit `789c4a0`'s body. Tier 1 now contains: Phase C bundle (#1), Phase B (#2). |
| 2026-05-25 | Closure | Brief E (Titans skills cleanup, Ship 1 + Ship 2) shipped as `9540abd` with closure appended as `0fdedfb`. Titans .skill bundles repackaged and uploaded to Claude.ai. Moved from Top of queue to Recent closures. |
| 2026-05-27 | Top of queue restored to empty | Top of queue placeholder restored. Awaiting new major build entry (per Nick 2026-05-27 — urgent overhaul scope TBD) OR Phase C bundle brief authoring. |
| 2026-06-17 | v3 — rebuild stack seated | Top of queue filled with the L0/L1/L2 rebuild stack (the 2026-05-27 "urgent overhaul" placeholder). Forced by the signal-edge-validation finding 2026-06-16. L0 brief Titans-reviewed → unanimous APPROVE FOR CC (`3671c85`). sb3 (scoring) + sec-work (Fable security) noted as in-flight parallel tracks. Tier-1 ZEUS Phase I items (Phase C bundle, Phase B) now sit BELOW the rebuild stack — displaced per ATHENA: fixing a foundation with no demonstrated edge outranks adding enrichment tools on top of it. |
| 2026-06-29 | Backlog reconciliation | Marked OAuth state persistence **SHIPPED** (`3d6dd94`, 2026-05-27, Brief D rev2 Layer 2) — entry had gone stale as a "rev3 investigation-first" track, flagged in `dual-review-hub-scope-2026-05-27.md` but never updated (the 6/17 v3 pass demoted the Phase C bundle without auditing its bullets). Added closure-table row + this entry. **STILL PENDING:** the same Phase C bundle entry's "three v2 hub MCP tools" (`hub_get_options_chain`, `hub_get_chart_indicators` `e6a94ed`, `hub_get_market_profile`) have also shipped, and the 5/27 dual-review dissolved the bundle (enrichment wrappers dropped, A.5 split to HELIOS) — full Phase C bundle reconciliation not yet done. |
| 2026-07-15 | Two new Tier 1/2 items — S-1 closure smoke pass findings | Fable countersigned the S-1 F-3 closure Olympus smoke pass (BTC-USD + SPY control, 14 agents, real skill files + live MCP tools, zero crashes/regressions) and folded two findings from it into the backlog per explicit instruction: `hub_get_portfolio_balances(account="breakout_prop")` fake-healthy defect (Tier 1 #3, named blocking dependency for S-6's distance-to-floor chip) and `hub_get_flow_radar` crypto-blindness (Tier 2 #4). Both are pre-existing/unrelated to S-1's own code, surfaced only because real crypto committee passes are now running. F-4 shadow-write collection checked same day: **0 shadow rows after ~17.4h is NOT a dual-write bug** — the underlying `Crypto Scanner` strategy (CTA logic on the 15-ticker crypto universe, untouched by S-1) has produced zero real signals since 2026-07-03, 12 days before this check. The 48h/n>=30 readiness bar for the F-4 diff report will not be met by passive collection at the observed signal rate; flagged to Fable rather than silently waiting. |
| 2026-07-15 | Crypto Scanner dormancy root-caused; new Tier 2 watchdog item; F-4 plumbing smoke-tested | Fable-directed read-only investigation confirmed root cause: **not** a scheduler crash (uptime-traced, `_scanner_loop()` fired every 30 min throughout, zero swallowed top-level exceptions), **not** L0.1a enforcement (`02111cd`'s own commit message + code inspection confirm the Crypto Scanner bypass is untouched by the read-surface enforcement flip), **not** Binance (this scanner path — `analyze_ticker_cta()` — has zero Binance dependency, fetches straight from yfinance, confirmed live and returning current data). Actual cause: 12 of 15 tracked tickers are in `CAPITULATION`/`WATERFALL` CTA zones (a genuine bearish structural condition, `sma20 < sma120` confirmed live) and the scanner's signal set is long-only trend-continuation logic with `allow_shorts=False` hardcoded on this path — bearish structure + long-only criteria = zero qualifying setups, correctly. Added Tier 2 item #5 (strategy-emission flatline watchdog) plus a quick-fix note (3 of 15 `CRYPTO_TICKERS` — MATIC/UNI/APT — are silently delisted on yfinance, dead weight in the universe). Separately, per Fable's ruling, fired one clearly-tagged synthetic signal (`S1_PHASE4_DUALWRITE_SMOKE_BTC_20260715`, strategy `S1_Phase4_DualWriteSmoke`, F-2 test-row convention — left in place as documented evidence, not real-strategy-filter-visible) through both the real write path and `shadow_write_crypto_signal()`: both landed correctly, diff report picked up the row cleanly. This confirms F-4's plumbing is sound despite zero real traffic — **the readiness clock does not count this row** and restarts from whenever the Crypto Scanner resumes producing real signals (Fable's ruling); no bar-lowering. No deploy made — root cause reported before any fix per instruction. |
| 2026-07-14 | v4 — ZEUS Phase II promoted | Committee brief (2026-07-12) + Titans review (2026-07-13) approved Brief S-1 (Stater Swap v2 foundation) as top-of-queue, forced by a live P0 (wrong-asset crypto quote) and the crypto L0-governance-bypass finding. Rebuild-stack L1/L2, Outcome Tracking Phase C, committee review logging, and Phase B `get_bars` all displaced (not dropped — resequenced behind S-1). S-1's own F-1 through F-4 shipped and deployed same week (`1aae39e`→`90f9d10`); F-5 (this update) closes the "BTCUSDT crypto ticker support" Tier-2 item (absorbed, far larger than originally scoped), records the post-R-2 checkpoint as a standing sequencing gate, records the HELIOS mockup parallel-track approval, and adds the Olympus-crypto-specialist Tier-3 item (Titans one-pager required before any build). Also flagged: hub MCP tool-descriptions spec is 5 tools stale (Framework/housekeeping). |
| 2026-07-15 | F-4 cutover — inverted shadow, unified pipeline now primary | Fable ruled cutover greenlit: `process_signal_unified` is now the PRIMARY writer for Crypto Scanner signals (persistence/Discord/broadcast/committee-flagging/conflict-dismissal all real); the original ad hoc bypass scorer is demoted to a comparison-only shadow-logger in the same `crypto_dual_write_shadow` table (roles inverted, no schema change). Diff report now tracks RETIREMENT (n>=30 real signals) rather than cutover. Pre-deploy checklist: a 4-agent parallel research pass confirmed no blocking Discord/fan-out risk — the one genuinely new mechanism (VPS committee auto-run on score>=85) is gated by a threshold crypto signals have never crossed historically (max 72 observed) and fails soft on missing enrichment data; feed-tier-v2 top_feed alerts are structurally unreachable for crypto (Pythia watchlist ceiling); lightning-dedup and dashboard rendering confirmed safe no-ops; cross-strategy conflict-dismissal confirmed non-triggerable in practice due to ticker-format inconsistency across the three crypto signal sources (BTCUSDT vs BTC-USD vs raw TradingView format). Added Tier 2 item #6 (incidental finding: `tradingview.py::is_crypto_ticker()` misses hyphenated tickers, unrelated to this cutover, not fixed). Full record: `docs/strategy-reviews/stater-swap-redesign/s1-phase4-findings.md`. |
