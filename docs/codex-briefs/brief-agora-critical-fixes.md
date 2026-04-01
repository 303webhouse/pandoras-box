# BRIEF: Agora Critical Fixes — Regime Scaling, Bias Polling, Sector Staleness, Greeks, Earnings, Regime Bar Relocation
## Priority: P0 (Fixes 1-3), P1 (Fixes 4-6) | System: Backend + Frontend
## Date: 2026-04-01

---

## CONTEXT FOR CLAUDE CODE

Multiple issues identified in the Agora frontend. This brief contains 6 fixes ordered by priority. Each fix is independent — commit after each one so we can verify incrementally.

**IMPORTANT:** The frontend app.js is ~530KB / 12,600 lines. Use targeted find/replace. Do NOT rewrite large sections. Each fix below gives exact old/new strings.

**Database is Railway Postgres** (NOT Supabase). Use `get_postgres_client()`.

---

## FIX 1: Regime Bar Score Scaling Bug (CRITICAL — 3-line fix)

### Problem
The regime bar ALWAYS shows "Hostile environment" regardless of actual market conditions. Root cause: `backend/api/regime.py` reads the raw composite score (range: -1.0 to +1.0) and compares it against thresholds designed for a 0-100 scale (70, 50, 30). A score of -0.06 (which is NEUTRAL) reads as `< 30` → "Hostile."

### File: `backend/api/regime.py`

**Find this block** (around line 79-93):

```python
            score = composite.get("composite_score", 0)
            if isinstance(score, str):
                try:
                    score = float(score)
                except (ValueError, TypeError):
                    score = 50

            if score >= 70:
                label = f"Favorable environment (composite {score:.0f}/100). Full signal menu active. Normal position sizing."
            elif score >= 50:
                label = f"Cautious environment (composite {score:.0f}/100). Favor high-conviction setups only. Reduce position sizing."
            elif score >= 30:
                label = f"Unfavorable environment (composite {score:.0f}/100). Minimal new positions. Hedge existing exposure."
            else:
                label = f"Hostile environment (composite {score:.0f}/100). Avoid new longs. Focus on capital preservation and catalyst-aligned trades only."

            return {
                "regime_label": label,
                "direction": "BULLISH" if score >= 60 else "BEARISH" if score <= 40 else "NEUTRAL",
```

**Replace with:**

```python
            raw_score = composite.get("composite_score", 0)
            if isinstance(raw_score, str):
                try:
                    raw_score = float(raw_score)
                except (ValueError, TypeError):
                    raw_score = 0.0

            # Convert from -1..+1 scale to 0..100 for display and thresholds
            score = round(((raw_score + 1) / 2) * 100)

            if score >= 70:
                label = f"Favorable ({score}/100) — full signal menu, normal sizing"
            elif score >= 50:
                label = f"Cautious ({score}/100) — high-conviction setups only"
            elif score >= 30:
                label = f"Unfavorable ({score}/100) — minimal new positions, hedge exposure"
            else:
                label = f"Hostile ({score}/100) — capital preservation only"

            return {
                "regime_label": label,
                "direction": "BULLISH" if score >= 60 else "BEARISH" if score <= 40 else "NEUTRAL",
```

**Why this works:** The raw score is on a -1 to +1 scale (see `score_to_bias()` in `bias_engine/composite.py` — thresholds at ±0.20, ±0.60). Converting to 0-100 matches the frontend's display (which does the same math in app.js line ~1855). The labels are also shortened per Nick's request to reduce clutter.

---

## FIX 2: Add Composite Bias Polling Interval (1-line fix)

### Problem
`fetchCompositeBias()` has NO periodic refresh — it only fires on page load and WebSocket `BIAS_UPDATE` pushes. If the WS misses a push or the browser reconnects, the composite bias card goes stale. Meanwhile `fetchTimeframeBias` already polls every 2 minutes.

### File: `frontend/app.js`

**Find this block** (around line 1293-1295):

```javascript
    // Refresh timeframe data every 2 minutes
    setInterval(fetchTimeframeBias, 2 * 60 * 1000);
```

**Replace with:**

```javascript
    // Refresh bias data every 2 minutes
    setInterval(fetchCompositeBias, 2 * 60 * 1000);
    setInterval(fetchTimeframeBias, 2 * 60 * 1000);
```

---

## FIX 3: Move Regime Bar Into Market Bias Panel (Condensed)

