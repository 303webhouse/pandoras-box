# Brief: Artemis (formerly Hub Sniper) — Gateway Plumbing Fix

**Date:** March 11, 2026
**Priority:** HIGH — Strategy is effectively non-functional until this is done
**Scope:** 3 files modified, 1 file renamed
**Estimated effort:** Small (no new files, no schema changes)

---

## Context

Hub Sniper v2.1 is being renamed to **Artemis** (Greek mythology theme, goddess of the hunt — fits the precision VWAP band strategy). It's a VWAP band mean-reversion strategy on 15m charts that fires webhooks from TradingView PineScript.

Currently it routes through `process_sniper_signal()` — the same handler as the old Ursa/Taurus Sniper strategy. This causes:
1. Shared dedup keys (Artemis and old Sniper signals on same ticker can collide)
2. Analytics can't distinguish the two strategies
3. Unique Artemis fields (`mode`, `avwap_ctx`, `prox_atr`) get silently dropped by the Pydantic model
4. Scoring treats it as a generic Sniper (base score 40) instead of recognizing VWAP mean-reversion context

---

## Build 1 — Add Artemis fields to Pydantic model

**File:** `backend/webhooks/tradingview.py`

### Find (TradingViewAlert model, after the Absorption Wall fields block):

```python
    # Absorption Wall fields (order flow data)
    signal_type: Optional[str] = None
    delta_ratio: Optional[float] = None
    buy_pct: Optional[float] = None
    buy_vol: Optional[float] = None
    sell_vol: Optional[float] = None
    total_vol: Optional[float] = None
    secret: Optional[str] = None
```

### Replace with:

```python
    # Absorption Wall fields (order flow data)
    signal_type: Optional[str] = None
    delta_ratio: Optional[float] = None
    buy_pct: Optional[float] = None
    buy_vol: Optional[float] = None
    sell_vol: Optional[float] = None
    total_vol: Optional[float] = None
    # Artemis (VWAP mean reversion) fields
    mode: Optional[str] = None          # "Normal" or "Flush"
    avwap_ctx: Optional[str] = None     # Weekly AVWAP context ("above"/"below")
    avwap_buf_atr: Optional[float] = None  # AVWAP buffer in ATR units
    prox_atr: Optional[float] = None    # Proximity to VWAP band in ATR units
    adx_rising: Optional[bool] = None   # ADX direction
    secret: Optional[str] = None
```

---

## Build 2 — Add Artemis route + dedicated handler

**File:** `backend/webhooks/tradingview.py`

### Find (strategy router in receive_tradingview_alert, the elif chain):

```python
        if "scout" in strategy_lower:
            return await process_scout_signal(alert, start_time)
        elif "holy_grail" in strategy_lower or "holygrail" in strategy_lower:
            return await process_holy_grail_signal(alert, start_time)
        elif "exhaustion" in strategy_lower:
            return await process_exhaustion_signal(alert, start_time)
        elif "sniper" in strategy_lower:
            return await process_sniper_signal(alert, start_time)
        elif "absorption" in strategy_lower or "wall" in strategy_lower:
            return await process_absorption_signal(alert, start_time)
```

### Replace with:

```python
        if "scout" in strategy_lower:
            return await process_scout_signal(alert, start_time)
        elif "holy_grail" in strategy_lower or "holygrail" in strategy_lower:
            return await process_holy_grail_signal(alert, start_time)
        elif "exhaustion" in strategy_lower:
            return await process_exhaustion_signal(alert, start_time)
        elif "artemis" in strategy_lower or "hub_sniper" in strategy_lower or "hubsniper" in strategy_lower:
            return await process_artemis_signal(alert, start_time)
        elif "sniper" in strategy_lower:
            return await process_sniper_signal(alert, start_time)
        elif "absorption" in strategy_lower or "wall" in strategy_lower:
            return await process_absorption_signal(alert, start_time)
```

**IMPORTANT:** The Artemis route MUST come before the generic "sniper" route, otherwise `"hub_sniper"` would match on `"sniper"` first.

### Add new handler (place immediately after `process_absorption_signal` and before `process_generic_signal`):

