# CODEX SPEC 2: Trade Signal Improvements

**Repo:** `trading-hub/trading-hub/`  
**Depends on:** CODEX-MASTER (Spec 1) must be completed first — this spec modifies the same signal functions.  
**Pairs with:** CODEX-UW (Spec 3) — this spec includes hooks for UW flow data. Those hooks return null gracefully when UW isn't set up yet.

Read this ENTIRE document before writing any code.

---

## WHAT THIS CHANGES

Currently, every CTA signal uses the same static formula:
```python
entry = price
stop = price - (ATR * 1.5)   # or + for shorts
target = price + (ATR * 3.0)  # or - for shorts
```

This produces identical 2:1 R:R regardless of signal type, zone strength, sector alignment, or market context. A golden touch in MAX_LONG gets the same treatment as a zone upgrade in DE_LEVERAGING. This spec makes signals smarter, more actionable, and more honest about conviction.

---

## TABLE OF CONTENTS

| Item | What It Does |
|------|-------------|
| 1 | Context-Aware R:R Profiles — stop/target multipliers vary by signal type + zone |
| 2 | SMA-Anchored Stops — stops placed at structural levels, not arbitrary ATR distances |
| 3 | Scale-Out Targets (T1/T2) — conservative take-profit + full thesis target |
| 4 | Entry Windows — valid entry zone instead of stale exact price |
| 5 | Confluence Scoring — boost conviction when multiple signals stack on same ticker |
| 6 | Sector Wind — sector ETF alignment adds/reduces conviction |
| 7 | Bias Alignment — macro bias direction confirms or conflicts with signal |
| 8 | UW Flow Hooks — reads cached UW data from Redis if available (Spec 3 writes it) |
| 9 | Signal Invalidation Levels — price level where thesis breaks, not just a timer |
| 10 | Signal Output Shape — updated `setup` and new `setup_context` fields |
| 11 | Historical Hit Rate Tracking — nightly batch job scoring past signals |

---

## BUILD ORDER

1. **R:R Profiles** (Item 1) — config-only, no new data, biggest immediate impact
2. **SMA-Anchored Stops** (Item 2) — moderate effort, uses existing indicator data
3. **Scale-Out Targets** (Item 3) — small effort, builds on Item 1+2
4. **Entry Windows** (Item 4) — small effort, uses existing SMA data
5. **Signal Output Shape** (Item 10) — update the output format to carry all new fields
6. **Confluence Scoring** (Item 5) — runs after all check functions, before signal output
7. **Sector Wind** (Item 6) — one Redis read per signal, lightweight
8. **Bias Alignment** (Item 7) — one Redis read per signal, lightweight
9. **UW Flow Hooks** (Item 8) — Redis read, returns null if no data yet
10. **Signal Invalidation** (Item 9) — adds invalidation_level to each signal
11. **Hit Rate Tracking** (Item 11) — separate batch job, doesn't block anything

---

## ITEM 1: Context-Aware R:R Profiles

### New File: `backend/config/signal_profiles.py`

```python
"""
R:R profiles that vary stop/target ATR multipliers by signal type and CTA zone.

Usage:
    stop_mult, target_mult = get_rr_profile("GOLDEN_TOUCH", "MAX_LONG")
    stop = entry - (atr * stop_mult)   # for longs
    target = entry + (atr * target_mult)
"""

# (signal_type, cta_zone) → (stop_atr_multiplier, target_atr_multiplier)
# Higher target_mult / stop_mult = better R:R
RR_PROFILES = {
    # GOLDEN_TOUCH: Price pulling back to 20 SMA in uptrend
    ("GOLDEN_TOUCH", "MAX_LONG"):        (1.0, 3.5),   # Tight stop, let it run — strongest setup
    ("GOLDEN_TOUCH", "RECOVERY"):        (1.25, 2.5),  # Trend reforming, moderate targets
    ("GOLDEN_TOUCH", "DE_LEVERAGING"):   (1.5, 2.0),   # Fighting gravity, defensive

    # PULLBACK_ENTRY: Deeper pullback to 50 SMA
    ("PULLBACK_ENTRY", "MAX_LONG"):      (1.25, 3.0),  # Deeper stop needed, trend supports target
    ("PULLBACK_ENTRY", "RECOVERY"):      (1.5, 2.5),   # Trend uncertain
    ("PULLBACK_ENTRY", "DE_LEVERAGING"): (1.75, 2.0),  # High risk, tight target

    # TWO_CLOSE_VOLUME: Breakout confirmation with volume
    ("TWO_CLOSE_VOLUME", "MAX_LONG"):    (1.0, 3.0),   # Momentum confirmed, tight stop
    ("TWO_CLOSE_VOLUME", "RECOVERY"):    (1.25, 2.5),  # Breakout from base
    ("TWO_CLOSE_VOLUME", "DE_LEVERAGING"): (1.5, 2.0), # Counter-trend breakout, be careful

    # ZONE_UPGRADE: Zone just improved (e.g., WATERFALL → RECOVERY)
    ("ZONE_UPGRADE", "RECOVERY"):        (1.5, 2.0),   # Speculative — trend MAY be turning
    ("ZONE_UPGRADE", "MAX_LONG"):        (1.25, 2.5),  # Upgraded into strength
    ("ZONE_UPGRADE", "DE_LEVERAGING"):   (2.0, 2.0),   # Very speculative, 1:1 minimum

    # TRAPPED_LONGS (short signal): Bearish capitulation play
    ("TRAPPED_LONGS", "WATERFALL"):      (1.25, 3.5),  # Full capitulation, let it fall
    ("TRAPPED_LONGS", "DE_LEVERAGING"):  (1.5, 3.0),   # Trend weakening, shorts working
    ("TRAPPED_LONGS", "CAPITULATION"):   (1.5, 2.5),   # Already extended, tighter target

    # TRAPPED_SHORTS (long signal): Short squeeze play
    ("TRAPPED_SHORTS", "MAX_LONG"):      (1.0, 3.5),   # Squeeze into strong trend
    ("TRAPPED_SHORTS", "RECOVERY"):      (1.25, 3.0),  # Squeeze helping recovery
}

DEFAULT_PROFILE = (1.5, 3.0)  # Fallback: standard 2:1


def get_rr_profile(signal_type: str, cta_zone: str) -> tuple:
    """
    Return (stop_atr_mult, target_atr_mult) for a given signal + zone combination.
    Falls back to DEFAULT_PROFILE if no specific profile exists.
    """
    profile = RR_PROFILES.get((signal_type, cta_zone))
    if profile:
        return profile

    # Try signal type with any zone
    for (sig, _zone), prof in RR_PROFILES.items():
        if sig == signal_type:
            return prof

    return DEFAULT_PROFILE
```

