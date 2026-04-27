# CC Brief — P2 Sector Drill-Down Enrichment

**Date:** 2026-04-27
**Author:** Opus + Titans audit (via Nick)
**Status:** P2 — biggest trader-visible upgrade from Titans audit
**Scope:** backend enrichment + frontend columns + heatmap toggle + UW budget guardrail
**Estimated effort:** 2-3 days CC work

**Pre-deploy dependency:** P1 freshness indicators should ship FIRST. P2 modifies the same `app.js` panels that P1 instruments, and clean P1 verification gives us baseline timestamps to confirm new UW data is flowing live.

---

## Background — why this brief exists

Today's UW migration cutover put real-time UW data behind the sector heatmap's price/change values. But the **drill-down popup** (best/worst performers per sector) still shows only sector-relative percentage moves. The Titans audit (run today) flagged this as the biggest trader-visible win available post-cutover.

Per HELIOS in the audit: *"A trader looking at this in Agora wants to scan for: 'which stock in this sector has unusual flow + breaking out + IV is cheap?' — that's a 3-data-point answer with one glance. Current UI gives one of those (price relative)."*

This brief adds three new data columns to the constituent table (flow ratio, IV rank, dark pool badge), a "Flow / Price" toggle on the main heatmap, and the caching/budget guardrails AEGIS required as a non-negotiable rider.

Sources:
- Titans audit Pass 2: ATLAS A2, B2 + HELIOS H2, H5 + AEGIS AE2, AE5
- ATHENA prioritization: bundle as P2, single brief, single PR

---

## Scope summary

| # | Workstream | File(s) |
|---|---|---|
| **B1** | Add UW enrichment helpers (IV rank, DP volume, flow direction) | `backend/api/sectors.py` |
| **B2** | Update `/{sector_etf}/leaders` endpoint to return new fields | `backend/api/sectors.py` |
| **B3** | Replace DB-based `_get_flow_direction` with UW-direct call | `backend/api/sectors.py` |
| **B4** | Update `FACTOR_CONFIG.source` declarations (AE5 rider) | `backend/bias_engine/composite.py` |
| **B5** | Add UW budget tracker + 70% alarm (AE2 rider) | `backend/integrations/uw_api.py` + new file |
| **F1** | Render 3 new columns in sector drill-down popup | `frontend/app.js` + `frontend/styles.css` |
| **F2** | Add "Flow / Price" toggle on main sector heatmap | `frontend/app.js` + `frontend/styles.css` |

**13 logical edits across 5 files + 1 new file.**

---

## Pre-flight verification (CC must do FIRST)

Before applying any edits, verify the UW API helpers exist with these signatures:

```bash
grep -n "^async def get_iv_rank\|^async def get_darkpool_ticker\|^async def get_flow_per_expiry" backend/integrations/uw_api.py
```

Expected: each function should be defined. If any are missing, **PAUSE** and report — they'd need to be added before this brief can proceed. (They are referenced in the Titans audit as pre-existing, so this is a sanity check, not an expected gap.)

Also confirm the post-cleanup state:
```bash
grep -n "POLYGON_API_KEY\|polygon_options\|polygon_equities" backend/api/sectors.py
# Expected: zero matches (after cleanup commit eb3a250)
```

If any of these grep commands surface unexpected results, pause and report rather than improvising.

---

## Backend changes

### B1 — Add UW enrichment helpers

In `backend/api/sectors.py`, add three new helper functions after the existing `_get_flow_direction` function (around line 480 in the post-cleanup file):

**APPEND** these new functions:

