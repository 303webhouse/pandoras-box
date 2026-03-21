# Brief — Intelligence Center: Market Map + Flow Radar (Middle Column Redesign)

**Priority:** HIGH — transforms the most visible UI real estate from 3 disconnected tabs into an integrated intelligence center
**Touches:** `backend/api/flow_radar.py` (NEW), `backend/main.py`, `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`
**Estimated time:** 4–5 hours
**Context:** Olympus + Titans joint review. Middle column currently has 3 tabs (Sectors/Flow/Headlines) where Flow is dead and Headlines requires a click to see. Redesign merges them into a 2-section stacked layout.

---

## Design Overview

Replace the current 3-tab structure with two always-visible stacked sections:

**Top: MARKET MAP** — Sector heatmap (unchanged) with flow-dot overlay on each cell + a compact one-line market pulse + 3 headline strip. No tabs — everything visible at once.

**Bottom: FLOW RADAR** — Scrollable prioritized list with 3 sub-sections:
1. **Position Flow** — open positions with flow alignment (confirming/counter)
2. **Unusual Activity** — watchlist tickers with extreme P/C ratios or premium spikes
3. **Sector Rotation** — which sectors have the heaviest call vs. put premium

Both sections refresh every 2 minutes during market hours.

---

## Part 1 — Backend: New `/api/flow/radar` Endpoint

### File: `backend/api/flow_radar.py` (NEW FILE)

This replaces the dumb `/api/flow/summary` as the primary flow data endpoint for the UI. It combines:
- UW flow data from Redis (`uw:flow:*`)
- Open positions from `unified_positions`
- Watchlist tickers with sector from `watchlist_tickers`
- Sector mapping from static `SECTOR_WEIGHTS` dict
- Current bias from Redis `bias:composite:latest`

