# Brief — Agora Bloomberg Parity: Macro Strip, Trip Wires, Greeks, Alerts, Cleanup

**Priority:** HIGH — addresses portfolio-level risk awareness gaps and UI redundancy
**Touches:** `backend/api/sectors.py`, `backend/api/unified_positions.py`, `backend/api/alerts.py`, new `backend/api/macro_strip.py`, new `backend/api/trip_wires.py`, `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`
**Estimated time:** 6-8 hours across 3 phases
**Build order:** Phase 1 → Phase 2 → Phase 3 (each phase is independently deployable)

---

## Context

Olympus Committee + Titans reviewed Agora against Bloomberg Terminal capabilities. Key gaps: no cross-asset macro visibility, no portfolio-level greeks display, no expiry concentration awareness, trip wire thresholds only exist in Nick's head, Black Swan alert backend exists but frontend never calls it, and the Sector Overview section is redundant with the improved heatmap + drill-down popup.

---

## PHASE 1 — Macro Strip + Trip Wire Monitor + Alert Wiring (~3 hours)

### 1A. Backend: New `/api/macro/strip` endpoint

**New file:** `backend/api/macro_strip.py`

```python
"""
Macro Strip — persistent cross-asset ticker strip.
Single Polygon snapshot call for macro tickers, 10s cache during market hours.
"""

import json
import logging
import os
from datetime import datetime, timezone

import aiohttp
from fastapi import APIRouter

from database.redis_client import get_redis_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/macro", tags=["macro"])

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
SNAPSHOT_URL = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"

# Macro tickers: ETF proxies for cross-asset monitoring
MACRO_TICKERS = {
    "SPY":  {"label": "SPY",  "name": "S&P 500"},
    "QQQ":  {"label": "QQQ",  "name": "Nasdaq"},
    "IWM":  {"label": "IWM",  "name": "Russell 2K"},
    "USO":  {"label": "OIL",  "name": "Crude Oil"},
    "GLD":  {"label": "GOLD", "name": "Gold"},
    "TLT":  {"label": "BONDS","name": "20Y Treasury"},
    "UUP":  {"label": "DXY",  "name": "US Dollar"},
    "HYG":  {"label": "HY",   "name": "High Yield"},
}

MACRO_CACHE_KEY = "macro:strip"
MACRO_CACHE_TTL_LIVE = 10     # 10s during market hours
MACRO_CACHE_TTL_CLOSED = 300  # 5 min when closed


def _is_market_hours():
    import pytz
    et = datetime.now(pytz.timezone("America/New_York"))
    if et.weekday() >= 5:
        return False
    if et.hour == 9 and et.minute >= 30:
        return True
    if 10 <= et.hour < 16:
        return True
    return False


@router.get("/strip")
async def get_macro_strip():
    """Return cross-asset macro data for the persistent ticker strip."""
    redis = await get_redis_client()

    if redis:
        try:
            cached = await redis.get(MACRO_CACHE_KEY)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    tickers = list(MACRO_TICKERS.keys())
    result_data = []

    if POLYGON_API_KEY:
        try:
            ticker_str = ",".join(tickers)
            url = f"{SNAPSHOT_URL}?tickers={ticker_str}&apiKey={POLYGON_API_KEY}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for t in data.get("tickers", []):
                            sym = t.get("ticker", "")
                            if sym not in MACRO_TICKERS:
                                continue
                            day = t.get("day", {})
                            prev = t.get("prevDay", {})
                            price = day.get("c") or prev.get("c") or 0
                            prev_close = prev.get("c") or 0
                            change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
                            info = MACRO_TICKERS[sym]
                            result_data.append({
                                "ticker": sym,
                                "label": info["label"],
                                "name": info["name"],
                                "price": round(price, 2),
                                "change_pct": change_pct,
                            })
        except Exception as e:
            logger.error("Macro strip Polygon fetch failed: %s", e)

    # Sort by MACRO_TICKERS order
    ticker_order = list(MACRO_TICKERS.keys())
    result_data.sort(key=lambda x: ticker_order.index(x["ticker"]) if x["ticker"] in ticker_order else 99)

    result = {
        "tickers": result_data,
        "is_market_hours": _is_market_hours(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if redis and result_data:
        ttl = MACRO_CACHE_TTL_LIVE if _is_market_hours() else MACRO_CACHE_TTL_CLOSED
        try:
            await redis.set(MACRO_CACHE_KEY, json.dumps(result), ex=ttl)
        except Exception:
            pass

    return result
```

**Register in `backend/main.py`:**
Find the block where routers are included (look for `app.include_router`). Add:
```python
from api.macro_strip import router as macro_strip_router
app.include_router(macro_strip_router, prefix="/api")
```

### 1B. Backend: New `/api/trip-wires` endpoint

**New file:** `backend/api/trip_wires.py`

