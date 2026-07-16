# Titans Review Record — Stater Swap v2 (ZEUS Phase II)

**Date:** 2026-07-13 | **Lane:** Coordination (Fable) | **Repo state reviewed:** `main` @ `30c3921`
**Build source:** `docs/strategy-reviews/stater-swap-redesign/2026-07-12-stater-swap-v2-committee-brief.md` (incl. Addendum A, decisions D1–D4)
**Output brief:** `docs/codex-briefs/2026-07-13-stater-swap-s1-foundation-brief.md`
**Full pass transcript:** coordination-lane session 2026-07-13. This record is the durable summary; the brief carries the binding S-1 tasks.

## Verdicts

| Stage | ATLAS | HELIOS | AEGIS | ATHENA |
|---|---|---|---|---|
| Pass 1 | No veto, HIGH | No veto (mockup gate standing), MODERATE | No veto, HIGH | No veto, PROCEED, HIGH |
| Pass 2 | HIGH (unchanged) | MODERATE (unchanged) | HIGH (unchanged) | PROCEED (unchanged) |
| Overview | — | — | — | **PROCEED TO BRIEF, HIGH** |
| Final review (on S-1) | APPROVE (A1, A2) | APPROVE (A5) | APPROVE (A3, A4) | APPROVE (A1–A5 + this record) |

Validate-before-design satisfied on evidence (live-verified P0 wrong-asset quote; Phase-0 audit in committee brief Part 1). No validation flags. No vetoes at any stage.

## Nick decisions at Clarify (2026-07-13)

1. **Post-R-2 checkpoint:** deferred to Fable → **taken.** Forced reassessment of rebuild-stack L1 vs. continuing to R-3/R-4 before the back half proceeds.
2. **Mockup parallel-track:** approved. HELIOS concept production runs during R-0/R-1; design ≠ build, so the "R-5 forbidden before R-0 ships" line binds builds only.
3. **MIDAS / OCEANUS:** remain one-off guest seats. New Tier-3 backlog item: permanent Olympus crypto specialist seat (MIDAS-class skill), Titans one-pager required before any build. (Recorded via S-1 task 5.3.)

## Agreed scope (Pass 2 amendments to the R-stack)

- A-1 Symbol Capability Matrix gains two columns: **BAR_WALK bars source** and **Binance-fail fallback**
- F-3 gains the **consolidated per-symbol state envelope** (`/crypto/state/{symbol}`), carrying tier + capability flags from the matrix
- F-2 built as the **shared asset-class-aware resolver core** (15-min walker), which Outcome Tracking Phase C later consumes
- F-1 gains **per-feed input sanity bounds** (reject + never cache) and the **Data Source Hierarchy table update**
- S-1 carries the **webhook HMAC coverage check** and **backlog v4**
- Gate/threshold parameters introduced anywhere in this program are **config-driven, hot-reloadable** — no redeploy-to-tune
- Boundary settled: UI refresh may pause on hidden tab; **backend collection never pauses**
- Binance geo-block resolution is **replace, never evade** (no proxy/VPN)
- Tier-3 symbols contained to the funding/OI/liquidation strategy class for all of v2

## Final-review amendments applied to S-1 (A1–A5)

- **A1 (ATLAS):** F-2 extension target named — `outcome_resolver.py` (15-min walker); daily-walker crypto support deferred to S-4
- **A2 (ATLAS):** any schema migration ships with an explicit `-- DOWN` rollback block
- **A3 (AEGIS):** health-state transitions + sanction/replace decisions write audit-log entries
- **A4 (AEGIS):** task 1.7 rotation guidance per `docs/operations/mcp-token-rotation.md`
- **A5 (HELIOS):** state envelope carries tier + capability flags from the matrix

## Carry-forward obligations (binding on future briefs)

| Brief | Obligation | Owner lane |
|---|---|---|
| S-2 | R-1 regime/session gates config-driven, hot-reloadable; regime states shadow-logged for validation before gating goes live | ATLAS |
| S-2 | Session clock Denver-localized or dual-labeled (UTC sessions × America/Denver user) | HELIOS |
| S-3 | Cycle Extremes: staleness contract on every signal cell; FROTH copy reads "reduce new risk," never "sell"; dial rendered as single-axis marker, not two tables (mockup decision) | HELIOS |
| S-4 | **Anti-Bloat classification table**: every strategy candidate classified REPLACES / ELEVATES / ADDS with a named deprecation target (one-in-one-out mandatory) before enrollment | ATHENA |
| S-4 | Discord embed parity: funding cost over intended hold, liquidation-distance-in-ATRs, tier badge; regime + session + tier legible in the embed's first line | HELIOS |
| S-4 | Carry-asymmetry display on funding-fade cards (DAEDALUS rule); negative-funding fades require stronger structural trigger; no negative-funding-fade longs at Tier 3 | ATLAS |
| S-4 | Daily-walker crypto support ships here if WRR-on-BTC-daily enrolls; RSI-2 perp re-test lowest priority, CHOP-gated, shadow-only | ATLAS |
| S-5 | UW ETF-flow polling sized against the 17K/18K watchdog thresholds before enablement | ATLAS |
| S-5 | Macro band Horse-Rule-separated (context only, zero scalp-score inputs); pre-print entry freeze implemented as a risk/timing rule | ATLAS |
| S-6 | **MOCKUP GATE:** ≥3 approved concepts showing the multi-symbol switcher, per-symbol N/A states, tier badges, and at least one Tier-3 (e.g., FARTCOIN) view; final sign-off before brief; post-deploy screenshot comparison | HELIOS (standing veto) |
| S-6 | Distance-to-floor in header, always visible, red-state thresholds; discipline chips render enforced backend state; visibility-based polling client-side only | HELIOS |
| Standing | Post-R-2 checkpoint: reassess rebuild-stack L1 vs. R-3/R-4 before proceeding | ATHENA |
| Standing | Olympus Impact section + connector re-toggle + BTC/SPY committee re-test on every brief that ships hub MCP tools | ATHENA |

## Displacements (named)

Activating ZEUS Phase II defers: rebuild-stack **L1 (Signal Quality)** and **L2**, **Outcome Tracking Phase C** (partially self-paying via F-2), **committee review logging**, **Phase B `get_bars` migration**. Offset: R-0 absorbs four already-queued items (wrong-asset quote P0, crypto L0 routing bypass, `session_sweep` red test, BTCUSDT ticker support).
