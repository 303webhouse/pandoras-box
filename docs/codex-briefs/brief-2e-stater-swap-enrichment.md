# Brief 2E: Stater Swap Signal Card Enrichment + Engine Tuning

## Summary

Four improvements from Olympus review: (1) Show market structure context and Breakout sizing in Stater Swap signal cards — currently only visible in Discord embeds. (2) Add regime pre-filter to suppress signals during dead conditions. (3) Add minimum range check to Session Sweep. (4) Add score decay for stale signals.

## Part 1: Signal Card Enrichment (HIGHEST PRIORITY)

### Problem

The `createCryptoSignalCard()` function in `frontend/app.js` (~line 3725) renders entry/stop/target/R:R and a score badge. It does NOT display:
- Market structure context label (STRONG / NEUTRAL / WEAK / AVOID)
- POC/VAH/VAL relative to entry
- CVD direction
- Orderbook imbalance
- Breakout position sizing (contracts, leverage, risk %)
- Strategy-specific context (funding rate %, session name, liquidation volume)

This data IS in the signal's `enrichment_data` JSON — the Discord embeds already show it. The dashboard just doesn't parse it.

### Fix

In `createCryptoSignalCard()`, parse `enrichment_data` and add three new sections to the card HTML:

#### 1a. Market Structure Badge (prominent, top of card)

Parse `enrichment_data.market_structure`:

```javascript
const enrichment = typeof signal.enrichment_data === 'string'
    ? JSON.parse(signal.enrichment_data || '{}') : (signal.enrichment_data || {});
const ms = enrichment.market_structure || {};
const sizing = enrichment.position_sizing || {};
```

Add a colored badge right after the score row:

```html
<div class="crypto-structure-badge ${ms.context_label?.toLowerCase() || 'neutral'}">
    ${ms.context_label || 'N/A'}
    <span class="structure-modifier">${ms.score_modifier > 0 ? '+' : ''}${ms.score_modifier || 0}</span>
</div>
```

CSS classes:
- `.strong` — green background, white text
- `.neutral` — gray background, white text
- `.weak` — orange background, dark text
- `.avoid` — red background, white text

#### 1b. Market Structure Detail Row

Below entry/stop/target, add a compact detail row:

```html
<div class="crypto-signal-structure">
    <span><span class="crypto-signal-detail-label">POC</span>
        <span class="crypto-signal-detail-value">${formatPrice(ms.poc)}</span></span>
    <span><span class="crypto-signal-detail-label">CVD</span>
        <span class="crypto-signal-detail-value ${(ms.cvd_direction || '').toLowerCase()}">
            ${ms.cvd_direction || '--'}</span></span>
    <span><span class="crypto-signal-detail-label">Book</span>
        <span class="crypto-signal-detail-value">
            ${ms.book_imbalance ? ms.book_imbalance.toFixed(2) + 'x' : '--'}</span></span>
</div>
```

#### 1c. Breakout Sizing Row

Add position sizing below the structure row:

```html
<div class="crypto-signal-sizing">
    <span><span class="crypto-signal-detail-label">Size</span>
        <span class="crypto-signal-detail-value">${sizing.contracts ? sizing.contracts.toFixed(4) + ' BTC' : '--'}</span></span>
    <span><span class="crypto-signal-detail-label">Leverage</span>
        <span class="crypto-signal-detail-value ${sizing.safe === false ? 'danger' : ''}">
            ${sizing.leverage ? sizing.leverage.toFixed(1) + 'x' : '--'}</span></span>
    <span><span class="crypto-signal-detail-label">Risk</span>
        <span class="crypto-signal-detail-value">
            ${sizing.risk_usd ? '$' + sizing.risk_usd.toFixed(0) + ' (' + sizing.risk_pct + '%)' : '--'}</span></span>
</div>
```

If `sizing.safe === false` (leverage > 3x), show the leverage value in red.

#### 1d. Strategy Context Row

Show strategy-specific enrichment data:

