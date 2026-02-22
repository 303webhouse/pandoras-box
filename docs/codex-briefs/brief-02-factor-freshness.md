# Codex Brief 02: Factor Freshness Indicator in EOD Brief

**Date:** February 22, 2026
**Priority:** HIGH
**Scope:** Enhance `pivot2_brief.py` (EOD mode) + Railway API `/bias/composite` response to surface per-factor freshness data
**Estimated effort:** ~30 min agent time

---

## Problem

The EOD brief currently reports factor health as a single aggregate line: "13/21 factors fresh (8 stale)." This tells Nick _how many_ factors are stale but not _which ones matter_ or _how stale they are_. He can't tell the difference between a factor that went stale 2 hours ago vs. one that hasn't updated in 3 days. He also can't tell which "active" factors are actually running on fallback data (returning neutral scores because no real data exists).

This makes it hard to judge how trustworthy the composite bias actually is on any given day.

---

## What This Changes

Two things:

1. **`pivot2_brief.py`** — Enrich the `factor_health` payload in the EOD data with per-factor freshness details, so the LLM can write a smarter factor health section.
2. **EOD prompt template** — Update the LLM instructions to use the enriched data and produce a categorized factor health readout.

**No backend (Railway) changes required.** The composite API already returns everything needed: per-factor timestamps, source, fallback flags, and staleness thresholds are in `FACTOR_CONFIG` in `composite.py`. The enrichment happens client-side in the brief script.

---

## Current State

### What the composite API returns per factor (when not null):

```json
{
  "factor_id": "vix_regime",
  "score": 0.0,
  "signal": "NEUTRAL",
  "detail": "VIX at 19.1 (elevated)",
  "timestamp": "2026-02-22T08:08:00.232861",
  "source": "yfinance",
  "raw_data": { "vix": 19.09 },
  "metadata": {}
}
```

For fallback factors (no real data, scored neutral):
```json
{
  "factor_id": "options_sentiment",
  "score": 0.0,
  "signal": "NEUTRAL",
  "detail": "No UW Market Tide data received; neutral fallback",
  "timestamp": "2026-02-22T08:08:01.326173",
  "source": "fallback",
  "raw_data": { "fallback": true },
  "metadata": { "timestamp_source": "fallback" }
}
```

Null factors (completely stale — no reading at all):
```json
"vix_term": null
```

### What the composite API returns at the top level:

```json
{
  "active_factors": ["vix_regime", "spy_trend_intraday", ...],
  "stale_factors": ["vix_term", "tick_breadth", "credit_spreads", ...],
  "unverifiable_factors": ["options_sentiment", "put_call_ratio"],
  "confidence": "HIGH"
}
```

### Current factor_health in EOD payload (built in `fetch_pandora_data()`):

```python
payload["factor_health"] = {
    "fresh": max(total - len(stale_names), 0),
    "total": total,
    "stale_count": len(stale_names),
    "stale_factors": stale_names,
}
```

This is the aggregate-only view that needs enrichment.

---

## Implementation

### Step 1: Define factor metadata (in `pivot2_brief.py`)

Add a constant dict near the top of the file that maps factor IDs to their staleness thresholds, weights, and timeframe categories. This mirrors `FACTOR_CONFIG` from `composite.py` but only the fields needed for freshness reporting:

```python
FACTOR_META = {
    # Intraday (fast-moving, 4-8h staleness)
    "vix_term":          {"staleness_hours": 4,    "weight": 0.07, "timeframe": "intraday", "label": "VIX Term Structure"},
    "tick_breadth":      {"staleness_hours": 4,    "weight": 0.06, "timeframe": "intraday", "label": "TICK Breadth"},
    "vix_regime":        {"staleness_hours": 4,    "weight": 0.05, "timeframe": "intraday", "label": "VIX Regime"},
    "spy_trend_intraday":{"staleness_hours": 4,    "weight": 0.05, "timeframe": "intraday", "label": "SPY Intraday Trend"},
    "breadth_momentum":  {"staleness_hours": 24,   "weight": 0.04, "timeframe": "intraday", "label": "Breadth Momentum"},
    "options_sentiment": {"staleness_hours": 8,    "weight": 0.03, "timeframe": "intraday", "label": "Options Sentiment (UW)"},
    # Swing (multi-day, 24-72h staleness)
    "credit_spreads":    {"staleness_hours": 48,   "weight": 0.09, "timeframe": "swing",    "label": "Credit Spreads"},
    "market_breadth":    {"staleness_hours": 48,   "weight": 0.09, "timeframe": "swing",    "label": "Market Breadth"},
    "sector_rotation":   {"staleness_hours": 48,   "weight": 0.07, "timeframe": "swing",    "label": "Sector Rotation"},
    "spy_200sma_distance":{"staleness_hours": 24,  "weight": 0.07, "timeframe": "swing",    "label": "SPY 200 SMA Distance"},
    "high_yield_oas":    {"staleness_hours": 48,   "weight": 0.05, "timeframe": "swing",    "label": "High Yield OAS"},
    "dollar_smile":      {"staleness_hours": 48,   "weight": 0.04, "timeframe": "swing",    "label": "Dollar Smile"},
    "put_call_ratio":    {"staleness_hours": 72,   "weight": 0.04, "timeframe": "swing",    "label": "Put/Call Ratio"},
    # Macro (slow-moving, 48-1080h staleness)
    "yield_curve":       {"staleness_hours": 72,   "weight": 0.05, "timeframe": "macro",    "label": "Yield Curve"},
    "initial_claims":    {"staleness_hours": 168,  "weight": 0.05, "timeframe": "macro",    "label": "Initial Claims"},
    "sahm_rule":         {"staleness_hours": 168,  "weight": 0.04, "timeframe": "macro",    "label": "Sahm Rule"},
    "copper_gold_ratio": {"staleness_hours": 48,   "weight": 0.03, "timeframe": "macro",    "label": "Copper/Gold Ratio"},
    "dxy_trend":         {"staleness_hours": 48,   "weight": 0.05, "timeframe": "macro",    "label": "DXY Trend"},
    "excess_cape":       {"staleness_hours": 168,  "weight": 0.03, "timeframe": "macro",    "label": "Excess CAPE Yield"},
    "ism_manufacturing": {"staleness_hours": 720,  "weight": 0.03, "timeframe": "macro",    "label": "ISM Manufacturing"},
    "savita":            {"staleness_hours": 1080, "weight": 0.02, "timeframe": "macro",    "label": "BofA Sell Side (Savita)"},
}
```

### Step 2: Build enriched factor_health in `fetch_pandora_data()`

Replace the existing `factor_health` block in the `if mode == "eod"` branch with an enriched version:

```python
if mode == "eod":
    # ... existing convergence + uw_snapshots fetches ...

    factors = (composite or {}).get("factors") if isinstance(composite, dict) else {}
    if not isinstance(factors, dict):
        factors = {}

    stale_list = (composite or {}).get("stale_factors") if isinstance(composite, dict) else []
    if not isinstance(stale_list, list):
        stale_list = []
    stale_set = set(str(s) for s in stale_list if isinstance(s, str))

    active_list = (composite or {}).get("active_factors") if isinstance(composite, dict) else []
    if not isinstance(active_list, list):
        active_list = []

    unverifiable_list = (composite or {}).get("unverifiable_factors") if isinstance(composite, dict) else []
    if not isinstance(unverifiable_list, list):
        unverifiable_list = []
    unverifiable_set = set(str(s) for s in unverifiable_list if isinstance(s, str))

    now = now_utc()
    factor_details = []

    for fid, meta in FACTOR_META.items():
        entry = {
            "factor_id": fid,
            "label": meta["label"],
            "timeframe": meta["timeframe"],
            "weight": meta["weight"],
            "staleness_hours": meta["staleness_hours"],
        }

        factor_data = factors.get(fid)
        if factor_data is None or fid in stale_set:
            entry["status"] = "STALE"
            entry["age_hours"] = None
            entry["source"] = None
        elif fid in unverifiable_set:
            entry["status"] = "FALLBACK"
            entry["age_hours"] = 0
            entry["source"] = "fallback"
        else:
            ts_raw = factor_data.get("timestamp") if isinstance(factor_data, dict) else None
            if ts_raw:
                try:
                    factor_ts = parse_iso_ts(str(ts_raw)) if isinstance(ts_raw, str) else now
                    age_hours = round((now - factor_ts).total_seconds() / 3600, 1)
                except Exception:
                    age_hours = None
            else:
                age_hours = None

            source = factor_data.get("source", "unknown") if isinstance(factor_data, dict) else "unknown"
            entry["status"] = "FRESH"
            entry["age_hours"] = age_hours
            entry["source"] = source

        factor_details.append(entry)

    # Group counts by timeframe
    timeframe_health = {}
    for tf in ("intraday", "swing", "macro"):
        tf_factors = [f for f in factor_details if f["timeframe"] == tf]
        fresh_count = sum(1 for f in tf_factors if f["status"] == "FRESH")
        fallback_count = sum(1 for f in tf_factors if f["status"] == "FALLBACK")
        stale_count = sum(1 for f in tf_factors if f["status"] == "STALE")
        total_weight = sum(f["weight"] for f in tf_factors)
        active_weight = sum(f["weight"] for f in tf_factors if f["status"] in ("FRESH", "FALLBACK"))
        timeframe_health[tf] = {
            "fresh": fresh_count,
            "fallback": fallback_count,
            "stale": stale_count,
            "total": len(tf_factors),
            "total_weight": round(total_weight, 2),
            "active_weight": round(active_weight, 2),
        }

    total_factors = len(FACTOR_META)
    total_fresh = sum(1 for f in factor_details if f["status"] == "FRESH")
    total_fallback = sum(1 for f in factor_details if f["status"] == "FALLBACK")
    total_stale = sum(1 for f in factor_details if f["status"] == "STALE")

    payload["factor_health"] = {
        "summary": {
            "fresh": total_fresh,
            "fallback": total_fallback,
            "stale": total_stale,
            "total": total_factors,
            "confidence": (composite or {}).get("confidence", "UNKNOWN"),
        },
        "by_timeframe": timeframe_health,
        "factors": factor_details,
    }
```

### Step 3: Update the EOD prompt template in `build_prompt()`

Replace the full EOD instructions block with:

```python
    else:
        instructions = (
            "Generate the EOD summary. Follow the format from your identity/personality context.\n\n"
            "Lead with the day verdict: did the bias call play out?\n\n"
            "FACTOR HEALTH section (use data.factor_health):\n"
            "- Summary line: X/Y factors fresh, Z on fallback, W stale | Confidence: {confidence}\n"
            "- If stale_count > 5: 'WARNING: Low data confidence - too many stale factors.'\n"
            "- Group by timeframe (intraday, swing, macro). For each group show:\n"
            "  - How many fresh vs stale vs fallback\n"
            "  - Call out any factor that is STALE with high weight (>=0.05) as a blind spot\n"
            "  - Call out FALLBACK factors as 'scoring neutral but unverified'\n"
            "- If any fresh factor has age_hours > staleness_hours * 0.75, flag it as 'aging' (close to going stale)\n"
            "- End with a one-line data quality verdict: 'Data quality: GOOD/DEGRADED/POOR'\n"
            "  - GOOD: <=3 stale, no high-weight blind spots\n"
            "  - DEGRADED: 4-7 stale or 1+ high-weight blind spot\n"
            "  - POOR: 8+ stale or confidence LOW\n\n"
            "Signal Convergence section (last 24h):\n"
            "  - 'CONVERGENCE: {ticker} {direction} - confirmed by {source1}, {source2}'\n"
            "  - 2 sources = MODERATE, 3+ = HIGH\n"
            "  - If none: 'No signal convergence detected today.'\n\n"
            "UW Flow Intelligence from screenshots if provided:\n"
            "  - Market Tide read, Dark Pool positioning, GEX analysis\n"
            "  - If no screenshots: 'UW visual data not provided - flow analysis based on API data only.'\n\n"
            "Remaining sections:\n"
            "- Factor changes during session (what moved, what did not)\n"
            "- DEFCON events today\n"
            "- Notable flow activity\n"
            "- P&L across accounts if data available\n"
            "- Breakout account end-of-day status\n"
            "- Lessons or patterns worth noting\n"
            "- Setup for tomorrow (overnight bias lean)\n"
        )
```

---

## Example Output (What the LLM Should Produce)

The factor health section of the EOD brief should look something like this:

```
📊 FACTOR HEALTH: 13/21 fresh, 2 fallback, 8 stale | Confidence: HIGH

INTRADAY (4 fresh, 2 stale):
  ✅ VIX Regime — fresh (0.1h, yfinance)
  ✅ SPY Intraday Trend — fresh (0.1h, yfinance)
  ✅ Breadth Momentum — fresh (0.1h, yfinance)
  ⚠️ Options Sentiment — FALLBACK (scoring neutral, no UW data)
  ❌ VIX Term Structure — STALE (wt 0.07) ← BLIND SPOT
  ❌ TICK Breadth — STALE (wt 0.06) ← BLIND SPOT

SWING (4 fresh, 3 stale):
  ✅ SPY 200 SMA Distance — fresh (0.1h)
  ✅ High Yield OAS — fresh (0.1h, FRED)
  ✅ Yield Curve — fresh (0.1h, FRED)
  ⚠️ Put/Call Ratio — FALLBACK (scoring neutral, no CBOE data)
  ❌ Credit Spreads — STALE (wt 0.09) ← BLIND SPOT
  ❌ Market Breadth — STALE (wt 0.09) ← BLIND SPOT
  ❌ Sector Rotation — STALE (wt 0.07) ← BLIND SPOT

MACRO (5 fresh, 3 stale):
  ✅ Initial Claims, Sahm Rule, Copper/Gold, DXY Trend, ISM — all fresh
  ❌ Dollar Smile — STALE (wt 0.04)
  ❌ Excess CAPE — STALE (wt 0.03)
  ❌ Savita — STALE (wt 0.02)

Data quality: DEGRADED — Credit Spreads and Market Breadth (combined wt 0.18) are blind spots.
Composite bias may underweight risk appetite signals.
```

The LLM doesn't need to follow this format exactly — it should adapt based on what's actually stale/fresh. The key is that it now has the data to make per-factor judgments.

---

## Files Changed

| File | Change |
|------|--------|
| `/opt/openclaw/workspace/scripts/pivot2_brief.py` | Add `FACTOR_META` constant, enrich `factor_health` in `fetch_pandora_data()`, update EOD instructions in `build_prompt()` |

**No Railway backend changes.** No new API endpoints. No database changes. No other scripts affected.

---

## Testing

### Step 1: Dry run EOD brief

```bash
ssh root@188.245.250.2
su - openclaw
cd /opt/openclaw/workspace/scripts
python3 pivot2_brief.py --mode eod --dry-run 2>&1
```

Verify the JSON output includes the enriched `factor_health` with `summary`, `by_timeframe`, and `factors` arrays.

### Step 2: Check factor_health structure in output

In the dry-run JSON preview, confirm:
- Each factor has `status` (FRESH/FALLBACK/STALE), `age_hours`, `source`, `weight`, `timeframe`
- `by_timeframe` has correct counts for intraday/swing/macro
- `summary` has correct totals

### Step 3: Full EOD brief test

```bash
python3 pivot2_brief.py --mode eod --channel-id 1474135100521451813 --window-minutes 0
```

Read the posted brief in #pivot-ii. Confirm the factor health section:
- Lists factors grouped by timeframe
- Calls out high-weight stale factors as blind spots
- Flags fallback factors
- Ends with a data quality verdict

### Step 4: Verify morning brief unaffected

```bash
python3 pivot2_brief.py --mode morning --dry-run
```

Confirm morning mode still works and does NOT include the enriched factor_health (morning brief doesn't need it — it uses the simpler "flag stale factors" approach already in the prompt).

---

## Definition of Done

- [ ] `FACTOR_META` constant added to `pivot2_brief.py` with all 21 factors, correct weights/staleness/timeframes
- [ ] `fetch_pandora_data()` EOD branch builds enriched `factor_health` with per-factor details
- [ ] EOD prompt template updated to instruct LLM on factor health section format
- [ ] Dry-run produces correct enriched JSON
- [ ] Live EOD brief in Discord shows categorized factor health with blind spot callouts
- [ ] Morning brief unchanged and still works
- [ ] Script deployed to VPS at `/opt/openclaw/workspace/scripts/pivot2_brief.py`

---

## What This Does NOT Include

- No changes to Railway backend or composite API
- No changes to morning brief format (morning already flags stale factors simply)
- No new cron jobs or scripts
- No changes to factor collection or staleness thresholds
- No UI/frontend changes
