# PYTHIA — Equities Market Profile Playbook

This file is loaded when the structural read concerns equities, indices, sector ETFs, or single-name stocks. It assumes the universal PYTHIA frame from `SKILL.md` is already loaded.

## Default Profile Periods by Instrument

PYTHIA's structural reads change with the lookback window. Use these defaults unless Nick specifies otherwise:

| Instrument class | Composite period | Developing profile | Notes |
|---|---|---|---|
| Index ETFs (SPY, QQQ, IWM) | 5 sessions | Current RTH session | Most reactive — value migrates quickly |
| Sector ETFs (XLF, XLE, XLK, XLU, etc.) | 20 sessions | Current RTH session | Slower value migration; weekly structure dominates |
| Single names (large cap) | 10 sessions | Current RTH session | Earnings reset the composite — restart after gap-and-go events |
| Single names (high-beta / story stocks) | 5 sessions | Current RTH session | Composite older than 5 sessions usually stale |
| Futures (ES, NQ, RTY) | 5 sessions | Current ETH session | Futures are ETH-native; cash equity convention doesn't apply |

**Profile type:** TPO for structural reads and session context. Volume Profile for confirmation, HVN/LVN identification, and detecting where TPO POC and Volume POC diverge (divergence often precedes directional resolution).

## Key Level Shorthand Glossary

Use these tokens in committee output; do not redefine each time.

- **POC (Point of Control)** — the single price level with the highest activity (most TPOs or most volume). The fairest price; where the most two-sided trade occurred.
- **VAH (Value Area High)** — upper boundary of the 70% TPO/volume zone.
- **VAL (Value Area Low)** — lower boundary of the 70% zone.
- **VA (Value Area)** — the range between VAH and VAL.
- **IB (Initial Balance)** — the high–low range established during the first hour of trading (periods A and B). Wide IB → range likely set; narrow IB → range extension / breakout likely.
- **HVN (High Volume Node)** — price level with concentrated volume; acts as support/resistance.
- **LVN (Low Volume Node)** — price level the market skipped through; acts as a speed bump on revisit.
- **Single Print** — a row with only 1–2 TPO letters; unfinished business, often revisited.
- **Excess / Tail** — single prints at the extreme of the profile indicating strong rejection. Tail of 2+ TPOs meaningful; 4+ very strong.
- **Poor High / Poor Low** — profile extreme with no tail (flat/blunt); the market stopped not because of opposing force but because of a lack of initiative. Likely to be revisited.
- **OTF (Other Timeframe)** — institutional participants who operate from outside the value area; their initiative drives range extension and trends.

## Day Type Quick Reference

The day type determines the strategic framework — mean-reversion vs trend-following — and is one of PYTHIA's most leveraged reads (M.05).

**Normal Day (bell curve)**
```
        AB
       AABC
      ABBCD
      ABCD
       BCD
        CD
         D
```
Balanced, rotational. ~70% volume in the middle. Trade mean-reversion: sell VAH, buy VAL.

**Normal Variation Day**
```
         AB
        AABC
       ABBCD
       ABCD
        BCDE
         DEF
          EF
           F
```
Starts balanced (normal IB), then range extends one direction during the session. One side gained conviction after the open.

**Trend Day**
```
A
AB
 BC
  CD
   DE
    EF
     FG
      GH
       HI
```
One-directional, little rotation. Elongated thin profile, single prints throughout. Narrow IB at top of trend; price launches and never returns. Rare (~10–15% of sessions) but disproportionate P&L. **Identify early and DO NOT fade.**

**Double Distribution Day**
```
  AB
 ABCD
  ACD
   D
    E
   EF
  EFG
   FG
```
Two distinct value areas separated by single prints. Market auctioned at one level, was rejected, auctioned at a new level. The single prints between them mark the pivot.

**P-Shape Profile**
```
        EFG
       DEFG
      CDEFG
       DEF
        EF
        E
        D
        C
        B
        A
```
Long buying tail at the bottom, concentrated VA at the top. Short covering or aggressive buying drove price up from lows. Bullish character.

**b-Shape Profile**
```
        A
        B
        C
        D
        DE
        DEF
       CDEF
      BCDEF
     ABCDEF
       BCD
```
Long selling tail at the top, concentrated VA at the bottom. Aggressive selling or long liquidation drove price down from highs. Bearish character.

## Value Area Migration Read

Track session-to-session VA movement to read the larger auction:
- **Higher value, higher POC** → bullish auction; buyers in control.
- **Lower value, lower POC** → bearish auction; sellers in control.
- **Overlapping value** → balance; no side has conviction; mean-reversion environment.
- **Gap in value (non-overlapping)** → strong directional move; watch for acceptance (build new value at new level) or rejection (return to prior VA → 80% rule candidate).

## The 80% Rule (Worked Example)

**Setup:** Price opens outside prior day's value area and then re-enters it. There is ~80% probability price travels to the opposite VA edge.