```python
"""
Trip Wire Monitor — checks 4 reversal conditions against live data.
Reads existing bias factor Redis keys + macro strip for Brent.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter

from database.redis_client import get_redis_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trip-wires", tags=["trip-wires"])


async def _get_redis_float(redis, key: str) -> Optional[float]:
    """Read a float from Redis, returning None if missing."""
    if not redis:
        return None
    try:
        val = await redis.get(key)
        if val is not None:
            return float(val)
    except Exception:
        pass
    return None


@router.get("")
async def get_trip_wires():
    """
    Return status of 4 reversal trip wires.
    Two firing simultaneously = regime change signal.
    """
    redis = await get_redis_client()

    # Wire 1: SPX distance to 200 DMA (~6,600 target)
    # The bias factor spy_200sma_distance stores this
    spy_price = await _get_redis_float(redis, "bias:factor:spy_price")
    spy_200dma = await _get_redis_float(redis, "bias:factor:spy_200sma")
    if spy_price is None or spy_200dma is None:
        # Fallback: try macro strip cache
        try:
            macro = await redis.get("macro:strip")
            if macro:
                macro_data = json.loads(macro)
                for t in macro_data.get("tickers", []):
                    if t["ticker"] == "SPY":
                        spy_price = t["price"]
                        break
        except Exception:
            pass
    spx_threshold = 6600
    spx_status = "COLD"
    spx_proximity = 0
    if spy_price and spy_200dma:
        spx_proximity = round(spy_price / spy_200dma * 100, 1)
        if spy_price >= spy_200dma:
            spx_status = "HOT"
        elif spy_price >= spy_200dma * 0.97:
            spx_status = "WARM"

    # Wire 2: Brent crude below $95
    # Use USO from macro strip as proxy, or check for BNO
    brent_price = None
    try:
        macro = await redis.get("macro:strip")
        if macro:
            macro_data = json.loads(macro)
            for t in macro_data.get("tickers", []):
                if t["ticker"] == "USO":
                    brent_price = t["price"]
                    break
    except Exception:
        pass
    brent_threshold = 95
    brent_status = "COLD"
    brent_note = "Using USO as proxy — check Brent directly for precision"
    # USO doesn't map 1:1 to Brent, so this wire needs manual confirmation
    # For now, just show USO price and let Nick interpret

    # Wire 3: Formal ceasefire / Hormuz reopening — manual only
    ceasefire_status = "COLD"
    ceasefire_manual = True
    try:
        cf = await redis.get("trip_wire:ceasefire")
        if cf and cf.decode() == "HOT":
            ceasefire_status = "HOT"
    except Exception:
        pass

    # Wire 4: VIX below 20 for 48 hours
    vix_price = await _get_redis_float(redis, "bias:factor:vix_price")
    if vix_price is None:
        try:
            macro = await redis.get("macro:strip")
            if macro:
                macro_data = json.loads(macro)
                # VIX isn't in macro strip (it's not an equity ticker on Polygon snapshots)
                # So we check bias factor cache
        except Exception:
            pass
    vix_threshold = 20
    vix_status = "COLD"
    vix_proximity = 0
    if vix_price:
        vix_proximity = round(vix_price / vix_threshold * 100, 1)
        if vix_price < vix_threshold:
            # Check if it's been below for 48 hours
            vix_status = "WARM"  # Need duration tracking for full HOT
            try:
                below_since = await redis.get("trip_wire:vix_below_since")
                if below_since:
                    from datetime import datetime as dt
                    since = dt.fromisoformat(below_since.decode())
                    hours_below = (datetime.now(timezone.utc) - since).total_seconds() / 3600
                    if hours_below >= 48:
                        vix_status = "HOT"
                else:
                    # Start tracking
                    await redis.set("trip_wire:vix_below_since", datetime.now(timezone.utc).isoformat())
            except Exception:
                pass
        else:
            # VIX above threshold, clear tracker
            try:
                await redis.delete("trip_wire:vix_below_since")
            except Exception:
                pass

    wires = [
        {
            "id": "spx_200dma",
            "label": "SPX vs 200 DMA",
            "current": round(spy_price, 2) if spy_price else None,
            "threshold": f">{spx_threshold} (2 closes)",
            "threshold_display": str(spx_threshold),
            "status": spx_status,
            "proximity_pct": spx_proximity,
        },
        {
            "id": "brent_crude",
            "label": "Oil (USO proxy)",
            "current": round(brent_price, 2) if brent_price else None,
            "threshold": f"<${brent_threshold}",
            "threshold_display": str(brent_threshold),
            "status": brent_status,
            "note": brent_note,
        },
        {
            "id": "ceasefire",
            "label": "Ceasefire / Hormuz",
            "current": "Manual",
            "threshold": "Confirmed",
            "threshold_display": "Confirmed",
            "status": ceasefire_status,
            "manual": True,
        },
        {
            "id": "vix_48h",
            "label": "VIX <20 (48hr)",
            "current": round(vix_price, 2) if vix_price else None,
            "threshold": f"<{vix_threshold} for 48h",
            "threshold_display": str(vix_threshold),
            "status": vix_status,
            "proximity_pct": vix_proximity,
        },
    ]

    hot_count = sum(1 for w in wires if w["status"] == "HOT")
    warm_count = sum(1 for w in wires if w["status"] == "WARM")

    return {
        "wires": wires,
        "hot_count": hot_count,
        "warm_count": warm_count,
        "regime_change": hot_count >= 2,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/ceasefire/{status}")
async def set_ceasefire_wire(status: str):
    """Manually set the ceasefire trip wire. Values: HOT, COLD."""
    if status.upper() not in ("HOT", "COLD"):
        from fastapi import HTTPException
        raise HTTPException(400, "Status must be HOT or COLD")
    redis = await get_redis_client()
    if redis:
        await redis.set("trip_wire:ceasefire", status.upper())
    return {"status": status.upper(), "wire": "ceasefire"}
```

