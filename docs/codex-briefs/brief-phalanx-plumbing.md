# Brief: Phalanx (formerly Absorption Wall) — Gateway Plumbing + Strategy Doc

**Date:** March 11, 2026
**Priority:** HIGH — Strategy has NEVER generated a signal despite 10-15 active TV alerts
**Scope:** 2 files modified, 1 file created
**Estimated effort:** Small
**Dependency:** If the Artemis brief has already been applied, the strategy router anchors in Build 2 will reflect the Artemis changes. Adjust find anchors accordingly — the key change is the same either way (rename the absorption/wall route to also match phalanx).

---

## Context

Absorption Wall Detector v1.5 is being renamed to **Phalanx** (Greek phalanx — an impenetrable wall of shields absorbing enemy attacks). It detects institutional order flow absorption: two consecutive bars with matched volume, matched delta ratio, and matched buy percentage where price barely moves, indicating a large order absorbing directional pressure.

**Why zero signals exist despite active TV alerts:** The `alert.interval` AttributeError bug in the webhook dedup code was returning 500 on ALL TradingView webhooks. This was fixed on March 11, 2026. Nick's existing 10-15 Phalanx alerts (set to "Any alert() function call") should now start flowing through.

The current handler (`process_absorption_signal`) is a 20-line skeleton missing:
- `signal_category` field (should be `ORDER_FLOW`)
- Wall level caching in Redis for future confluence enrichment
- Proper base scores in the scorer (currently falls to DEFAULT: 30)
- Approved strategy doc

