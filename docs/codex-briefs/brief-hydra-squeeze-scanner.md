# BRIEF: Hydra — Squeeze Scanner Module
## Priority: P1 | System: Railway + Agora UI
## Date: 2026-03-31
## Related: Hermes Flash (Briefs 1 + 2) — Hydra integrates with Hermes for convergence alerts

---

## CONTEXT FOR CLAUDE CODE

Hydra is a short squeeze detection system that serves two purposes:

1. **Defensive (default):** Warns Nick when his own short positions (puts on SMH, XLF, HYG, IYR, IWM) are vulnerable to a squeeze. If shorts are covering aggressively on names he's betting against, he needs to know immediately.

2. **Offensive (opt-in):** Surfaces the top squeeze candidates as Bucket 2 tactical trade ideas — short-dated calls on heavily-shorted names about to rip. These are 3-5 day holds with 50-100%+ targets.

**The connection to Hermes:** When a Hermes Flash velocity breach fires AND Hydra shows elevated squeeze scores in the affected sector, the system generates a "Convergence Alert" — the highest-priority signal. Example: Hermes detects SPY +1.5% on peace talk headlines + Hydra shows SMH shorts deeply underwater = high probability squeeze unfolding in semis.

**Database is Railway Postgres** (NOT Supabase). Use `get_postgres_client()` from `backend/database/postgres_client.py` for all DB operations.

**Data sources available:**
- Polygon.io (Stocks Starter, $29/mo) — equities, ETFs, options data. API key in env: `POLYGON_API_KEY`
- UW Watcher pipeline — options flow events already land in `flow_events` table
- Scanner signals — Artemis, Phalanx, Trojan Horse data in existing tables
- Hermes `catalyst_events` table (from Brief 1)
- `unified_positions` table — Nick's current open positions

---

## STEP 1: Database — `squeeze_scores` Table

```sql
CREATE TABLE IF NOT EXISTS squeeze_scores (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker TEXT NOT NULL,
    short_interest_shares BIGINT,
    shares_float BIGINT,
    short_interest_pct NUMERIC(6,2),
    days_to_cover NUMERIC(6,2),
    short_interest_date DATE,
    current_price NUMERIC(10,2),
    price_30d_ago NUMERIC(10,2),
    price_change_30d_pct NUMERIC(6,2),
    estimated_short_pnl TEXT DEFAULT 'unknown',
    unusual_call_volume BOOLEAN DEFAULT FALSE,
    call_put_ratio NUMERIC(6,2),
    large_call_flow_value NUMERIC(14,2),
    sector TEXT,
    sector_velocity_pct NUMERIC(6,2),
    composite_score NUMERIC(5,1) NOT NULL DEFAULT 0,
    in_nick_book BOOLEAN DEFAULT FALSE,
    nick_position_direction TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_squeeze_ticker UNIQUE (ticker)
);

CREATE INDEX idx_squeeze_composite ON squeeze_scores (composite_score DESC);
CREATE INDEX idx_squeeze_nick_book ON squeeze_scores (in_nick_book) WHERE in_nick_book = TRUE;
```

**Score ranges:** 0-30 low, 31-60 moderate, 61-80 elevated, 81-100 extreme squeeze risk.

---

## STEP 2: Short Interest Data Ingestion

Polygon may or may not have short interest at Starter tier. Check first.

