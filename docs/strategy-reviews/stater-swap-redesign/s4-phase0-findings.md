# S-4 Phase 0 Findings (2026-07-19)

Read-only reconnaissance per `docs/codex-briefs/2026-07-16-stater-swap-s4-strategy-layer-brief.md` §1. Five items (0.1–0.5) run in parallel via independent research agents; 0.6/0.7 run directly. **Several findings contradict the brief's assumptions — flagging per the brief's own rule before touching Phase 1.** Severity varies; see the Verdict section.

## Verdict — what needs a call before proceeding

- **0.3 is the blocking one.** The brief's entire Phase 2 (Discord embed parity) assumes it's adding 4 fields to an *already-live* crypto-aware embed. It isn't live. The VPS-deployed `signal_notifier.py` is a stale 382-line pre-crypto version with no `post_crypto_signal_alert`, no `is_signal_crypto`, no argparse at all — the `--crypto` cron flag has been a silent no-op. Production crypto Discord alerts today render through the old equity-style path, showing none of the market-structure/POC/CVD fields the brief (and I, when I authored it) assumed were already shipping. Closing the 4 named gaps on top of a function that isn't deployed needs the local repo's crypto-aware `post_crypto_signal_alert` deployed to the VPS FIRST, as a bundled prerequisite, not assumed pre-existing infrastructure.
- **0.1 and 0.5 found real contradictions too, but both are absorbable** — not gates, just corrections to how Phase 1/Phase 4 get built. Documented below with the corrected plan already worked out.
- **0.4 (ATLAS's binding precondition) is clean and satisfied** — a concrete, existing-field-based "stronger structural trigger" definition came back with no complications. Phase 3 can use it as-is when that phase starts.
- **0.2 found no contradiction**, just real nuance the brief's binary applies/doesn't-apply framing didn't have room for (documented, not blocking).

Given 0.3's severity, **recommend Fable/Nick weigh in on sequencing before Phase 1** — not because Phase 1 (the Anti-Bloat table) is blocked by it, but because the overall brief's Phase 2 scope needs to expand to include "deploy the existing crypto embed code" as an explicit first step, which changes the effort/sequencing picture for the whole brief.

---

## 0.1 — Strategy population re-verification

**Contradicts the brief's six-strategy assumption.** `SELECT DISTINCT strategy FROM signals WHERE asset_class='CRYPTO'` returns **8** distinct values, not 6:

| strategy | status | count | notes |
|---|---|---|---|
| Crypto Scanner | REAL | 830 | 2026-03-03–07-03. Graded (excl. COUNTERFACTUAL_*): WIN=12/LOSS=105 (117 graded), win rate 10.3%, expectancy ≈ −2.50%/signal |
| Session_Sweep | REAL | 143 | 2026-03-13–07-19. Graded: WIN=4/LOSS=9 (13 graded), win rate 30.8%, expectancy ≈ −0.108%/signal. `signal_outcomes` table shows a disjoint vocabulary (EXPIRED=124/PENDING=17/STOPPED_OUT=2, no WIN/LOSS) — two unreconciled outcome-tracking layers, flagged not fixed |
| **CVD_ABSORPTION** | **REAL, NEW** | 3 | First fired 2026-07-18 23:03–23:22 UTC — this session's own S-3b Item 2 work, one day before this research ran. Not in the brief's six-name list at all |
| Funding_Rate_Fade | THEORETICAL | 0 | Never fired |
| Liquidation_Flush | THEORETICAL | 0 | Never fired |
| Holy_Grail | THEORETICAL | 0 | Never fired |
| Exhaustion | THEORETICAL | 0 | Never fired |
| 5× `S1_Phase*`/`S2_Phase4_*` labels | NOISE | 1 each | One-shot pipeline-verification/smoke-test signals from the S-1/S-2 rollout (2026-07-14–16), not trading strategies — confirmed in `docs/build-backlog.md` and the s1-phase2/phase4 findings docs |

**Resolution, not a gate:** CVD_ABSORPTION is real and needs a 7th row in Phase 1's classification table (REAL, n=3, too new to grade). The 5 noise labels need a footnote excluding them from the strategy count. Neither changes how the Anti-Bloat framework applies — just the enumeration.

**Also surfaced, worth a separate ticket, not S-4's to fix:** `signals.outcome` and the joined `signal_outcomes` table disagree on vocabulary/values for both Session_Sweep and CVD_ABSORPTION — two outcome-grading pipelines that aren't reconciled. Flagging per the same discipline as every other cross-cutting finding this program has surfaced.

---

## 0.2 — Anti-Bloat framework applicability

No contradiction of the brief's own hypothesis, but the binary "equity-specific vs. transfers" framing undersells real nuance. Full sub-rule verdicts:

| sub-rule | verdict |
|---|---|
| Core Classification (REPLACES/ELEVATES/ADDS/REJECTED) | **APPLIES AS-IS** — pure governance taxonomy |
| Confluence caps (cash≤3, derivatives≤2 additive, 4+ override bar) | **APPLIES AS-IS** on the cap numbers; derivatives **APPLIES-DIFFERENTLY** on the named menu — funding/OI/basis/skew (Coinalyze/Deribit) substitute for IV rank/GEX/max pain, which mostly don't exist for crypto (no dealer-gamma market in perps/spot) |
| Filter rules (subtractive-only, ≥30% weekly-count test) | **APPLIES AS-IS**, and arguably *more* load-bearing for crypto — 24/7 + 5-min cadence + webhooks with no session close to cap volume naturally |
| ADD: provisional-until-backtest | **APPLIES AS-IS**, already organically followed — S-2/S-3 both ship `gating_enabled=false`/`dial_writes_to_feed=false` shadow-only |
| ADD: mandatory named deprecation target | **APPLIES AS-IS as a rule, UNSATISFIED as a fact** — no crypto ADD to date has one; Phase 1's table is the first attempt |
| Location-Quality Multiplier (PYTHIA, VA-edge grading) | **APPLIES-DIFFERENTLY, partially built.** POC/VAH/VAL exist (`btc_market_structure.py`); S-3b's CVD divergence/absorption is a *trigger-location gate*, not a +0.5/−0.5 grade multiplier. The "prior-session developing VA" anti-lookahead rule **does not cleanly map at all** — crypto has 3 rolling 8h partitions (Asia/London/NY) plus a 24h composite, so "prior session" is multi-valued and genuinely unresolved anywhere in the repo, not just unported |
| Sector-Rotation Regime Spec (THALES) | **DOES-NOT-APPLY literally** (no sectors, grep-confirmed zero crypto wiring to any `sector_rs`/`sector_rotation` module) — **APPLIES-DIFFERENTLY via an identified-but-unbuilt analog**: BTC dominance/ETH-BTC/alt-breadth, named explicitly in the committee brief (Addendum A-3), currently `alt_gate.status="NOT_AVAILABLE"` in `crypto_gate_config_seed.py`. The closest live mechanism (`master_rules`' trend-down hard-blocks) is a different regime axis (trend, not rotation) and a binary block, not the equity rule's soft 0.75x penalty |
| Signal Enrichment at Trigger Time | Sector-rotation tag: **DOES-NOT-APPLY** (unbuilt analog). Auction-state tag: **APPLIES-DIFFERENTLY with a real substitute already shipped** — `regime_symbol`/`regime_master` + `session_partition` are live in `crypto_gate_shadow` rows today. Prior-session VA-relative context: blocked on both the same partition-ambiguity issue above AND S-3's spot-feed hard-stop (now resolved by S-3b, so this may be less blocked than when the committee brief was written — worth re-checking). IV rank: **DOES-NOT-APPLY, firmly** — no listed crypto options in Nick's accounts at all, not a data-source gap |

---

## 0.3 — Discord embed parity: current inventory + the 4 gaps (SEVERITY: HIGH, see Verdict)

Confirmed current embed inventory in `scripts/signal_notifier.py::post_crypto_signal_alert` (lines 313-450, local repo): direction, entry/stop/target, R:R + risk $, market-structure POC/CVD/book-imbalance, breakout sizing, session+score, Take/Watching/Pass buttons. Matches the brief's description accurately — **for the local repo.**

**Critical finding: this function has never been deployed to the VPS.** Live SSH read of `/opt/openclaw/workspace/scripts/signal_notifier.py` on the VPS shows a 382-line pre-crypto version — no `post_crypto_signal_alert`, no `is_signal_crypto`, no argparse. Both cron entries (`*/15 14-21 * * 1-5` equity, `*/5 * * * * --crypto`) point at this same stale file; the `--crypto` flag is silently ignored since there's no argparse to read it. **Every live crypto Discord alert today renders through the old equity-style path.**

Per-gap sources (with corrections to the brief's assumed locations):

| gap | brief assumed | actual | status |
|---|---|---|---|
| 1. Funding cost over hold | `binance_client.py` | `coinalyze_client.py:190` `get_funding_rate(symbol)` — `binance_client.py` has zero funding code (only spot orderbook skew + quarterly basis) | Rate source exists (S-3 FA-7 parametrized, all 6 symbols). **"Intended hold duration" has no existing derivation from a signal's `timeframe` field anywhere in the repo — genuine build gap, needs a new convention** |
| 2. Liquidation-distance-in-ATRs | ATR calc in `btc_market_structure.py` | No ATR calc there at all (grep-confirmed zero references). Canonical ATR is `indicators/atr.py::latest_atr()`, wired ONLY to UW *equity daily* bars today, never crypto | `get_liquidations()` (`coinalyze_client.py:448`) exists but returns backward-looking rolling liquidation volume/composition, **not price-level clusters** — "distance to a liquidation cluster" has no data source in the codebase at all. Needs a decision: build true cluster-distance (new vendor work) or redefine as "ATR-normalized recent liquidation flow" (buildable now with what exists) |
| 3. Tier badge | `crypto_gate_config`'s tiers dict, canonical | Real, but there are **two parallel, currently-identical, architecturally separate** tier sources: `crypto_gate_config` (DB, hot-reload, consumed only inside `crypto_gates.py`, no HTTP route) vs. `crypto_symbol_matrix.py`'s `SYMBOL_TIER` (code-deploy, already HTTP-exposed via `/api/crypto/state`/`/api/crypto/regime`) | Values agree today but could drift independently. Simplest integration reuses the already-HTTP-live source — a design choice to confirm, since the brief specifically named the other one canonical |
| 4. First line `{regime}\|{session}\|Tier {n}` | `/api/crypto/regime` + `/api/crypto/clock`, VPS connectivity to confirm | Both endpoints confirmed exactly as named, no auth dependency. **VPS-to-hub HTTP connectivity empirically confirmed** — live curl from the VPS during this research returned HTTP 200 for `/api/crypto/regime` (~0.3s), `/api/crypto/clock` (~0.3s), and `/api/crypto/state/BTC` (~4.7s — sequential sub-fetches, worth profiling before relying on it inside a 5-min cron batch) | Confirmed working. Integration must go through HTTP (the VPS notifier is sync/urllib-only, no DB/vendor credentials, no backend module imports possible) |

**Sequencing implication:** Phase 2 as scoped ("close 4 gaps") needs to become "deploy the current local `post_crypto_signal_alert` to the VPS, THEN close 4 gaps on top of it" — a materially larger Phase 2 than the brief describes.

---

## 0.4 — Funding-fade "stronger structural trigger" (ATLAS's binding precondition): SATISFIED

Read `check_funding_rate_fade` in full (`backend/strategies/crypto_setups.py:119-187`). Confirmed neither proposed rule exists anywhere in the file, `crypto_gates.py`, or `signals/pipeline.py` (grep-confirmed, zero matches for tier/structural/negative-funding terms).

**Concrete, implementable definition** (existing field, existing value, no new dimension — matching ATLAS's exact constraint):

> When `rate < 0` (the LONG/negative-funding-fade branch), raise the entry-qualification floor on the already-computed `abs_rate` field from `>= 0.0003` (the function's existing MEDIUM-confidence floor, line 142) to `>= 0.0005` (the function's own existing HIGH-confidence boundary, line 162 — reused, not invented). The positive-funding/SHORT branch keeps `>= 0.0003` unchanged. Net effect: negative-funding LONGs can only ever fire at HIGH/VERY_HIGH confidence (score ≥75); positive-funding SHORTs still fire at MEDIUM (score ≥65) as today.

Confirmed Tier 3 = HYPE-USD/ZEC-USD/FARTCOIN-USD, live in `crypto_gate_config` (all 3 versions checked, current id=3) and the seed file — needed for gating rule 2 (§4.3). Confirmed rule 2 belongs in `crypto_gate_config` + `crypto_gates.py` (config-driven), per the brief's own §4.3 instruction — NOT in `crypto_setups.py`, a different implementation home than rule 1. `crypto_gates.py`'s `evaluate_gates()` currently has no visibility into funding sign; recommend inferring "negative-funding-fade" from `(strategy=='Funding_Rate_Fade' AND direction=='LONG')` rather than threading the raw rate into the gate evaluator — sufficient and avoids a new field.

**Open, not blocking:** whether `Funding_Rate_Fade` has fired since S-2 Phase 0 was independently re-confirmed in 0.1 above — still 0/theoretical, so §4.4's shadow-tag-or-enforce question resolves to: no live signals exist yet, shadow-tag by default per the program's standing posture regardless.

---

## 0.5 — Daily-walker crypto support: technical plan (with brief-assumption corrections)

Confirmed `score_signals.py` is equity-only today — zero `asset_class` references anywhere (grep-confirmed), matching S-1 F-2's finding. Cron-gated to `mon-fri 21:00 ET` (`bias_scheduler.py:2793-2797`) plus an internal `is_trading_day()` NYSE-calendar check — no crypto bypass, unlike `outcome_resolver.py`'s dual-loop (equity-hours-gated + 24/7 crypto).

**Two corrections to the brief's "mirror outcome_resolver.py" framing:**

1. `signal_outcomes` (the table `score_signals.py` reads) has **no `asset_class` column and no FK to `signals`** (confirmed: `postgres_client.py:516-536` schema) — `outcome_resolver.py`'s column-based dispatch (`WHERE asset_class = $1`) cannot be literally mirrored. Dispatch has to become ticker-format detection (`normalize_crypto_ticker()` on the symbol column) instead.
2. The "walk logic" the brief warns against duplicating isn't actually shared between the two walkers even on the existing equity path — `outcome_resolver.py`'s `_walk_touch` (2-state WIN/LOSS vs. a single target+stop) and `score_signals.py`'s inline loop (4-state HIT_T1/HIT_T2/STOPPED_OUT/INVALIDATED with continuation-past-T1 and whole-history max_favorable/max_adverse) are structurally different, independently-implemented models. "Don't fork a second implementation" is best satisfied by never touching the walk loop at all, confining the diff to the bar-fetch boundary.

**Minimal-diff plan:** make `_fetch_history` (`score_signals.py:94-99`) asset-aware — try `normalize_crypto_ticker(symbol)` first; if it resolves, call `fetch_crypto_ohlc(base_symbol, use_daily=True)` (NOT `fetch_crypto_bars`, which drops Close — needed for the INVALIDATED check and `outcome_price`), client-filter to `ts >= start`, wrap into a DataFrame matching yfinance's existing shape; if normalization fails, fall through unchanged to the existing yfinance call. Zero changes to `crypto_bars.py` itself, zero changes to the walk loop (lines 133-268 untouched).

**Flagged, not solved (read-only scope):** the mon-fri-21:00-ET cron gate would still skip crypto on weekends — low severity since the walker re-walks full history each run, so a Monday run still catches a Saturday stop-out with reporting latency, not a missed outcome. Not addressed here per the brief's own "capability only, no enrollment" scope.

---

## 0.6 — Bypass-retirement tracker

Ran `scripts/crypto_dual_write_diff_report.py` per the standing instruction. Retirement bar (F-4.1: ≥48h OR n≥30) **MET** (101.4h since first row). 3 comparison rows, would_suppress=false across all, 0/3 flagged for committee review. No action taken — informational per the standing instruction; full retirement still requires Nick's explicit go-ahead per the F-4.2 addendum.

## 0.7 — Known-red baseline

`18 failed, 391 passed, 1 skipped, 203 errors` — same composition confirmed all night (2 feed-tier/scanner + 2 countertrend + 14 `test_uw_api_mapping.py`), unchanged since DEF-ENRICH-CLOBBER's completion.

---

## Status

**Not proceeding to Phase 1 yet — reporting for a sequencing call given 0.3's severity.** 0.1/0.5's contradictions are absorbable and already have corrected plans above; 0.4 is clean; 0.2 is nuance-only. 0.3 changes Phase 2's real scope (deploy the existing crypto embed to the VPS as a prerequisite, not assumed live) enough that it's worth a decision on sequencing before continuing, matching this program's standing discipline of stopping on brief-contradicting findings rather than absorbing everything silently.