```python
"""
Flow Radar API — contextual flow intelligence for the Agora middle column.

Combines UW options flow data with positions, watchlist, and sector data
into a single dashboard-friendly payload. Replaces the old /flow/summary
as the primary frontend data source.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from fastapi import APIRouter
from database.redis_client import get_redis_client
from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/flow", tags=["flow-radar"])

# Map sector names from watchlist_tickers to sector ETFs
# watchlist_tickers uses full names like "Technology", "Health Care"
# sectors.py uses ETFs like "XLK", "XLV"
SECTOR_NAME_TO_ETF = {
    "technology": "XLK",
    "information technology": "XLK",
    "financials": "XLF",
    "health care": "XLV",
    "healthcare": "XLV",
    "consumer discretionary": "XLY",
    "consumer disc.": "XLY",
    "communication services": "XLC",
    "communications": "XLC",
    "industrials": "XLI",
    "consumer staples": "XLP",
    "energy": "XLE",
    "utilities": "XLU",
    "real estate": "XLRE",
    "materials": "XLB",
}


def _format_premium(val):
    """Format premium as human-readable string."""
    if not val or val == 0:
        return "$0"
    if val >= 1_000_000_000:
        return f"${val / 1_000_000_000:.1f}B"
    if val >= 1_000_000:
        return f"${val / 1_000_000:.0f}M"
    if val >= 1_000:
        return f"${val / 1_000:.0f}K"
    return f"${val}"


@router.get("/radar")
async def get_flow_radar():
    """
    Contextual flow intelligence: positions, watchlist, sectors, market pulse.
    
    Returns:
        position_flow: open positions matched with UW flow alignment
        watchlist_unusual: watchlist tickers with extreme flow activity
        sector_flow: per-sector aggregated flow from UW data
        market_pulse: overall market flow + bias regime
        headlines_compact: latest 3 headlines for the strip
    """
    redis = await get_redis_client()
    pool = await get_postgres_client()

    # === 1. Load all UW flow data from Redis in one batch ===
    flow_data: Dict[str, Dict] = {}
    if redis:
        try:
            # Scan for all uw:flow:* keys
            keys = []
            cursor = b"0"
            while True:
                cursor, batch = await redis.scan(cursor, match="uw:flow:*", count=200)
                keys.extend(batch)
                if cursor == b"0" or cursor == 0:
                    break

            if keys:
                values = await redis.mget(*keys)
                for key, val in zip(keys, values):
                    if not val:
                        continue
                    try:
                        parsed = json.loads(val)
                        ticker = parsed.get("ticker", "").upper()
                        if ticker:
                            flow_data[ticker] = parsed
                    except (json.JSONDecodeError, TypeError):
                        continue
        except Exception as e:
            logger.warning("Flow radar Redis scan failed: %s", e)

    # === 2. Load open positions ===
    position_flow = []
    if pool:
        try:
            async with pool.acquire() as conn:
                pos_rows = await conn.fetch(
                    "SELECT ticker, direction, structure, position_id FROM unified_positions WHERE status = 'OPEN'"
                )
            for row in pos_rows:
                ticker = (row["ticker"] or "").upper()
                direction = (row["direction"] or "LONG").upper()
                flow = flow_data.get(ticker)
                if not flow:
                    continue  # No flow data for this ticker — skip

                flow_sentiment = (flow.get("sentiment") or "NEUTRAL").upper()
                pc_ratio = flow.get("pc_ratio")

                # Determine alignment
                is_long = direction in ("LONG", "BUY")
                is_short = direction in ("SHORT", "SELL", "MIXED")
                if flow_sentiment == "BULLISH" and is_long:
                    alignment = "CONFIRMING"
                elif flow_sentiment == "BEARISH" and is_short:
                    alignment = "CONFIRMING"
                elif flow_sentiment == "BULLISH" and is_short:
                    alignment = "COUNTER"
                elif flow_sentiment == "BEARISH" and is_long:
                    alignment = "COUNTER"
                else:
                    alignment = "NEUTRAL"

                # Strength
                strength = "WEAK"
                if pc_ratio is not None:
                    if pc_ratio < 0.5 or pc_ratio > 2.0:
                        strength = "STRONG"
                    elif pc_ratio < 0.7 or pc_ratio > 1.3:
                        strength = "MODERATE"

                position_flow.append({
                    "ticker": ticker,
                    "position_id": row["position_id"],
                    "direction": direction,
                    "structure": row["structure"],
                    "alignment": alignment,
                    "strength": strength,
                    "sentiment": flow_sentiment,
                    "pc_ratio": pc_ratio,
                    "total_premium": flow.get("total_premium"),
                    "premium_display": _format_premium(flow.get("total_premium")),
                })
        except Exception as e:
            logger.warning("Flow radar position load failed: %s", e)

    # === 3. Load watchlist tickers with sectors, find unusual flow ===
    watchlist_unusual = []
    ticker_to_sector: Dict[str, str] = {}
    if pool:
        try:
            async with pool.acquire() as conn:
                wl_rows = await conn.fetch(
                    "SELECT symbol, sector FROM watchlist_tickers WHERE muted = false"
                )
            for row in wl_rows:
                ticker = (row["symbol"] or "").upper()
                sector = row["sector"] or "Unknown"
                ticker_to_sector[ticker] = sector

                flow = flow_data.get(ticker)
                if not flow:
                    continue

                pc_ratio = flow.get("pc_ratio")
                total_premium = flow.get("total_premium") or 0
                sentiment = (flow.get("sentiment") or "NEUTRAL").upper()
                change_pct = flow.get("change_pct")

                # "Unusual" = extreme P/C ratio (< 0.5 or > 2.0)
                is_unusual = (pc_ratio is not None and (pc_ratio < 0.5 or pc_ratio > 2.0))

                # "Divergence" = price moving opposite to flow sentiment
                divergence = False
                if change_pct is not None and sentiment != "NEUTRAL":
                    if sentiment == "BULLISH" and change_pct < -0.5:
                        divergence = True  # Smart money buying the dip
                    elif sentiment == "BEARISH" and change_pct > 0.5:
                        divergence = True  # Smart money selling the rip

                if is_unusual or divergence:
                    watchlist_unusual.append({
                        "ticker": ticker,
                        "sector": sector,
                        "sentiment": sentiment,
                        "pc_ratio": pc_ratio,
                        "total_premium": total_premium,
                        "premium_display": _format_premium(total_premium),
                        "change_pct": change_pct,
                        "divergence": divergence,
                        "unusual": is_unusual,
                    })

            # Sort: divergences first, then by premium descending
            watchlist_unusual.sort(
                key=lambda x: (not x["divergence"], -(x["total_premium"] or 0))
            )
            # Limit to top 10
            watchlist_unusual = watchlist_unusual[:10]
        except Exception as e:
            logger.warning("Flow radar watchlist load failed: %s", e)

    # === 4. Aggregate flow by sector ===
    sector_flow = []
    sector_agg: Dict[str, Dict[str, Any]] = {}  # ETF -> aggregated data

    for ticker, flow in flow_data.items():
        sector_name = ticker_to_sector.get(ticker, "").lower()
        etf = SECTOR_NAME_TO_ETF.get(sector_name)
        if not etf:
            # Also try matching the ticker itself if it's a sector ETF
            if ticker in ("XLK", "XLF", "XLV", "XLY", "XLC", "XLI", "XLP", "XLE", "XLU", "XLRE", "XLB"):
                etf = ticker
        if not etf:
            continue

        if etf not in sector_agg:
            sector_agg[etf] = {
                "etf": etf,
                "call_premium": 0,
                "put_premium": 0,
                "total_premium": 0,
                "ticker_count": 0,
                "pc_ratios": [],
            }

        s = sector_agg[etf]
        s["call_premium"] += flow.get("call_premium") or 0
        s["put_premium"] += flow.get("put_premium") or 0
        s["total_premium"] += flow.get("total_premium") or 0
        s["ticker_count"] += 1
        if flow.get("pc_ratio") is not None:
            s["pc_ratios"].append(flow["pc_ratio"])

    for etf, agg in sector_agg.items():
        avg_pc = round(sum(agg["pc_ratios"]) / len(agg["pc_ratios"]), 2) if agg["pc_ratios"] else None
        if avg_pc is not None:
            if avg_pc < 0.7:
                sentiment = "BULLISH"
            elif avg_pc > 1.3:
                sentiment = "BEARISH"
            else:
                sentiment = "NEUTRAL"
        else:
            sentiment = "NEUTRAL"

        sector_flow.append({
            "etf": etf,
            "sentiment": sentiment,
            "avg_pc_ratio": avg_pc,
            "total_premium": agg["total_premium"],
            "premium_display": _format_premium(agg["total_premium"]),
            "ticker_count": agg["ticker_count"],
        })

    # Sort by total premium descending
    sector_flow.sort(key=lambda x: -(x["total_premium"] or 0))

    # === 5. Market pulse: overall flow + bias ===
    total_call = sum(f.get("call_premium") or 0 for f in flow_data.values())
    total_put = sum(f.get("put_premium") or 0 for f in flow_data.values())
    total_all = total_call + total_put
    overall_pc = round(total_put / max(total_call, 1), 2) if total_call > 0 else 0

    if overall_pc < 0.7:
        overall_sentiment = "BULLISH"
    elif overall_pc > 1.3:
        overall_sentiment = "BEARISH"
    else:
        overall_sentiment = "NEUTRAL"

    # Bias from Redis
    bias_level = "NEUTRAL"
    if redis:
        try:
            bias_raw = await redis.get("bias:composite:latest")
            if bias_raw:
                bias_data = json.loads(bias_raw)
                bias_level = bias_data.get("bias_level") or "NEUTRAL"
        except Exception:
            pass

    market_pulse = {
        "overall_pc_ratio": overall_pc,
        "overall_sentiment": overall_sentiment,
        "call_premium_total": total_call,
        "put_premium_total": total_put,
        "call_premium_display": _format_premium(total_call),
        "put_premium_display": _format_premium(total_put),
        "total_premium_display": _format_premium(total_all),
        "bias_level": bias_level,
        "tickers_with_flow": len(flow_data),
    }

    # === 6. Compact headlines (latest 3) ===
    headlines_compact = []
    if redis:
        try:
            headlines_raw = await redis.get("market:news:latest")
            if headlines_raw:
                articles = json.loads(headlines_raw)
                for a in (articles if isinstance(articles, list) else articles.get("articles", []))[:3]:
                    headlines_compact.append({
                        "title": a.get("title", ""),
                        "source": a.get("source", ""),
                        "url": a.get("url", ""),
                    })
        except Exception:
            pass

    return {
        "position_flow": position_flow,
        "watchlist_unusual": watchlist_unusual,
        "sector_flow": sector_flow,
        "market_pulse": market_pulse,
        "headlines": headlines_compact,
        "flow_tickers_loaded": len(flow_data),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
```