```python
async def _get_uw_iv_rank(ticker: str) -> Optional[Dict]:
    """Fetch IV rank from UW API with 60s Redis cache.

    Returns: {"iv_rank": 45.2, "iv_percentile": 38.7, "tier": "low"|"mid"|"high"} or None
    """
    redis = await get_redis_client()
    cache_key = f"uw:iv_rank:{ticker}"

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    try:
        from integrations.uw_api import get_iv_rank
        data = await get_iv_rank(ticker)
        if not data:
            return None
        iv_rank_val = data.get("iv_rank")
        if iv_rank_val is None:
            return None
        # Tier classification
        if iv_rank_val >= 70:
            tier = "high"
        elif iv_rank_val >= 30:
            tier = "mid"
        else:
            tier = "low"
        result = {
            "iv_rank": round(float(iv_rank_val), 1),
            "iv_percentile": round(float(data.get("iv_percentile", 0)), 1),
            "tier": tier,
        }
        if redis:
            try:
                await redis.set(cache_key, json.dumps(result), ex=60)
            except Exception:
                pass
        return result
    except Exception as e:
        logger.debug("UW IV rank failed for %s: %s", ticker, e)
        return None


async def _get_uw_darkpool_volume(ticker: str) -> Optional[Dict]:
    """Fetch dark pool volume from UW API with 60s Redis cache.

    Returns: {"dp_volume_24h": 1234567, "has_recent_prints": true, "last_print_minutes_ago": 12} or None
    has_recent_prints = true if any DP prints in last 30 minutes
    """
    redis = await get_redis_client()
    cache_key = f"uw:darkpool:{ticker}"

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    try:
        from integrations.uw_api import get_darkpool_ticker
        data = await get_darkpool_ticker(ticker)
        if not data:
            return None

        # UW returns a list of recent DP prints; aggregate
        prints = data if isinstance(data, list) else data.get("prints", [])
        if not prints:
            return {"dp_volume_24h": 0, "has_recent_prints": False, "last_print_minutes_ago": None}

        total_volume = sum(p.get("size", 0) or 0 for p in prints)
        # Find most recent print
        from datetime import datetime as dt_cls, timezone as tz_cls
        now = dt_cls.now(tz_cls.utc)
        most_recent = None
        for p in prints:
            ts = p.get("executed_at") or p.get("timestamp")
            if ts:
                try:
                    print_time = dt_cls.fromisoformat(ts.replace("Z", "+00:00"))
                    age_min = (now - print_time).total_seconds() / 60.0
                    if most_recent is None or age_min < most_recent:
                        most_recent = age_min
                except Exception:
                    continue

        result = {
            "dp_volume_24h": int(total_volume),
            "has_recent_prints": most_recent is not None and most_recent <= 30,
            "last_print_minutes_ago": round(most_recent, 1) if most_recent is not None else None,
        }
        if redis:
            try:
                await redis.set(cache_key, json.dumps(result), ex=60)
            except Exception:
                pass
        return result
    except Exception as e:
        logger.debug("UW darkpool failed for %s: %s", ticker, e)
        return None


async def _get_uw_flow_direction(ticker: str) -> Dict:
    """Fetch flow direction from UW API directly (replaces DB-based version).

    Returns: {"direction": "bullish"|"bearish"|"neutral", "call_pct": 0.65, "total_premium": 12345600}
    """
    redis = await get_redis_client()
    cache_key = f"uw:flow_direction:{ticker}"

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    try:
        from integrations.uw_api import get_flow_per_expiry
        data = await get_flow_per_expiry(ticker)
        if not data:
            return {"direction": "neutral", "call_pct": 0.5, "total_premium": 0}

        # Aggregate across expiries
        total_call_premium = 0
        total_put_premium = 0
        for expiry_data in (data if isinstance(data, list) else data.get("expiries", [])):
            total_call_premium += float(expiry_data.get("call_premium", 0) or 0)
            total_put_premium += float(expiry_data.get("put_premium", 0) or 0)

        total = total_call_premium + total_put_premium
        if total == 0:
            return {"direction": "neutral", "call_pct": 0.5, "total_premium": 0}

        call_pct = total_call_premium / total
        if call_pct > 0.6:
            direction = "bullish"
        elif call_pct < 0.4:
            direction = "bearish"
        else:
            direction = "neutral"

        result = {
            "direction": direction,
            "call_pct": round(call_pct, 3),
            "total_premium": int(total),
        }
        if redis:
            try:
                await redis.set(cache_key, json.dumps(result), ex=30)
            except Exception:
                pass
        return result
    except Exception as e:
        logger.debug("UW flow direction failed for %s: %s", ticker, e)
        return {"direction": "neutral", "call_pct": 0.5, "total_premium": 0}
```

