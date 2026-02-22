# Brief 02: Factor Freshness Indicator in EOD Brief

**Date:** February 22, 2026
**Priority:** HIGH
**Scope:** One file changed: `/opt/openclaw/workspace/scripts/pivot2_brief.py`
**Estimated effort:** ~20 min agent time

---

## Problem

The EOD brief reports factor health as a single aggregate: "13/21 fresh (8 stale)." Nick can't tell which factors are stale, how stale they are, or which "active" factors are just returning neutral fallback scores. He needs per-factor freshness to judge composite bias trustworthiness.

---

## What This Changes

One file, three edits:

1. **Add `FACTOR_META` constant** — Insert after line 20 (`MAX_IMAGE_COUNT = 6`)
2. **Replace `factor_health` block** — Swap the simple aggregate with enriched per-factor data
3. **Replace EOD prompt instructions** — Tell the LLM how to use the enriched data

**No backend/Railway changes.** The composite API already returns per-factor timestamps, sources, and fallback flags. Enrichment happens in the brief script.

---

## Edit 1 of 3: Add FACTOR_META constant

**Where:** Insert immediately AFTER this line (line 20):
```python
MAX_IMAGE_COUNT = 6
```

**Insert this block (add a blank line before it):**

```python

FACTOR_META = {
    # Intraday (fast-moving, 4-8h staleness)
    "vix_term":           {"staleness_hours": 4,    "weight": 0.07, "timeframe": "intraday", "label": "VIX Term Structure"},
    "tick_breadth":       {"staleness_hours": 4,    "weight": 0.06, "timeframe": "intraday", "label": "TICK Breadth"},
    "vix_regime":         {"staleness_hours": 4,    "weight": 0.05, "timeframe": "intraday", "label": "VIX Regime"},
    "spy_trend_intraday": {"staleness_hours": 4,    "weight": 0.05, "timeframe": "intraday", "label": "SPY Intraday Trend"},
    "breadth_momentum":   {"staleness_hours": 24,   "weight": 0.04, "timeframe": "intraday", "label": "Breadth Momentum"},
    "options_sentiment":  {"staleness_hours": 8,    "weight": 0.03, "timeframe": "intraday", "label": "Options Sentiment (UW)"},
    # Swing (multi-day, 24-72h staleness)
    "credit_spreads":     {"staleness_hours": 48,   "weight": 0.09, "timeframe": "swing",    "label": "Credit Spreads"},
    "market_breadth":     {"staleness_hours": 48,   "weight": 0.09, "timeframe": "swing",    "label": "Market Breadth"},
    "sector_rotation":    {"staleness_hours": 48,   "weight": 0.07, "timeframe": "swing",    "label": "Sector Rotation"},
    "spy_200sma_distance":{"staleness_hours": 24,   "weight": 0.07, "timeframe": "swing",    "label": "SPY 200 SMA Distance"},
    "high_yield_oas":     {"staleness_hours": 48,   "weight": 0.05, "timeframe": "swing",    "label": "High Yield OAS"},
    "dollar_smile":       {"staleness_hours": 48,   "weight": 0.04, "timeframe": "swing",    "label": "Dollar Smile"},
    "put_call_ratio":     {"staleness_hours": 72,   "weight": 0.04, "timeframe": "swing",    "label": "Put/Call Ratio"},
    # Macro (slow-moving, 48-1080h staleness)
    "yield_curve":        {"staleness_hours": 72,   "weight": 0.05, "timeframe": "macro",    "label": "Yield Curve"},
    "initial_claims":     {"staleness_hours": 168,  "weight": 0.05, "timeframe": "macro",    "label": "Initial Claims"},
    "sahm_rule":          {"staleness_hours": 168,  "weight": 0.04, "timeframe": "macro",    "label": "Sahm Rule"},
    "copper_gold_ratio":  {"staleness_hours": 48,   "weight": 0.03, "timeframe": "macro",    "label": "Copper/Gold Ratio"},
    "dxy_trend":          {"staleness_hours": 48,   "weight": 0.05, "timeframe": "macro",    "label": "DXY Trend"},
    "excess_cape":        {"staleness_hours": 168,  "weight": 0.03, "timeframe": "macro",    "label": "Excess CAPE Yield"},
    "ism_manufacturing":  {"staleness_hours": 720,  "weight": 0.03, "timeframe": "macro",    "label": "ISM Manufacturing"},
    "savita":             {"staleness_hours": 1080, "weight": 0.02, "timeframe": "macro",    "label": "BofA Sell Side (Savita)"},
}
```