```python
async def process_artemis_signal(alert: TradingViewAlert, start_time: datetime):
    """
    Process Artemis (VWAP Band Mean Reversion) signals.
    
    Two modes:
    - Normal: trend + confirmation candle at VWAP band (VAH/VAL)
    - Flush: exhaustion reversal after 3%+ move into VWAP band
    
    Unique fields: mode, avwap_ctx, prox_atr (proximity to band in ATR units)
    """
    # Calculate risk/reward
    rr = calculate_risk_reward(alert)
    
    # Determine signal type
    direction = (alert.direction or "").upper()
    mode = (alert.mode or "Normal").capitalize()
    
    if direction in ["LONG", "BUY"]:
        signal_type = "ARTEMIS_LONG"
    else:
        signal_type = "ARTEMIS_SHORT"
    
    # Build signal data with Artemis-specific context
    signal_id = f"ARTEMIS_{alert.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    
    signal_data = {
        "signal_id": signal_id,
        "timestamp": alert.timestamp or datetime.now().isoformat(),
        "ticker": alert.ticker,
        "strategy": "Artemis",
        "direction": alert.direction,
        "signal_type": signal_type,
        "entry_price": alert.entry_price,
        "stop_loss": alert.stop_loss,
        "target_1": alert.target_1,
        "target_2": alert.target_2,
        "risk_reward": rr["primary"],
        "risk_reward_t1": rr["t1_rr"],
        "risk_reward_t2": rr["t2_rr"],
        "timeframe": alert.timeframe,
        "trade_type": "MEAN_REVERSION",
        "asset_class": "CRYPTO" if is_crypto_ticker(alert.ticker) else "EQUITY",
        "status": "ACTIVE",
        "rsi": alert.rsi,
        "adx": alert.adx,
        "rvol": alert.rvol,
        # Artemis-specific fields for scoring enrichment
        "artemis_mode": mode,
        "avwap_ctx": alert.avwap_ctx,
        "prox_atr": alert.prox_atr,
        "adx_rising": alert.adx_rising,
    }
    
    # Fire-and-forget: return 200 immediately, process in background
    asyncio.ensure_future(process_signal_unified(signal_data, source="tradingview"))

    logger.info(
        "🏹 Artemis accepted: %s %s (%s mode, prox=%.2f ATR, avwap=%s)",
        alert.ticker, signal_type, mode,
        alert.prox_atr if alert.prox_atr is not None else 0,
        alert.avwap_ctx or "unknown",
    )

    return {
        "status": "accepted",
        "signal_id": signal_id,
        "signal_type": signal_type,
        "mode": mode,
    }
```

---

## Build 3 — Add Artemis base scores to scorer

**File:** `backend/scoring/trade_ideas_scorer.py`

### Find (in STRATEGY_BASE_SCORES dict, the Sniper section):

```python
    # Sniper signals
    "SNIPER": 40,
    "SNIPER_URSA": 40,
    "SNIPER_TAURUS": 40,
```

### Replace with:

```python
    # Sniper signals (legacy Ursa/Taurus continuation)
    "SNIPER": 40,
    "SNIPER_URSA": 40,
    "SNIPER_TAURUS": 40,

    # Artemis (VWAP band mean reversion)
    "ARTEMIS": 45,
    "ARTEMIS_LONG": 45,
    "ARTEMIS_SHORT": 45,
```

---

## Build 4 — Rename strategy doc

**Rename:** `docs/approved-strategies/hub-sniper.md` → `docs/approved-strategies/artemis.md`

Update the title line inside the file:
- Old: `# Hub Sniper v2.1 (VWAP Band Mean Reversion)`
- New: `# Artemis v2.1 (VWAP Band Mean Reversion)`

Update the pipeline route line:
- Old: `` `/webhook/tradingview` → `process_sniper_signal()` → `process_signal_unified()` ``
- New: `` `/webhook/tradingview` → `process_artemis_signal()` → `process_signal_unified()` ``

Update the signal types section:
- Old: `` `BULLISH_TRADE` — long signal (can upgrade to `APIS_CALL` at score ≥ 85) ``
- New: `` `ARTEMIS_LONG` — long signal (can upgrade to `APIS_CALL` at score ≥ 85) ``
- Old: `` `BEAR_CALL` — short signal (can upgrade to `KODIAK_CALL` at score ≥ 85) ``  
- New: `` `ARTEMIS_SHORT` — short signal (can upgrade to `KODIAK_CALL` at score ≥ 85) ``

---

## TradingView PineScript Update (Nick does manually)

In the Hub Sniper PineScript alert JSON, change the `strategy` field:
- Old: `"strategy": "Sniper"`
- New: `"strategy": "Artemis"`

This is the ONLY PineScript change needed. All other fields stay the same.

---

## Testing

1. After deploy, send test webhook:
```bash
curl -X POST https://pandoras-box-production.up.railway.app/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "SPY",
    "strategy": "Artemis",
    "direction": "LONG",
    "entry_price": 560.50,
    "stop_loss": 558.00,
    "target_1": 564.25,
    "target_2": 567.00,
    "timeframe": "15",
    "rsi": 35,
    "adx": 22,
    "rvol": 1.4,
    "mode": "Normal",
    "avwap_ctx": "above",
    "prox_atr": 0.3,
    "secret": "<WEBHOOK_SECRET>"
  }'
```

2. Verify response contains `"signal_type": "ARTEMIS_LONG"` and `"mode": "Normal"`
3. Check signals table: `SELECT * FROM signals WHERE strategy = 'Artemis' ORDER BY created_at DESC LIMIT 5;`
4. Verify old Sniper signals still route correctly (strategy="Sniper" should NOT match Artemis route)

---

## What This Does NOT Change

- Scout Sniper (completely separate strategy, `"scout"` route — untouched)
- Old Ursa/Taurus Sniper (still routes through `process_sniper_signal()`)
- PineScript parameters (no loosening yet — that's a separate future change after baseline measurement)
- Scoring bonuses for Artemis-specific fields like proximity and flush mode (future enhancement, separate brief)

---

## Definition of Done

- [ ] Artemis fields on Pydantic model
- [ ] Dedicated route + handler for Artemis
- [ ] Base scores in scorer
- [ ] Strategy doc renamed
- [ ] Test webhook returns ARTEMIS_LONG/ARTEMIS_SHORT
- [ ] Old Sniper route still works for legacy signals
- [ ] Nick updates PineScript strategy field to "Artemis"