```python
import httpx, os, logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("hydra")
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
POLYGON_BASE = "https://api.polygon.io"

HYDRA_WATCHLIST = [
    # Nick's short positions (defensive)
    "SMH", "XLF", "HYG", "IYR", "IWM",
    # High short interest ETFs
    "ARKK", "SQQQ", "XRT", "KRE", "BITO",
    # Individual stocks — commonly squeezed / thesis-relevant
    "TSLA", "COIN", "CVNA", "GME", "AMC",
    "MSTR", "RIVN", "LCID", "SOFI", "PLTR",
    "UPST", "AFRM", "U", "ASTS", "APLD",
    "NVDA", "MRVL", "AVGO", "AAPL",
]

async def fetch_short_interest_polygon(ticker: str) -> dict:
    """Try Polygon SI endpoint; fall back to snapshot for price/volume."""
    result = {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Attempt 1: Direct short interest endpoint
        try:
            resp = await client.get(
                f"{POLYGON_BASE}/v2/reference/short-interest/{ticker}",
                params={"apiKey": POLYGON_API_KEY}
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("results"):
                    latest = data["results"][0] if isinstance(data["results"], list) else data["results"]
                    result["short_interest_shares"] = latest.get("shortInterest") or latest.get("short_interest")
                    result["short_interest_date"] = latest.get("date") or latest.get("settlement_date")
                    result["source"] = "polygon_direct"
                    return result
            elif resp.status_code == 403:
                logger.info(f"HYDRA: Polygon SI not available at current tier for {ticker}")
        except Exception as e:
            logger.debug(f"HYDRA: Polygon SI attempt failed for {ticker}: {e}")

        # Attempt 2: Snapshot for current price + volume
        try:
            resp = await client.get(
                f"{POLYGON_BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}",
                params={"apiKey": POLYGON_API_KEY}
            )
            if resp.status_code == 200:
                data = resp.json()
                td = data.get("ticker", {})
                day = td.get("day", {})
                prev = td.get("prevDay", {})
                result["current_price"] = day.get("c") or prev.get("c")
                result["volume"] = day.get("v") or prev.get("v")
                result["source"] = "polygon_snapshot"
        except Exception as e:
            logger.debug(f"HYDRA: Polygon snapshot failed for {ticker}: {e}")

    return result


async def fetch_price_history(ticker: str) -> dict:
    """Current price and 30-day-ago price for short P&L estimation."""
    result = {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            ago = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")

            resp = await client.get(
                f"{POLYGON_BASE}/v2/aggs/ticker/{ticker}/prev",
                params={"apiKey": POLYGON_API_KEY}
            )
            if resp.status_code == 200 and resp.json().get("results"):
                result["current_price"] = resp.json()["results"][0].get("c")

            resp2 = await client.get(
                f"{POLYGON_BASE}/v2/aggs/ticker/{ticker}/range/1/day/{ago}/{ago}",
                params={"apiKey": POLYGON_API_KEY, "adjusted": "true"}
            )
            if resp2.status_code == 200 and resp2.json().get("results"):
                result["price_30d_ago"] = resp2.json()["results"][0].get("c")

            if result.get("current_price") and result.get("price_30d_ago"):
                chg = round(((result["current_price"] - result["price_30d_ago"]) / result["price_30d_ago"]) * 100, 2)
                result["price_change_30d_pct"] = chg
                result["estimated_short_pnl"] = "underwater" if chg > 5 else ("profitable" if chg < -5 else "breakeven")
        except Exception as e:
            logger.error(f"HYDRA: Price history failed for {ticker}: {e}")
    return result
```

---

## STEP 3: UW Flow Integration

Large call buying on heavily-shorted names is the match that lights the squeeze fuse.

```python
async def get_unusual_call_flow(ticker: str, pool) -> dict:
    """Check flow_events for unusual call activity in last 24h."""
    result = {"unusual_call_volume": False, "call_put_ratio": 0, "large_call_flow_value": 0}
    try:
        # CC: adjust column names to match actual flow_events schema
        rows = await pool.fetch("""
            SELECT side, sentiment, premium, ticker
            FROM flow_events
            WHERE ticker = $1
            AND created_at >= NOW() - INTERVAL '24 hours'
            AND premium >= 100000
        """, ticker)

        if not rows:
            return result

        total_call = sum(float(r.get("premium", 0)) for r in rows if "call" in (r.get("side") or "").lower())
        total_put = sum(float(r.get("premium", 0)) for r in rows if "put" in (r.get("side") or "").lower())

        result["call_put_ratio"] = round(total_call / total_put, 2) if total_put > 0 else (99.0 if total_call > 0 else 0)
        result["large_call_flow_value"] = total_call
        result["unusual_call_volume"] = total_call >= 500000 or result["call_put_ratio"] >= 3.0

    except Exception as e:
        logger.error(f"HYDRA: Flow query failed for {ticker}: {e}")
    return result
```

