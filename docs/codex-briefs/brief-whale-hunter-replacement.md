# Brief: Replace Whale Hunter PineScript with UW Flow-to-Signal Pipeline

**Target Agent:** Claude Code (VSCode)
**Priority:** HIGH — replaces dead PineScript with live data source
**Repo:** `303webhouse/pandoras-box` (branch: `main`)
**Deploy:** Push to `main` → Railway auto-deploys

---

## Context

The Whale Hunter PineScript (TradingView) has NEVER fired a real signal across 32 alerts.
Its detection conditions are too strict for OHLCV bar data. Meanwhile, the UW Watcher on
VPS is already capturing institutional flow data from the Unusual Whales Discord Premium Bot
and posting it to Railway's `/api/uw/ticker-updates` endpoint, which stores it in Redis
(`uw:flow:{ticker}`) and Postgres (`flow_events`).

The fix: promote large UW flow events into DARK_POOL trade idea signals automatically.
No new data sources needed — we're wiring existing data into the existing signal pipeline.

Olympus Committee reviewed and approved this approach.

---

## Change 1: Archive Whale Hunter PineScript

Move the PineScript source to an archived directory. Do NOT delete it.

```bash
mkdir -p docs/pinescript/archived
git mv docs/pinescript/webhooks/whale_hunter_v2.pine docs/pinescript/archived/whale_hunter_v2.pine
```

Nick will manually delete the 32 TradingView alerts separately.

---

## Change 2: Add Flow-to-Signal Promotion in UW Ingestion

**File:** `backend/api/flow_ingestion.py`

Find the `ingest_uw_ticker_updates` function. After the existing Redis + Postgres write loop,
add a check that promotes large flow events to DARK_POOL trade idea signals.

After the loop that writes each ticker to Redis and Postgres, add this block:

```python
    # === Flow-to-Signal Promotion (Whale Hunter Replacement) ===
    # When a UW flow event exceeds the premium threshold, create a DARK_POOL
    # signal in the signals table so it appears as a trade idea card.
    promoted = 0
    for t in req.tickers:
        if not t.ticker or not t.flow_sentiment:
            continue

        premium = t.total_premium or 0
        # Configurable threshold — check Redis first, fall back to default
        try:
            threshold_raw = await redis.get("config:uw_flow:signal_threshold")
            threshold = int(threshold_raw) if threshold_raw else 1_000_000
        except Exception:
            threshold = 1_000_000  # $1M default

        if premium < threshold:
            continue

        # Check cooldown — don't re-promote same ticker+direction within 4 hours
        direction = "LONG" if t.flow_sentiment == "BULLISH" else "SHORT"
        cooldown_key = f"signal:cooldown:{t.ticker}:UW_FLOW:{direction}"
        try:
            if await redis.get(cooldown_key):
                continue
            await redis.set(cooldown_key, "1", ex=14400)  # 4 hour cooldown
        except Exception:
            pass

        # Build signal data for the unified pipeline
        premium_display = f"${premium/1_000_000:.1f}M" if premium >= 1_000_000 else f"${premium/1_000:.0f}K"
        signal_data = {
            "ticker": t.ticker,
            "strategy": "UW_FLOW",
            "direction": direction,
            "signal_type": "DARK_POOL",
            "signal_category": "DARK_POOL",
            "price": t.price or 0,
            "timeframe": "flow",
            "source": "uw_watcher",
            "metadata": {
                "total_premium": premium,
                "premium_display": premium_display,
                "flow_sentiment": t.flow_sentiment,
                "pc_ratio": t.pc_ratio,
                "put_volume": t.put_volume,
                "call_volume": t.call_volume,
                "volume": t.volume,
            },
        }

        try:
            from signals.pipeline import process_signal_unified
            import asyncio
            asyncio.ensure_future(process_signal_unified(signal_data))
            promoted += 1
            logger.info(
                f"UW flow promoted to DARK_POOL signal: {t.ticker} {direction} "
                f"({premium_display} premium)"
            )
        except Exception as e:
            logger.warning(f"Failed to promote UW flow to signal: {e}")

    return {
        "status": "success",
        "tickers_received": len(req.tickers),
        "redis_written": redis_written,
        "pg_written": pg_written,
        "signals_promoted": promoted,
        "errors": errors[:5],
    }
```

**Important:** This replaces the existing return statement at the end of the function.
Make sure the existing Redis + Postgres write loop is preserved above this block.
The promotion logic goes AFTER the existing writes, not instead of them.

