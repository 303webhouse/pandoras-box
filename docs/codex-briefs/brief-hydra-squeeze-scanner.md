# BRIEF: Hydra — Squeeze Scanner Module
## Priority: P1 | System: Railway + Agora UI
## Date: 2026-03-31
## Depends on: Hermes Flash (Briefs 1+2) for convergence alerts

---

## CONTEXT FOR CLAUDE CODE

Nick holds a bearish options book (puts on XLF, SMH, HYG, IYR, IWM). Today (3/31) a peace headline caused SPY to rally 2%+ and the most-shorted names ripped hardest. Nick had no visibility into which stocks were most vulnerable to short squeezes — meaning he couldn't see WHERE forced buying would hit hardest, or whether his OWN positions sat in the crosshairs.

Hydra is a squeeze vulnerability scanner with two modes:
1. **Defensive (default):** Cross-references Nick's open positions against squeeze risk scores. Warns him when his shorts are in dangerous territory.
2. **Offensive:** Ranks the top squeeze candidates for Bucket 2 tactical trades (quick 3-5 day momentum plays, max $200-300 each).

**Database: Railway Postgres.** Use the existing `get_postgres_client()` from `backend/database/postgres_client.py` for ALL database operations. NOT Supabase.

---

## STEP 1: Data Source — Short Interest Ingestion

Short interest data is the core fuel for squeeze scoring. There are multiple possible sources. **CC: try them in this priority order and use the first one that works.**

### Option A: Polygon Short Volume (check first)

Polygon may have daily short volume data. Check if this endpoint works with the Stocks Starter tier:
```
GET https://api.polygon.io/v2/shorts/{ticker}?apiKey={POLYGON_API_KEY}
```
Or:
```
GET https://api.polygon.io/v3/reference/shorts/{ticker}?apiKey={POLYGON_API_KEY}
```

**Test from within the app code** or via curl from Railway shell. If it returns data, use it. If it returns 403/401 (tier restriction), move to Option B.

### Option B: FINRA Short Interest via Polygon Reference (fallback)

Polygon's reference endpoints sometimes include short interest in ticker details:
```
GET https://api.polygon.io/v3/reference/tickers/{ticker}?apiKey={POLYGON_API_KEY}
```
Check if the response includes `short_interest` or `shares_short` fields.

### Option C: yfinance Fallback (last resort)

yfinance provides short interest data for free via the `info` property:
```python
import yfinance as yf
ticker = yf.Ticker("AAPL")
info = ticker.info
short_pct = info.get("shortPercentOfFloat", 0)  # e.g., 0.0312 = 3.12%
short_ratio = info.get("shortRatio", 0)  # days to cover
shares_short = info.get("sharesShort", 0)
short_prior = info.get("sharesShortPriorMonth", 0)
```
**This is the fallback.** yfinance is slow and rate-limited, but the short interest data is reliable and free. Rate limit: max 5-10 tickers per minute to avoid blocks. FINRA updates short interest bi-weekly (15th and end of month) so this data has a 2-week lag — acceptable for squeeze scoring since positions build over weeks, not hours.

### Implementation: `backend/data/short_interest.py`

```python
"""
Short Interest Data Provider
Tries Polygon first, falls back to yfinance.
Caches results in Redis (24h TTL) to avoid repeated API calls.
"""

import logging
import json
import os
from typing import Optional, Dict
from datetime import datetime, timezone

logger = logging.getLogger("short_interest")

POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")


async def get_short_interest(ticker: str) -> Optional[Dict]:
    """
    Get short interest data for a ticker.
    Returns: {
        "ticker": str,
        "short_pct_float": float,  # e.g., 15.2 means 15.2% of float is short
        "days_to_cover": float,    # short ratio
        "shares_short": int,
        "shares_short_prior": int, # prior month for trend
        "source": str,             # "polygon" or "yfinance"
        "updated_at": str          # ISO timestamp
    }
    """
    from database.redis_client import get_redis_client

    # Check Redis cache first (24h TTL)
    redis = await get_redis_client()
    if redis:
        cached = await redis.get(f"hydra:short:{ticker}")
        if cached:
            return json.loads(cached)

    # Try Polygon first
    data = await _try_polygon(ticker)

    # Fallback to yfinance
    if not data:
        data = await _try_yfinance(ticker)

    # Cache result
    if data and redis:
        await redis.set(f"hydra:short:{ticker}", json.dumps(data), ex=86400)  # 24h TTL

    return data


async def _try_polygon(ticker: str) -> Optional[Dict]:
    """Attempt to get short interest from Polygon API."""
    if not POLYGON_API_KEY:
        return None
    try:
        import httpx
        # CC: Test these endpoints and use whichever works at Stocks Starter tier
        # Option 1: Direct short interest endpoint
        # Option 2: Ticker details with short interest fields
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://api.polygon.io/v3/reference/tickers/{ticker}",
                params={"apiKey": POLYGON_API_KEY}
            )
            if resp.status_code == 200:
                result = resp.json().get("results", {})
                # Check if short interest fields exist in response
                if "share_class_shares_outstanding" in result:
                    # Polygon may include this data — CC verify field names
                    return {
                        "ticker": ticker,
                        "short_pct_float": result.get("short_percent_of_float", 0),
                        "days_to_cover": result.get("short_ratio", 0),
                        "shares_short": result.get("shares_short", 0),
                        "shares_short_prior": result.get("shares_short_prior_month", 0),
                        "source": "polygon",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
    except Exception as e:
        logger.debug(f"Polygon short interest failed for {ticker}: {e}")
    return None


async def _try_yfinance(ticker: str) -> Optional[Dict]:
    """Fallback: get short interest from yfinance."""
    try:
        import yfinance as yf
        import asyncio

        # yfinance is synchronous — run in thread pool
        def _fetch():
            t = yf.Ticker(ticker)
            info = t.info
            return {
                "ticker": ticker,
                "short_pct_float": round((info.get("shortPercentOfFloat") or 0) * 100, 2),
                "days_to_cover": round(info.get("shortRatio") or 0, 2),
                "shares_short": info.get("sharesShort") or 0,
                "shares_short_prior": info.get("sharesShortPriorMonth") or 0,
                "source": "yfinance",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }

        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, _fetch)
        return data
    except Exception as e:
        logger.warning(f"yfinance short interest failed for {ticker}: {e}")
    return None


async def get_short_interest_batch(tickers: list) -> Dict[str, Dict]:
    """
    Get short interest for multiple tickers.
    Rate-limits yfinance calls to avoid blocks.
    """
    import asyncio
    results = {}
    for ticker in tickers:
        data = await get_short_interest(ticker)
        if data:
            results[ticker] = data
        # Small delay between yfinance calls to avoid rate limiting
        await asyncio.sleep(0.5)
    return results
```