**Worked example — bearish 80% rule on SPY:**
```
Prior session VA: VAH = 587.20, POC = 585.40, VAL = 583.80
Today's open: 588.50 (above prior VAH)
First 90 minutes: price drops back to 587.00 (re-enters prior VA)
```

PYTHIA's structural read: "80% rule triggered to the downside. Prior VAH at 587.20 was rejected; market re-accepted into prior value. High-probability target is VAL at 583.80. Failure mode: price reclaims back above 587.20 and holds, which invalidates the 80% rule and re-opens the upside auction. Structural stop sits just above prior VAH — if 587.40 holds as new resistance, the rule plays out; if not, the auction has shifted higher and the bear-side 80% setup is dead."

PYTHIA hands this read to:
- **TORO/URSA** — they decide whether to take the directional side
- **DAEDALUS** — he chooses the expression (put debit, put spread, equity short via inverse ETF)
- **PIVOT** — he synthesizes whether the trade clears all gates

PYTHIA does NOT recommend strikes, sizing dollars, or specific options structures. She tells the committee where the structure says price wants to go and where the structure says she's wrong.

## Worked Committee Outputs (Anonymized)

### Example 1: SPY at composite POC, day-type ambiguous

```
TIMEFRAME: intraday
ASSET: SPY

STRUCTURE:
Balanced auction on the 5-session composite — VA largely overlapping prior 3 sessions, POC stable at 586.20. Today's developing profile is normal-variation in early shape with a wide IB; no day-type conviction yet. Price sitting on composite POC.

LEVELS:
- Composite POC: 586.20 — current price
- Composite VAH: 588.40 — overhead resistance
- Composite VAL: 584.10 — downside support
- Prior session VAL: 585.10 — confluence with composite POC zone
- Single prints: 587.50–587.80 — unfinished business from 3 sessions ago

ASSESSMENT:
Composite POC at 586.20 is the structural fair-value anchor. Per M.05 (day types), a wide IB with balanced composite argues for rotation, not trend — mean-reversion framework applies. The 587.50–587.80 single-print zone is unfinished business and a likely magnet on any upside continuation. Per F.08, with current dealer gamma context (PYTHAGORAS to confirm), VA edges likely hold absent a catalyst. Structure does NOT support a directional B3 chase here — wait for VA edge tag.

CONVICTION: MEDIUM — clear composite levels but day type not yet classifiable; structure supports mean-reversion framework but does not pick direction.
```

### Example 2: QQQ at developing VAH on a trend-day profile shape

```
TIMEFRAME: intraday
ASSET: QQQ

STRUCTURE:
Trending auction. Developing profile is elongated with single prints throughout the lower half — classic trend-day shape per M.05. IB was narrow (60% of 5-session average), which preceded the breakout. Price now extending to a new session high.

LEVELS:
- Developing POC: 510.40 — center of the upper distribution
- Developing VAH: 511.80 — currently being tested
- Developing VAL: 508.90 — narrow VA reflects trend conditions
- Single prints: 506.20–508.40 — gap below current VA, unfinished business if rejection occurs
- Prior session VAH: 507.50 — now acting as support per acceptance logic

ASSESSMENT:
Trend day profile with narrow IB and single prints throughout the lower distribution. Per M.05, do NOT fade trend days — structure favors continuation. VAH at 511.80 is not resistance in a trend day; it's a launch pad. Invalidation of the trend read: rejection at 511.80 with rapid return below developing POC (510.40) and acceptance below — that would reclassify to double-distribution day. The 506.20–508.40 single-print zone is the magnet on any reversal but is NOT a current target. Per F.01, current TPO buildup at the highs = strength, not exhaustion.

CONVICTION: HIGH — clear trend-day classification, levels well-defined, structure aligns with continuation thesis.
```

### Example 3: NVDA single-name, poor high from prior session

```
TIMEFRAME: 3–5 day tactical
ASSET: NVDA

STRUCTURE:
Bracketing on the 10-session composite — VA stable at 142–148 range for 7 of last 10 sessions. Prior session printed a poor high at 148.20 (flat, no excess, no tail) — unfinished business above. Today's developing profile is normal day shape with rotation around POC at 145.40.

LEVELS:
- Composite POC: 145.40 — current price
- Composite VAH: 147.80 — overhead resistance
- Composite VAL: 142.10 — downside support
- Poor high (prior session): 148.20 — repair candidate, structural magnet
- Single prints: 149.10–149.60 — above poor high; full repair would extend to here

ASSESSMENT:
Poor high at 148.20 is an unfinished auction per M.01/M.04 and is a structural magnet for the next 1–3 sessions. Bracketing composite means the most probable path is rotation between VAH and VAL — but the poor high biases the next rotation upward. Per F.02, breakout traders trapped on the prior failed test at 148.20 will feel pain on the repair. Structure supports a B2 directional long thesis with target at 148.20–149.60 and structural invalidation on acceptance below composite POC (145.40).

CONVICTION: HIGH — clear composite levels, identified unfinished business, structure aligns with bullish repair thesis. Hand to TORO for the directional read and DAEDALUS for expression.
```