These values are copied from `backend/bias_engine/composite.py` `FACTOR_CONFIG`. They must stay in sync — if a factor is added/removed/reweighted there, update here too.

---

## Edit 2 of 3: Replace factor_health block in `fetch_pandora_data()`

**Find this exact block** (starts at line 226, inside the `if mode == "eod":` branch):

```python
        factors = (composite or {}).get("factors") if isinstance(composite, dict) else {}
        if not isinstance(factors, dict):
            factors = {}

        stale = (composite or {}).get("stale_factors") if isinstance(composite, dict) else []
        if not isinstance(stale, list):
            stale = []

        total = len(factors)
        stale_names = [str(item) for item in stale if isinstance(item, str)]
        payload["factor_health"] = {
            "fresh": max(total - len(stale_names), 0),
            "total": total,
            "stale_count": len(stale_names),
            "stale_factors": stale_names,
        }
```

**Replace with:**

```python
        factors = (composite or {}).get("factors") if isinstance(composite, dict) else {}
        if not isinstance(factors, dict):
            factors = {}

        stale_list = (composite or {}).get("stale_factors") if isinstance(composite, dict) else []
        if not isinstance(stale_list, list):
            stale_list = []
        stale_set = set(str(s) for s in stale_list if isinstance(s, str))

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
                age_hours = None
                if ts_raw and isinstance(ts_raw, str):
                    try:
                        factor_ts = parse_iso_ts(ts_raw)
                        age_hours = round((now - factor_ts).total_seconds() / 3600, 1)
                    except Exception:
                        pass
                source = factor_data.get("source", "unknown") if isinstance(factor_data, dict) else "unknown"
                entry["status"] = "FRESH"
                entry["age_hours"] = age_hours
                entry["source"] = source

            factor_details.append(entry)

        timeframe_health = {}
        for tf in ("intraday", "swing", "macro"):
            tf_factors = [f for f in factor_details if f["timeframe"] == tf]
            timeframe_health[tf] = {
                "fresh": sum(1 for f in tf_factors if f["status"] == "FRESH"),
                "fallback": sum(1 for f in tf_factors if f["status"] == "FALLBACK"),
                "stale": sum(1 for f in tf_factors if f["status"] == "STALE"),
                "total": len(tf_factors),
                "total_weight": round(sum(f["weight"] for f in tf_factors), 2),
                "active_weight": round(sum(f["weight"] for f in tf_factors if f["status"] in ("FRESH", "FALLBACK")), 2),
            }

        payload["factor_health"] = {
            "summary": {
                "fresh": sum(1 for f in factor_details if f["status"] == "FRESH"),
                "fallback": sum(1 for f in factor_details if f["status"] == "FALLBACK"),
                "stale": sum(1 for f in factor_details if f["status"] == "STALE"),
                "total": len(FACTOR_META),
                "confidence": (composite or {}).get("confidence", "UNKNOWN"),
            },
            "by_timeframe": timeframe_health,
            "factors": factor_details,
        }
```

**Important:** The two lines ABOVE this block (`payload["convergence"]` and `payload["uw_snapshots_api"]`) must remain untouched. The line BELOW (`return payload`) must remain untouched.

---

## Edit 3 of 3: Replace EOD prompt instructions in `build_prompt()`

**Find this exact block** (starts at line 276):

```python
    else:
        instructions = (
            "Generate the EOD summary. Follow the format from your identity/personality context.\n\n"
            "Lead with the day verdict: did the bias call play out?\n"
            "- Factor Health line: fresh/total fresh (stale count and names)\n"
            "- If stale_count > 5: \"WARNING: Low data confidence - factors stale. Composite bias may be unreliable.\"\n"
            "- Signal Convergence section (last 24h):\n"
            "  - \"CONVERGENCE: {ticker} {direction} - confirmed by {source1}, {source2}\"\n"
            "  - 2 sources = MODERATE, 3+ = HIGH\n"
            "  - If none: \"No signal convergence detected today.\"\n"
            "- UW Flow Intelligence from screenshots if provided:\n"
            "  - Market Tide read, Dark Pool positioning, GEX analysis\n"
            "  - If no screenshots: \"UW visual data not provided - flow analysis based on API data only.\"\n"
            "- Factor changes during session (what moved, what did not)\n"
            "- DEFCON events today\n"
            "- Notable flow activity\n"
            "- P&L across accounts if data available\n"
            "- Breakout account end-of-day status\n"
            "- Lessons or patterns worth noting\n"
            "- Setup for tomorrow (overnight bias lean)\n"
        )
```

**Replace with:**

