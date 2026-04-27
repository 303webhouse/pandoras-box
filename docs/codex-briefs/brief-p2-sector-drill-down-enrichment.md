# Brief — P2: Sector Drill-Down Enrichment + Heatmap Flow Toggle + AE2/AE5

**Status:** Ready for CC
**Source:** Today's Titans audit (P2 priority bundle), POST-CUTOVER-TODO.md
**Estimated effort:** 2–3 sessions (backend → frontend → verify)
**Dependencies:** P1 (freshness indicators) should land first if running in parallel — minor app.js merge risk otherwise

---

## Intent

After the UW migration cutover today, the sector drill-down popup and heatmap show only basic price/RSI/volume data despite UW now exposing rich flow, IV, and dark pool intel for every ticker. P2 surfaces three new high-value columns in the drill-down table (Flow %, IV rank pill, DP badge) and adds a Flow/Price toggle to the heatmap so cells can be colored by options-flow direction instead of price change. Bundles two cleanup items (AE2 multi-threshold budget tracker, AE5 FACTOR_CONFIG description fix) plus polygon constant removal.

**Trader-visible win:** When SPY is flat but XLK has aggressive bullish flow with elevated IV and a fresh DP buy, the heatmap and drill-down should TELL Nick that immediately — not require a separate ticker lookup.

---

## Pre-flight checks

Run these BEFORE making any edits. If any fail, STOP and report back.

```bash
cd /c/trading-hub
git status                                    # Should be clean on main
git pull --rebase                             # Pull any P1 changes first
ls backend/api/sectors.py                     # Must exist (post-cutover state)
ls backend/integrations/uw_api.py             # Must exist
ls backend/integrations/uw_api_cache.py       # Must exist
ls backend/bias_engine/composite.py           # Must exist
grep -n "get_flow_per_expiry\|get_iv_rank\|get_darkpool_ticker" backend/integrations/uw_api.py
# All three should appear — they're the UW endpoints we'll call
```

If `git status` is dirty, stash first: `git stash`. If grep returns nothing, abort and notify Nick — uw_api.py was tampered with.

---

## Phase A — Backend: enrich sector leaders endpoint

**File:** `backend/api/sectors.py`

### A.1 — Replace `_get_flow_direction` with richer `_get_flow_metrics`

Current function returns a 3-state string. We want both the string AND the call-premium percentage so the frontend can render an actual number.

**Find:**

```python
async def _get_flow_direction(ticker: str) -> str:
    """Derive flow direction from flow_events table (last 24h)."""
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT
                       COALESCE(SUM(CASE WHEN contract_type = 'call' THEN premium ELSE 0 END), 0) AS call_premium,
                       COALESCE(SUM(CASE WHEN contract_type = 'put' THEN premium ELSE 0 END), 0) AS put_premium
                   FROM flow_events
                   WHERE ticker = $1 AND created_at > NOW() - INTERVAL '24 hours'""",
                ticker,
            )
            if not row:
                return "neutral"
            total = (row["call_premium"] or 0) + (row["put_premium"] or 0)
            if total == 0:
                return "neutral"
            call_pct = (row["call_premium"] or 0) / total
            if call_pct > 0.6:
                return "bullish"
            elif call_pct < 0.4:
                return "bearish"
            return "neutral"
    except Exception:
        return "neutral"
```

**Replace with:**

```python
async def _get_flow_metrics(ticker: str) -> Dict[str, Any]:
    """Derive flow metrics from flow_events table (last 24h).

    Returns dict with:
        direction: 'bullish' / 'bearish' / 'neutral'
        call_pct: float 0..1 (call premium share of total)
        total_premium: dollar amount across both sides
    """
    default = {"direction": "neutral", "call_pct": None, "total_premium": 0.0}
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT
                       COALESCE(SUM(CASE WHEN contract_type = 'call' THEN premium ELSE 0 END), 0) AS call_premium,
                       COALESCE(SUM(CASE WHEN contract_type = 'put' THEN premium ELSE 0 END), 0) AS put_premium
                   FROM flow_events
                   WHERE ticker = $1 AND created_at > NOW() - INTERVAL '24 hours'""",
                ticker,
            )
            if not row:
                return default
            call_prem = float(row["call_premium"] or 0)
            put_prem = float(row["put_premium"] or 0)
            total = call_prem + put_prem
            if total == 0:
                return default
            call_pct = call_prem / total
            if call_pct > 0.6:
                direction = "bullish"
            elif call_pct < 0.4:
                direction = "bearish"
            else:
                direction = "neutral"
            return {
                "direction": direction,
                "call_pct": round(call_pct, 3),
                "total_premium": round(total, 2),
            }
    except Exception:
        return default


# Backward-compat shim — old callers (heatmap aggregation) use the simple string form.
async def _get_flow_direction(ticker: str) -> str:
    metrics = await _get_flow_metrics(ticker)
    return metrics["direction"]
```

### A.2 — Add IV rank helper

**Add this new function** immediately after `_get_flow_metrics` (and before any `@router.get` decorator):