---

## STEP 4: Composite Squeeze Score

```python
def calculate_squeeze_score(
    short_interest_pct=0, days_to_cover=0, estimated_short_pnl="unknown",
    unusual_call_volume=False, call_put_ratio=0, sector_velocity_pct=0
) -> float:
    """
    Composite 0-100. Weights:
    - Short Interest % Float: 30%  (fuel)
    - Days to Cover: 20%          (exit difficulty)
    - Short P&L Estimate: 20%     (pain = pressure)
    - Unusual Call Flow: 15%      (amplifier)
    - Sector Velocity: 15%        (catalyst trigger)
    """
    score = 0.0
    score += min(30, float(short_interest_pct) * 1.0)
    score += min(20, float(days_to_cover) * 2.0)
    score += {"underwater": 20, "breakeven": 10, "profitable": 3, "unknown": 8}.get(estimated_short_pnl, 8)
    if unusual_call_volume:
        score += 15 if call_put_ratio >= 5 else (12 if call_put_ratio >= 3 else 10)
    if sector_velocity_pct > 0:
        score += min(15, float(sector_velocity_pct) * 5.0)
    return round(min(100, max(0, score)), 1)
```

---

## STEP 5: Hydra Refresh Cron

Runs daily at 09:35 ET + every 30 min during market hours.