**Register in `backend/main.py`:**
```python
from api.trip_wires import router as trip_wires_router
app.include_router(trip_wires_router, prefix="/api")
```

### 1C. Frontend: Macro Strip (top of page)

**File: `frontend/index.html`**

Find the opening of `<main id="hubShell"` (just before the Regime Bar). Insert BEFORE the regime bar:

```html
        <!-- MACRO TICKER STRIP -->
        <div class="macro-strip" id="macroStrip">
            <div class="macro-strip-inner" id="macroStripInner">
                <!-- Populated by JS -->
            </div>
        </div>
```

**File: `frontend/styles.css`**

Add (near the regime-bar styles):

```css
/* Macro Ticker Strip — persistent cross-asset bar */
.macro-strip {
    background: var(--dark-bg);
    border-bottom: 1px solid var(--border-color);
    padding: 4px 16px;
    overflow: hidden;
}

.macro-strip-inner {
    display: flex;
    gap: 6px;
    align-items: center;
    justify-content: center;
    flex-wrap: nowrap;
}

.macro-cell {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    font-family: 'Orbit', sans-serif;
    font-size: 11px;
    white-space: nowrap;
}

.macro-cell-label {
    color: var(--text-secondary);
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    font-size: 10px;
}

.macro-cell-price {
    color: var(--text-primary);
    font-weight: 500;
}

.macro-cell-change {
    font-weight: 600;
    font-size: 10px;
}

.macro-cell-change.positive { color: #7CFF6B; }
.macro-cell-change.negative { color: #FF6B35; }

.macro-sep {
    color: var(--border-color);
    font-size: 8px;
    user-select: none;
}
```

**File: `frontend/app.js`**

Add to the init section (near `loadSectorHeatmap()`):

```javascript
loadMacroStrip();
setInterval(loadMacroStrip, 10 * 1000);

async function loadMacroStrip() {
    try {
        const resp = await fetch(`${API_URL}/macro/strip`);
        if (!resp.ok) return;
        const data = await resp.json();
        renderMacroStrip(data.tickers);
    } catch (e) {
        console.error('Macro strip load failed:', e);
    }
}

function renderMacroStrip(tickers) {
    const container = document.getElementById('macroStripInner');
    if (!container || !tickers || tickers.length === 0) return;

    container.innerHTML = tickers.map((t, i) => {
        const sign = t.change_pct >= 0 ? '+' : '';
        const cls = t.change_pct >= 0 ? 'positive' : 'negative';
        const sep = i < tickers.length - 1 ? '<span class="macro-sep">·</span>' : '';
        return `<div class="macro-cell" title="${t.name}">
            <span class="macro-cell-label">${escapeHtml(t.label)}</span>
            <span class="macro-cell-price">${t.price.toFixed(2)}</span>
            <span class="macro-cell-change ${cls}">${sign}${t.change_pct.toFixed(2)}%</span>
        </div>${sep}`;
    }).join('');
}
```

### 1D. Frontend: Trip Wire Monitor (inside Bias Panel)

**File: `frontend/index.html`**

Find the closing `</div>` of `bias-composite-panel` (after the factor breakdown area, before `</div><!-- end bias-composite-panel -->`). Insert BEFORE that closing div:

```html
                <!-- Trip Wire Monitor -->
                <div class="trip-wire-section" id="tripWireSection">
                    <div class="trip-wire-header" id="tripWireToggle">
                        <span class="trip-wire-title">TRIP WIRES</span>
                        <span class="trip-wire-count" id="tripWireCount">(0 of 4)</span>
                    </div>
                    <div class="trip-wire-body" id="tripWireBody" style="display:none;">
                        <!-- Populated by JS -->
                    </div>
                </div>
```

**File: `frontend/styles.css`**