### B2 — Update `/{sector_etf}/leaders` endpoint

In `backend/api/sectors.py`, find the existing `get_sector_leaders` function. Replace its constituent loop body to fetch and include the new fields.

**FIND** (the constituent loop inside `get_sector_leaders`, in the post-cleanup version):
```python
    constituents = []
    for r in rows:
        ticker = r["ticker"]
        snap = snapshot.get(ticker, {})
        price = snap.get("price", 0)
        day_change_pct = snap.get("day_change_pct", 0)
        sector_relative_pct = round(day_change_pct - sector_day_change, 2)

        entry = {
            "ticker": ticker,
            "price": price,
            "day_change_pct": day_change_pct,
            "sector_relative_pct": sector_relative_pct,
        }

        if not fast:
            entry["company_name"] = r["company_name"]
            entry["market_cap"] = r["market_cap"]

            vol = snap.get("volume", 0)
            avg_vol = r["avg_volume_20d"]
            if avg_vol and avg_vol > 0:
                entry["volume_ratio"] = round(vol / avg_vol, 1)
            elif snap.get("prev_volume") and snap["prev_volume"] > 0:
                entry["volume_ratio"] = round(vol / snap["prev_volume"], 1)
            else:
                entry["volume_ratio"] = None

            entry["rsi_14"] = await _get_rsi_for_ticker(ticker, redis)
            entry["flow_direction"] = await _get_flow_direction(ticker)
            entry["week_change_pct"] = None
            entry["month_change_pct"] = None

        constituents.append(entry)
```

**REPLACE WITH:**
```python
    constituents = []
    for r in rows:
        ticker = r["ticker"]
        snap = snapshot.get(ticker, {})
        price = snap.get("price", 0)
        day_change_pct = snap.get("day_change_pct", 0)
        sector_relative_pct = round(day_change_pct - sector_day_change, 2)

        entry = {
            "ticker": ticker,
            "price": price,
            "day_change_pct": day_change_pct,
            "sector_relative_pct": sector_relative_pct,
        }

        if not fast:
            entry["company_name"] = r["company_name"]
            entry["market_cap"] = r["market_cap"]

            vol = snap.get("volume", 0)
            avg_vol = r["avg_volume_20d"]
            if avg_vol and avg_vol > 0:
                entry["volume_ratio"] = round(vol / avg_vol, 1)
            elif snap.get("prev_volume") and snap["prev_volume"] > 0:
                entry["volume_ratio"] = round(vol / snap["prev_volume"], 1)
            else:
                entry["volume_ratio"] = None

            entry["rsi_14"] = await _get_rsi_for_ticker(ticker, redis)

            # P2 — UW enrichment fields (parallelized for performance)
            iv_data, dp_data, flow_data = await asyncio.gather(
                _get_uw_iv_rank(ticker),
                _get_uw_darkpool_volume(ticker),
                _get_uw_flow_direction(ticker),
                return_exceptions=True,
            )

            # Handle any gather exceptions gracefully
            entry["iv_rank"] = iv_data if isinstance(iv_data, dict) else None
            entry["darkpool"] = dp_data if isinstance(dp_data, dict) else None
            entry["flow"] = flow_data if isinstance(flow_data, dict) else {"direction": "neutral", "call_pct": 0.5, "total_premium": 0}

            # Keep legacy field for backward compat with frontend that hasn't migrated yet
            entry["flow_direction"] = entry["flow"]["direction"]

            entry["week_change_pct"] = None
            entry["month_change_pct"] = None

        constituents.append(entry)
```

### B3 — Add staleness timestamp to leaders response

**FIND** (in `get_sector_leaders`, the response construction):
```python
    response = {
        "sector_etf": sector_etf,
        "sector_day_change_pct": sector_day_change,
        "constituents": constituents,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
```