---

## STEP 2: Database — `squeeze_scores` Table

```sql
CREATE TABLE IF NOT EXISTS squeeze_scores (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker TEXT NOT NULL,
    -- Short interest data
    short_pct_float NUMERIC(8,2) DEFAULT 0,      -- % of float sold short
    days_to_cover NUMERIC(8,2) DEFAULT 0,         -- short ratio
    shares_short BIGINT DEFAULT 0,
    short_trend TEXT DEFAULT 'stable',             -- increasing, decreasing, stable
    -- Price action vs estimated short entry
    price_vs_short_entry_pct NUMERIC(8,2) DEFAULT 0,  -- positive = shorts underwater
    -- Flow data
    uw_call_flow_score NUMERIC(8,2) DEFAULT 0,    -- unusual call buying (0-100)
    uw_put_call_ratio NUMERIC(8,2) DEFAULT 0,     -- low ratio = more calls = squeeze fuel
    -- Sector context
    sector TEXT,
    sector_velocity NUMERIC(8,2) DEFAULT 0,       -- from Hermes if available
    -- Composite
    composite_score NUMERIC(8,2) DEFAULT 0,       -- 0-100 squeeze vulnerability
    squeeze_tier TEXT DEFAULT 'low',               -- low, moderate, high, extreme
    -- Position exposure (defensive mode)
    nick_has_position BOOLEAN DEFAULT FALSE,
    nick_position_direction TEXT,                  -- LONG, SHORT
    nick_position_id TEXT,                         -- FK to unified_positions
    -- Meta
    data_source TEXT DEFAULT 'yfinance',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_squeeze_scores_ticker ON squeeze_scores (ticker);
CREATE INDEX idx_squeeze_scores_composite ON squeeze_scores (composite_score DESC);
CREATE INDEX idx_squeeze_scores_exposure ON squeeze_scores (nick_has_position) WHERE nick_has_position = TRUE;
```

---

## STEP 3: Squeeze Scoring Engine

**File:** `backend/scanners/hydra_squeeze.py`