```javascript
// Parse strategy-specific context
let contextHtml = '';
const strategy = (signal.strategy || '').toLowerCase();

if (strategy.includes('funding')) {
    const fr = enrichment.funding_rate;
    const mts = enrichment.minutes_to_settlement;
    if (fr !== undefined) {
        contextHtml = `<div class="crypto-signal-context">
            <span>Funding: <strong>${(fr * 100).toFixed(4)}%</strong></span>
            ${mts !== undefined ? `<span>Settlement in: <strong>${mts}m</strong></span>` : ''}
        </div>`;
    }
} else if (strategy.includes('session')) {
    const session = enrichment.session;
    const sweep = enrichment.sweep_type;
    if (session) {
        contextHtml = `<div class="crypto-signal-context">
            <span>Session: <strong>${session}</strong></span>
            ${sweep ? `<span>Sweep: <strong>${sweep}</strong></span>` : ''}
        </div>`;
    }
} else if (strategy.includes('liquidation') || strategy.includes('flush')) {
    const vol = enrichment.liquidation_volume;
    if (vol) {
        contextHtml = `<div class="crypto-signal-context">
            <span>Liquidation Volume: <strong>$${(vol / 1e6).toFixed(1)}M</strong></span>
        </div>`;
    }
} else if (strategy.includes('holy_grail')) {
    const adx = signal.adx;
    const rsi = signal.rsi;
    contextHtml = `<div class="crypto-signal-context">
        ${adx ? `<span>ADX: <strong>${adx}</strong></span>` : ''}
        ${rsi ? `<span>RSI: <strong>${rsi}</strong></span>` : ''}
    </div>`;
}
```

Insert all four sections into the card template between the existing details and the action buttons.

#### 1e. CSS for New Sections

Add to `frontend/styles.css` (or inline in index.html if styles are there):

```css
.crypto-structure-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 2px 10px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}
.crypto-structure-badge.strong { background: #1b5e20; color: #fff; }
.crypto-structure-badge.neutral { background: #424242; color: #ccc; }
.crypto-structure-badge.weak { background: #e65100; color: #fff; }
.crypto-structure-badge.avoid { background: #b71c1c; color: #fff; }
.structure-modifier { opacity: 0.7; font-weight: 400; }

.crypto-signal-structure,
.crypto-signal-sizing,
.crypto-signal-context {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    font-size: 12px;
    padding: 4px 0;
    border-top: 1px solid rgba(255,255,255,0.06);
}

.crypto-signal-sizing .danger {
    color: #ef5350;
    font-weight: 600;
}

.crypto-signal-context {
    font-size: 11px;
    color: var(--text-secondary);
}

.crypto-signal-detail-value.bullish { color: #4caf50; }
.crypto-signal-detail-value.bearish { color: #ef5350; }
```

## Part 2: Regime Pre-Filter (HIGH)

### Problem

The setup engine fires signals 24/7 regardless of market conditions. During low-vol sideways chop (common in Sunday-Monday Asia sessions), strategies still generate signals. Market structure scoring downgrades them, but they still clutter the signal feed.

### Fix

In `backend/strategies/crypto_setups.py`, add a regime check at the top of `run_crypto_scan()` before running any strategies:

```python
async def _check_btc_regime(klines: List[List]) -> Dict:
    """
    Lightweight regime classification from recent klines.
    Returns regime label and whether signals should fire.
    """
    if not klines or len(klines) < 20:
        return {"regime": "UNKNOWN", "tradeable": True}  # fail open

    # Calculate current ATR from last 14 candles
    trs = []
    for i in range(1, min(15, len(klines))):
        high = float(klines[i][2])
        low = float(klines[i][3])
        prev_close = float(klines[i-1][4])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)

    current_atr = sum(trs[-7:]) / 7 if len(trs) >= 7 else sum(trs) / len(trs)
    avg_atr = sum(trs) / len(trs)

    atr_ratio = current_atr / avg_atr if avg_atr > 0 else 1.0

    if atr_ratio < 0.5:
        return {
            "regime": "QUIET",
            "tradeable": False,
            "reason": f"ATR ratio {atr_ratio:.2f} — market is dead, suppressing all signals"
        }
    elif atr_ratio > 2.0:
        return {
            "regime": "VOLATILE",
            "tradeable": True,
            "suppress": ["funding_rate", "session_sweep"],
            "reason": f"ATR ratio {atr_ratio:.2f} — too volatile for funding/session, allowing flush/HG"
        }
    elif atr_ratio > 1.3:
        return {"regime": "TRENDING", "tradeable": True}
    else:
        return {"regime": "RANGING", "tradeable": True}
```

In `run_crypto_scan()`, add after fetching klines:

```python
# Regime check — suppress signals during dead conditions
regime = await _check_btc_regime(klines_1h)
if not regime.get("tradeable", True):
    logger.info(f"Regime: {regime['regime']} — {regime.get('reason', 'skipping')}")
    return []

suppressed = set(regime.get("suppress", []))
```

