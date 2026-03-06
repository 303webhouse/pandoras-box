# Signal Confluence Architecture — Design Document

**Author:** Nick Hertzog + Claude (Architecture Session)
**Date:** March 6, 2026
**Status:** APPROVED DESIGN — Not yet built
**Scope:** Defines how the signal system should evolve from independent strategies into a unified confluence engine that makes strategies strengthen each other.

---

## The Problem

Right now, every strategy is an independent signal generator. If AAPL triggers a CTA Pullback Entry, a Holy Grail confirmation, AND a Whale Hunter bullish signal on the same day, that shows up as 3 separate trade ideas in the feed — not one screaming-loud setup. Meanwhile, a weak Scout alert on some random ticker gets the same visual weight. Everything is flat.

The system generates ~40-55 trade ideas per day across 6 active strategies. Nick manually scans these and selects which to send to the Trading Committee via the Analyze button. There's no automated way to surface which ideas are reinforced by multiple independent signals.

## The Goal

A system where strategies *reinforce* each other. One strategy firing on a ticker is interesting. Two strategies firing on the same ticker in the same direction on the same day is actionable. Three is "stop what you're doing and look at this."

Each individual strategy doesn't need to be perfect. It needs to be an **independent lens** on the same market data. When multiple independent lenses point at the same ticker and direction, the probability of a real setup goes way up.

---

## Critical Constraint: TradingView Subscription Limits

