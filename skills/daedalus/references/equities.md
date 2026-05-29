# DAEDALUS — Equities Options Structure / Greeks / Sizing Playbook

This file is loaded when the structure-selection task concerns equities, ETFs, or crypto-adjacent equities (COIN, MSTR, MARA, IBIT). It assumes the universal DAEDALUS frame from `SKILL.md` is already loaded.

## Greeks Quick Reference

### Delta — directional exposure

Delta is the dollar change in option price per $1 change in the underlying (call delta 0 to +1; put delta 0 to -1).

| Position type | Delta range | What it means |
|---|---|---|
| Long call ATM | +0.50 | Each $1 up in underlying = +$50/contract (×100 multiplier) |
| Long call ITM | +0.70 to +0.95 | Closer to 1:1 with underlying; less convexity, less time premium |
| Long call OTM | +0.10 to +0.40 | More convex; more sensitive to IV; cheaper but lower probability |
| Long put ATM | -0.50 | Inverse; each $1 down in underlying = +$50/contract |
| Spread (debit) | net of long minus short | Capped delta exposure; lower cost, lower max gain |
| Iron condor | ~0 at inception | Delta-neutral when symmetric; profit from time decay if underlying stays in range |

**Portfolio delta** — sum across all open options positions (× 100 per contract). DAEDALUS tracks this implicitly when recommending new positions; surfaces "this adds X delta to a book currently at Y delta" when the new position materially shifts net directional exposure.

### Theta — time decay

Theta is the daily dollar decay of the position (negative for long premium; positive for short premium).

**Theta burn threshold:** if theta burn on a long-premium position exceeds 5% of position value per day, flag it explicitly. That's an unsustainable bleed rate — the position needs to work within days or it dies.

**Theta acceleration:** theta accelerates non-linearly as DTE approaches zero. Below 21 DTE, theta becomes the dominant Greek on long premium positions — this is why the 21 DTE rule (close at 60-70% of max) exists.

### Gamma — rate of delta change

Gamma is highest at-the-money and increases as DTE shrinks. High gamma near expiration means positions can move violently.

**Gamma risk window:** short options inside 7-10 DTE have unmanageable gamma. DAEDALUS advocates closing or rolling short-side positions before this window. Long options inside 7-10 DTE have favorable convexity but rapid theta decay — sharp directional moves can multiply value 5-10x intraday, but stagnation kills the position fast.

### Vega — IV sensitivity

Vega is the dollar change in option price per 1% change in IV (positive for long premium; negative for short premium).

