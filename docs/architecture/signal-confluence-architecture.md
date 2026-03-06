# Signal Confluence Architecture — Design Document

**Author:** Nick Hertzog + Claude (Architecture Session)
**Date:** March 6, 2026
**Status:** APPROVED WITH MODIFICATIONS — Committee-reviewed, not yet built
**Scope:** Defines how the signal system should evolve from independent strategies into a unified confluence engine that makes strategies strengthen each other.

**Committee Review:** March 6, 2026 — Double-pass analysis (TORO/URSA/TECHNICALS/PIVOT). Verdict: BUILD WITH MODIFICATIONS. Key changes: resequenced phases, added validation gates, tightened lens categories, deferred Phase C.

---

## The Problem

Right now, every strategy is an independent signal generator. If AAPL triggers a CTA Pullback Entry, a Holy Grail confirmation, AND a Whale Hunter bullish signal on the same day, that shows up as 3 separate trade ideas in the feed — not one screaming-loud setup. Meanwhile, a weak Scout alert on some random ticker gets the same visual weight. Everything is flat.

The system generates ~40-55 trade ideas per day across 6 active strategies. Nick manually scans these and selects which to send to the Trading Committee via the Analyze button. There's no automated way to surface which ideas are reinforced by multiple independent signals.

**The 0 TAKE problem:** 100 committee runs produced zero TAKE recommendations. 70% of signals expired before Nick acted. This is a signal SELECTION problem, not a signal quality problem. The committee is seeing random samples from a noisy universe, not the setups where multiple independent systems agree something real is happening.

## The Goal

A system where strategies *reinforce* each other. One strategy firing on a ticker is interesting. Two strategies firing on the same ticker in the same direction on the same day is actionable. Three is "stop what you're doing and look at this."

Each individual strategy doesn't need to be perfect. It needs to be an **independent lens** on the same market data. When multiple independent lenses point at the same ticker and direction, the probability of a real setup goes way up.

**Important caveat (from URSA):** Three mediocre signals on the same ticker ≠ one high-quality signal. Confluence is a *filtering mechanism* to surface the 5-10 signals/day that deserve committee analysis. It is NOT a claim that stacking weak signals creates strong ones. This must be validated empirically before trusting it.

---

## Critical Constraint: TradingView Subscription Limits