Nick's TradingView plan allows:
- **2 Watchlist Alerts** (upgradeable to 15 on a significantly more expensive plan)
- **Watchlists limited to 50-100 tickers**
- **Per-chart alerts are unlimited** (circuit breakers, TICK, breadth, etc. don't count)

This means we CANNOT rely on TradingView to run every strategy across the full ticker universe. The architecture must work around this.

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
| Hub Sniper | TradingView PineScript | VWAP bands + ADX + exhaustion candles. All computable from bars. |

Server-side scanners have **no ticker limits**. They scan the full watchlist + S&P 500 + Russell universe (200+ tickers currently, expandable to 500+). They run on a schedule (every 15-60 min during market hours) and cost nothing beyond Railway compute.

**Migration path:** Port the PineScript logic from Holy Grail, Scout Sniper, and Hub Sniper into Python scanner modules that follow the same pattern as `cta_scanner.py`. The PineScripts stay on TradingView as visual chart aids (you still want to see the signals on your charts), but the webhook alerts become optional — the server-side scanner is the primary signal source.

### Tier 2: TradingView Intrabar Strategies (Requires Real-Time Sub-Bar Data)

Some strategies genuinely need data that OHLCV APIs can't provide — specifically, intrabar volume distribution and lower-timeframe price action within a single bar.

**Must stay on TradingView:**

| Strategy | Why It Needs TV | TV Resource Cost |
|---|---|---|
| Whale Hunter v2 | Uses `request.security_lower_tf()` for 1-min POC calculation | 1 Watchlist Alert |
| Absorption Wall Detector | Needs intrabar delta via lower-timeframe volume splits | Can share watchlist alert with Whale Hunter* |
| Circuit Breaker (SPY) | Real-time SPY price monitoring | Per-chart alert (free) |
| Circuit Breaker (VIX) | Real-time VIX price monitoring | Per-chart alert (free) |
| TICK Reporter | $TICK symbol, per-chart | Per-chart alert (free) |
| Breadth Webhook | $UVOL/$DVOL symbols, per-chart | Per-chart alert (free) |
| McClellan Webhook | $ADVN/$DECLN symbols, daily | Per-chart alert (free) |

*Whale Hunter and Absorption Wall could potentially be combined into a single PineScript that runs both detection algorithms and sends both signal types in the same alert. This is a significant PineScript engineering task but would reduce watchlist alert usage to 1.

**Optimal TV allocation:**
- Watchlist Alert 1: Combined Whale Hunter + Absorption Wall (top 50-100 tickers)
- Watchlist Alert 2: Reserved for future intrabar strategy, or expanded ticker coverage
- Per-chart alerts: Circuit breakers, TICK, breadth, McClellan (unlimited, no cost)

This means **80% of signal generation runs server-side with zero TV dependency**, and TV is reserved exclusively for the strategies that genuinely need real-time intrabar data.

---

## The Confluence Layer

Sits between signal generation and Trade Ideas display. Every signal is still generated independently (strategies should never be coupled to each other's code). But before a signal hits Trade Ideas, a confluence engine checks: "Is anything else saying the same thing about this ticker right now?"

### Three Tiers

**Standalone** — One strategy, one signal.
- Default state for all signals
- Shows in Trade Ideas at normal priority
- No special treatment

**Confirmed** — Two different strategies agree on the same ticker + direction within a time window.
- Example: CTA says PULLBACK_ENTRY LONG on AAPL, and Holy Grail says LONG on AAPL an hour later
- Gets a visual confluence badge in Trade Ideas
- Elevated sort priority
- Optional: automatic Discord ping to `#📊-signals`

**Conviction** — Three or more strategies converge, OR two strategies plus a structural confirmation.
- Example: CTA PULLBACK_ENTRY + Holy Grail + Whale Hunter bullish accumulation at the same price level
- Example: Hub Sniper LONG at VAL + Absorption Wall bullish at the same zone
- Highest visual priority in Trade Ideas
- Automatic Discord alert with "🔥 CONVICTION SETUP" tag
- Candidate for automatic committee queuing (bypasses manual Analyze click)

### Confluence Rules

**Time window:** Signals must fire within the same trading session (9:30 AM - 4:00 PM ET) to be grouped.

**Direction must match:** A CTA LONG and a Hub Sniper SHORT on the same ticker are **conflicting**, not confirming. Conflicting signals get demoted (same logic as the existing `score_confluence()` in `cta_scanner.py`).

**Strategy independence:** For confluence to be meaningful, the strategies must use different analytical lenses. Two signals from the CTA Scanner (e.g., PULLBACK_ENTRY + TRAPPED_SHORTS) already have their own confluence scoring. Cross-strategy confluence only counts when the strategies use fundamentally different methods:

| Lens | Strategies |
|---|---|
| Trend Structure (SMA alignment) | CTA Scanner |
| Momentum Continuation (ADX + pullback) | Holy Grail |
| Mean Reversion (VWAP bands) | Hub Sniper |
| Reversal Detection (RSI hooks + exhaustion) | Scout Sniper, Exhaustion |
| Institutional Footprint (volume matching) | Whale Hunter |
| Order Flow Balance (buy/sell delta) | Absorption Wall |
| Options Flow (institutional positioning) | UW Watcher |

Two signals from the same lens category don't count as confluence — they're redundant, not independent.

### Implementation Approach

The confluence engine is a **background task** that runs every 15 minutes during market hours on Railway (similar to the signal expiry loop already in `main.py`). It:

1. Queries active signals from the past session (Postgres `trade_ideas` table)
2. Groups by `ticker` + `direction`
3. For each group with 2+ signals from different lens categories:
   a. Calculates a confluence score
   b. Updates the signals with confluence metadata (tier, contributing strategies, badge)
   c. For Conviction tier: optionally posts a Discord alert and/or auto-queues for committee
4. Broadcasts confluence updates via WebSocket so the frontend can update in real-time

**New fields on trade ideas:**
```
confluence_tier: "STANDALONE" | "CONFIRMED" | "CONVICTION"
confluence_signals: [signal_id, signal_id, ...]  // other signals in the group
confluence_lenses: ["TREND_STRUCTURE", "MOMENTUM_CONTINUATION"]  // which lenses agree
confluence_updated_at: timestamp
```

### Frontend Impact

Trade Ideas UI gets:
- A confluence badge/icon on Confirmed and Conviction signals
- Sort/filter option: "Show confluent signals first"
- Confluence detail tooltip: "Also flagged by: Holy Grail (LONG, 2:15 PM), CTA Pullback (LONG, 1:47 PM)"

---

## Migration Plan

### Phase A: Port Strategies Server-Side (Prerequisite)

Before the confluence layer works well, we need enough independent signal sources running server-side. Priority order:

1. **Holy Grail → Server-Side Scanner** — Highest value. ADX + EMA pullback logic is straightforward to port. The PineScript version stays on TV as a visual aid but the scanner becomes the primary signal source.

2. **Hub Sniper → Server-Side Scanner** — VWAP band calculation, ADX, RSI, RVOL, and confirmation candle detection. Slightly more complex due to VWAP stdev bands and the AVWAP context gate, but all computable from OHLCV.

3. **Scout Sniper → Server-Side Scanner** — RSI hooks, RVOL, candle patterns. The TRADEABLE/IGNORE classification and the quality score (0-6) should carry over.

4. **Absorption Wall → Wire to Pipeline** — Rewrite the PineScript alert to send JSON (not pipe-delimited) and route through a Railway handler. This stays on TV (needs intrabar data) but its signals join the confluence pool.

5. **Whale Hunter → Wire to Pipeline** — Configure TV watchlist alert pointing to `/webhook/whale`. Verify the handler parses the v2 JSON payload. Also stays on TV.

### Phase B: Build Confluence Engine

Once we have 4+ independent lens categories generating signals server-side:

1. Add `confluence_*` fields to the trade ideas schema
2. Build the 15-min confluence background task
3. Add Discord notification for Conviction tier
4. Update Trade Ideas UI with confluence badges and sorting

### Phase C: Combine TV PineScripts

Optimize TradingView resource usage:

1. Combine Whale Hunter + Absorption Wall into a single PineScript indicator that runs both algorithms and sends both signal types
2. Apply to a watchlist of the top 50-100 tickers (your most-traded names + current positions + watchlist)
3. Free up the second watchlist alert slot

---

## What Each Strategy Provides to the Ensemble

The value of this architecture comes from each strategy being a genuinely different lens:

| Strategy | What It Detects | Unique Edge |
|---|---|---|
| CTA Scanner | Trend structure via SMA alignment (20/50/120/200) | Institutional flow replication — where CTAs are positioning |
| Holy Grail | Strong trend + pullback to EMA + continuation | Raschke-proven pattern with ADX confirmation |
| Hub Sniper | Price at VWAP band extremes + exhaustion or confirmation | Statistical mean reversion with regime awareness |
| Scout Sniper | RSI extremes + reversal candles + VWAP position | Early warning system — catches reversals before they confirm |
| Exhaustion | Extended moves + capitulation volume + reversal candles | Counter-trend setups where the trend has gone too far |
| Whale Hunter | Volume + POC fingerprint matching across bars | Detects algorithmic execution that other strategies can't see |
| Absorption Wall | Intrabar buy/sell delta balance at high volume | Order flow balance — where large orders are being absorbed |
| UW Watcher | Unusual options activity + net premium direction | Smart money positioning via derivatives flow |

When CTA says "the trend structure supports LONG on AAPL" and Whale Hunter says "I see institutional accumulation at this price on AAPL" and Hub Sniper says "price is at a VWAP support zone" — that's three completely independent analytical methods all pointing the same direction. That's not noise, that's signal.

---

## Cost & Performance

**Server-side scanner compute:** Each ported strategy adds ~5-15 seconds per scan run (200 tickers × yfinance call + indicator calculation). Stagger scans to avoid overloading yfinance rate limits. Total additional Railway compute: minimal (already running CTA scanner hourly).

**Confluence engine:** Runs every 15 min, queries Postgres for active signals, groups and scores. Sub-second execution. No LLM cost.

**TV subscription:** Stays at current plan (2 watchlist alerts). No upgrade needed unless we want broader intrabar coverage.

**LLM cost:** No change. Committee still runs only when Nick clicks Analyze (or auto-queued for Conviction tier — cap at 2-3 auto-runs per day to control cost).

---

## Definition of Done

The system is "confluent" when:
1. At least 4 independent lens categories are generating signals into the same pipeline
2. The confluence engine groups signals by ticker+direction and assigns tiers
3. Trade Ideas UI shows confluence badges and supports sorting by confluence
4. Conviction-tier setups generate a Discord notification without manual intervention
5. Individual strategy accuracy matters less because the ensemble filters noise naturally