**Vega awareness:** long premium positions GAIN value when IV rises (you're long volatility). Short premium positions LOSE value when IV rises. Always check IV regime before recommending a structure.

## IV Decision Matrix

The buy-vs-sell-premium framework drives structure selection:

| IV rank | Bias | Favored structures |
|---|---|---|
| **> 50th percentile** | Sell premium | Credit spreads (bull put, bear call), iron condors, covered calls |
| **30-50th percentile** | Context-dependent | Check skew and term structure; can do either |
| **< 30th percentile** | Buy premium | Debit spreads (bull call, bear put), long options, calendars, diagonals |

**The structural edge:** options are a bet on future realized volatility vs current implied. When IV >> historical realized vol, selling premium has statistical edge. When IV << realized vol, buying premium is cheap. Always frame the recommendation in these terms when IV is at an extreme.

**Inferring IV without rank data:** if hub doesn't expose IV rank, DAEDALUS reads VIX context + recent realized moves. VIX > 20 with rising realized vol = elevated IV regime. VIX < 14 with low realized vol = compressed IV regime. Single-name IV often moves with the index but spikes around earnings — always check the earnings calendar before committing to a long-premium structure.

## Structure Catalog

### Long Call

**Setup:** Bullish directional bet, long premium.
**Max loss:** premium paid.
**Max gain:** unlimited (underlying × delta minus premium).
**Greeks:** positive delta, negative theta, positive gamma, positive vega.
**When to use:** strong bullish directional input + low/compressed IV + DTE long enough to ride the move (30+ DTE for swing; 7-14 for tactical; 0-2 for B3 scalp).
**When to avoid:** elevated IV (premium expensive), unclear directional input, catalyst within DTE that's already priced in.

### Long Put

**Setup:** Bearish directional bet, long premium. Mirror of long call.
**Max loss:** premium paid.
**Max gain:** strike × multiplier (asymmetric; bounded by underlying going to zero).
**Greeks:** negative delta, negative theta, positive gamma, positive vega.
**When to use:** strong bearish directional input + low/compressed IV + DTE long enough to ride the move.
**When to avoid:** elevated IV, unclear bearish thesis, or when URSA flags the trade as bias-driven rather than evidence-driven.

### Bull Call Spread (Debit)

**Setup:** Buy lower-strike call, sell higher-strike call. Defined-risk bullish.
**Max loss:** net debit paid × multiplier × contracts.
**Max gain:** (width of spread − net debit) × multiplier × contracts.
**Greeks:** positive but capped delta, smaller negative theta than naked long, capped gamma/vega.
**When to use:** moderate bullish bias + IV elevated or neutral + want defined risk + targeting a specific level (sell short strike at PYTHAGORAS's resistance or PYTHIA's VAH).
**Sizing example formula:** max contracts = ⌊(account × 0.05) / (net debit × 100)⌋, capped at 3 per Robinhood rules.

### Bear Put Spread (Debit) — Nick's preferred bearish vehicle

**Setup:** Buy higher-strike put, sell lower-strike put. Defined-risk bearish.
**Max loss:** net debit paid × multiplier × contracts.
**Max gain:** (width of spread − net debit) × multiplier × contracts.
**Greeks:** negative but capped delta, smaller negative theta than naked long put.
**When to use:** moderate bearish bias + IV elevated (puts are expensive but the spread caps cost) + targeting a specific downside level (sell short strike at PYTHAGORAS's support or PYTHIA's VAL).

### Bull Put Spread (Credit)

**Setup:** Sell higher-strike put, buy lower-strike put. Defined-risk neutral-to-bullish.
**Max loss:** (width of spread − net credit) × multiplier × contracts.
**Max gain:** net credit received × multiplier × contracts.
**Greeks:** positive delta (small), positive theta (this is the point), negative vega.
**When to use:** neutral-to-bullish + IV elevated (collect premium) + short strike below structural support (PYTHIA's VAL or PYTHAGORAS's 20 SMA).
**Margin:** Robinhood requires collateral equal to max loss; sizing math factors this.

### Bear Call Spread (Credit)

**Setup:** Sell lower-strike call, buy higher-strike call. Defined-risk neutral-to-bearish. Mirror of bull put.
**When to use:** neutral-to-bearish + IV elevated + short strike above structural resistance.

### Iron Condor

**Setup:** Sell OTM put + buy further-OTM put (the put credit side) + sell OTM call + buy further-OTM call (the call credit side). Defined-risk delta-neutral.
**Max loss:** (width of wider wing − net credit) × multiplier × contracts.
**Max gain:** net credit received × multiplier × contracts.
**Greeks:** ~zero delta at inception, positive theta, negative vega.
**When to use:** PYTHIA says BRACKETING / balanced auction + PYTHAGORAS says RANGE day + IV elevated. Wings anchored at PYTHIA's VAH (short call wing) and VAL (short put wing), or PYTHAGORAS's structural resistance/support.
**When to avoid:** trending auction, expanding ATR, low IV (insufficient credit to justify the trade), catalyst within DTE.

### Risk Reversal (Synthetic Long or Short)

**Setup (bullish):** Sell OTM put + buy OTM call. Synthetic long stock with asymmetric expression.
**Max loss:** if assigned the put, unbounded below (essentially long the stock at the short put strike). Requires explicit Nick approval per R.05.
**When to use:** very strong bullish bias + heavy put skew (puts overpriced relative to calls) + willing to take assignment if it happens.

### Calendar / Diagonal

**Setup:** Sell shorter-DTE option, buy longer-DTE option at same (calendar) or different (diagonal) strike.
**Greeks:** complex — net positive theta (front decays faster), positive vega (long DTE more vega-sensitive).
**When to use:** advanced setups for specific IV term-structure plays or post-earnings vol crush plays. DAEDALUS recommends these only when IV term structure is explicit and Nick has an understanding of the mechanics.

## DTE Selection Framework

Match DTE to timeframe AND to catalyst calendar:

| Trade timeframe | DTE range | Notes |
|---|---|---|
| Intraday / B3 scalp | 0-2 DTE | Maximum gamma + theta both ways; only structural triggers per E.09 |
| B2 tactical (3-5 days) | 7-14 DTE | Standard swing window; cut if not profitable in 3 days |
| B1 thesis (multi-week) | 30-60 DTE minimum | Time for the thesis to play out without theta dominating |
| Deep thesis (multi-month) | LEAPS or deep ITM | Long-dated convexity for multi-month directional bets |

**Catalyst adjustments:**
- Earnings within DTE → AVOID long premium (IV crush risk); credit structures sized smaller (vol surprise risk)
- FOMC / CPI within DTE → elevated vol expected → favor structures that benefit (long vol on debit; short vol on credit only if conviction)
- OpEx week → check Battlefield Brief for pin risk; structures sensitive to specific strikes may behave abnormally

## Sizing Math (Placeholder Examples)

**Critical:** every number below uses PLACEHOLDER `$X` values. Real sizing math uses the live balance pulled from `hub_get_portfolio_balances()`. Never hardcode actual dollar amounts in output.

### Example A: Robinhood debit spread sizing

Given:
- Account balance: $X (pulled live)
- 5% max risk per trade rule
- Per-trade max risk: $X × 0.05
- Spread width: $5
- Net debit: $1.80
- Per-contract max loss: $1.80 × 100 = $180
- Max contracts within risk cap: ⌊($X × 0.05) / $180⌋
- Capped at 3 contracts per Robinhood rule

**Sizing output:** "Recommend X contracts, max loss $XXX (XX% of balance per live tool call)."

### Example B: Portfolio concentration check

Given:
- Sum of max losses across all open positions: $X
- Account balance: $Y (pulled live)
- Concentration ratio: $X / $Y
- New position max loss: $Z

**Check:** ($X + $Z) / $Y ≤ 20% per hard rule.

**Output:** "Adding this position brings total portfolio risk to XX% of balance. Within 20% cap." OR "Adding this position would bring total portfolio risk to XX% — exceeds 20% cap. Recommend reducing size to N contracts or closing an existing position first."

## Worked Committee Outputs (Anonymized)

### Example 1: SPY bear put spread — bear thesis input

```
TIMEFRAME: 3–5 day tactical
ASSET: SPY @ 587.00
DIRECTIONAL INPUT: URSA bear case — distribution at the highs, M.04 stop-run setup at 587.20. Invalidation: reclaim above 587.40 with volume.

PROPOSED STRUCTURE: Bear put spread (debit)
STRIKES: +585P / -580P (5-wide)
EXPIRATION: 7 DTE (matches B2 tactical horizon)
ESTIMATED GREEKS: Delta -0.35 per contract (capped by spread), Theta -$3/contract/day, Vega -$8/contract per 1% IV. Requires chain snapshot for precision.
IV CONTEXT: Inferred neutral-to-elevated — VIX at 17, recent realized vol modestly above implied. Debit structure acceptable.

RISK PARAMETERS:
- Max loss: net debit × contracts × 100. At debit $1.80 × 2 contracts × 100 = $360 (assumes balance supports 2 contracts within 5% cap; verify via live balance call)
- Position size: 2 contracts (within three-bucket B2 cap of $200-300 if debit $1.80 × 2 = $360 — slightly over; recommend 1 contract to stay strict, or downgrade B2 to its $300 ceiling)
- Entry: $1.80 debit (limit)
- Stop: underlying reclaim above 587.40 (URSA's invalidation) → close the spread, accept partial loss
- Target: T1 underlying $583.80 (PYTHIA's VAL — partial close at 50% of max gain), T2 underlying $580.00 (full close at max gain)
- Time stop: 4 DTE OR 3 trading days unfavorable (matches B2 cut rule)

CATALYST AWARENESS: No major macro catalyst within DTE (CPI was 2 days ago; next FOMC outside window). No earnings risk on SPY directly.
LIQUIDITY: SPY options are mega-cap-tier liquid — bid-ask typically <2% of option price. No flag.
CONVICTION: MODERATE — URSA's bear case is clean and PYTHIA's 80% rule supports the downside path, but IV regime is neutral (not strongly favorable for debit) and the position pushes against the structural upward bias TORO would flag. PIVOT to synthesize.
```

### Example 2: NVDA bull call spread — TORO breakout thesis

```
TIMEFRAME: 3–5 day tactical
ASSET: NVDA @ 148.50
DIRECTIONAL INPUT: TORO breakout above 148.20 (prior swing high), PYTHAGORAS confirms volume-confirmed breakout, PYTHIA flags 148.20 poor high being repaired.

PROPOSED STRUCTURE: Bull call spread (debit)
STRIKES: +150C / -155C (5-wide)
EXPIRATION: 14 DTE (matches B2 with room to ride)
ESTIMATED GREEKS: Delta +0.30 per contract (capped), Theta -$4/day, Vega +$10. Chain snapshot recommended.
IV CONTEXT: NVDA IV elevated post-recent moves but below earnings spike levels. Debit structure acceptable but spread caps the IV cost.

RISK PARAMETERS:
- Max loss: net debit × contracts × 100. At debit $2.20 × 2 contracts × 100 = $440 (verify supports 5% cap on live balance)
- Position size: 2 contracts (B2 fit; need balance > $8,800 to fit within 5% cap)
- Entry: $2.20 debit (limit)
- Stop: underlying close back below 148.20 (PYTHAGORAS's invalidation) → close the spread
- Target: T1 underlying $152.80 (PYTHAGORAS's next resistance, 50% close), T2 underlying $155.00 (max gain at short strike)
- Time stop: 7 DTE OR 3 trading days unfavorable

CATALYST AWARENESS: NVDA earnings >30 days out — no catalyst risk inside DTE window. Sector context (THALES when built) would refine the read.
LIQUIDITY: NVDA options highly liquid — bid-ask typically 1-2% of option price. No flag.
CONVICTION: HIGH — TORO + PYTHAGORAS + PYTHIA all align (rare three-way agreement); IV manageable via spread; clear structural invalidation; within risk caps.
```

### Example 3: SPY iron condor — range thesis

```
TIMEFRAME: 3–5 day tactical
ASSET: SPY @ 586.20
DIRECTIONAL INPUT: PYTHIA bracketing auction (composite VA stable 584-588 for 5 sessions), PYTHAGORAS range day classification. No strong directional input from TORO or URSA — range-favorable.

PROPOSED STRUCTURE: Iron condor
STRIKES: -590C / +593C / -582P / +579P (3-wide wings)
EXPIRATION: 10 DTE
ESTIMATED GREEKS: Delta ~0 at inception, Theta +$5/day (positive — collecting decay), Vega -$8 (short vol).
IV CONTEXT: VIX at 16, IV neutral. Iron condor needs IV elevated enough to justify the trade — verify chain shows credit > 33% of width (rule of thumb).

RISK PARAMETERS:
- Max loss: (3 wing width − net credit) × 100 per contract per side. At net credit $1.10 × 2 contracts × 100 = $220 credit collected; max loss per side = ($3 − $1.10) × 100 × 2 = $380
- Position size: 2 contracts (B2 fit; max loss $380 must clear 5% live balance check)
- Entry: $1.10 net credit (limit; if fill <$1.00, the trade math fails — pass)
- Stop: underlying close above 590 or below 582 → close the breached side and reassess
- Target: T1 50% of max profit = close for $0.55 debit, T2 close at 21 DTE per shared rule
- Time stop: standard — close at 21 DTE regardless of profit per shared rule

CATALYST AWARENESS: No major catalyst within 10 days. SPY direct catalyst risk minimal (no earnings); macro CPI/FOMC outside window per current calendar.
LIQUIDITY: SPY options highly liquid. No flag.
CONVICTION: MODERATE — clean range setup but IV is borderline for the credit. Trade math works if entered at $1.10+ credit; passes below that. PIVOT to confirm range thesis with PYTHIA before committing.
```

### Example 4: IBIT bear put spread — bias-aware thesis

```
TIMEFRAME: 3–5 day tactical
ASSET: IBIT @ 52.40
DIRECTIONAL INPUT: URSA bear case + bias challenge note — Nick's macro-bearish bias aligns with thesis; URSA flags as bias-aware MODERATE conviction (the chart supports the trade, but Nick's bias is also pushing him toward it).

PROPOSED STRUCTURE: Bear put spread (debit)
STRIKES: +52P / -49P (3-wide)
EXPIRATION: 10 DTE
ESTIMATED GREEKS: Delta -0.30 per contract (capped), Theta -$2/day, Vega -$5. Chain snapshot recommended.
IV CONTEXT: IBIT IV elevated (BTC-tracking ETFs run high IV). Debit structure caps the cost; spread compresses the IV impact.

RISK PARAMETERS:
- Max loss: net debit × contracts × 100. At debit $0.80 × 3 contracts × 100 = $240 (B2 fit; verify 5% cap live)
- Position size: 3 contracts (Robinhood max; B2 cap respected)
- Entry: $0.80 debit (limit)
- Stop: underlying close back above 52.50 (URSA's invalidation) → close
- Target: T1 underlying $50.20, T2 underlying $49.00 (max gain at short strike)
- Time stop: 5 DTE OR 3 trading days unfavorable

CATALYST AWARENESS: No specific IBIT catalyst within DTE. Crypto-correlated — watch BTC for catalyst events (ETF flow data, major BTC price moves).
LIQUIDITY: IBIT options moderately liquid — bid-ask typically 3-5% of option price. Acceptable, no flag.
CONVICTION: MODERATE — clean structure but URSA flagged the bias-conflict signal. If TORO has nothing strong on the bullish side, this can pass; if there's any bullish counter-evidence, downgrade to LOW or pass.
```

### Example 5: Direct-mode position management

```
SCENARIO: Nick asks DAEDALUS to evaluate an existing SPY 580/575 bear put spread currently at 18 DTE, originally entered at $1.50 debit, currently worth $2.40.

DAEDALUS read:
- Current value $2.40 vs entry $1.50 = 60% of max value reached.
- Per 21 DTE shared rule: close at 60-70% of max value below 21 DTE — we're AT the threshold.
- Greeks check: theta now eating into the position (~$3/day going forward), gamma still manageable but accelerating in 2-3 days.
- Recommendation: CLOSE NOW or set GTC at $2.55 (70% of max). Don't hold for $3.00 expiry max — the math says lock the win.

If Nick wants to hold: surface that the additional 16% upside (from $2.40 to $3.00 max) requires the spread holding for 18 more days; theta will accelerate; and the trade has already accomplished 60% of its intended math. The risk/reward of holding ($0.60 potential gain vs $2.40 at risk) is unfavorable. The math doesn't work on holding this one.
```

## Bid-Ask Liquidity Benchmarks

| Underlying type | Typical bid-ask % of option price | Threshold for liquidity flag |
|---|---|---|
| Mega-cap (SPY, QQQ, AAPL, MSFT, NVDA) | 1-2% | > 5% |
| Large-cap (most S&P 500) | 2-4% | > 7% |
| Mid-cap | 4-7% | > 10% |
| Small-cap | 7-12% | > 15% (often disqualifying) |
| Crypto-adjacent ETFs (IBIT, ETHE, COIN) | 3-5% | > 10% |
| Inverse ETFs (SQQQ, SH) | 5-8% | > 12% |

**Hard rule:** if bid-ask spread > 10% of option price for any structure, flag in the output. For ATM structures on mid-cap and below, this often disqualifies the trade entirely — the slippage on entry + exit eats too much edge.

## Common Failure Modes (Equities Options-Specific)

- Recommending long premium when IV rank is elevated and a credit structure has better edge.
- Failing to check the catalyst calendar within DTE window before recommending long premium (IV crush eats positions).
- Hardcoding a position size or max loss number instead of pulling live balance via `hub_get_portfolio_balances()`.
- Overriding TORO/URSA directional input with DAEDALUS's own directional view (out of lane).
- Recommending iron condors in trending auctions per PYTHIA's read (condor is a range structure).
- Not flagging bid-ask spread as a liquidity concern on mid-cap and below.
- Missing the 21 DTE management call — holding positions past the close-at-60-70% threshold and watching the win evaporate.
- Recommending naked structures without explicit Nick approval flag (violates R.05).