### Modify Check Functions in `cta_scanner.py`

Every check function (`check_golden_touch`, `check_pullback_entry`, `check_two_close_volume`, `check_zone_upgrade`, `check_trapped_longs`, `check_trapped_shorts`) currently has hardcoded ATR multipliers. Replace them with profile lookups.

**Pattern — apply to ALL check functions:**

```python
# BEFORE (in every check function):
entry = round(price, 2)
stop = round(price - (atr * 1.5), 2)
target = round(price + (atr * 3.0), 2)

# AFTER:
from config.signal_profiles import get_rr_profile

zone, _ = get_cta_zone(price, latest.get('sma20'), latest.get('sma50'), latest.get('sma120'))
stop_mult, target_mult = get_rr_profile("GOLDEN_TOUCH", zone)  # Use actual signal type

entry = round(price, 2)
if direction == "LONG":
    stop = round(price - (atr * stop_mult), 2)
    target = round(price + (atr * target_mult), 2)
else:  # SHORT
    stop = round(price + (atr * stop_mult), 2)
    target = round(price - (atr * target_mult), 2)
```

The zone is already calculated earlier in the scan flow. Pass it into each check function or calculate it locally from the available SMA data (already in the DataFrame).

---

## ITEM 2: SMA-Anchored Stops

Instead of pure ATR-distance stops, anchor to the nearest structural SMA level when it produces a better stop than the raw ATR calculation.

### New Function in `cta_scanner.py`

```python
def calculate_smart_stop(
    signal_type: str,
    direction: str,
    price: float,
    smas: dict,
    atr: float,
    zone: str,
) -> tuple:
    """
    Calculate stop using structural SMA levels when available.
    Returns (stop_price, stop_anchor_description).

    Logic:
    - Identify candidate SMA levels on the correct side of price
    - Add a small ATR buffer below/above the SMA (0.25 ATR)
    - Pick the candidate that gives the best R:R while still being structurally sound
    - Fall back to ATR-based stop if no good SMA candidate exists
    """
    from config.signal_profiles import get_rr_profile
    stop_mult, target_mult = get_rr_profile(signal_type, zone)
    atr_stop = price - (atr * stop_mult) if direction == "LONG" else price + (atr * stop_mult)
    buffer = atr * 0.25

    candidates = []

    if direction == "LONG":
        # Look for SMAs below price to use as support stops
        sma_levels = [
            ("20 SMA", smas.get("sma20")),
            ("50 SMA", smas.get("sma50")),
            ("120 SMA", smas.get("sma120")),
            ("200 SMA", smas.get("sma200")),
        ]
        for label, sma_val in sma_levels:
            if sma_val and sma_val < price:
                candidate_stop = sma_val - buffer
                risk = price - candidate_stop
                # Only consider if risk is reasonable (0.5 to 3.0 ATR)
                if 0.5 * atr <= risk <= 3.0 * atr:
                    candidates.append((candidate_stop, f"{label} ({round(sma_val, 2)}) - buffer"))

        # Prefer closest SMA to price (tightest stop with structural support)
        if candidates:
            candidates.sort(key=lambda c: price - c[0])  # Closest first
            # Pick the tightest candidate
            best_stop, best_anchor = candidates[0]
            return round(best_stop, 2), best_anchor

    elif direction == "SHORT":
        # Look for SMAs above price to use as resistance stops
        sma_levels = [
            ("20 SMA", smas.get("sma20")),
            ("50 SMA", smas.get("sma50")),
            ("120 SMA", smas.get("sma120")),
            ("200 SMA", smas.get("sma200")),
        ]
        for label, sma_val in sma_levels:
            if sma_val and sma_val > price:
                candidate_stop = sma_val + buffer
                risk = candidate_stop - price
                if 0.5 * atr <= risk <= 3.0 * atr:
                    candidates.append((candidate_stop, f"{label} ({round(sma_val, 2)}) + buffer"))

        if candidates:
            candidates.sort(key=lambda c: c[0] - price)  # Closest first
            best_stop, best_anchor = candidates[0]
            return round(best_stop, 2), best_anchor

    # Fallback: pure ATR stop
    return round(atr_stop, 2), f"{stop_mult} ATR"
```