**REPLACE WITH:**
```python
    response = {
        "sector_etf": sector_etf,
        "sector_day_change_pct": sector_day_change,
        "constituents": constituents,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "timestamp": datetime.now(timezone.utc).isoformat(),  # P1 freshness indicator hook
        "enrichment_window": "Today's flow + 24h DP volume",  # User-facing label for new fields
    }
```

### B4 — Update `FACTOR_CONFIG.source` declarations (AE5 rider)

In `backend/bias_engine/composite.py`, find the `FACTOR_CONFIG` dictionary. Update the `source` field for any factor whose actual data source has changed since this dict was last touched.

CC: search for `FACTOR_CONFIG = {` in `composite.py`. For each factor entry, verify the `source` field matches the actual scorer's data source as of post-cutover state. Specifically:

- Factors using `uw_api.get_snapshot` or other UW endpoints → `"source": "uw_api"`
- Factors using yfinance directly → `"source": "yfinance"`
- Factors using FRED → `"source": "fred"` or `"source": "fred_cache"`
- TradingView webhook factors → `"source": "tradingview"`
- NYSE proxy/breadth → `"source": "nyse_proxy"`
- Manual entry (Savita) → `"source": "manual"`

**Common likely-stale entries to check first:**
- `gex` (was Polygon → now uw_api)
- `iv_regime` (was yfinance options chain → still yfinance until P3, but verify)
- Any factor that mentions Polygon in its description

**Don't speculate** — only update entries where you can verify the actual data source by reading the corresponding `bias_filters/*.py` file. If unclear, leave the entry as-is and note it in the commit message.

### B5 — UW budget tracker + 70% alarm (AE2 rider)

Create new file `backend/monitoring/uw_budget.py`:

```python
"""
UW API budget tracker.
Tracks daily UW call count + per-endpoint counts in Redis.
Pages Discord webhook when daily total exceeds 70% of 20K quota.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Dict

from database.redis_client import get_redis_client

logger = logging.getLogger(__name__)

DAILY_QUOTA = int(os.getenv("UW_DAILY_QUOTA", "20000"))
ALARM_THRESHOLD_PCT = 0.70
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_OPERATIONS") or os.getenv("DISCORD_WEBHOOK_SIGNALS") or ""


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


async def increment_uw_call(endpoint: str) -> None:
    """Record a UW API call. Increments daily total + per-endpoint count.

    Fires Discord alarm if daily total crosses 70% threshold (once per day).
    """
    redis = await get_redis_client()
    if not redis:
        return

    today = _today_key()
    daily_key = f"uw:budget:daily:{today}"
    endpoint_key = f"uw:budget:endpoint:{today}:{endpoint}"
    alarm_key = f"uw:budget:alarm_fired:{today}"

    try:
        # Increment counters with 48h TTL (auto-cleanup old days)
        new_total = await redis.incr(daily_key)
        await redis.expire(daily_key, 172800)
        await redis.incr(endpoint_key)
        await redis.expire(endpoint_key, 172800)

        # Check alarm threshold
        if new_total >= int(DAILY_QUOTA * ALARM_THRESHOLD_PCT):
            already_fired = await redis.get(alarm_key)
            if not already_fired:
                await redis.setex(alarm_key, 86400, "1")
                await _fire_alarm(new_total, endpoint)
    except Exception as e:
        logger.debug("UW budget increment failed: %s", e)


async def _fire_alarm(current_total: int, latest_endpoint: str) -> None:
    """POST a warning to Discord when budget threshold is crossed."""
    if not DISCORD_WEBHOOK:
        logger.warning("UW budget at %d/%d (%.0f%%) — no Discord webhook configured", current_total, DAILY_QUOTA, current_total / DAILY_QUOTA * 100)
        return
    try:
        import urllib.request
        import json as _json
        payload = _json.dumps({
            "content": f"⚠️ **UW API budget alarm** — {current_total:,}/{DAILY_QUOTA:,} calls used today ({current_total / DAILY_QUOTA * 100:.0f}%). Latest endpoint: `{latest_endpoint}`. Per-endpoint breakdown: `/api/monitoring/uw-budget`."
        }).encode()
        req = urllib.request.Request(
            DISCORD_WEBHOOK,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
        logger.info("UW budget alarm fired at %d calls", current_total)
    except Exception as e:
        logger.warning("Failed to fire UW budget alarm: %s", e)


async def get_budget_status() -> Dict:
    """Return current daily budget usage for monitoring endpoint."""
    redis = await get_redis_client()
    if not redis:
        return {"status": "redis_unavailable"}

    today = _today_key()
    try:
        daily_total = int(await redis.get(f"uw:budget:daily:{today}") or 0)

        # Get per-endpoint counts
        keys_pattern = f"uw:budget:endpoint:{today}:*"
        endpoint_counts = {}
        async for key in redis.scan_iter(match=keys_pattern):
            key_str = key.decode() if isinstance(key, bytes) else key
            endpoint_name = key_str.rsplit(":", 1)[-1]
            count = int(await redis.get(key) or 0)
            endpoint_counts[endpoint_name] = count

        return {
            "date": today,
            "daily_total": daily_total,
            "daily_quota": DAILY_QUOTA,
            "pct_used": round(daily_total / DAILY_QUOTA * 100, 1),
            "alarm_threshold_pct": int(ALARM_THRESHOLD_PCT * 100),
            "alarm_fired_today": bool(await redis.get(f"uw:budget:alarm_fired:{today}")),
            "endpoints": dict(sorted(endpoint_counts.items(), key=lambda x: -x[1])),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
```

