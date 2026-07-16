# Brief S-1 — Stater Swap v2: Foundation (R-0) — Closure Note

**Date:** 2026-07-15 | **Brief:** `docs/codex-briefs/2026-07-13-stater-swap-s1-foundation-brief.md`
**Executor:** Claude Code | **Coordination:** Fable (Nick's coordination lane)

All 10 Done Definition items are met. One item (#7, dual-write) was exceeded — the brief asked for a diff report with cutover status "recorded either way"; Fable ruled cutover in this same window, so F-4 shipped a full cutover rather than stopping at the report. Evidence for every item below is a real commit, a committed doc, or a direct database read taken while authoring this note (re-verified 2026-07-15, not carried over from memory).

## Done Definition — status + evidence

### 1. Phase-0 findings doc committed with file:line evidence
**MET.** `docs/strategy-reviews/stater-swap-redesign/s1-phase0-findings.md`, commit `a669429`. Traces every crypto signal write-path call site, schema check (`asset_class` column, outcome_resolver behavior on non-equity symbols), vendor client inventory, and the TradingView webhook HMAC check.

### 2. Matrix complete for all six symbols incl. BAR_WALK-source and Binance-fallback columns
**MET** (wording correction after adversarial verification, see below). `docs/strategy-reviews/stater-swap-redesign/symbol-capability-matrix.md` + `backend/config/crypto_symbol_matrix.py`, commit `1aae39e`. Covers BTC/ETH/SOL/HYPE/ZEC/FARTCOIN across funding/OI/liquidations/term structure, 25-delta skew, quarterly basis, spot orderbook, UW/TV coverage, BAR_WALK source, and Binance-fail fallback — every non-live cell is tagged `UNAVAILABLE` or `GEO_BLOCKED` with a stated reason (e.g. HYPE's UW fake-healthy trap), not the literal string `UNVERIFIED` this note originally claimed — corrected here rather than left standing. ZEC's bar-walk source is tagged `LIVE` in the Phase 1 matrix, but that entry's own caveat text ("candle-history endpoint not independently pulled in S-1") was never updated after Phase 2 actually live-verified it (`s1-phase2-findings.md`, "Pre-wiring verification" — 5 real 15m candles confirmed). The capability itself is fine; the Phase 1 doc's caveat text is stale and worth a one-line touch-up, not a functional gap.

### 3. All vendors live-tested from Railway; sanction/replace decisions documented; hierarchy table updated
**MET.** Live vendor tests (commit `1aae39e`) confirmed: Binance Futures geo-blocked from Railway (HTTP 451, 2026-07-13) → replaced with OKX fallback per the brief's hard rule (no proxy/VPN); Coinalyze live for all 6 symbols; Deribit live for BTC/ETH only (SOL has zero active option instruments — nominal, not functional); OKX candles live for HYPE/FARTCOIN. `PROJECT_RULES.md`'s Data Source Hierarchy table (re-verified today, lines ~135-139) carries the full six-symbol crypto rows with these exact decisions. Separately, `222f452` fixed a genuine, pre-existing Coinalyze bug found during this verification pass (OKX open-interest fallback read the raw contract-count field instead of `oiUsd` — 600x-scale wrong).

### 4. Sanity bounds + flatline/DEAD live on every sanctioned client
**MET.** `backend/config/crypto_sanity_bounds.py` (per-symbol bounds, mirrors the existing VIX/DXY pattern) and `backend/bias_filters/crypto_vendor_health.py` (LIVE/DEGRADED/DEAD tracking, audit-logged only on status transition) shipped in `1aae39e`, wired into all four vendor clients (`coinalyze_client.py`, `deribit_client.py`, `binance_client.py`, `defillama_client.py`). Migration `023_crypto_vendor_health_audit.sql` carries an explicit `-- DOWN` block per the brief's rollback rule.

### 5. One BTC shadow signal graded end-to-end in `signal_outcomes`
**MET** (evidence re-verified directly against the database today; note the brief's own wording says "`signal_outcomes`" but the actual grading columns live on `signals` itself — `outcome`/`outcome_pnl_pct`/`outcome_resolved_at`/`outcome_source`, confirmed present via `information_schema.columns`). Row `id=14893`, `signal_id='S1_PHASE2_SHADOW_TEST_BTC_20260713'` (commit `3b91328`), re-queried 2026-07-15:
```
outcome = 'WIN', outcome_pnl_pct = 0.48465266558966075, outcome_source = 'BAR_WALK',
outcome_resolved_at = 2026-07-13T23:10:46.877Z
```
Exact match to the findings doc's original claim. The same resolver run also correctly graded 3 real, previously-permanently-stuck `Session_Sweep` (BTCUSDT) signals and 1 real equity signal (`ARTEMIS_NKE`) — empirical proof on real, not just synthetic, data. A follow-up correction is recorded in the same doc: the initially-assumed "129-signal backlog" was re-checked post-deploy and found to be 101 `EXPIRED` + 28 `DISMISSED`, both already excluded by the resolver's existing WHERE clause — no actual backlog, self-corrected rather than left standing.

### 6. `hub_get_crypto_quote` live + empirically verified; `hub_get_quote("BTC")` disambiguation (P0 closed); 4 deploy-verification steps; connector re-toggle flagged
**MET.** Commit `90f9d10`. `hub_get_crypto_quote("BTC-USD")` verified live against real BTC price (cross-checked against an independent web quote at ship time). `hub_get_quote("BTC")` (bare, no `asset_class`) returns the disambiguation error naming both candidates rather than silently resolving to the $28 NYSE ETF — **P0 closed**. `hub_get_quote("SPY")` re-verified unaffected (equity path untouched). All 4 deploy-verification steps recorded in `s1-phase3-findings.md`. Nick's connector re-toggle was flagged in that doc and again ahead of the closure smoke pass (item 10).

### 7. Dual-write diff report produced (cutover status recorded either way) — EXCEEDED
**MET, then superseded.** F-4 shipped shadow dual-write first (`2c2263d`) with `scripts/crypto_dual_write_diff_report.py` reporting honestly (0 real rows, dormant scanner — root-caused separately, see below). Fable then ruled an "inverted-shadow" cutover rather than waiting on the diff report's own readiness bar: `process_signal_unified` is now the PRIMARY writer for crypto signals (persistence/Discord/broadcast/committee-flagging/conflict-dismissal all real); the original bypass scorer is demoted to a comparison-only shadow-logger (commit `47b4a79`). The diff report keeps running — see **Bypass-retirement tracker** below, now a standing post-closure item rather than a one-time gate.

### 8. Drogen note committed; `session_sweep` test green (or root cause + fix documented)
**MET.** Commit `a284955`. `docs/strategy-reviews/stater-swap-redesign/drogen-momentum-framework.md` committed with explicit provenance (recovered from the 2026-05-22 session record, never previously committed). `session_sweep`'s known-red test fixed: root cause was a stale hardcoded score predating an Olympus floor retune, not a classifier bug — fixed to use the `TOP_FEED_FLOOR` constant. `test_path_a_footprint_long` explicitly left untouched (different, pre-existing known-red, out of scope).

### 9. Backlog v4 committed, incl. the Olympus-crypto-specialist Tier-3 item
**MET** (commit list corrected after adversarial verification, see below). `docs/build-backlog.md`, first committed as `a284955`, since extended by `42145e6`, `63f1acd`, and `47b4a79` as new findings surfaced (`4af379d`, the datetime-sanitizer fix, does **not** touch this file — corrected here rather than left standing; that commit belongs only under "Findings surfaced" below). ZEUS Phase II promoted to top-of-queue; displacements named (rebuild-stack L1/L2, Outcome Tracking Phase C, committee review logging, Phase B `get_bars`); post-R-2 checkpoint recorded as a standing sequencing gate; HELIOS mockup parallel-track recorded; Olympus-crypto-specialist Tier-3 item present (Titans one-pager required before any build).

### 10. One Olympus committee smoke pass post-tool-ship confirms no regression
**MET.** Run in the coordination lane per the brief's own instruction. BTC-USD via the new hub tools + SPY as control, 14 agents, real skill files + live MCP tools — zero crashes/regressions. Fable countersigned the pass "pending one connector-visibility check on Fable's side" (recorded in `docs/build-backlog.md`'s 2026-07-15 update-log entry, the durable record for this item — no separate smoke-pass transcript was persisted as its own file). The pass itself surfaced two pre-existing, unrelated P1 fake-healthy defects (`hub_get_portfolio_balances`, `hub_get_flow_radar`), both logged to the backlog rather than fixed inline, since S-1's Done Definition doesn't depend on them.

## Findings surfaced during S-1 execution (not blocking closure, all logged)

- **P0 closed:** `hub_get_quote("BTC")` no longer silently resolves to the wrong ETF (item 6).
- **`hub_get_portfolio_balances(account="breakout_prop")`** — fake-healthy defect, named S-6 blocking dependency. Backlog Tier 1 #3.
- **`hub_get_flow_radar` crypto-blindness** — fake-healthy defect. Backlog Tier 2.
- **Crypto Scanner 12-day dormancy** — root-caused as a genuine bearish market condition (12/15 tickers in CAPITULATION/WATERFALL CTA zones) combined with the scanner being long-only by design, not a bug. Backlog Tier 2 #5 (strategy-emission flatline watchdog) added as a result.
- **3/15 `CRYPTO_TICKERS`** (MATIC-USD, UNI-USD, APT-USD) silently delisted on yfinance. Parked for R-2 per Fable's instruction.
- **`tradingview.py::is_crypto_ticker()`** misses hyphenated tickers (`"BTC-USD"` not recognized). Backlog Tier 2 #6 — being closed by the new canonical-ticker-normalization item below.
- **Platform-wide datetime-serialization bug**: `process_signal_unified()` injected a raw `datetime` into every signal's `expires_at`, and two of three duplicate `sanitize_for_json()` copies didn't handle it — silently breaking Redis cache + WebSocket broadcast for every signal from every source (not crypto-specific, not introduced by S-1, but exposed for crypto by the F-4 cutover). Fixed 2026-07-15 (`4af379d`): consolidated into `backend/utils/json_sanitize.py`, unit-tested, verified live with zero warnings post-deploy.
- **Ticker-format inconsistency across the three crypto signal sources** (`BTCUSDT` vs `BTC-USD` vs raw TradingView format) — means cross-strategy conflict-dismissal cannot currently trigger for the same coin across engines. Addressed by the new canonical-ticker-normalization backlog item below (R-2), which explicitly closes Tier 2 #6 and enables real conflict-dismissal.

## Bypass-retirement tracker (standing post-closure item)

F-4's cutover (`47b4a79`) made `process_signal_unified` the real writer for crypto signals; the original bypass scorer is demoted to a comparison-only shadow-logger (`backend/jobs/crypto_dual_write_shadow.py::log_bypass_shadow_comparison`), writing into `crypto_dual_write_shadow` (migration 024, reused, roles inverted).

**Retirement bar (unchanged from the brief's own F-4.1 numbers):** ≥48h of real operation OR n≥30 real (unified-path) signals, whichever comes first — tracked by `scripts/crypto_dual_write_diff_report.py`. As of this closure note, the table holds 3 rows, all one-off tagged tests (`S1_PHASE4_DUALWRITE_SMOKE_BTC_20260715` — pre-cutover plumbing check; `S1_PHASE4_CUTOVER_SMOKE_BTC_20260715` — cutover verification; `S1_PHASE4_DATETIME_FIX_VERIFY_BTC_20260715` — datetime-fix verification) — **none count toward the bar**, which restarts from whenever the Crypto Scanner next produces a real signal (currently dormant per the CAPITULATION-zone finding above).

**Action on retirement, once the bar is met:** remove `log_bypass_shadow_comparison()`'s call site in `bias_scheduler.py::run_crypto_scan_scheduled()`, delete the now-redundant bypass `calculate_signal_score()` call, and decide whether `crypto_dual_write_shadow` itself is dropped or kept as a historical audit table (Nick's call, not automated). This is a standing item — not part of any currently-scheped phase — whoever next touches the Crypto Scanner should check `scripts/crypto_dual_write_diff_report.py`'s output first.

## New backlog item (this closure)

**Canonical ticker normalization at pipeline ingress** — reuses `backend/jobs/crypto_bars.py::normalize_crypto_ticker()` (already built and proven in F-2) at the point every crypto signal source writes its `ticker` field, so `crypto_setups.py` (`BTCUSDT`), the Crypto Scanner (`BTC-USD`), and the TradingView webhook path (raw alert ticker) all persist the same canonical form for the same coin. Slotted for **R-2**. Closes backlog Tier 2 #6 (`is_crypto_ticker()`'s hyphenated-ticker miss becomes moot once ingress is normalized upstream of that classifier). Also **enables real crypto conflict-dismissal** — `_check_and_clear_conflicting_signals()`'s exact-string ticker match currently can't catch cross-strategy conflicts on the same coin; normalization is the prerequisite, not a fix to that function itself.

## Verification note

Before sign-off, every Done-item citation in this note was independently re-checked against actual commit diffs, live file content, and (for item 5) a direct database query — not carried over from memory. Two citation errors were caught and corrected in place rather than left standing: item 2 originally claimed matrix cells use the literal label `UNVERIFIED` (they actually use `UNAVAILABLE`/`GEO_BLOCKED` with stated reasons — same spirit, different vocabulary; also caught a stale caveat on ZEC's Phase 1 matrix entry that Phase 2 had already resolved), and item 9 originally listed `4af379d` as a commit that extended the backlog (it doesn't touch that file at all). Everything else confirmed clean on the first pass.

## Sign-off

CC flags S-1 as closed per the brief's own Done Definition, with F-4 exceeded (cutover shipped, not just the diff report) per Fable's ruling. Both acknowledgments are now on record and the gate ("Nothing in R-1+ may start until this brief's Done definition is met") is cleared:

- **Nick — SIGNED, 2026-07-15 22:28Z (16:28 MDT).** Empirical connector check: Pandora connector re-toggled post-tool-ship; `hub_get_crypto_quote("BTC-USD")` returned live Bitcoin (fresh timestamp, clean v2.0 envelope, correct asset) through Nick's own Claude.ai connector — the Done-item-10 connector-visibility condition is satisfied.
- **Fable — COUNTERSIGNED, 2026-07-15.** The "pending one connector-visibility check" condition attached to the item-10 countersign is resolved by the same check. S-1 is formally closed.

R-1 work (Brief S-2, `docs/codex-briefs/2026-07-15-stater-swap-s2-regime-session-brief.md`) is cleared to begin.
