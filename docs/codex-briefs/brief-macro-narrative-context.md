# Brief: Macro Narrative Context for Committee + Pivot

**Priority:** HIGH — The committee currently has zero awareness of geopolitical events, commodity prices, or macro regime narrative
**Target:** VPS (`committee_context.py`) + Railway (`bot.py` context builder)
**Estimated time:** 3-4 hours
**Source:** Committee review session March 6 — agents couldn't reference the Iran war, oil spike, stagflation risk, or any current macro backdrop

---

## Problem

The committee and Pivot have two blind spots:

### Blind Spot 1: Twitter sentiment is reduced to useless scores

The Twitter scraper fetches tweets from 30+ curated accounts (unusual_whales, DeItaone, KobeissiLetter, etc.) and scores them. But the committee only sees:
```
Twitter sentiment: URSA_MAJOR from unusual_whales — "Geopolitical tensions, oil supply disruptions"
```

What it SHOULD see:
```
## RECENT HEADLINES (last 2 hours)
- unusual_whales: "BREAKING: Russia has provided Iran with information to help Tehran strike U.S. military, AP sources"
- DeItaone: "Oil surges past $92 on Iran supply disruption fears"
- KobeissiLetter: "Unemployment claims rising for 3rd consecutive week — stagflation risk increasing"
```

The actual tweet text is available in `twitter_signals.jsonl` — it just gets summarized into a score and the raw content is thrown away before it reaches the agents.

### Blind Spot 2: No persistent macro regime narrative

Even when headlines work, they only cover the last 30-minute window. The committee has no awareness of persistent macro facts like:
- "The U.S. is at war with Iran" (ongoing for weeks)
- "Oil is above $90 and rising" (ongoing trend)
- "Tariff policy is creating sector-specific headwinds" (weeks/months)
- "The Fed is constrained — can't cut with oil spiking, can't hold with growth slowing" (regime)

These don't appear in any tweet window because they're not NEW — they're the BACKDROP.

---

## Solution: Three Additions to Committee Context

### Addition 1: Raw Headlines Block (from Twitter)

Instead of scoring tweets into a single sentiment number, pass the TOP 5-8 highest-impact raw headlines to the committee as a context block.

**In `committee_context.py`, find `_get_twitter_sentiment_context()`.**

The current function reads `twitter_signals.jsonl` and formats a sentiment summary. Modify it (or add a companion function) to ALSO extract recent raw tweet text.

**New function: `_get_headline_context()`**

```python
def _get_headline_context(lookback_hours: int = 4, max_headlines: int = 8) -> str:
    """
    Extract actual headline text from recent twitter signals.
    Returns raw headlines, not scores — the agents need to know
    WHAT is happening, not just a sentiment number.
    """
    signals_path = Path("/opt/openclaw/workspace/data/twitter_signals.jsonl")
    if not signals_path.exists():
        return ""
    
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    headlines = []
    
    for line in signals_path.open():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
            if ts < cutoff:
                continue
            
            # Only include high-weight sources
            weight = entry.get("weight", 0)
            if weight < 0.5:
                continue
            
            summary = entry.get("summary", "").strip()
            username = entry.get("username", "unknown")
            signal = entry.get("signal", "")
            
            if summary:
                headlines.append({
                    "source": username,
                    "text": summary,
                    "signal": signal,
                    "score": entry.get("score", 0),
                    "ts": ts,
                })
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    
    if not headlines:
        return ""
    
    # Sort by absolute score (most impactful first), then recency
    headlines.sort(key=lambda h: (-abs(h["score"]), -h["ts"].timestamp()))
    headlines = headlines[:max_headlines]
    
    lines = ["## RECENT HEADLINES"]
    for h in headlines:
        lines.append(f"- @{h['source']}: {h['text']}")
    
    return "\n".join(lines)
```

**Wire into `format_signal_context()` alongside the existing twitter sentiment block:**
```python
# After existing twitter sentiment injection:
headline_ctx = _get_headline_context(lookback_hours=4, max_headlines=8)
if headline_ctx:
    sections.append(headline_ctx)
```

### Addition 2: Macro Prices Block

Pull key macro prices and inject as a context section. The bias engine already has most of this data in its factor raw_data fields — we just need to format it.

**New function: `_get_macro_prices_context()`**