```python
async def hydra_refresh():
    """Full refresh of squeeze scores for all watchlist tickers."""
    from backend.database.postgres_client import get_postgres_client
    import json

    pool = await get_postgres_client()
    logger.info(f"HYDRA REFRESH: Scanning {len(HYDRA_WATCHLIST)} tickers")

    # Load Nick's positions for defensive flagging
    nick_positions = {}
    try:
        pos_rows = await pool.fetch("""
            SELECT ticker, direction, status FROM unified_positions WHERE status = 'open'
        """)
        # CC: adjust columns — may need option_type or strategy to determine direction
        for row in pos_rows:
            nick_positions[row.get("ticker", "")] = row.get("direction", "short")
    except Exception as e:
        logger.error(f"HYDRA: Failed to load positions: {e}")

    # Get latest sector velocities from Hermes
    sector_velocities = {}
    try:
        row = await pool.fetchrow("""
            SELECT sector_velocity FROM catalyst_events
            WHERE sector_velocity IS NOT NULL
            ORDER BY created_at DESC LIMIT 1
        """)
        if row and row.get("sector_velocity"):
            sv = row["sector_velocity"]
            sector_velocities = json.loads(sv) if isinstance(sv, str) else sv
    except Exception:
        pass

    ticker_sector_map = {
        "SMH": "SMH", "NVDA": "SMH", "MRVL": "SMH", "AVGO": "SMH",
        "XLF": "XLF", "KRE": "XLF", "SOFI": "XLF",
        "IYR": "IYR", "ARKK": "QQQ", "TSLA": "QQQ",
        "COIN": "QQQ", "PLTR": "QQQ", "U": "QQQ", "AAPL": "QQQ",
    }

    for ticker in HYDRA_WATCHLIST:
        try:
            si_data = await fetch_short_interest_polygon(ticker)
            price_data = await fetch_price_history(ticker)
            flow_data = await get_unusual_call_flow(ticker, pool)

            sector_etf = ticker_sector_map.get(ticker, "SPY")
            sector_vel = sector_velocities.get(sector_etf, 0)
            si_pct = float(si_data.get("short_interest_pct") or 0)
            dtc = float(si_data.get("days_to_cover") or 0)
            short_pnl = price_data.get("estimated_short_pnl", "unknown")

            composite = calculate_squeeze_score(
                short_interest_pct=si_pct, days_to_cover=dtc,
                estimated_short_pnl=short_pnl,
                unusual_call_volume=flow_data["unusual_call_volume"],
                call_put_ratio=flow_data["call_put_ratio"],
                sector_velocity_pct=float(sector_vel)
            )

            in_book = ticker in nick_positions
            direction = nick_positions.get(ticker, "")

            await pool.execute("""
                INSERT INTO squeeze_scores (
                    ticker, short_interest_shares, shares_float,
                    short_interest_pct, days_to_cover, short_interest_date,
                    current_price, price_30d_ago, price_change_30d_pct,
                    estimated_short_pnl,
                    unusual_call_volume, call_put_ratio, large_call_flow_value,
                    sector, sector_velocity_pct, composite_score,
                    in_nick_book, nick_position_direction, updated_at
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,NOW()
                )
                ON CONFLICT (ticker) DO UPDATE SET
                    short_interest_shares=EXCLUDED.short_interest_shares,
                    shares_float=EXCLUDED.shares_float,
                    short_interest_pct=EXCLUDED.short_interest_pct,
                    days_to_cover=EXCLUDED.days_to_cover,
                    short_interest_date=EXCLUDED.short_interest_date,
                    current_price=EXCLUDED.current_price,
                    price_30d_ago=EXCLUDED.price_30d_ago,
                    price_change_30d_pct=EXCLUDED.price_change_30d_pct,
                    estimated_short_pnl=EXCLUDED.estimated_short_pnl,
                    unusual_call_volume=EXCLUDED.unusual_call_volume,
                    call_put_ratio=EXCLUDED.call_put_ratio,
                    large_call_flow_value=EXCLUDED.large_call_flow_value,
                    sector=EXCLUDED.sector,
                    sector_velocity_pct=EXCLUDED.sector_velocity_pct,
                    composite_score=EXCLUDED.composite_score,
                    in_nick_book=EXCLUDED.in_nick_book,
                    nick_position_direction=EXCLUDED.nick_position_direction,
                    updated_at=NOW()
            """,
                ticker, si_data.get("short_interest_shares"), si_data.get("shares_float"),
                si_pct, dtc, si_data.get("short_interest_date"),
                price_data.get("current_price"), price_data.get("price_30d_ago"),
                price_data.get("price_change_30d_pct"), short_pnl,
                flow_data["unusual_call_volume"], flow_data["call_put_ratio"],
                flow_data["large_call_flow_value"], sector_etf, sector_vel,
                composite, in_book, direction
            )
            logger.debug(f"HYDRA: {ticker} score={composite} {'⚠️ IN BOOK' if in_book else ''}")

        except Exception as e:
            logger.error(f"HYDRA: Error processing {ticker}: {e}")
            continue

    logger.info("HYDRA REFRESH: Complete")
```

**Cron registration:** Add alongside existing crons. Schedule: daily at 09:35 ET + every 30 min during market hours (`*/30 9-16 * * 1-5` in ET).

---

## STEP 6: API Endpoints