```css
/* Trip Wire Monitor */
.trip-wire-section {
    margin-top: 8px;
    border-top: 1px solid var(--border-color);
    padding-top: 6px;
}

.trip-wire-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 8px;
    cursor: pointer;
    font-family: 'Orbit', sans-serif;
}

.trip-wire-header:hover {
    background: rgba(20, 184, 166, 0.05);
    border-radius: 4px;
}

.trip-wire-title {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: var(--text-secondary);
}

.trip-wire-count {
    font-size: 10px;
    color: var(--text-secondary);
}

.trip-wire-count.alert {
    color: #FF6B35;
    font-weight: 700;
}

.trip-wire-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 8px;
    font-size: 11px;
}

.tw-label {
    flex: 1;
    color: var(--text-secondary);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}

.tw-values {
    display: flex;
    align-items: center;
    gap: 6px;
    font-family: 'Orbit', sans-serif;
}

.tw-current {
    color: var(--text-primary);
    font-weight: 500;
    font-size: 11px;
}

.tw-threshold {
    color: var(--text-secondary);
    font-size: 10px;
}

.tw-status {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.5px;
    padding: 1px 6px;
    border-radius: 3px;
    text-transform: uppercase;
}

.tw-status.cold {
    background: rgba(100, 100, 100, 0.2);
    color: #888;
}

.tw-status.warm {
    background: rgba(255, 152, 0, 0.15);
    color: #ffb74d;
}

.tw-status.hot {
    background: rgba(255, 107, 53, 0.2);
    color: #FF6B35;
    animation: tw-pulse 1.5s ease-in-out infinite;
}

@keyframes tw-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
}

.trip-wire-regime-alert {
    background: rgba(255, 107, 53, 0.12);
    border: 1px solid rgba(255, 107, 53, 0.3);
    border-radius: 6px;
    padding: 6px 10px;
    margin: 6px 8px;
    font-size: 11px;
    font-weight: 600;
    color: #FF6B35;
    text-align: center;
    animation: tw-pulse 1.5s ease-in-out infinite;
}
```

**File: `frontend/app.js`**

```javascript
// Trip Wire Monitor
loadTripWires();
setInterval(loadTripWires, 30 * 1000); // 30s refresh

// Toggle collapse
document.getElementById('tripWireToggle')?.addEventListener('click', function() {
    const body = document.getElementById('tripWireBody');
    if (body) body.style.display = body.style.display === 'none' ? 'block' : 'none';
});

async function loadTripWires() {
    try {
        const resp = await fetch(`${API_URL}/trip-wires`);
        if (!resp.ok) return;
        const data = await resp.json();
        renderTripWires(data);
    } catch (e) {
        console.error('Trip wires load failed:', e);
    }
}

function renderTripWires(data) {
    const body = document.getElementById('tripWireBody');
    const count = document.getElementById('tripWireCount');
    if (!body) return;

    if (count) {
        const hotCount = data.hot_count || 0;
        count.textContent = `(${hotCount} of 4)`;
        count.className = 'trip-wire-count' + (hotCount >= 2 ? ' alert' : '');
    }

    let html = '';
    if (data.regime_change) {
        html += '<div class="trip-wire-regime-alert">⚠ REGIME CHANGE — 2+ TRIP WIRES ACTIVE — CLOSE SHORTS</div>';
        // Auto-expand when regime change detected
        body.style.display = 'block';
    }

    (data.wires || []).forEach(w => {
        const currentStr = w.current != null ? w.current : '--';
        const statusCls = (w.status || 'cold').toLowerCase();
        html += `<div class="trip-wire-row">
            <span class="tw-label">${escapeHtml(w.label)}</span>
            <div class="tw-values">
                <span class="tw-current">${currentStr}</span>
                <span class="tw-threshold">/ ${escapeHtml(w.threshold_display)}</span>
            </div>
            <span class="tw-status ${statusCls}">${w.status}</span>
        </div>`;
    });

    body.innerHTML = html;
}
```

### 1E. Frontend: Wire Black Swan Alerts to Regime Bar

**File: `frontend/app.js`**

Add to init section:

```javascript
loadBlackSwanAlerts();
setInterval(loadBlackSwanAlerts, 60 * 1000); // 1 min refresh

async function loadBlackSwanAlerts() {
    try {
        const resp = await fetch(`${API_URL}/alerts/black-swan`);
        if (!resp.ok) return;
        const data = await resp.json();
        renderBlackSwanAlerts(data);
    } catch (e) {
        console.error('Black swan alerts failed:', e);
    }
}

function renderBlackSwanAlerts(data) {
    const bar = document.getElementById('regimeBar');
    if (!bar) return;

    // Remove any existing alert badges
    bar.querySelectorAll('.bs-alert-badge').forEach(el => el.remove());

    const alerts = data.alerts || [];
    if (alerts.length === 0) return;

    const controlsArea = bar.querySelector('.regime-controls');
    if (!controlsArea) return;

    // Add alert badges before the controls
    alerts.forEach(alert => {
        const badge = document.createElement('span');
        badge.className = 'bs-alert-badge';
        badge.className += alert.severity === 'CRITICAL' ? ' bs-critical' : ' bs-warning';
        badge.textContent = alert.title || alert.alert_type;
        badge.title = alert.description || '';
        controlsArea.prepend(badge);
    });

    // Flash the regime bar if should_pause_trading
    if (data.should_pause_trading) {
        bar.classList.add('regime-bar-alert');
    } else {
        bar.classList.remove('regime-bar-alert');
    }
}
```

