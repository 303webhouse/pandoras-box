# Brief: Fix Committee Data Access — Bias, Positions, Prices, UW Flow

**Priority:** CRITICAL — The committee is making decisions blind. Bias URL is wrong, positions may not render, prices are stale.
**Target:** VPS (`/opt/openclaw/workspace/scripts/pivot2_committee.py` + `committee_context.py`)
**Estimated time:** 2-3 hours
**Source:** PLTR trade review revealed committee had no market bias context, wrong positions, and stale prices

---

## Problem Summary

The Trading Committee agents should have access to all live data in the hub. Currently they're missing critical context:

| Data Source | Status | Impact |
|---|---|---|
| Composite bias score | ❌ WRONG URL | Committee has zero market regime context |
| Timeframe sub-scores | ❌ WRONG URL | No intraday/swing/macro breakdown |
| Current positions | ❓ Code exists but may be bypassed | Committee doesn't know what Nick already holds |
| Live prices (equities) | ✅ Works via yfinance | OK for stocks |
| Live prices (crypto) | ❌ yfinance unreliable | BTC prices off by $20K+ |
| UW flow data | ❓ Functions exist, endpoints unverified | Committee can't see institutional flow |
| Twitter sentiment | ✅ Works from JSONL | OK |
| News context | ✅ Works via Polygon | OK |

## Fix 1 (CRITICAL): Bias Endpoint URL

The committee calls `/bias/composite` but the correct Railway path is `/api/bias/composite`.

**In `pivot2_committee.py`, find (around line 620):**
```python
        composite = http_json(url=f"{base}/bias/composite", headers=headers, timeout=30)
```

**Replace with:**
```python
        composite = http_json(url=f"{base}/api/bias/composite", headers=headers, timeout=30)
```

**Also find the timeframes endpoint (around line 655):**
```python
        tf_data = http_json(url=f"{base}/bias/composite/timeframes", headers=headers, timeout=30)
```

**Replace with:**
```python
        tf_data = http_json(url=f"{base}/api/bias/composite/timeframes", headers=headers, timeout=30)
```

**Verify by running manually:**
```bash
curl -s "https://pandoras-box-production.up.railway.app/api/bias/composite" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('bias_level'), d.get('composite_score'))"
```
Expected: `URSA_MINOR -0.37` (or current bias)

## Fix 2: Verify Portfolio Data Reaches Agents

The file header says "Position data removed" but the fetch/format functions exist. Check these:

1. `fetch_portfolio_context(api_url)` is called in `build_market_context()` — verify the URL is correct:
```python
# Check if it's using /api/portfolio/balances or /portfolio/balances
# The correct URL has the /api prefix
req = urllib.request.Request(f"{base}/api/portfolio/balances")
req = urllib.request.Request(f"{base}/api/portfolio/positions")
```

2. `format_portfolio_context(portfolio)` is called in `run_committee()` and appended to `base_context` — verify this code path executes (add a log line).

3. Update the file header comment (line 7) from "Position data removed" to "Position data included via portfolio context."

**Test the full chain:**
```python
from committee_context import fetch_portfolio_context, format_portfolio_context
p = fetch_portfolio_context("https://pandoras-box-production.up.railway.app")
print(format_portfolio_context(p))
```
This should print a formatted block showing account balances and open positions.

## Fix 3: Verify UW Flow Data Reaches Agents

The context builder has `build_uw_flow_context()` and `build_market_flow_context()`. Check:

1. What Railway endpoint do they call? Verify it exists.
2. Does the UW Watcher write data to a Redis key or Railway endpoint that the context builder can read?
3. If the endpoints don't exist, the UW data needs to be pulled from Redis directly or via a new Railway endpoint.

**The UW Watcher (running on VPS) captures flow to Redis with 1h TTL.** The committee context builder runs on VPS too, so it could read Redis directly instead of going through Railway.

**Check Redis for UW data:**
```bash
# From VPS
redis-cli -u $REDIS_URL KEYS "uw:*" | head -10
```

## Fix 4: Add Bias Detail to Agent Context

The current `format_signal_context()` only shows:
```
Bias: URSA_MINOR
Composite Score: -0.37
Confidence: HIGH
DEFCON: ...
```