```python
from fastapi import APIRouter, Query
from backend.database.postgres_client import get_postgres_client
import json

router = APIRouter(prefix="/api/hydra", tags=["hydra"])

@router.get("/scores")
async def get_squeeze_scores(
    limit: int = Query(20, ge=1, le=100),
    min_score: float = Query(0, ge=0, le=100),
    in_book_only: bool = Query(False)
):
    """Ranked squeeze scores. Defensive: in_book_only=true. Offensive: all tickers."""
    pool = await get_postgres_client()
    query = "SELECT * FROM squeeze_scores WHERE composite_score >= $1"
    params = [min_score]
    if in_book_only:
        query += " AND in_nick_book = TRUE"
    query += f" ORDER BY composite_score DESC LIMIT ${len(params)+1}"
    params.append(limit)
    rows = await pool.fetch(query, *params)
    return {"scores": [dict(row) for row in rows], "count": len(rows), "mode": "defensive" if in_book_only else "offensive"}

@router.get("/exposure")
async def get_squeeze_exposure():
    """Defensive: Nick's positions sorted by squeeze vulnerability."""
    pool = await get_postgres_client()
    rows = await pool.fetch("""
        SELECT ticker, composite_score, short_interest_pct, days_to_cover,
               estimated_short_pnl, unusual_call_volume, call_put_ratio,
               price_change_30d_pct, sector_velocity_pct, nick_position_direction, updated_at
        FROM squeeze_scores WHERE in_nick_book = TRUE
        ORDER BY composite_score DESC
    """)
    positions = [dict(row) for row in rows]
    high_risk = [p for p in positions if p.get("composite_score", 0) >= 60]
    return {
        "positions": positions,
        "high_risk_count": len(high_risk),
        "moderate_risk_count": len([p for p in positions if 30 <= p.get("composite_score", 0) < 60]),
        "alert": len(high_risk) > 0,
        "alert_message": f"⚠️ {len(high_risk)} position(s) at elevated squeeze risk" if high_risk else None
    }

@router.get("/convergence")
async def check_convergence():
    """Highest-priority: active Hermes catalyst + elevated squeeze scores in same sector."""
    pool = await get_postgres_client()
    hermes = await pool.fetch("""
        SELECT id, trigger_ticker, tier, sector_velocity, created_at
        FROM catalyst_events
        WHERE dismissed = FALSE AND created_at >= NOW() - INTERVAL '30 minutes'
        ORDER BY created_at DESC LIMIT 5
    """)
    if not hermes:
        return {"convergence": False, "events": []}

    convergences = []
    for event in hermes:
        trigger = event.get("trigger_ticker", "")
        squeezed = await pool.fetch("""
            SELECT ticker, composite_score, short_interest_pct, unusual_call_volume
            FROM squeeze_scores
            WHERE composite_score >= 50 AND (ticker = $1 OR sector = $1)
            ORDER BY composite_score DESC LIMIT 5
        """, trigger)
        if squeezed:
            convergences.append({
                "hermes_event_id": str(event["id"]),
                "trigger_ticker": trigger,
                "hermes_tier": event.get("tier"),
                "squeeze_candidates": [dict(s) for s in squeezed]
            })
    return {
        "convergence": len(convergences) > 0,
        "events": convergences,
        "alert_message": f"🔴 CONVERGENCE: {len(convergences)} catalyst + squeeze overlap(s)" if convergences else None
    }
```

**Router registration:** `from routes.hydra import router as hydra_router; app.include_router(hydra_router)`

---

## STEP 7: Agora Frontend — Hydra Panel

Collapsible panel below portfolio section with two tabs.

### HTML:
```html
<div class="hydra-panel" id="hydra-panel">
    <div class="hydra-header" onclick="toggleHydraPanel()">
        <span class="hydra-title">🐍 HYDRA — Squeeze Monitor</span>
        <span class="hydra-alert-badge" id="hydra-alert-badge" style="display: none;">!</span>
        <span class="hydra-toggle" id="hydra-toggle">▼</span>
    </div>
    <div class="hydra-body" id="hydra-body" style="display: none;">
        <div class="hydra-tabs">
            <button class="hydra-tab active" id="hydra-tab-defensive" onclick="switchHydraTab('defensive')">🛡 Defensive</button>
            <button class="hydra-tab" id="hydra-tab-offensive" onclick="switchHydraTab('offensive')">⚔ Offensive</button>
        </div>
        <div class="hydra-content" id="hydra-defensive">
            <div class="hydra-exposure-summary" id="hydra-exposure-summary"></div>
            <div class="hydra-table-container" id="hydra-defensive-table"></div>
        </div>
        <div class="hydra-content" id="hydra-offensive" style="display: none;">
            <div class="hydra-table-container" id="hydra-offensive-table"></div>
        </div>
        <div class="hydra-convergence" id="hydra-convergence" style="display: none;">
            <div class="hydra-convergence-text" id="hydra-convergence-text"></div>
        </div>
    </div>
</div>
```

