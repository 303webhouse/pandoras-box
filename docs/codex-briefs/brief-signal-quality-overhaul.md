# Brief — Signal Quality Overhaul: Regime Filtering, Artemis Routing, Trigger Metadata

**Priority:** HIGH — directly impacts trade decision quality
**Touches:** `backend/scoring/score_v2.py`, `backend/api/trade_ideas.py`, `backend/webhooks/tradingview.py`, `backend/signals/pipeline.py`
**Estimated time:** 3–4 hours
**Context:** Olympus Committee review of Friday 3/20 signals. Market in sustained bearish downtrend (URSA_MINOR bias), quad witching day, SPY -1.43%.

---

## Problem Statement

Friday's 16 signals all scored between 38–54 on v2. With "Show all scores" checked, Nick saw them all and correctly assessed most as poor options trade setups. Three core problems:

1. **No regime awareness in scoring.** Three Artemis LONG signals (VLO, EOG, COP) scored 54.3 despite fighting URSA_MINOR bias. Zero penalty for going long in a selloff. Meanwhile SHORT sell_the_rip signals (aligned with the tape) got zero bonus.
2. **Artemis equity signals are intraday setups** that don't work as multi-day options holds for a non-PDT account. They belong in the crypto scalping interface, not Agora Insights. Artemis on crypto tickers is fine.
3. **CTA Scanner signals show no trigger context** — just "CTA Scanner" with no info about which scan condition fired (RSI extreme? Volume breakout? Quality gate?).

**Friday 3/20 signals (actual data):**

| Ticker | Strategy | Dir | Flash | v2 | R:R | Problem |
|--------|----------|-----|-------|-----|-----|---------|
| VLO | Artemis | LONG | 49.3 | 54.3 | 2.0 | LONG in URSA, intraday setup |
| EOG | Artemis | LONG | 49.3 | 54.3 | 2.0 | LONG in URSA, intraday setup |
| COP | Artemis | LONG | 49.3 | 54.3 | 2.0 | LONG in URSA, intraday setup |
| LYFT | sell_the_rip | SHORT | 60.0 | 54.0 | 1.5 | Aligned but no regime bonus |
| CRWD | sell_the_rip | SHORT | 58.3 | 52.3 | 1.5 | Aligned but penalized by enrichment |
| ZS | sell_the_rip | SHORT | 57.0 | 54.0 | 1.5 | Aligned but no regime bonus |
| PLD | CTA Scanner | SHORT | 54.0 | None | 2.3 | No trigger context |
| QQQ | sell_the_rip | SHORT | 55.0 | 52.0 | 1.5 | Best setup, still under 65 |
| UNH | sell_the_rip | SHORT | 55.0 | 52.0 | 1.5 | — |
| SLB/SMH/FXY | sell_the_rip | SHORT | 52.8 | 52.8 | 1.5 | Low scores |
| NBIS/IGV | Footprint | SHORT | 38.0 | 38.0 | — | No entry/stop/target |
| BTCUSDT ×2 | Session_Sweep | MIXED | 38.0 | 38.0 | — | Crypto, low score |

With regime bonuses: the SHORT sell_the_rip signals would gain +5 → pushing LYFT to 59, CRWD to 57.3, ZS to 59, QQQ/UNH to 57. With the Artemis LONGs penalized -10, they'd drop to 44.3 and clearly not surface. The best SHORT signals still wouldn't hit 65, but they'd be much closer — and with a future lowered threshold for regime-aligned signals (discussed in Part 1b), they could surface.

---

## Part 1a — Regime-Aware Score Penalty (Score v2)

### File: `backend/scoring/score_v2.py`

**Find** the regime placeholder section (~line 82):
```python
    # --- Regime bonus (placeholder — degraded until Phase 3 X2) ---
    regime = signal_data.get("regime")
    regime_bonus = 0
    factors["regime"] = {"value": regime, "bonus": regime_bonus, "note": "degraded until Phase 3 X2 regime module"}
```