### Zone-Specific SMA Preferences

The function above picks the closest SMA. But we can be smarter — in certain zones, certain SMAs are more meaningful:

```python
# Preferred stop anchors by zone (checked first before fallback to closest)
PREFERRED_STOP_ANCHORS = {
    # zone → preferred SMA key for LONG stops
    "MAX_LONG": "sma20",       # In MAX_LONG, the 20 SMA IS the trend — stop just below it
    "RECOVERY": "sma50",       # In RECOVERY, the 50 SMA is structural support
    "DE_LEVERAGING": "sma120", # In DE_LEVERAGING, only the 120 SMA matters
}
```

Add this preference to `calculate_smart_stop()`: check the preferred SMA first, use it if valid, otherwise fall through to the closest-SMA logic.

---

## ITEM 3: Scale-Out Targets (T1 / T2)

### Logic

- **T1 (conservative):** Take partial profit, move stop to breakeven. Calculated as roughly half the full target distance, OR the nearest SMA overhead (for longs) / underfoot (for shorts).
- **T2 (full thesis):** The original target from the R:R profile. Let remaining position ride to this level.

### Implementation in Each Check Function

After calculating entry, stop, and target:

```python
# Calculate T1 and T2
risk = abs(entry - stop)
full_reward = abs(target - entry)

if direction == "LONG":
    # T1: Half the reward distance, or nearest SMA overhead, whichever is closer
    t1_atr = entry + (full_reward * 0.5)
    t1_sma = None
    # Check for SMA between entry and target that could act as resistance
    for sma_key in ["sma20", "sma50", "sma120"]:
        sma_val = smas.get(sma_key)
        if sma_val and entry < sma_val < target:
            t1_sma = sma_val
            break  # Take the first (closest above entry)
    t1 = round(min(t1_atr, t1_sma) if t1_sma else t1_atr, 2)
    t2 = target
else:
    t1_atr = entry - (full_reward * 0.5)
    t1_sma = None
    for sma_key in ["sma20", "sma50", "sma120"]:
        sma_val = smas.get(sma_key)
        if sma_val and target < sma_val < entry:
            t1_sma = sma_val
            break
    t1 = round(max(t1_atr, t1_sma) if t1_sma else t1_atr, 2)
    t2 = target

# Ensure T1 gives at least 0.75:1 R:R to be worth taking
t1_reward = abs(t1 - entry)
if t1_reward < (risk * 0.75):
    t1 = t2  # Skip T1, just use single target
```

---

## ITEM 4: Entry Windows

### Problem

Signals say `"entry": 845.20` but by the time the trader sees it, price may be $847. Is it still valid?

### Solution

Each signal defines a valid entry zone: a price range where the thesis holds. Outside this range, the signal is stale.

```python
def calculate_entry_window(
    signal_type: str,
    direction: str,
    price: float,
    smas: dict,
    atr: float,
) -> dict:
    """
    Define the price range where this signal's entry thesis is still valid.
    """
    if direction == "LONG":
        if signal_type == "GOLDEN_TOUCH":
            # Thesis: price is pulling back to 20 SMA. Valid while price is
            # between 20 SMA and 0.75 ATR above it.
            sma20 = smas.get("sma20")
            if sma20:
                entry_low = round(sma20, 2)
                entry_high = round(sma20 + (atr * 0.75), 2)
            else:
                entry_low = round(price - (atr * 0.25), 2)
                entry_high = round(price + (atr * 0.5), 2)

        elif signal_type == "PULLBACK_ENTRY":
            # Thesis: deeper pullback to 50 SMA.
            sma50 = smas.get("sma50")
            if sma50:
                entry_low = round(sma50, 2)
                entry_high = round(sma50 + (atr * 0.75), 2)
            else:
                entry_low = round(price - (atr * 0.25), 2)
                entry_high = round(price + (atr * 0.5), 2)

        elif signal_type == "TWO_CLOSE_VOLUME":
            # Thesis: breakout with volume. Valid while price hasn't run too far.
            entry_low = round(price - (atr * 0.25), 2)
            entry_high = round(price + (atr * 1.0), 2)

        elif signal_type == "TRAPPED_SHORTS":
            # Thesis: squeeze. Valid while price is still near VWAP/200 SMA area.
            entry_low = round(price - (atr * 0.5), 2)
            entry_high = round(price + (atr * 1.0), 2)

        else:
            # Generic window
            entry_low = round(price - (atr * 0.5), 2)
            entry_high = round(price + (atr * 0.75), 2)

        return {"entry_low": entry_low, "entry_high": entry_high}

    else:  # SHORT
        if signal_type == "TRAPPED_LONGS":
            entry_low = round(price - (atr * 1.0), 2)
            entry_high = round(price + (atr * 0.5), 2)
        else:
            entry_low = round(price - (atr * 0.75), 2)
            entry_high = round(price + (atr * 0.5), 2)

        return {"entry_low": entry_low, "entry_high": entry_high}
```