```python
def _get_macro_prices_context(bias_composite: dict) -> str:
    """
    Extract key macro prices from the bias composite's raw factor data.
    Gives agents concrete numbers: oil, yields, dollar, gold, VIX.
    """
    factors = bias_composite.get("factors", {})
    lines = ["## MACRO PRICES"]
    
    # VIX
    vix_data = factors.get("vix_term", {}) or {}
    vix_raw = vix_data.get("raw_data", {}) or {}
    vix = vix_raw.get("vix")
    if vix:
        lines.append(f"VIX: {vix:.1f}")
    
    # DXY
    dxy_data = factors.get("dxy_trend", {}) or {}
    dxy_raw = dxy_data.get("raw_data", {}) or {}
    dxy = dxy_raw.get("current")
    if dxy:
        dxy_trend = dxy_raw.get("trend", "")
        lines.append(f"DXY (Dollar): {dxy:.2f} ({dxy_trend})")
    
    # Yield curve
    yc_data = factors.get("yield_curve", {}) or {}
    yc_raw = yc_data.get("raw_data", {}) or {}
    spread = yc_raw.get("spread_pct")
    if spread is not None:
        lines.append(f"10Y-2Y Spread: {spread:.2f}%")
    
    # Copper/Gold (risk appetite proxy)
    cg_data = factors.get("copper_gold_ratio", {}) or {}
    cg_raw = cg_data.get("raw_data", {}) or {}
    cg_spread = cg_raw.get("spread")
    if cg_spread is not None:
        lines.append(f"Copper vs Gold (20d): {cg_spread:.1f}% (negative = risk-off)")
    
    # SPY vs SMAs
    spy50_data = factors.get("spy_50sma_distance", {}) or {}
    spy50_raw = spy50_data.get("raw_data", {}) or {}
    spy_price = spy50_raw.get("price")
    sma50 = spy50_raw.get("sma50")
    if spy_price and sma50:
        pct = spy50_raw.get("pct_distance", 0)
        lines.append(f"SPY: {spy_price:.2f} ({pct:+.1f}% from 50 SMA)")
    
    # Oil — NOT in bias factors, needs separate fetch
    # Add yfinance fetch for CL=F (WTI crude)
    try:
        import yfinance as yf
        oil = yf.Ticker("CL=F").fast_info.get("last_price")
        if oil:
            lines.append(f"Oil (WTI): ${oil:.2f}")
    except Exception:
        pass
    
    # Gold
    try:
        import yfinance as yf
        gold = yf.Ticker("GC=F").fast_info.get("last_price")
        if gold:
            lines.append(f"Gold: ${gold:.2f}")
    except Exception:
        pass
    
    # 10Y yield
    try:
        import yfinance as yf
        tnx = yf.Ticker("^TNX").fast_info.get("last_price")
        if tnx:
            lines.append(f"10Y Yield: {tnx:.2f}%")
    except Exception:
        pass
    
    if len(lines) <= 1:
        return ""
    
    return "\n".join(lines)
```

**Wire into `format_signal_context()`:**
```python
# After the MARKET REGIME section:
macro_ctx = _get_macro_prices_context(context.get("bias_composite_full", {}))
if macro_ctx:
    sections.append(macro_ctx)
```

**Note:** The bias composite endpoint currently returns factor data. You may need to pass the FULL composite response (with raw_data for each factor) into the context builder, not just the top-level bias_level/score/confidence. Check what `build_market_context()` in `pivot2_committee.py` currently stores — it may already have the full response.

### Addition 3: Persistent Macro Briefing File

Create a simple JSON file that stores the current macro narrative. This gets updated weekly (manually by Nick or by the Saturday weekly review) and injected into every committee run.

**File: `/opt/openclaw/workspace/data/macro_briefing.json`**

```json
{
  "updated_at": "2026-03-06T21:00:00Z",
  "updated_by": "nick",
  "regime": "RISK-OFF / STAGFLATION RISK",
  "narrative": "The U.S. is engaged in military operations against Iran. Oil has spiked above $90 on supply disruption fears. Russia is providing Iran with intelligence to target U.S. military assets. Unemployment claims are rising for the 3rd consecutive week. The Fed is constrained — can't cut rates with oil spiking inflation, can't hold with growth slowing. Tariff policy is creating additional uncertainty across sectors. Defense/intelligence stocks (PLTR, LMT, RTX) are counter-trending higher as war trades.",
  "key_facts": [
    "Iran war: active and escalating",
    "Oil: above $90, supply disruption premium",
    "Russia: providing Iran targeting intelligence",
    "Unemployment: rising 3 consecutive weeks",
    "Fed: rate path uncertain, stagflation bind",
    "Tariffs: ongoing uncertainty",
    "VIX: 27+ elevated, backwardation",
    "DXY: 99+ rising on safe-haven flows",
    "Gold: ATH, risk-off signal",
    "Defense stocks: counter-trending higher (war trade)"
  ],
  "sectors_to_watch": {
    "bullish": ["defense", "energy", "gold miners"],
    "bearish": ["tech (non-defense)", "consumer discretionary", "homebuilders"],
    "neutral": ["utilities", "healthcare"]
  }
}
```

