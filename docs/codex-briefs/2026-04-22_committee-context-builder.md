# Brief: Committee Context Builder — Per-Ticker Data Hydration

**Date:** 2026-04-22
**Priority:** P0 (committee reasoning is currently garbage-in; fixing threshold without fixing context just gives fewer garbage reviews)
**Target:** Claude Code (VSCode) — with preliminary Titans design review
**Estimated effort:** 3-4 hours (Titans design pass + implementation + verification)
**Origin:** 2026-04-22 live committee output on MO (Artemis, score 82) showed every analyst agent complaining about missing per-ticker data:
- TECHNICALS: "No specific chart data for MO in this context, I will not fabricate levels"
- URSA: "Options flow context is explicitly bearish on semis — ZERO flow confirmation for MO"
- PYTHIA: Used 2-month-old zone shift because no fresh market profile was pulled
- TORO: Reasoned from macro regime only, no MO-specific signal

The committee is being asked to make decisions without per-ticker evidence. Every review is effectively a macro-only call wearing a committee costume.

---

## Root cause

Current context builder in `/opt/openclaw/workspace/scripts/committee_context.py` (and/or the `build_market_context` call in `committee_railway_bridge.py:264`) pulls **market-wide** context: bias composite, sector rotation, macro regime, general flow radar. It does NOT pull **per-ticker** context scoped to the signal being reviewed.

The committee sees:
- ✅ Market bias (LEAN_URSA / MINOR_TORO / etc.)
- ✅ Sector strength map  
- ✅ Macro regime (DEFCON levels)
- ❌ **The ticker's own technicals** (EMAs, RSI, MACD, volume profile)
- ❌ **The ticker's own options flow** (now available post-flow_poller fix)
- ❌ **The ticker's own Pythia zone** (fresh — not 2 months stale)
- ❌ **The ticker's own IV rank + earnings** (UW has this)
- ❌ **Recent news headlines for the ticker** (UW headlines endpoint)

---

## Titans design pass (required before implementation)

Because this is a significant architectural change — restructuring how `committee_context.py` builds its packet — run Titans Pass 1 → Pass 2 → ATHENA overview BEFORE CC writes code. Specifically:

- **ATLAS:** How should the new per-ticker hydration layer be structured? Async-parallel fetches? Cache hits against `flow_events`, `signals` recent rows, cached UW data? What's the schema of the context object passed to `run_committee`?
- **HELIOS:** Not really relevant — this is backend. Skip.
- **AEGIS:** Does the hydration introduce new API keys, external calls, credential exposure? Rate-limit exposure against UW's 120req/min?
- **ATHENA:** Final call on scope cut. If the full data set takes 30 seconds per signal to pull, we're creating a new problem. What's the minimum viable context packet?

Once Titans agrees on architecture, implementation below.

---

## Required context additions

### Per-ticker technicals

For the signal's ticker, pull via yfinance (OHLCV only per data hierarchy):

- Current price, 20-period EMA, 50-period EMA, 200-period EMA on signal's timeframe
- RSI(14)
- MACD + signal line + histogram
- Volume ratio (current volume / 20-period avg)
- ADX (already computed by Phase 5 filter for Artemis — reuse the cache)

Compute once, pass to all agents.

### Per-ticker options flow

Now that `flow_events` is live (1400+ rows / 24h confirmed 2026-04-22), filter on ticker:

```sql
SELECT 
  call_premium, put_premium, total_premium, 
  call_volume, put_volume, pc_ratio,
  flow_sentiment, captured_at
FROM flow_events
WHERE ticker = $1
  AND captured_at > NOW() - INTERVAL '24 hours'
ORDER BY captured_at DESC
LIMIT 10;
```

Plus: latest flow alerts for the ticker (via UW `/api/stock/{ticker}/flow-alerts`), capped at 5 most recent.

### Per-ticker Pythia zone

Fresh read — not cached from weeks ago. Pull current Pythia webhook state or compute from recent OHLCV. VAH, VAL, POC on both daily and signal's timeframe.

### Per-ticker derivatives state (for DAEDALUS — requires porting DAEDALUS first, see separate brief)

