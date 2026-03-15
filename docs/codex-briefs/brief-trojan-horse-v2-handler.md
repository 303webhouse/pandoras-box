# Brief: Trojan Horse v2 — Footprint Handler Update

**Date:** March 15, 2026
**Priority:** LOW — Enhancement, not a fix. Signals already flow without this.
**Scope:** 1 file modified (`backend/webhooks/footprint.py`)
**Estimated effort:** Tiny (3 surgical edits)
**Depends on:** Nothing — v2 PineScript already deployed to TradingView

---

## Context

Trojan Horse v2 PineScript (`docs/pinescript/webhooks/trojan_horse_footprint_v2.pine`) removed the noisy absorption signals and added three new quality-gate fields to the webhook payload:

- `density_pct` — percentage of all footprint rows showing imbalances (higher = more conviction)
- `zone_coverage_pct` — stacked imbalance zone as % of bar range (higher = more significant)
- `vol_ratio` — bar volume vs 20-bar SMA (higher = more reliable)

The `FootprintSignal` Pydantic model has `model_config = {"extra": "allow"}` so these fields are accepted without errors, but they aren't persisted to Redis cache or pipeline metadata. This brief wires them through.

Also cleans up dead references to the removed absorption signal types.

---

## Build 1 — Add v2 fields to Pydantic model explicitly

**File:** `backend/webhooks/footprint.py`

### Find:

```python
class FootprintSignal(BaseModel):
    signal: str = "FOOTPRINT"
    ticker: str
    tf: Optional[str] = None
    sub_type: Optional[str] = None
    direction: Optional[str] = None
    price: Optional[float] = None
    stacked_layers: Optional[int] = None
    buy_imb_count: Optional[int] = None
    sell_imb_count: Optional[int] = None
    secret: Optional[str] = None

    model_config = {"extra": "allow"}
```

### Replace with:

```python
class FootprintSignal(BaseModel):
    signal: str = "FOOTPRINT"
    ticker: str
    tf: Optional[str] = None
    sub_type: Optional[str] = None
    direction: Optional[str] = None
    price: Optional[float] = None
    stacked_layers: Optional[int] = None
    buy_imb_count: Optional[int] = None
    sell_imb_count: Optional[int] = None
    # v2 quality-gate fields
    density_pct: Optional[float] = None      # % of rows with imbalances
    zone_coverage_pct: Optional[float] = None # stacked zone as % of bar range
    vol_ratio: Optional[float] = None         # bar volume vs 20-SMA
    secret: Optional[str] = None

    model_config = {"extra": "allow"}
```

---

## Build 2 — Add v2 fields to Redis cache

### Find (inside `footprint_webhook`, the `cache_data` dict):

```python
            cache_data = {
                "ticker": data.ticker.upper(),
                "sub_type": data.sub_type,
                "direction": data.direction,
                "price": data.price,
                "stacked_layers": data.stacked_layers,
                "buy_imb_count": data.buy_imb_count,
                "sell_imb_count": data.sell_imb_count,
                "tf": data.tf,
                "cached_at": datetime.utcnow().isoformat() + "Z",
            }
```

### Replace with:

```python
            cache_data = {
                "ticker": data.ticker.upper(),
                "sub_type": data.sub_type,
                "direction": data.direction,
                "price": data.price,
                "stacked_layers": data.stacked_layers,
                "buy_imb_count": data.buy_imb_count,
                "sell_imb_count": data.sell_imb_count,
                "density_pct": data.density_pct,
                "zone_coverage_pct": data.zone_coverage_pct,
                "vol_ratio": data.vol_ratio,
                "tf": data.tf,
                "cached_at": datetime.utcnow().isoformat() + "Z",
            }
```

---

## Build 3 — Add v2 fields to pipeline metadata

### Find (inside `footprint_webhook`, the `signal_data` metadata dict):

```python
                "metadata": {
                    "sub_type": data.sub_type,
                    "stacked_layers": data.stacked_layers,
                    "buy_imb_count": data.buy_imb_count,
                    "sell_imb_count": data.sell_imb_count,
                },
```

### Replace with:

```python
                "metadata": {
                    "sub_type": data.sub_type,
                    "stacked_layers": data.stacked_layers,
                    "buy_imb_count": data.buy_imb_count,
                    "sell_imb_count": data.sell_imb_count,
                    "density_pct": data.density_pct,
                    "zone_coverage_pct": data.zone_coverage_pct,
                    "vol_ratio": data.vol_ratio,
                },
```

---

## Build 4 — Clean up dead absorption references

### Find (the `_sub_type_display` function):

```python
def _sub_type_display(sub_type: Optional[str]) -> str:
    return {
        "stacked_buy": "Stacked Buy Imbalance",
        "stacked_sell": "Stacked Sell Imbalance",
        "buy_absorption": "Buy Absorption",
        "sell_absorption": "Sell Absorption",
    }.get(sub_type or "", sub_type or "Unknown")
```

### Replace with:

```python
def _sub_type_display(sub_type: Optional[str]) -> str:
    return {
        "stacked_buy": "Stacked Buy Imbalance",
        "stacked_sell": "Stacked Sell Imbalance",
    }.get(sub_type or "", sub_type or "Unknown")
```

### Find (in the module docstring payload schema, the sub_type comment):

```python
  "sub_type":        "stacked_buy",    // stacked_buy, stacked_sell, buy_absorption, sell_absorption
```

### Replace with:

```python
  "sub_type":        "stacked_buy",    // stacked_buy, stacked_sell
```

---

## Testing

1. Deploy and wait for next Trojan Horse signal during market hours
2. Check Railway logs for `Footprint signal received:` — confirm it still processes
3. Check Redis: `GET footprint:recent:SPY` — confirm `density_pct`, `zone_coverage_pct`, `vol_ratio` appear in cached JSON
4. Check signals table: confirm metadata column includes the three new fields

## Future Consideration

Once Trojan Horse accumulates enough signal data, add `FOOTPRINT_LONG` and `FOOTPRINT_SHORT` to `STRATEGY_BASE_SCORES` in the scorer (currently falls to DEFAULT: 30) and add v2 fields as scoring modifiers — same pattern as the Artemis `prox_atr` extension boost.