### Problem
The regime bar currently sits as a standalone full-width bar between the macro strip and the bias section. Nick wants it moved INSIDE the Market Bias panel, just above the "Factor Breakdown" toggle, with less text/clutter.

### Step 3A: Remove the regime bar from its current location in index.html

**File: `frontend/index.html`**

**Find and DELETE this entire block** (around lines 84-145 — the regime bar AND the regime override modal). Replace it with an empty comment placeholder:

Find:
```html
        <!-- REGIME BAR — Phase 5 Catalyst Awareness -->
        <div id="regimeBar" class="regime-bar">
            <div class="regime-bar-content">
                <div class="regime-label-area">
                    <span id="regimeSourceBadge" class="regime-source-badge">AUTO</span>
                    <span id="regimeLabel" class="regime-label-text">Loading regime...</span>
                    <span id="regimeExpiry" class="regime-expiry"></span>
                </div>
                <div class="regime-controls">
                    <div class="regime-pills" id="regimePills"></div>
                    <label class="reversal-toggle" title="Reversal Mode: rank signals by relative performance divergence">
                        <input type="checkbox" id="reversalModeToggle">
                        <span class="reversal-toggle-label">&#x27F2; REVERSAL</span>
                    </label>
                    <button id="regimeOverrideBtn" class="regime-override-btn" title="Manually set market regime">&#x270E; Override</button>
                    <button id="regimeClearBtn" class="regime-clear-btn" style="display:none;" title="Clear manual override">&#x2715; Clear</button>
                </div>
            </div>
        </div>
```

Replace with:
```html
        <!-- Regime bar moved into bias panel (Fix 3) -->
```

### Step 3B: Insert condensed regime bar inside the Market Bias panel

**File: `frontend/index.html`**

Find:
```html
                <div class="factor-breakdown">
                    <div class="factor-breakdown-header" id="factorBreakdownToggle">
```

Replace with:
```html
                <!-- Condensed Regime Bar (moved from top) -->
                <div id="regimeBar" class="regime-bar-inline">
                    <span id="regimeSourceBadge" class="regime-source-badge-sm">AUTO</span>
                    <span id="regimeLabel" class="regime-label-inline">Loading...</span>
                    <span id="regimeExpiry" class="regime-expiry-sm"></span>
                    <div class="regime-inline-controls">
                        <div class="regime-pills" id="regimePills"></div>
                        <label class="reversal-toggle-sm" title="Reversal Mode">
                            <input type="checkbox" id="reversalModeToggle">
                            <span>&#x27F2;</span>
                        </label>
                        <button id="regimeOverrideBtn" class="regime-override-btn-sm" title="Override">&#x270E;</button>
                        <button id="regimeClearBtn" class="regime-clear-btn-sm" style="display:none;" title="Clear">&#x2715;</button>
                    </div>
                </div>

                <div class="factor-breakdown">
                    <div class="factor-breakdown-header" id="factorBreakdownToggle">
```

**NOTE:** Keep the regime override modal (`regimeOverrideModal`) where it is — it's a modal overlay and its position in the DOM doesn't matter.

### Step 3C: Add inline regime bar styles

**File: `frontend/styles.css`**

Append the following styles at the end of the file (or find and update the existing `.regime-bar` styles):

```css
/* === INLINE REGIME BAR (inside bias panel) === */
.regime-bar-inline {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    margin: 0 0 6px 0;
    border-radius: 4px;
    background: rgba(255,255,255,0.03);
    border: 1px solid var(--border-color);
    font-size: 11px;
    flex-wrap: wrap;
}
.regime-bar-inline.regime-bullish {
    border-color: rgba(0, 230, 118, 0.3);
    background: rgba(0, 230, 118, 0.05);
}
.regime-bar-inline.regime-bearish {
    border-color: rgba(229, 55, 14, 0.3);
    background: rgba(229, 55, 14, 0.05);
}
.regime-bar-inline.reversal-active {
    border-color: rgba(255, 152, 0, 0.4);
    background: rgba(255, 152, 0, 0.06);
}
.regime-source-badge-sm {
    font-size: 9px;
    font-weight: 700;
    padding: 1px 5px;
    border-radius: 3px;
    background: rgba(0, 230, 118, 0.15);
    color: #00e676;
    letter-spacing: 0.5px;
}
.regime-source-badge-sm.manual {
    background: rgba(255, 152, 0, 0.15);
    color: #ff9800;
}
.regime-label-inline {
    color: var(--text-secondary);
    flex: 1;
    min-width: 120px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.regime-expiry-sm {
    font-size: 9px;
    color: var(--text-secondary);
    opacity: 0.7;
}
.regime-inline-controls {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-left: auto;
}
.reversal-toggle-sm {
    cursor: pointer;
    font-size: 12px;
    color: var(--text-secondary);
    opacity: 0.6;
}
.reversal-toggle-sm:hover { opacity: 1; }
.regime-override-btn-sm,
.regime-clear-btn-sm {
    background: none;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 12px;
    padding: 2px 4px;
    opacity: 0.6;
}
.regime-override-btn-sm:hover,
.regime-clear-btn-sm:hover { opacity: 1; }
```

