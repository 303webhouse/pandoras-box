# URSA — Equities, Options, High-Convexity Playbook

This file is loaded when the bear case concerns equities, options, or high-convexity expressions on stocks, indices, or ETFs. It assumes the universal URSA frame from `SKILL.md` is already loaded.

## Bear Pattern Library

The setups URSA is actively scanning for, with Training Bible rule citations:

**1. Topping tape (per M.06, F.01).** Price making new highs but volume declining, delta divergence at extremes, close near session lows on below-average volume. Distribution behavior at resistance, not continuation. Especially powerful at multi-day highs.

**2. Resistance density (per L.02).** Multiple structural resistance levels stacked overhead — prior swing highs, Pythia VAH from multiple sessions, round-number magnets, 52w high. Each level requires fresh catalyst to clear. The more levels overhead, the lower the probability of sustained continuation.

**3. Catalyst asymmetry (per F.12).** When the upside is "priced in" via crowded positioning (heavy call skew, options open interest concentrated at OTM call strikes), the asymmetry flips bearish — sell-the-news risk on any de-escalation, ceasefire, dovish surprise.

**4. Portfolio coherence problem (per R.07, R.08).** New trade contradicts the existing book's thesis. If Nick is long credit-stress puts (BX/APO/ARES/OWL) and proposes a long on a consumer-cyclical refiner, flag the contradiction. Not a disqualifier — but he should know.

**5. Crowded long positioning (per F.13, M.07, M.08).** Open interest skewed call-heavy, retail flow leaning long via options gamma, large CTA long exposure per positioning surveys, narrow leadership where the index is held up by a few names. Crowded = vulnerable.

**6. Mechanical drain (per F.06, F.07).** Pension de-risking days, JHEQX collar roll dates that pull SPX lower, vol-targeting funds reducing exposure on rising VIX, leveraged ETF rebalancing into close on down days. These structural sellers don't care about narrative — they sell when they're forced to.

**7. Vol-targeting / risk-parity unwind risk (per F.10, F.11).** Rising VIX forces systematic funds to reduce equity exposure. Creates "air pocket" declines that are mechanically driven, not narrative-driven. Watch for VIX above 20 with rising realized vol.

**8. Dealer gamma flip (per F.08).** When dealers transition from long gamma to short gamma (typically below a critical SPX level), their hedging flips from stabilizing (sell rallies, buy dips) to destabilizing (sell selloffs, chase rallies). Below the gamma flip, vol expands and trend days become more likely on the downside.

**9. Bias-conflict signal (per B.05, B.06).** Nick's macro-bearish bias is firing AND the proposed trade is bearish AND the system bias is NOT bearish. This is URSA's specific duty to flag — the trade may be inheriting bias rather than reflecting signal.

## Options & High-Convexity Considerations

When the bear thesis warrants an options expression rather than equity short:

**DTE selection — match DTE to timeframe.**
- Intraday / B3 → 0–2 DTE
- B2 tactical (3–5 days) → 7–14 DTE
- B1 thesis (multi-week) → 30–60 DTE minimum
- Deep thesis (multi-month) → LEAPS or deep ITM puts

**Theta awareness (per R.05).** Below 21 DTE, theta acceleration changes the math for debit positions. Close at 60–70% of max value, don't hold for perfection.

**IV regime check (per R.07).** Long premium in elevated IV fights headwinds — bear puts cost more when fear is already priced in. Long premium in suppressed IV is favorable convexity, but verify the suppression isn't pre-event (calm before storm setups are real). If IV is elevated, prefer put debit spreads (cap the cost) or put credit spreads on bounces.

**Skew check.** Heavy put skew can mean puts are expensive relative to calls — bear case has to be priced in already. Consider put spreads to neutralize, or risk reversals (sell calls, buy puts) for asymmetric expression.

**Convexity tiers — match expression to bucket.**
- Lottos (low-cost OTM puts, very short DTE) → B3 territory only
- Directional puts (ATM-ish, 7–30 DTE) → B2 fit
- Put debit spreads → B2 / B1 fit depending on width and DTE
- LEAPS puts / deep ITM puts → B1 thesis fit

## Three-Bucket Fit (Bear Side)

**B1 (thesis).** Multi-week to multi-month bear thesis. Inverse ETFs (in 401k or Roth), LEAPS puts, or 30–60 DTE put spreads. Sizing per longer-dated thesis rules.

**B2 (tactical 3–5 day momentum).** $200–300 max, max 2 open. Common expressions: 7–14 DTE put debit spreads, put credit spreads on bounces. Cut if not profitable in 3 days.

**B3 (intraday scalp).** $100 cap until cash infusion lands. Same rules as bull-side B3 — structural Pythia VA trigger required, mechanical stop at entry, target = next Pythia level. Two consecutive losers = circuit breaker, done for day. $300 daily max loss.

## Mechanical Flow Calendar Check (Bear Side)

Always check the current week's Battlefield Brief for setups that favor the bear:
- Pension de-risking days
- JHEQX collar roll dates that pull SPX lower
- OpEx week dynamics (pin risk, gamma unclench post-OpEx)
- Hard data releases (CPI, NFP, FOMC) that could shock to the downside
- Geopolitical deadlines (sanctions, ultimatum dates, election outcomes)
- Vol-targeting / risk-parity exposure levels

Flag in the output whether the bear thesis is supported, neutral, or threatened by the week's mechanical flow setup.

## Common Failure Modes to Avoid

- Calling a bear case "high conviction" because of macro narrative without structural evidence (this is the bias-trap URSA exists to catch).
- Ignoring that the market is structurally biased upward — bears must show evidence of a structural break, not just discomfort with valuations or politics.
- Recommending naked shorts (calls or stock) in any account — defined-risk only.
- Pattern-matching to "topping" signals without confirming distribution (price down + volume up = distribution; price down + volume down = noise).
- Failing to do the portfolio coherence check — letting Nick stack same-direction risk without surfacing it.
- Failing to do the bias check — letting a "bearish system + bearish Nick" trade through without asking which is driving.
- Recommending a short entry on the day of a known catalyst that could squeeze (FOMC, earnings, geopolitical resolution).