- IV rank (UW `/api/stock/{ticker}/iv-rank`)
- Realized HV
- Days to next earnings (UW earnings endpoint)
- GEX (UW greek-exposure endpoint, net call gamma + put gamma)
- Max pain for nearest monthly expiry

### Per-ticker news headlines (last 5)

UW `/api/news/headlines?ticker={ticker}&limit=5` — lets URSA and THALES factor known catalysts.

---

## Implementation sketch

In `committee_context.py`, add a new function called from `build_market_context`:

```python
async def hydrate_ticker_context(ticker: str, signal_timeframe: str) -> dict:
    """Pull per-ticker evidence for the committee to reason over."""
    # Run all fetches in parallel — this is latency-sensitive
    tech_task = asyncio.create_task(fetch_technicals(ticker, signal_timeframe))
    flow_task = asyncio.create_task(fetch_flow_context(ticker))
    pythia_task = asyncio.create_task(fetch_pythia_zone(ticker))
    deriv_task = asyncio.create_task(fetch_derivatives(ticker))
    news_task = asyncio.create_task(fetch_news(ticker, limit=5))
    
    # Wait for all, tolerate individual failures
    results = await asyncio.gather(
        tech_task, flow_task, pythia_task, deriv_task, news_task,
        return_exceptions=True,
    )
    tech, flow, pythia, deriv, news = [
        r if not isinstance(r, Exception) else None for r in results
    ]
    
    return {
        "technicals": tech,
        "flow": flow,
        "pythia_zone": pythia,
        "derivatives": deriv,
        "news_headlines": news,
    }
```

Then in the main context packet:

```python
def build_market_context(signal, api_url, api_key):
    base_context = build_existing_macro_context(...)  # whatever's there now
    ticker_context = asyncio.run(hydrate_ticker_context(
        signal["ticker"], signal.get("timeframe", "1D")
    ))
    return {**base_context, "ticker_context": ticker_context}
```

### Prompt updates required

Each agent's prompt in `pivot2_committee.py` needs to reference the new fields. TECHNICALS should read `ticker_context.technicals`. URSA should check `ticker_context.flow` for evidence against the position. PYTHIA should use `ticker_context.pythia_zone` and explicitly note "data as of TIMESTAMP" so the agent can judge staleness.

Key rule: **if a field is null, the agent must say so explicitly rather than reasoning around it.** Current MO output shows TECHNICALS correctly refused to fabricate — make that the pattern for all agents when data is missing.

---

## Verification

1. Pick a stuck PENDING_REVIEW signal (LCID probably still in COMMITTEE_REVIEW), manually run the bridge on it after deploy
2. Inspect the Discord embed output — does it show per-ticker technicals, flow, Pythia?
3. Read each agent's analysis — are they referencing specific LCID data (e.g., "LCID RSI at 58, 20EMA holding") rather than generic market commentary?
4. If any agent still says "no data provided" — that's a bug. Hydration should be exhaustive or explicit about gaps.

---

## Open question for Nick

The full hydration above is heavy: 5 parallel fetches per committee run. With the current 10 runs/day budget that's 50 extra UW calls/day, well within the 120/min rate limit. But **total committee run latency will go up from ~5s to probably 10-15s**.

Acceptable? If you want faster runs, we can:
- Drop the news headlines (saves 1 UW call)
- Cache the Pythia zone for 15 min per ticker
- Skip derivatives fetch if signal isn't an options trade

My recommendation: ship the full hydration first, measure actual latency, optimize if it matters. Don't pre-optimize.

---

## Done when

- [ ] Titans design pass complete (ATLAS + AEGIS + ATHENA sign-off, even if informal)
- [ ] `hydrate_ticker_context()` implemented with parallel fetches + tolerant error handling
- [ ] `build_market_context` returns packet containing both macro AND ticker-specific data
- [ ] Agent prompts updated to reference per-ticker fields
- [ ] Test run on a real pending signal shows committee reasoning from ticker-specific evidence
- [ ] No agent says "no data provided" unless a specific field legitimately failed to fetch