```python
    else:
        instructions = (
            "Generate the EOD summary. Follow the format from your identity/personality context.\n\n"
            "Lead with the day verdict: did the bias call play out?\n\n"
            "FACTOR HEALTH section (use data.factor_health):\n"
            "- Summary line: X/Y factors fresh, Z on fallback, W stale | Confidence: {confidence}\n"
            "- If summary.stale > 5: 'WARNING: Low data confidence - too many stale factors.'\n"
            "- Group by timeframe (intraday, swing, macro). For each group show:\n"
            "  - How many fresh vs stale vs fallback\n"
            "  - Call out any factor with status STALE and weight >= 0.05 as a blind spot\n"
            "  - Call out FALLBACK factors as 'scoring neutral but unverified'\n"
            "- If any FRESH factor has age_hours > staleness_hours * 0.75, flag it as 'aging'\n"
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

**Important:** The line immediately after this block (`combined = {`) must remain untouched. The morning brief `if mode == "morning":` block above must remain untouched.

---

## Verification: What the enriched factor_health JSON looks like

After Edit 2, the EOD `data.factor_health` in the LLM prompt will contain:

```json
{
  "summary": {
    "fresh": 11,
    "fallback": 2,
    "stale": 8,
    "total": 21,
    "confidence": "HIGH"
  },
  "by_timeframe": {
    "intraday": {"fresh": 3, "fallback": 1, "stale": 2, "total": 6, "total_weight": 0.30, "active_weight": 0.17},
    "swing":    {"fresh": 3, "fallback": 1, "stale": 3, "total": 7, "total_weight": 0.45, "active_weight": 0.16},
    "macro":    {"fresh": 5, "fallback": 0, "stale": 3, "total": 8, "total_weight": 0.30, "active_weight": 0.20}
  },
  "factors": [
    {"factor_id": "vix_term", "label": "VIX Term Structure", "timeframe": "intraday", "weight": 0.07, "staleness_hours": 4, "status": "STALE", "age_hours": null, "source": null},
    {"factor_id": "vix_regime", "label": "VIX Regime", "timeframe": "intraday", "weight": 0.05, "staleness_hours": 4, "status": "FRESH", "age_hours": 0.1, "source": "yfinance"},
    {"factor_id": "options_sentiment", "label": "Options Sentiment (UW)", "timeframe": "intraday", "weight": 0.03, "staleness_hours": 8, "status": "FALLBACK", "age_hours": 0, "source": "fallback"}
  ]
}
```

(Showing 3 example entries — actual output will have all 21 factors.)

The LLM uses this to write a categorized factor health section with blind spot callouts. The exact formatting is up to the LLM — it just needs the data.

---

## Testing

### Test 1: Dry run EOD brief

```bash
ssh root@188.245.250.2
su - openclaw
cd /opt/openclaw/workspace/scripts
python3 pivot2_brief.py --mode eod --dry-run 2>&1
```

**Pass criteria:** JSON output includes `factor_health` with `summary`, `by_timeframe`, and `factors` keys. Each factor entry has `status`, `age_hours`, `source`, `weight`, `timeframe`.

### Test 2: Verify morning brief unaffected

```bash
python3 pivot2_brief.py --mode morning --dry-run 2>&1
```

**Pass criteria:** Morning mode still works. Output does NOT contain the enriched `factor_health` (morning uses the simpler factor flag approach).

### Test 3: Live EOD brief

```bash
python3 pivot2_brief.py --mode eod --channel-id 1474135100521451813 --window-minutes 0
```

**Pass criteria:** Brief posts to #pivot-ii. Factor health section groups factors by timeframe, calls out high-weight stale factors as blind spots, flags fallback factors, ends with GOOD/DEGRADED/POOR verdict.

---

## Definition of Done

- [ ] `FACTOR_META` constant inserted after `MAX_IMAGE_COUNT = 6` with all 21 factors
- [ ] `factor_health` block in `fetch_pandora_data()` replaced with enriched version
- [ ] EOD instructions in `build_prompt()` replaced with categorized factor health instructions
- [ ] `python3 pivot2_brief.py --mode eod --dry-run` produces enriched JSON
- [ ] `python3 pivot2_brief.py --mode morning --dry-run` still works unchanged
- [ ] Live EOD brief in #pivot-ii shows categorized factor health with blind spots
- [ ] No other files changed

---

## Scope Boundaries

- **Only file changed:** `/opt/openclaw/workspace/scripts/pivot2_brief.py`
- **No Railway backend changes.** No new API endpoints. No database changes.
- **No morning brief changes.** Morning prompt and data pipeline untouched.
- **No new cron jobs or scripts.**
- **No factor collection or staleness threshold changes.**