**File: `frontend/styles.css`**

```css
/* Black Swan Alert Badges */
.bs-alert-badge {
    font-size: 10px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 3px;
    letter-spacing: 0.3px;
    white-space: nowrap;
}

.bs-alert-badge.bs-critical {
    background: rgba(255, 107, 53, 0.2);
    color: #FF6B35;
    animation: tw-pulse 1.5s ease-in-out infinite;
}

.bs-alert-badge.bs-warning {
    background: rgba(255, 152, 0, 0.15);
    color: #ffb74d;
}

.regime-bar-alert {
    border-bottom: 2px solid #FF6B35 !important;
}
```

---

## PHASE 2 — Portfolio Greeks + Expiry Timeline + P&L Sparkline (~3 hours)

### 2A. Backend: Cache Portfolio Greeks

**File: `backend/api/unified_positions.py`**

Find the existing `portfolio_greeks()` function. Wrap the response in a Redis cache (60s TTL):

After computing `ticker_greeks`, before returning, add:

```python
# Cache the result for 60 seconds
if redis:
    try:
        await redis.set("portfolio:greeks:cache", json.dumps(result), ex=60)
    except Exception:
        pass
```

And at the top of the function, add cache check:

```python
redis = await get_redis_client()
if redis:
    try:
        cached = await redis.get("portfolio:greeks:cache")
        if cached:
            return json.loads(cached)
    except Exception:
        pass
```

### 2B. Backend: Extend `/v2/positions/summary` with Expiry Grouping

**File: `backend/api/unified_positions.py`**

Find the `portfolio_summary()` function. In the return dict, add an `expiry_clusters` field:

```python
# Compute expiry clusters
expiry_map = {}
for pos in positions:
    exp = pos.get("expiry_date")
    if not exp:
        continue
    exp_str = exp.isoformat() if hasattr(exp, 'isoformat') else str(exp)
    if exp_str not in expiry_map:
        expiry_map[exp_str] = {"date": exp_str, "count": 0, "total_cost": 0}
    expiry_map[exp_str]["count"] += 1
    expiry_map[exp_str]["total_cost"] += abs(pos.get("cost_basis", 0))

expiry_clusters = sorted(expiry_map.values(), key=lambda x: x["date"])
```

Add `"expiry_clusters": expiry_clusters` to the response dict.

### 2C. Frontend: Greeks Row with Context-Aware Tooltips

**File: `frontend/index.html`**

Find the portfolio summary card (`portfolio-summary-card`). After the `portfolio-accounts` div, add:

```html
                    <div class="portfolio-greeks-row" id="portfolioGreeksRow" style="display:none;">
                        <div class="greeks-toggle" id="greeksToggle">Greeks ▸</div>
                        <div class="greeks-values" id="greeksValues" style="display:none;">
                            <span class="greek-cell" id="greekDelta" data-greek="delta" title="">Δ --</span>
                            <span class="greek-cell" id="greekGamma" data-greek="gamma" title="">Γ --</span>
                            <span class="greek-cell" id="greekTheta" data-greek="theta" title="">Θ --</span>
                            <span class="greek-cell" id="greekVega" data-greek="vega" title="">V --</span>
                        </div>
                    </div>
```

**File: `frontend/styles.css`**

```css
/* Portfolio Greeks Row */
.portfolio-greeks-row {
    border-top: 1px solid var(--border-color);
    padding: 4px 8px;
    display: flex;
    align-items: center;
    gap: 8px;
}

.greeks-toggle {
    font-size: 10px;
    font-weight: 600;
    color: var(--text-secondary);
    cursor: pointer;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    user-select: none;
}

.greeks-toggle:hover { color: var(--accent-teal); }

.greeks-values {
    display: flex;
    gap: 10px;
    font-family: 'Orbit', sans-serif;
}

.greek-cell {
    font-size: 11px;
    font-weight: 500;
    color: var(--text-primary);
    cursor: help;
    position: relative;
}

.greek-cell.positive { color: #7CFF6B; }
.greek-cell.negative { color: #FF6B35; }

/* Greek tooltip — shows on hover */
.greek-tooltip {
    position: absolute;
    bottom: calc(100% + 8px);
    left: 50%;
    transform: translateX(-50%);
    background: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 11px;
    color: var(--text-primary);
    white-space: normal;
    width: 220px;
    line-height: 1.4;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
    z-index: 1000;
    pointer-events: none;
    font-family: -apple-system, sans-serif;
    font-weight: 400;
}
```