---

## Change 3: Add UW_FLOW Base Score to Scorer

**File:** `backend/scoring/trade_ideas_scorer.py`

Find the `STRATEGY_BASE_SCORES` dict (or equivalent mapping of strategy names to base scores).
Add an entry for UW_FLOW:

```python
    "UW_FLOW": 55,  # Moderate base — flow alone isn't a setup, but large flow is meaningful
```

This gives UW flow signals a 55 base score. With bias alignment (up to 1.25x) and
catalyst alignment (+5 from Phase 5G), a bias-aligned $2M flow event would score
around 73-75 — enough to appear in the feed but not auto-trigger committee review
(threshold 75). This is intentional: flow is context, not a standalone trade.

If the flow ALSO has a technical signal on the same ticker (confluence from 5I),
the grouped card will show both and the confirmation bonus will push it higher.

---

## Change 4: Update Grouped Card Rendering for DARK_POOL

**File:** `frontend/app.js`

The grouped card renderer already has handling for `signal_category === 'DARK_POOL'`
from the original Whale Hunter build. Verify it renders correctly for UW_FLOW signals.

Find the card rendering section. The DARK_POOL template should show:
- Premium amount (from `metadata.premium_display`)
- Flow sentiment (BULLISH/BEARISH)
- P:C ratio if available
- "UW FLOW" as the strategy label instead of "WHALE"

If the existing DARK_POOL card template references whale-specific fields (poc, lean, rvol),
update it to handle UW_FLOW fields gracefully:

```javascript
// In the card detail rendering, check the strategy
const isUwFlow = signal.strategy === 'UW_FLOW';
const meta = typeof signal.metadata === 'string' ? JSON.parse(signal.metadata) : (signal.metadata || {});

if (category === 'DARK_POOL') {
    detailsHtml = isUwFlow
        ? `<div class="signal-details flow-details">
             <span class="flow-premium">${meta.premium_display || ''}</span>
             <span class="flow-sentiment ${(meta.flow_sentiment || '').toLowerCase()}">${meta.flow_sentiment || ''}</span>
             ${meta.pc_ratio ? `<span class="flow-pcr">P:C ${meta.pc_ratio.toFixed(2)}</span>` : ''}
           </div>`
        : `<div class="signal-details">
             <span>POC: ${signal.poc || meta.poc || '-'}</span>
             <span>Lean: ${signal.lean || meta.lean || '-'}</span>
             <span>RVOL: ${signal.rvol || meta.rvol || '-'}</span>
           </div>`;
}
```

---

## Change 5: Set Default Threshold in Redis

After deploying, set the promotion threshold via the API or directly:

```bash
# Set $1M as the default threshold (can be tuned without redeploy)
curl -s -X POST "https://pandoras-box-production.up.railway.app/api/config/set" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"key": "config:uw_flow:signal_threshold", "value": "1000000"}'
```

If no config endpoint exists, the code falls back to the hardcoded $1M default.
Nick can adjust the threshold later by setting this Redis key.

---

## Verification

1. Archive move: `docs/pinescript/archived/whale_hunter_v2.pine` exists
2. UW Watcher posts a ticker with $1M+ premium → DARK_POOL signal appears in signals table
3. Signal appears as a trade idea card with premium amount and sentiment
4. Same ticker+direction doesn't re-promote within 4 hours (cooldown)
5. Tickers below $1M premium remain in Flow tab only (not promoted)
6. Existing UW flow to Redis + Postgres still works (not broken by new code)
7. DARK_POOL cards render correctly in grouped view
8. All existing tests pass

## Commit Message

```
feat: replace Whale Hunter PineScript with UW flow-to-signal pipeline
```

## Definition of Done

- [ ] `whale_hunter_v2.pine` moved to `docs/pinescript/archived/`
- [ ] UW flow events >= $1M create DARK_POOL signals via pipeline
- [ ] 4-hour cooldown per ticker+direction prevents spam
- [ ] UW_FLOW base score of 55 added to scorer
- [ ] DARK_POOL card template handles UW_FLOW metadata
- [ ] Threshold configurable via Redis key `config:uw_flow:signal_threshold`
- [ ] Existing flow ingestion (Redis + Postgres) unchanged
- [ ] All existing tests pass

## Nick's Manual Steps (after CC deploys)

1. Delete all 32 Whale Hunter alerts in TradingView
2. Verify UW Discord Premium Bot is still posting to #uw-flow-alerts
3. Watch for DARK_POOL trade idea cards next market session
