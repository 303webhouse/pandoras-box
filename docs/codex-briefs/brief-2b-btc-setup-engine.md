# Brief 2B: BTC Setup Engine + Agora Strategy Reuse

## Summary

Two-part build: (1) Add BTCUSDT.P to existing Agora TradingView alert watchlists so Holy Grail, CTA Scanner, and Exhaustion fire on BTC charts — zero backend code needed, just TV config + scoring entries. (2) Build 3 crypto-native strategies (Funding Rate Fade, Session Sweep, Liquidation Flush) that use data already flowing through the hub.

All signals land in the `signals` table with `asset_class=CRYPTO` and route to Stater Swap automatically.

## Part 1: Agora Strategy Reuse (TV + Scoring Only)

### What Nick Does (manual, not code)

In TradingView, add `BYBIT:BTCUSDT.P` to the watchlist for these PineScript alerts:
- Holy Grail Pullback
- CTA Scanner
- Exhaustion Reversal

Recommended timeframes for BTC:
- Holy Grail: 15m and 1H
- CTA Scanner: 1H and 4H
- Exhaustion: 15m and 1H

These alerts fire through the same webhook pipeline as equities. Brief 2A's ticker normalization ensures `BTCUSDT.P` → `asset_class=CRYPTO`.

### Backend: Scoring entries for BTC

The signal scoring system in `backend/scoring/` may need BTC-specific score adjustments. Check if the scorer already handles crypto tickers. If not, ensure:

- Base scores for Holy Grail / CTA / Exhaustion apply equally to crypto signals (they should — the strategies are asset-agnostic)
- Bias alignment scoring: BTC signals should NOT be checked against the equity composite bias. Either skip bias alignment for crypto or add a crypto-specific bias (future Phase 2E). For now, set bias alignment to NEUTRAL for all crypto signals so they don't get penalized or boosted by equity market conditions.

In `backend/webhooks/tradingview.py`, find where bias alignment is calculated for each strategy handler. Add a check:

```python
# Skip equity bias alignment for crypto signals
if is_crypto_ticker(alert.ticker):
    signal_data["bias_alignment"] = "NEUTRAL"
    signal_data["alignment_multiplier"] = 1.0
else:
    # existing equity bias logic
    ...
```

This prevents BTC setups from being filtered/boosted by SPY's bias direction.

## Part 2: Crypto-Native Strategies (New Code)

### Architecture

Create a new module: `backend/strategies/crypto_setups.py`

This module runs as a **scheduled job** (Railway cron or APScheduler), NOT a persistent WebSocket connection. It polls data via REST APIs and generates signals when setups are detected.

Frequency: Every 5 minutes during active sessions, every 15 minutes during quiet hours.

### Strategy 1: Funding Rate Fade

**Edge:** Extreme funding rates mean the market is overleveraged in one direction. Fading before settlement windows (00:00, 08:00, 16:00 UTC) catches the rebalancing.

**Data source:** Binance REST API `GET /fapi/v1/fundingRate` for current + historical funding rates.

**Signal logic:**
```
IF current_funding_rate > +0.03% (3x normal)
  AND time_to_next_settlement < 30 minutes
  → SHORT signal (fade the longs)

IF current_funding_rate < -0.03%
  AND time_to_next_settlement < 30 minutes
  → LONG signal (fade the shorts)

Confidence scales with how extreme the rate is:
  ±0.03-0.05% → MEDIUM confidence
  ±0.05-0.10% → HIGH confidence
  >±0.10% → VERY HIGH confidence (rare, strong signal)
```

**Risk params (Breakout-safe):**
- Stop: 0.3% from entry (tight — funding moves are small)
- Target: 0.5-1.0% (funding normalization range)
- R:R: ~2:1 minimum
- Position size: calculated against Breakout 1% max risk rule

### Strategy 2: Session Sweep Reversal

**Edge:** BTC respects session opens. Price sweeps the Asian session high/low during London/NY open, then reverses. Classic liquidity grab.

**Data source:** Binance REST API `GET /fapi/v1/klines` for session OHLC. Session windows already defined in `backend/bias_filters/btc_bottom_signals.py` (`get_btc_sessions()`).

**Signal logic:**
```
1. Track session ranges:
   - Asia: 00:00-08:00 UTC (high/low)
   - London: 08:00-13:00 UTC
   - NY: 13:00-21:00 UTC

2. At London/NY open:
   IF price sweeps ABOVE Asia high by > 0.1% THEN reverses below it
   → SHORT signal (liquidity grab above, reversal)

   IF price sweeps BELOW Asia low by > 0.1% THEN reverses above it
   → LONG signal (liquidity grab below, reversal)

3. Confirmation: reversal candle closes back inside the session range
```

**Risk params:**
- Stop: beyond the sweep high/low (the invalidation point)
- Target: opposite end of session range (measured move)
- R:R: typically 2:1 to 3:1
- Position size: Breakout 1% max risk

### Strategy 3: Liquidation Flush Reversal

**Edge:** Large liquidation cascades create sharp price dislocations. When $10M+ in longs/shorts get liquidated in a short window, the move is often exhausted and reverses.

**Data source:** Binance REST API for recent trades with `aggTrades` endpoint, filtered for large size. OR use the existing `crypto_market.py` CVD and trade flow data that's already computed.