```python
async def _get_iv_rank_for_ticker(ticker: str) -> Optional[Dict[str, Any]]:
    """Fetch IV rank from UW. Returns dict with 'rank' (0-100) and 'tier' (low/mid/high).

    Returns None if UW data unavailable. Cached upstream by uw_api_cache (300s TTL).
    """
    try:
        from integrations.uw_api import get_iv_rank
        data = await get_iv_rank(ticker)
        if not data:
            return None
        # UW returns a list; latest entry first
        latest = data[0] if isinstance(data, list) else data
        rank = latest.get("iv_rank") or latest.get("rank")
        if rank is None:
            return None
        rank_pct = float(rank)
        # Normalize to 0-100 if UW returns 0-1
        if rank_pct <= 1.0:
            rank_pct = rank_pct * 100
        rank_pct = round(rank_pct, 1)
        if rank_pct >= 70:
            tier = "high"
        elif rank_pct >= 30:
            tier = "mid"
        else:
            tier = "low"
        return {"rank": rank_pct, "tier": tier}
    except Exception as e:
        logger.debug("IV rank fetch failed for %s: %s", ticker, e)
        return None
```

### A.3 — Add dark pool activity helper

**Add this** immediately after `_get_iv_rank_for_ticker`:

```python
async def _get_dp_activity_for_ticker(ticker: str) -> Optional[Dict[str, Any]]:
    """Fetch recent dark pool activity for a ticker. Returns activity summary or None.

    Considers a ticker "active" if it has DP prints in the last 30 minutes.
    Cached upstream by uw_api_cache (300s TTL).
    """
    try:
        from integrations.uw_api import get_darkpool_ticker
        prints = await get_darkpool_ticker(ticker)
        if not prints:
            return None
        # Filter to last 30 min
        from datetime import datetime as dt_cls, timezone as tz_cls
        now_utc = dt_cls.now(tz_cls.utc)
        cutoff = now_utc.timestamp() - 1800  # 30 min
        recent = []
        for p in prints if isinstance(prints, list) else []:
            ts_raw = p.get("executed_at") or p.get("timestamp") or p.get("time")
            if not ts_raw:
                continue
            try:
                if isinstance(ts_raw, (int, float)):
                    ts = float(ts_raw) / 1000 if ts_raw > 1e12 else float(ts_raw)
                else:
                    ts = dt_cls.fromisoformat(str(ts_raw).replace("Z", "+00:00")).timestamp()
                if ts >= cutoff:
                    recent.append(p)
            except (ValueError, TypeError):
                continue
        if not recent:
            return None
        total_size = sum(float(p.get("size") or 0) for p in recent)
        total_value = sum(float(p.get("size") or 0) * float(p.get("price") or 0) for p in recent)
        return {
            "active": True,
            "prints_30m": len(recent),
            "total_size": int(total_size),
            "total_value": round(total_value, 0),
        }
    except Exception as e:
        logger.debug("DP activity fetch failed for %s: %s", ticker, e)
        return None
```

### A.4 — Wire the new helpers into `get_sector_leaders`