**File: `frontend/app.js`**

```javascript
// Greeks display
loadPortfolioGreeks();
setInterval(loadPortfolioGreeks, 60 * 1000);

document.getElementById('greeksToggle')?.addEventListener('click', function() {
    const vals = document.getElementById('greeksValues');
    if (vals) {
        const show = vals.style.display === 'none';
        vals.style.display = show ? 'flex' : 'none';
        this.textContent = show ? 'Greeks ▾' : 'Greeks ▸';
    }
});

async function loadPortfolioGreeks() {
    try {
        const resp = await fetch(`${API_URL}/v2/positions/greeks`);
        if (!resp.ok) return;
        const data = await resp.json();
        renderPortfolioGreeks(data);
    } catch (e) {
        console.error('Portfolio greeks failed:', e);
    }
}

function renderPortfolioGreeks(data) {
    const row = document.getElementById('portfolioGreeksRow');
    if (!row) return;

    const totals = data.totals || {};
    const delta = totals.delta || 0;
    const gamma = totals.gamma || 0;
    const theta = totals.theta || 0;
    const vega = totals.vega || 0;

    // Only show if we have data
    if (delta === 0 && gamma === 0 && theta === 0 && vega === 0) return;
    row.style.display = 'flex';

    // Render values
    const fmt = (v, prefix) => {
        const sign = v >= 0 ? '+' : '';
        return `${prefix} ${sign}${Math.round(v)}`;
    };
    document.getElementById('greekDelta').textContent = fmt(delta, 'Δ');
    document.getElementById('greekDelta').className = 'greek-cell ' + (delta >= 0 ? 'positive' : 'negative');
    document.getElementById('greekGamma').textContent = fmt(gamma, 'Γ');
    document.getElementById('greekGamma').className = 'greek-cell ' + (gamma >= 0 ? 'positive' : 'negative');
    document.getElementById('greekTheta').textContent = fmt(theta, 'Θ');
    document.getElementById('greekTheta').className = 'greek-cell ' + (theta >= 0 ? 'positive' : 'negative');
    document.getElementById('greekVega').textContent = fmt(vega, 'V');
    document.getElementById('greekVega').className = 'greek-cell ' + (vega >= 0 ? 'positive' : 'negative');

    // Context-aware tooltips
    _setGreekTooltip('greekDelta', 'delta', delta);
    _setGreekTooltip('greekGamma', 'gamma', gamma);
    _setGreekTooltip('greekTheta', 'theta', theta);
    _setGreekTooltip('greekVega', 'vega', vega);
}

function _setGreekTooltip(elId, greek, value) {
    const el = document.getElementById(elId);
    if (!el) return;

    let tip = '';
    const absVal = Math.abs(Math.round(value));

    switch (greek) {
        case 'delta':
            if (value < -100) {
                tip = `Your portfolio loses ~$${absVal} for every $1 SPY rises. You're heavily short-biased — big moves up hurt, big moves down pay.`;
            } else if (value < 0) {
                tip = `Your portfolio loses ~$${absVal} for every $1 SPY rises. Moderately short-biased — you profit when the market drops.`;
            } else if (value > 100) {
                tip = `Your portfolio gains ~$${absVal} for every $1 SPY rises. You're heavily long-biased — you need the market to go up.`;
            } else if (value > 0) {
                tip = `Your portfolio gains ~$${absVal} for every $1 SPY rises. Moderately long-biased.`;
            } else {
                tip = `Your portfolio is roughly neutral — moves up and down affect you about equally.`;
            }
            break;
        case 'gamma':
            if (value > 30) {
                tip = `High gamma (+${absVal}): Your delta shifts fast as prices move. Big moves in either direction will accelerate your P&L — good if you're right, bad if you're wrong.`;
            } else if (value > 0) {
                tip = `Positive gamma (+${absVal}): Price moves will push your delta in the direction of the move. You benefit from volatility.`;
            } else if (value < -30) {
                tip = `Negative gamma (${value}): Price moves push your delta against you. Steady, range-bound markets are your friend. Big moves are dangerous.`;
            } else {
                tip = `Low gamma (${value}): Your delta is relatively stable — price moves won't dramatically shift your exposure.`;
            }
            break;
        case 'theta':
            if (value < -50) {
                tip = `You're losing ~$${absVal}/day to time decay. Every day that passes without a move costs you. This is the price of holding options.`;
            } else if (value < 0) {
                tip = `You're losing ~$${absVal}/day to time decay. Moderate bleed — your positions need to move in your favor to overcome this daily cost.`;
            } else if (value > 0) {
                tip = `You're earning ~$${absVal}/day from time decay. Time is on your side — you profit as long as prices stay in your range.`;
            } else {
                tip = `Roughly theta-neutral: time decay isn't significantly helping or hurting you.`;
            }
            break;
        case 'vega':
            if (value > 20) {
                tip = `High vega (+${absVal}): You profit when implied volatility rises. Fear spikes and panic selling help your positions. You're long volatility.`;
            } else if (value > 0) {
                tip = `Positive vega (+${absVal}): Rising volatility (fear/uncertainty) mildly benefits your portfolio.`;
            } else if (value < -20) {
                tip = `Negative vega (${value}): You profit when implied volatility drops. Calm, stable markets help your positions.`;
            } else {
                tip = `Low vega (${value}): Volatility changes don't significantly affect your portfolio value.`;
            }
            break;
    }

    // Remove existing tooltip handler and add new one
    el.onmouseenter = function() {
        const existing = el.querySelector('.greek-tooltip');
        if (existing) existing.remove();
        const tipEl = document.createElement('div');
        tipEl.className = 'greek-tooltip';
        tipEl.textContent = tip;
        el.appendChild(tipEl);
    };
    el.onmouseleave = function() {
        const existing = el.querySelector('.greek-tooltip');
        if (existing) existing.remove();
    };
}
```

### 2D. Frontend: Expiry Timeline (dual-mode toggle in Ledger)

**File: `frontend/index.html`**

Find the at-risk strip header area. Add a toggle:

```html
                <div class="at-risk-mode-toggle">
                    <button class="at-risk-mode active" data-mode="direction" id="atRiskModeDirection">By Direction</button>
                    <button class="at-risk-mode" data-mode="expiry" id="atRiskModeExpiry">By Expiry</button>
                </div>