Nick's TradingView plan allows:
- **2 Watchlist Alerts** (upgradeable to 15 on a significantly more expensive plan)
- **Watchlists limited to 50-100 tickers**
- **Per-chart alerts are unlimited** (circuit breakers, TICK, breadth, etc. don't count)

This means we CANNOT rely on TradingView to run every strategy across the full ticker universe. The architecture must work around this.

**Note (from URSA):** The TV upgrade cost ($30-60/mo) may be cheaper than the engineering effort to port strategies server-side. However, the server-side architecture has value beyond the subscription savings — it means signal generation runs on infrastructure we control, with no third-party dependency. The engineering work is not wasted even if TV is upgraded later.

---

## Architecture: Two-Tier Signal Generation

### Tier 1: Server-Side Scanners (Railway — No TV Dependency)

Strategies that only need OHLCV bar data (daily or hourly candles, volume, standard indicators like SMA/EMA/RSI/ADX/ATR) should run as Python scanners on Railway, like the CTA Scanner already does.

**Can be ported server-side (OHLCV is sufficient):**

| Strategy | Current Source | Why It Can Be Server-Side |
|---|---|---|
| CTA Scanner (9 signal types) | Already server-side | Already done — 285 trade ideas |
| Exhaustion | Already server-side | Already done — 13 trade ideas |
| Holy Grail | TradingView PineScript | ADX + 20 EMA pullback + confirmation candle. Standard OHLCV math. |
| Scout Sniper | TradingView PineScript | RSI hooks + RVOL + VWAP position. All computable from bars. |
| Hub Sniper | TradingView PineScript | VWAP bands + ADX + exhaustion candles. All computable from bars. **⚠️ HIGHEST PORT RISK** — VWAP band calculation from yfinance OHLCV may diverge from TV's tick-level VWAP. |

Server-side scanners have **no ticker limits**. They scan the full watchlist + S&amp;P 500 + Russell universe (200+ tickers currently, expandable to 500+). They run on a schedule (every 15-60 min during market hours) and cost nothing beyond Railway compute.

**Migration path:** Port the PineScript logic from Holy Grail, Scout Sniper, and Hub Sniper into Python scanner modules that follow the same pattern as `cta_scanner.py`. The PineScripts stay on TradingView as visual chart aids (you still want to see the signals on your charts), but the webhook alerts become optional — the server-side scanner is the primary signal source.

**Data source note (from TECHNICALS):** Holy Grail and Scout need intraday bars (15m or 1H), not daily bars. Use Polygon.io intraday via the Railway endpoints, not yfinance, for better accuracy and lower latency.

### Tier 2: TradingView Intrabar Strategies (Requires Real-Time Sub-Bar Data)

Some strategies genuinely need data that OHLCV APIs can't provide — specifically, intrabar volume distribution and lower-timeframe price action within a single bar.

**Must stay on TradingView:**

| Strategy | Why It Needs TV | TV Resource Cost |
|---|---|---|
| Whale Hunter v2 | Uses `request.security_lower_tf()` for 1-min POC calculation | 1 Watchlist Alert |
| Absorption Wall Detector | Needs intrabar delta via lower-timeframe volume splits | 1 Watchlist Alert (or combined with Whale Hunter) |
| Circuit Breaker (SPY) | Real-time SPY price monitoring | Per-chart alert (free) |
| Circuit Breaker (VIX) | Real-time VIX price monitoring | Per-chart alert (free) |
| TICK Reporter | $TICK symbol, per-chart | Per-chart alert (free) |
| Breadth Webhook | $UVOL/$DVOL symbols, per-chart | Per-chart alert (free) |
| McClellan Webhook | $ADVN/$DECLN symbols, daily | Per-chart alert (free) |

**TV allocation:**
- Watchlist Alert 1: Whale Hunter v2 on top 50 tickers
- Watchlist Alert 2: Absorption Wall Detector on top 50 tickers
- Per-chart alerts: Circuit breakers, TICK, breadth, McClellan (unlimited, no cost)

**Phase C (combining Whale Hunter + Absorption Wall into one script) is DEFERRED** per committee recommendation — high engineering risk, not needed yet since neither is currently using a watchlist slot.

---

## The Confluence Layer

Sits between signal generation and Trade Ideas display. Every signal is still generated independently (strategies should never be coupled to each other's code). But before a signal hits Trade Ideas, a confluence engine checks: "Is anything else saying the same thing about this ticker right now?"

### Three Tiers

**Standalone** — One strategy, one signal.
- Default state for all signals
- Shows in Trade Ideas at normal priority
- No special treatment

**Confirmed** — Two different analytical lenses agree on the same ticker + direction within a 4-hour window.
- Example: CTA says PULLBACK_ENTRY LONG on AAPL, and Hub Sniper says LONG on AAPL 2 hours later
- Gets a visual confluence badge in Trade Ideas
- Elevated sort priority
- Discord ping to `#📊-signals`

**Conviction** — Three or more lenses converge, OR two lenses plus a quality gate (Scout score ≥5, or Holy Grail ADX ≥30).
- Example: CTA PULLBACK_ENTRY + Hub Sniper LONG at VAL + Whale Hunter bullish accumulation
- Highest visual priority in Trade Ideas
- Automatic Discord alert with "🔥 CONVICTION SETUP" tag
- Candidate for automatic committee queuing (start with Discord notification only; add auto-committee after 2 weeks of data)

### Confluence Rules

**Time window:** 4 hours (not full session). Two signals 6 hours apart are probably unrelated. Two signals 2 hours apart from different lenses are meaningful. (Changed from "same trading session" per TECHNICALS recommendation.)

**Direction must match:** A CTA LONG and a Hub Sniper SHORT on the same ticker are **conflicting**, not confirming. Conflicting signals get demoted.

**Lens categories (REVISED per committee review):**

The original design had 7 lens categories. Committee analysis revealed that CTA and Holy Grail are "adjacent lenses" (both are trend-following pullback strategies using moving averages), and CTA TWO_CLOSE_VOLUME overlaps with Hub Sniper's mean reversion thesis. Revised categories:

| Lens Category | Strategies | Independence Level |
|---|---|---|
| **Trend Structure** | CTA PULLBACK_ENTRY, CTA RESISTANCE_REJECTION, CTA GOLDEN_TOUCH, CTA BEARISH_BREAKDOWN, CTA DEATH_CROSS | Internal — treat all CTA sub-types as ONE lens |
| **Momentum Continuation** | Holy Grail | Adjacent to Trend Structure — confluence counts but at reduced weight |
| **Mean Reversion** | Hub Sniper, CTA TWO_CLOSE_VOLUME | Hub Sniper is primary; CTA TWO_CLOSE_VOLUME is adjacent |
| **Reversal Detection** | Scout Sniper, Exhaustion | Complementary — both count independently |
| **Institutional Footprint** | Whale Hunter | Fully independent |
| **Order Flow Balance** | Absorption Wall | Fully independent |
| **Options Flow** | UW Watcher | Fully independent |

**Key rule:** CTA + Holy Grail on the same ticker counts as CONFIRMED (adjacent lenses) but should NOT count toward CONVICTION on its own. CTA + Hub Sniper (different lens categories) is a stronger confirmation than CTA + Holy Grail.

**Truly independent lenses (highest confluence value):**
1. Trend/Momentum (CTA or Holy Grail — pick the stronger signal, count as 1)
2. Mean Reversion (Hub Sniper)
3. Reversal (Scout or Exhaustion)
4. Institutional Footprint (Whale Hunter)
5. Order Flow (Absorption Wall)
6. Options Flow (UW Watcher)

Three of these agreeing = genuine CONVICTION.

### Implementation Approach

The confluence engine is a **background task** that runs every 15 minutes during market hours on Railway (similar to the signal expiry loop already in `main.py`). It:

1. Queries active signals from the past 4 hours (Postgres `trade_ideas` table)
2. Groups by `ticker` + `direction`
3. For each group with 2+ signals from different lens categories:
   a. Calculates a confluence score (with reduced weight for adjacent lenses)
   b. Updates the signals with confluence metadata (tier, contributing strategies, badge)
   c. For Conviction tier: posts a Discord alert
4. Broadcasts confluence updates via WebSocket so the frontend can update in real-time

**New fields on trade ideas:**
```
confluence_tier: "STANDALONE" | "CONFIRMED" | "CONVICTION"
confluence_signals: [signal_id, signal_id, ...]
confluence_lenses: ["TREND_STRUCTURE", "MEAN_REVERSION"]
confluence_updated_at: timestamp
```

### Frontend Impact

Trade Ideas UI gets:
- A confluence badge/icon on Confirmed and Conviction signals
- Sort/filter option: "Show confluent signals first"
- Confluence detail tooltip: "Also flagged by: Hub Sniper (LONG, 2:15 PM), CTA Pullback (LONG, 1:47 PM)"

---

## Approved Build Sequence (Committee-Modified)

### Step 0: Fix Outcome Tracking (PREREQUISITE — This Week)

**Non-negotiable.** The nightly outcome matcher cron (11 PM ET) exists but isn't writing to `outcome_log.jsonl`. Without P&L data:
- Cannot validate whether server-side signals match TV quality
- Cannot measure whether confluence improves win rates
- Cannot determine which strategies to keep/kill
- Every decision about weighting and thresholds is a guess

SSH to VPS, check the `committee_outcomes.py` script, fix whatever's broken. This is a 30-minute fix that unblocks everything.

### Week 1: Confluence Engine + VWAP Validation (Parallel)

**Day 1-2:** Build VWAP validation harness
- Run parallel TV + server-side VWAP calculations on SPY for 5 trading days
- Log divergence at 1-minute intervals
- Acceptance threshold: mean absolute error < 0.1%, max error < 0.5%
- If threshold fails, Hub Sniper stays on TradingView and uses a watchlist alert slot

**Day 2-5:** Build Phase B — Confluence Engine
- Use existing 332 signals already in pipeline (CTA 285 + Scout 21 + Exhaustion 13 + Holy Grail 8 + Hub Sniper 6)
- Implement lens categorization, 4-hour grouping window, tier assignment
- Discord webhook for CONFIRMED (ping) and CONVICTION (alert)

**Day 5-7:** Collect 20 confluence events from live market, measure vs standalone

### Validation Gate (MUST PASS before Week 2)

After 20 CONFIRMED/CONVICTION events fire, compare their 24-hour outcomes vs 20 random STANDALONE signals:
- Track: Win rate, R-multiple, time-to-invalidation
- **Success threshold:** Confluence tier beats standalone by ≥12% win rate OR ≥0.3R average
- **Failure condition:** If confluence ≤ standalone + 5%, STOP and reassess before proceeding

### Week 2: Server-Side Ports (If Validation Passes)

**Phase A.1:** Port Holy Grail (2-3 days)
- Server-side scanner runs every 15 min (offset +3 min from other scans to stagger API calls)
- Uses `ta-lib` or `pandas_ta` for EMA(20) and ADX calculations
- Matches TV logic: ADX ≥25, price within 0.15% of EMA, confirmation candle
- **Validation:** Run parallel TV + server-side on 10 known historical signals. Must match ≥80%.

**Phase A.2:** Port Scout Sniper (3-4 days) — MOVED UP per TECHNICALS
- RSI, RVOL, candle patterns are deterministic from OHLC — low divergence risk
- VWAP position check is simple above/below, not band arithmetic
- 15-min scan cadence catches setups within 1 bar of formation
- Carry over TRADEABLE/IGNORE filter and quality score (0-6)

**Phase A.3:** Port Hub Sniper (4-5 days) — MOVED TO LAST, conditional on VWAP validation
- Only proceed if VWAP validation harness passes acceptance threshold
- If VWAP divergence exceeds threshold, Hub Sniper stays on TradingView with 1 watchlist alert
- This is the highest-risk port due to VWAP band sensitivity

### Week 2 (Parallel): Wire TV-Only Strategies

**Absorption Wall → Trade Ideas**
- Rewrite PineScript alert payload from pipe-delimited to JSON
- Route through `process_generic_signal()` or build a dedicated handler
- Adds a genuinely unique lens (order flow) to the confluence pool

**Whale Hunter → Trade Ideas**
- Configure TV watchlist alert on top 50 tickers pointing to `/webhook/whale`
- Verify `whale.py` handler parses the v2 JSON payload correctly

### Week 3-4: Observe and Tune

- Review 2 weeks of confluence data
- Are Confirmed setups actually winning more than Standalone?
- Adjust lens categorization, time windows, and tier thresholds based on real outcomes
- Decide whether to add auto-committee for Conviction tier (start with Discord notification only)

### DEFERRED

- **Phase C (combine Whale Hunter + Absorption Wall PineScripts):** HIGH engineering risk, not needed until both watchlist alert slots are occupied
- **Auto-committee for Conviction tier:** Start with Discord notifications only, add auto-queuing after 2 weeks of outcome data proves confluence value
- **TV subscription upgrade:** Not needed if server-side ports work. Revisit if Hub Sniper VWAP validation fails.

---

## What Each Strategy Provides to the Ensemble

| Strategy | What It Detects | Unique Edge | Lens |
|---|---|---|---|
| CTA Scanner | Trend structure via SMA alignment (20/50/120/200) | Institutional flow replication | Trend Structure |
| Holy Grail | Strong trend + pullback to EMA + continuation | Raschke-proven pattern with ADX confirmation | Momentum (adjacent to Trend) |
| Hub Sniper | Price at VWAP band extremes + exhaustion or confirmation | Statistical mean reversion with regime awareness | Mean Reversion |
| Scout Sniper | RSI extremes + reversal candles + VWAP position | Early warning — catches reversals before they confirm | Reversal Detection |
| Exhaustion | Extended moves + capitulation volume + reversal candles | Counter-trend setups where the trend has gone too far | Reversal Detection |
| Whale Hunter | Volume + POC fingerprint matching across bars | Detects algorithmic execution that other strategies can't see | Institutional Footprint |
| Absorption Wall | Intrabar buy/sell delta balance at high volume | Order flow balance — where large orders are being absorbed | Order Flow Balance |
| UW Watcher | Unusual options activity + net premium direction | Smart money positioning via derivatives flow | Options Flow |

---

## Cost &amp; Performance

**Server-side scanner compute:** Each ported strategy adds ~5-15 seconds per scan run (200 tickers × API call + indicator calculation). Use Polygon.io for intraday data (not yfinance) for better accuracy. Stagger scans to avoid rate limits. Total additional Railway compute: minimal.

**Confluence engine:** Runs every 15 min, queries Postgres for active signals, groups and scores. Sub-second execution. No LLM cost.

**TV subscription:** Stays at current plan (2 watchlist alerts). No upgrade needed unless Hub Sniper VWAP validation fails.

**LLM cost:** No change for manual Analyze. Auto-committee for Conviction tier deferred until validated — when enabled, capped at 2-3 runs/day (~$0.06/day).

---

## Definition of Done

The system is "confluent" when:
1. At least 4 independent lens categories are generating signals into the same pipeline
2. The confluence engine groups signals by ticker+direction with 4-hour window and assigns tiers
3. Trade Ideas UI shows confluence badges and supports sorting by confluence
4. Conviction-tier setups generate a Discord notification without manual intervention
5. **Validation data shows confluence tier beats standalone by ≥12% win rate or ≥0.3R** (not just assumed)
6. Outcome tracking is operational and producing P&amp;L data for continuous validation

---

## URSA's Manual Validation Test (Pre-Build Sanity Check)

Before any engineering, manually track the next 20 times you notice 2+ strategies firing on the same ticker within 4 hours in the current Trade Ideas feed. Compare their outcomes vs 20 random standalone signals. If confluence signals don't meaningfully outperform, the entire architecture is premature. This costs zero engineering time and takes ~2 weeks of observation.