This is too terse. The agents need to see:
- Which timeframe tier is driving the bias (intraday bearish, swing neutral, macro neutral)
- Key factor readings: VIX level, GEX sign, SPY vs 50/200 SMA distance
- Circuit breaker status and trigger
- Active factor count and any stale factors

**Enhance the MARKET REGIME section in `format_signal_context()` to include:**
```python
sections.append(
    f"## MARKET REGIME\n"
    f"Bias: {bias.get('bias_level', 'UNKNOWN')}\n"
    f"Composite Score: {bias.get('composite_score', 'N/A')}\n"
    f"Confidence: {bias.get('confidence', 'UNKNOWN')}\n"
    f"DEFCON: {context.get('defcon', 'UNKNOWN')}\n"
    f"\nTimeframe Breakdown:\n"
    f"  Intraday: {tf.get('intraday', {}).get('bias_level', '?')} ({tf.get('intraday', {}).get('sub_score', '?')})\n"
    f"  Swing: {tf.get('swing', {}).get('bias_level', '?')} ({tf.get('swing', {}).get('sub_score', '?')})\n"
    f"  Macro: {tf.get('macro', {}).get('bias_level', '?')} ({tf.get('macro', {}).get('sub_score', '?')})\n"
    f"\nKey Factors:\n"
    f"  VIX: {vix_detail}\n"
    f"  GEX: {gex_detail}\n"
    f"  SPY vs 50 SMA: {spy50_detail}\n"
    f"  SPY vs 200 SMA: {spy200_detail}\n"
    f"  Circuit Breaker: {cb_status}"
)
```

This gives agents enough context to make regime-aware decisions.

## Fix 5: Crypto Price Source

The committee uses yfinance for price data. For crypto tickers (BTC, ETH, etc.), yfinance is unreliable — prices can be $20K+ stale.

**In `committee_context.py`, wherever live prices are fetched via yfinance, add a crypto fallback:**
```python
def get_live_price(ticker: str) -> float | None:
    """Get live price, using Polygon for crypto."""
    crypto_tickers = {"BTC", "ETH", "SOL", "BTC-USD", "ETH-USD"}
    
    if ticker.upper().replace("-USD", "") in {"BTC", "ETH", "SOL"}:
        # Use Polygon crypto endpoint
        try:
            from polygon_client import get_crypto_price
            return get_crypto_price(ticker)
        except Exception:
            pass
    
    # Fall back to yfinance for equities
    import yfinance as yf
    try:
        return yf.Ticker(ticker).fast_info.get("last_price")
    except Exception:
        return None
```

**Check if Polygon crypto endpoint exists on Railway:**
```bash
curl -s "https://pandoras-box-production.up.railway.app/api/crypto/price/BTC" | head -3
```

## Summary of All URL Fixes

| Current (WRONG) | Correct | File |
|---|---|---|
| `{base}/bias/composite` | `{base}/api/bias/composite` | pivot2_committee.py ~620 |
| `{base}/bias/composite/timeframes` | `{base}/api/bias/composite/timeframes` | pivot2_committee.py ~655 |
| `{base}/portfolio/balances` (if wrong) | `{base}/api/portfolio/balances` | committee_context.py ~925 |
| `{base}/portfolio/positions` (if wrong) | `{base}/api/portfolio/positions` | committee_context.py ~933 |

## Files Changed

- `/opt/openclaw/workspace/scripts/pivot2_committee.py` — Fix bias URLs
- `/opt/openclaw/workspace/scripts/committee_context.py` — Fix portfolio URLs if needed, enhance bias formatting, add crypto price fallback

## Deployment

VPS only:
```bash
systemctl restart openclaw
systemctl restart pivot2-interactions
```

## Validation

Run a manual committee analysis on a known signal and verify the output includes:
- [ ] Correct composite bias score (should show URSA_MINOR or current bias)
- [ ] Timeframe breakdown (intraday/swing/macro sub-scores)
- [ ] Current positions listed
- [ ] Account balances mentioned
- [ ] Key factors (VIX level, GEX, SPY SMA distances)