```python
"""
HYDRA — Squeeze Vulnerability Scanner

Composite scoring model that ranks tickers by short squeeze risk.
Two modes:
  - Defensive: warns when Nick's positions are in squeeze territory
  - Offensive: surfaces top squeeze candidates for Bucket 2 trades

Score weights:
  - Short Interest % of Float:       30%  (higher = more fuel)
  - Days to Cover:                    20%  (higher = harder to exit)
  - Price vs Est. Short Entry:        20%  (shorts underwater = pressure)
  - Unusual Call Flow (UW):           15%  (call buying amplifies squeeze)
  - Sector Velocity (Hermes):         15%  (sector catalyst = ignition)
"""

import logging
import json
from typing import Dict, List, Optional
from datetime import datetime, timezone

from database.postgres_client import get_postgres_client
from database.redis_client import get_redis_client
from data.short_interest import get_short_interest, get_short_interest_batch

logger = logging.getLogger("hydra")

# Scoring weights
WEIGHT_SHORT_PCT = 0.30
WEIGHT_DAYS_TO_COVER = 0.20
WEIGHT_PRICE_VS_ENTRY = 0.20
WEIGHT_CALL_FLOW = 0.15
WEIGHT_SECTOR_VELOCITY = 0.15

# Thresholds for tier classification
TIER_THRESHOLDS = {
    "extreme": 75,
    "high": 55,
    "moderate": 35,
    "low": 0
}


async def calculate_squeeze_score(ticker: str, sector_velocity: float = 0.0) -> Optional[Dict]:
    """
    Calculate composite squeeze vulnerability score for a single ticker.
    Returns full score breakdown or None if insufficient data.
    """
    # 1. Get short interest data
    short_data = await get_short_interest(ticker)
    if not short_data:
        logger.debug(f"HYDRA: No short interest data for {ticker}")
        return None

    short_pct = short_data.get("short_pct_float", 0)
    dtc = short_data.get("days_to_cover", 0)
    shares_short = short_data.get("shares_short", 0)
    shares_prior = short_data.get("shares_short_prior", 0)

    # Skip if negligible short interest
    if short_pct < 3.0:
        return None

    # 2. Determine short trend
    if shares_prior and shares_short:
        change_pct = ((shares_short - shares_prior) / shares_prior) * 100
        if change_pct > 5:
            short_trend = "increasing"
        elif change_pct < -5:
            short_trend = "decreasing"
        else:
            short_trend = "stable"
    else:
        short_trend = "unknown"

    # 3. Price vs estimated short entry
    price_vs_entry = await _estimate_short_pnl(ticker)

    # 4. UW call flow score
    call_flow_score, put_call_ratio = await _get_flow_score(ticker)

    # 5. Score each component (normalize to 0-100)
    score_short_pct = min(short_pct * 3.0, 100)        # 33%+ float short → max score
    score_dtc = min(dtc * 12.5, 100)                    # 8+ days to cover → max score
    score_price = min(max(price_vs_entry * 5, 0), 100)  # 20%+ underwater → max score
    score_flow = call_flow_score                         # Already 0-100
    score_sector = min(abs(sector_velocity) * 50, 100)  # 2%+ sector move → max score

    # 6. Composite weighted score
    composite = (
        score_short_pct * WEIGHT_SHORT_PCT +
        score_dtc * WEIGHT_DAYS_TO_COVER +
        score_price * WEIGHT_PRICE_VS_ENTRY +
        score_flow * WEIGHT_CALL_FLOW +
        score_sector * WEIGHT_SECTOR_VELOCITY
    )

    # 7. Tier classification
    tier = "low"
    for tier_name, threshold in sorted(TIER_THRESHOLDS.items(), key=lambda x: -x[1]):
        if composite >= threshold:
            tier = tier_name
            break

    return {
        "ticker": ticker,
        "composite_score": round(composite, 1),
        "squeeze_tier": tier,
        "short_pct_float": short_pct,
        "days_to_cover": dtc,
        "shares_short": shares_short,
        "short_trend": short_trend,
        "price_vs_short_entry_pct": round(price_vs_entry, 2),
        "uw_call_flow_score": round(call_flow_score, 1),
        "uw_put_call_ratio": round(put_call_ratio, 2),
        "sector_velocity": sector_velocity,
        "data_source": short_data.get("source", "unknown"),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }


async def _estimate_short_pnl(ticker: str) -> float:
    """
    Estimate how underwater the shorts are.
    Compares current price to estimated average short entry price.
    Uses 30-day VWAP as a rough proxy for when most shorts were added.

    Returns: positive number = shorts are losing money (squeeze pressure)
             negative number = shorts are profitable (no squeeze pressure)
    """
    try:
        import httpx
        import os
        api_key = os.environ.get("POLYGON_API_KEY")
        if not api_key:
            return 0.0

        async with httpx.AsyncClient(timeout=10.0) as client:
            # Get current price
            snap_resp = await client.get(
                f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}",
                params={"apiKey": api_key}
            )
            if snap_resp.status_code != 200:
                return 0.0

            snap = snap_resp.json()
            current_price = snap.get("ticker", {}).get("day", {}).get("c", 0)
            if not current_price:
                current_price = snap.get("ticker", {}).get("lastTrade", {}).get("p", 0)

            # Get 30-day SMA as proxy for average short entry
            sma_resp = await client.get(
                f"https://api.polygon.io/v1/indicators/sma/{ticker}",
                params={
                    "timespan": "day",
                    "window": 30,
                    "series_type": "close",
                    "order": "desc",
                    "limit": 1,
                    "apiKey": api_key
                }
            )
            if sma_resp.status_code == 200:
                sma_results = sma_resp.json().get("results", {}).get("values", [])
                if sma_results:
                    avg_entry = sma_results[0].get("value", current_price)
                    if avg_entry > 0:
                        # Positive = price above avg entry = shorts underwater
                        return ((current_price - avg_entry) / avg_entry) * 100

    except Exception as e:
        logger.debug(f"HYDRA short PnL estimate failed for {ticker}: {e}")

    return 0.0


async def _get_flow_score(ticker: str) -> tuple:
    """
    Get unusual call flow score from UW data in Redis.
    Returns: (call_flow_score 0-100, put_call_ratio)
    """
    try:
        redis = await get_redis_client()
        if not redis:
            return 0.0, 1.0

        # Check UW flow data for this ticker
        flow_key = f"uw:flow:{ticker}"
        flow_data = await redis.get(flow_key)
        if not flow_data:
            return 0.0, 1.0

        flow = json.loads(flow_data)

        # Extract call vs put flow
        total_calls = flow.get("total_call_premium", 0)
        total_puts = flow.get("total_put_premium", 0)
        call_count = flow.get("call_count", 0)
        put_count = flow.get("put_count", 0)
        bullish_count = flow.get("bullish_count", 0)
        total_count = flow.get("total_count", 1)

        # Put/call ratio (lower = more bullish = more squeeze fuel)
        if total_puts > 0:
            pc_ratio = total_calls / total_puts
        else:
            pc_ratio = 2.0 if total_calls > 0 else 1.0

        # Call flow score: combination of call dominance and bullish sentiment
        call_dominance = (call_count / max(total_count, 1)) * 100
        bullish_pct = (bullish_count / max(total_count, 1)) * 100

        # Score: heavy call flow + bullish sentiment = squeeze fuel
        score = (call_dominance * 0.5 + bullish_pct * 0.5)

        return min(score, 100), round(pc_ratio, 2)

    except Exception as e:
        logger.debug(f"HYDRA flow score failed for {ticker}: {e}")
        return 0.0, 1.0


# === BATCH OPERATIONS ===

async def scan_squeeze_universe(universe: list = None) -> List[Dict]:
    """
    Scan a universe of tickers for squeeze vulnerability.
    Default universe: most-shorted names + any tickers in Nick's positions.

    Returns: List of score dicts sorted by composite_score descending.
    """
    if not universe:
        universe = await _build_scan_universe()

    scores = []
    for ticker in universe:
        score = await calculate_squeeze_score(ticker)
        if score:
            scores.append(score)

    # Sort by composite score descending
    scores.sort(key=lambda x: x["composite_score"], reverse=True)
    return scores


async def _build_scan_universe() -> list:
    """
    Build the ticker universe for squeeze scanning.
    Sources:
    1. All tickers in Nick's open positions (defensive)
    2. Tickers with active UW flow data (real-time signal)
    3. A curated watchlist of commonly-shorted names
    """
    universe = set()

    # 1. Nick's open positions
    try:
        pool = await get_postgres_client()
        rows = await pool.fetch(
            "SELECT DISTINCT ticker FROM unified_positions WHERE status = 'OPEN'"
        )
        for row in rows:
            universe.add(row["ticker"])
    except Exception as e:
        logger.warning(f"HYDRA: Failed to get positions: {e}")

    # 2. Active UW flow tickers
    try:
        redis = await get_redis_client()
        if redis:
            cursor = b"0"
            while True:
                cursor, keys = await redis.scan(cursor, match="uw:flow:*", count=100)
                for key in keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    if key_str not in ("uw:flow:recent",):
                        ticker = key_str.replace("uw:flow:", "")
                        if ticker.isalpha() and len(ticker) <= 5:
                            universe.add(ticker.upper())
                if cursor == b"0" or cursor == 0:
                    break
    except Exception as e:
        logger.debug(f"HYDRA: Failed to get UW flow tickers: {e}")

    # 3. Curated commonly-shorted ETFs/stocks relevant to Nick's thesis
    curated = [
        # Nick's position tickers (ensure coverage even if DB query fails)
        "XLF", "SMH", "HYG", "IYR", "IWM", "IBIT", "COIN",
        # Commonly shorted / high short interest names
        "TSLA", "CVNA", "MSTR", "GME", "AMC", "RIVN",
        "UPST", "SOFI", "HOOD", "LCID", "PLUG", "SNAP",
        "BYND", "CHPT", "SPCE", "WISH",
        # High-beta tech susceptible to squeeze on relief rally
        "ARKK", "ROKU", "DKNG", "CRWD", "NET", "SNOW"
    ]
    universe.update(curated)

    return list(universe)


async def check_position_exposure() -> List[Dict]:
    """
    DEFENSIVE MODE: Cross-reference Nick's open positions against squeeze scores.
    Returns positions sorted by squeeze risk (highest first).
    """
    pool = await get_postgres_client()
    positions = await pool.fetch("""
        SELECT position_id, ticker, direction, structure, status,
               entry_price, quantity, cost_basis, max_loss, max_profit,
               expiry, long_strike, short_strike, account
        FROM unified_positions
        WHERE status = 'OPEN'
    """)

    exposure = []
    for pos in positions:
        ticker = pos["ticker"]
        score_data = await calculate_squeeze_score(ticker)
        if not score_data:
            continue

        # Determine if this position is vulnerable
        direction = pos["direction"] or ""
        is_short = direction.upper() in ("SHORT",) or "put" in (pos["structure"] or "").lower()

        # Short positions are vulnerable to squeezes
        # Long positions benefit from squeezes
        if is_short:
            risk_level = score_data["squeeze_tier"]
        else:
            risk_level = "beneficial"  # Squeeze helps longs

        exposure.append({
            **score_data,
            "nick_has_position": True,
            "nick_position_id": pos["position_id"],
            "nick_position_direction": direction,
            "nick_position_structure": pos["structure"],
            "nick_position_expiry": str(pos["expiry"]) if pos["expiry"] else None,
            "nick_position_cost_basis": float(pos["cost_basis"]) if pos["cost_basis"] else None,
            "position_risk_level": risk_level
        })

    # Sort: shorts with highest squeeze risk first
    exposure.sort(key=lambda x: (
        0 if x["position_risk_level"] in ("extreme", "high") else 1,
        -x["composite_score"]
    ))

    return exposure


async def persist_scores(scores: List[Dict]):
    """Save squeeze scores to database for historical tracking."""
    pool = await get_postgres_client()
    for score in scores:
        await pool.execute("""
            INSERT INTO squeeze_scores (
                ticker, short_pct_float, days_to_cover, shares_short,
                short_trend, price_vs_short_entry_pct,
                uw_call_flow_score, uw_put_call_ratio,
                sector_velocity, composite_score, squeeze_tier,
                nick_has_position, nick_position_direction, nick_position_id,
                data_source, updated_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,NOW())
            ON CONFLICT (ticker) DO UPDATE SET
                short_pct_float = $2, days_to_cover = $3, shares_short = $4,
                short_trend = $5, price_vs_short_entry_pct = $6,
                uw_call_flow_score = $7, uw_put_call_ratio = $8,
                sector_velocity = $9, composite_score = $10, squeeze_tier = $11,
                nick_has_position = $12, nick_position_direction = $13,
                nick_position_id = $14, data_source = $15, updated_at = NOW()
        """,
            score["ticker"],
            score.get("short_pct_float", 0),
            score.get("days_to_cover", 0),
            score.get("shares_short", 0),
            score.get("short_trend", "unknown"),
            score.get("price_vs_short_entry_pct", 0),
            score.get("uw_call_flow_score", 0),
            score.get("uw_put_call_ratio", 1.0),
            score.get("sector_velocity", 0),
            score.get("composite_score", 0),
            score.get("squeeze_tier", "low"),
            score.get("nick_has_position", False),
            score.get("nick_position_direction"),
            score.get("nick_position_id"),
            score.get("data_source", "unknown")
        )
```

