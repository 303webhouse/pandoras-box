# Brief — Phase 2: Flow Badges on Position Cards

**Priority:** HIGH — first user-facing value from the flow pipeline
**Touches:** `backend/api/unified_positions.py`, `frontend/app.js`, `frontend/styles.css`
**Estimated time:** 1.5–2 hours
**Depends on:** Phase 1 (flow_ingestion.py) deployed — but can be built before Phase 1 data starts flowing; badges will just show nothing until Redis has data.

---

## Context

Phase 1 built the plumbing: UW Watcher data now flows into Redis as `uw:flow:{TICKER}` keys. Phase 2 puts that data where it helps — directly on each open position card as a simple confirming/counter badge.

**The user experience:** Each position card shows a small colored badge answering one question: "Is the options market agreeing or disagreeing with my trade?" Plus a strength indicator (whisper vs. shout).

The implementation follows the **exact same pattern** as the existing counter-signal and confirming-signal banners (see `unified_positions.py` ~lines 592-608 and `app.js` ~lines 8502-8540). Backend attaches data from Redis per ticker; frontend renders a banner.

---

## Part 1 — Backend: Attach Flow Data to Open Positions

### File: `backend/api/unified_positions.py` — `list_positions()` endpoint

Find the existing Redis attachment block (~line 592):

```python
# Attach counter-signal warnings from Redis for open positions
if status.upper() == "OPEN":
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            for p in positions:
                ticker = (p.get("ticker") or "").upper()
                if ticker:
                    raw = await redis.get(f"counter_signal:{ticker}")
                    if raw:
                        p["counter_signal"] = json.loads(raw)
                    raw_conf = await redis.get(f"confirming_signal:{ticker}")
                    if raw_conf:
                        p["confirming_signal"] = json.loads(raw_conf)
    except Exception as e:
        logger.warning(f"Failed to attach counter-signals: {e}")
```

**Add immediately after the confirming_signal block (inside the same `if redis:` / `for p in positions:` loop), before the `except`:**

```python
                    # Attach flow sentiment from UW Watcher data
                    raw_flow = await redis.get(f"uw:flow:{ticker}")
                    if raw_flow:
                        flow = json.loads(raw_flow)
                        pos_direction = (p.get("direction") or "LONG").upper()
                        flow_sentiment = (flow.get("sentiment") or "NEUTRAL").upper()
                        pc_ratio = flow.get("pc_ratio")
                        total_premium = flow.get("total_premium") or 0

                        # Determine flow alignment with position direction
                        # LONG positions want BULLISH flow; SHORT/bearish positions want BEARISH flow
                        is_bullish_position = pos_direction == "LONG"
                        is_bearish_position = pos_direction in ("SHORT", "MIXED")

                        if flow_sentiment == "BULLISH" and is_bullish_position:
                            alignment = "CONFIRMING"
                        elif flow_sentiment == "BEARISH" and is_bearish_position:
                            alignment = "CONFIRMING"
                        elif flow_sentiment == "BULLISH" and is_bearish_position:
                            alignment = "COUNTER"
                        elif flow_sentiment == "BEARISH" and is_bullish_position:
                            alignment = "COUNTER"
                        else:
                            alignment = "NEUTRAL"

                        # Strength: based on how extreme the P/C ratio is
                        # P/C < 0.5 or > 2.0 = STRONG, 0.5-0.7 or 1.3-2.0 = MODERATE, else WEAK
                        if pc_ratio is not None:
                            if pc_ratio < 0.5 or pc_ratio > 2.0:
                                strength = "STRONG"
                            elif pc_ratio < 0.7 or pc_ratio > 1.3:
                                strength = "MODERATE"
                            else:
                                strength = "WEAK"
                        else:
                            strength = "WEAK"

                        p["flow_signal"] = {
                            "alignment": alignment,
                            "strength": strength,
                            "sentiment": flow_sentiment,
                            "pc_ratio": pc_ratio,
                            "total_premium": total_premium,
                            "last_updated": flow.get("last_updated"),
                        }
```

**IMPORTANT:** This goes inside the existing `for p in positions:` loop where `counter_signal` and `confirming_signal` are attached. Do NOT create a separate loop — keep it in the same Redis connection block for efficiency.

---

## Part 2 — Frontend: Render Flow Badge on Position Cards

### File: `frontend/app.js`

Find the position card rendering function. Look for where `counterBanner` and `confirmBanner` are built (~line 8502). After the `confirmBanner` block and before the `cardClass` line, add the flow badge:

**Find (~line 8540):**
```javascript
    const cardClass = pos.counter_signal ? ' has-counter-signal' : pos.confirming_signal ? ' has-confirming-signal' : '';
```

