# Brief: Fix Golden Touch Signal — Zero Fires

**Priority:** HIGH — Golden Touch is the highest-conviction CTA signal and has never fired once across 389 trade ideas.

**File to modify:** `backend/scanners/cta_scanner.py`

**Function:** `check_golden_touch()`

---

## Problem

Golden Touch requires ALL FIVE conditions on the SAME BAR. The probability of all five co-occurring is near zero with current thresholds:

1. Price within 1% of 120 SMA ✅ (reasonable)
2. Above 120 SMA for 50+ consecutive days ❌ (doc says 30, code says 50)
3. Correction between 5-12% from 60-day rolling high ✅ (reasonable)
4. 20 SMA still above 120 SMA ✅ (standard)
5. Volume on touch bar ≥ 2.0x 30-day average ❌ (institutional accumulation at support is usually quiet, not 2x spikes)

Conditions 2 and 5 are the killers. Condition 5 alone probably eliminates 90%+ of otherwise valid setups.

---

## Changes

### Change 1: Align `min_bars_above_120` with strategy doc

**Find this block in `CTA_CONFIG`:**
```python
    "golden_touch": {
        "min_bars_above_120": 50,  # Must be above 120 for 50+ days
        "min_correction_pct": 5.0,  # 5% minimum correction from high
        "max_correction_pct": 12.0,  # Not too deep (>12% = broken trend)
    },
```

**Replace with:**
```python
    "golden_touch": {
        "min_bars_above_120": 30,  # Must be above 120 for 30+ days (aligned with strategy doc)
        "min_correction_pct": 5.0,  # 5% minimum correction from high
        "max_correction_pct": 12.0,  # Not too deep (>12% = broken trend)
    },
```

### Change 2: Reduce volume threshold and add multi-bar window

**Find this block in `CTA_CONFIG["volume"]`:**
```python
        "golden_touch_threshold": 2.00,  # 100% above avg for Golden Touch (H5)
```

**Replace with:**
```python
        "golden_touch_threshold": 1.30,  # 30% above avg for Golden Touch (was 2.00 — too strict, never fired)
```

### Change 3: Add multi-bar touch window in `check_golden_touch()`

The current logic only checks the latest bar. Change it to check the last 3 bars for the touch and volume conditions.

**Find this section in `check_golden_touch()`:**
```python
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    price = latest["Close"]
    sma120 = latest["sma120"]
    sma20 = latest["sma20"]
    days_above = latest["days_above_120"]
    correction = latest["correction_pct"]
    atr = latest["atr"]

    if pd.isna(sma120) or pd.isna(sma20) or pd.isna(days_above):
        return None

    touching_120 = (latest["Low"] <= sma120 * 1.01 and price >= sma120 * 0.99)
    was_above_long = days_above >= config["min_bars_above_120"]
    valid_correction = config["min_correction_pct"] <= correction <= config["max_correction_pct"]
    uptrend_intact = sma20 > sma120

    # H5: Golden Touch requires volume confirmation at the touch candle
    touch_vol_ratio = latest.get("vol_ratio")
    vol_at_touch = (pd.notna(touch_vol_ratio) and
                    touch_vol_ratio >= CTA_CONFIG["volume"]["golden_touch_threshold"])

    if touching_120 and was_above_long and valid_correction and uptrend_intact and vol_at_touch:
```

**Replace with:**
```python
    if len(df) < 4:
        return None

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    price = latest["Close"]
    sma120 = latest["sma120"]
    sma20 = latest["sma20"]
    days_above = latest["days_above_120"]
    correction = latest["correction_pct"]
    atr = latest["atr"]

    if pd.isna(sma120) or pd.isna(sma20) or pd.isna(days_above):
        return None

    # Check touch across a 3-bar window (120 SMA is a zone, not a laser line)
    touching_120 = False
    for i in range(-1, -4, -1):
        bar = df.iloc[i]
        bar_sma120 = bar.get("sma120")
        if pd.notna(bar_sma120) and bar["Low"] <= bar_sma120 * 1.01 and bar["Close"] >= bar_sma120 * 0.99:
            touching_120 = True
            break

    was_above_long = days_above >= config["min_bars_above_120"]
    valid_correction = config["min_correction_pct"] <= correction <= config["max_correction_pct"]
    uptrend_intact = sma20 > sma120

    # Volume confirmation across 3-bar window (institutional accumulation can be spread)
    vol_threshold = CTA_CONFIG["volume"]["golden_touch_threshold"]
    vol_at_touch = False
    for i in range(-1, -4, -1):
        bar = df.iloc[i]
        bar_vol = bar.get("vol_ratio")
        if pd.notna(bar_vol) and bar_vol >= vol_threshold:
            vol_at_touch = True
            break

    if touching_120 and was_above_long and valid_correction and uptrend_intact and vol_at_touch:
```

---

## Expected Impact

- `min_bars_above_120`: 50 → 30 roughly doubles the eligible stock pool
- `golden_touch_threshold`: 2.00 → 1.30 dramatically increases the chance of volume confirmation
- 3-bar touch window: Catches setups where price approaches 120 SMA over 2-3 bars instead of requiring a single-bar touch
- Combined: expect 5-15 Golden Touch signals per month (from zero)

## Validation

After deploying, monitor the next CTA scan run. Check Railway logs for:
```
Golden {count}
```
in the scan summary line. If count > 0, the fix is working.

## Files Changed

- `backend/scanners/cta_scanner.py` — `CTA_CONFIG` dict + `check_golden_touch()` function

## No Other Files Affected

Golden Touch signals flow through the same `scan_ticker_cta()` → `process_signal_unified()` pipeline as all other CTA signals. No handler changes needed.