**NOTE on headlines:** The headlines Redis key may be different from `market:news:latest`. CC should check what key `loadHeadlines()` in `app.js` reads from, or what key the news endpoint caches to. If the frontend calls `/api/market/news` directly, just have the radar return an empty `headlines` array and let the frontend continue fetching headlines separately — the UI will render them either way.

---

## Part 2 — Backend: Register Router

### File: `backend/main.py`

**Find** the flow_summary import (~line 629):
```python
from api.flow_summary import router as flow_summary_router
```

**Add immediately after:**
```python
from api.flow_radar import router as flow_radar_router
```

**Find** the flow_summary registration (~line 667):
```python
app.include_router(flow_summary_router, prefix="/api", tags=["flow-summary"])
```

**Add immediately after:**
```python
app.include_router(flow_radar_router, prefix="/api", tags=["flow-radar"])
```

Keep `flow_summary_router` — it's still called by the old Flow tab code and won't hurt. The new endpoint is at `GET /api/flow/radar`.

---

## Part 3 — Frontend: Replace HTML Structure

### File: `frontend/index.html`

**Find** the entire headlines-card block (~lines 113-136):
```html
<!-- Headlines / Sectors / Flow (column 2) -->
<div class="headlines-card" id="headlinesCard">
    <div class="headlines-tabs">
        <button class="headlines-tab active" data-tab="sectors">SECTORS</button>
        <button class="headlines-tab" data-tab="flow">FLOW</button>
        <button class="headlines-tab" data-tab="headlines">HEADLINES</button>
    </div>
    <div class="headlines-tab-content" id="sectorsTabContent">
        <div class="sector-heatmap" id="sectorHeatmap">
            <p class="empty-state">Loading sectors...</p>
        </div>
    </div>
    <div class="headlines-tab-content" id="flowTabContent" style="display:none;">
        <div class="flow-compact-list" id="flowCompactList">
            <p class="empty-state">No flow data yet</p>
        </div>
    </div>
    <div class="headlines-tab-content" id="headlinesTabContent" style="display:none;">
        <ul class="headlines-list" id="headlinesList">
            <li class="headlines-empty">Loading headlines...</li>
        </ul>
    </div>
</div>
```

