# BRIEF: Scout Sniper — Indentation Bug Fix + Threshold Relaxation (P0/P1)

## Problem
1. **CRITICAL BUG**: Signal detection logic is outside the lookback for-loop due to an indentation error. The `try: import pytz` block and all subsequent signal logic (RVOL gate, structural checks, long/short evaluation) runs once after the loop exits, not inside it.
2. **Overly strict thresholds**: RSI 35/65 + VWAP hard gate + bullish/bearish candle = triple conjunction that almost never fires on liquid large-caps in the current regime.
3. **Quality gate too high**: `min_quality_score >= 3` on top of the triple conjunction filters out everything.

## Changes Required

### 1. Fix indentation — move signal logic inside the for-loop in `backend/scanners/scout_sniper_scanner.py`

The entire block from `# Time filter` through the end of `check_scout_signals()` needs to be indented one level to be inside the `for offset in range(lookback):` loop.

Find:
```python
        if any(pd.isna(x) for x in [rsi, rsi_prev, rvol, vwap, atr]):
            continue

        # Time filter: skip first 15 min (9:30-9:45 ET) and lunch (12-1 PM ET)
    try:
        import pytz
```

Replace with:
```python
        if any(pd.isna(x) for x in [rsi, rsi_prev, rvol, vwap, atr]):
            continue

        # Time filter: skip first 15 min (9:30-9:45 ET) and lunch (12-1 PM ET)
        try:
            import pytz
```

AND every subsequent line in the function from `et_now = datetime.now(...)` through the final `return signals` must be indented by 8 spaces (inside the for loop's body). This is the bulk of the fix.

Specifically, the following blocks must all be at 8-space indent (inside the for loop):
- The `try/except` for pytz time filter
- `if not time_ok: return signals` → change to `continue` (don't abort entire function, skip this bar)
- RVOL gate → change `return signals` to `continue`
- Structural awareness block
- SMA regime block
- Long signal / Short signal detection
- Tradeable vs IGNORE logic
- Quality score calculation
- Signal construction loop

IMPORTANT: Where the original code says `return signals` inside what should be loop iterations, change to `continue` so the loop checks the next bar instead of aborting the entire scan for this ticker.

### 2. Relax RSI thresholds in `backend/scanners/scout_sniper_scanner.py`

Find:
```python
    "rsi_oversold": 35,
    "rsi_overbought": 65,
```

Replace with:
```python
    "rsi_oversold": 40,
    "rsi_overbought": 60,
```

### 3. Lower quality gate in `backend/scanners/scout_sniper_scanner.py`

Find:
```python
    "min_quality_score": 3,
```

Replace with:
```python
    "min_quality_score": 2,
```

### 4. Make VWAP a quality bonus instead of hard gate

Find:
```python
    # Long signal: RSI oversold hook + below VWAP + bullish reversal candle
    long_sig = (
        bool(latest.get("bull_hook", False)) and
        latest["Close"] <= vwap and
        bool(latest.get("bull_candle", False))
    )

    # Short signal: RSI overbought hook + above VWAP + bearish reversal candle
    short_sig = (
        bool(latest.get("bear_hook", False)) and
        latest["Close"] >= vwap and
        bool(latest.get("bear_candle", False))
    )
```

Replace with:
```python
    # Long signal: RSI oversold hook + bullish reversal candle (VWAP is quality bonus, not gate)
    long_sig = (
        bool(latest.get("bull_hook", False)) and
        bool(latest.get("bull_candle", False))
    )

    # Short signal: RSI overbought hook + bearish reversal candle (VWAP is quality bonus, not gate)
    short_sig = (
        bool(latest.get("bear_hook", False)) and
        bool(latest.get("bear_candle", False))
    )
```

Then in the `calc_score` function, add VWAP as a bonus point:

Find:
```python
    def calc_score(direction):
        s = 0
        s += 1 if time_ok else 0
        s += 1 if (direction == "LONG" and not sma_bearish) or (direction == "SHORT" and not sma_bullish) else 0
        s += 2 if tier == "A" else 1
        s += 1 if (direction == "LONG" and sma_bullish) or (direction == "SHORT" and sma_bearish) else 0
        s += 1 if (direction == "LONG" and structural_long_ok) or (direction == "SHORT" and structural_short_ok) else 0
        return s
```

Replace with:
```python
    def calc_score(direction):
        s = 0
        s += 1 if time_ok else 0
        s += 1 if (direction == "LONG" and not sma_bearish) or (direction == "SHORT" and not sma_bullish) else 0
        s += 2 if tier == "A" else 1
        s += 1 if (direction == "LONG" and sma_bullish) or (direction == "SHORT" and sma_bearish) else 0
        s += 1 if (direction == "LONG" and structural_long_ok) or (direction == "SHORT" and structural_short_ok) else 0
        # VWAP confluence bonus: long below VWAP or short above VWAP
        s += 1 if (direction == "LONG" and latest["Close"] <= vwap) or (direction == "SHORT" and latest["Close"] >= vwap) else 0
        return s
```

## Testing
- Deploy and wait for next Scout scan (runs every 15 min)
- Check Railway logs for `Scout scan:` — should now show signals_found > 0
- Verify signals appear in trade_ideas feed
- From VPS: `curl -s -H "X-API-Key: $KEY" "$BASE/api/trade-ideas?strategy=Scout" | python3 -m json.tool | head -40`

## Risk
Medium. Relaxing thresholds may produce false positives initially. The quality gate (now >= 2) and VWAP bonus scoring should keep signal quality reasonable. Monitor for 2-3 days and tighten if noise is too high.