**New function: `_get_macro_briefing_context()`**

```python
def _get_macro_briefing_context() -> str:
    """Load persistent macro briefing that provides regime-level context."""
    briefing_path = Path("/opt/openclaw/workspace/data/macro_briefing.json")
    if not briefing_path.exists():
        return ""
    
    try:
        data = json.loads(briefing_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    
    # Check staleness — warn if > 7 days old
    updated = data.get("updated_at", "")
    stale_warning = ""
    try:
        updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - updated_dt).days
        if age_days > 7:
            stale_warning = f" (WARNING: {age_days} days old — may be outdated)"
    except Exception:
        pass
    
    regime = data.get("regime", "UNKNOWN")
    narrative = data.get("narrative", "")
    key_facts = data.get("key_facts", [])
    
    lines = [f"## MACRO BACKDROP{stale_warning}"]
    lines.append(f"Regime: {regime}")
    if narrative:
        lines.append(f"\n{narrative}")
    if key_facts:
        lines.append("\nKey facts:")
        for fact in key_facts[:10]:
            lines.append(f"- {fact}")
    
    sectors = data.get("sectors_to_watch", {})
    if sectors:
        bull = ", ".join(sectors.get("bullish", []))
        bear = ", ".join(sectors.get("bearish", []))
        if bull:
            lines.append(f"\nSectors favored: {bull}")
        if bear:
            lines.append(f"Sectors under pressure: {bear}")
    
    return "\n".join(lines)
```

**Wire into `format_signal_context()`:**
```python
# At the TOP of the context sections (before Market Regime):
macro_briefing = _get_macro_briefing_context()
if macro_briefing:
    sections.insert(0, macro_briefing)  # First thing agents see
```

---

## Updating the Macro Briefing

Three ways to keep it current:

### Option A: Nick updates manually via Discord
Add a Pivot chat command: `/macro-update "Iran war escalating, oil above $90"`
Pivot writes to `macro_briefing.json`. Quick and easy.

### Option B: Weekly auto-update from Saturday review
The `committee_review.py` already synthesizes weekly analytics. Extend it to also update `macro_briefing.json` based on:
- Top Twitter headlines from the week
- Bias engine trend (which direction has bias been moving?)
- Key factor changes (VIX spike, DXY move, yield curve shift)

### Option C: Nick updates here in Claude.ai
Nick tells me the macro situation, I SSH and write to `macro_briefing.json`.

Recommendation: Start with Option C (I do it now) + Option A (Pivot command for quick updates). Add Option B later.

---

## Also Apply to Pivot Chat (Railway)

The same macro context should be available to Pivot's chat handler (`bot.py` on Railway). Since Pivot Chat is getting the data access upgrade (CC's current build), add:

1. A Railway API endpoint that returns `macro_briefing.json` content: `GET /api/macro/briefing`
2. Pivot Chat's `build_market_context()` fetches this endpoint and includes it in context

OR simpler: store `macro_briefing.json` content in Redis with a known key (`macro:briefing`) and have both VPS and Railway read from the same source.

---

## Summary of Changes

| Addition | What It Does | File |
|---|---|---|
| Raw Headlines | Top 8 tweet headlines as text, not scores | `committee_context.py` |
| Macro Prices | Oil, gold, 10Y, DXY, VIX, SPY from bias data + yfinance | `committee_context.py` |
| Macro Briefing | Persistent regime narrative from JSON file | `committee_context.py` + new data file |
| Briefing endpoint | Railway serves macro briefing for Pivot Chat | Railway `backend/api/` (optional) |

## Files Changed

- VPS: `/opt/openclaw/workspace/scripts/committee_context.py` — three new functions + wiring
- VPS: `/opt/openclaw/workspace/data/macro_briefing.json` — new persistent file (create)
- Railway (optional): new endpoint for macro briefing

## Deployment

VPS:
```bash
# After updating committee_context.py:
systemctl restart openclaw
systemctl restart pivot2-interactions
```

Railway: push to main for auto-deploy (if endpoint added).

## Validation

Run a manual committee analysis on any signal and verify the output includes:
- [ ] MACRO BACKDROP section with regime + narrative
- [ ] RECENT HEADLINES with actual tweet text (not just scores)
- [ ] MACRO PRICES with oil, gold, VIX, 10Y, DXY, SPY numbers