Wire into `backend/integrations/uw_api.py` — find the central HTTP request function (likely a `_make_request` or similar wrapper that all endpoint helpers call). Add:

```python
# At the top of the request wrapper, AFTER request validation but BEFORE the actual HTTP call:
try:
    from monitoring.uw_budget import increment_uw_call
    await increment_uw_call(endpoint_path)  # endpoint_path = the path being requested, e.g. "/api/stock/AAPL/snapshot"
except Exception:
    pass  # Budget tracking failures must NEVER block a real UW call
```

CC: if `uw_api.py` doesn't have a single central wrapper, add this call to each public helper function (get_snapshot, get_bars, get_iv_rank, etc.) at the top before any network I/O.

Wire the monitoring endpoint into `backend/main.py` next to the other monitoring routes (search for `@app.get("/api/monitoring/factor-staleness")`):

```python
@app.get("/api/monitoring/uw-budget")
async def uw_budget_endpoint():
    """Check UW API budget usage for the current day."""
    from monitoring.uw_budget import get_budget_status
    return await get_budget_status()
```

---

## Frontend changes

### F1 — Render 3 new columns in sector drill-down popup

CC: locate the render function for the sector drill-down popup. Likely candidates: `renderSectorDrillDown`, `renderSectorLeaders`, `renderSectorPopup`, or similar. Search `frontend/app.js` for references to `/leaders` or `sector_relative_pct` (the existing field) to find the right function.

Once located, the constituent table currently renders rows with `ticker`, `price`, `day_change_pct`, `sector_relative_pct`, etc. Add three new column cells per row.

**Pattern (apply within the existing row-construction loop):**

