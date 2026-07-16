# Brief S-1 — Stater Swap v2: Foundation (R-0)

**Date:** 2026-07-13 | **Track:** ZEUS Phase II | **Executor:** Claude Code (VSCode, launched from repo root)
**Sources:** `docs/strategy-reviews/stater-swap-redesign/2026-07-12-stater-swap-v2-committee-brief.md` (incl. Addendum A) + Titans Pass 1/Pass 2 + ATHENA Overview (2026-07-13, coordination lane)
**Scope class:** Foundation. No strategy logic, no scoring changes, no UI.

## Purpose

Stater Swap v2 is gated on five foundation items (F-1…F-5). The current crypto module identifies the right strategy classes but skips signal governance, tracks no outcomes, resolves "BTC" to a same-named NYSE ETF ($28.33, status "live" — verified P0), and runs on four vendors wired before the data hierarchy existed. This brief ships the plumbing every later phase (R-1 regime/session, R-2 keep-list upgrades, R-3 strategy program, R-4 surfaces, R-5 UI port) stands on. Nothing in R-1+ may start until this brief's Done definition is met.

## Pre-flight (mandatory)

1. `git fetch && git status` — clean tree, latest `main`. Stop if dirty.
2. Read `PROJECT_RULES.md` (repo root) — binding throughout, esp. Data Source Hierarchy, Outcome Tracking Semantics, Deployment Verification.
3. Read the committee brief (path above) — Parts 1, 4, and Addendum A.
4. Confirm env vars exist BY NAME only (`COINALYZE_API_KEY`, `UW_API_KEY` in Railway). Never print values in code, logs, chat, or docs.
5. Deploy timing: pushes to `main` trigger Railway redeploy (hub down ~60–170s). No pushes 07:30–14:00 MT on trading days without explicit Nick override. Batch commits; push once per phase, outside the window.

## Phase 0 — Investigation (read-only; no code changes)

- **0.1** Trace the crypto signal write path. Confirm which callers use `bias_scheduler.log_signal` vs `process_signal_unified` (start: `backend/strategies/crypto_setups.py`, `backend/strategies/btc_market_structure.py`, the scanner registry, and the scheduler). Record every call site with file:line.
- **0.2** Schema check: does `signals` carry `asset_class`? Count existing `asset_class='CRYPTO'` rows in `signals` and `signal_outcomes`. What does `outcome_resolver.py` do today when handed a non-equity symbol (e.g., BTC-USD)?
- **0.3** Vendor client inventory: locate the Coinalyze / Deribit / Binance / DeFiLlama client modules; record auth mode (key vs public), base URLs, timeout/retry behavior, any existing staleness handling.
- **0.4** Webhook check (AEGIS): confirm `/webhook/tradingview` HMAC signature validation applies identically on the crypto alert path (BTCUSDT.P) as on equities.

**Deliverable:** `docs/strategy-reviews/stater-swap-redesign/s1-phase0-findings.md` with file:line evidence. Commit before Phase 1 begins.

## Phase 1 — F-1: Vendor verification + Symbol Capability Matrix