Then before each strategy check:
```python
if "funding_rate" not in suppressed:
    # ... run funding rate fade
if "session_sweep" not in suppressed:
    # ... run session sweep
# Liquidation flush and Holy Grail always run (they work in volatile conditions)
```

Also include the regime label in each signal's enrichment_data so the UI can display it:
```python
signal_enrichment["regime"] = regime.get("regime", "UNKNOWN")
```

## Part 3: Session Sweep Minimum Range (MEDIUM)

### Problem

If the Asia session range is extremely narrow (0.2-0.3%), a "sweep" of that range plus 0.1% is noise, not a real liquidity grab.

### Fix

In `check_session_sweep()` in `crypto_setups.py`, after computing the session range, add:

```python
# Minimum range check — skip if range is too narrow
range_pct = (session_high - session_low) / session_low * 100
if range_pct < 0.5:
    return None  # Range too narrow, not a real session to sweep
```

Add this before the sweep detection logic. 0.5% of BTC price (~$420 at $84K) is a reasonable minimum for a tradeable session range.

## Part 4: Score Decay for Stale Signals (MEDIUM)

### Problem

A 20-minute-old crypto signal with score 80 looks identical to a fresh one. In crypto scalping, a signal from 20 minutes ago may have already played out.

### Fix

In `renderCryptoSignals()` in `frontend/app.js` (~line 3440), apply decay before sorting/rendering:

```javascript
// Apply score decay for stale signals
const now = Date.now();
cryptoSignals = cryptoSignals.map(s => {
    const created = new Date(s.timestamp || s.created_at || 0).getTime();
    const ageMinutes = (now - created) / 60000;

    if (ageMinutes > 15) {
        const decayBlocks = Math.floor((ageMinutes - 15) / 5);
        const decay = decayBlocks * 5;  // -5 points per 5-min block after 15 min
        s = { ...s, display_score: Math.max(0, (s.score || 0) - decay) };
    } else {
        s = { ...s, display_score: s.score || 0 };
    }
    return s;
});
```

Then in `createCryptoSignalCard()`, use `signal.display_score` instead of `signal.score` for rendering. Keep the original `signal.score` for data purposes.

Also add a visual age indicator:
```javascript
// In the card template, add after timestamp
const ageMin = Math.floor((Date.now() - new Date(signal.timestamp || signal.created_at || 0).getTime()) / 60000);
const ageLabel = ageMin < 5 ? 'FRESH' : ageMin < 15 ? `${ageMin}m ago` : `${ageMin}m ago ⚠️`;
const ageClass = ageMin < 5 ? 'fresh' : ageMin < 15 ? '' : 'stale';
```

Add CSS:
```css
.signal-age.fresh { color: #4caf50; font-weight: 600; }
.signal-age.stale { color: #ef5350; opacity: 0.7; }
```

## Out of Scope

- Time-of-day scoring modifier (deferred — needs outcome data)
- Holy Grail 15m noise tuning (monitor for 1 week first)
- Scoring weight calibration between components (needs outcome data)
- Account state awareness / daily P&L tracking (future enhancement)

## Testing

1. Open Stater Swap → verify signal cards show market structure badge, POC/CVD/book row, Breakout sizing row
2. Verify STRONG badge is green, AVOID is red
3. Verify leverage > 3x shows in red
4. Verify strategy context shows (funding rate %, session name, liquidation volume, ADX/RSI)
5. Manually trigger a signal during quiet market conditions → verify regime suppresses it
6. Verify Session Sweep doesn't fire when Asia range < 0.5%
7. Load Stater Swap with signals > 15 min old → verify score decay applied visually
8. Verify all existing tests pass (168+)

## Definition of Done

- [ ] Signal cards show market structure context label (STRONG/NEUTRAL/WEAK/AVOID) as colored badge
- [ ] Signal cards show POC, CVD direction, orderbook imbalance
- [ ] Signal cards show Breakout sizing (contracts, leverage, risk)
- [ ] Signal cards show strategy-specific context (funding rate, session, liquidation vol, ADX/RSI)
- [ ] Leverage > 3x flagged in red
- [ ] Regime pre-filter suppresses signals during QUIET conditions
- [ ] VOLATILE regime suppresses funding rate and session sweep only
- [ ] Session Sweep skips ranges < 0.5%
- [ ] Score decay: -5 per 5-min block after 15 minutes
- [ ] Signal age indicator (FRESH / Xm ago / stale warning)
- [ ] All existing tests pass