### Step 3D: Update renderRegimeBar to work with new class names

**File: `frontend/app.js`**

The `renderRegimeBar` function (around line 11294) applies CSS classes to the bar. The bar now uses `regime-bar-inline` as the base class instead of `regime-bar`. Update:

Find:
```javascript
    // Direction-based bar color
    bar.className = 'regime-bar';
```

Replace with:
```javascript
    // Direction-based bar color
    bar.className = 'regime-bar-inline';
```

---

## FIX 4: Sector Heatmap Staleness — Add Logging + Today-Bar Fallback

### Problem
Sector heatmap shows yesterday's data during market hours. The `_fetch_sector_snapshot()` calls Polygon's snapshot API but may silently return empty data. The fallback `_fetch_all_bars()` only fetches through yesterday (`to_date = today - 1`), so the daily change shows yesterday's close-to-prior-close, not today's movement.

### Step 4A: Add logging to snapshot failures

**File: `backend/api/sectors.py`**

Find (in `_fetch_sector_snapshot`, around line 457):
```python
                if resp.status != 200:
                    logger.warning("Polygon sector snapshot HTTP %d", resp.status)
                    return result
```

Replace with:
```python
                if resp.status != 200:
                    body_preview = await resp.text()
                    logger.warning("Polygon sector snapshot HTTP %d — body: %.200s", resp.status, body_preview)
                    return result
```

### Step 4B: Include today's bar in fallback

**File: `backend/api/sectors.py`**

Find (in `_fetch_all_bars`, around line 100):
```python
    to_date = (today - td(days=1)).isoformat()  # Yesterday — today's bar is partial
```

Replace with:
```python
    to_date = today.isoformat()  # Include today's partial bar for intraday fallback
```

### Step 4C: Add logging to heatmap endpoint when snapshot is empty

**File: `backend/api/sectors.py`**

Find (around line 147-148):
```python
    # --- Live data from Polygon snapshot (primary) ---
    polygon_snapshot = await _fetch_sector_snapshot(ALL_TICKERS)
```

Replace with:
```python
    # --- Live data from Polygon snapshot (primary) ---
    polygon_snapshot = await _fetch_sector_snapshot(ALL_TICKERS)
    if not polygon_snapshot:
        logger.warning("Sector heatmap: Polygon snapshot returned empty — falling back to historical bars only")
    else:
        logger.debug("Sector heatmap: Polygon snapshot returned %d tickers", len(polygon_snapshot))
```

---

## FIX 5: Earnings Visibility — Pre-load on Init + Earnings Date on Cards

### Problem
1. Chronos earnings data only loads when user clicks the "CHRONOS" tab — not visible by default
2. Trade idea cards and open position cards don't show upcoming earnings dates

### Step 5A: Pre-load Chronos earnings on page init

**File: `frontend/app.js`**

Find (around line 1275):
```javascript
        loadRegime(),
    ]);
```

Replace with:
```javascript
        loadRegime(),
    ]);
    
    // Pre-load Chronos earnings data so it's ready when tab is clicked
    loadChronosEarnings();
```

### Step 5B: Add next-earnings-date endpoint to backend

**File: `backend/api/chronos.py`**

Add the following new endpoint at the end of the file (before the closing of the module):

Find:
```python
    from jobs.chronos_ingest import run_chronos_earnings_ingest
    await run_chronos_earnings_ingest()
    return {"status": "ok", "message": "Earnings refresh complete"}
```

