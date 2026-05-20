# PYTHAGORAS — Equities Trend / Structure / Indicators Playbook

This file is loaded when the chart-reading task concerns equities, indices, sector ETFs, or single-name stocks. It assumes the universal PYTHAGORAS frame from `SKILL.md` is already loaded.

## Indicator Quick Reference

### Moving Averages (Layer 1 trend definition)

**EMA Stack (9/20/55) — short-term trend, intraday + swing**
- Bullish stack: EMA 9 > EMA 20 > EMA 55, all sloping up
- Bearish stack: EMA 9 < EMA 20 < EMA 55, all sloping down
- Compressed: EMAs within ~0.5% of each other → transition / range condition; do not trade trend setups here

**SMA Stack (50/120/200) — CTA zone system, multi-week trend**
- Bullish: SMA 50 > SMA 120 > SMA 200, all rising
- Bearish: SMA 50 < SMA 120 < SMA 200, all falling
- Transitioning: SMA 50 crossing through SMA 120 or 200 — high-volatility, no clean trend setup
- Golden Touch: pullback to rising SMA 120 in a bullish stack = highest-conviction dip-buy in PYTHAGORAS's framework (per S.02)

### Rolling VWAPs (multi-timeframe value)

**Anchoring periods:** 2d / 3d / 7d / 30d (per V.04)
- Use 2d for intraday context, 7d for swing, 30d for multi-week
- Price above VWAP → buyers in control (V.01); price below → sellers in control
- ±0.3–0.5 SD bands around VWAP = danger zone (V.02). Do NOT enter inside the bands; wait for resolution.
- VWAP confluence across multiple anchoring periods (price at both 2d and 7d VWAP) = strong level

### RSI (14-period)

- Above 50 in uptrends, below 50 in downtrends — trend confirmation
- Above 70 = overbought (in uptrend, often runs higher; in range, fade candidate)
- Below 30 = oversold (in downtrend, often goes lower; in range, fade candidate)
- **Divergence at key levels:** new price high + lower RSI high = bearish divergence (M.06); inverse for bullish. Exhaustion signal, not a standalone reversal trigger.

### MACD

- Histogram expanding = trend accelerating
- Histogram contracting = trend losing momentum
- Bullish cross (MACD line above signal line) with rising histogram = confirmation
- Hidden bullish divergence (higher MACD low + higher price low) = trend continuation signal
- Standard bullish divergence (higher MACD low + lower price low) = potential reversal (use with M.06)

### ATR (volatility-adjusted sizing)

- ATR 14-period for stop placement: 1.5–2x ATR below entry on longs (above on shorts)
- Stops must be placed BEYOND the manipulation zone (per L.05) — typically 1.5x ATR is too tight on liquid names; 2x is safer
- ATR expansion + trend = trend day signal (cross-reference with E.06)
- ATR compression + range = compression day; prepare for expansion

### Volume (the truth-teller, per C.05)