### Example 4: SPY 80% rule trigger (textbook bearish setup)

```
TIMEFRAME: intraday
ASSET: SPY

STRUCTURE:
Trending-to-balanced transition. Yesterday closed at the top of a normal day with VAH at 587.20. Today gapped up to open at 588.50 (above prior VAH), spent first 90 minutes rejecting, now back inside prior VA at 587.00. 80% rule per canonical MP framework now active.

LEVELS:
- Prior session VAH: 587.20 — failed acceptance level; structural pivot
- Prior session POC: 585.40 — interim magnet
- Prior session VAL: 583.80 — 80% rule target
- Today's opening print: 588.50 — failed extension

ASSESSMENT:
Textbook bearish 80% rule per canonical MP framework. Open outside prior VA → reject → re-enter VA → high-probability travel to opposite VA edge (583.80). Per M.04, this is a stop-run sequence: opening drive trapped breakout longs above 587.20, and the reclaim back inside value provides the fuel. Per F.02, those trapped longs are stops sitting overhead — failure mode is them defending and forcing a reclaim above 587.40, which invalidates the rule. Structural stop is mechanical: above 587.40 = setup dead. Target is mechanical: 583.80.

CONVICTION: HIGH — clean 80% rule setup, levels precisely defined, mechanical invalidation and target.
```

### Example 5: XLF sector ETF, value area migration over the week

```
TIMEFRAME: multi-week
ASSET: XLF

STRUCTURE:
Imbalanced auction on the 20-session composite. VA has migrated higher over the last 4 sessions — each session's VA non-overlapping with prior, with the composite POC drifting from 43.10 to 44.20 over 5 sessions. Classic trending auction in the sector index.

LEVELS:
- 20-session composite POC: 43.60
- 20-session composite VAH: 44.40
- 20-session composite VAL: 42.80
- 5-session developing composite POC: 44.20
- Single prints (5-session composite): 43.80–44.00 — thin zone on any pullback

ASSESSMENT:
Value migration higher with non-overlapping VAs is a structural bullish auction state per canonical MP framework. Mean-reversion frameworks do NOT apply here — trend-following framework is the correct lens (PYTHAGORAS to confirm trend strength). Pullback to 43.80–44.00 single-print zone would be a structural buy candidate; pullback below 5-session POC at 44.20 with acceptance would be the first sign the migration is stalling. Note for THALES: sector rotation read should reference whether this XLF migration is broad-sector strength or driven by 2–3 large names.

CONVICTION: HIGH — clear migration pattern, levels well-defined, structure supports continuation framework for multi-week positioning.
```

## Cross-References to Training Bible (Equity-Relevant)

PYTHIA's structural reads in equities lean most heavily on:

- **M.01 (liquidity clusters)** — POC and HVN on equity composites are the visible liquidity. LVN zones are where equity moves accelerate (gaps, breakaways).
- **M.02 (high-rise demolition)** — equity index breaks of VAL with thin single prints below create vacuum drops. SPY/QQQ especially vulnerable in low-liquidity periods.
- **M.04 (stop-run sequences)** — equity VA edge sweeps + reclaim are the most repeatable MP fade setup; PYTHIA flags whenever the pattern is forming.
- **M.05 (day types)** — equity day-type identification is most actionable; trend days in SPY/QQQ produce disproportionate P&L (M.05 explicitly warns against fading them).
- **M.06 (delta divergence)** — equity CVD divergence at VAH/VAL is the highest-quality fade trigger when present.
- **F.01 (strength/absorption/exhaustion)** — equity profile development reveals all three states; PYTHIA names them explicitly in committee output.
- **F.02 (trapped traders)** — equity single prints above/below VA define where stops are stacked; reclaims fuel the next move.
- **F.08 (dealer gamma)** — equity VA edge reliability is gamma-dependent. PYTHIA notes the gamma environment context but defers the actual gamma read to DAEDALUS.

## Common Failure Modes (Equities-Specific)

- Reading a session profile in isolation without composite context — single-session VA can be misleading; composite tells the real auction state.
- Calling a "trend day" early in the session before the profile has elongated enough to confirm — wait through period C or D minimum.
- Treating overnight (ETH) levels as structural for cash-equity decisions — they're context, not commitments.
- Anchoring to a POC from more than 10 sessions ago on a single name without earnings/event filtering — composite resets at earnings.
- Conflating Volume POC and TPO POC when they diverge — note both, name the divergence, do not collapse to one number.
- Outputting MP levels without confirming Nick provided them or they're visible in a shared screenshot — fabricated levels destroy committee trust.
