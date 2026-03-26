# BRIEF: Sell the Rip — Migrate Cooldown to Redis (P1)

## Problem
Same issue as Holy Grail: Sell the Rip's `_cooldown_tracker` is an in-memory dict that resets on every deploy. The P0 fix (24h cooldown + calendar-day check) mitigates this with timestamp-based dedup, but it still resets on deploy. Moving to Redis makes it deploy-proof.

## Changes Required

### 1. Replace in-memory tracker in `backend/scanners/sell_the_rip_scanner.py`

Find:
```python
# Track last signal time per ticker for cooldown
_cooldown_tracker: Dict[str, datetime] = {}
```

Replace with:
```python
# Cooldown now stored in Redis (survives deploys)
# Key format: scanner:str:cooldown:{ticker} with 24h TTL
STR_COOLDOWN_SECONDS = 86400  # 24 hours
```

Find the cooldown check in `check_sell_the_rip`:
```python
    # Cooldown check — calendar-day dedup for daily-bar scanner
    last_signal = _cooldown_tracker.get(ticker)
    if last_signal:
        elapsed = (datetime.utcnow() - last_signal).total_seconds()
        same_day = last_signal.date() == datetime.utcnow().date()
        if same_day or elapsed < STR_CONFIG["cooldown_minutes"] * 60:
            return signals
```

Note: If the P0 brief hasn't been applied yet, the original code reads:
```python
    # Cooldown check
    last_signal = _cooldown_tracker.get(ticker)
    if last_signal and (datetime.utcnow() - last_signal).total_seconds() < STR_CONFIG["cooldown_minutes"] * 60:
        return signals
```

Either way, remove the cooldown check from `check_sell_the_rip` (it's sync — Redis is async). Move it to the async `run_sell_the_rip_scan` function instead.

Replace the cooldown check with just a comment:
```python
    # Cooldown check is async — handled in run_sell_the_rip_scan via Redis
```

Find the cooldown set at the end of `check_sell_the_rip`:
```python
    if signals:
        _cooldown_tracker[ticker] = datetime.utcnow()
```

Remove this (Redis set happens in the async scan runner).

In `run_sell_the_rip_scan`, wrap the per-ticker loop with Redis cooldown:

Find:
```python
    for ticker in tickers:
        try:
            df = await _fetch_daily_bars_async(ticker)
            if df.empty or len(df) < 60:
                continue

            df = compute_indicators(df)

            # Get sector context for this ticker
            sector_etf = ticker_to_etf.get(ticker)
            sector_rs = all_sector_rs.get(sector_etf) if sector_etf else None

            signals = check_sell_the_rip(df, ticker, sector_etf, sector_rs)
            all_signals.extend(signals)
        except Exception as e:
            logger.error("Sell the Rip scan error for %s: %s", ticker, e)
        await asyncio.sleep(0.05)  # Rate limiting
```

Replace with:
```python
    redis = await get_redis_client()

    for ticker in tickers:
        try:
            # Redis cooldown check (survives deploys)
            cooldown_key = f"scanner:str:cooldown:{ticker}"
            if await redis.exists(cooldown_key):
                continue

            df = await _fetch_daily_bars_async(ticker)
            if df.empty or len(df) < 60:
                continue

            df = compute_indicators(df)

            # Get sector context for this ticker
            sector_etf = ticker_to_etf.get(ticker)
            sector_rs = all_sector_rs.get(sector_etf) if sector_etf else None

            signals = check_sell_the_rip(df, ticker, sector_etf, sector_rs)
            if signals:
                await redis.set(cooldown_key, "1", ex=STR_COOLDOWN_SECONDS)
            all_signals.extend(signals)
        except Exception as e:
            logger.error("Sell the Rip scan error for %s: %s", ticker, e)
        await asyncio.sleep(0.05)  # Rate limiting
```

## Testing
- Deploy, trigger scan, verify signals appear
- Check Redis: `redis-cli KEYS scanner:str:*`
- Redeploy — verify same ticker doesn't re-fire within 24h

## Risk
Low. Same pattern as Holy Grail Redis migration.