Replace with:
```python
    from jobs.chronos_ingest import run_chronos_earnings_ingest
    await run_chronos_earnings_ingest()
    return {"status": "ok", "message": "Earnings refresh complete"}


# ── GET /chronos/next-earnings ─────────────────────────────────────
@router.get("/next-earnings/{ticker}")
async def get_next_earnings(ticker: str):
    """Get the next upcoming earnings date for a ticker."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT report_date, timing FROM earnings_calendar WHERE ticker = $1 AND report_date >= CURRENT_DATE ORDER BY report_date ASC LIMIT 1",
            ticker.upper()
        )
    if row:
        return {"ticker": ticker.upper(), "next_date": row["report_date"].isoformat(), "timing": row["timing"]}
    return {"ticker": ticker.upper(), "next_date": None, "timing": None}


# ── GET /chronos/next-earnings-batch ───────────────────────────────
@router.get("/next-earnings-batch")
async def get_next_earnings_batch(tickers: str = Query(..., description="Comma-separated tickers")):
    """Batch fetch next earnings dates for multiple tickers."""
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        return {"earnings": {}}

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT DISTINCT ON (ticker) ticker, report_date, timing
               FROM earnings_calendar
               WHERE ticker = ANY($1) AND report_date >= CURRENT_DATE
               ORDER BY ticker, report_date ASC""",
            ticker_list
        )
    result = {}
    for r in rows:
        result[r["ticker"]] = {"date": r["report_date"].isoformat(), "timing": r["timing"]}
    return {"earnings": result}
```

Also add the Query import if not already present at the top of chronos.py:

Find:
```python
from fastapi import APIRouter, Depends, HTTPException, Query, Request
```

If `Query` is not in that import, add it. If the import line is different, just make sure `Query` is included.

### Step 5C: Fetch and display earnings dates on position cards

**File: `frontend/app.js`**

Search for the function that renders position cards — look for where position card HTML is built. Add the following helper function near the loadChronosEarnings section (at the end of the file, before the last few functions):

Add this new function at line ~12575 (just before the `// === CHRONOS EARNINGS ===` comment):

```javascript
// === EARNINGS DATE ENRICHMENT ===
async function enrichCardsWithEarnings() {
    // Collect all tickers from visible position cards and trade idea cards
    const cards = document.querySelectorAll('[data-ticker]');
    const tickers = [...new Set([...cards].map(c => c.dataset.ticker).filter(Boolean))];
    if (!tickers.length) return;

    try {
        const resp = await fetch(`${API_URL}/chronos/next-earnings-batch?tickers=${tickers.join(',')}`, { headers: authHeaders() });
        if (!resp.ok) return;
        const data = await resp.json();
        const earnings = data.earnings || {};

        cards.forEach(card => {
            const ticker = card.dataset.ticker;
            if (!ticker || !earnings[ticker]) return;
            
            // Skip if already has earnings badge
            if (card.querySelector('.earnings-date-badge')) return;

            const e = earnings[ticker];
            const dateStr = e.date;
            const timing = e.timing || '';
            const earningsDate = new Date(dateStr + 'T12:00:00');
            const now = new Date();
            const daysUntil = Math.ceil((earningsDate - now) / 86400000);

            // Only show if within 30 days
            if (daysUntil > 30 || daysUntil < 0) return;

            const urgency = daysUntil <= 3 ? 'urgent' : daysUntil <= 7 ? 'soon' : '';
            const timingLabel = timing === 'BMO' ? 'pre' : timing === 'AMC' ? 'post' : '';
            const badge = document.createElement('span');
            badge.className = `earnings-date-badge ${urgency}`;
            badge.title = `Earnings: ${dateStr} ${timingLabel}`;
            badge.textContent = `\uD83D\uDCC5 ${daysUntil}d ${timingLabel}`;
            
            // Insert at the top-right of the card
            const header = card.querySelector('.card-header, .position-card-header, .lightning-card-header');
            if (header) {
                header.appendChild(badge);
            } else {
                card.prepend(badge);
            }
        });
    } catch (err) {
        console.debug('Earnings enrichment error:', err);
    }
}
```

Then call it after positions and signals load. Find the section where `loadOpenPositionsEnhanced()` is called in the init block (around line 1273):

Find:
```javascript
        loadRegime(),
    ]);
    
    // Pre-load Chronos earnings data so it's ready when tab is clicked
    loadChronosEarnings();
```

Replace with:
```javascript
        loadRegime(),
    ]);
    
    // Pre-load Chronos earnings data so it's ready when tab is clicked
    loadChronosEarnings();
    
    // Enrich position/signal cards with earnings dates (runs after cards render)
    setTimeout(enrichCardsWithEarnings, 3000);
```