**Replace with:**
```html
<!-- Intelligence Center (column 2) -->
<div class="intel-center" id="intelCenter">
    <!-- MARKET MAP: sector heatmap + pulse + headlines -->
    <div class="market-map-section">
        <div class="sector-heatmap" id="sectorHeatmap">
            <p class="empty-state">Loading sectors...</p>
        </div>
        <div class="market-pulse-strip" id="marketPulseStrip">
            <span class="pulse-regime" id="pulseRegime">--</span>
            <span class="pulse-separator">·</span>
            <span class="pulse-pc" id="pulsePcRatio">P/C --</span>
            <span class="pulse-separator">·</span>
            <span class="pulse-premium" id="pulsePremium">$--</span>
        </div>
        <div class="headlines-strip" id="headlinesStrip">
            <div class="headline-compact">Loading headlines...</div>
        </div>
    </div>
    <!-- FLOW RADAR: positions, unusual activity, sector rotation -->
    <div class="flow-radar-section" id="flowRadarSection">
        <div class="radar-header">
            <span class="radar-title">FLOW RADAR</span>
            <span class="radar-status" id="radarStatus">--</span>
        </div>
        <div class="radar-content" id="radarContent">
            <p class="empty-state">Waiting for flow data...</p>
        </div>
    </div>
</div>
```

---

## Part 4 — Frontend: CSS

### File: `frontend/styles.css`

**Replace** the `.headlines-card` rule (~line 253) and all the old tab styles with:

```css
/* ===== Intelligence Center (column 2) ===== */
.intel-center {
    grid-column: 2;
    background: var(--card-bg);
    border: 2px solid var(--border-color);
    border-radius: 10px;
    min-width: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    align-self: stretch;
}

.market-map-section {
    flex: 0 0 auto;
    padding: 10px 12px 0 12px;
}

/* Market pulse strip (one-line regime + P/C + premium) */
.market-pulse-strip {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 0;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.5px;
    color: var(--text-secondary);
    border-bottom: 1px solid var(--border-color);
}

.pulse-regime { text-transform: uppercase; }
.pulse-separator { opacity: 0.3; }

/* Headlines compact strip (3 lines, always visible) */
.headlines-strip {
    padding: 6px 0;
    border-bottom: 1px solid var(--border-color);
}

.headline-compact {
    font-size: 11px;
    line-height: 1.35;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    padding: 2px 0;
}

.headline-compact a {
    color: var(--text-primary);
    text-decoration: none;
}

.headline-compact a:hover {
    color: var(--accent-teal);
}

.headline-compact .hl-source {
    font-size: 9px;
    color: var(--text-secondary);
    margin-left: 6px;
}

/* Flow Radar section */
.flow-radar-section {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    padding: 0 12px 10px 12px;
}

.radar-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0 6px 0;
    flex-shrink: 0;
}

.radar-title {
    font-family: 'Orbit', sans-serif;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: var(--text-secondary);
}

.radar-status {
    font-size: 9px;
    color: var(--text-secondary);
    opacity: 0.6;
}

.radar-content {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: rgba(20, 184, 166, 0.3) transparent;
}

/* Radar sub-section headers */
.radar-sub-header {
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-secondary);
    padding: 8px 0 4px 0;
    opacity: 0.7;
}

.radar-sub-header:first-child {
    padding-top: 0;
}

/* Radar rows (used by position flow, unusual activity, sector rotation) */
.radar-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 0;
    font-size: 11px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.03);
    cursor: pointer;
    transition: background 0.15s;
}

.radar-row:hover {
    background: rgba(20, 184, 166, 0.05);
}

.radar-ticker {
    font-weight: 700;
    min-width: 48px;
    color: var(--text-primary);
}

.radar-alignment {
    font-size: 12px;
    min-width: 16px;
    text-align: center;
}

.radar-alignment.confirming { color: #4ade80; }
.radar-alignment.counter { color: #f87171; }
.radar-alignment.neutral { color: #78909c; }

.radar-detail {
    flex: 1;
    font-size: 10px;
    color: var(--text-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.radar-pc {
    font-size: 10px;
    min-width: 50px;
    text-align: right;
    color: var(--text-secondary);
}

.radar-premium {
    font-size: 10px;
    min-width: 44px;
    text-align: right;
    color: var(--text-secondary);
    opacity: 0.7;
}

/* Divergence badge */
.radar-div-badge {
    font-size: 8px;
    font-weight: 700;
    padding: 1px 4px;
    border-radius: 3px;
    background: rgba(251, 191, 36, 0.15);
    color: #fbbf24;
    border: 1px solid rgba(251, 191, 36, 0.3);
    letter-spacing: 0.5px;
}

/* Sector flow row */
.radar-sector-sentiment {
    font-size: 11px;
    min-width: 16px;
}

.radar-sector-sentiment.bullish { color: #4ade80; }
.radar-sector-sentiment.bearish { color: #f87171; }
.radar-sector-sentiment.neutral { color: #78909c; }

/* Sector heatmap flow dot overlay */
.sector-flow-dot {
    position: absolute;
    top: 4px;
    right: 4px;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    opacity: 0.85;
}

.sector-flow-dot.bullish { background: #4ade80; box-shadow: 0 0 4px rgba(74, 222, 128, 0.5); }
.sector-flow-dot.bearish { background: #f87171; box-shadow: 0 0 4px rgba(248, 113, 113, 0.5); }
.sector-flow-dot.neutral { background: #78909c; }
```

**IMPORTANT:** Keep all existing `.sector-heatmap`, `.sector-heatmap-cell`, `.sector-hm-*` styles intact — the heatmap itself is unchanged. Only the container around it changes.

Also keep the existing `.headlines-list`, `.headline-link`, `.headline-meta` styles — they're still used by the `loadHeadlines()` function even though the display method changes. Or if the headline rendering is fully replaced, the old styles can be removed.

**Update grid layout** — find the `.bias-section` grid definition (~line 210) and update column 2 if needed. The `headlines-card` class was used for `grid-column: 2`. Now `.intel-center` takes that slot:

```css
/* In any rule that referenced .headlines-card in the grid: */
/* Replace .headlines-card with .intel-center */
```

Search for all CSS rules that target `.headlines-card` and rename to `.intel-center` (or verify they're replaced by the new styles above).

---

## Part 5 — Frontend: JavaScript

### File: `frontend/app.js`

This is the largest change. Several functions need updating:

**5a. New function: `loadFlowRadar()`**

Add this function. It replaces the old `loadFlowSummary()`:

```javascript
async function loadFlowRadar() {
    try {
        const response = await fetch(`${API_URL}/flow/radar`);
        if (!response.ok) return;
        const data = await response.json();
        renderFlowRadar(data);
    } catch (error) {
        console.error('Flow radar load failed:', error);
    }
}
```

**5b. New function: `renderFlowRadar(data)`**

Replaces `renderFlowSummary()`:

```javascript
function renderFlowRadar(data) {
    // --- Market Pulse Strip ---
    const pulseRegime = document.getElementById('pulseRegime');
    const pulsePc = document.getElementById('pulsePcRatio');
    const pulsePremium = document.getElementById('pulsePremium');
    const mp = data.market_pulse || {};

    if (pulseRegime) {
        const bl = mp.bias_level || 'NEUTRAL';
        pulseRegime.textContent = bl;
        pulseRegime.style.color = bl.includes('URSA') ? '#f87171'
            : bl.includes('TORO') ? '#4ade80' : 'var(--text-secondary)';
    }
    if (pulsePc) {
        const pc = mp.overall_pc_ratio;
        pulsePc.textContent = pc != null ? `P/C ${pc.toFixed(2)}` : 'P/C --';
        if (pc != null) {
            pulsePc.style.color = pc < 0.7 ? '#4ade80' : pc > 1.3 ? '#f87171' : 'var(--text-secondary)';
        }
    }
    if (pulsePremium) {
        pulsePremium.textContent = mp.total_premium_display || '$--';
    }

    // --- Headlines Strip ---
    const hlStrip = document.getElementById('headlinesStrip');
    if (hlStrip && data.headlines && data.headlines.length > 0) {
        hlStrip.innerHTML = data.headlines.map(h =>
            `<div class="headline-compact">
                <a href="${h.url || '#'}" target="_blank" rel="noopener">${escapeHtml(h.title)}</a>
                ${h.source ? `<span class="hl-source">${escapeHtml(h.source)}</span>` : ''}
            </div>`
        ).join('');
    }
    // If no headlines from radar, fall back to existing loadHeadlines() which populates separately

    // --- Radar Status ---
    const radarStatus = document.getElementById('radarStatus');
    if (radarStatus) {
        const count = data.flow_tickers_loaded || 0;
        radarStatus.textContent = count > 0 ? `${count} tickers · live` : 'no flow data';
    }

    // --- Radar Content ---
    const radarContent = document.getElementById('radarContent');
    if (!radarContent) return;

    let html = '';

    // Section 1: Position Flow
    const pf = data.position_flow || [];
    if (pf.length > 0) {
        html += '<div class="radar-sub-header">YOUR POSITIONS</div>';
        pf.forEach(p => {
            const icon = p.alignment === 'CONFIRMING' ? '✓' : p.alignment === 'COUNTER' ? '⚠' : '○';
            const alignClass = p.alignment.toLowerCase();
            const detail = p.alignment === 'CONFIRMING'
                ? (p.strength === 'STRONG' ? 'Strong flow confirms' : 'Flow confirms')
                : p.alignment === 'COUNTER'
                ? (p.strength === 'STRONG' ? 'Strong flow disagrees' : 'Flow disagrees')
                : 'Flow neutral';
            html += `<div class="radar-row" data-ticker="${p.ticker}">
                <span class="radar-ticker">${p.ticker}</span>
                <span class="radar-alignment ${alignClass}">${icon}</span>
                <span class="radar-detail">${detail}</span>
                <span class="radar-pc">P/C ${p.pc_ratio != null ? p.pc_ratio.toFixed(2) : '--'}</span>
                <span class="radar-premium">${p.premium_display || ''}</span>
            </div>`;
        });
    }

    // Section 2: Unusual Watchlist Activity
    const wu = data.watchlist_unusual || [];
    if (wu.length > 0) {
        html += '<div class="radar-sub-header">UNUSUAL ACTIVITY</div>';
        wu.forEach(w => {
            const sentIcon = w.sentiment === 'BULLISH' ? '🐂' : w.sentiment === 'BEARISH' ? '🐻' : '→';
            const divBadge = w.divergence ? '<span class="radar-div-badge">DIV</span>' : '';
            const changePct = w.change_pct != null ? ` ${w.change_pct >= 0 ? '+' : ''}${w.change_pct.toFixed(1)}%` : '';
            html += `<div class="radar-row" data-ticker="${w.ticker}">
                <span class="radar-ticker">${w.ticker}</span>
                <span class="radar-alignment">${sentIcon}</span>
                <span class="radar-detail">${changePct} ${divBadge}</span>
                <span class="radar-pc">P/C ${w.pc_ratio != null ? w.pc_ratio.toFixed(2) : '--'}</span>
                <span class="radar-premium">${w.premium_display || ''}</span>
            </div>`;
        });
    }

    // Section 3: Sector Rotation
    const sf = data.sector_flow || [];
    if (sf.length > 0) {
        html += '<div class="radar-sub-header">SECTOR ROTATION</div>';
        sf.forEach(s => {
            const icon = s.sentiment === 'BULLISH' ? '🐂' : s.sentiment === 'BEARISH' ? '🐻' : '→';
            const sentClass = s.sentiment.toLowerCase();
            html += `<div class="radar-row">
                <span class="radar-ticker">${s.etf}</span>
                <span class="radar-sector-sentiment ${sentClass}">${icon}</span>
                <span class="radar-detail">${s.ticker_count} tickers</span>
                <span class="radar-pc">P/C ${s.avg_pc_ratio != null ? s.avg_pc_ratio.toFixed(2) : '--'}</span>
                <span class="radar-premium">${s.premium_display || ''}</span>
            </div>`;
        });
    }

    // Empty state
    if (!html) {
        html = '<p class="empty-state">No flow data yet — updates during market hours</p>';
    }

    radarContent.innerHTML = html;

    // Click handler: clicking a ticker row changes the chart
    radarContent.querySelectorAll('.radar-row[data-ticker]').forEach(row => {
        row.addEventListener('click', () => {
            const ticker = row.dataset.ticker;
            if (ticker) changeChartSymbol(ticker);
        });
    });
}
```

**5c. Sector heatmap flow dots**

In `renderSectorHeatmap()`, after the cell HTML is built but inside the forEach loop, add a flow dot to each sector cell. The flow data needs to be passed in.

Modify `loadSectorHeatmap()` to also fetch flow radar data and pass sector flow to the renderer:

```javascript
async function loadSectorHeatmap() {
    try {
        const [sectorRes, radarRes] = await Promise.all([
            fetch(`${API_URL}/sectors/heatmap`),
            fetch(`${API_URL}/flow/radar`).catch(() => null),
        ]);
        const sectorData = await sectorRes.json();
        const radarData = radarRes && radarRes.ok ? await radarRes.json() : null;
        
        // Build sector flow lookup: ETF -> sentiment
        const sectorFlowMap = {};
        if (radarData && radarData.sector_flow) {
            radarData.sector_flow.forEach(sf => {
                sectorFlowMap[sf.etf] = sf.sentiment;
            });
        }
        
        renderSectorHeatmap(sectorData.sectors, sectorData, sectorFlowMap);
        
        // Also render the rest of the radar
        if (radarData) renderFlowRadar(radarData);
    } catch (error) {
        console.error('Sector heatmap load failed:', error);
    }
}
```

Then in `renderSectorHeatmap()`, update the function signature to accept `sectorFlowMap` and add the dot inside each cell's HTML:

In the cell HTML template (after `${cellContent}`), add:
```javascript
const flowSentiment = (sectorFlowMap || {})[sector.etf];
const flowDotHtml = flowSentiment
    ? `<div class="sector-flow-dot ${flowSentiment.toLowerCase()}"></div>`
    : '';
```

And insert `${flowDotHtml}` inside the cell div (before the closing `</div>`).

**5d. Remove old tab switching code**

Find the `headlines-tab` click handler that switches between SECTORS/FLOW/HEADLINES tabs and **remove it**. The new layout has no tabs.

Also remove or repurpose the `loadFlowSummary()` and `renderFlowSummary()` functions — they're superseded by `loadFlowRadar()` and `renderFlowRadar()`.

**5e. Add 2-minute refresh**

In the initialization section, add a market-hours refresh for the flow radar:

```javascript
// Refresh flow radar every 2 minutes during market hours
setInterval(() => {
    const now = new Date();
    const et = new Date(now.toLocaleString('en-US', {timeZone: 'America/New_York'}));
    const h = et.getHours();
    const m = et.getMinutes();
    const day = et.getDay();
    if (day >= 1 && day <= 5 && (h > 9 || (h === 9 && m >= 30)) && h < 17) {
        loadFlowRadar();
    }
}, 120000);  // 2 minutes
```

**5f. Keep `loadHeadlines()` as fallback**

The existing `loadHeadlines()` function and its renderer should stay as a fallback. If the flow radar doesn't return headlines (Redis key mismatch or empty), `loadHeadlines()` still populates via its own endpoint. But instead of rendering to the old `headlinesList` UL, wire it to populate `headlinesStrip`:

Check if `loadHeadlines()` can be pointed at the `headlinesStrip` container. If it currently targets `headlinesList` by ID, update the ID reference. Or let both systems populate: radar provides compact headlines if available, `loadHeadlines()` fills in if radar headlines are empty.

---

## Part 6 — Cache Bust

### File: `frontend/index.html`

Bump CSS and JS version numbers.

---

## Build Order

| Step | File | What |
|------|------|------|
| 1 | `backend/api/flow_radar.py` | New file — radar endpoint |
| 2 | `backend/main.py` | Register flow_radar_router |
| 3 | `frontend/index.html` | Replace 3-tab HTML with 2-section stacked layout |
| 4 | `frontend/styles.css` | New intel-center styles, remove old tab styles |
| 5 | `frontend/app.js` | loadFlowRadar, renderFlowRadar, sector flow dots, remove old tab code, 2-min refresh |
| 6 | `frontend/index.html` | Cache bust |

---

## Verification Checklist

- [ ] `GET /api/flow/radar` returns valid JSON with all 5 sections (even if flow data is empty)
- [ ] Middle column shows heatmap at top (no tabs)
- [ ] Market pulse strip shows regime + P/C + premium (or "--" if no data)
- [ ] Headlines strip shows 3 compact headlines below the heatmap
- [ ] Flow Radar section scrollable below the market map
- [ ] Position Flow sub-section shows open positions with confirming/counter alignment (when UW data exists for those tickers)
- [ ] Unusual Activity sub-section shows watchlist tickers with extreme P/C or divergence
- [ ] Divergence items show yellow "DIV" badge
- [ ] Sector Rotation sub-section shows per-sector flow aggregation
- [ ] Clicking a radar row changes the chart to that ticker
- [ ] Sector heatmap cells show small colored flow dots (green=call-heavy, red=put-heavy)
- [ ] No old SECTORS/FLOW/HEADLINES tab buttons visible
- [ ] 2-minute auto-refresh during market hours
- [ ] Empty state graceful: "No flow data yet — updates during market hours"

---

## Known Limitations

1. **Flow data depends on UW Watcher posting during market hours.** Outside hours, Flow Radar will show empty position flow and unusual activity. Sector heatmap still works (yfinance data).
2. **Headlines fallback:** If the radar endpoint doesn't return headlines (Redis key mismatch), the `loadHeadlines()` fallback should still populate the strip. CC should verify which Redis key news articles are cached under.
3. **Sector flow aggregation is approximate.** We map watchlist tickers to sectors, then aggregate their UW flow. Tickers not on the watchlist won't be counted in sector totals. This is acceptable since the watchlist covers the tickers Nick actually trades.
4. **No flow velocity yet.** This build shows snapshots, not trends. Velocity ("accelerating/decelerating") requires comparing `flow_events` history, which is a Phase B enhancement.

---

## Commit

```
feat: intelligence center — Market Map + Flow Radar (middle column redesign)
```