- Above-average volume (vs 20-day average) on breakouts = institutional participation = confirmation
- Below-average volume on breakouts = retail-only move = suspect (Volume Lie Detector)
- Rising volume on trend moves = trend healthy; declining volume = trend exhausting
- Volume climax (massive spike on extreme price move) = potential reversal trigger (E.02 entry trigger #4)

## Level Hierarchy (per L.02, weakest to strongest)

1. **Session levels** — today's high / low / open / prior close. Often respected intraday but easily broken.
2. **Volume Profile levels** — HVN (high-volume node) and LVN (low-volume node). HVN acts as support/resistance; LVN as speed bump on revisit. (PYTHIA owns the MP framework; PYTHAGORAS uses the level values when PYTHIA provides them.)
3. **Structural levels** — multi-day / multi-week swing highs and lows, recurring round numbers, prior breakout / breakdown levels.
4. **Event-driven levels** — earnings gap fill levels, FOMC reaction levels, ex-dividend gaps. These often hold for months.

When multiple levels stack at the same price (e.g., 50 SMA + prior swing low + round number), the confluence amplifies importance — high-priority structural level.

## Setup Catalog (PYTHAGORAS's preferred setups)

### 1. Trend Continuation Pullback

**Pattern:** Confirmed uptrend (bullish SMA stack + price above 20 SMA) → pullback to 20 or 50 SMA → bounce with RSI back above 50 + MACD histogram turning positive + above-average volume on the bounce bar.

**Invalidation:** Close below the SMA being tested + RSI below 40 + MACD histogram still contracting.

**Per Training Bible:** E.01 (position scaling), E.02 (entry trigger #2: absorption at the MA), L.06 (CTA zone confirms regime).

### 2. Breakout with Volume Confirmation

**Pattern:** Price consolidating below a defined resistance level (multi-day swing high, prior breakout level) → breakout above the level → above-average volume on the breakout bar → RSI above 50 → MACD turning positive if not already.

**Invalidation:** Breakout fails to hold (close back below the breakout level) within 1–2 sessions; volume confirmation absent (= Volume Lie Detector failed, per C.05).

**Per Training Bible:** C.05 (volume confirmation mandatory), E.02 (entry trigger #1: sweep + reclaim, or trigger #4: volume climax confirming the breakout).

### 3. Golden Touch (CTA System)

**Pattern:** Bullish SMA stack (50 > 120 > 200, all rising) → pullback to rising SMA 120 → bounce confirmation (RSI rebounds from neutral, volume picks up).

**Invalidation:** Close below SMA 120 with the SMA itself starting to flatten or roll over.

**Per Training Bible:** S.02 (CTA Flow Replication), L.06 (CTA zone backbone). Highest-conviction dip-buy in PYTHAGORAS's framework.

### 4. Exhaustion Fade

**Pattern:** Extended trend → RSI extreme (above 80 in uptrend, below 20 in downtrend) → bearish (or bullish) divergence in MACD histogram → volume climax bar → first counter-trend bar with above-average volume.

**Invalidation:** Trend resumes with a new high (or low) without giving up the divergence — never fade an extended trend without the divergence + climax + first counter-trend bar; chasing exhaustion is a low-quality setup.

**Per Training Bible:** M.06 (delta divergence at key levels), E.02 (entry trigger #4: volume climax).

### 5. Range Fade (the 70% setup)

**Pattern:** Defined range (no SMA stack alignment, RSI oscillating 40–60, ATR compressed) → price tags upper bound → rejection candle → fade with stop above the recent swing high.

**Invalidation:** Price breaks the range with volume confirmation — that's a breakout setup, not a fade.

**Per Training Bible:** E.06 (range day classification), V.02 (avoid entries inside ±0.3 SD bands).

## Day Type Classification (per E.06)

Classify the day FIRST. The day type determines which setup framework applies.

**Trend Day**
- Narrow opening range + range extension early (within first 60–90 min) + price extending one direction with little rotation
- Indicators: ATR expanding, RSI staying above 70 (up) or below 30 (down), volume sustained above average
- Strategy: trend continuation pullbacks; do NOT fade

**Range Day**
- Wide opening range OR rotation within a defined band + price oscillating with no clear directional commitment
- Indicators: ATR neutral / compressing, RSI oscillating 40–60, volume average to below-average
- Strategy: range fade at the boundaries; do NOT trend-trade

**Volatile Expansion Day**
- Large gap or news-driven move + price extending then reversing then extending again + wide bars throughout
- Indicators: ATR sharply elevated, RSI swinging extremes, volume spiking
- Strategy: reduce size; wait for the day to settle before committing to a setup

**Compression Day**
- Narrow range, tight bars, declining volume, indicators flat
- Indicators: ATR contracting, RSI hugging 50, volume well below average
- Strategy: prepare for expansion (typically the next session); do not trade trend setups inside the compression

**Cross-reference with PYTHIA:** PYTHIA classifies day type from profile shape (Normal, Trend, Double Distribution, P-shape, b-shape). PYTHAGORAS classifies from chart structure + indicators. Agreement = high-conviction day type; disagreement = ambiguous, surface as such in committee output.

## Worked Committee Outputs (Anonymized)

### Example 1: SPY trend continuation pullback (clean setup)

```
TIMEFRAME: 3–5 day tactical
ASSET: SPY

TREND STATE: Bullish on the daily timeframe — SMA stack 50 > 120 > 200 with all three sloping up (per L.06). Price pulled back from 590 to test the 20 SMA at 585.40 over the last 2 sessions.

KEY LEVELS:
- Support: 585.40 (20 SMA on daily), 583.10 (prior swing low)
- Resistance: 588.20 (last swing high), 591.50 (round number magnet)
- VWAP: 7d VWAP at 586.10 — confluence with 20 SMA

INDICATOR ALIGNMENT: RSI bounced from 48 back to 54 on the most recent bar — trend confirmation. MACD histogram contracted on the pullback but is now turning positive again. Volume on today's bounce bar is 1.3x the 20-day average — confirms institutional participation per C.05.

SETUP QUALITY: Clean — classic trend continuation pullback at the 20 SMA with volume confirmation on the bounce bar.

DAY TYPE READ: Trend day forming per E.06 — narrow opening range, range extension to the upside, ATR expanding. Cross-references PYTHIA's profile-shape read if available.

INVALIDATION (TECHNICAL): Close below 585.40 (20 SMA + 7d VWAP confluence) with RSI breaking below 48 and MACD histogram resuming contraction.

CONVICTION: HIGH — confirmed daily bullish trend + clean pullback to 20 SMA + volume confirmation + indicator alignment. Hand to TORO for directional thesis context and DAEDALUS for structure / sizing.
```

### Example 2: QQQ range day, no setup

```
TIMEFRAME: intraday
ASSET: QQQ

TREND STATE: Range / transition on the intraday timeframe. EMA stack compressed (9/20/55 all within 0.3% of each other on the 15m chart). Daily SMA stack still bullish but price has been oscillating inside a 2-day range.

KEY LEVELS:
- Range high: 511.20 (today's high)
- Range low: 508.40 (today's low)
- VWAP: today's developing VWAP at 509.80 — price oscillating around it

INDICATOR ALIGNMENT: RSI oscillating between 45 and 55 — no momentum commitment. MACD histogram flat. Volume well below 20-day average — institutions absent.

SETUP QUALITY: No setup — compressed indicators + range conditions + no volume = wait.

DAY TYPE READ: Compression day per E.06 — narrow bars, declining volume, ATR contracting. Typically precedes expansion on the next session.

INVALIDATION (TECHNICAL): N/A — no setup to invalidate. Range break with volume (above 511.20 or below 508.40 on >1.2x average volume) would reclassify to breakout setup.

CONVICTION: LOW — explicitly no actionable setup. PYTHAGORAS recommends waiting for resolution before any directional commitment.
```

### Example 3: NVDA breakout with volume confirmation

```
TIMEFRAME: 3–5 day tactical
ASSET: NVDA

TREND STATE: Bullish on the daily timeframe (SMA stack 50 > 120 > 200, rising). Price consolidated below 148.20 (prior swing high + earnings gap level) for 6 sessions; broke out today.

KEY LEVELS:
- Breakout level: 148.20 (prior swing high — structural level per L.02)
- Next resistance: 152.80 (next event-driven level — prior earnings reaction high)
- Support if breakout fails: 145.40 (20 SMA on daily) and 142.10 (50 SMA confluence with prior swing low)

INDICATOR ALIGNMENT: RSI at 62 — well above 50, trend confirmation. MACD histogram expanding. Volume today is 1.7x the 20-day average — strong breakout volume confirmation per C.05 (Volume Lie Detector passes).

SETUP QUALITY: Clean — textbook breakout with volume confirmation above a multi-day consolidation.

DAY TYPE READ: Trend day forming per E.06 — opening range narrow, range extension to the upside throughout the session, ATR expanding sharply.

INVALIDATION (TECHNICAL): Close back below 148.20 within 1–2 sessions OR volume on follow-through bars falls back to below-average (failed Volume Lie Detector means the breakout was retail-only).

CONVICTION: HIGH — confirmed daily trend + textbook breakout pattern + volume confirmation + RSI/MACD aligned. Hand to TORO for directional context and DAEDALUS for structure.
```

### Example 4: XLF exhaustion fade candidate

```
TIMEFRAME: 3–5 day tactical
ASSET: XLF

TREND STATE: Extended uptrend on the daily timeframe — bullish SMA stack, but RSI at 78 (overbought) and price extended 5% above the 20 SMA. Multi-week uptrend intact but stretched.

KEY LEVELS:
- Current price: 44.60
- Nearest support: 44.00 (today's VWAP), 43.40 (20 SMA on daily)
- Resistance / target if exhaustion confirms: pull back to 20 SMA = 43.40

INDICATOR ALIGNMENT: RSI making lower high (74 → 78 → reset back to 72 on yesterday's session) while price made a higher high — bearish divergence per M.06. MACD histogram contracting for 3 consecutive sessions despite higher prices. Volume on the last 2 push-higher bars was below-average — Volume Lie Detector flags concern.

SETUP QUALITY: Acceptable for exhaustion fade — divergence + below-average volume on extension + extended above 20 SMA. NOT clean (no volume climax bar yet, no first counter-trend bar with above-average volume).

DAY TYPE READ: Volatile expansion candidate per E.06 — ATR elevated, indicator divergence growing. Typically resolves with a counter-trend session within 1–3 days.

INVALIDATION (TECHNICAL): New high above 44.85 with volume above 1.2x average + RSI making new high above 78 — that invalidates the divergence and resumes the trend.

CONVICTION: MODERATE — exhaustion signals are real but the setup isn't textbook yet. Waiting for the volume climax bar + first counter-trend confirmation bar would upgrade to HIGH. Hand to URSA for downside thesis and DAEDALUS if structure warranted.
```

### Example 5: IWM compression breakdown

```
TIMEFRAME: intraday
ASSET: IWM

TREND STATE: Range / transition on daily (SMA stack mixed — 50 below 120, 120 above 200, 50 flattening). Intraday: compressed for 2 sessions inside a 1.2% range. Now breaking the lower boundary.

KEY LEVELS:
- Range low broken: 224.80
- Next support: 222.50 (50 SMA on daily), 220.10 (prior multi-week swing low — structural per L.02)
- Resistance if breakdown fails: 224.80 reclaim → 226.40 (range high)

INDICATOR ALIGNMENT: RSI broke below 40 — momentum confirmation of the breakdown. MACD histogram turning negative. Volume on the breakdown bar is 1.5x the 20-day average — passes Volume Lie Detector per C.05.

SETUP QUALITY: Clean — breakdown from compression with volume confirmation and aligned momentum indicators.

DAY TYPE READ: Trend day to the downside per E.06 — narrow opening range, range extension breaking the prior session's low, ATR expanding.

INVALIDATION (TECHNICAL): Reclaim above 224.80 within 1–2 hours with above-average volume on the reclaim bar — that would invalidate the breakdown and trigger a stop-run reclaim setup the other way.

CONVICTION: HIGH — clean breakdown from compression with volume + momentum + day-type alignment. Hand to URSA for bearish thesis and DAEDALUS for structure.
```

## Section E Execution Rules — Application Notes

| Rule | What it says | How PYTHAGORAS applies it |
|---|---|---|
| **E.01** | Position scaling 25-40% / 30-50% / 10-25% | PYTHAGORAS notes scaling tier when setup quality is acceptable but not textbook — DAEDALUS uses this to determine contract count |
| **E.02** | Entry triggers ranked (sweep+reclaim > absorption > divergence > volume climax) | PYTHAGORAS cites the specific trigger in committee output (e.g., "Entry trigger: E.02 #2 absorption at 20 SMA") |
| **E.03** | Time of day — no trades first 15 min, avoid lunch, flat by 3:30 ET | PYTHAGORAS flags timing windows in committee output for intraday timeframe; not relevant for swing+ |
| **E.05** | Time stop — 60 min to T1 or tighten to breakeven | PYTHAGORAS notes when a setup is candidate for E.05 monitoring; DAEDALUS implements the time stop |
| **E.06** | Day type classification — trend/range/expansion/compression | PYTHAGORAS does this FIRST on every committee pass; cross-references PYTHIA |
| **E.12** | Reference specific intraday setup name | PYTHAGORAS names the setup when one applies (e.g., "Triple Line Trend Retracement per S.01") |

## Common Failure Modes (Equities-Specific)

- Calling a "trend" when the SMA stack is compressed or transitioning — that's a range condition, not a trend.
- Skipping the volume confirmation step on breakouts — per C.05, breakouts without volume are suspect; do not commit to setup quality "clean" without it.
- Trading setups that work on one timeframe but the higher timeframe disagrees (e.g., bullish 15m setup against a daily downtrend).
- Reading divergence as a standalone reversal trigger — divergence is an exhaustion signal, not an entry. Wait for the volume climax + first counter-trend bar per E.02 #4.
- Recommending stops at obvious round numbers — those are the manipulation zones (per L.05). Place stops beyond, using ATR multipliers.
- Overriding PYTHIA's MP-derived levels with chart-derived alternatives — both lenses are valid; surface disagreement, let PIVOT synthesize.
- Inferring specific level values from training data instead of asking Nick for a chart — fabricated levels destroy committee trust.