**Add BEFORE that line:**
```javascript
    // Flow sentiment badge (UW options flow data)
    let flowBadge = '';
    if (pos.flow_signal) {
        const fs = pos.flow_signal;
        const alignment = fs.alignment || 'NEUTRAL';
        const strength = fs.strength || 'WEAK';

        let badgeClass, badgeIcon, badgeText;
        if (alignment === 'CONFIRMING') {
            badgeClass = 'flow-confirming';
            badgeIcon = '✓';
            badgeText = strength === 'STRONG' ? 'Strong flow confirms'
                      : strength === 'MODERATE' ? 'Flow confirms'
                      : 'Weak flow confirms';
        } else if (alignment === 'COUNTER') {
            badgeClass = 'flow-counter';
            badgeIcon = '⚠';
            badgeText = strength === 'STRONG' ? 'Strong flow disagrees'
                      : strength === 'MODERATE' ? 'Flow disagrees'
                      : 'Weak flow disagrees';
        } else {
            badgeClass = 'flow-neutral';
            badgeIcon = '○';
            badgeText = 'Flow neutral';
        }

        // Premium display for hover/detail
        const premStr = fs.total_premium
            ? (fs.total_premium >= 1e9 ? '$' + (fs.total_premium / 1e9).toFixed(1) + 'B'
               : fs.total_premium >= 1e6 ? '$' + (fs.total_premium / 1e6).toFixed(0) + 'M'
               : fs.total_premium >= 1e3 ? '$' + (fs.total_premium / 1e3).toFixed(0) + 'K'
               : '$' + fs.total_premium)
            : '';
        const pcStr = fs.pc_ratio != null ? `P/C ${fs.pc_ratio.toFixed(2)}` : '';
        const tooltip = [badgeText, pcStr, premStr ? `Premium: ${premStr}` : ''].filter(Boolean).join(' · ');

        flowBadge = `
            <div class="flow-badge ${badgeClass}" title="${tooltip}">
                <span class="flow-badge-icon">${badgeIcon}</span>
                <span class="flow-badge-text">${badgeText}</span>
            </div>`;
    }
```

**Then update the card HTML template.** Find where `${counterBanner}` and `${confirmBanner}` are inserted in the card template (~line 8549):

```javascript
            ${counterBanner}
            ${confirmBanner}
```

**Add the flow badge immediately after:**
```javascript
            ${counterBanner}
            ${confirmBanner}
            ${flowBadge}
```

---

## Part 3 — Frontend: CSS for Flow Badges

### File: `frontend/styles.css`

Find the existing `.counter-signal-warning` styles. Add nearby:

```css
/* Flow sentiment badges on position cards */
.flow-badge {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
    margin-top: 4px;
    letter-spacing: 0.3px;
}

.flow-badge-icon {
    font-size: 11px;
}

.flow-confirming {
    background: rgba(74, 222, 128, 0.1);
    color: #4ade80;
    border: 1px solid rgba(74, 222, 128, 0.25);
}

.flow-counter {
    background: rgba(248, 113, 113, 0.1);
    color: #f87171;
    border: 1px solid rgba(248, 113, 113, 0.25);
}

.flow-neutral {
    background: rgba(120, 144, 156, 0.08);
    color: #78909c;
    border: 1px solid rgba(120, 144, 156, 0.15);
}
```

---

## Part 4 — Cache Bust

### File: `frontend/index.html`

Bump CSS and JS version numbers by 1 from current values.

---

## Build Order

| Step | File | What |
|------|------|------|
| 1 | `unified_positions.py` | Attach `flow_signal` from Redis in list_positions loop |
| 2 | `app.js` | Build flow badge HTML in position card renderer |
| 3 | `styles.css` | Flow badge styling (confirming/counter/neutral) |
| 4 | `index.html` | Cache bust |

---

## How It Works (End to End)

1. UW Watcher parses Discord → POSTs to `/api/uw/ticker-updates` → writes Redis `uw:flow:AAPL`
2. Frontend calls `GET /v2/positions?status=OPEN` → backend loops positions, reads `uw:flow:AAPL` from Redis
3. Backend compares flow sentiment (BULLISH/BEARISH) to position direction (LONG/SHORT) → attaches alignment (CONFIRMING/COUNTER/NEUTRAL) + strength (STRONG/MODERATE/WEAK)
4. Frontend renders a small colored badge on each position card:
   - **Green badge** with checkmark: "Flow confirms" (or "Strong flow confirms")
   - **Red badge** with warning: "Flow disagrees" (or "Strong flow disagrees")
   - **Grey badge**: "Flow neutral"
5. Hover/title shows details: P/C ratio and total premium

---

## Alignment Logic

| Position Direction | Flow Sentiment | Result |
|---|---|---|
| LONG | BULLISH | ✓ Confirming |
| LONG | BEARISH | ⚠ Counter |
| SHORT | BEARISH | ✓ Confirming |
| SHORT | BULLISH | ⚠ Counter |
| Any | NEUTRAL | ○ Neutral |

## Strength Logic

| P/C Ratio | Strength | Meaning |
|---|---|---|
| < 0.5 or > 2.0 | STRONG | Very lopsided flow — loud signal |
| 0.5–0.7 or 1.3–2.0 | MODERATE | Noticeable lean |
| 0.7–1.3 | WEAK | Balanced flow — whisper |

---

## Verification Checklist

- [ ] `GET /v2/positions?status=OPEN` returns positions with `flow_signal` field when Redis has UW data for that ticker
- [ ] Positions for tickers with no UW data have no `flow_signal` field (not an error, just absent)
- [ ] Position card shows green badge when flow confirms position direction
- [ ] Position card shows red badge when flow opposes position direction
- [ ] Position card shows grey badge when flow is neutral
- [ ] Hover on badge shows P/C ratio and premium
- [ ] Badge appears below the confirming/counter-signal banners (if both exist)
- [ ] No visible badge when no flow data exists for that ticker

---

## Known Limitations

1. **Badge only appears for tickers UW Watcher covers.** If a position is on a ticker UW doesn't post about, no badge appears — this is correct behavior, not a bug.
2. **MIXED direction positions** are treated as bearish for alignment purposes (hedged/mixed positions generally benefit from volatility, which correlates with put-heavy flow).
3. **Flow data is 15-30 min delayed** from actual market activity (UW posting frequency). The badge reflects the most recent UW snapshot, not live second-by-second flow.
4. **No flow velocity yet.** This brief shows the current snapshot only. Phase 3 would add "accelerating/decelerating" using `flow_events` history.

---

## Commit

```
feat: flow sentiment badges on position cards (Phase 2)
```