```javascript
// Existing row HTML construction continues unchanged for ticker/price/day-change cells

// NEW: Flow ratio cell
const flow = row.flow || {direction: "neutral", call_pct: 0.5};
const flowPct = Math.round(flow.call_pct * 100);
const flowColor = flow.direction === "bullish" ? "#22c55e" : flow.direction === "bearish" ? "#ef4444" : "#888";
const flowCell = `<td class="constituent-flow" style="color: ${flowColor}; font-variant-numeric: tabular-nums;" title="Call premium: ${flowPct}% / Put premium: ${100-flowPct}%">${flowPct}%</td>`;

// NEW: IV rank cell
const ivData = row.iv_rank;
let ivCell;
if (ivData && ivData.iv_rank !== null && ivData.iv_rank !== undefined) {
  const ivClass = ivData.tier === "high" ? "iv-high" : ivData.tier === "low" ? "iv-low" : "iv-mid";
  ivCell = `<td class="constituent-iv"><span class="iv-pill ${ivClass}" title="IV percentile: ${ivData.iv_percentile || '—'}">${Math.round(ivData.iv_rank)}</span></td>`;
} else {
  ivCell = `<td class="constituent-iv"><span class="iv-pill iv-na">—</span></td>`;
}

// NEW: Dark pool badge cell
const dp = row.darkpool;
let dpCell;
if (dp && dp.has_recent_prints) {
  const dpVol = (dp.dp_volume_24h / 1_000_000).toFixed(1);
  const ageMin = dp.last_print_minutes_ago !== null ? `${Math.round(dp.last_print_minutes_ago)}m` : "?";
  dpCell = `<td class="constituent-dp"><span class="dp-badge dp-active" title="Last DP print ${ageMin} ago / 24h DP vol: ${dpVol}M">DP</span></td>`;
} else {
  dpCell = `<td class="constituent-dp"></td>`;
}
```

**Add the new cells to the row HTML in this order (after `sector_relative_pct`, before `volume_ratio`):** `flowCell`, `ivCell`, `dpCell`.

**Update the table header row** to add the three new column headers:
```html
<th title="Net options call% (today)">Flow</th>
<th title="Implied volatility rank (0-100)">IV</th>
<th title="Recent dark pool print activity">DP</th>
```

### F2 — "Flow / Price" toggle on main sector heatmap

Locate the sector heatmap render function (likely `renderSectorHeatmap` or similar — search for `/api/sectors/heatmap` in `app.js`).

Add a toggle button above the heatmap UI:
```html
<div class="heatmap-mode-toggle">
  <button id="heatmap-mode-price" class="heatmap-toggle active">Price</button>
  <button id="heatmap-mode-flow" class="heatmap-toggle">Flow</button>
  <span class="heatmap-mode-subtitle">Today's flow</span>
</div>
```

Wire up click handlers:
```javascript
let heatmapMode = "price";  // "price" | "flow"

document.getElementById("heatmap-mode-price").addEventListener("click", () => {
  heatmapMode = "price";
  document.getElementById("heatmap-mode-price").classList.add("active");
  document.getElementById("heatmap-mode-flow").classList.remove("active");
  renderSectorHeatmap();  // re-render with new mode
});

document.getElementById("heatmap-mode-flow").addEventListener("click", () => {
  heatmapMode = "flow";
  document.getElementById("heatmap-mode-flow").classList.add("active");
  document.getElementById("heatmap-mode-price").classList.remove("active");
  renderSectorHeatmap();
});
```

In the heatmap cell rendering, color cells based on mode:
- `mode === "price"` → existing logic, color by `change_1d`
- `mode === "flow"` → fetch flow data per ETF (call `_get_uw_flow_direction(etf)` via a new endpoint OR include `flow` field in the heatmap response)

**Backend addendum for F2:** add `flow` field to the `/api/sectors/heatmap` response. In `get_sector_heatmap`, after building `sectors_data`, batch-fetch flow per ETF in parallel:

```python
# Inside get_sector_heatmap, after sectors_data is built but before the response is assembled:
flow_results = await asyncio.gather(
    *[_get_uw_flow_direction(s["etf"]) for s in sectors_data],
    return_exceptions=True,
)
for sector_dict, flow_data in zip(sectors_data, flow_results):
    if isinstance(flow_data, dict):
        sector_dict["flow"] = flow_data
    else:
        sector_dict["flow"] = {"direction": "neutral", "call_pct": 0.5}
```

### F3 — CSS additions

In `frontend/styles.css`, append:

```css
/* === P2 Sector Drill-Down Enrichment === */

/* Flow column */
.constituent-flow {
  text-align: right;
  padding: 2px 6px;
}

/* IV rank pill */
.iv-pill {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.iv-pill.iv-high { background: #ef4444; color: white; }
.iv-pill.iv-mid { background: #f59e0b; color: white; }
.iv-pill.iv-low { background: #22c55e; color: white; }
.iv-pill.iv-na { background: #444; color: #888; }

/* Dark pool badge */
.dp-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: bold;
}
.dp-badge.dp-active {
  background: #8b5cf6;
  color: white;
  cursor: help;
}

/* Heatmap mode toggle */
.heatmap-mode-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.heatmap-toggle {
  padding: 4px 12px;
  border: 1px solid #333;
  background: #1a1a1a;
  color: #888;
  cursor: pointer;
  font-size: 12px;
  border-radius: 3px;
}
.heatmap-toggle.active {
  background: #2a2a2a;
  color: #fff;
  border-color: #555;
}
.heatmap-toggle:hover:not(.active) {
  background: #222;
  color: #aaa;
}
.heatmap-mode-subtitle {
  font-size: 10px;
  color: #666;
  margin-left: auto;
  font-style: italic;
}
```

---

## Verification

After deploy:

### 1. Backend: leaders endpoint returns new fields

```bash
curl -s -H "X-API-Key: $PIVOT_API_KEY" \
  "https://pandoras-box-production.up.railway.app/api/sectors/XLK/leaders" | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)
constituents = d['constituents']
sample = constituents[0] if constituents else {}
checks = {
    'has_iv_rank': 'iv_rank' in sample,
    'has_darkpool': 'darkpool' in sample,
    'has_flow': 'flow' in sample and 'direction' in sample.get('flow', {}),
    'flow_legacy_compat': 'flow_direction' in sample,
    'has_timestamp': 'timestamp' in d,
    'has_enrichment_window': 'enrichment_window' in d,
}
for k, v in checks.items():
    print(f'  {\"✓\" if v else \"✗\"} {k}')
print(f'PASS' if all(checks.values()) else 'FAIL')
"
```
**Expected:** all 6 checks PASS.

### 2. Backend: heatmap response includes flow field per sector

```bash
curl -s -H "X-API-Key: $PIVOT_API_KEY" \
  "https://pandoras-box-production.up.railway.app/api/sectors/heatmap" | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)
sectors = d['sectors']
with_flow = [s for s in sectors if s.get('flow') and 'direction' in s['flow']]
print(f'Sectors with flow: {len(with_flow)}/11')
print('PASS' if len(with_flow) >= 9 else 'FAIL')
"
```
**Expected:** ≥9/11 sectors with flow data (some thinly-traded sectors may lack data).

### 3. Backend: budget tracker is recording

```bash
curl -s -H "X-API-Key: $PIVOT_API_KEY" \
  "https://pandoras-box-production.up.railway.app/api/monitoring/uw-budget" | \
  python3 -m json.tool
```
**Expected:** returns JSON with `daily_total > 0`, `endpoints` dict with at least one entry.

### 4. Frontend: drill-down popup shows new columns

Open Agora, click any sector ETF on the heatmap. The drill-down popup should show three new column headers: Flow, IV, DP. Each constituent row should show:
- Flow: percentage in green/red/gray
- IV: colored pill with number (or "—" if unavailable)
- DP: purple "DP" badge if recent prints, blank otherwise

### 5. Frontend: heatmap toggle works

Click the "Flow" toggle button above the heatmap. Cells should re-color based on flow direction (green=bullish, red=bearish, gray=neutral) instead of % change. Subtitle should read "Today's flow." Click "Price" to toggle back.

### 6. Cache TTLs reasonable

After the page loads once, immediately reload. Network tab should show the leaders endpoint completing in <500ms (cached) for the second hit. Wait 90 seconds, reload again — should refetch fresh data (cache expired).

### 7. Logs clean

Tail Railway logs for 60s after deploy. Look for:
- No `ImportError` or `ModuleNotFoundError`
- No `NameError` related to new helper functions
- May see `UW IV rank failed for X: ...` debug-level messages — these are EXPECTED for some thin tickers and are not errors