---

## ITEM 5: Confluence Scoring

### Where It Runs

After all check functions have run on a ticker in `scan_ticker_cta()`, BEFORE the signals are returned. This is a post-processing step on the signals list.

### Add to `cta_scanner.py`

```python
def score_confluence(signals: List[Dict]) -> List[Dict]:
    """
    Score confluence when multiple signals fire on the same ticker.

    Rules:
    - 2+ signals in the same direction: boost priority by 25, set confluence flag
    - Signals in conflicting directions: flag conflict warning on both
    - Specific high-value combos get extra boost:
        - GOLDEN_TOUCH + TRAPPED_SHORTS = squeeze into trend (priority +40)
        - TWO_CLOSE_VOLUME + ZONE_UPGRADE = breakout confirmation (priority +30)
    """
    if len(signals) <= 1:
        return signals

    long_signals = [s for s in signals if s.get("direction") == "LONG"]
    short_signals = [s for s in signals if s.get("direction") == "SHORT"]

    # Check for directional conflict
    if long_signals and short_signals:
        for s in signals:
            s["confluence"] = {
                "count": len(signals),
                "warning": "CONFLICTING_SIGNALS",
                "note": f"{len(long_signals)} LONG + {len(short_signals)} SHORT signals on same ticker — thesis is muddled",
            }
            s["confidence"] = "LOW"
        return signals

    # Same direction — boost
    aligned_signals = long_signals or short_signals
    signal_types = [s["signal_type"] for s in aligned_signals]

    # Check for high-value combos
    combo_boost = 0
    combo_label = None
    if "GOLDEN_TOUCH" in signal_types and "TRAPPED_SHORTS" in signal_types:
        combo_boost = 40
        combo_label = "Squeeze into trend (Golden Touch + Trapped Shorts)"
    elif "TWO_CLOSE_VOLUME" in signal_types and "ZONE_UPGRADE" in signal_types:
        combo_boost = 30
        combo_label = "Breakout confirmation (Volume + Zone Upgrade)"
    elif "GOLDEN_TOUCH" in signal_types and "TWO_CLOSE_VOLUME" in signal_types:
        combo_boost = 25
        combo_label = "Trend + Volume confirmation"

    base_boost = 25 if len(aligned_signals) >= 2 else 0
    total_boost = base_boost + combo_boost

    for s in aligned_signals:
        s["priority"] = s.get("priority", 50) + total_boost
        s["confidence"] = "HIGH" if total_boost >= 40 else s.get("confidence", "MEDIUM")
        s["confluence"] = {
            "count": len(aligned_signals),
            "signal_types": signal_types,
            "boost": total_boost,
            "combo": combo_label,
        }

    return signals
```

### Wire into `scan_ticker_cta()`

```python
async def scan_ticker_cta(ticker: str, allow_shorts: bool = False) -> List[Dict]:
    # ... all existing check functions ...
    # ... trapped trader checks (from Spec 1) ...

    # POST-PROCESSING: Score confluence across all signals for this ticker
    signals = score_confluence(signals)

    return signals
```

---

## ITEM 6: Sector Wind

### Logic

At signal generation time, look up the sector ETF's CTA zone. If the sector trend aligns with the signal direction, it's wind at the back. If it opposes, flag it.

### Add to `cta_scanner.py`

```python
async def get_sector_wind(ticker: str, signal_direction: str) -> dict:
    """
    Check if the signal direction aligns with the sector trend.
    Reads the sector ETF's CTA zone from Redis (already written by Item 10 in Spec 1).
    """
    from config.sectors import detect_sector, SECTOR_ETF_MAP
    from database.redis_client import get_redis_client

    sector = detect_sector(ticker)
    if sector == "Uncategorized":
        return {"sector": sector, "alignment": "UNKNOWN", "etf_zone": None}

    etf = SECTOR_ETF_MAP.get(sector, {}).get("etf")
    if not etf:
        return {"sector": sector, "alignment": "UNKNOWN", "etf_zone": None}

    try:
        client = await get_redis_client()
        if client:
            etf_zone = await client.get(f"cta:zone:{etf}")
            if etf_zone:
                etf_zone = etf_zone.decode() if isinstance(etf_zone, bytes) else etf_zone

                # Determine alignment
                bullish_zones = {"MAX_LONG", "RECOVERY"}
                bearish_zones = {"WATERFALL", "CAPITULATION", "DE_LEVERAGING"}

                if signal_direction == "LONG" and etf_zone in bullish_zones:
                    alignment = "TAILWIND"
                elif signal_direction == "SHORT" and etf_zone in bearish_zones:
                    alignment = "TAILWIND"
                elif signal_direction == "LONG" and etf_zone in bearish_zones:
                    alignment = "HEADWIND"
                elif signal_direction == "SHORT" and etf_zone in bullish_zones:
                    alignment = "HEADWIND"
                else:
                    alignment = "NEUTRAL"

                return {"sector": sector, "etf": etf, "etf_zone": etf_zone, "alignment": alignment}
    except Exception:
        pass

    return {"sector": sector, "alignment": "UNKNOWN", "etf_zone": None}
```