**Replace with:**
```python
    # --- Regime alignment penalty/bonus ---
    # Uses composite bias level from bias_at_signal snapshot.
    # Penalizes counter-regime signals, rewards aligned signals.
    regime_bonus = 0
    bias_snapshot = signal_data.get("bias_at_signal") or {}
    if isinstance(bias_snapshot, str):
        try:
            import json as _json
            bias_snapshot = _json.loads(bias_snapshot)
        except Exception:
            bias_snapshot = {}
    if not isinstance(bias_snapshot, dict):
        bias_snapshot = {}

    bias_level = (bias_snapshot.get("bias_level") or "").upper()
    direction = (signal_data.get("direction") or "").upper()
    is_long = direction in ("LONG", "BUY")
    is_short = direction in ("SHORT", "SELL")

    # Bearish regimes: penalize LONG, reward SHORT
    if "URSA" in bias_level:
        if is_long:
            if "EXTREME" in bias_level:
                regime_bonus = -20
            elif "MAJOR" in bias_level:
                regime_bonus = -15
            else:  # URSA_MINOR
                regime_bonus = -10
        elif is_short:
            regime_bonus = 5

    # Bullish regimes: penalize SHORT, reward LONG
    elif "TORO" in bias_level:
        if is_short:
            if "EXTREME" in bias_level:
                regime_bonus = -20
            elif "MAJOR" in bias_level:
                regime_bonus = -15
            else:  # TORO_MINOR
                regime_bonus = -10
        elif is_long:
            regime_bonus = 5

    factors["regime"] = {
        "bias_level": bias_level,
        "direction": direction,
        "bonus": regime_bonus,
    }

    post_enrichment_bonus += regime_bonus
```

---

## Part 1b — Lower Insights Threshold for Regime-Aligned Signals

### File: `backend/api/trade_ideas.py` — `get_trade_ideas_grouped()`

Currently all signals need `score >= 65` to appear in Insights. Regime-aligned signals (e.g., SHORT during URSA) should have a lower bar since the market itself is the confirmation.

**Find (~line 161):**
```python
    effective_min_score = None if show_all else min_score
    if effective_min_score is not None:
        conditions.append(f"COALESCE(score_v2, score, 0) >= ${idx}")
        params.append(effective_min_score)
        idx += 1
```

**Replace with:**
```python
    effective_min_score = None if show_all else min_score
    if effective_min_score is not None:
        # Fetch current bias level for regime-aware threshold
        regime_threshold = effective_min_score
        try:
            from bias_engine.composite import get_cached_composite
            cached = await get_cached_composite()
            if cached:
                bl = (cached.get("bias_level") or "").upper()
                # In strong regimes, lower the threshold for ALIGNED signals
                # by adding a SQL OR clause that checks direction alignment
                if "URSA" in bl:
                    # Accept lower-scored SHORT signals during bear regimes
                    conditions.append(
                        f"(COALESCE(score_v2, score, 0) >= ${idx} OR "
                        f"(COALESCE(score_v2, score, 0) >= ${idx + 1} AND UPPER(direction) IN ('SHORT', 'SELL')))"
                    )
                    params.append(effective_min_score)           # normal threshold (65)
                    params.append(effective_min_score - 15)      # relaxed threshold for aligned (50)
                    idx += 2
                elif "TORO" in bl:
                    conditions.append(
                        f"(COALESCE(score_v2, score, 0) >= ${idx} OR "
                        f"(COALESCE(score_v2, score, 0) >= ${idx + 1} AND UPPER(direction) IN ('LONG', 'BUY')))"
                    )
                    params.append(effective_min_score)
                    params.append(effective_min_score - 15)
                    idx += 2
                else:
                    # Neutral regime: standard threshold
                    conditions.append(f"COALESCE(score_v2, score, 0) >= ${idx}")
                    params.append(effective_min_score)
                    idx += 1
            else:
                conditions.append(f"COALESCE(score_v2, score, 0) >= ${idx}")
                params.append(effective_min_score)
                idx += 1
        except Exception:
            conditions.append(f"COALESCE(score_v2, score, 0) >= ${idx}")
            params.append(effective_min_score)
            idx += 1
```

**NOTE:** `get_cached_composite()` may not exist yet. Check if there's a function that reads the cached composite from Redis. If not, read it directly:
```python
from database.redis_client import get_redis_client
import json
redis = await get_redis_client()
cached_raw = await redis.get("bias:composite:latest") if redis else None
cached = json.loads(cached_raw) if cached_raw else None
```
Use whichever Redis key the bias composite is cached under — check `bias_engine/composite.py` for the key name.

**Impact:** With this change, Friday's LYFT sell_the_rip SHORT (v2=54 + regime bonus 5 = 59) would surface in Insights during URSA because the aligned threshold drops to 50. The Artemis LONGs (v2=54 - regime penalty 10 = 44) would be filtered out even with "Show all" off.

---

## Part 2 — Artemis Equity Routing: Suppress from Agora Insights

### Problem
Artemis is a VWAP mean-reversion strategy designed for intraday entries. Nick can't day trade equities (no PDT, under $25K). These signals are useful for crypto scalping but not for Agora Insights.

### File: `backend/webhooks/tradingview.py` — `process_artemis_signal()` (~line 649)

**After** the `signal_data` dict is built (~line 696) but **before** the dedup check (~line 700), add:

```python
    # Artemis equity signals are intraday setups — not viable as multi-day options holds.
    # Route to INTRADAY_SETUP category so they don't surface in Agora Insights.
    # Crypto Artemis signals stay as TRADE_SETUP for the scalping interface.
    asset_class = signal_data.get("asset_class", "EQUITY")
    if asset_class != "CRYPTO":
        signal_data["signal_category"] = "INTRADAY_SETUP"
```

### File: `backend/api/trade_ideas.py` — `get_trade_ideas_grouped()` (~line 152)

**Find:**
```python
    conditions = [
        "status = 'ACTIVE'",
        "(expires_at IS NULL OR expires_at > NOW())",
        "created_at > NOW() - INTERVAL '24 hours'",
        "user_action IS NULL",  # Exclude accepted/rejected/dismissed signals
    ]
```

**Replace with:**
```python
    conditions = [
        "status = 'ACTIVE'",
        "(expires_at IS NULL OR expires_at > NOW())",
        "created_at > NOW() - INTERVAL '24 hours'",
        "user_action IS NULL",
        "COALESCE(signal_category, 'TRADE_SETUP') NOT IN ('INTRADAY_SETUP', 'FOOTPRINT')",
    ]
```

This keeps Artemis equity signals in the database (for analytics and crypto interface) but hides them from Agora Insights. FOOTPRINT signals are also excluded since they lack entry/stop/target and aren't directly tradeable.

---

## Part 3 — CTA Scanner Trigger Metadata

### Problem
CTA Scanner signals show "CTA Scanner" with no indication of which scan condition triggered it. The `triggering_factors` field exists in the schema but is empty.

### File: `backend/webhooks/tradingview.py` — `process_generic_signal()` (~line 729)