### CSS:
```css
.hydra-panel { background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; margin-top: 8px; }
.hydra-header { display: flex; align-items: center; padding: 8px 12px; cursor: pointer; }
.hydra-header:hover { background: rgba(255,255,255,0.03); }
.hydra-title { font-size: 13px; font-weight: 600; font-family: 'IBM Plex Mono', monospace; color: rgba(255,255,255,0.7); }
.hydra-alert-badge { margin-left: 8px; background: #f44336; color: white; border-radius: 50%; width: 18px; height: 18px; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; animation: hydra-pulse 1.5s ease-in-out infinite; }
@keyframes hydra-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }
.hydra-toggle { margin-left: auto; opacity: 0.4; font-size: 11px; }
.hydra-body { padding: 8px 12px; }
.hydra-tabs { display: flex; gap: 4px; margin-bottom: 8px; }
.hydra-tab { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); color: rgba(255,255,255,0.5); padding: 4px 10px; border-radius: 3px; font-size: 11px; cursor: pointer; font-family: 'IBM Plex Mono', monospace; }
.hydra-tab.active { background: rgba(255,255,255,0.1); color: rgba(255,255,255,0.9); border-color: rgba(255,255,255,0.2); }
.hydra-exposure-summary { font-size: 12px; padding: 4px 0 8px; border-bottom: 1px solid rgba(255,255,255,0.05); margin-bottom: 6px; }
.hydra-score-low { color: #4caf50; }
.hydra-score-moderate { color: #ff9800; }
.hydra-score-high { color: #f44336; }
.hydra-score-extreme { color: #f44336; font-weight: 700; }
.hydra-row { display: grid; grid-template-columns: 60px 50px 60px 55px 55px 1fr; gap: 6px; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.03); font-size: 11px; font-family: 'IBM Plex Mono', monospace; align-items: center; }
.hydra-row.header { color: rgba(255,255,255,0.4); font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
.hydra-row-ticker { font-weight: 700; }
.hydra-convergence { margin-top: 8px; padding: 6px 10px; background: rgba(244,67,54,0.12); border: 1px solid rgba(244,67,54,0.3); border-radius: 4px; font-size: 12px; color: #f44336; animation: hydra-pulse 1.5s ease-in-out infinite; }
```

