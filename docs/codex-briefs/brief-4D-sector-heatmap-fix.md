# Brief 4D — Sector Heatmap: Missing Sectors + Day/Week/Month + Daily RS Rankings

**Target:** Claude Code (VSCode)
**Depends on:** Polygon equities integration (`backend/integrations/polygon_equities.py`)
**Estimated scope:** Small-Medium — backend rewrite of one file + frontend column addition

---

## Problem

1. **5 of 11 sectors missing data** — XLC, XLP, XLU, XLRE, XLB all show 0% change, rank 99, no price. Root cause: the heatmap endpoint (`/sectors/heatmap`) reads from the enrichment cache (`watchlist:enriched`), which only contains sectors that have tickers in Nick's watchlist. Five sectors have no watchlist tickers so they never get enriched.

2. **No monthly performance** — Only `change_1d` and `change_1w` exist. Nick wants Day, Week, AND Month columns in the Sector Overview.

3. **RS rankings based on weekly, not daily** — The `strength_rank` field is ranked by weekly performance. Nick wants rankings based on **daily divergence vs SPY** (sector daily return minus SPY daily return).

## Solution

Rewrite `backend/api/sectors.py` to fetch sector data **directly from Polygon** instead of relying on the enrichment cache. This guarantees all 11 sectors always have data regardless of watchlist composition.

### Backend: Rewrite `backend/api/sectors.py`

**Data source:** Use `polygon_equities.get_bars()` to fetch ~25 daily bars for SPY + all 11 sector ETFs. From the bars, compute:

```
change_1d = (close[-1] / close[-2] - 1) * 100      # last bar vs previous
change_1w = (close[-1] / close[-6] - 1) * 100       # last bar vs 5 bars ago  
change_1m = (close[-1] / close[-22] - 1) * 100      # last bar vs ~21 bars ago
rs_daily = change_1d - spy_change_1d                 # daily divergence vs SPY
```

**Ranking:** Sort sectors by `rs_daily` descending. Rank 1 = strongest daily outperformance vs SPY.

**Caching:** Use Redis key `sector_heatmap:polygon` with 5-min TTL during market hours (9:30-4 ET), 4-hour TTL outside hours. This replaces the current cache at `sector_heatmap`.

**Fallback:** If Polygon fails for a ticker, try yfinance (`_fetch_sector_prices` from `scanners/sector_rs.py` already does this). If both fail, return the sector with null price and 0% changes.

**Implementation pattern:**

```python
from integrations.polygon_equities import get_bars

async def _fetch_sector_bars():
    """Fetch 25 daily bars for SPY + all 11 sector ETFs via Polygon."""
    tickers = ["SPY"] + list(SECTOR_WEIGHTS.keys())  # 12 tickers
    results = {}
    for ticker in tickers:
        bars = await get_bars(ticker, 1, "day")  # default 60-day lookback
        if bars:
            closes = [b["c"] for b in bars if b.get("c")]
            results[ticker] = closes
    return results
```

**Response shape** (add `change_1m` and `rs_daily` to each sector):

```json
{
  "sectors": [
    {
      "etf": "XLE",
      "name": "Energy",
      "weight": 0.034,
      "price": 57.85,
      "change_1d": 0.26,
      "change_1w": 2.72,
      "change_1m": -1.45,
      "rs_daily": -0.76,
      "trend": "up",
      "strength_rank": 3
    }
  ],
  "spy_change_1d": 1.02,
  "spy_change_1w": -2.15,
  "spy_change_1m": -4.30,
  "timestamp": "2026-03-16T..."
}
```

`strength_rank` is now based on `rs_daily` (daily divergence), not weekly return.

**Keep backward compat:** The existing fields (`change_1d`, `change_1w`, `trend`, `strength_rank`) stay in the same shape. We just ADD `change_1m`, `rs_daily`, `spy_change_1w`, `spy_change_1m`.

### Frontend: Update `renderSectorHeatmap()` in `frontend/app.js`

The heatmap cells currently show only daily change. Update to show Day / Week / Month in the tooltip AND in the cell if space allows.

**Find** the tooltip `title` attribute in `renderSectorHeatmap()` (around line ~6910):
```
title="${escapeHtml(sector.name)} (${sector.etf})\nDaily: ...\nWeekly: ...\nWeekly Trend: ..."
```

**Replace** with:
```
title="${escapeHtml(sector.name)} (${sector.etf})\nDay: ${change1d}%\nWeek: ${change1w}%\nMonth: ${change1m}%\nRS (daily): ${rsDailyStr}%\nSPY Weight: ${weightStr}%"
```

Also update the cell content to show the daily RS value as a small secondary line:
```html
<span class="sector-hm-change">+0.26%</span>
<span class="sector-hm-rs">RS: -0.76%</span>  <!-- NEW: small text showing daily divergence -->
```

### Also: Update `renderSectorRotationStrip()` (the bias section strip)

This function at ~line 2108 renders sector chips in the bias section. It currently reads from `sectorData` which comes from the enrichment pipeline. Update it to also call `/sectors/heatmap` if `sectorData` is empty or stale, so the rotation strip always shows all 11 sectors.

## Files to Modify

- `backend/api/sectors.py` — Rewrite `get_sector_heatmap()` to use Polygon bars
- `frontend/app.js` — Update `renderSectorHeatmap()` tooltip + cell content; update `renderSectorRotationStrip()` fallback

## Files for Reference (read-only)

- `backend/integrations/polygon_equities.py` — `get_bars()` function to use
- `backend/scanners/sector_rs.py` — existing RS computation (yfinance-based, keep as fallback)
- `frontend/app.js` lines ~6858-6950 — current heatmap rendering

## Verification

1. `GET /api/sectors/heatmap` returns all 11 sectors with non-null prices
2. Every sector has `change_1d`, `change_1w`, `change_1m` populated
3. `strength_rank` is ordered by `rs_daily` (daily divergence vs SPY), not weekly
4. XLC, XLP, XLU, XLRE, XLB — previously missing — now show real data
5. Heatmap UI shows all 11 sectors with color-coded daily performance
6. Hovering a sector shows Day/Week/Month in tooltip