---

## STEP 4: API Endpoints

**File:** `backend/api/hydra.py` (new file)

```python
"""
HYDRA Squeeze Scanner API Endpoints

- GET /hydra/scores         — Top squeeze candidates (offensive mode)
- GET /hydra/exposure       — Nick's position exposure (defensive mode)
- GET /hydra/convergence    — Hermes + Hydra convergence check
- POST /hydra/refresh       — Trigger a full rescan
"""

from fastapi import APIRouter, HTTPException, Query
import logging

from scanners.hydra_squeeze import (
    scan_squeeze_universe,
    check_position_exposure,
    calculate_squeeze_score,
    persist_scores
)
from database.postgres_client import get_postgres_client

logger = logging.getLogger("hydra_api")
router = APIRouter(prefix="/hydra", tags=["Hydra Squeeze Scanner"])


@router.get("/scores")
async def get_squeeze_scores(
    limit: int = Query(default=15, le=50),
    min_score: float = Query(default=30.0, description="Minimum composite score"),
    tier: str = Query(default=None, description="Filter by tier: extreme, high, moderate")
):
    """
    OFFENSIVE MODE: Top squeeze candidates ranked by composite score.
    Use for Bucket 2 tactical trade ideas.
    """
    pool = await get_postgres_client()
    query = """
        SELECT * FROM squeeze_scores
        WHERE composite_score >= $1
    """
    params = [min_score]

    if tier:
        query += " AND squeeze_tier = $2"
        params.append(tier)

    query += " ORDER BY composite_score DESC LIMIT $" + str(len(params) + 1)
    params.append(limit)

    rows = await pool.fetch(query, *params)

    if not rows:
        return {"scores": [], "message": "No squeeze candidates above threshold. Run /hydra/refresh to rescan."}

    return {
        "scores": [dict(r) for r in rows],
        "count": len(rows),
        "min_score_filter": min_score
    }


@router.get("/exposure")
async def get_position_exposure():
    """
    DEFENSIVE MODE: Cross-reference Nick's open positions against squeeze risk.
    Returns positions with squeeze vulnerability, highest risk first.
    """
    exposure = await check_position_exposure()

    # Count risk levels
    risk_summary = {
        "extreme": sum(1 for e in exposure if e.get("position_risk_level") == "extreme"),
        "high": sum(1 for e in exposure if e.get("position_risk_level") == "high"),
        "moderate": sum(1 for e in exposure if e.get("position_risk_level") == "moderate"),
        "beneficial": sum(1 for e in exposure if e.get("position_risk_level") == "beneficial"),
    }

    # Generate warning if any positions are at high+ risk
    warning = None
    if risk_summary["extreme"] > 0:
        extreme_tickers = [e["ticker"] for e in exposure if e.get("position_risk_level") == "extreme"]
        warning = f"SQUEEZE WARNING: {', '.join(extreme_tickers)} at EXTREME squeeze risk. Consider reducing exposure."
    elif risk_summary["high"] > 0:
        high_tickers = [e["ticker"] for e in exposure if e.get("position_risk_level") == "high"]
        warning = f"Elevated squeeze risk on: {', '.join(high_tickers)}. Monitor closely."

    return {
        "exposure": exposure,
        "risk_summary": risk_summary,
        "warning": warning,
        "positions_checked": len(exposure)
    }


@router.get("/convergence")
async def check_convergence():
    """
    CONVERGENCE CHECK: Cross-reference active Hermes catalyst events
    with elevated squeeze scores. When both fire = highest urgency alert.
    """
    pool = await get_postgres_client()

    # Get recent undismissed Hermes events (last 30 min)
    hermes_events = await pool.fetch("""
        SELECT id, trigger_ticker, tier, trigger_move_pct, correlated_tickers,
               headline_summary, catalyst_category, created_at
        FROM catalyst_events
        WHERE dismissed = FALSE
        AND created_at > NOW() - INTERVAL '30 minutes'
        ORDER BY created_at DESC
        LIMIT 5
    """)

    if not hermes_events:
        return {"convergence": False, "message": "No active Hermes events"}

    # Get tickers involved in Hermes events
    hermes_tickers = set()
    for event in hermes_events:
        hermes_tickers.add(event["trigger_ticker"])
        if event["correlated_tickers"]:
            corr = event["correlated_tickers"]
            if isinstance(corr, str):
                corr = json.loads(corr)
            for c in corr:
                if isinstance(c, dict):
                    hermes_tickers.add(c.get("ticker", ""))
                elif isinstance(c, str):
                    hermes_tickers.add(c)

    # Check squeeze scores for those tickers
    high_squeeze = await pool.fetch("""
        SELECT ticker, composite_score, squeeze_tier
        FROM squeeze_scores
        WHERE ticker = ANY($1)
        AND composite_score >= 50
    """, list(hermes_tickers))

    if high_squeeze:
        convergence_tickers = [r["ticker"] for r in high_squeeze]
        return {
            "convergence": True,
            "convergence_tickers": convergence_tickers,
            "hermes_events": [dict(e) for e in hermes_events[:3]],
            "squeeze_scores": [dict(s) for s in high_squeeze],
            "alert": f"CONVERGENCE: Catalyst event + high squeeze risk on {', '.join(convergence_tickers)}. Forced buying likely."
        }

    return {"convergence": False, "hermes_active": len(hermes_events), "high_squeeze_matches": 0}


@router.post("/refresh")
async def refresh_squeeze_scores():
    """
    Trigger a full rescan of the squeeze universe.
    Usually called by cron, but can be triggered manually.
    """
    logger.info("HYDRA: Manual refresh triggered")
    scores = await scan_squeeze_universe()
    await persist_scores(scores)

    tier_counts = {}
    for s in scores:
        t = s.get("squeeze_tier", "low")
        tier_counts[t] = tier_counts.get(t, 0) + 1

    return {
        "status": "refreshed",
        "tickers_scanned": len(scores),
        "tier_breakdown": tier_counts,
        "top_5": [{"ticker": s["ticker"], "score": s["composite_score"], "tier": s["squeeze_tier"]} for s in scores[:5]]
    }
```