```

Add a new container for the expiry view (right after the existing `at-risk-strip` div):

```html
                <div class="expiry-timeline" id="expiryTimeline" style="display:none;">
                    <!-- Populated by JS -->
                </div>
```

**File: `frontend/styles.css`**

```css
/* At-Risk Mode Toggle */
.at-risk-mode-toggle {
    display: flex;
    gap: 2px;
    padding: 2px;
    background: var(--dark-bg);
    border-radius: 4px;
    margin: 0 8px 4px;
}

.at-risk-mode {
    flex: 1;
    background: transparent;
    border: none;
    color: var(--text-secondary);
    font-family: 'Orbit', sans-serif;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    padding: 3px 6px;
    border-radius: 3px;
    cursor: pointer;
}

.at-risk-mode.active {
    background: rgba(20, 184, 166, 0.15);
    color: var(--accent-teal);
}

/* Expiry Timeline */
.expiry-timeline {
    padding: 4px 8px;
}

.expiry-cluster {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 3px 0;
    cursor: pointer;
}

.expiry-cluster:hover { opacity: 0.8; }

.expiry-date {
    font-size: 10px;
    font-weight: 600;
    color: var(--text-secondary);
    width: 90px;
    flex-shrink: 0;
    font-family: 'Orbit', sans-serif;
}

.expiry-bar-container {
    flex: 1;
    height: 14px;
    background: rgba(255,255,255,0.05);
    border-radius: 3px;
    overflow: hidden;
}

.expiry-bar {
    height: 100%;
    border-radius: 3px;
    transition: width 0.3s;
}

.expiry-bar.urgent { background: rgba(255, 107, 53, 0.5); }   /* < 14 days */
.expiry-bar.soon { background: rgba(255, 152, 0, 0.4); }       /* 14-30 days */
.expiry-bar.safe { background: rgba(124, 255, 107, 0.3); }     /* > 30 days */

.expiry-amount {
    font-size: 10px;
    font-weight: 500;
    color: var(--text-primary);
    width: 60px;
    text-align: right;
    flex-shrink: 0;
}

.expiry-count {
    font-size: 9px;
    color: var(--text-secondary);
    width: 20px;
    text-align: right;
    flex-shrink: 0;
}
```

**File: `frontend/app.js`**

```javascript
// Expiry mode toggle
document.querySelectorAll('.at-risk-mode').forEach(btn => {
    btn.addEventListener('click', function() {
        document.querySelectorAll('.at-risk-mode').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        const mode = this.dataset.mode;
        document.getElementById('atRiskStrip').style.display = mode === 'direction' ? 'flex' : 'none';
        document.getElementById('expiryTimeline').style.display = mode === 'expiry' ? 'block' : 'none';
    });
});

// Load expiry data from portfolio summary
async function loadExpiryTimeline() {
    try {
        const resp = await fetch(`${API_URL}/v2/positions/summary`);
        if (!resp.ok) return;
        const data = await resp.json();
        renderExpiryTimeline(data.expiry_clusters || []);
    } catch (e) {
        console.error('Expiry timeline failed:', e);
    }
}