### JavaScript:
```javascript
let hydraPollingInterval = null;

function initHydra() {
    hydraPollingInterval = setInterval(fetchHydraData, 30000);
    fetchHydraData();
}

async function fetchHydraData() {
    try {
        const resp = await fetch('/api/hydra/exposure', { headers: { 'X-API-Key': API_KEY } });
        if (resp.ok) {
            const data = await resp.json();
            renderDefensiveView(data);
            const badge = document.getElementById('hydra-alert-badge');
            badge.style.display = data.alert ? 'flex' : 'none';
            if (data.alert) badge.textContent = data.high_risk_count;
        }
        const convResp = await fetch('/api/hydra/convergence', { headers: { 'X-API-Key': API_KEY } });
        if (convResp.ok) {
            const conv = await convResp.json();
            const el = document.getElementById('hydra-convergence');
            el.style.display = conv.convergence ? 'block' : 'none';
            if (conv.convergence) document.getElementById('hydra-convergence-text').textContent = conv.alert_message;
        }
    } catch (err) { console.error('Hydra error:', err); }
}

function renderDefensiveView(data) {
    document.getElementById('hydra-exposure-summary').innerHTML = data.alert
        ? `<span class="hydra-score-high">${data.alert_message}</span>`
        : '<span style="color:#4caf50">All positions: low squeeze risk</span>';
    const table = document.getElementById('hydra-defensive-table');
    let html = '<div class="hydra-row header"><span>Ticker</span><span>Score</span><span>SI%</span><span>DTC</span><span>Calls</span><span>Short P&L</span></div>';
    for (const p of data.positions) {
        const s = p.composite_score||0;
        const cls = s>=80?'extreme':s>=60?'high':s>=30?'moderate':'low';
        html += `<div class="hydra-row"><span class="hydra-row-ticker">${p.ticker}</span><span class="hydra-score-${cls}">${s}</span><span>${p.short_interest_pct||'—'}%</span><span>${p.days_to_cover||'—'}</span><span>${p.unusual_call_volume?'🔥':'—'}</span><span>${p.estimated_short_pnl||'—'}</span></div>`;
    }
    table.innerHTML = html;
}

async function switchHydraTab(tab) {
    document.getElementById('hydra-tab-defensive').classList.toggle('active', tab==='defensive');
    document.getElementById('hydra-tab-offensive').classList.toggle('active', tab==='offensive');
    document.getElementById('hydra-defensive').style.display = tab==='defensive'?'block':'none';
    document.getElementById('hydra-offensive').style.display = tab==='offensive'?'block':'none';
    if (tab==='offensive') {
        const resp = await fetch('/api/hydra/scores?limit=15&min_score=20', { headers: {'X-API-Key': API_KEY} });
        if (resp.ok) renderOffensiveView(await resp.json());
    }
}

function renderOffensiveView(data) {
    const table = document.getElementById('hydra-offensive-table');
    let html = '<div class="hydra-row header"><span>Ticker</span><span>Score</span><span>SI%</span><span>DTC</span><span>Calls</span><span>30d Chg</span></div>';
    for (const s of data.scores) {
        const sc = s.composite_score||0;
        const cls = sc>=80?'extreme':sc>=60?'high':sc>=30?'moderate':'low';
        const chg = s.price_change_30d_pct;
        html += `<div class="hydra-row"><span class="hydra-row-ticker">${s.ticker}</span><span class="hydra-score-${cls}">${sc}</span><span>${s.short_interest_pct||'—'}%</span><span>${s.days_to_cover||'—'}</span><span>${s.unusual_call_volume?'🔥':'—'}</span><span style="color:${chg>=0?'#4caf50':'#f44336'}">${chg!=null?((chg>=0?'+':'')+chg+'%'):'—'}</span></div>`;
    }
    table.innerHTML = html;
}

function toggleHydraPanel() {
    const body = document.getElementById('hydra-body');
    const toggle = document.getElementById('hydra-toggle');
    const vis = body.style.display !== 'none';
    body.style.display = vis ? 'none' : 'block';
    toggle.textContent = vis ? '▼' : '▲';
}

// Add initHydra() to dashboard init alongside initHermesFlash()
```

---

## STEP 8: Convergence Hook in Hermes Webhook

In the Hermes webhook handler (Brief 1), after storing the catalyst event, add a Hydra convergence check:

```python
# After storing catalyst_event, check Hydra convergence
try:
    pool = await get_postgres_client()
    squeezed = await pool.fetch("""
        SELECT ticker, composite_score FROM squeeze_scores
        WHERE composite_score >= 50 AND (ticker = $1 OR sector = $1)
        ORDER BY composite_score DESC LIMIT 3
    """, ticker)
    if squeezed:
        await pool.execute("""
            UPDATE catalyst_events
            SET trip_wire_status = trip_wire_status || $1
            WHERE id = $2
        """, json.dumps({"hydra_convergence": True, "squeeze_tickers": [dict(s)["ticker"] for s in squeezed]}), event_id)
        logger.info(f"HERMES+HYDRA CONVERGENCE: {ticker} + {[dict(s)['ticker'] for s in squeezed]}")
except Exception as e:
    logger.debug(f"Hydra convergence check failed: {e}")
```

---

## NOTES FOR CC

- `HYDRA_WATCHLIST` is hardcoded for v1. Should eventually move to `system_config` for easy editing.
- Polygon SI endpoint may return 403 on Starter tier. Code handles this — if no SI data, score weights shift toward flow + price action.
- `flow_events` table schema needs inspection. Adjust column names in Step 3 to match actual schema.
- Same for `unified_positions` — the defensive flagging needs to map position types (puts = short direction).
- ~30 Polygon API calls per Hydra refresh cycle. Verify this stays within Starter rate limits.
- Defensive mode is the default. Offensive tab is opt-in. Nick runs a bearish book — showing him long squeeze candidates should feel secondary.
