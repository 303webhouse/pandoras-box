# BRIEF: Holy Grail — Redis Cooldown + Daily Signal Cap (P1)

## Problem
Holy Grail uses an in-memory dict (`_cooldown_tracker`) for per-ticker cooldowns. This resets on every Railway deploy, allowing duplicate signals. With 1H bars and a 5-bar cooldown, trending tickers can signal every ~5 hours — and more often after deploys.

## Changes Required

### 1. Replace in-memory cooldown with Redis in `backend/scanners/holy_grail_scanner.py`

Find:
```python
# Track last signal bar index per ticker to enforce cooldown
_cooldown_tracker: Dict[str, int] = {}
```

Replace with:
```python
# Cooldown now stored in Redis (survives deploys)
# Key format: scanner:hg:cooldown:{ticker} with 24h TTL
HG_COOLDOWN_SECONDS = 86400  # 24 hours
HG_DAILY_CAP = 2  # Max signals per ticker per calendar day
```

Find the cooldown check in `check_holy_grail_signals`:
```python
    # Cooldown check — skip if last signal was within N bars
    bar_idx = len(df) - 1
    last_signal_idx = _cooldown_tracker.get(ticker, -999)
    if (bar_idx - last_signal_idx) < HG_CONFIG["cooldown_bars"]:
        return signals
```

Replace with:
```python
    # Cooldown check is now async — handled in scan_ticker_holy_grail
    # This function is sync, so we skip the check here
    bar_idx = len(df) - 1
```

Find the cooldown set after signal creation (appears twice — once for long, once for short):
```python
            _cooldown_tracker[ticker] = bar_idx
```

Remove both occurrences (Redis set happens in the async wrapper).

Then modify `scan_ticker_holy_grail` to add async Redis cooldown:

Find:
```python
async def scan_ticker_holy_grail(ticker: str) -> List[Dict]:
    """Scan a single ticker for Holy Grail setups."""
    await _refresh_hg_vix_adjustments()
    try:
        df = await _fetch_1h_bars_async(ticker)

        if df.empty or len(df) < 40:  # Need 20 EMA + 14 ADX warmup
            return []

        df = calculate_holy_grail_indicators(df)
        return check_holy_grail_signals(df, ticker)

    except Exception as e:
        logger.error("Holy Grail scan error for %s: %s", ticker, e)
        return []
```

Replace with:
```python
async def scan_ticker_holy_grail(ticker: str) -> List[Dict]:
    """Scan a single ticker for Holy Grail setups."""
    await _refresh_hg_vix_adjustments()
    try:
        # Redis cooldown check (survives deploys)
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        cooldown_key = f"scanner:hg:cooldown:{ticker}"
        if await redis.exists(cooldown_key):
            return []

        # Daily cap check
        from datetime import date
        cap_key = f"scanner:hg:daily_count:{ticker}:{date.today().isoformat()}"
        daily_count = await redis.get(cap_key)
        if daily_count and int(daily_count) >= HG_DAILY_CAP:
            return []

        df = await _fetch_1h_bars_async(ticker)

        if df.empty or len(df) < 40:
            return []

        df = calculate_holy_grail_indicators(df)
        signals = check_holy_grail_signals(df, ticker)

        # Set cooldown and increment daily cap for each signal
        if signals:
            await redis.set(cooldown_key, "1", ex=HG_COOLDOWN_SECONDS)
            await redis.incr(cap_key)
            await redis.expire(cap_key, 86400)  # TTL = 24h

        return signals

    except Exception as e:
        logger.error("Holy Grail scan error for %s: %s", ticker, e)
        return []
```

## Testing
- Deploy, trigger a scan, verify signals appear
- Check Redis for cooldown keys: `redis-cli KEYS scanner:hg:*`
- Redeploy — verify same ticker doesn't re-fire within 24h
- From VPS: `curl -s -H "X-API-Key: $KEY" "$BASE/api/trade-ideas?strategy=Holy_Grail" | python3 -m json.tool | head -40`

## Risk
Low. Redis is already proven for other cooldowns in the system. The 24h cooldown is conservative — Holy Grail setups develop over hours/days, not minutes.