**Signal logic:**
```
1. Monitor net liquidation flow from crypto_market.py trade data

2. IF net_sell_volume in last 5 min > $10M (large long liquidation)
   AND price dropped > 1% in that window
   AND CVD showing seller exhaustion (net selling decreasing)
   → LONG signal (flush is exhausted, bounce incoming)

3. IF net_buy_volume in last 5 min > $10M (large short squeeze)
   AND price rose > 1% in that window
   AND CVD showing buyer exhaustion
   → SHORT signal (squeeze exhausted)
```

**Risk params:**
- Stop: 0.5% beyond the flush low/high
- Target: 50% retracement of the flush move
- R:R: typically 2:1 to 4:1
- Position size: 0.5% max risk (aggressive strategy, half normal size)

### Signal Output Format

All three strategies write to the `signals` table using the existing `process_signal_unified()` function or direct DB insert:

```python
signal_data = {
    "signal_id": f"CRYPTO_{strategy}_{ticker}_{timestamp}",
    "ticker": "BTCUSDT",
    "direction": "LONG" or "SHORT",
    "strategy": "Funding_Rate_Fade" | "Session_Sweep" | "Liquidation_Flush",
    "asset_class": "CRYPTO",
    "signal_category": "CRYPTO_SETUP",
    "source": "crypto_engine",
    "score": calculated_score,  # 0-100 based on confidence
    "entry_price": entry,
    "stop_loss": stop,
    "target_1": target,
    "timeframe": "5" or "15",  # minutes
    "enrichment_data": json.dumps({
        "funding_rate": ...,
        "session": ...,
        "liquidation_volume": ...,
        # strategy-specific context
    }),
}
```

### Breakout Risk Model

Port the position sizing logic from `crypto-scalper/backend/risk/position_manager.py` into the new module. Key calculations:

```python
def calculate_breakout_position(
    account_balance: float,  # $25,000
    entry_price: float,
    stop_price: float,
    max_risk_pct: float = 0.01,  # 1% of account
    max_daily_loss_pct: float = 0.04,  # 4% daily limit
    static_drawdown_pct: float = 0.06,  # 6% static drawdown
) -> dict:
    risk_per_trade = account_balance * max_risk_pct  # $250
    stop_distance = abs(entry_price - stop_price)
    stop_pct = stop_distance / entry_price

    # Position size in BTC
    position_size_btc = risk_per_trade / stop_distance

    # Contract value (BTC perp = 1 BTC per contract on most exchanges)
    contracts = position_size_btc

    # Leverage check (keep conservative for eval)
    notional = position_size_btc * entry_price
    leverage = notional / account_balance

    return {
        "contracts": round(contracts, 4),
        "risk_usd": round(risk_per_trade, 2),
        "risk_pct": round(max_risk_pct * 100, 2),
        "leverage": round(leverage, 2),
        "notional_usd": round(notional, 2),
        "stop_distance_pct": round(stop_pct * 100, 3),
        "safe": leverage <= 3.0,  # flag if leverage too high
    }
```

Include this in every crypto signal's `enrichment_data` so Stater Swap can display position sizing.

### Scheduler Setup

Add the crypto setup engine to the Railway scheduler (`backend/scheduler/`) or as a standalone cron-triggered script:

```python
# Run every 5 minutes during active sessions
# Active sessions: always (crypto is 24/7) but frequency can vary
# Peak: London+NY overlap (13:00-17:00 UTC) → every 3 min
# Normal: all other hours → every 5 min
# Quiet: weekends → every 15 min (crypto trades weekends but lower vol)
```

The scheduler should:
1. Fetch current BTC price, funding rate, session data
2. Run all 3 strategy checks
3. If any setup detected, write to signals table
4. Dedup: don't fire the same setup type within 30 minutes

### Binance API Integration

The hub already has `crypto_market.py` fetching from Binance. Reuse the same HTTP client pattern. Key endpoints needed:

```
GET https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1
GET https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=100
GET https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=BTCUSDT
```

No API key needed for these public endpoints. Rate limit: 1200 requests/minute (we'll use ~20/cycle).

**Geo-restriction note:** `crypto_market.py` already handles Binance geo-restrictions with fallback logic. Reuse the same `_fetch_json()` helper and fallback patterns.

## Out of Scope

- Multi-coin support (BTC only for now)
- WebSocket real-time data (REST polling is sufficient for 5-min cycles)
- Committee review for crypto signals (too slow for scalping)
- Discord delivery (Phase 2C)
- Exchange execution integration (signals are manual execution only)

## File Structure

```
backend/
  strategies/
    crypto_setups.py          # NEW — 3 strategies + scheduler entry point
  integrations/
    binance_futures.py        # NEW — Binance futures REST client (funding, klines)
```

## Testing

1. Send a test webhook with `ticker: "BTCUSDT.P"` → verify it appears in Stater Swap (not Agora)
2. Run crypto_setups.py manually → verify it fetches data without errors
3. Mock extreme funding rate → verify Funding Rate Fade signal generated
4. Verify position sizing returns sane values for $25K account
5. Verify dedup: same strategy doesn't fire twice within 30 min window
6. Existing 154+ tests still pass

## Definition of Done

- [ ] BTCUSDT.P Holy Grail / CTA / Exhaustion alerts flow to Stater Swap with `asset_class=CRYPTO`
- [ ] Crypto signals get `bias_alignment=NEUTRAL` (skip equity bias)
- [ ] `crypto_setups.py` with Funding Rate Fade, Session Sweep, Liquidation Flush
- [ ] `binance_futures.py` REST client for funding rates and klines
- [ ] Breakout position sizing in every crypto signal's enrichment_data
- [ ] Scheduler runs every 5 minutes
- [ ] Signal dedup (30-min cooldown per strategy)
- [ ] All existing tests pass
