# CTA/Artemis Decompose (§8.2) + Pre-UW vs UW-Era (§8.3) — re-analyses

**Date:** 2026-06-16 · READ-ONLY (no writes) · Parent: rebuild brief §8.2/§8.3; validation doc.
**Data:** `signals`, resolved WIN/LOSS pool. P&L unit `outcome_pnl_pct`; expectancy = mean over pool.

## §8.2 — CTA Scanner is a mixed bucket. Thesis CONFIRMED. Route by signal_type; do NOT kill the parent.

CTA Scanner parent = −0.425 (n=1,391). Decomposed by `signal_type`:

| signal_type | n | WR% | Exp | Total | verdict |
|---|---|---|---|---|---|
| GOLDEN_TOUCH | 21 | 52.4 | +1.75 | +37 | KEEP (low-vol gem) |
| TRAPPED_SHORTS | 54 | 37.0 | +0.82 | +44 | KEEP |
| TWO_CLOSE_VOLUME | 30 | 36.7 | +0.82 | +25 | KEEP |
| APIS_CALL | 138 | 37.7 | +0.61 | +84 | KEEP (best volume) |
| BEARISH_BREAKDOWN | 12 | 41.7 | −1.09 | −13 | suppress (small-n) |
| PULLBACK_ENTRY | 744 | 29.6 | −0.25 | −189 | SUPPRESS (high-vol bleeder) |
| RESISTANCE_REJECTION | 354 | 37.0 | −1.37 | −483 | SUPPRESS single-name / KEEP liquid |
| TRAPPED_LONGS | 38 | 34.2 | −2.54 | −97 | SUPPRESS |

Routing the +190 (4 positive types) and cutting the −782 (bleeders) flips CTA from −592 to **+190**.

Sub-findings:
- **Seed's "PULLBACK_ENTRY reaches top_feed / IS the top_feed edge" hypothesis is FALSE.**
  PULLBACK_ENTRY is a high-volume bleeder (−0.25) and reaches *zero* top_feed in resolved data
  (research_log/watchlist/ta_feed only, all negative). The thin top_feed edge is not CTA pullbacks.
- **Universe effect is signal_type-specific** — breaks the uniform "bias to liquid" rule:
  RESISTANCE_REJECTION = +0.73 in liquid (55% WR, n=56) but −1.76 in single-names; APIS_CALL is the
  *opposite* (+1.52 single-name, breakeven liquid). Liquid-gating must be applied per signal_type.
- **Golden Touch** = CTA `GOLDEN_TOUCH` signal_type: 91 total / 21 resolved, +1.75 exp / 52% WR.
  Real low-frequency edge, buried in the negative parent aggregate.

Artemis decompose: ARTEMIS_SHORT +0.04 (breakeven, n=1,086), ARTEMIS_LONG −0.11 (n=1,118).
Consistent with no-long-edge; ARTEMIS_SHORT salvageable-marginal, not a gem.

**L0 action:** signal_type-level routing for CTA. Keep the 4 positive sub-types (+ RESISTANCE_REJECTION
liquid-only). Suppress PULLBACK_ENTRY, RESISTANCE_REJECTION single-name, TRAPPED_LONGS, BEARISH_BREAKDOWN.

## §8.3 — Pessimism is NOT mainly a pre-UW data artifact. Kills stand.

Cutover assumed **2026-05-24** (get_bars / UW real-time bars migration — VERIFY exact date).

| segment | n | WR% | Exp |
|---|---|---|---|
| pre-UW (overall) | 8,098 | 34.0 | −0.455 |
| UW-era (overall) | 1,612 | 25.7 | −0.511 |

UW-era is **not better** — marginally worse. Per-strategy pre → uw expectancy:

| strategy | pre | uw | read |
|---|---|---|---|
| Holy_Grail | −1.24 | −0.56 | less-bad on clean data, STILL negative → kill holds |
| sell_the_rip | +0.86 | −0.78 | collapse is the regime flip (late-May/Jun), n=87 |
| CTA Scanner | −0.37 | −0.67 | worse |
| Artemis | −0.01 | −0.13 | worse |
| Crypto Scanner | −1.55 | −4.33 | worse |

**Heavy regime confound.** The pre/post split is time-entangled with regime. Monthly expectancy:
Feb +0.12, Mar +0.09, **Apr −1.55 (the −3,872 catastrophe)**, May −0.11, Jun −0.68. The April disaster
sits in the pre-UW bucket; the UW-era window (late-May–Jun) is post-April chop + sell_the_rip's
regime-flip collapse. So UW-era ≠ clean-regime, and §8.3 cannot cleanly isolate data-quality from
regime at the aggregate level.

**Actionable conclusion:** clean UW data does NOT rescue any killed strategy — none flips
negative→positive in the UW-era. Holy_Grail improves but stays negative (kill holds). The dataset's
negativity is structural (strategy + regime), not a data artifact.

**Caveats:** UW-era = only ~17% of resolved signals and recent; sell_the_rip UW n=87. Re-run as
UW-era data accumulates. Cutover date is an assumption — confirm the real UW wire-in date.