**Find this block** in `get_sector_leaders` (the loop that builds each constituent's `entry` dict):

```python
            entry["rsi_14"] = await _get_rsi_for_ticker(ticker, redis)
            entry["flow_direction"] = await _get_flow_direction(ticker)
            entry["week_change_pct"] = None
            entry["month_change_pct"] = None
```

**Replace with:**

```python
            entry["rsi_14"] = await _get_rsi_for_ticker(ticker, redis)

            # Enriched flow metrics (P2)
            flow_metrics = await _get_flow_metrics(ticker)
            entry["flow_direction"] = flow_metrics["direction"]
            entry["flow_call_pct"] = flow_metrics["call_pct"]
            entry["flow_premium"] = flow_metrics["total_premium"]

            # IV rank (P2)
            iv_data = await _get_iv_rank_for_ticker(ticker)
            entry["iv_rank"] = iv_data["rank"] if iv_data else None
            entry["iv_tier"] = iv_data["tier"] if iv_data else None

            # Dark pool activity (P2)
            dp_data = await _get_dp_activity_for_ticker(ticker)
            entry["dp_active"] = bool(dp_data and dp_data.get("active"))
            entry["dp_prints_30m"] = dp_data["prints_30m"] if dp_data else 0

            entry["week_change_pct"] = None
            entry["month_change_pct"] = None
```

### A.5 — Cleanup: polygon constants and module docstring

**Find** at the top of the file:

```python
"""
Sector API — heatmap + drill-down popup (Phase 2).

Heatmap: Polygon snapshot for live daily prices (primary), Polygon daily bars
         for weekly/monthly historical changes (cached 30 min).
Leaders: Per-sector top-20 constituents with real-time Polygon snapshot data,
         RSI, volume ratio, and options flow direction.
"""
```

**Replace with:**

```python
"""
Sector API — heatmap + drill-down popup.

Heatmap: UW API (yfinance under the hood) for live daily prices and historical bars.
Leaders: Per-sector top-20 constituents with live snapshot data, RSI, volume ratio,
         options flow metrics (direction + call %), IV rank, and dark pool activity.
"""
```

**Also find:**

```python
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY") or ""
```

**Delete that line entirely** (it's at the top after imports).

**Then find** further down (the second occurrence in the Phase 2 section):

```python
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
SNAPSHOT_URL = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
```

**Delete both lines.** They are unused post-cutover.

---

## Phase B — Backend: heatmap flow toggle endpoint

**File:** `backend/api/sectors.py`

The heatmap currently colors cells by `change_1d`. Add a query parameter `metric` so the frontend can request `metric=flow` and color cells by sector-level options flow direction instead.

### B.1 — Update `get_sector_heatmap` signature

**Find:**

```python
@router.get("/heatmap")
async def get_sector_heatmap():
    """Return sector data for treemap: all 11 sectors with Day/Week/Month changes and daily RS."""
```

**Replace with:**

```python
@router.get("/heatmap")
async def get_sector_heatmap(
    metric: str = Query("price", regex="^(price|flow)$",
                        description="Color metric: 'price' (% change) or 'flow' (options flow direction)"),
):
    """Return sector data for treemap: all 11 sectors with Day/Week/Month changes, daily RS,
    and (when metric='flow') aggregate options flow direction per sector."""
```

### B.2 — Add aggregate flow per sector

**Find** (still in `get_sector_heatmap`, the block near the end before the "Rank by rs_daily" sort):

```python
        sectors_data.append({
            "etf": etf,
            "name": info["name"],
            "weight": info["weight"],
            "price": round(price, 2) if price is not None else None,
            "change_1d": change_1d if change_1d is not None else 0.0,
            "change_1w": change_1w if change_1w is not None else 0.0,
            "change_1m": change_1m if change_1m is not None else 0.0,
            "rs_daily": rs_daily if rs_daily is not None else 0.0,
            "trend": trend,
            "strength_rank": 99,  # placeholder, computed below
        })
```

**Replace with:**

```python
        sector_entry = {
            "etf": etf,
            "name": info["name"],
            "weight": info["weight"],
            "price": round(price, 2) if price is not None else None,
            "change_1d": change_1d if change_1d is not None else 0.0,
            "change_1w": change_1w if change_1w is not None else 0.0,
            "change_1m": change_1m if change_1m is not None else 0.0,
            "rs_daily": rs_daily if rs_daily is not None else 0.0,
            "trend": trend,
            "strength_rank": 99,  # placeholder, computed below
        }

        # When metric=flow, compute aggregate flow direction for the sector ETF itself.
        # Cached upstream by _get_flow_metrics' DB query patterns; cheap.
        if metric == "flow":
            flow_metrics = await _get_flow_metrics(etf)
            sector_entry["flow_direction"] = flow_metrics["direction"]
            sector_entry["flow_call_pct"] = flow_metrics["call_pct"]
            sector_entry["flow_premium"] = flow_metrics["total_premium"]

        sectors_data.append(sector_entry)
```

### B.3 — Update result + cache key per metric

**Find:**

```python
    result = {
        "sectors": sorted(sectors_data, key=lambda s: s["weight"], reverse=True),
        "spy_change_1d": spy_change_1d,
        "spy_change_1w": spy_change_1w,
        "spy_change_1m": spy_change_1m,
        "is_market_hours": is_live,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
```

**Replace with:**

```python
    result = {
        "sectors": sorted(sectors_data, key=lambda s: s["weight"], reverse=True),
        "spy_change_1d": spy_change_1d,
        "spy_change_1w": spy_change_1w,
        "spy_change_1m": spy_change_1m,
        "is_market_hours": is_live,
        "metric": metric,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
```

### B.4 — Make the cache key metric-aware

**Find** the two locations where `HEATMAP_CACHE_KEY` is used to set/get cached data:

```python
    if redis:
        try:
            cached = await redis.get(HEATMAP_CACHE_KEY)
            if cached:
                return json.loads(cached)
```

**Replace with:**

```python
    cache_key = f"{HEATMAP_CACHE_KEY}:{metric}"
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
```

**And further down, find:**

```python
    if redis:
        try:
            result_json = json.dumps(result)
            await redis.set(HEATMAP_CACHE_KEY, result_json, ex=_heatmap_cache_ttl())
            if has_real_data:
                await redis.set(HEATMAP_STALE_KEY, result_json, ex=86400)
        except Exception:
            pass
```

**Replace with:**

```python
    if redis:
        try:
            result_json = json.dumps(result)
            await redis.set(cache_key, result_json, ex=_heatmap_cache_ttl())
            if has_real_data and metric == "price":
                await redis.set(HEATMAP_STALE_KEY, result_json, ex=86400)
        except Exception:
            pass
```

(Stale fallback only stores price-metric data — flow data shouldn't survive 24h staleness because flow ages out of the 24h window).

---

## Phase C — Backend: AE2 multi-threshold budget tracker

**File:** `backend/integrations/uw_api_cache.py`

Current code fires one alert at 50%. AE2 wants 50/70/85/95% with idempotent firing (don't re-alert once fired today).

### C.1 — Replace single threshold with thresholds list

**Find:**

```python
DAILY_BUDGET = 20000     # UW Basic plan limit
BUDGET_ALERT_PCT = 0.50  # Alert at 50%
```

**Replace with:**

```python
DAILY_BUDGET = 20000     # UW Basic plan limit
BUDGET_ALERT_THRESHOLDS = [0.50, 0.70, 0.85, 0.95]  # Alert at each crossing
```

### C.2 — Update `increment_daily_counter` to fire per-threshold

**Find:**

```python
        # Budget alert at threshold
        alert_threshold = int(DAILY_BUDGET * BUDGET_ALERT_PCT)
        if count == alert_threshold:
            logger.warning("UW API daily budget at %d%% (%d/%d requests)",
                           int(BUDGET_ALERT_PCT * 100), count, DAILY_BUDGET)
            await _post_budget_alert(count)
```

**Replace with:**

```python
        # Budget alerts at multiple thresholds (50/70/85/95%)
        # Use Redis flag per threshold per day to ensure each fires only once.
        from datetime import date as _date
        today_str = _date.today().isoformat()
        for threshold_pct in BUDGET_ALERT_THRESHOLDS:
            threshold_count = int(DAILY_BUDGET * threshold_pct)
            if count >= threshold_count:
                flag_key = f"uw:budget_alert_fired:{today_str}:{int(threshold_pct * 100)}"
                already_fired = await redis.get(flag_key)
                if not already_fired:
                    await redis.setex(flag_key, 172800, "1")  # 48h TTL
                    logger.warning("UW API daily budget at %d%% (%d/%d requests)",
                                   int(threshold_pct * 100), count, DAILY_BUDGET)
                    await _post_budget_alert(count, int(threshold_pct * 100))
```

### C.3 — Update alert helper to include threshold

**Find:**

```python
async def _post_budget_alert(count: int) -> None:
    """Post budget alert to Discord webhook."""
    try:
        import os
        import httpx
        webhook = os.getenv("DISCORD_WEBHOOK_SIGNALS", "")
        if not webhook:
            return
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(webhook, json={
                "content": f"**UW API Budget Alert:** {count}/{DAILY_BUDGET} requests "
                           f"({int(count/DAILY_BUDGET*100)}%) — monitor usage"
            })
    except Exception:
        pass
```

**Replace with:**

```python
async def _post_budget_alert(count: int, threshold_pct: int) -> None:
    """Post budget alert to Discord webhook with explicit threshold tier."""
    try:
        import os
        import httpx
        webhook = os.getenv("DISCORD_WEBHOOK_SIGNALS", "")
        if not webhook:
            return
        # Severity emoji based on threshold tier
        if threshold_pct >= 95:
            emoji = "\U0001F6A8"  # rotating light
            severity = "CRITICAL"
        elif threshold_pct >= 85:
            emoji = "\U000026A0\uFE0F"  # warning
            severity = "WARNING"
        elif threshold_pct >= 70:
            emoji = "\U0001F4CA"  # bar chart
            severity = "ELEVATED"
        else:
            emoji = "\U0001F4CB"  # clipboard
            severity = "INFO"
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(webhook, json={
                "content": f"{emoji} **UW API Budget [{severity}]** — {count}/{DAILY_BUDGET} requests "
                           f"({threshold_pct}% crossed) — monitor usage"
            })
    except Exception:
        pass
```

---

## Phase D — Backend: AE5 FACTOR_CONFIG description fix

**File:** `backend/bias_engine/composite.py`

The `iv_regime` factor description still references Polygon as its data source. Post-cutover, IV data comes from UW.

**Find:**

```python
    "iv_regime": {
        "weight": 0.02,
        "staleness_hours": 24,
        "description": "SPY IV rank percentile from Polygon chain - options pricing regime",
        "timeframe": "swing",
    },
```

**Replace with:**

```python
    "iv_regime": {
        "weight": 0.02,
        "staleness_hours": 24,
        "description": "SPY IV rank percentile from UW IV rank endpoint - options pricing regime",
        "timeframe": "swing",
    },
```

(That is the ONLY description still referencing Polygon — verify with `grep -i polygon backend/bias_engine/composite.py` after applying.)

---

## Phase E — Frontend: drill-down popup new columns

**File:** `frontend/app.js`

The drill-down popup table has 9 columns today. We're adding 3 more: Flow %, IV rank pill, DP badge. We're also keeping the existing flow icon column (it stays as a quick visual cue) — but adding the % beside it.

### E.1 — Update `_sectorPopupRow` to render new columns

**Find** (around line 6000-ish, the entire `_sectorPopupRow` function):

```javascript
function _sectorPopupRow(c, sectorDayChange) {
    var relColor = c.sector_relative_pct >= 0 ? 'var(--accent-green,#00e676)' : 'var(--accent-red,#ff5252)';
    var priceColor = c.day_change_pct >= 0 ? 'var(--accent-green,#00e676)' : 'var(--accent-red,#ff5252)';

    // Volume indicator
    var volIcon = '';
    if (c.volume_ratio != null) {
        if (c.volume_ratio > 2.0) volIcon = '\ud83d\udd25';
        else if (c.volume_ratio >= 1.0) volIcon = '\ud83d\udcc8';
        else if (c.volume_ratio < 0.5) volIcon = '\ud83d\ude34';
    }

    // Flow indicator
    var flowIcon = '\u26aa';
    if (c.flow_direction === 'bullish') flowIcon = '\ud83d\udfe2';
    else if (c.flow_direction === 'bearish') flowIcon = '\ud83d\udd34';

    var weekPct = c.week_change_pct != null ? ((c.week_change_pct >= 0 ? '+' : '') + c.week_change_pct.toFixed(1) + '%') : '-';
    var monthPct = c.month_change_pct != null ? ((c.month_change_pct >= 0 ? '+' : '') + c.month_change_pct.toFixed(1) + '%') : '-';

    return '<tr data-ticker="' + escapeHtml(c.ticker) + '" class="sector-popup-row">'
        + '<td class="sector-popup-ticker">' + escapeHtml(c.ticker) + (c.company_name ? '<span class="sector-popup-name">' + escapeHtml(c.company_name) + '</span>' : '') + '</td>'
        + '<td class="col-r" style="color:' + priceColor + '">' + (c.price ? '$' + c.price.toFixed(2) : '-') + '</td>'
        + '<td class="col-r" style="color:' + relColor + '">' + (c.day_change_pct >= 0 ? '+' : '') + c.day_change_pct.toFixed(2) + '%</td>'
        + '<td class="col-r" style="color:' + relColor + '">' + (c.sector_relative_pct >= 0 ? '+' : '') + c.sector_relative_pct.toFixed(2) + '%</td>'
        + '<td class="col-r">' + weekPct + '</td>'
        + '<td class="col-r">' + monthPct + '</td>'
        + '<td class="col-c">' + (c.rsi_14 != null ? c.rsi_14 : '-') + '</td>'
        + '<td class="col-c">' + volIcon + '</td>'
        + '<td class="col-c">' + flowIcon + '</td>'
        + '</tr>';
}
```

**Replace with:**

```javascript
function _sectorPopupRow(c, sectorDayChange) {
    var relColor = c.sector_relative_pct >= 0 ? 'var(--accent-green,#00e676)' : 'var(--accent-red,#ff5252)';
    var priceColor = c.day_change_pct >= 0 ? 'var(--accent-green,#00e676)' : 'var(--accent-red,#ff5252)';

    // Volume indicator
    var volIcon = '';
    if (c.volume_ratio != null) {
        if (c.volume_ratio > 2.0) volIcon = '\ud83d\udd25';
        else if (c.volume_ratio >= 1.0) volIcon = '\ud83d\udcc8';
        else if (c.volume_ratio < 0.5) volIcon = '\ud83d\ude34';
    }

    // Flow indicator + percentage (P2)
    var flowIcon = '\u26aa';
    if (c.flow_direction === 'bullish') flowIcon = '\ud83d\udfe2';
    else if (c.flow_direction === 'bearish') flowIcon = '\ud83d\udd34';
    var flowPct = '-';
    if (c.flow_call_pct != null) {
        flowPct = Math.round(c.flow_call_pct * 100) + '%';
    }

    // IV rank pill (P2)
    var ivPill = '<span class="sector-iv-pill sector-iv-na">-</span>';
    if (c.iv_rank != null && c.iv_tier) {
        ivPill = '<span class="sector-iv-pill sector-iv-' + escapeHtml(c.iv_tier) + '" '
               + 'title="IV Rank: ' + c.iv_rank.toFixed(1) + ' (' + c.iv_tier.toUpperCase() + ')">'
               + Math.round(c.iv_rank) + '</span>';
    }

    // Dark pool badge (P2)
    var dpBadge = '';
    if (c.dp_active) {
        var dpTitle = 'Dark pool active: ' + (c.dp_prints_30m || 0) + ' prints in last 30 min';
        dpBadge = '<span class="sector-dp-badge" title="' + escapeHtml(dpTitle) + '">DP</span>';
    } else {
        dpBadge = '<span class="sector-dp-badge sector-dp-inactive">-</span>';
    }

    var weekPct = c.week_change_pct != null ? ((c.week_change_pct >= 0 ? '+' : '') + c.week_change_pct.toFixed(1) + '%') : '-';
    var monthPct = c.month_change_pct != null ? ((c.month_change_pct >= 0 ? '+' : '') + c.month_change_pct.toFixed(1) + '%') : '-';

    return '<tr data-ticker="' + escapeHtml(c.ticker) + '" class="sector-popup-row">'
        + '<td class="sector-popup-ticker">' + escapeHtml(c.ticker) + (c.company_name ? '<span class="sector-popup-name">' + escapeHtml(c.company_name) + '</span>' : '') + '</td>'
        + '<td class="col-r" style="color:' + priceColor + '">' + (c.price ? '$' + c.price.toFixed(2) : '-') + '</td>'
        + '<td class="col-r" style="color:' + priceColor + '">' + (c.day_change_pct >= 0 ? '+' : '') + c.day_change_pct.toFixed(2) + '%</td>'
        + '<td class="col-r" style="color:' + relColor + '">' + (c.sector_relative_pct >= 0 ? '+' : '') + c.sector_relative_pct.toFixed(2) + '%</td>'
        + '<td class="col-r">' + weekPct + '</td>'
        + '<td class="col-r">' + monthPct + '</td>'
        + '<td class="col-c">' + (c.rsi_14 != null ? c.rsi_14 : '-') + '</td>'
        + '<td class="col-c">' + volIcon + '</td>'
        + '<td class="col-c">' + flowIcon + ' <span class="sector-flow-pct">' + flowPct + '</span></td>'
        + '<td class="col-c">' + ivPill + '</td>'
        + '<td class="col-c">' + dpBadge + '</td>'
        + '</tr>';
}
```

> **Note:** I also fixed a small bug while I was in there — the original `Day%` column used `relColor` (sector-relative color), which made big absolute moves look small if they matched the sector. New version uses `priceColor` for the Day% cell, which is what a trader actually wants to see at a glance.

### E.2 — Update divider row to match new column count

The "sector ETF" divider row currently has 9 cells. Now needs 12 (added Flow %, IV pill, DP badge).

**Find** (in `_renderSectorPopupTable`, the divider row block):

```javascript
    // Divider row (sector ETF)
    var etfPrice = data.etf_price || 0;
    html += '<tr class="sector-popup-divider">'
        + '<td><strong>' + escapeHtml(data.sector_etf || '') + '</strong></td>'
        + '<td class="col-r">' + (etfPrice ? '$' + etfPrice.toFixed(2) : '-') + '</td>'
        + '<td class="col-r" style="color:' + (sectorDayChange >= 0 ? 'var(--accent-green,#00e676)' : 'var(--accent-red,#ff5252)') + '">'
            + (sectorDayChange >= 0 ? '+' : '') + sectorDayChange.toFixed(2) + '%</td>'
        + '<td class="col-r">0.00%</td>'
        + '<td class="col-r">-</td><td class="col-r">-</td>'
        + '<td class="col-c">-</td><td class="col-c">-</td><td class="col-c">-</td>'
        + '</tr>';
```

**Replace with:**

```javascript
    // Divider row (sector ETF) — 12 cells matching enriched _sectorPopupRow (P2)
    var etfPrice = data.etf_price || 0;
    html += '<tr class="sector-popup-divider">'
        + '<td><strong>' + escapeHtml(data.sector_etf || '') + '</strong></td>'
        + '<td class="col-r">' + (etfPrice ? '$' + etfPrice.toFixed(2) : '-') + '</td>'
        + '<td class="col-r" style="color:' + (sectorDayChange >= 0 ? 'var(--accent-green,#00e676)' : 'var(--accent-red,#ff5252)') + '">'
            + (sectorDayChange >= 0 ? '+' : '') + sectorDayChange.toFixed(2) + '%</td>'
        + '<td class="col-r">0.00%</td>'
        + '<td class="col-r">-</td><td class="col-r">-</td>'
        + '<td class="col-c">-</td><td class="col-c">-</td><td class="col-c">-</td>'
        + '<td class="col-c">-</td><td class="col-c">-</td><td class="col-c">-</td>'
        + '</tr>';
```

### E.3 — Update the table header to include new column labels

The popup table header is built from HTML defined elsewhere in app.js. Find the function or inline string that generates the popup's `<thead>` (search for the existing text labels like `RSI` or `Vol` or `Flow` near a `<th>` tag). The original header has 9 `<th>` cells. Add three more after the existing Flow header:

```html
<th class="col-c">Flow</th>
<th class="col-c">IV</th>
<th class="col-c">DP</th>
```

(The existing Flow header should now be wide enough to show "Flow %" — change its inner text to `Flow` if currently something else, but the column WILL display both icon and percentage thanks to E.1.)

If you can't locate the header generator cleanly, search for `sector-popup-table` class definition in `frontend/styles.css` — the `<thead>` is likely generated by an `_initSectorPopupHTML` or similar function in app.js. Report back if the header anchor isn't obvious; I'll write a more specific find/replace.

---

## Phase F — Frontend: heatmap Flow/Price toggle

**File:** `frontend/app.js`

Add a small toggle button to the heatmap header that switches between coloring by daily price change (current) and coloring by aggregate options flow direction (new).

### F.1 — Add the toggle button

Find the heatmap render function. It will reference `getSectorHeatmap` or fetch `/sectors/heatmap`. Search for:

```
fetch(API_URL + '/sectors/heatmap')
```

Just above where the heatmap data is rendered into the DOM, add a toggle UI element. The exact insertion point depends on the heatmap container structure — find the heatmap header `<div>` (likely class `heatmap-header` or `sector-heatmap-title`) and append:

```html
<div class="heatmap-toggle">
    <button class="heatmap-toggle-btn active" data-metric="price">Price</button>
    <button class="heatmap-toggle-btn" data-metric="flow">Flow</button>
</div>
```

Then add a global state variable near the other heatmap-related state:

```javascript
var _heatmapMetric = 'price';  // 'price' | 'flow'
```

And wire up button click handlers (when the heatmap is initialized):

```javascript
document.querySelectorAll('.heatmap-toggle-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
        var metric = btn.dataset.metric;
        if (metric === _heatmapMetric) return;
        _heatmapMetric = metric;
        document.querySelectorAll('.heatmap-toggle-btn').forEach(function(b) {
            b.classList.toggle('active', b.dataset.metric === metric);
        });
        if (typeof renderSectorHeatmap === 'function') renderSectorHeatmap();
        else if (typeof loadSectorHeatmap === 'function') loadSectorHeatmap();
    });
});
```

### F.2 — Update the fetch URL

Find the heatmap fetch and update it:

```javascript
// OLD:
var resp = await fetch(API_URL + '/sectors/heatmap');

// NEW:
var resp = await fetch(API_URL + '/sectors/heatmap?metric=' + (_heatmapMetric || 'price'));
```

### F.3 — Update cell coloring to honor the metric

Find the part of the heatmap render code that sets cell colors based on `change_1d`. It will look something like:

```javascript
var color = sector.change_1d >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
```

Wrap this in a metric branch:

```javascript
var color;
if (_heatmapMetric === 'flow') {
    if (sector.flow_direction === 'bullish') color = 'var(--accent-green,#00e676)';
    else if (sector.flow_direction === 'bearish') color = 'var(--accent-red,#ff5252)';
    else color = 'var(--text-secondary,#888)';
} else {
    color = sector.change_1d >= 0 ? 'var(--accent-green,#00e676)' : 'var(--accent-red,#ff5252)';
}
```

If color INTENSITY is computed (alpha based on magnitude), use `flow_call_pct` distance from 0.5 as the magnitude when in flow mode:

```javascript
var intensity;
if (_heatmapMetric === 'flow') {
    var pct = sector.flow_call_pct != null ? sector.flow_call_pct : 0.5;
    intensity = Math.min(1, Math.abs(pct - 0.5) * 4);  // 0.5 = neutral, 0.75 = max
} else {
    intensity = Math.min(1, Math.abs(sector.change_1d) / 2);  // existing behavior
}
```

> **Find-as-you-go:** the heatmap rendering varies between hub builds. If the existing color logic doesn't match the snippets above, adapt — the goal is "same color rules, but flow_direction substitutes for change_1d sign when metric=flow."

---

## Phase G — Frontend: CSS additions

**File:** `frontend/styles.css`

Add these rules at the end of the file (or in the sector-popup section if it exists):

```css
/* ── P2: Sector drill-down enrichment ─────────────────────────── */

.sector-flow-pct {
    font-size: 0.85em;
    color: var(--text-secondary, #888);
    margin-left: 4px;
}

.sector-iv-pill {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 0.8em;
    font-weight: 600;
    min-width: 28px;
    text-align: center;
    background: var(--surface-2, #2a2a2a);
    color: var(--text-secondary, #aaa);
}

.sector-iv-pill.sector-iv-low {
    background: rgba(0, 230, 118, 0.15);
    color: var(--accent-green, #00e676);
}

.sector-iv-pill.sector-iv-mid {
    background: rgba(255, 167, 38, 0.15);
    color: var(--accent-amber, #ffa726);
}

.sector-iv-pill.sector-iv-high {
    background: rgba(255, 82, 82, 0.15);
    color: var(--accent-red, #ff5252);
}

.sector-iv-pill.sector-iv-na {
    background: transparent;
    color: var(--text-disabled, #555);
    font-weight: 400;
}

.sector-dp-badge {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.75em;
    font-weight: 700;
    background: rgba(124, 77, 255, 0.2);
    color: #b39ddb;
    letter-spacing: 0.5px;
}

.sector-dp-badge.sector-dp-inactive {
    background: transparent;
    color: var(--text-disabled, #555);
    font-weight: 400;
    letter-spacing: 0;
}

/* Heatmap Flow/Price toggle */
.heatmap-toggle {
    display: inline-flex;
    gap: 0;
    border: 1px solid var(--border-color, #333);
    border-radius: 6px;
    overflow: hidden;
    margin-left: 12px;
}

.heatmap-toggle-btn {
    background: transparent;
    border: none;
    color: var(--text-secondary, #888);
    padding: 4px 12px;
    font-size: 0.85em;
    cursor: pointer;
    transition: background 0.15s, color 0.15s;
}

.heatmap-toggle-btn:hover {
    background: var(--surface-2, #2a2a2a);
}

.heatmap-toggle-btn.active {
    background: var(--accent-blue, #2196f3);
    color: white;
    font-weight: 600;
}
```

---

## Sequenced commit plan

Apply the brief in three commits, each ending with `git push` and a brief verification pause:

**Commit 1 — Backend changes (Phases A, B, C, D)**

```bash
# Apply Phase A.1, A.2, A.3, A.4, A.5
# Apply Phase B.1, B.2, B.3, B.4
# Apply Phase C.1, C.2, C.3
# Apply Phase D
python -c "import ast; ast.parse(open('backend/api/sectors.py').read())"
python -c "import ast; ast.parse(open('backend/integrations/uw_api_cache.py').read())"
python -c "import ast; ast.parse(open('backend/bias_engine/composite.py').read())"
git add backend/api/sectors.py backend/integrations/uw_api_cache.py backend/bias_engine/composite.py
git commit -m "P2: enrich sector leaders + heatmap flow toggle + AE2 multi-threshold budget + AE5 desc fix"
git push origin main
# Wait ~90s for Railway deploy
```

**Commit 2 — Frontend changes (Phases E, F, G)**

```bash
# Apply Phase E (3 sub-edits in app.js)
# Apply Phase F (3 sub-edits in app.js)
# Apply Phase G (CSS additions)
git add frontend/app.js frontend/styles.css
git commit -m "P2 frontend: drill-down flow%/IV/DP columns + heatmap Flow/Price toggle"
git push origin main
# No Railway deploy wait — frontend served as static files
```

---

## Verification checklist

Run all checks AFTER both commits land. Use `claude-pivot-key-2025-XYZ` from `/opt/pivot/.env` as the API key (or fetch it from VPS as part of verification). Each check is PASS/FAIL:

### Backend — direct curl

1. **Drill-down endpoint returns enriched fields** (XLK as test sector):
   ```bash
   curl -sH "X-API-Key: $PIVOT_API_KEY" \
     "https://pandoras-box-production.up.railway.app/api/sectors/XLK/leaders" \
     | python -m json.tool | grep -E '"flow_call_pct"|"iv_rank"|"iv_tier"|"dp_active"|"dp_prints_30m"' | head -20
   ```
   PASS if all 5 fields appear in output. FAIL if any are missing.

2. **Heatmap default (price metric) still works:**
   ```bash
   curl -sH "X-API-Key: $PIVOT_API_KEY" \
     "https://pandoras-box-production.up.railway.app/api/sectors/heatmap" \
     | python -m json.tool | grep '"metric"'
   ```
   PASS if `"metric": "price"` appears.

3. **Heatmap flow metric returns flow_direction per sector:**
   ```bash
   curl -sH "X-API-Key: $PIVOT_API_KEY" \
     "https://pandoras-box-production.up.railway.app/api/sectors/heatmap?metric=flow" \
     | python -m json.tool | grep -E '"flow_direction"|"flow_call_pct"' | head -10
   ```
   PASS if both fields present, with values like `bullish`/`bearish`/`neutral`.

4. **Heatmap rejects invalid metric:**
   ```bash
   curl -sH "X-API-Key: $PIVOT_API_KEY" \
     "https://pandoras-box-production.up.railway.app/api/sectors/heatmap?metric=garbage" \
     -o /dev/null -w "%{http_code}\n"
   ```
   PASS if 422 (Unprocessable Entity from FastAPI validation).

5. **Polygon constants are gone:**
   ```bash
   grep -n "POLYGON_API_KEY\|SNAPSHOT_URL" backend/api/sectors.py
   ```
   PASS if no matches. FAIL if any remain.

6. **FACTOR_CONFIG iv_regime description updated:**
   ```bash
   grep -A2 '"iv_regime"' backend/bias_engine/composite.py | grep -i polygon
   ```
   PASS if no output (Polygon NOT mentioned). FAIL if "Polygon" still appears.

7. **Module docstring updated:**
   ```bash
   head -10 backend/api/sectors.py | grep -i polygon
   ```
   PASS if no output.

### Frontend — browser checks

8. **Open Agora at https://pandoras-box-production.up.railway.app**, log in, and click into the Sector Heatmap.
   - Confirm Flow/Price toggle appears in the heatmap header. PASS/FAIL.
   - Click "Flow" — heatmap cells re-color based on flow direction (greens stay green if bullish flow, etc.). PASS/FAIL.
   - Click "Price" — returns to original % change coloring. PASS/FAIL.

9. **Click into any sector to open the drill-down popup.**
   - Confirm 12 columns now visible: Ticker, Price, Day%, vs Sector%, Week%, Month%, RSI, Vol, Flow, IV, DP. (Last 3 are new.) PASS/FAIL.
   - Confirm IV pills are color-coded: green (low), amber (mid), red (high). PASS/FAIL.
   - Confirm DP badge appears in purple for active tickers, dash for inactive. PASS/FAIL.
   - Hover an IV pill — tooltip shows "IV Rank: XX.X (TIER)". PASS/FAIL.
   - Hover a DP badge — tooltip shows "Dark pool active: N prints in last 30 min". PASS/FAIL.

10. **Open browser DevTools Network tab, refresh popup. Find the `/leaders` response.**
    - Confirm `flow_call_pct`, `iv_rank`, `iv_tier`, `dp_active`, `dp_prints_30m` are all in the JSON. PASS/FAIL.

### UW budget check (AE2 sanity, optional)

11. **Verify UW health endpoint shows budget threshold flags exist** (this won't fire unless count crosses; just sanity):
    ```bash
    curl -sH "X-API-Key: $PIVOT_API_KEY" \
      "https://pandoras-box-production.up.railway.app/api/uw/health" \
      | python -m json.tool | grep -E '"daily_requests"|"daily_budget"'
    ```
    PASS if both fields appear with sane values (count ≥ 0, budget = 20000).

---

## Known risks & non-goals

- **Drill-down API latency increases** — we now make 3 additional UW calls per ticker (IV rank, DP activity) plus the existing flow query. With 20 constituents per sector and 5-min cache TTLs, the second-and-subsequent open of a popup will be fast. The FIRST open after cache expiry will add ~2-4 seconds. **Mitigation:** UW Basic plan has 120 req/min ceiling; 20 tickers × 2 endpoints = 40 calls per popup open well under cap. Cache prevents amplification on repeat opens.
- **Heatmap flow coloring requires populated `flow_events` table** — the table is filled by the existing UW flow poller cron (every 5 min during market hours). If poller is failing, flow toggle will show all-neutral. **Mitigation:** existing alerting catches poller failure separately; not P2's concern.
- **UW IV rank endpoint can return null/empty for thin tickers** — these get `iv_rank: null` and the frontend renders a `-`. Expected. Not a bug.
- **Dark pool data has 30-minute lookback only** — by design; longer lookbacks dilute signal. If we want longer windows later, that's a v-next followup.
- **Non-goal: full sector flow leaders** (e.g., "show me which sector has the most aggressive bullish flow right now"). That's a separate watchlist feature — not in P2.
- **Non-goal: per-endpoint UW budget caps via env vars.** AE2 includes the multi-threshold ALERT system but skips the env-var per-endpoint cap mechanism. Per-endpoint caps add complexity (which endpoints? how to gracefully degrade when capped?) without a current overage problem. Revisit if budget burn rate increases post-P2.

---

## Rollback plan

If P2 breaks production:

```bash
git revert <p2-frontend-commit-sha>
git revert <p2-backend-commit-sha>
git push origin main
# Wait ~90s for Railway redeploy
```

The changes are surgical and isolated — backend revert restores the previous heatmap/leaders behavior; frontend revert restores the 9-column popup. No DB schema changes, no migrations, no cron changes.

---

## What this delivers

After P2 lands, the sector heatmap and drill-down popup answer three questions Nick currently has to leave the hub to answer:

1. **Is this ticker's options flow bullish or bearish, and how strongly?** → Flow % column
2. **Are options expensive or cheap right now?** → IV rank pill (low = cheap calls/puts, high = expensive)
3. **Is institutional money quietly accumulating?** → DP badge

Plus the heatmap flow toggle gives a single-glance read on which sectors institutions are actually positioning in — versus which are merely up on momentum-trader noise.

This compresses what is currently a 4-tab workflow (heatmap → drill down → ticker popup → external IV check) into the existing 2-tab flow, with no new screens or panels.