Phalanx is a **dual-purpose signal**: standalone ORDER_FLOW context card in Trade Ideas (like Whale Hunter's DARK_POOL cards) AND a future confluence enrichment source that boosts other signals near wall levels.

---

## Build 1 — Rename handler + add signal_category + wall level caching

**File:** `backend/webhooks/tradingview.py`

### Find (strategy router — the absorption/wall elif):

```python
        elif "absorption" in strategy_lower or "wall" in strategy_lower:
            return await process_absorption_signal(alert, start_time)
```

### Replace with:

```python
        elif "phalanx" in strategy_lower or "absorption" in strategy_lower or "wall" in strategy_lower:
            return await process_phalanx_signal(alert, start_time)
```

### Find (the entire process_absorption_signal function):

```python
async def process_absorption_signal(alert: TradingViewAlert, start_time: datetime):
    """Process Absorption Wall signals with order flow context."""
    signal_id = f"WALL_{alert.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

    direction = (alert.direction or "").upper()
    signal_type = alert.signal_type or ("BULL_WALL" if direction in ["LONG", "BUY"] else "BEAR_WALL")

    signal_data = {
        "signal_id": signal_id,
        "timestamp": alert.timestamp or datetime.now().isoformat(),
        "ticker": alert.ticker,
        "strategy": "AbsorptionWall",
        "direction": alert.direction,
        "signal_type": signal_type,
        "entry_price": alert.entry_price,
        "timeframe": alert.timeframe,
        "trade_type": "ORDER_FLOW",
        "asset_class": "CRYPTO" if is_crypto_ticker(alert.ticker) else "EQUITY",
        "status": "ACTIVE",
        "rvol": alert.rvol,
        "delta_ratio": alert.delta_ratio,
        "buy_pct": alert.buy_pct,
    }

    asyncio.ensure_future(process_signal_unified(signal_data, source="tradingview"))

    logger.info("Absorption Wall accepted: %s %s (delta=%.4f)",
                alert.ticker, signal_type,
                alert.delta_ratio if alert.delta_ratio is not None else 0)

    return {"status": "accepted", "signal_id": signal_id, "signal_type": signal_type}
```

### Replace with:

```python
async def process_phalanx_signal(alert: TradingViewAlert, start_time: datetime):
    """
    Process Phalanx (Absorption Wall) signals — institutional order flow detection.

    Detects two-bar walls where matched volume + near-zero delta indicates large
    orders absorbing directional pressure. Directional lean comes from approach:
    price falling INTO wall = bullish support, rising INTO wall = bearish resistance.

    No stop/target — this is a LEVEL IDENTIFICATION signal, not a trade generator.
    Dual purpose: standalone ORDER_FLOW card + future confluence enrichment.
    """
    signal_id = f"PHALANX_{alert.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

    direction = (alert.direction or "").upper()
    signal_type = "PHALANX_BULL" if direction in ["LONG", "BUY"] else "PHALANX_BEAR"

    # Wall level = entry_price (close at the wall zone)
    wall_level = alert.entry_price or 0

    signal_data = {
        "signal_id": signal_id,
        "timestamp": alert.timestamp or datetime.now().isoformat(),
        "ticker": alert.ticker,
        "strategy": "Phalanx",
        "direction": alert.direction,
        "signal_type": signal_type,
        "entry_price": wall_level,
        "timeframe": alert.timeframe,
        "trade_type": "ORDER_FLOW",
        "asset_class": "CRYPTO" if is_crypto_ticker(alert.ticker) else "EQUITY",
        "status": "ACTIVE",
        "signal_category": "ORDER_FLOW",
        "rvol": alert.rvol,
        "delta_ratio": alert.delta_ratio,
        "buy_pct": alert.buy_pct,
        "phalanx_wall_level": wall_level,
        "note": "Institutional absorption wall — use as confluence for nearby trade signals",
    }

    # Fire-and-forget pipeline processing
    asyncio.ensure_future(process_signal_unified(signal_data, source="tradingview"))

    # Cache wall level in Redis for confluence enrichment (4-hour TTL)
    try:
        from database.redis_client import get_redis_client
        import json as _json
        client = await get_redis_client()
        if client and wall_level > 0:
            cache_key = f"phalanx:wall:{alert.ticker.upper()}"
            cache_data = _json.dumps({
                "wall_level": wall_level,
                "direction": direction,
                "signal_type": signal_type,
                "delta_ratio": alert.delta_ratio,
                "buy_pct": alert.buy_pct,
                "rvol": alert.rvol,
                "cached_at": datetime.utcnow().isoformat() + "Z",
            })
            await client.set(cache_key, cache_data, ex=14400)  # 4-hour TTL
    except Exception as e:
        logger.warning("Phalanx wall cache failed (signal still processed): %s", e)

    logger.info(
        "\U0001f6e1 Phalanx accepted: %s %s (wall=%.2f, delta=%.4f, buy%%=%.1f%%, rvol=%.2f)",
        alert.ticker, signal_type, wall_level,
        alert.delta_ratio if alert.delta_ratio is not None else 0,
        (alert.buy_pct or 0) * 100,
        alert.rvol if alert.rvol is not None else 0,
    )

    return {"status": "accepted", "signal_id": signal_id, "signal_type": signal_type}
```

---

## Build 2 — Add Phalanx base scores to scorer

**File:** `backend/scoring/trade_ideas_scorer.py`

### Find (in STRATEGY_BASE_SCORES dict, the Whale Hunter section):

```python
    # Whale Hunter (dark pool algorithmic execution detection)
    "WHALE_LONG": 50,
    "WHALE_SHORT": 50,
    "WHALE_BULLISH": 50,
    "WHALE_BEARISH": 50,
```

### Replace with:

```python
    # Whale Hunter (dark pool algorithmic execution detection)
    "WHALE_LONG": 50,
    "WHALE_SHORT": 50,
    "WHALE_BULLISH": 50,
    "WHALE_BEARISH": 50,

    # Phalanx (absorption wall — institutional order flow)
    "PHALANX": 40,
    "PHALANX_BULL": 40,
    "PHALANX_BEAR": 40,
```

---

## Build 3 — Create approved strategy doc

**Create new file:** `docs/approved-strategies/phalanx.md`

```markdown
# Phalanx v1.5 (Absorption Wall Detector)

## Overview
Detects institutional order flow absorption: two consecutive bars with matched total volume (within 5%), matched delta ratio (within 3%), and matched buy percentage (within 3%), while price barely moves (stall < 0.30 ATR). Indicates a large order absorbing directional pressure at a specific price level.

Directional lean from approach: price falling INTO wall = bullish support (PHALANX_BULL), price rising INTO wall = bearish resistance (PHALANX_BEAR).

This is a LEVEL IDENTIFICATION signal, not a trade generator. No stop/target. Dual purpose:
1. Standalone ORDER_FLOW context card in Trade Ideas
2. Future confluence enrichment — boosts score of other signals near the wall level

## PineScript Source
`docs/pinescript/webhooks/absorption_wall_detector_v1.5.pine`

## Indicators Required
- Intrabar (1m) volume data via `request.security_lower_tf()` — TradingView only, cannot run server-side
- Volume MA (20-bar) — min 2.0x RVOL to fire
- ATR (14-period) — price stall measurement
- Approach slope (3-bar SMA of close change) — directional context

## Signal Logic

### Core Detection (Two-Bar Wall)
1. Both bars are absorption bars: near-zero delta (|delta/volume| <= 8%) + high RVOL (>= 2.0x)
2. Volume match: total volume within 5% tolerance between the two bars
3. Delta ratio match: within 3% tolerance
4. Buy percentage match: within 3% tolerance
5. Price stall: HL2 moved less than 0.30 ATR between bars
6. Bar range overlap (optional, default on): bars must overlap in price range
7. Only fires on confirmed bar close (no repaint)

### Directional Context
- **PHALANX_BULL**: 3-bar approach slope < 0 (price was falling INTO the wall = support)
- **PHALANX_BEAR**: 3-bar approach slope > 0 (price was rising INTO the wall = resistance)

### Optional Level Filter
Can restrict to only fire near manually specified price levels (disabled by default).

## Risk Management
N/A — Phalanx is a level identification signal, not a trade signal. No entry/stop/target.

## Signal Types
- `PHALANX_BULL` — bullish absorption wall (institutional support)
- `PHALANX_BEAR` — bearish absorption wall (institutional resistance)

## Signal Category
`ORDER_FLOW`

## Webhook Payload
JSON with: ticker, strategy ("AbsorptionWall" — will migrate to "Phalanx"), direction, signal_type, entry_price (close at wall), timeframe, delta_ratio, buy_pct, buy_vol, sell_vol, total_vol, rvol

## Pipeline Route
`/webhook/tradingview` → `process_phalanx_signal()` → `process_signal_unified()`

Wall level cached in Redis at `phalanx:wall:{TICKER}` with 4-hour TTL for future confluence enrichment.

## TradingView Alert Setup
- Add indicator to 15m chart (or 5m for higher frequency)
- Alert condition: **"Any alert() function call"** — NOT the named alertcondition() entries (those send pipe-delimited format that fails Pydantic validation)
- Webhook URL: `https://pandoras-box-production.up.railway.app/webhook/tradingview`
- Can use watchlist alerts to cover many tickers at once

## Applied To
15-minute charts on liquid equities and ETFs. Best on SPY, QQQ, and high-volume individual names.

## Future Enhancement
Confluence enrichment: when scoring other signals (CTA, Artemis, etc.), check Redis for nearby Phalanx wall levels. If signal entry_price is within 0.5 ATR of a cached wall AND direction matches: +10 confluence bonus. Separate brief.
```

---

## PineScript Update (Nick does manually — AFTER existing alerts start flowing)

In `absorption_wall_detector_v1.5.pine`, update the strategy field in the JSON alert payload.

### Find (near bottom of Pine, inside the `if wall and barstate.isconfirmed` block):

```pine
    alert_payload = '{"ticker":"' + syminfo.ticker +
         '","strategy":"AbsorptionWall"' +
```

### Replace with:

```pine
    alert_payload = '{"ticker":"' + syminfo.ticker +
         '","strategy":"Phalanx"' +
```

**NOTE:** This is NOT urgent. The route matches `"absorption"` so existing alerts will keep working. Update when convenient to keep analytics clean.

---

## Testing

1. After deploy, verify existing alerts flow through. Wait for market hours and check:
```sql
SELECT * FROM signals WHERE strategy = 'Phalanx' OR strategy = 'AbsorptionWall' ORDER BY created_at DESC LIMIT 10;
```

2. Or send a manual test:
```bash
curl -X POST https://pandoras-box-production.up.railway.app/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "SPY",
    "strategy": "Phalanx",
    "direction": "LONG",
    "signal_type": "BULL_WALL",
    "entry_price": 560.50,
    "timeframe": "15",
    "delta_ratio": 0.0234,
    "buy_pct": 0.5117,
    "buy_vol": 2500000,
    "sell_vol": 2400000,
    "total_vol": 4900000,
    "rvol": 2.45
  }'
```

3. Verify response contains `"signal_type": "PHALANX_BULL"`
4. Verify Redis wall cache: `GET phalanx:wall:SPY` should return JSON with wall_level

---

## What This Does NOT Change

- Whale Hunter (completely separate strategy on `/webhook/whale` — untouched)
- PineScript detection logic (no parameter changes — the Pine is well-built)
- Confluence enrichment scoring (future brief — needs wall data flowing first)

---

## Definition of Done

- [ ] Handler renamed to `process_phalanx_signal()` with signal_category and wall caching
- [ ] Route matches "phalanx", "absorption", and "wall"
- [ ] Base scores PHALANX_BULL/PHALANX_BEAR in scorer
- [ ] Approved strategy doc created
- [ ] Test webhook returns PHALANX_BULL/PHALANX_BEAR
- [ ] Existing AbsorptionWall alerts still route correctly (backward compat)
- [ ] Nick updates PineScript strategy field to "Phalanx" when convenient