---

## ITEM 7: Bias Alignment

### Logic

Check if the signal direction matches the daily/weekly composite bias.

### Add to `cta_scanner.py`

```python
async def get_bias_alignment(signal_direction: str) -> dict:
    """
    Check if signal direction aligns with the current composite bias.
    Reads from Redis where the bias engine stores its latest output.
    """
    from database.redis_client import get_redis_client

    try:
        client = await get_redis_client()
        if client:
            bias_data = await client.get("bias:composite:latest")
            if bias_data:
                import json
                bias = json.loads(bias_data)
                bias_label = bias.get("bias_label", "NEUTRAL")

                bullish_biases = {"TORO_MAJOR", "TORO_MINOR"}
                bearish_biases = {"URSA_MAJOR", "URSA_MINOR"}

                if signal_direction == "LONG" and bias_label in bullish_biases:
                    return {"bias": bias_label, "alignment": "ALIGNED", "conviction_mult": 1.2}
                elif signal_direction == "SHORT" and bias_label in bearish_biases:
                    return {"bias": bias_label, "alignment": "ALIGNED", "conviction_mult": 1.2}
                elif bias_label == "NEUTRAL":
                    return {"bias": bias_label, "alignment": "NEUTRAL", "conviction_mult": 1.0}
                else:
                    return {"bias": bias_label, "alignment": "COUNTER_TREND", "conviction_mult": 0.8}
    except Exception:
        pass

    return {"bias": "UNKNOWN", "alignment": "UNKNOWN", "conviction_mult": 1.0}
```

### Apply Conviction Multiplier to Target

When bias is aligned, widen T2 by 20%. When counter-trend, tighten by 20%:

```python
# After calculating T2:
bias_info = await get_bias_alignment(direction)
conviction_mult = bias_info.get("conviction_mult", 1.0)
reward_distance = abs(t2 - entry)
adjusted_reward = reward_distance * conviction_mult
t2 = round(entry + adjusted_reward, 2) if direction == "LONG" else round(entry - adjusted_reward, 2)
```

---

## ITEM 8: UW Flow Hooks

These hooks read UW data from Redis if available. Spec 3 (CODEX-UW) writes the data. If Spec 3 isn't deployed yet, these return null gracefully — the signal still works.

### Add to `cta_scanner.py`

```python
async def get_uw_flow_confirmation(ticker: str, signal_direction: str) -> dict:
    """
    Read cached UW options flow data for this ticker.
    Data is written by Pivot's UW collector (Spec 3).
    Returns null fields if no UW data is available.
    """
    from database.redis_client import get_redis_client

    result = {
        "available": False,
        "net_premium": None,
        "flow_sentiment": None,
        "unusual_count": None,
        "confirmation": None,
        "conflict": None,
    }

    try:
        client = await get_redis_client()
        if not client:
            return result

        import json
        flow_raw = await client.get(f"uw:flow:{ticker}")
        if not flow_raw:
            return result

        flow = json.loads(flow_raw)
        result["available"] = True
        result["net_premium"] = flow.get("net_premium")
        result["flow_sentiment"] = flow.get("sentiment")
        result["unusual_count"] = flow.get("unusual_count")

        sentiment = flow.get("sentiment", "NEUTRAL")

        if signal_direction == "LONG" and sentiment == "BULLISH":
            result["confirmation"] = f"Bullish flow (${_format_premium(flow.get('net_premium', 0))} net calls, {flow.get('unusual_count', 0)} unusual trades)"
        elif signal_direction == "SHORT" and sentiment == "BEARISH":
            result["confirmation"] = f"Bearish flow (${_format_premium(abs(flow.get('net_premium', 0)))} net puts, {flow.get('unusual_count', 0)} unusual trades)"
        elif signal_direction == "LONG" and sentiment == "BEARISH":
            result["conflict"] = "⚠️ Heavy put buying despite bullish technical setup"
        elif signal_direction == "SHORT" and sentiment == "BULLISH":
            result["conflict"] = "⚠️ Heavy call buying despite bearish technical setup"

    except Exception:
        pass

    return result


def _format_premium(amount: float) -> str:
    """Format dollar amounts: 1500000 → '1.5M', 250000 → '250K'."""
    if abs(amount) >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M"
    elif abs(amount) >= 1_000:
        return f"{amount / 1_000:.0f}K"
    return f"{amount:.0f}"
```

---

## ITEM 9: Signal Invalidation Levels

### Logic

Each signal gets an `invalidation_level` — the price at which the thesis structurally breaks. This is different from the stop loss (which is where you exit for risk management). The invalidation level is where the signal is no longer valid, even if you haven't entered yet.

