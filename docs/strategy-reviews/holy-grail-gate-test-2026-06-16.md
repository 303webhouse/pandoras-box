# Holy Grail — ADX Gate-Test (rebuild §8.1 re-analysis)

**Date:** 2026-06-16 · **Bucket:** investigation · READ-ONLY (no writes)
**Parent:** rebuild brief §8.1; validation doc `signal-edge-validation-2026-06-16.md`
**Data:** `signals` where `strategy='Holy_Grail'` and `outcome in ('WIN','LOSS')` → **4,324 resolved**.
P&L unit = `outcome_pnl_pct`; expectancy = mean over WIN+LOSS pool.

## Hypothesis (from the rebuild seed)
Holy Grail (Raschke trend-continuation: ADX>30 + pullback to the 20-EMA) bled because it fired
*outside* its ADX>30 precondition (in chop). Gate to ADX>30 × liquid × in-trend and a profitable
subset should emerge. Keep if so; kill only if still negative when properly gated.

## Result: hypothesis FALSIFIED. Verdict = KILL.

| Gate | n | WR% | Expectancy | Total |
|---|---|---|---|---|
| Baseline (all resolved) | 4,324 | 21.8% | −1.13 | −4,867 |
| ADX 25–30 | 1,917 | 19.8% | −0.96 | −1,847 |
| ADX 30–35 | 1,041 | 22.4% | −1.14 | −1,187 |
| ADX 35–40 | 699 | 24.9% | −1.06 | −739 |
| ADX 40+ | 667 | 23.5% | **−1.64** | −1,095 |
| ADX>30 (precondition) | 2,392 | 23.5% | −1.26 | −3,004 |
| ADX>30 × liquid | 369 | 27.6% | −0.35 | −130 |
| ADX>30 × liquid × 1H | 368 | 27.7% | −0.35 | −129 |
| in-trend (bias ALIGNED, all tickers) | 333 | 34.2% | −1.00 | −332 |

## Findings
1. **ADX gating does not rescue it — it slightly hurts.** Expectancy worsens from −1.13 (all) to
   −1.26 (ADX>30). The strongest-trend bucket (ADX 40+) is the *worst* (−1.64): over-extended trends
   turn pullback-continuation entries into reversals.
2. **It never fired in true chop.** Min ADX in the dataset = 25.0. The "fired outside precondition"
   premise is largely false — it fired near threshold, and the threshold does not sort edge.
3. **1H-only.** 4,323 of 4,324 signals are 60-min; exactly one 15m signal. The 1H-vs-15m split is moot.
4. **Every gated subset is negative.** Best win-rate cut (in-trend ALIGNED, 34.2%) still loses
   ~1%/signal. No gate reaches positive expectancy.
5. **Liquid universe is the only real lever — and it only *contains* the bleed.** ADX>30 × liquid cuts
   expectancy from −1.42 (single-name) to −0.35. Less-bad, still bleeding. A few single liquid tickers
   print positive (TLT +0.13, XLF +0.61, XLK +0.35) at n=10–22 — noise, not a deployable subset.

## Implication for L0
Confirms the validation doc's **NONE (suppress)** verdict, now stress-tested against the specific
rescue hypothesis. L0 action: **suppress `Holy_Grail` outright.** Do NOT attempt an ADX-gated revival
(dead) and do NOT carve out the liquid slice (still negative). The liquid-vs-single-name gap
(−0.35 vs −1.42) is additional support for the broader L0 thesis: damage concentrates in the
single-name long tail.

## Method note
"Liquid universe" = index/sector ETFs + mega-cap tech (SPY/QQQ/IWM/HYG/TLT/FXI/SMH/XLK… +
NVDA/MSFT/AAPL/… ~50 tickers). "In-trend" proxied by `bias_alignment='ALIGNED'` (signal direction
aligned with bias regime at fire time); `signals.bias_level` is 100% NULL so per-signal
`bias_alignment` was used. ADX from the populated `signals.adx` column. Read-only; no prod writes.