**Router registration — add to main app:**
```python
from api.hydra import router as hydra_router
app.include_router(hydra_router, prefix="/api")
```

---

## STEP 5: Cron Job — Scheduled Refresh

Add a scheduled task that refreshes squeeze scores at market open and every 30 minutes during market hours. Wire this into the existing cron/scheduler pattern used by the committee pipeline.

**If the app uses APScheduler or similar:**
```python
# Add to scheduler setup
scheduler.add_job(
    hydra_refresh_job,
    'cron',
    day_of_week='mon-fri',
    hour='9-16',  # ET market hours
    minute='0,30',
    timezone='America/New_York',
    id='hydra_squeeze_refresh'
)

async def hydra_refresh_job():
    from scanners.hydra_squeeze import scan_squeeze_universe, persist_scores
    scores = await scan_squeeze_universe()
    await persist_scores(scores)
    logger.info(f"HYDRA CRON: Refreshed {len(scores)} squeeze scores")
```

**If the app uses simple cron endpoints** (hit via external cron or Railway cron):
```python
@router.post("/hydra/cron")
async def hydra_cron_trigger(request: Request):
    """Called by Railway cron to refresh squeeze scores."""
    # Auth check
    api_key = request.headers.get("X-API-Key")
    if api_key != os.environ.get("PIVOT_API_KEY"):
        raise HTTPException(status_code=401)
    return await refresh_squeeze_scores()
```