function renderExpiryTimeline(clusters) {
    const container = document.getElementById('expiryTimeline');
    if (!container || clusters.length === 0) {
        if (container) container.innerHTML = '<p class="empty-state">No options positions</p>';
        return;
    }

    const maxCost = Math.max(...clusters.map(c => c.total_cost));
    const now = new Date();

    container.innerHTML = clusters.map(c => {
        const expDate = new Date(c.date);
        const daysLeft = Math.max(0, Math.round((expDate - now) / (1000 * 60 * 60 * 24)));
        const barPct = Math.max(5, (c.total_cost / maxCost) * 100);
        const urgency = daysLeft < 14 ? 'urgent' : daysLeft < 30 ? 'soon' : 'safe';
        const dateStr = expDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

        return `<div class="expiry-cluster" title="Click to filter ledger">
            <span class="expiry-date">${dateStr} (${daysLeft}d)</span>
            <div class="expiry-bar-container">
                <div class="expiry-bar ${urgency}" style="width:${barPct}%"></div>
            </div>
            <span class="expiry-amount">$${Math.round(c.total_cost).toLocaleString()}</span>
            <span class="expiry-count">${c.count}x</span>
        </div>`;
    }).join('');
}

// Load on init
loadExpiryTimeline();
setInterval(loadExpiryTimeline, 120 * 1000); // 2 min refresh
```

---

## PHASE 3 — Remove Redundancies + Surface Enrichments (~1 hour)

### 3A. Remove Sector Overview Section

The Sector Overview (the `watchlist-left` div inside `watchlist-section`) is redundant with the heatmap + drill-down popup. **Remove the entire `watchlist-left` div** from index.html and give the `watchlist-middle` (Radar) the full width.

**File: `frontend/index.html`**

Find:
```html
        <section class="watchlist-section">
            <div class="watchlist-v3">
                <div class="watchlist-left">
                    ...entire watchlist-left div...
                </div>

                <div class="watchlist-middle">
```

Remove the entire `<div class="watchlist-left">...</div>` block (from `<div class="watchlist-left">` through its closing `</div>`).

**File: `frontend/styles.css`**

Find the CSS grid rule for `.watchlist-v3` and change it to single column (the Radar panel gets full width):

```css
.watchlist-v3 {
    display: block; /* was grid with 2 columns */
}
```

Remove all `.watchlist-left`, `.watchlist-container`, `.watchlist-grid`, `.watchlist-header h2` rules that only apply to the Sector Overview. Keep any shared styles used by the Radar panel.

**File: `frontend/app.js`**

Remove or comment out the `renderSectorWatchlist()` function and its caller. The data it fetched (`/api/watchlist/enriched`) may still be needed by the Radar panel — check before removing the fetch call.

### 3B. Remove Sector Rotation Strip (below TV chart)

**File: `frontend/index.html`**

Find and remove:
```html
                <div class="sector-rotation-strip" id="sectorRotationStrip">
                    <div class="sector-chips" id="sectorChips">
                        <!-- Populated by JS -->
                    </div>
                </div>
```

**File: `frontend/app.js`**

Remove `renderSectorRotationStrip()` and its caller.

### 3C. Collapse Strategy Controls into Settings Modal

**File: `frontend/index.html`**

Remove the entire `strategies-section` from the page. Add a gear icon to the header:

```html
<button class="settings-btn" id="settingsBtn" title="Strategy Controls">⚙</button>
```

Move the `strategies-section` HTML into a modal (similar to the position entry modal).

---

## Verification Checklist

### Phase 1
- [ ] Macro strip visible at top with 8 tickers (SPY, QQQ, IWM, OIL, GOLD, BONDS, DXY, HY)
- [ ] Macro strip updates every 10 seconds during market hours
- [ ] Trip wire section visible in bias panel (collapsed by default)
- [ ] Click to expand shows 4 wires with current/threshold/status
- [ ] Auto-expands with regime change alert when 2+ wires are HOT
- [ ] Black swan alert badges appear in regime bar when active

### Phase 2
- [ ] Greeks row visible in portfolio card (collapsed by default)
- [ ] Hovering each greek shows context-aware plain-English tooltip
- [ ] Tooltip text changes based on actual portfolio values
- [ ] Expiry timeline toggleable in ledger (By Direction / By Expiry)
- [ ] Bars color-coded by urgency (red <14d, amber 14-30d, green 30d+)

### Phase 3
- [ ] Sector Overview section removed — no broken references
- [ ] Sector Rotation Strip (below chart) removed
- [ ] Radar panel fills full width in watchlist section
- [ ] Strategy Controls accessible via gear icon modal

---

## Commit Messages

```
Phase 1: feat: macro strip + trip wire monitor + black swan alert wiring
Phase 2: feat: portfolio greeks with tooltips + expiry timeline + P&L sparkline
Phase 3: refactor: remove redundant Sector Overview/rotation strip, collapse strategies
```