This is where CTA Scanner signals land (they don't match any specific strategy handler). Find the signal_data dict construction inside this function.

**After** the signal_data dict is built, add trigger metadata extraction:

```python
    # Extract triggering factors from alert fields for CTA Scanner / Sniper
    if "cta" in strategy_lower or "sniper" in strategy_lower or "scanner" in strategy_lower:
        triggers = []
        if alert.rsi is not None:
            if alert.rsi <= 35:
                triggers.append(f"RSI_{alert.rsi:.0f}_oversold")
            elif alert.rsi >= 65:
                triggers.append(f"RSI_{alert.rsi:.0f}_overbought")
            else:
                triggers.append(f"RSI_{alert.rsi:.0f}")
        if alert.rvol is not None and alert.rvol >= 1.5:
            triggers.append(f"RVOL_{alert.rvol:.1f}x")
        if alert.adx is not None:
            if alert.adx >= 25:
                triggers.append(f"ADX_{alert.adx:.0f}_trending")
            else:
                triggers.append(f"ADX_{alert.adx:.0f}_weak")
        if alert.score is not None:
            triggers.append(f"quality_gate_{int(alert.score)}")
        if triggers:
            signal_data["triggering_factors"] = triggers
            # Also include in notes for committee context
            signal_data["note"] = (signal_data.get("note") or "") + f" Triggers: {', '.join(triggers)}"
```

This makes the triggering factors visible in:
- The signal's `triggering_factors` field (persisted to DB, available in API responses)
- The `notes` field (visible in Discord committee embeds and the signal detail view)

The frontend already renders `triggering_factors` if present — check that the signal card template displays them. If not, add a line after the strategy badge:

### File: `frontend/app.js` — signal card rendering

Search for where the signal strategy badge is rendered in the Insights section. If `triggering_factors` are available, render them as small tags:

```javascript
// After the strategy badge in the signal card template:
const triggers = signal.triggering_factors || signal.primary_signal?.triggering_factors || [];
const triggerHtml = triggers.length
    ? `<div class="signal-triggers">${triggers.map(t =>
        `<span class="trigger-tag">${t.replace(/_/g, ' ')}</span>`
      ).join('')}</div>`
    : '';
```

Add CSS:
```css
.signal-triggers { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 3px; }
.trigger-tag {
    font-size: 9px;
    padding: 1px 5px;
    border-radius: 3px;
    background: rgba(20, 184, 166, 0.1);
    color: var(--accent-teal);
    border: 1px solid rgba(20, 184, 166, 0.2);
    text-transform: uppercase;
    letter-spacing: 0.3px;
}
```

---

## Part 4 — Investigate Signal Gap

### Observation
The system generated signals on Friday, but no Holy Grail, Scout/Sniper, Phalanx, or Whale Hunter signals fired. On a quad witching day with SPY -1.43%, this is suspicious.

### Diagnosis Steps for CC

1. **Check Railway logs for Friday 3/20 webhook activity:**
   Search logs for `"Scout alert accepted"`, `"Holy Grail accepted"`, `"Phalanx accepted"`, `"Whale"` log messages between 13:30-21:00 UTC on 3/20. Also check for `"cooldown"` messages — strategies might have been suppressed by overly aggressive cooldown windows.

2. **Check TradingView alert status:**
   Nick should verify in TradingView that alerts for Holy Grail, Scout, and Phalanx are still active on the Primary Watchlist. After the recent Artemis v3.1 and Phalanx v2 updates, alerts may need to be re-created.

3. **Check Whale Hunter webhook routing:**
   Whale Hunter signals go through `process_generic_signal()` (not a dedicated handler). Verify the webhook payload uses a `strategy` field that gets captured correctly. The current routing in the main webhook handler doesn't have an explicit whale handler — it falls through to generic. This is fine as long as the strategy name is preserved.

4. **Check strategy cooldowns:**
   ```python
   STRATEGY_COOLDOWNS = {
       "Holy_Grail": {"equity": 14400, "crypto": 7200},   # 4h equity
       "Scout": {"equity": 14400, "crypto": 7200},          # 4h equity
       "Phalanx": {"equity": 3600, "crypto": 3600},         # 1h both
       "Artemis": {"equity": 3600, "crypto": 1800},         # 1h equity
   }
   ```
   Holy Grail and Scout have 4-hour cooldowns. If they fired once early in the day, they'd be suppressed for the rest of the session. On a day with sustained selling, this means only one signal per ticker per 4 hours — potentially too aggressive.

**Recommendation:** Reduce Holy_Grail and Scout cooldowns to 2 hours (7200s) for equity. On high-volatility days like quad witching, conditions change fast enough to warrant re-evaluation.

### No code change in this brief — just diagnosis steps. If CC confirms the cooldowns are suppressing, a follow-up one-line fix to `STRATEGY_COOLDOWNS` is trivial.

---

## Part 5 — Contract Recommendation Engine (Future Build — NOT in This Brief)

This is documented here for the roadmap, not for implementation now.

**Goal:** When a signal surfaces, auto-recommend a specific options contract:
- **Strike selection:** ATM or first OTM for the long leg, 1-2 strikes further OTM for the short leg
- **Expiry selection:** 2× expected hold time (if target implies a 5-day move, recommend 10 DTE minimum)
- **Spread construction:** Based on direction + IV environment (high IV → credit spreads, low IV → debit spreads)
- **Price validation:** Query Polygon for the recommended spread's current bid/ask
- **Display:** Show on the signal card as "Suggested: AAPL 235/225 put spread, Apr 17, ~$2.15, max risk $215"

**Prerequisites:** Polygon options snapshots (already working for MTM), reliable entry/stop/target from the signal, IV rank from enrichment data.

**Estimated build:** 4–6 hours, separate brief after Parts 1–4 are validated.

---

## Build Order

| Step | File | What |
|------|------|------|
| 1 | `scoring/score_v2.py` | Regime penalty/bonus using bias_at_signal |
| 2 | `api/trade_ideas.py` | Regime-aware threshold lowering in grouped endpoint |
| 3 | `webhooks/tradingview.py` | Artemis equity → INTRADAY_SETUP category |
| 4 | `api/trade_ideas.py` | Exclude INTRADAY_SETUP + FOOTPRINT from grouped feed |
| 5 | `webhooks/tradingview.py` | CTA/Scanner trigger metadata extraction |
| 6 | `frontend/app.js` + `styles.css` | Trigger tags on signal cards |
| 7 | Diagnose | Check Friday logs for missing strategy signals |
| 8 | `index.html` | Cache bust |

---

## Verification Checklist

- [ ] Score v2 for a LONG signal during URSA_MINOR is ~10 points lower than flash score
- [ ] Score v2 for a SHORT signal during URSA_MINOR is ~5 points higher than flash score
- [ ] Artemis LONG on equity ticker gets `signal_category: INTRADAY_SETUP`
- [ ] Artemis on BTCUSDT keeps `signal_category: TRADE_SETUP` (crypto is unaffected)
- [ ] Grouped Insights endpoint excludes INTRADAY_SETUP signals
- [ ] During URSA regime, SHORT signals with v2 >= 50 appear in Insights (lowered threshold)
- [ ] During URSA regime, LONG signals still need v2 >= 65 to appear
- [ ] CTA Scanner signals show `triggering_factors` like `["RSI_33_oversold", "RVOL_2.8x"]`
- [ ] Trigger tags render on signal cards in the frontend
- [ ] Strategy cooldown logs checked for Friday suppression

---

## Commit

```
feat: regime-aware scoring, Artemis routing, CTA trigger metadata
```
