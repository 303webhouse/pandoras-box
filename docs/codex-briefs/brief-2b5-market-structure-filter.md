# Brief 2B.5: BTC Market Structure Scoring Filter

## Summary

Add a market structure scoring layer to the crypto setup engine. Three components — Volume Profile, CVD Gate, and Orderbook Imbalance — each modify a crypto signal's confidence score by ±10-20 points based on whether the setup location and order flow context support the trade.

This is a **scoring modifier**, not a new strategy. The existing strategies (Holy Grail, Funding Rate Fade, Session Sweep, Liquidation Flush) remain the triggers. This layer tells them whether the market structure context makes the trigger worth taking.

## Why This Matters

Price-based signals (like Holy Grail's EMA pullback) don't know where volume traded. A pullback to the 20 EMA at a high-volume node (POC) is a high-probability bounce. The same pullback in a low-volume gap is likely to slice through. Without volume profile context, every signal is equally confident regardless of location.

Successful crypto traders use TPO/volume profile/order flow as the roadmap and price triggers as the entry. We're adding the roadmap.

## Architecture

New module: `backend/strategies/btc_market_structure.py`

Single entry point function called by the setup engine before finalizing any crypto signal's score:

```python
async def get_market_structure_context(ticker: str, entry_price: float, direction: str) -> dict:
    """
    Evaluate market structure context for a crypto signal.
    Returns scoring modifiers and context data.

    Args:
        ticker: e.g. "BTCUSDT"
        entry_price: proposed entry price
        direction: "LONG" or "SHORT"

    Returns:
        {
            "score_modifier": int,  # -20 to +20, added to signal score
            "context_label": str,   # "STRONG", "NEUTRAL", "WEAK"
            "volume_profile": {...},
            "cvd": {...},
            "orderbook": {...},
            "reasoning": str,  # Human-readable explanation
        }
    """
```

## Component 1: Volume Profile (from Klines)

### Data Source
Binance klines — already fetched by `binance_futures.py` (`get_klines()`). Use 1H klines from the last 24 hours for intraday profile, and 4H klines from the last 7 days for a swing profile.

### What to Compute

```python
def compute_volume_profile(klines: list, num_bins: int = 50) -> dict:
    """
    Build volume-at-price histogram from OHLCV klines.

    For each kline, distribute its volume across the price range (high-low)
    proportionally. Then bin all volume into price buckets.

    Returns:
        {
            "poc": float,           # Point of Control — highest volume price level
            "vah": float,           # Value Area High (70% of volume above/below POC)
            "val": float,           # Value Area Low
            "hv_nodes": [float],    # High Volume Nodes (top 20% by volume)
            "lv_gaps": [(low, high)],  # Low Volume Gaps (bottom 20% by volume)
            "profile": [(price, volume)],  # Full histogram for display
        }
    """
```

**Volume distribution method:** For each kline, assume volume is distributed uniformly between the low and high of that candle. This is a standard approximation when tick data isn't available. Assign volume to each price bin that falls within [low, high] proportionally.

**Value Area calculation:** Starting from POC, expand up and down alternately, adding the higher-volume side first, until 70% of total volume is captured. The boundaries are VAH and VAL.

### Scoring Logic

```
Entry at/near POC (within 0.3%):  +10 points (high volume = strong support/resistance)
Entry inside Value Area:          +5 points  (normal range, fair value)
Entry at HV node (not POC):       +8 points  (secondary support/resistance)
Entry in LV gap:                  -10 points (price moves fast through gaps, risky)
Entry outside Value Area:         -5 points  (extended, higher risk of reversion)
```

For LONG signals, proximity to VAL/POC from below is bullish. For SHORT signals, proximity to VAH/POC from above is bearish.

### Cache
Volume profile changes slowly. Cache the 24H profile for 15 minutes and the 7D profile for 1 hour. Store in module-level dict with timestamp.

## Component 2: CVD Gate (Already Computed)

### Data Source
`crypto_market.py` already computes CVD (Cumulative Volume Delta) in its market snapshot. The `get_market_snapshot()` function returns `cvd_analysis` with net buy/sell pressure.

Call the existing endpoint: `GET /api/crypto/market?symbol=BTCUSDT`

Relevant fields from the response:
- `cvd_analysis.net_volume_usd` — positive = net buying, negative = net selling
- `cvd_analysis.buy_ratio` — percentage of volume that's buy-side
- `cvd_analysis.direction` — "BULLISH", "BEARISH", or "NEUTRAL"

### Scoring Logic

```
CVD confirms signal direction:     +10 points
  (LONG signal + BULLISH CVD, or SHORT signal + BEARISH CVD)

CVD neutral:                        0 points
  (CVD direction is NEUTRAL)

CVD diverges from signal:          -15 points
  (LONG signal + BEARISH CVD, or SHORT signal + BULLISH CVD)
  This is a strong warning — flow disagrees with the setup.
```

### Cache
CVD is real-time data. Cache for 60 seconds max (the crypto market endpoint already has a short TTL cache).

## Component 3: Orderbook Imbalance

### Data Source
Binance Futures orderbook depth. New function in `binance_futures.py`:

```python
async def get_orderbook_depth(symbol: str = "BTCUSDT", limit: int = 20) -> dict:
    """
    Fetch orderbook depth from Binance Futures.
    GET https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=20

    Returns:
        {
            "bids": [[price, qty], ...],  # Buy orders (descending price)
            "asks": [[price, qty], ...],  # Sell orders (ascending price)
        }
    """
```

No API key needed. Rate limit friendly (1 request per cycle).

### What to Compute

```python
def compute_orderbook_imbalance(orderbook: dict, current_price: float) -> dict:
    """
    Calculate bid/ask imbalance within 0.5% of current price.

    Returns:
        {
            "bid_volume_usd": float,   # Total bid $ within range
            "ask_volume_usd": float,   # Total ask $ within range
            "imbalance_ratio": float,  # bid/ask ratio (>1 = bid heavy, <1 = ask heavy)
            "direction": str,          # "BID_HEAVY", "ASK_HEAVY", "BALANCED"
            "nearest_wall": {          # Largest single order within 1%
                "side": "BID" or "ASK",
                "price": float,
                "size_usd": float,
            }
        }
    """
```

Imbalance ratio thresholds:
- `> 1.5` = BID_HEAVY (more buyers stacked)
- `< 0.67` = ASK_HEAVY (more sellers stacked)
- Between = BALANCED

### Scoring Logic

```
Book supports signal direction:    +5 points
  (LONG + BID_HEAVY, or SHORT + ASK_HEAVY)

Book is balanced:                   0 points

Book opposes signal direction:     -10 points
  (LONG + ASK_HEAVY, or SHORT + BID_HEAVY)

Large wall supporting signal:      +5 bonus points
  (wall > $1M on the signal's side within 0.5% of entry)

Large wall opposing signal:        -5 penalty
  (wall > $1M against the signal within 0.5% of entry)
```

### Cache
Orderbook is highly dynamic. Cache for 30 seconds.

## Integration Point

In `backend/strategies/crypto_setups.py`, after a strategy generates a signal but BEFORE calling `process_signal_unified()`, call the market structure filter:

```python
from strategies.btc_market_structure import get_market_structure_context

# After signal is generated...
structure = await get_market_structure_context(
    ticker="BTCUSDT",
    entry_price=signal_data["entry_price"],
    direction=signal_data["direction"]
)

# Apply score modifier
signal_data["score"] = max(0, min(100, signal_data["score"] + structure["score_modifier"]))

# Attach context for display in Stater Swap
signal_data["enrichment_data"]["market_structure"] = {
    "context_label": structure["context_label"],
    "score_modifier": structure["score_modifier"],
    "reasoning": structure["reasoning"],
    "poc": structure["volume_profile"]["poc"],
    "vah": structure["volume_profile"]["vah"],
    "val": structure["volume_profile"]["val"],
    "cvd_direction": structure["cvd"]["direction"],
    "book_imbalance": structure["orderbook"]["imbalance_ratio"],
}
```

Also apply the same filter to BTC signals from TradingView (Holy Grail) webhooks. In `backend/webhooks/tradingview.py`, after building signal_data for crypto tickers and before calling `process_signal_unified()`, run the same market structure check.

## Score Modifier Ranges

The three components combined can modify a signal's score from -45 to +35:

| Component | Min | Max |
|-----------|-----|-----|
| Volume Profile | -10 | +10 |
| CVD Gate | -15 | +10 |
| Orderbook Imbalance | -15 | +10 |
| Wall bonus/penalty | -5 | +5 |
| **Total range** | **-45** | **+35** |

This means:
- A Funding Rate Fade (base score ~60) at POC with confirming CVD and supportive book → 60 + 25 = **85** (high confidence)
- Same signal in a low-volume gap with diverging CVD and opposing book → 60 - 35 = **25** (effectively filtered out)

## Context Labels

Compute an overall label from the combined modifier:

```python
if total_modifier >= 15:
    label = "STRONG"   # Market structure strongly supports this setup
elif total_modifier >= 0:
    label = "NEUTRAL"  # No strong opinion from structure
elif total_modifier >= -15:
    label = "WEAK"     # Structure is lukewarm, trade with caution
else:
    label = "AVOID"    # Structure actively disagrees, consider skipping
```

The label gets displayed in Stater Swap signal cards so Nick can see at a glance whether market structure supports the trade.

## Error Handling

If any component fails to fetch data (Binance down, geo-blocked, timeout):
- Return 0 for that component's modifier
- Set that component's data to `{"error": "reason"}`
- Still return a result — don't block the signal

The market structure filter is informational and should never prevent a signal from being generated. It modifies confidence, it doesn't gate entry.

## Out of Scope

- **TPO (Time Price Opportunity)** — requires 30-min brackets across weeks of data. Future enhancement.
- **Footprint charts** — need tick-level data. Not available via public APIs.
- **Per-level delta** — computing buy/sell volume at each price level (beyond aggregate CVD). Would require trade-by-trade analysis. Possible future enhancement.
- **Frontend display of volume profile** — showing the actual histogram in Stater Swap. Nice to have but not needed for the scoring layer to work. Can be added later.

## File Structure

```
backend/
  strategies/
    btc_market_structure.py   # NEW — volume profile + CVD gate + orderbook imbalance
  integrations/
    binance_futures.py        # MODIFY — add get_orderbook_depth()
  strategies/
    crypto_setups.py          # MODIFY — call market structure filter before signal output
  webhooks/
    tradingview.py            # MODIFY — call market structure filter for crypto HG signals
```

## Testing

1. Call `compute_volume_profile()` with real kline data → verify POC/VAH/VAL are sane (POC should be near the most-traded price level)
2. Call `get_market_structure_context()` with current BTC price → verify all three components return data
3. Mock a signal at the POC → verify positive score modifier
4. Mock a signal in a low-volume gap with diverging CVD → verify strong negative modifier
5. Simulate Binance API failure → verify graceful fallback (0 modifier, no crash)
6. Verify crypto signals now include `market_structure` in enrichment_data
7. All existing 168+ tests still pass

## Definition of Done

- [ ] `btc_market_structure.py` with volume profile, CVD gate, orderbook imbalance
- [ ] `get_orderbook_depth()` added to `binance_futures.py`
- [ ] `compute_volume_profile()` builds POC/VAH/VAL from klines
- [ ] `compute_orderbook_imbalance()` computes bid/ask ratio and wall detection
- [ ] Setup engine calls market structure filter before `process_signal_unified()`
- [ ] TradingView crypto signals also get market structure scoring
- [ ] Score modifiers applied (combined range -45 to +35)
- [ ] Context label (STRONG/NEUTRAL/WEAK/AVOID) in enrichment_data
- [ ] Caching: volume profile 15min, CVD 60s, orderbook 30s
- [ ] Graceful error handling (component failure = 0 modifier, not crash)
- [ ] All existing tests pass