### Implementation

Add to each check function's return dict:

```python
# GOLDEN_TOUCH: Thesis breaks if price closes below 50 SMA (deeper than a 20 SMA pullback)
"invalidation_level": round(smas["sma50"] - (atr * 0.25), 2) if smas.get("sma50") else None,
"invalidation_reason": "Price close below 50 SMA invalidates pullback thesis",

# PULLBACK_ENTRY: Thesis breaks if price closes below 120 SMA
"invalidation_level": round(smas["sma120"] - (atr * 0.25), 2) if smas.get("sma120") else None,
"invalidation_reason": "Price close below 120 SMA invalidates recovery thesis",

# TWO_CLOSE_VOLUME: Thesis breaks if price closes below breakout level (the pre-breakout high)
"invalidation_level": round(price - (atr * 1.5), 2),
"invalidation_reason": "Price close below breakout level negates volume confirmation",

# ZONE_UPGRADE: Thesis breaks if zone downgrades back
"invalidation_level": round(smas["sma50"], 2) if smas.get("sma50") else None,
"invalidation_reason": "Zone downgrade invalidates thesis",

# TRAPPED_LONGS: Thesis breaks if price reclaims 200 SMA (for short)
"invalidation_level": round(smas["sma200"] + (atr * 0.25), 2) if smas.get("sma200") else None,
"invalidation_reason": "Price reclaiming 200 SMA negates trapped longs thesis",

# TRAPPED_SHORTS: Thesis breaks if price drops below 200 SMA (for long)
"invalidation_level": round(smas["sma200"] - (atr * 0.25), 2) if smas.get("sma200") else None,
"invalidation_reason": "Price losing 200 SMA negates trapped shorts thesis",
```

---

## ITEM 10: Updated Signal Output Shape

### Current Shape (from Spec 1)

```json
{
    "signal_id": "NVDA_GOLDEN_TOUCH_20260209",
    "timestamp": "2026-02-09T14:30:00",
    "symbol": "NVDA",
    "signal_type": "GOLDEN_TOUCH",
    "direction": "LONG",
    "confidence": "HIGH",
    "priority": 80,
    "description": "Golden touch: Price pulled back to 20 SMA with volume",
    "setup": {
        "entry": 845.20,
        "stop": 838.50,
        "target": 868.90,
        "rr_ratio": 3.5
    }
}
```

### New Shape (after this spec)

```json
{
    "signal_id": "NVDA_GOLDEN_TOUCH_20260209",
    "timestamp": "2026-02-09T14:30:00",
    "symbol": "NVDA",
    "signal_type": "GOLDEN_TOUCH",
    "direction": "LONG",
    "confidence": "HIGH",
    "priority": 145,
    "description": "Golden touch: Price pulled back to 20 SMA with volume",
    "setup": {
        "entry": 845.20,
        "entry_window": {
            "entry_low": 840.12,
            "entry_high": 848.50
        },
        "stop": 838.50,
        "t1": 855.80,
        "t2": 868.90,
        "rr_ratio": 3.5,
        "invalidation_level": 825.30,
        "invalidation_reason": "Price close below 50 SMA invalidates pullback thesis"
    },
    "setup_context": {
        "stop_anchor": "20 SMA (840.12) - 0.25 ATR buffer",
        "t1_anchor": "Recent swing high / 0.5x reward",
        "t2_anchor": "3.5 ATR (MAX_LONG profile)",
        "rr_profile": ["GOLDEN_TOUCH", "MAX_LONG", 1.0, 3.5],
        "sector_wind": {
            "sector": "Technology",
            "etf": "XLK",
            "etf_zone": "MAX_LONG",
            "alignment": "TAILWIND"
        },
        "bias_alignment": {
            "bias": "TORO_MINOR",
            "alignment": "ALIGNED",
            "conviction_mult": 1.2
        },
        "uw_flow": {
            "available": true,
            "confirmation": "Bullish flow ($1.2M net calls, 3 unusual trades)",
            "conflict": null
        },
        "confluence": {
            "count": 2,
            "signal_types": ["GOLDEN_TOUCH", "TRAPPED_SHORTS"],
            "boost": 65,
            "combo": "Squeeze into trend (Golden Touch + Trapped Shorts)"
        }
    }
}
```

**Key points:**
- `setup.target` is REMOVED. Replaced by `setup.t1` and `setup.t2`.
- `setup.entry_window` is NEW — defines valid entry range.
- `setup.invalidation_level` is NEW — structural thesis break price.
- `setup_context` is entirely NEW — all the "why" behind the numbers. Frontend can show/hide this.
- `confluence` is NEW — only present when multiple signals fired on the same ticker.
- `uw_flow` fields are null when UW data isn't available. This is expected pre-Spec 3.
- The existing `trapped_trader_data` field on trapped trader signals remains alongside `setup_context`.

### Backward Compatibility

The `setup.target` field is being replaced by `t1`/`t2`. Anywhere in the codebase that reads `signal["setup"]["target"]`, update to read `signal["setup"]["t2"]`. Search for these locations:

- `build_combined_recommendation()` in `analyzer.py`
- `analyze_ticker_cta_from_df()` in `cta_scanner.py`
- Signal display in frontend
- Signal cache/read logic in `bias_scheduler.py`

Add a compatibility shim: `setup["target"] = setup["t2"]` so old code doesn't break immediately. Remove the shim once all references are updated.

---

## ITEM 11: Historical Hit Rate Tracking

### New Table: `signal_outcomes`

Add to `init_database()` in `postgres_client.py`:

```sql
CREATE TABLE IF NOT EXISTS signal_outcomes (
    id SERIAL PRIMARY KEY,
    signal_id VARCHAR(100) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    signal_type VARCHAR(50) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    cta_zone VARCHAR(30),
    entry DECIMAL(12, 2),
    stop DECIMAL(12, 2),
    t1 DECIMAL(12, 2),
    t2 DECIMAL(12, 2),
    invalidation_level DECIMAL(12, 2),
    created_at TIMESTAMP NOT NULL,
    outcome VARCHAR(20),
        -- 'HIT_T1', 'HIT_T2', 'STOPPED_OUT', 'INVALIDATED', 'EXPIRED', 'PENDING'
    outcome_at TIMESTAMP,
    outcome_price DECIMAL(12, 2),
    max_favorable DECIMAL(12, 2),
        -- How far price moved in signal direction before outcome (for optimization)
    max_adverse DECIMAL(12, 2),
        -- How far price moved against signal before outcome
    days_to_outcome INTEGER,
    UNIQUE(signal_id)
);

CREATE INDEX IF NOT EXISTS idx_signal_outcomes_symbol ON signal_outcomes(symbol);
CREATE INDEX IF NOT EXISTS idx_signal_outcomes_type ON signal_outcomes(signal_type);
CREATE INDEX IF NOT EXISTS idx_signal_outcomes_outcome ON signal_outcomes(outcome);
```

### On Signal Creation

When a new signal is cached in `run_cta_scan_scheduled()`, also insert into `signal_outcomes`:

```python
# After cache_signal():
try:
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO signal_outcomes
                (signal_id, symbol, signal_type, direction, cta_zone,
                 entry, stop, t1, t2, invalidation_level, created_at, outcome)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), 'PENDING')
            ON CONFLICT (signal_id) DO NOTHING
        """,
            signal["signal_id"], signal["symbol"], signal["signal_type"],
            signal["direction"], signal.get("setup_context", {}).get("rr_profile", [None, None])[1],
            signal["setup"]["entry"], signal["setup"]["stop"],
            signal["setup"].get("t1"), signal["setup"].get("t2"),
            signal["setup"].get("invalidation_level"),
        )
except Exception as e:
    logger.warning(f"Failed to record signal outcome: {e}")
```

### Nightly Scoring Job

Create `backend/jobs/score_signals.py`:

```python
"""
Nightly batch job that checks PENDING signals against subsequent price action.
Run via scheduler at 9 PM ET daily (after market close).
"""
import logging
from datetime import datetime, timedelta
import yfinance as yf

logger = logging.getLogger(__name__)

MAX_SIGNAL_AGE_DAYS = 10  # Signals older than this auto-expire


async def score_pending_signals():
    """
    For each PENDING signal:
    1. Fetch price data from signal creation date to now
    2. Check if price hit T1, T2, stop, or invalidation level
    3. Update outcome accordingly
    """
    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        pending = await conn.fetch(
            "SELECT * FROM signal_outcomes WHERE outcome = 'PENDING'"
        )

    logger.info(f"Scoring {len(pending)} pending signals")

    for row in pending:
        try:
            signal_date = row["created_at"]
            age_days = (datetime.utcnow() - signal_date).days

            # Auto-expire old signals
            if age_days > MAX_SIGNAL_AGE_DAYS:
                await _update_outcome(pool, row["signal_id"], "EXPIRED", None, age_days)
                continue

            # Fetch price data since signal creation
            ticker = yf.Ticker(row["symbol"])
            start = signal_date.strftime("%Y-%m-%d")
            df = ticker.history(start=start)

            if df.empty:
                continue

            direction = row["direction"]
            entry = float(row["entry"])
            stop = float(row["stop"]) if row["stop"] else None
            t1 = float(row["t1"]) if row["t1"] else None
            t2 = float(row["t2"]) if row["t2"] else None
            invalidation = float(row["invalidation_level"]) if row["invalidation_level"] else None

            # Track max favorable / adverse excursion
            if direction == "LONG":
                max_favorable = float(df["High"].max()) - entry
                max_adverse = entry - float(df["Low"].min())
            else:
                max_favorable = entry - float(df["Low"].min())
                max_adverse = float(df["High"].max()) - entry

            # Check outcomes in order: invalidation → stop → T1 → T2
            outcome = None
            outcome_price = None

            for _, bar in df.iterrows():
                if direction == "LONG":
                    if invalidation and bar["Close"] < invalidation:
                        outcome = "INVALIDATED"
                        outcome_price = round(bar["Close"], 2)
                        break
                    if stop and bar["Low"] <= stop:
                        outcome = "STOPPED_OUT"
                        outcome_price = stop
                        break
                    if t2 and bar["High"] >= t2:
                        outcome = "HIT_T2"
                        outcome_price = t2
                        break
                    if t1 and not outcome and bar["High"] >= t1:
                        outcome = "HIT_T1"
                        outcome_price = t1
                        # Don't break — keep checking for T2
                else:  # SHORT
                    if invalidation and bar["Close"] > invalidation:
                        outcome = "INVALIDATED"
                        outcome_price = round(bar["Close"], 2)
                        break
                    if stop and bar["High"] >= stop:
                        outcome = "STOPPED_OUT"
                        outcome_price = stop
                        break
                    if t2 and bar["Low"] <= t2:
                        outcome = "HIT_T2"
                        outcome_price = t2
                        break
                    if t1 and not outcome and bar["Low"] <= t1:
                        outcome = "HIT_T1"
                        outcome_price = t1

            if outcome:
                days_to = (datetime.utcnow() - signal_date).days
                await _update_outcome(
                    pool, row["signal_id"], outcome, outcome_price, days_to,
                    round(max_favorable, 2), round(max_adverse, 2),
                )

        except Exception as e:
            logger.warning(f"Error scoring signal {row['signal_id']}: {e}")


async def _update_outcome(pool, signal_id, outcome, price, days, max_fav=None, max_adv=None):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE signal_outcomes
            SET outcome = $1, outcome_price = $2, outcome_at = NOW(),
                days_to_outcome = $3, max_favorable = $4, max_adverse = $5
            WHERE signal_id = $6
        """, outcome, price, days, max_fav, max_adv, signal_id)


async def get_hit_rates() -> dict:
    """
    Return hit rates by signal_type and zone.
    Used by the dashboard to show historical performance.
    """
    from database.postgres_client import get_postgres_client
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT signal_type, cta_zone, outcome, COUNT(*) as cnt
            FROM signal_outcomes
            WHERE outcome != 'PENDING'
            GROUP BY signal_type, cta_zone, outcome
            ORDER BY signal_type, cta_zone
        """)

    # Aggregate into hit rate percentages
    from collections import defaultdict
    stats = defaultdict(lambda: defaultdict(int))
    for row in rows:
        key = (row["signal_type"], row["cta_zone"] or "ANY")
        stats[key][row["outcome"]] += row["cnt"]
        stats[key]["total"] += row["cnt"]

    result = {}
    for (sig_type, zone), outcomes in stats.items():
        total = outcomes["total"]
        result[f"{sig_type}|{zone}"] = {
            "total": total,
            "hit_t1_pct": round(outcomes.get("HIT_T1", 0) / total * 100, 1) if total > 0 else 0,
            "hit_t2_pct": round(outcomes.get("HIT_T2", 0) / total * 100, 1) if total > 0 else 0,
            "stopped_pct": round(outcomes.get("STOPPED_OUT", 0) / total * 100, 1) if total > 0 else 0,
            "invalidated_pct": round(outcomes.get("INVALIDATED", 0) / total * 100, 1) if total > 0 else 0,
            "expired_pct": round(outcomes.get("EXPIRED", 0) / total * 100, 1) if total > 0 else 0,
        }

    return result
```

### Schedule the Nightly Job

Add to `bias_scheduler.py` (or to Pivot's cron_runner if preferred):

```python
from jobs.score_signals import score_pending_signals

scheduler.add_job(
    score_pending_signals,
    CronTrigger(day_of_week="mon-fri", hour=21, minute=0, timezone=TZ),
    id="score_signals",
)
```

### API Endpoint for Hit Rates

Add to `backend/api/analyzer.py`:

```python
@router.get("/signals/hit-rates")
async def get_signal_hit_rates():
    """Return historical hit rates by signal type and zone."""
    from jobs.score_signals import get_hit_rates
    rates = await get_hit_rates()
    return {"status": "success", "hit_rates": rates}
```

---

## COMPLETE FILE LIST

### New Files
- `backend/config/signal_profiles.py` — R:R profile lookup table
- `backend/jobs/score_signals.py` — nightly signal outcome scoring
- `backend/jobs/__init__.py` — empty init

### Modified Files
- `backend/scanners/cta_scanner.py` — all check functions get profile-based R:R, SMA-anchored stops, T1/T2, entry windows, invalidation levels; add `score_confluence()`, `get_sector_wind()`, `get_bias_alignment()`, `get_uw_flow_confirmation()`, `calculate_smart_stop()`, `calculate_entry_window()`
- `backend/api/analyzer.py` — add `/signals/hit-rates` endpoint, update `build_combined_recommendation()` to use `t2` instead of `target`
- `backend/scheduler/bias_scheduler.py` — add signal outcome recording after cache_signal(), add nightly scoring job
- `backend/database/postgres_client.py` — add `signal_outcomes` table to `init_database()`

### Do NOT Modify
- `backend/config/sectors.py` — created in Spec 1, used as-is here
- `backend/scanners/universe.py` — no changes needed
- `backend/api/watchlist.py` — no changes needed