---

## STEP 6: Agora Frontend — Hydra Panel

Add a new collapsible panel below the portfolio view in Agora.

### HTML (add to dashboard):

```html
<!-- Hydra Squeeze Monitor Panel -->
<div class="hydra-panel" id="hydra-panel">
    <div class="hydra-header" onclick="toggleHydraPanel()">
        <span class="hydra-title">🐍 HYDRA Squeeze Monitor</span>
        <span class="hydra-warning-badge" id="hydra-warning-badge" style="display:none;">!</span>
        <span class="hydra-toggle" id="hydra-toggle">▶</span>
    </div>
    <div class="hydra-body" id="hydra-body" style="display:none;">
        <!-- Tab bar -->
        <div class="hydra-tabs">
            <button class="hydra-tab active" onclick="switchHydraTab('defensive')" id="hydra-tab-defensive">🛡 Defensive</button>
            <button class="hydra-tab" onclick="switchHydraTab('offensive')" id="hydra-tab-offensive">⚔ Offensive</button>
        </div>

        <!-- Defensive tab content -->
        <div class="hydra-tab-content" id="hydra-defensive-content">
            <div id="hydra-exposure-warning" class="hydra-exposure-warning" style="display:none;"></div>
            <table class="hydra-table" id="hydra-exposure-table">
                <thead>
                    <tr>
                        <th>Ticker</th>
                        <th>Your Position</th>
                        <th>Short %</th>
                        <th>DTC</th>
                        <th>Score</th>
                        <th>Risk</th>
                    </tr>
                </thead>
                <tbody id="hydra-exposure-tbody"></tbody>
            </table>
        </div>

        <!-- Offensive tab content -->
        <div class="hydra-tab-content" id="hydra-offensive-content" style="display:none;">
            <table class="hydra-table" id="hydra-scores-table">
                <thead>
                    <tr>
                        <th>Ticker</th>
                        <th>Short %</th>
                        <th>DTC</th>
                        <th>Shorts P&L</th>
                        <th>Call Flow</th>
                        <th>Score</th>
                        <th>Tier</th>
                    </tr>
                </thead>
                <tbody id="hydra-scores-tbody"></tbody>
            </table>
        </div>

        <!-- Convergence alert -->
        <div id="hydra-convergence" class="hydra-convergence" style="display:none;"></div>

        <div class="hydra-footer">
            <span id="hydra-last-updated" class="hydra-timestamp"></span>
            <button class="hydra-refresh-btn" onclick="refreshHydra()">↻ Refresh</button>
        </div>
    </div>
</div>
```

### CSS:

```css
/* === HYDRA SQUEEZE MONITOR === */
.hydra-panel {
    margin-top: 8px;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 4px;
    background: rgba(0,0,0,0.2);
}

.hydra-header {
    display: flex;
    align-items: center;
    padding: 8px 12px;
    cursor: pointer;
    user-select: none;
}
.hydra-header:hover { background: rgba(255,255,255,0.03); }

.hydra-title {
    font-size: 13px;
    font-weight: 600;
    font-family: 'IBM Plex Mono', monospace;
    color: rgba(255,255,255,0.8);
    flex: 1;
}

.hydra-warning-badge {
    background: #f44336;
    color: #fff;
    border-radius: 50%;
    width: 18px;
    height: 18px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 700;
    margin-right: 8px;
    animation: hermes-badge-pulse 1.5s ease-in-out infinite;
}

.hydra-toggle { font-size: 10px; opacity: 0.5; }

.hydra-body { padding: 0 12px 12px; }

.hydra-tabs {
    display: flex;
    gap: 4px;
    margin-bottom: 8px;
    padding-top: 4px;
}
.hydra-tab {
    padding: 4px 12px;
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 3px;
    background: none;
    color: rgba(255,255,255,0.5);
    font-size: 12px;
    cursor: pointer;
}
.hydra-tab.active {
    background: rgba(255,255,255,0.08);
    color: rgba(255,255,255,0.9);
    border-color: rgba(255,255,255,0.2);
}

.hydra-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    font-family: 'IBM Plex Mono', monospace;
}
.hydra-table th {
    text-align: left;
    padding: 4px 6px;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    color: rgba(255,255,255,0.4);
    font-weight: 500;
    font-size: 10px;
    text-transform: uppercase;
}
.hydra-table td {
    padding: 5px 6px;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    color: rgba(255,255,255,0.75);
}

.hydra-tier-extreme { color: #f44336; font-weight: 700; }
.hydra-tier-high { color: #ff9800; font-weight: 600; }
.hydra-tier-moderate { color: #ffc107; }
.hydra-tier-low { color: rgba(255,255,255,0.4); }

.hydra-exposure-warning {
    padding: 6px 10px;
    margin-bottom: 8px;
    border-radius: 3px;
    font-size: 12px;
    background: rgba(244, 67, 54, 0.12);
    border: 1px solid rgba(244, 67, 54, 0.3);
    color: #f44336;
}

.hydra-convergence {
    margin-top: 8px;
    padding: 6px 10px;
    border-radius: 3px;
    font-size: 12px;
    background: rgba(156, 39, 176, 0.12);
    border: 1px solid rgba(156, 39, 176, 0.3);
    color: #ce93d8;
    font-weight: 600;
}

.hydra-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 8px;
    padding-top: 6px;
    border-top: 1px solid rgba(255,255,255,0.05);
}
.hydra-timestamp { font-size: 10px; opacity: 0.3; }
.hydra-refresh-btn {
    background: none;
    border: 1px solid rgba(255,255,255,0.1);
    color: rgba(255,255,255,0.5);
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 3px;
    cursor: pointer;
}
.hydra-refresh-btn:hover { background: rgba(255,255,255,0.05); }
```

### JavaScript:

```javascript
// === HYDRA SQUEEZE MONITOR — Frontend Logic ===

let hydraCurrentTab = 'defensive';

function initHydra() {
    // Load defensive view on init
    fetchHydraExposure();
    // Refresh every 5 minutes
    setInterval(fetchHydraExposure, 300000);
    // Check convergence every 30 seconds (lightweight)
    setInterval(checkHydraConvergence, 30000);
}

function toggleHydraPanel() {
    const body = document.getElementById('hydra-body');
    const toggle = document.getElementById('hydra-toggle');
    if (body.style.display === 'none') {
        body.style.display = 'block';
        toggle.textContent = '▼';
    } else {
        body.style.display = 'none';
        toggle.textContent = '▶';
    }
}

function switchHydraTab(tab) {
    hydraCurrentTab = tab;
    document.getElementById('hydra-tab-defensive').classList.toggle('active', tab === 'defensive');
    document.getElementById('hydra-tab-offensive').classList.toggle('active', tab === 'offensive');
    document.getElementById('hydra-defensive-content').style.display = tab === 'defensive' ? 'block' : 'none';
    document.getElementById('hydra-offensive-content').style.display = tab === 'offensive' ? 'block' : 'none';

    if (tab === 'offensive') {
        fetchHydraScores();
    }
}

async function fetchHydraExposure() {
    try {
        const resp = await fetch('/api/hydra/exposure', { headers: { 'X-API-Key': API_KEY } });
        if (!resp.ok) return;
        const data = await resp.json();

        // Warning banner
        const warningEl = document.getElementById('hydra-exposure-warning');
        if (data.warning) {
            warningEl.textContent = data.warning;
            warningEl.style.display = 'block';
            // Show warning badge on collapsed header
            document.getElementById('hydra-warning-badge').style.display = 'flex';
        } else {
            warningEl.style.display = 'none';
            document.getElementById('hydra-warning-badge').style.display = 'none';
        }

        // Table
        const tbody = document.getElementById('hydra-exposure-tbody');
        tbody.innerHTML = '';
        (data.exposure || []).forEach(item => {
            const row = document.createElement('tr');
            const tierClass = `hydra-tier-${item.position_risk_level === 'beneficial' ? 'low' : item.squeeze_tier}`;
            row.innerHTML = `
                <td style="font-weight:600">${item.ticker}</td>
                <td>${item.nick_position_structure || item.nick_position_direction || '—'}</td>
                <td>${item.short_pct_float}%</td>
                <td>${item.days_to_cover}</td>
                <td>${item.composite_score}</td>
                <td class="${tierClass}">${item.position_risk_level === 'beneficial' ? '✓ Long' : item.squeeze_tier.toUpperCase()}</td>
            `;
            tbody.appendChild(row);
        });

        document.getElementById('hydra-last-updated').textContent =
            `Updated: ${new Date().toLocaleTimeString()}`;

    } catch (err) {
        console.error('Hydra exposure fetch error:', err);
    }
}

async function fetchHydraScores() {
    try {
        const resp = await fetch('/api/hydra/scores?limit=15&min_score=25', { headers: { 'X-API-Key': API_KEY } });
        if (!resp.ok) return;
        const data = await resp.json();

        const tbody = document.getElementById('hydra-scores-tbody');
        tbody.innerHTML = '';
        (data.scores || []).forEach(item => {
            const row = document.createElement('tr');
            const tierClass = `hydra-tier-${item.squeeze_tier}`;
            const shortsPnl = item.price_vs_short_entry_pct || 0;
            const pnlColor = shortsPnl > 0 ? '#f44336' : '#4caf50';
            const pnlSign = shortsPnl >= 0 ? '+' : '';
            row.innerHTML = `
                <td style="font-weight:600">${item.ticker}</td>
                <td>${item.short_pct_float}%</td>
                <td>${item.days_to_cover}</td>
                <td style="color:${pnlColor}">${pnlSign}${shortsPnl.toFixed(1)}%</td>
                <td>${item.uw_call_flow_score.toFixed(0)}</td>
                <td style="font-weight:700">${item.composite_score.toFixed(0)}</td>
                <td class="${tierClass}">${item.squeeze_tier.toUpperCase()}</td>
            `;
            tbody.appendChild(row);
        });

    } catch (err) {
        console.error('Hydra scores fetch error:', err);
    }
}

async function checkHydraConvergence() {
    try {
        const resp = await fetch('/api/hydra/convergence', { headers: { 'X-API-Key': API_KEY } });
        if (!resp.ok) return;
        const data = await resp.json();

        const el = document.getElementById('hydra-convergence');
        if (data.convergence) {
            el.textContent = data.alert;
            el.style.display = 'block';
        } else {
            el.style.display = 'none';
        }
    } catch (err) {
        console.error('Hydra convergence check error:', err);
    }
}

async function refreshHydra() {
    const btn = document.querySelector('.hydra-refresh-btn');
    btn.textContent = '↻ Scanning...';
    btn.disabled = true;
    try {
        await fetch('/api/hydra/refresh', { method: 'POST', headers: { 'X-API-Key': API_KEY } });
        // Reload current tab data
        if (hydraCurrentTab === 'defensive') {
            await fetchHydraExposure();
        } else {
            await fetchHydraScores();
        }
    } catch (err) {
        console.error('Hydra refresh error:', err);
    }
    btn.textContent = '↻ Refresh';
    btn.disabled = false;
}

// Add to dashboard init:
// initHydra();
```

---

## STEP 7: Convergence Integration with Hermes

In the Hermes webhook handler (`routes/hermes.py` from Brief 1), after storing the catalyst event and triggering the VPS, also check Hydra convergence:

**Find/replace anchor:** After the VPS trigger section in the `hermes_webhook` function, add:

```python
    # Check Hydra convergence — are any high-squeeze tickers involved in this event?
    try:
        from scanners.hydra_squeeze import calculate_squeeze_score
        involved_tickers = [ticker] + [b["ticker"] for b in correlated]
        for t in involved_tickers:
            score = await calculate_squeeze_score(t, sector_velocity=sector_velocity.get(t, 0))
            if score and score["composite_score"] >= 50:
                logger.info(f"HERMES+HYDRA CONVERGENCE: {t} catalyst + squeeze score {score['composite_score']}")
                # Update the catalyst event with convergence flag
                # CC: Add a convergence_flags JSONB column to catalyst_events if needed
    except Exception as e:
        logger.debug(f"Hydra convergence check in Hermes failed: {e}")
```

---

## NOTES FOR CC

- **Database is Railway Postgres.** Use `get_postgres_client()` everywhere. Not Supabase.
- **yfinance is the likely data source for short interest.** Polygon Stocks Starter probably doesn't include short interest endpoints. Test Polygon first but expect to fall back to yfinance. The code handles both transparently.
- **yfinance rate limiting is real.** The `get_short_interest_batch()` function has a 0.5s delay between calls. The scan universe is ~30-40 tickers, so a full scan takes ~15-20 seconds. This is fine for a cron that runs every 30 minutes.
- **Redis caching (24h TTL) prevents redundant yfinance calls.** Short interest data only updates bi-weekly from FINRA anyway, so caching aggressively is correct behavior.
- **The curated universe list in `_build_scan_universe()`** includes Nick's position tickers + commonly-shorted names. This list is hardcoded for now — can be moved to system_config later if it needs to be editable.
- **The convergence check is lightweight** — it just queries the `squeeze_scores` and `catalyst_events` tables. The 30-second polling interval in the frontend is fine.
- **The "Shorts P&L" column** uses 30-day SMA as a proxy for average short entry price. This is rough but directionally correct. Shorts added in the last month at higher prices will show as "underwater" when the stock rallies.
- **The defensive tab is the default** when the panel opens. This is intentional — Nick's primary use case is protecting his positions, not chasing squeeze longs.
- **The `position_risk_level` = "beneficial"** for long positions means a squeeze would help those positions. This prevents false alarms on Nick's long plays.
