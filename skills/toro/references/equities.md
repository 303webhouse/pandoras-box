# TORO — Equities, Options, High-Convexity Playbook

This file is loaded when the bull case concerns equities, options, or high-convexity expressions on stocks, indices, or ETFs. It assumes the universal TORO frame from `SKILL.md` is already loaded.

## Bull Pattern Library

The setups TORO is actively scanning for, with Training Bible rule citations:

**1. Squeeze setup (per M.09, F.02).** Hydra score elevated; gamma flip level sitting below current price (so dealer hedging accelerates upside per F.08); ATM IV not stretched. Best B2 fit. Cross-reference with `/api/hydra/scores`.

**2. Breakout with flow confirmation (per F.01, M.11).** Price clearing a structural level (Pythia VAH, prior session high, prior swing high) AND `/api/flow/radar` shows confirming call buying or call spread imprint within the prior session. Without the flow confirm, this is a B3 candidate at best, never a B1/B2 thesis.

**3. Sector RS leader inside a leading sector (per C.01, C.02).** Ticker ranks top-quintile relative strength within a sector that itself is leading per `/api/watchlist/sector-strength`. Cross-reference with THALES output if available. Best B1/B2 fit.

**4. Mechanical flow tailwind (per F.06, F.07).** Pension rebalancing into month-end or quarter-end with current allocations skewed away from equities; JHEQX collar roll positioning that pulls SPX higher; OpEx pin sitting above current price with dealer gamma supporting the pin (F.08). Strong tactical (B2) tailwinds; never the sole reason to enter, but a meaningful conviction amplifier.

**5. Catalyst-driven (per F.12).** Active Hermes alert (earnings, FDA, M&A, macro print) with confirming flow positioning. The catalyst is the trigger; the flow is the conviction check. No flow confirm = pass.

**6. Oversold mean reversion (per M.06).** McClellan extreme (oscillator deeply negative); VIX spike with reversion underway; flow imprint quietly turning constructive (puts being sold, calls being bought). Tactical B2 setup; tight stops; do not size up on these.

**7. Stop-run reclaim (per M.04, F.03).** Price sweeps a key level (prior low, round number) and reclaims back above. The trapped breakout-failure shorts provide fuel. Wait for the reclaim to complete before entry — do not anticipate.

**8. Golden Trade (per C.03).** Price pulls back to the 120 SMA in a confirmed uptrend (SMA stack bullish, 120 SMA rising). Highest-conviction dip-buy in the CTA framework. Best B1 fit.

## Options & High-Convexity Considerations

When the bull thesis warrants an options expression rather than equity:

**DTE selection — match DTE to timeframe.**
- Intraday / B3 → 0–2 DTE
- B2 tactical (3–5 days) → 7–14 DTE
- B1 thesis (multi-week) → 30–60 DTE minimum
- Deep thesis (multi-month) → LEAPS or deep ITM

**Theta awareness.** Below 21 DTE, theta acceleration changes the math. Hard rule from the user's framework: close at 60–70% of max value, don't hold for perfection.

**IV regime.** Check the `iv_regime v2` reading. Long premium in elevated IV fights headwinds; consider spreads or risk reversals to neutralize the IV layer. Long premium in suppressed IV is favorable convexity — but verify IV isn't compressed for a reason (low-volume holiday, pre-event suppression, etc.).

**Skew check.** Heavy put skew can mean calls are cheap relative to puts — flag when the convexity math is unusually favorable. Same logic in reverse for crowded call skew (avoid chasing into already-priced upside).

**Convexity tiers — match expression to bucket.**
- Lottos (low-cost OTM, very short DTE) → B3 territory only
- Directional calls (ATM-ish, 7–30 DTE) → B2 fit
- LEAPS / deep ITM → B1 thesis fit

## Three-Bucket Fit

**B1 (thesis).** Multi-week to multi-month bull thesis. Equity, LEAPS, or 30–60 DTE calls/spreads. Sizing per longer-dated thesis rules.

**B2 (tactical 3–5 day momentum).** $200–300 max, max 2 open. Common expressions: 7–14 DTE calls or call debit spreads. Cut if not profitable in 3 days.

**B3 (intraday scalp).** $100 cap until cash infusion lands, max 2 concurrent, max 3/day, same-day close. Requires structural Pythia VA trigger (break or rejection). Mechanical stop at entry. Target = next Pythia level. Two consecutive losers = circuit breaker, done for the day. $300 daily max loss.

## Mechanical Flow Calendar Check

Always check the current week's Battlefield Brief for:
- Pension rebalance windows
- JPM JHEQX collar roll dates
- OpEx week dynamics (pin risk, gamma unclench)
- Hard data releases (CPI, NFP, FOMC) with prior prints and narrative-change thresholds
- Geopolitical deadlines

Flag in the output whether the bull thesis is supported, neutral, or threatened by the week's mechanical flow setup. The user has been caught on the wrong side of pension rebalances and JHEQX rolls before — surface these proactively rather than waiting to be asked.

## Common Failure Modes to Avoid

- Pattern-matching to a setup template without confirming the flow imprint.
- Calling a bull case "high conviction" when the bias composite is mixed or neutral.
- Ignoring overhead structural resistance (Pythia VAH from prior session, prior swing highs, round-number magnets).
- Recommending B3 entries without a Pythia VA-based structural trigger.
- Sizing into options expirations without DTE/theta math.
- Conflating "stock has moved a lot" with "stock will keep moving" — late-cycle parabolics are where the user has historically entered too early on the short side, but the inverse failure (chasing parabolic longs) is the bull-case version. Don't.
- Recommending a long entry the day before a known mechanical drain (e.g., a known pension de-risking day) without flagging the headwind.