- **1.1** Live-test every vendor client **from Railway** (not local): one benign read per vendor per symbol. Binance geo-check explicit — document the HTTP status / geo error verbatim, minus any key material. Scrub auth headers and keyed URLs from all logging.
- **1.2** Build the **Symbol Capability Matrix** — machine-readable (JSON config file or Postgres table; CC's call, document why) plus a human-readable doc. Rows: BTC, ETH, SOL, HYPE, ZEC, FARTCOIN. Columns: funding, OI, liquidations, term structure (Coinalyze — explicitly verify Hyperliquid exchange coverage for HYPE/FARTCOIN), 25-delta skew (Deribit), quarterly basis (Binance), spot orderbook (Binance), UW crypto endpoint coverage, TV coverage, **BAR_WALK bars source**, **Binance-fail fallback**. Every cell is verified, never assumed; unknown = `UNVERIFIED` with reason, never blank.
- **1.3** If Coinalyze lacks Hyperliquid-native pairs: Hyperliquid public API enters as a sanction candidate (keyless; base URL pinned in config; hard timeouts; never construct request URLs from another vendor's response data). Surface as a one-line confirm for Nick.
- **1.4** **Input sanity bounds per feed** (AEGIS): per-symbol plausible ranges for price, funding %, OI, basis. Out-of-range values are rejected and never cached (mirror the VIX/DXY bounds pattern in PROJECT_RULES). Document chosen bounds in the matrix doc.
- **1.5** Flatline detection + honest DEAD state per client, per the label contract (`as_of`, `data_age_seconds`, `degraded`). Health-state transitions (LIVE↔DEGRADED↔DEAD) and every sanction/replace decision write audit-log entries.
- **1.6** Update `PROJECT_RULES.md` Data Source Hierarchy: replace the stale `Crypto (BTC, ETH)` row with the six-symbol vendor coverage from the matrix; document yfinance's crypto role (retained fallback or dropped) with a one-line rationale.
- **1.7** Credential handling for any newly sanctioned vendor: keys (if any) stored as Railway env vars and enrolled in the rotation pattern per `docs/operations/mcp-token-rotation.md`. Existing `COINALYZE_API_KEY` handling unchanged. Keyless public APIs: nothing to rotate — record that explicitly in the matrix doc.

**Hard rule:** if Binance is geo-blocked from Railway, the resolution is REPLACE (per the matrix fallback column). Never proxy, VPN, or otherwise evade a geo-restriction.

## Phase 2 — F-2: Outcome-tracking parity (shared resolver core)

- **2.1** Extend `outcome_resolver.py` (the 15-min walker — canonical for scalp-class signals per the canonical-walker policy) as an **asset-class-aware core**, not a crypto fork: bars source resolved per symbol via the matrix. Daily-walker (`score_signals.py`) crypto support is explicitly deferred until a crypto swing strategy enrolls (S-4). Symbols with no sanctioned grading source: signals stay shadow-only/ungraded — enforced in code, marked in the matrix.
- **2.2** End-to-end proof: one BTC shadow test signal flows into `signal_outcomes` with BAR_WALK grading. Document the row ID in the closure note.
- **2.3** **No historical backfill in S-1.** If a backfill is ever run later, it follows dry-run + apply with hard-stop gates.

## Phase 3 — F-3: Crypto data path on the hub

- **3.1** New MCP tools: `hub_get_crypto_quote(symbol)` + crypto bars access (UW crypto endpoints primary where the matrix confirms coverage; sanctioned vendors otherwise).
- **3.2** **Asset-class guard on `hub_get_quote`:** add an explicit `asset_class` param; bare collision symbols ("BTC", "ETH", …) return a disambiguation error naming both candidates — never the ETF silently. Canonical crypto symbol convention: `BTC-USD` style. Document in tool docstrings + `api_spec.yaml`.
- **3.3** **Consolidated per-symbol state envelope:** `/crypto/state/{symbol}` returning session, funding, OI, basis, plus tape-health and regime placeholders — each field carrying `as_of` / `data_age_seconds` / `degraded`. Fields not yet populated return honest nulls with `degraded` set; the envelope ships now so R-1/R-2 and the UI integrate exactly once. The envelope also carries the symbol's **tier and capability flags read from the matrix**, so the UI and committee render per-symbol N/A states from a single payload — no client-side coverage guessing.
- **3.4** Redis TTL audit for all crypto cache keys: TTLs sized for a 24/7 market (no equity overnight-reset assumptions). Document changed keys.
- **3.5** **Deploy verification — all 4 steps per PROJECT_RULES** — plus empirical checks: `hub_get_crypto_quote("BTC-USD")` within sane range of two independent web quotes; `hub_get_quote("BTC")` returns the disambiguation error (P0 closed). Closure note flags: Nick must toggle the Pandora connector after tool ship.

## Phase 4 — F-4: L0 routing (dual-write cutover)

- **4.1** Route crypto signals through `process_signal_unified` in **shadow dual-write**: both paths log; produce a diff report after ≥48h of 24/7 operation or n≥30 signals, whichever comes first.
- **4.2** **Cutover gate:** Nick reviews the diff report and greenlights in writing → retire the `bias_scheduler.log_signal` side door. No greenlight, no cutover — the dual-write may outlive this brief.
- **4.3** Anything tunable introduced here (thresholds, cadences) is config-driven (Postgres/Redis), hot-reloadable — no redeploy-to-tune.

## Phase 5 — F-5: Hygiene + bookkeeping

- **5.1** Commit the recovered Drogen framework note → `docs/strategy-reviews/stater-swap-redesign/drogen-momentum-framework.md`. Content per committee brief Part 1 recovery (Module A: BTC 50-DMA regime filter; Module B: cross-sectional momentum, long top 20% / short bottom 20% by 30-day return; Module C: broken-parabolic short — handled at prompt level). Mark provenance: recovered from the 2026-05-22 session record; original was never committed.
- **5.2** Fix `session_sweep`'s known-red scanner test — root cause first, then fix; document both. Other known-reds stay untouched.
- **5.3** **Backlog v4** (`docs/build-backlog.md`): promote ZEUS Phase II to top-of-queue; name displacements (rebuild-stack L1/L2, Outcome Tracking Phase C, committee review logging, Phase B `get_bars`); absorb the defect items this brief closes (wrong-asset quote P0, crypto L0 routing, `session_sweep` red test, Tier-2 "BTCUSDT crypto ticker support"); record the **post-R-2 checkpoint** as a sequencing gate; record the mockup parallel-track (HELIOS concepts in progress during R-0/R-1); **add Tier-3 / Post-ZEUS item: "Olympus crypto specialist — permanent committee seat (MIDAS-class skill). Guest-seat precedent: 2026-07-12 Stater Swap v2 pass. Requires Titans one-pager before any build."** Dated update-log entry with reasons.

## Output spec

- `docs/strategy-reviews/stater-swap-redesign/s1-phase0-findings.md`
- Symbol Capability Matrix (machine-readable artifact + `docs/strategy-reviews/stater-swap-redesign/symbol-capability-matrix.md`)
- Code: vendor clients (bounds/flatline/DEAD), resolver core extension, hub MCP tools + state envelope, dual-write routing
- `PROJECT_RULES.md` hierarchy update; `docs/build-backlog.md` v4; Drogen note; `session_sweep` fix
- Commits: **pathspec-only** (never `git add .`), one logical commit per phase, message prefix `s1(phaseN):`

## Gates — what NOT to do

- No strategy logic changes, no scoring changes, no UI work, no `crypto.md` stub authoring (stubs stay stubs until R-1/R-2)
- No Tier-3 strategy enablement of any kind
- No historical backfills
- Any schema migration ships with an explicit rollback (`-- DOWN`) block
- No live F-4 cutover without Nick's written greenlight on the diff report
- No credential values anywhere (code, logs, docs, commit messages)
- No proxy/VPN/geo-evasion — geo-blocked vendor ⇒ replace
- No pushes during the 07:30–14:00 MT trading-day window without explicit override

## Done definition

1. Phase-0 findings doc committed with file:line evidence
2. Matrix complete for all six symbols incl. BAR_WALK-source and Binance-fallback columns; every cell verified or explicitly UNVERIFIED with reason
3. All vendors live-tested from Railway; sanction/replace decisions documented; hierarchy table updated
4. Sanity bounds + flatline/DEAD live on every sanctioned client
5. One BTC shadow signal graded end-to-end in `signal_outcomes`
6. `hub_get_crypto_quote` live + empirically verified against two web sources; `hub_get_quote("BTC")` returns disambiguation (P0 closed); all 4 deploy-verification steps recorded; connector re-toggle flagged to Nick
7. Dual-write diff report produced (cutover status recorded either way)
8. Drogen note committed; `session_sweep` test green (or root cause + fix documented)
9. Backlog v4 committed, incl. the Olympus-crypto-specialist Tier-3 item
10. One Olympus committee smoke pass post-tool-ship (BTC-USD via new tools + SPY as control) confirms no regression — coordination lane runs this; CC flags readiness in the closure note

## Olympus Impact

- **Skills touched:** all seven agents gain crypto quote/bars + state envelope access via hub MCP (read paths only)
- **Behavior change:** committee crypto legs stop web-fallback for quotes once tools are verified; equity paths untouched
- **Re-test:** one full committee pass on BTC-USD (new tools) + one on SPY (control) after F-3 ships — run in the coordination lane; connector must be re-toggled first
- **Not in scope:** crypto playbook authoring (that's R-1/R-2 output)