### Step 5D: Add earnings badge CSS

**File: `frontend/styles.css`**

Append:

```css
/* === EARNINGS DATE BADGES === */
.earnings-date-badge {
    display: inline-block;
    font-size: 9px;
    font-weight: 600;
    padding: 1px 5px;
    border-radius: 3px;
    background: rgba(100, 181, 246, 0.12);
    color: #64b5f6;
    margin-left: auto;
    white-space: nowrap;
}
.earnings-date-badge.soon {
    background: rgba(255, 152, 0, 0.15);
    color: #ff9800;
}
.earnings-date-badge.urgent {
    background: rgba(229, 55, 14, 0.15);
    color: #e5370e;
    animation: pulse-subtle 2s infinite;
}
```

---

## FIX 6: Greeks — Add Debug Logging

### Problem
Greeks row shows "--" for all values. The endpoint exists and code looks correct, but we can't tell if: (a) Polygon returns empty data, (b) positions lack strike/expiry fields, or (c) contracts don't match. Need logging to diagnose.

### File: `backend/api/unified_positions.py`

Find (in the `_portfolio_greeks_inner` function, around line 960):
```python
        for ticker, pos_list in by_ticker.items():
            try:
                greeks_result = await get_ticker_greeks_summary(ticker, pos_list)
                if greeks_result:
                    ticker_greeks[ticker] = greeks_result
```

Replace with:
```python
        for ticker, pos_list in by_ticker.items():
            try:
                logger.info("Greeks: fetching for %s (%d positions). Strikes: %s",
                           ticker, len(pos_list),
                           [(p.get("long_strike"), p.get("short_strike"), p.get("expiry")) for p in pos_list])
                greeks_result = await get_ticker_greeks_summary(ticker, pos_list)
                if greeks_result:
                    logger.info("Greeks: %s returned delta=%.2f gamma=%.4f theta=%.2f vega=%.2f",
                               ticker,
                               greeks_result.get("net_delta", 0),
                               greeks_result.get("net_gamma", 0),
                               greeks_result.get("net_theta", 0),
                               greeks_result.get("net_vega", 0))
                    ticker_greeks[ticker] = greeks_result
                else:
                    logger.warning("Greeks: %s returned None (snapshot empty or no matching contracts)", ticker)
```

Also add logging to the `get_ticker_greeks_summary` function in `backend/integrations/polygon_options.py`:

Find (around line 428):
```python
    chain = await get_options_snapshot(underlying)
    if not chain:
        return None
```

Replace with:
```python
    chain = await get_options_snapshot(underlying)
    if not chain:
        logger.warning("Greeks: options snapshot for %s returned empty chain", underlying)
        return None
    logger.debug("Greeks: %s chain has %d contracts", underlying, len(chain))
```

---

## VERIFICATION CHECKLIST

After deploying (wait 60-90s for Railway restart):

1. **Fix 1:** Refresh Agora → regime bar should show "Cautious (47/100)" or similar instead of "Hostile (-0/100)"
2. **Fix 2:** Wait 2+ minutes without refreshing → composite bias card should auto-update
3. **Fix 3:** Regime bar should appear INSIDE the Market Bias panel, above Factor Breakdown, as a compact single line
4. **Fix 4:** Check Railway logs for "Polygon sector snapshot" messages → if HTTP 403, need to upgrade Polygon plan; if 200 with data, sectors should show today's changes
5. **Fix 5:** Chronos tab should have earnings data. Position/signal cards should show blue "📅 Xd" badges for upcoming earnings
6. **Fix 6:** Check Railway logs for "Greeks:" messages → will reveal which positions are missing strike data and whether Polygon returns data

---

## ORDER OF OPERATIONS

Execute in this order — each fix is independent, commit after each:

1. Fix 1 (regime scaling) — `backend/api/regime.py`
2. Fix 2 (bias polling) — `frontend/app.js`
3. Fix 3 (regime bar relocation) — `frontend/index.html` + `frontend/app.js` + `frontend/styles.css`
4. Fix 4 (sector staleness) — `backend/api/sectors.py`
5. Fix 5 (earnings) — `frontend/app.js` + `backend/api/chronos.py` + `frontend/styles.css`
6. Fix 6 (greeks logging) — `backend/api/unified_positions.py` + `backend/integrations/polygon_options.py`
