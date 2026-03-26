# BRIEF: Sell the Rip — Cooldown & Interval Fix (P0)

## Problem
Sell the Rip scanner runs every 5 minutes on **daily bars**. Daily bars don't change intraday, so once a ticker qualifies at 9:35 AM it re-fires every 30 minutes (the cooldown) all day long — producing 12-15 signals per ticker per day. This floods the trade ideas feed.

## Root Cause
- Scan interval (300s / 5 min) is mismatched with bar timeframe (daily)
- Cooldown (`cooldown_minutes: 30`) is too short for a daily-bar scanner
- No calendar-day dedup — same daily bar triggers repeatedly

## Changes Required

### 1. Change scan interval from 5 min to 4 hours in `backend/main.py`

Find:
```python
            await asyncio.sleep(300)  # 5 minutes
```
(This is the sleep at the end of `sell_the_rip_scan_loop`)

Replace with:
```python
            await asyncio.sleep(14400)  # 4 hours (daily bars don't change intraday)
```

### 2. Change cooldown from 30 min to 24 hours in `backend/scanners/sell_the_rip_scanner.py`

Find:
```python
    "cooldown_minutes": 30,
```

Replace with:
```python
    "cooldown_minutes": 1440,  # 24 hours — daily bars, one signal per ticker per day
```

### 3. Add calendar-day dedup check in `check_sell_the_rip()` in `backend/scanners/sell_the_rip_scanner.py`

Find:
```python
    # Cooldown check
    last_signal = _cooldown_tracker.get(ticker)
    if last_signal and (datetime.utcnow() - last_signal).total_seconds() < STR_CONFIG["cooldown_minutes"] * 60:
        return signals
```

Replace with:
```python
    # Cooldown check — calendar-day dedup for daily-bar scanner
    last_signal = _cooldown_tracker.get(ticker)
    if last_signal:
        elapsed = (datetime.utcnow() - last_signal).total_seconds()
        same_day = last_signal.date() == datetime.utcnow().date()
        if same_day or elapsed < STR_CONFIG["cooldown_minutes"] * 60:
            return signals
```

## Testing
- Deploy and wait for next STR scan cycle
- Check Railway logs for `Sell the Rip scan:` — should fire ~2x per trading day (10 AM ET, 2 PM ET)
- Verify no ticker appears more than once per day in trade_ideas
- From VPS: `curl -s -H "X-API-Key: $KEY" "$BASE/api/trade-ideas?strategy=sell_the_rip" | python3 -m json.tool | head -40`

## Risk
Low. Worst case: legitimate STR signals are delayed by up to 4 hours. This is acceptable for a daily-bar strategy — the setup develops over days, not minutes.
