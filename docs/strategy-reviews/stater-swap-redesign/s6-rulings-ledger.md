# S-6 RULINGS LEDGER — Stater Swap v2 · C2 Cockpit Grid

Authoritative running record of gate decisions and Phase-0 reconciliation rulings for the S-6 build. Where the render, charter, and brief disagree, the resolution adopted is recorded here with its provenance.

**Brief:** `docs/codex-briefs/2026-07-23-s6-stater-swap-v2-build-brief.md` (S6-BUILD-01)
**Phase 0 findings:** `docs/strategy-reviews/stater-swap-redesign/s6-phase0-findings.md`
**Build branch:** `s6-stater-build` (NOT main — deploy is SG-2-gated)

## Gate log

| Date | Gate / Item | Ruling | By | Source |
|---|---|---|---|---|
| 2026-07-23 | Mockup gate (S-6) | **C2 Cockpit Grid** selected as final direction; iteration deferred to in-use tweaks | Nick | `helios-mockup-track.md` |
| 2026-07-23 | Titans final review | Brief **APPROVED**; six conditions (C-A1/2/3, C-H1/2, C-S1, C-T1/2) folded into text | ATLAS · HELIOS · AEGIS · ATHENA | `2026-07-23-titans-final-s6-brief.md` |
| 2026-07-24 | **SG-0** (Phase 0 gate) | **STOP → resolved via Option A.** No enforced discipline endpoint exists (C-A1). Adopt honest-seam descope. | Nick | Phase 0 P0.3 |
| 2026-07-24 | **SG-1** (layout gate) | **CLEAR** — scaffold (S5.1 chips + S5.2 grid) matches the approved render | HELIOS via Fable | scaffold `1b47e82` |

## SG-0 Option A — honest-seam descope (detail)

The brief's §5.6 requires discipline chips to render *enforced* backend state, never client math; the fail-closed doctrine makes fake-healthy a P0 bug. Phase 0 found **no enforced discipline endpoint** — only advisory `/api/analytics/risk-budget`, where concurrent-count is real but daily-loss is a static `$1000` placeholder and cooldown does not exist. Ruling:

- **Discipline chips (S5.6):** `CONCURRENT · N / 2` rendered from `risk-budget`, **labeled advisory** (not an enforced gate). `DAILY · N/A — not tracked` (honest seam; never a fabricated `$0`). `COOLDOWN` omitted / N/A (not implemented). No fake-healthy financial-safety state ships.
- **S5.7 unbacked fields → honest seams:** governance shadow/live tag (`crypto_gate_shadow` is writer-only, no read API), est. funding-cost-over-hold (does not exist), liquidation-distance-in-ATRs (documented un-sourceable) all render unavailable-with-reason. Entry / invalidation / size are real.
- **Distance-to-floor (S5.1/S5.2):** `breakout_prop` untracked → empty ring + "N/A — breakout_prop not reported." Never zero, never full.

## P0.4 reconciliation rulings

Adopted per CC Phase-0 recommendations and ratified by Nick's 2026-07-24 directive to build drawer → dial → feed → macro band. Each remains subject to the SG-3 screenshot comparison (HELIOS standing veto).

- **P0.4-1 · Macro band content.** Charter/brief §5.5 say DXY / real-yields / calendar; the concept plan and the approved render say funding / OI / basis / liquidations. **Ruling: build to the render** (funding/OI/basis/liqs, BTC-master) — the render is top-precedence and is the SG-3 target. The charter's DXY/real-yields/calendar macro context is **logged as deferred coverage**, not silently dropped.
- **P0.4-2 · Cycle dial.** The approved render labels the dial "S-5 · DIAL PENDING BUILD," but `/api/crypto/cycle-extremes` returns a live `composite_score` marker today (only Signal #10 ETF-flow-exhaustion is S-5-deferred). **Ruling: render the live single-axis marker** from `composite_score` (matches the render's marker-at-CAPITULATION visual); keep an honest "S-10 input deferred (S-5)" note.
- **P0.4-3 · `cta_zone` relabel.** `cta_zone` is an equities field, absent from every crypto payload. **Ruling:** the drawer/dial "cycle position" reads from cycle-extremes `composite_score` / `capitulation_context_copy`, not a `cta_zone` field.

## Data-quality item (contained, backend follow-up)

- **FARTCOIN fake-healthy price.** `/api/crypto/market` returns a bogus `binance_spot: 506.59` for FARTCOIN (not listed on Binance spot; real ≈ `0.1333`; the payload's own `spread: -506.45` flags it). The client (`stater.js::priceOf`) rejects cohort outliers (>25% from median) so no fake price ships. Real fix is backend — tracked as a separate item.

## Still open (do not block the current build)

- SG-2 (pre-deploy Fable go) and SG-3 (post-deploy HELIOS screenshot comparison, 2026-08-03) remain binding.
- Branch `s6-stater-build` must be rebased on `main` before the SG-2 deploy.
- Timeline law: deploy by **2026-07-31** or S-6 holds past the 2026-08-04 → 08-15 freeze.