### 8. Budget alarm doesn't fire prematurely

After deploy, `/api/monitoring/uw-budget` should show `alarm_fired_today: false` unless legitimate volume crosses 70% of 20K. Manually verify daily call count is reasonable (~5-10K range during active market hours, much less off-hours).

---

## Rollback plan

If anything goes wrong:
```bash
cd C:\trading-hub
git revert HEAD
git push origin main
```

The brief is mostly additive (new endpoints, new fields) plus one frontend toggle. Rollback is safe — restores pre-P2 state with no data integrity concerns. The budget tracker's Redis keys auto-expire in 48h.

---

## Out of scope (do NOT touch)

- **P1 freshness indicators** — separate brief, must ship first
- **P3 backend data source unification** — separate workstream (yfinance → UW for non-critical paths)
- **P4 enrichments** (watchlist B3, Open Positions B4, news B5, insider B6, calendar B7) — separate briefs
- **Pythia v2.5** — separate workstream
- **Real-time tape widget** (HELIOS H4) — deferred indefinitely until UW budget headroom is verified

---

## Commit message

```
feat(sectors,frontend): P2 sector drill-down enrichment

Brings UW flow + IV rank + dark pool data into the panels traders look
at most. Adds a Flow/Price toggle on the main heatmap so traders can
see institutional flow direction at a glance instead of just % change.

Backend:
- New helpers in api/sectors.py: _get_uw_iv_rank, _get_uw_darkpool_volume,
  _get_uw_flow_direction (with Redis caching, 30-60s TTLs)
- /api/sectors/{etf}/leaders endpoint now returns iv_rank, darkpool,
  flow fields per constituent (legacy flow_direction kept for compat)
- /api/sectors/heatmap response includes flow field per sector for the
  Flow toggle
- New module monitoring/uw_budget.py + /api/monitoring/uw-budget endpoint
  tracks per-day UW call count, fires Discord alarm at 70% of daily quota
- Increment hook wired into uw_api.py request wrapper
- composite.py FACTOR_CONFIG.source declarations updated to match
  post-cutover reality (AE5 rider)

Frontend:
- 3 new columns in sector drill-down popup (Flow %, IV pill, DP badge)
- Heatmap "Flow / Price" toggle with subtitle clarifying aggregation window
- New CSS for IV pills, DP badges, mode toggle

Source: Titans audit 2026-04-27 (ATLAS A2/B2, HELIOS H2/H5, AEGIS AE2/AE5).
Caching strategy meets AE2 budget rider — projected ≤30% increase in daily
UW call volume during active market hours.
```

---

## Session checklist for CC

1. `cd C:\trading-hub && git pull origin main`
2. **Read this brief in full.** Note: P1 freshness indicators should already be shipped — verify by checking the most recent commits before starting P2.
3. **Run pre-flight verification** from the section near the top. PAUSE if any UW helper is missing.
4. Apply Backend B1 → B5 in order.
5. Apply Frontend F1 → F3 in order.
6. Run syntax checks:
   - `python -m py_compile backend/api/sectors.py backend/main.py backend/monitoring/uw_budget.py backend/bias_engine/composite.py`
   - `node -c frontend/app.js`
7. Commit with the message above.
8. `git push origin main`
9. Wait ~90s for Railway deploy.
10. Run all 8 verification checks.
11. **Watch UW budget for the first hour after deploy** — if `daily_total` is climbing faster than expected (more than ~50 calls/min during market hours), bump cache TTLs from 30/60s to 60/120s and redeploy. Record the actual rate observed in commit message of any TTL adjustment.
12. If all PASS, post: "P2 enrichment complete. Sector drill-downs now show flow/IV/DP. Heatmap Flow/Price toggle live. UW budget tracker active. [Note any TTL adjustments made.]"
13. **Surface any unexpected gaps** — if the UW helpers don't exist or have different signatures than assumed, if FACTOR_CONFIG entries don't match actual sources, if frontend render functions can't be cleanly located — report rather than improvise.
