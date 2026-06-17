# Regime Gate (mean-reversion resolution) + Flow-Wiring Audit

**Date:** 2026-06-16 · READ-ONLY (no writes) · Parent: Olympus committee pass; rebuild brief §3 (L1);
validation doc `signal-edge-validation-2026-06-16.md`.
**Data:** `signals` resolved WIN/LOSS pool. P&L unit `outcome_pnl_pct`; expectancy = mean.

## Finding 1 — Sell the Rip + Trapped Shorts are MEAN-REVERSION. The gate is trend strength, not bias direction.

Resolves the committee's open question (PYTHIA's "is it momentum or return-to-value?" split).

**Trapped Shorts** by trend state:
| regime | n | WR% | Exp |
|---|---|---|---|
| chop / non-trending | 31 | 45.2% | **+1.64** |
| trending | 27 | 22.2% | **−2.19** |

**Sell the Rip** by trend state + ADX cross-check:
| regime | n | WR% | Exp | | own ADX | n | Exp |
|---|---|---|---|---|---|---|---|
| chop / non-trending | 1,379 | 61.3% | **+1.12** | | <25 | 764 | +0.71 |
| trending | 269 | 35.7% | **−1.00** | | **25–30** | 422 | **+1.72** |
| | | | | | 30–35 | 312 | +0.05 |
| | | | | | 35+ | 150 | −0.05 |

Both print in chop / low-ADX and get run over in strong trends. Sell the Rip *peaks* at ADX 25–30
(+1.72) and dies above 35. **Confirms the chop-summer thesis with data.**

**Refines the validation doc:** "sell_the_rip works in URSA/bear regime" was a *correlate*. The driver
is **trend strength (ADX)**, not bias direction. A grinding-down market is low-ADX chop (its habitat);
the April blowup was a high-ADX violent whipsaw (its graveyard). Gate on ADX/auction, not bear-vs-bull.

**Operational gate:** deploy when ADX < ~30 / regime not trending / PYTHIA bracketing auction;
kill-switch when ADX rises / a trend ignites.

## Finding 2 — UW order flow was never wired into signal gating.

| signal record | count | meaning |
|---|---|---|
| STANDALONE confluence | 9,342 / 9,710 (96%) | fired with zero flow confirmation |
| CONFIRMED / CONVICTION | 361 / 7 | flow-confirmation tier barely existed, no edge |
| has GEX context | 9,513 (98%) | positioning context present (bias composite) |
| has options sweep | **1** | real options flow essentially absent |
| has dark-pool / whale | **0** | dark prints / whale trades never fed in |

Signals fire from TradingView (flow-blind Pine), enriched with GEX/positioning context only — real UW
order flow (sweeps, dark prints, whale trades, net flow) was absent from the gate. Confirms L1 as a
near-greenfield upgrade, not a tweak.

## L1 gate spec (implied by both findings)
A signal passes only if: **(a)** trend-strength condition met for its type (mean-reversion shorts:
ADX<~30 / bracketing auction; trend-continuation types: their appropriate ADX band), **(b)** UW order
flow confirms (net-flow / sweep direction aligns with the signal), **(c)** PYTHIA auction-acceptance at
the level. Shorthand: **"regime-appropriate + flow-confirmed + auction-accepted."**

## Caveats
Trapped Shorts n is small (58 resolved) — directionally strong, statistically thin. `regime.label` is
binary (trending / null); the continuous ADX cross-check corroborates the relationship. Read-only.
