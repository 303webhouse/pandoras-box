# BRIEF: Hydra Squeeze Scanner + Lightning Cards
## Priority: P1 | System: Railway + Agora Frontend
## Date: 2026-03-31
## Depends on: Brief 1 (Hermes Flash Core) deployed

---

## CONTEXT FOR CLAUDE CODE

Hydra is a squeeze detection system that monitors which stocks have the highest short squeeze vulnerability. Lightning Cards are the action layer — when a Hermes catalyst event coincides with elevated Hydra squeeze scores, the system generates a special trade idea card with a pre-populated options structure, real-time asymmetry math, and a visual treatment that screams "time-sensitive."

Lightning Cards render in the **existing Insights feed** (`#tradeSignals` container in `frontend/app.js`), **pinned to the top** above normal signal cards. They use a separate `createLightningCard()` function, not the existing `createSignalCard()`.

**Database is Railway Postgres** — use `get_postgres_client()` from `backend/database/postgres_client.py` for all DB operations. NOT Supabase.

---

## STEP 1: Database Tables

Run against Railway Postgres via the existing `init_database()` pattern or a migration script:

```sql
-- Hydra squeeze scores — refreshed intraday
CREATE TABLE IF NOT EXISTS squeeze_scores (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker TEXT NOT NULL,
    short_interest_pct NUMERIC(6,2),          -- Short interest as % of float
    days_to_cover NUMERIC(6,2),               -- Short interest / avg daily volume
    estimated_short_pnl NUMERIC(8,2),         -- Estimated P&L of short sellers (negative = underwater)
    uw_call_flow_score NUMERIC(4,2),          -- 0-100, from UW flow data
    sector_velocity NUMERIC(6,2),             -- From Hermes sector snapshot
    composite_score NUMERIC(5,2),             -- Weighted composite 0-100
    short_volume_ratio NUMERIC(4,3),          -- Daily short volume / total volume
    market_cap_millions NUMERIC(12,2),
    avg_daily_volume BIGINT,
    data_source TEXT DEFAULT 'polygon',        -- polygon, finra, manual
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ticker)
);

CREATE INDEX idx_squeeze_scores_composite ON squeeze_scores (composite_score DESC);
CREATE INDEX idx_squeeze_scores_ticker ON squeeze_scores (ticker);

-- Lightning Cards — convergence events that generate trade ideas
CREATE TABLE IF NOT EXISTS lightning_cards (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    catalyst_event_id UUID REFERENCES catalyst_events(id),
    ticker TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('bullish', 'bearish')),
    squeeze_composite_score NUMERIC(5,2),

    -- Options structure
    options_strike NUMERIC(10,2),
    options_expiry DATE,
    options_type TEXT CHECK (options_type IN ('call', 'put')),
    options_premium NUMERIC(8,2),
    options_bid NUMERIC(8,2),
    options_ask NUMERIC(8,2),
    options_bid_ask_spread_pct NUMERIC(5,2),
    options_open_interest INTEGER,
    options_volume INTEGER,
    options_volume_vs_avg NUMERIC(6,2),       -- Multiple of avg volume

    -- Asymmetry math
    max_loss NUMERIC(8,2),                    -- Premium paid (Bucket 2 cap)
    breakeven_price NUMERIC(10,2),
    payoff_1_sigma NUMERIC(8,2),              -- Estimated payoff at 1 std dev move
    payoff_2_sigma NUMERIC(8,2),              -- Estimated payoff at 2 std dev move
    risk_reward_ratio TEXT,                    -- e.g., "1:3 to 1:6"

    -- Bucket 2 enforcement
    bucket2_slots_used INTEGER DEFAULT 0,
    bucket2_capital_deployed NUMERIC(8,2) DEFAULT 0,
    bucket2_blocked BOOLEAN DEFAULT FALSE,
    bucket2_block_reason TEXT,

    -- Conflict detection
    conflict_detected BOOLEAN DEFAULT FALSE,
    conflict_position_id TEXT,
    conflict_details TEXT,                     -- e.g., "HYG $72/$68 put spread"

    -- Thesis integration
    catalyst_headline TEXT,
    catalyst_category TEXT,
    thesis_impact TEXT,

    -- Lifecycle
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'dismissed', 'acted_on', 'expired')),
    acted_on_at TIMESTAMPTZ,
    expired_at TIMESTAMPTZ,
    -- Post-mortem (populated after expiry)
    postmortem_price_at_generation NUMERIC(10,2),
    postmortem_price_at_expiry NUMERIC(10,2),
    postmortem_actual_move_pct NUMERIC(6,2),
    postmortem_estimated_missed_pnl NUMERIC(8,2),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_lightning_cards_status ON lightning_cards (status);
CREATE INDEX idx_lightning_cards_created ON lightning_cards (created_at DESC);
```

---

## STEP 2: Hydra Squeeze Scoring Engine

New file: `backend/scanners/hydra.py`

```python
# === HYDRA SQUEEZE SCANNER ===
# Scores tickers by short squeeze vulnerability.
# Feeds into Lightning Card generation when Hermes catalyst events align.

import logging
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List

logger = logging.getLogger("hydra")

POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")

# === COMPOSITE SCORE WEIGHTS ===
WEIGHTS = {
    "short_interest_pct": 0.30,      # Higher short interest = more squeeze fuel
    "days_to_cover": 0.20,           # Higher DTC = harder for shorts to exit
    "estimated_short_pnl": 0.20,     # Shorts deeper underwater = more pressure
    "uw_call_flow_score": 0.15,      # Unusual call buying amplifies squeeze
    "sector_velocity": 0.15          # Sector-wide catalyst = squeeze trigger
}


async def refresh_squeeze_scores(pool, tickers: Optional[List[str]] = None):
    """
    Refresh squeeze scores for all tracked tickers or a specific list.
    Called by cron (daily + intraday) and on-demand by Hermes convergence check.
    """
    if tickers is None:
        # Default watchlist: high-short-interest names + tickers from Nick's book
        # This list should be configurable via system_config
        tickers = await get_squeeze_watchlist(pool)

    for ticker in tickers:
        try:
            score_data = await calculate_squeeze_score(pool, ticker)
            if score_data:
                await upsert_squeeze_score(pool, ticker, score_data)
        except Exception as e:
            logger.error(f"HYDRA: Error scoring {ticker}: {e}")

    logger.info(f"HYDRA: Refreshed scores for {len(tickers)} tickers")


async def calculate_squeeze_score(pool, ticker: str) -> Optional[Dict]:
    """
    Calculate composite squeeze score for a single ticker.
    Pulls data from Polygon + internal flow data.
    """
    import httpx

    if not POLYGON_API_KEY:
        logger.error("HYDRA: No POLYGON_API_KEY")
        return None

    async with httpx.AsyncClient(timeout=10.0) as client:

        # 1. Get ticker details (market cap, float)
        details = await _polygon_get(client, f"/v3/reference/tickers/{ticker}")
        if not details:
            return None
        market_cap = (details.get("market_cap") or 0) / 1_000_000  # Convert to millions
        shares_outstanding = details.get("share_class_shares_outstanding") or details.get("weighted_shares_outstanding") or 0

        # 2. Get short volume data from Polygon (if available on Starter tier)
        # Polygon endpoint: /v2/shorts/{ticker} or /v3/reference/tickers/{ticker}/short-interest
        # If not available, use short_volume_ratio from daily bar data
        short_data = await _get_short_interest_data(client, ticker)
        short_interest_pct = short_data.get("short_interest_pct", 0)
        days_to_cover = short_data.get("days_to_cover", 0)
        short_volume_ratio = short_data.get("short_volume_ratio", 0)

        # 3. Get recent price action to estimate short P&L
        # If stock has risen X% in last 2 weeks, shorts entered at lower prices are underwater
        bars = await _polygon_get(client, f"/v2/aggs/ticker/{ticker}/range/1/day/{_days_ago(14)}/{_today()}")
        estimated_short_pnl = _estimate_short_pnl(bars)

        # 4. Get UW flow score from internal flow_events table
        uw_score = await _get_uw_call_flow_score(pool, ticker)

        # 5. Get sector velocity from most recent Hermes event (if any)
        sector_vel = await _get_sector_velocity_for_ticker(pool, ticker)

        # 6. Calculate composite score
        # Normalize each factor to 0-100 scale before weighting
        factors = {
            "short_interest_pct": _normalize(short_interest_pct, min_val=0, max_val=40, clip=True),
            "days_to_cover": _normalize(days_to_cover, min_val=0, max_val=15, clip=True),
            "estimated_short_pnl": _normalize(abs(estimated_short_pnl), min_val=0, max_val=30, clip=True),
            "uw_call_flow_score": uw_score,
            "sector_velocity": _normalize(abs(sector_vel), min_val=0, max_val=3, clip=True)
        }

        composite = sum(factors[k] * WEIGHTS[k] for k in WEIGHTS)

        return {
            "short_interest_pct": short_interest_pct,
            "days_to_cover": days_to_cover,
            "estimated_short_pnl": estimated_short_pnl,
            "uw_call_flow_score": uw_score,
            "sector_velocity": sector_vel,
            "composite_score": round(composite, 2),
            "short_volume_ratio": short_volume_ratio,
            "market_cap_millions": round(market_cap, 2),
            "avg_daily_volume": short_data.get("avg_daily_volume", 0),
            "data_source": "polygon"
        }


async def check_position_exposure(pool) -> List[Dict]:
    """
    DEFENSIVE MODE: Check Nick's open positions against squeeze scores.
    Returns positions that have elevated squeeze risk (shorts that could get squeezed against him).
    """
    # Get Nick's current short positions from unified_positions
    positions = await pool.fetch("""
        SELECT position_id, ticker, direction, quantity, entry_price, current_price, unrealized_pnl
        FROM unified_positions
        WHERE status = 'OPEN'
        AND (direction = 'SHORT' OR direction = 'BEARISH' OR option_type = 'PUT')
    """)

    exposure_alerts = []
    for pos in positions:
        ticker = pos["ticker"]
        # Check squeeze score for this ticker (or its underlying ETF)
        score = await pool.fetchrow(
            "SELECT * FROM squeeze_scores WHERE ticker = $1", ticker
        )
        if score and score["composite_score"] >= 60:
            exposure_alerts.append({
                "position_id": pos["position_id"],
                "ticker": ticker,
                "direction": pos["direction"],
                "squeeze_score": float(score["composite_score"]),
                "short_interest_pct": float(score["short_interest_pct"] or 0),
                "days_to_cover": float(score["days_to_cover"] or 0),
                "warning": f"{ticker} squeeze score {score['composite_score']}/100 — your {pos['direction']} position is vulnerable"
            })

    return exposure_alerts


async def get_top_squeeze_candidates(pool, limit: int = 10) -> List[Dict]:
    """
    OFFENSIVE MODE: Return top squeeze candidates ranked by composite score.
    Feeds Bucket 2 tactical trade ideas.
    """
    rows = await pool.fetch("""
        SELECT * FROM squeeze_scores
        WHERE composite_score >= 50
        AND market_cap_millions >= 500
        AND avg_daily_volume >= 500000
        ORDER BY composite_score DESC
        LIMIT $1
    """, limit)

    return [dict(r) for r in rows]


# === CONVERGENCE CHECK — Lightning Card Generation ===

async def check_convergence_and_generate_lightning(pool, catalyst_event: Dict):
    """
    Called when a new Hermes catalyst event fires.
    Checks if any elevated squeeze scores align with the catalyst's affected sectors.
    If so, generates a Lightning Card.
    """
    trigger_ticker = catalyst_event.get("trigger_ticker", "")
    correlated = catalyst_event.get("correlated_tickers", [])
    direction = "bullish" if catalyst_event.get("trigger_move_pct", 0) > 0 else "bearish"
    event_id = catalyst_event.get("id")

    # Get all tickers affected by this catalyst
    affected_tickers = [trigger_ticker] + [c.get("ticker", "") for c in correlated if isinstance(c, dict)]

    # Find squeeze candidates in the affected sector
    # Also check ETF components — if SPY rips, check most-shorted SPY components
    sector_category = await _get_sector_for_ticker(pool, trigger_ticker)
    sector_squeeze_candidates = await pool.fetch("""
        SELECT * FROM squeeze_scores
        WHERE composite_score >= 55
        AND updated_at > NOW() - INTERVAL '24 hours'
        ORDER BY composite_score DESC
        LIMIT 20
    """)

    # Filter to candidates related to the catalyst
    # For now: any high-score candidate benefits from a broad market move
    # Future: filter by sector correlation
    for candidate in sector_squeeze_candidates:
        ticker = candidate["ticker"]
        composite = float(candidate["composite_score"])

        # Skip if composite is below threshold for Lightning Card
        if composite < 60:
            continue

        # Check Bucket 2 capacity
        bucket2_status = await _check_bucket2_capacity(pool)
        if bucket2_status["blocked"]:
            logger.info(f"HYDRA: Bucket 2 full — skipping Lightning Card for {ticker}")
            # Still generate card but mark as blocked
            pass

        # Check for position conflicts
        conflict = await _check_position_conflict(pool, ticker, direction)

        # Get options structure
        options = await _get_options_structure(ticker, direction)

        # Get catalyst details from the event
        catalyst_headline = catalyst_event.get("headline_summary", "Velocity breach detected")
        catalyst_category = catalyst_event.get("catalyst_category", "unknown")
        thesis_impact = ""
        if catalyst_event.get("pivot_analysis"):
            pivot_data = catalyst_event["pivot_analysis"]
            if isinstance(pivot_data, str):
                try:
                    pivot_data = json.loads(pivot_data)
                except Exception:
                    pivot_data = {}
            thesis_impact = pivot_data.get("thesis_impact", "")

        # Get current price for post-mortem tracking
        current_price = await _get_current_price(ticker)

        # Generate Lightning Card
        card_data = {
            "catalyst_event_id": event_id,
            "ticker": ticker,
            "direction": direction,
            "squeeze_composite_score": composite,

            # Options (may be None if Polygon options snapshot unavailable)
            "options_strike": options.get("strike") if options else None,
            "options_expiry": options.get("expiry") if options else None,
            "options_type": options.get("type") if options else None,
            "options_premium": options.get("premium") if options else None,
            "options_bid": options.get("bid") if options else None,
            "options_ask": options.get("ask") if options else None,
            "options_bid_ask_spread_pct": options.get("spread_pct") if options else None,
            "options_open_interest": options.get("open_interest") if options else None,
            "options_volume": options.get("volume") if options else None,
            "options_volume_vs_avg": options.get("volume_vs_avg") if options else None,

            # Asymmetry
            "max_loss": options.get("premium") if options else None,
            "breakeven_price": options.get("breakeven") if options else None,
            "payoff_1_sigma": options.get("payoff_1_sigma") if options else None,
            "payoff_2_sigma": options.get("payoff_2_sigma") if options else None,
            "risk_reward_ratio": options.get("rr_ratio") if options else None,

            # Bucket 2
            "bucket2_slots_used": bucket2_status["slots_used"],
            "bucket2_capital_deployed": bucket2_status["capital_deployed"],
            "bucket2_blocked": bucket2_status["blocked"],
            "bucket2_block_reason": bucket2_status.get("reason"),

            # Conflict
            "conflict_detected": conflict["detected"],
            "conflict_position_id": conflict.get("position_id"),
            "conflict_details": conflict.get("details"),

            # Thesis
            "catalyst_headline": catalyst_headline,
            "catalyst_category": catalyst_category,
            "thesis_impact": thesis_impact,

            # Price tracking
            "postmortem_price_at_generation": current_price,
            "status": "active"
        }

        card_id = await _insert_lightning_card(pool, card_data)
        logger.info(f"HYDRA LIGHTNING: Generated card {card_id} for {ticker} ({direction}, score {composite})")

        # Only generate 1-2 cards per convergence event to avoid noise
        break  # Take the top candidate only


# === HELPER FUNCTIONS (CC implements) ===

async def _polygon_get(client, path: str) -> Optional[Dict]:
    """Hit Polygon API and return results dict."""
    try:
        resp = await client.get(
            f"https://api.polygon.io{path}",
            params={"apiKey": POLYGON_API_KEY}
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("results", data)
        return None
    except Exception as e:
        logger.debug(f"Polygon request failed {path}: {e}")
        return None


async def _get_short_interest_data(client, ticker: str) -> Dict:
    """
    Get short interest data for a ticker.
    Try Polygon first. If not available on Starter tier, fallback options:
    1. Calculate short_volume_ratio from daily bar data (short volume / total volume)
    2. Use FINRA short interest data (free, but only updates bi-weekly)
    3. Return zeros and let other factors drive the score

    CC: Check Polygon docs for short interest endpoints available on Stocks Starter.
    The key endpoint would be something like:
    - /v2/shorts/{ticker}
    - /v3/reference/tickers/{ticker}/short-interest

    If neither exists on Starter tier, implement the short_volume_ratio calculation:
    GET /v2/aggs/ticker/{ticker}/range/1/day/{date}/{date}
    Some Polygon bar responses include 'otc' or short volume fields.
    """
    return {
        "short_interest_pct": 0,
        "days_to_cover": 0,
        "short_volume_ratio": 0,
        "avg_daily_volume": 0
    }


async def _estimate_short_pnl(bars_data) -> float:
    """
    Estimate how much short sellers are up/down.
    Logic: If stock is UP X% over last 2 weeks, shorts are DOWN ~X%.
    Simple but effective for scoring.
    """
    if not bars_data or not bars_data.get("results"):
        return 0
    results = bars_data["results"]
    if len(results) < 2:
        return 0
    price_14d_ago = results[0].get("c", 0)
    price_now = results[-1].get("c", 0)
    if price_14d_ago == 0:
        return 0
    return -((price_now - price_14d_ago) / price_14d_ago * 100)


async def _get_uw_call_flow_score(pool, ticker: str) -> float:
    """
    Score unusual call flow from the flow_events table (UW Watcher pipeline).
    Look for large call purchases in the last 24h.
    High call flow on a heavily shorted name = squeeze catalyst.
    Returns 0-100.
    """
    try:
        result = await pool.fetchrow("""
            SELECT COUNT(*) as call_count,
                   COALESCE(SUM(CASE WHEN premium::numeric > 100000 THEN 1 ELSE 0 END), 0) as large_calls
            FROM flow_events
            WHERE ticker = $1
            AND side ILIKE '%call%'
            AND created_at > NOW() - INTERVAL '24 hours'
        """, ticker)
        if result:
            call_count = result["call_count"] or 0
            large_calls = result["large_calls"] or 0
            # Normalize: 5+ large calls in 24h = score 100
            return min(100, (large_calls / 5) * 100)
    except Exception:
        pass
    return 0


async def _get_sector_velocity_for_ticker(pool, ticker: str) -> float:
    """
    Get the most recent sector velocity reading for this ticker's sector
    from the latest Hermes catalyst_event.
    """
    try:
        result = await pool.fetchrow("""
            SELECT sector_velocity FROM catalyst_events
            WHERE sector_velocity IS NOT NULL
            ORDER BY created_at DESC LIMIT 1
        """)
        if result and result["sector_velocity"]:
            velocities = result["sector_velocity"]
            if isinstance(velocities, str):
                velocities = json.loads(velocities)
            return velocities.get(ticker, 0)
    except Exception:
        pass
    return 0


async def _check_bucket2_capacity(pool) -> Dict:
    """
    Check Bucket 2 rules: max 2 open positions, max $200-300 each.
    Query unified_positions for Bucket 2 tagged trades.
    """
    try:
        # Count active Bucket 2 positions
        # Bucket 2 positions could be tagged by a bucket field, or inferred by
        # short DTE + small size. CC: check how positions are currently tagged.
        result = await pool.fetch("""
            SELECT position_id, ticker, cost_basis
            FROM unified_positions
            WHERE status = 'OPEN'
            AND (tags::text ILIKE '%bucket_2%' OR tags::text ILIKE '%tactical%')
        """)
        slots_used = len(result)
        capital = sum(float(r.get("cost_basis", 0) or 0) for r in result)

        blocked = slots_used >= 2
        reason = None
        if blocked:
            reason = f"Bucket 2 full: {slots_used}/2 slots, ${capital:.0f} deployed"

        return {
            "slots_used": slots_used,
            "capital_deployed": round(capital, 2),
            "blocked": blocked,
            "reason": reason
        }
    except Exception:
        return {"slots_used": 0, "capital_deployed": 0, "blocked": False}


async def _check_position_conflict(pool, ticker: str, direction: str) -> Dict:
    """
    Check if a Lightning Card would conflict with an existing position.
    E.g., suggesting bullish squeeze on HYG when Nick holds HYG puts.
    Also checks correlated tickers (e.g., MRVL squeeze vs SMH puts).
    """
    try:
        # Direct ticker conflict
        conflicts = await pool.fetch("""
            SELECT position_id, ticker, direction, option_type,
                   strike_price, expiry_date, quantity
            FROM unified_positions
            WHERE status = 'OPEN'
            AND ticker = $1
        """, ticker)

        for c in conflicts:
            pos_direction = c.get("direction", "")
            option_type = c.get("option_type", "")
            # Conflict: suggesting bullish on a ticker Nick is short/has puts
            is_conflict = (
                (direction == "bullish" and (pos_direction in ["SHORT", "BEARISH"] or option_type == "PUT")) or
                (direction == "bearish" and (pos_direction in ["LONG", "BULLISH"] or option_type == "CALL"))
            )
            if is_conflict:
                strike = c.get("strike_price", "")
                expiry = c.get("expiry_date", "")
                details = f"{ticker} {option_type or pos_direction} {f'${strike}' if strike else ''} {expiry or ''}"
                return {
                    "detected": True,
                    "position_id": c["position_id"],
                    "details": details.strip()
                }

        # TODO V2: Check correlated ETF conflicts
        # e.g., if ticker is MRVL and Nick has SMH puts, flag it

    except Exception as e:
        logger.debug(f"Conflict check error: {e}")

    return {"detected": False}


async def _get_options_structure(ticker: str, direction: str) -> Optional[Dict]:
    """
    Pull options chain from Polygon and select the best structure for a Bucket 2 trade.
    Rules:
    - 7-21 DTE (sweet spot for tactical trades)
    - Bid/ask spread < 15%
    - Open interest > 100
    - Strike nearest to current price + 1 ATR (calls) or - 1 ATR (puts)
    - Premium capped at $200-300 (Bucket 2 max)

    Polygon endpoint: /v3/snapshot/options/{underlyingAsset}
    or /v3/reference/options/contracts with expiration_date filters

    CC: Verify this endpoint is available on Stocks Starter ($29/mo).
    If not available, return None and the Lightning Card will display
    squeeze data without a pre-built options structure.
    Nick can pull up the chain manually in that case.
    """
    import httpx

    if not POLYGON_API_KEY:
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Get current price
            snapshot = await _polygon_get(client, f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}")
            if not snapshot or not isinstance(snapshot, dict):
                return None

            # Handle both single ticker and list response formats
            if isinstance(snapshot, list) and len(snapshot) > 0:
                snapshot = snapshot[0]

            current_price = snapshot.get("day", {}).get("c") or snapshot.get("prevDay", {}).get("c")
            if not current_price:
                return None

            # Calculate ATR for strike selection (use day range as rough proxy)
            day_high = snapshot.get("day", {}).get("h", current_price)
            day_low = snapshot.get("day", {}).get("l", current_price)
            rough_atr = day_high - day_low
            if rough_atr == 0:
                rough_atr = current_price * 0.02  # 2% fallback

            # Determine option type and target strike
            option_type = "call" if direction == "bullish" else "put"
            target_strike = (current_price + rough_atr) if direction == "bullish" else (current_price - rough_atr)

            # Get options contracts
            # Date range: 7-21 DTE
            min_expiry = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            max_expiry = (datetime.now() + timedelta(days=21)).strftime("%Y-%m-%d")

            contracts_resp = await client.get(
                f"https://api.polygon.io/v3/reference/options/contracts",
                params={
                    "underlying_ticker": ticker,
                    "contract_type": option_type,
                    "expiration_date.gte": min_expiry,
                    "expiration_date.lte": max_expiry,
                    "strike_price.gte": round(target_strike * 0.9, 0),
                    "strike_price.lte": round(target_strike * 1.1, 0),
                    "limit": 20,
                    "apiKey": POLYGON_API_KEY
                }
            )

            if contracts_resp.status_code != 200:
                return None

            contracts = contracts_resp.json().get("results", [])
            if not contracts:
                return None

            # Find best contract: closest to target strike, meeting liquidity filters
            best = None
            best_distance = float('inf')

            for contract in contracts:
                strike = contract.get("strike_price", 0)
                distance = abs(strike - target_strike)

                # Get snapshot for this specific contract to check bid/ask
                contract_ticker = contract.get("ticker")
                if not contract_ticker:
                    continue

                option_snap = await _polygon_get(
                    client,
                    f"/v3/snapshot/options/{ticker}/{contract_ticker}"
                )

                if not option_snap:
                    continue

                # Handle response format
                snap_data = option_snap if isinstance(option_snap, dict) else {}
                if isinstance(option_snap, list) and len(option_snap) > 0:
                    snap_data = option_snap[0]

                day = snap_data.get("day", {})
                details = snap_data.get("details", {})
                greeks = snap_data.get("greeks", {})

                bid = snap_data.get("last_quote", {}).get("bid", 0) or 0
                ask = snap_data.get("last_quote", {}).get("ask", 0) or 0
                oi = day.get("open_interest") or details.get("open_interest") or 0
                vol = day.get("volume", 0) or 0

                # Liquidity filters
                if bid <= 0 or ask <= 0:
                    continue
                spread_pct = ((ask - bid) / ask) * 100 if ask > 0 else 100
                if spread_pct > 15:
                    continue
                if oi < 100:
                    continue

                # Premium cap: Bucket 2 max $300 per contract
                midpoint = (bid + ask) / 2
                premium_per_contract = midpoint * 100  # Options are per 100 shares
                if premium_per_contract > 300:
                    continue

                if distance < best_distance:
                    best_distance = distance
                    expiry_date = contract.get("expiration_date")

                    # Calculate asymmetry
                    breakeven = strike + midpoint if option_type == "call" else strike - midpoint
                    # 1-sigma move estimate (rough: 1 ATR in remaining DTE)
                    dte = (datetime.strptime(expiry_date, "%Y-%m-%d") - datetime.now()).days if expiry_date else 14
                    sigma_1_price = current_price + (rough_atr * 1.5) if direction == "bullish" else current_price - (rough_atr * 1.5)
                    sigma_2_price = current_price + (rough_atr * 3) if direction == "bullish" else current_price - (rough_atr * 3)

                    # Estimate option value at sigma prices (simplified: intrinsic value only)
                    if option_type == "call":
                        payoff_1 = max(0, (sigma_1_price - strike)) * 100 - premium_per_contract
                        payoff_2 = max(0, (sigma_2_price - strike)) * 100 - premium_per_contract
                    else:
                        payoff_1 = max(0, (strike - sigma_1_price)) * 100 - premium_per_contract
                        payoff_2 = max(0, (strike - sigma_2_price)) * 100 - premium_per_contract

                    rr_low = round(max(payoff_1, 0) / premium_per_contract, 1) if premium_per_contract > 0 else 0
                    rr_high = round(max(payoff_2, 0) / premium_per_contract, 1) if premium_per_contract > 0 else 0

                    best = {
                        "strike": strike,
                        "expiry": expiry_date,
                        "type": option_type,
                        "premium": round(midpoint, 2),
                        "bid": round(bid, 2),
                        "ask": round(ask, 2),
                        "spread_pct": round(spread_pct, 2),
                        "open_interest": oi,
                        "volume": vol,
                        "volume_vs_avg": 0,  # TODO: calculate vs historical avg
                        "breakeven": round(breakeven, 2),
                        "payoff_1_sigma": round(payoff_1, 2),
                        "payoff_2_sigma": round(payoff_2, 2),
                        "rr_ratio": f"1:{rr_low} to 1:{rr_high}"
                    }

            return best

    except Exception as e:
        logger.error(f"HYDRA options structure error for {ticker}: {e}")
        return None


async def _get_current_price(ticker: str) -> Optional[float]:
    """Get current price from Polygon snapshot."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            data = await _polygon_get(client, f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}")
            if data:
                if isinstance(data, list) and len(data) > 0:
                    data = data[0]
                return data.get("day", {}).get("c") or data.get("prevDay", {}).get("c")
    except Exception:
        pass
    return None


async def _insert_lightning_card(pool, card_data: Dict) -> str:
    """Insert a Lightning Card into the database. Returns card UUID."""
    columns = ", ".join(card_data.keys())
    placeholders = ", ".join(f"${i+1}" for i in range(len(card_data)))
    values = list(card_data.values())

    result = await pool.fetchrow(f"""
        INSERT INTO lightning_cards ({columns})
        VALUES ({placeholders})
        RETURNING id
    """, *values)
    return str(result["id"])


async def get_squeeze_watchlist(pool) -> List[str]:
    """
    Get the list of tickers to score for squeeze vulnerability.
    Sources:
    1. Nick's open short positions (defensive)
    2. Tickers from recent UW flow events (offensive)
    3. Hardcoded high-short-interest watchlist (baseline)
    """
    tickers = set()

    # Nick's short positions
    try:
        positions = await pool.fetch("""
            SELECT DISTINCT ticker FROM unified_positions
            WHERE status = 'OPEN'
        """)
        for p in positions:
            tickers.add(p["ticker"])
    except Exception:
        pass

    # Recent UW flow tickers with high call activity
    try:
        flow = await pool.fetch("""
            SELECT DISTINCT ticker FROM flow_events
            WHERE created_at > NOW() - INTERVAL '48 hours'
            AND side ILIKE '%call%'
            AND premium::numeric > 50000
            LIMIT 30
        """)
        for f in flow:
            tickers.add(f["ticker"])
    except Exception:
        pass

    # Baseline high-short-interest tickers (update periodically)
    baseline = ["TSLA", "CVNA", "COIN", "MSTR", "U", "ASTS", "APLD",
                 "SMCI", "MRVL", "RIVN", "LCID", "SNAP", "PINS",
                 "GME", "AMC", "BBAI", "IONQ", "RKLB"]
    tickers.update(baseline)

    return list(tickers)


def _normalize(value: float, min_val: float, max_val: float, clip: bool = True) -> float:
    """Normalize a value to 0-100 scale."""
    if max_val == min_val:
        return 50
    normalized = ((value - min_val) / (max_val - min_val)) * 100
    if clip:
        normalized = max(0, min(100, normalized))
    return normalized


def _days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")

def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")

async def _get_sector_for_ticker(pool, ticker: str) -> str:
    """Map ticker to sector category. Simple lookup."""
    sector_map = {
        "SPY": "broad", "QQQ": "tech", "SMH": "semis",
        "XLF": "financials", "HYG": "credit", "IYR": "real_estate",
        "TLT": "bonds", "USO": "oil", "GLD": "safe_haven", "IBIT": "crypto"
    }
    return sector_map.get(ticker, "other")
```

---

## STEP 3: API Endpoints

New file or add to existing router: `routes/hydra.py`

```python
# === HYDRA API ENDPOINTS ===

from fastapi import APIRouter, Request
from backend.database.postgres_client import get_postgres_client
from backend.scanners.hydra import (
    get_top_squeeze_candidates,
    check_position_exposure,
    check_convergence_and_generate_lightning,
    refresh_squeeze_scores
)
import json
import logging

logger = logging.getLogger("hydra_api")
router = APIRouter(prefix="/api/hydra", tags=["hydra"])


@router.get("/scores")
async def get_squeeze_scores(limit: int = 20, min_score: float = 0):
    """Ranked squeeze candidates."""
    pool = await get_postgres_client()
    rows = await pool.fetch("""
        SELECT * FROM squeeze_scores
        WHERE composite_score >= $1
        ORDER BY composite_score DESC
        LIMIT $2
    """, min_score, limit)
    return {"scores": [dict(r) for r in rows]}


@router.get("/exposure")
async def get_exposure():
    """Defensive mode: which of Nick's positions are squeeze-vulnerable?"""
    pool = await get_postgres_client()
    alerts = await check_position_exposure(pool)
    return {"exposure_alerts": alerts, "count": len(alerts)}


@router.get("/lightning")
async def get_lightning_cards(active_only: bool = True, limit: int = 5):
    """Get Lightning Cards for the frontend Insights feed."""
    pool = await get_postgres_client()
    query = """
        SELECT * FROM lightning_cards
        WHERE ($1 = FALSE OR status = 'active')
        ORDER BY created_at DESC
        LIMIT $2
    """
    rows = await pool.fetch(query, active_only, limit)

    cards = []
    for r in rows:
        card = dict(r)
        # Parse JSON fields
        for field in ["pivot_analysis"]:
            if card.get(field) and isinstance(card[field], str):
                try:
                    card[field] = json.loads(card[field])
                except Exception:
                    pass
        # Convert UUID and date types to strings
        for k, v in card.items():
            if hasattr(v, 'isoformat'):
                card[k] = v.isoformat()
            elif hasattr(v, 'hex'):
                card[k] = str(v)
        cards.append(card)

    return {"lightning_cards": cards}


@router.patch("/lightning/{card_id}/status")
async def update_lightning_status(card_id: str, request: Request):
    """Update card status: dismissed, acted_on, expired."""
    data = await request.json()
    new_status = data.get("status")
    if new_status not in ["dismissed", "acted_on", "expired"]:
        return {"error": "Invalid status"}

    pool = await get_postgres_client()
    timestamp_field = {
        "acted_on": "acted_on_at",
        "expired": "expired_at"
    }.get(new_status)

    update_clause = f"status = $1, updated_at = NOW()"
    if timestamp_field:
        update_clause += f", {timestamp_field} = NOW()"

    await pool.execute(f"""
        UPDATE lightning_cards SET {update_clause} WHERE id = $2
    """, new_status, card_id)

    return {"status": "updated", "card_id": card_id}


@router.post("/refresh")
async def manual_refresh(request: Request):
    """Manually trigger a squeeze score refresh."""
    data = await request.json() if request.headers.get("content-type") == "application/json" else {}
    tickers = data.get("tickers")
    pool = await get_postgres_client()
    await refresh_squeeze_scores(pool, tickers)
    return {"status": "refreshed"}
```

**Router registration — add to main app alongside Hermes router:**
```python
from routes.hydra import router as hydra_router
app.include_router(hydra_router)
```

---

## STEP 4: Convergence Hook in Hermes

In the Brief 1 webhook handler (`routes/hermes.py`), after storing the catalyst event and triggering the VPS, add the convergence check.

**Find/replace anchor in `hermes_webhook()` function — AFTER the `store_catalyst_event()` call, add:**

```python
    # === CONVERGENCE CHECK: Hermes × Hydra → Lightning Card ===
    try:
        from backend.scanners.hydra import check_convergence_and_generate_lightning
        catalyst_for_convergence = {
            "id": str(event_id),
            "trigger_ticker": ticker,
            "trigger_move_pct": float(velocity_pct),
            "correlated_tickers": correlated,
            "headline_summary": "",  # Not yet available — Pivot hasn't analyzed yet
            "catalyst_category": "unknown",
            "pivot_analysis": None
        }
        await check_convergence_and_generate_lightning(pool, catalyst_for_convergence)
    except Exception as e:
        logger.error(f"HERMES: Convergence check failed: {e}")
    # Lightning Cards update when Pivot analysis arrives via /api/hermes/analysis
```

**Also add a second convergence pass** in the `/api/hermes/analysis` endpoint (the one that receives Pivot's results). After updating the catalyst_event with the headline, re-run convergence with the full analysis so Lightning Cards get the thesis_impact field:

```python
    # After updating catalyst_events with Pivot analysis:
    try:
        from backend.scanners.hydra import check_convergence_and_generate_lightning
        # Update any existing Lightning Cards with the Pivot analysis
        await pool.execute("""
            UPDATE lightning_cards
            SET catalyst_headline = $1,
                catalyst_category = $2,
                thesis_impact = $3,
                updated_at = NOW()
            WHERE catalyst_event_id = $4
            AND status = 'active'
        """,
            analysis.get("headline_summary", ""),
            analysis.get("catalyst_category", "unknown"),
            analysis.get("thesis_impact", ""),
            event_id
        )
    except Exception as e:
        logger.error(f"Lightning Card update with Pivot analysis failed: {e}")
```

---

## STEP 5: Cron Job — Hydra Score Refresh

Add to existing cron setup (or create new cron entry):

```python
# Hydra squeeze score refresh
# Runs daily at market open (13:30 UTC) + every 30 min during market hours
# Cron: 30 13 * * 1-5 AND */30 13-20 * * 1-5

async def hydra_cron():
    pool = await get_postgres_client()
    await refresh_squeeze_scores(pool)
```

---

## STEP 6: Lightning Card Expiry Cron

Expire active cards older than 2 hours and populate post-mortem data:

```python
# Runs every 15 minutes during market hours

async def expire_lightning_cards():
    pool = await get_postgres_client()
    # Find cards older than 2 hours that are still active
    expired_cards = await pool.fetch("""
        SELECT id, ticker, postmortem_price_at_generation, options_premium, options_type, options_strike
        FROM lightning_cards
        WHERE status = 'active'
        AND created_at < NOW() - INTERVAL '2 hours'
    """)

    for card in expired_cards:
        ticker = card["ticker"]
        gen_price = float(card["postmortem_price_at_generation"] or 0)

        # Get current price for post-mortem
        from backend.scanners.hydra import _get_current_price
        current_price = await _get_current_price(ticker) or gen_price
        actual_move_pct = ((current_price - gen_price) / gen_price * 100) if gen_price else 0

        # Estimate missed P&L (simplified: intrinsic value of suggested option)
        missed_pnl = 0
        premium = float(card["options_premium"] or 0)
        strike = float(card["options_strike"] or 0)
        if card["options_type"] == "call" and current_price > strike:
            missed_pnl = ((current_price - strike) * 100) - (premium * 100)
        elif card["options_type"] == "put" and current_price < strike:
            missed_pnl = ((strike - current_price) * 100) - (premium * 100)

        await pool.execute("""
            UPDATE lightning_cards
            SET status = 'expired',
                expired_at = NOW(),
                postmortem_price_at_expiry = $1,
                postmortem_actual_move_pct = $2,
                postmortem_estimated_missed_pnl = $3,
                updated_at = NOW()
            WHERE id = $4
        """, current_price, round(actual_move_pct, 2), round(missed_pnl, 2), card["id"])

        logger.info(f"HYDRA: Card expired for {ticker} — actual move {actual_move_pct:+.1f}%, est missed P&L ${missed_pnl:.0f}")
```

---

## STEP 7: Agora Frontend — Lightning Card Renderer

Add to `frontend/app.js`:

### 7A: Lightning Card CSS

```css
/* === LIGHTNING CARDS === */

.lightning-card {
    position: relative;
    border-radius: 6px;
    padding: 12px 14px;
    margin-bottom: 10px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    background: rgba(0,0,0,0.4);
    overflow: hidden;
    animation: lightning-border-pulse 2s ease-in-out infinite;
}

/* Path-dependent border and glow */
.lightning-card.bullish {
    border: 1.5px solid #00e676;
    box-shadow: 0 0 8px rgba(0, 230, 118, 0.15);
}
.lightning-card.bearish {
    border: 1.5px solid #ff9800;
    box-shadow: 0 0 8px rgba(255, 152, 0, 0.15);
}

@keyframes lightning-border-pulse {
    0%, 100% {
        opacity: 1;
        filter: brightness(1);
    }
    50% {
        opacity: 0.8;
        filter: brightness(1.3);
    }
}

/* Expired card — stop pulsing, dim */
.lightning-card.expired {
    animation: none;
    opacity: 0.4;
    border-color: rgba(255,255,255,0.15);
    box-shadow: none;
}

/* Lightning icon */
.lightning-icon {
    width: 20px;
    height: 20px;
    flex-shrink: 0;
    animation: lightning-icon-pulse 2s ease-in-out infinite;
}
.lightning-card.expired .lightning-icon { animation: none; opacity: 0.3; }

@keyframes lightning-icon-pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.7; transform: scale(1.08); }
}

/* Header row */
.lightning-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
}
.lightning-ticker {
    font-size: 16px;
    font-weight: 700;
}
.lightning-direction-badge {
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}
.lightning-direction-badge.bullish { background: rgba(0, 230, 118, 0.2); color: #00e676; }
.lightning-direction-badge.bearish { background: rgba(255, 152, 0, 0.2); color: #ff9800; }

.lightning-countdown {
    margin-left: auto;
    font-size: 11px;
    opacity: 0.7;
}
.lightning-countdown.urgent { color: #ff9800; opacity: 1; }
.lightning-countdown.critical { color: #f44336; opacity: 1; font-weight: 700; }

/* Catalyst line */
.lightning-catalyst {
    font-size: 11px;
    margin-bottom: 8px;
    padding: 4px 8px;
    background: rgba(255,255,255,0.04);
    border-radius: 3px;
    color: rgba(255,255,255,0.8);
    font-style: italic;
}

/* Squeeze stats row */
.lightning-squeeze-stats {
    display: flex;
    gap: 12px;
    margin-bottom: 8px;
    font-size: 11px;
}
.lightning-stat {
    display: flex;
    flex-direction: column;
    align-items: center;
}
.lightning-stat-label { opacity: 0.5; font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px; }
.lightning-stat-value { font-weight: 700; font-size: 13px; }

/* Options structure */
.lightning-options {
    background: rgba(255,255,255,0.03);
    border-radius: 3px;
    padding: 6px 8px;
    margin-bottom: 8px;
    font-size: 11px;
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 4px;
}
.lightning-option-item { display: flex; justify-content: space-between; }
.lightning-option-label { opacity: 0.5; }
.lightning-option-value { font-weight: 600; }

/* Asymmetry box */
.lightning-asymmetry {
    padding: 6px 10px;
    border-radius: 3px;
    margin-bottom: 8px;
    font-size: 13px;
    font-weight: 700;
    text-align: center;
}
.lightning-card.bullish .lightning-asymmetry { background: rgba(0, 230, 118, 0.1); color: #00e676; }
.lightning-card.bearish .lightning-asymmetry { background: rgba(255, 152, 0, 0.1); color: #ff9800; }

/* Bucket 2 status */
.lightning-bucket2 {
    font-size: 10px;
    opacity: 0.6;
    margin-bottom: 4px;
}

/* Thesis impact */
.lightning-thesis {
    font-size: 11px;
    padding: 4px 8px;
    border-radius: 3px;
    margin-bottom: 6px;
}
.lightning-card.bullish .lightning-thesis { background: rgba(0,230,118,0.06); border-left: 2px solid rgba(0,230,118,0.3); }
.lightning-card.bearish .lightning-thesis { background: rgba(255,152,0,0.06); border-left: 2px solid rgba(255,152,0,0.3); }

/* Conflict warning */
.lightning-conflict {
    background: rgba(244, 67, 54, 0.12);
    border: 1px solid rgba(244, 67, 54, 0.3);
    border-radius: 3px;
    padding: 4px 8px;
    margin-bottom: 6px;
    font-size: 11px;
    color: #f44336;
}

/* Bucket 2 blocked warning */
.lightning-blocked {
    background: rgba(244, 67, 54, 0.08);
    border: 1px solid rgba(244, 67, 54, 0.2);
    border-radius: 3px;
    padding: 4px 8px;
    margin-bottom: 6px;
    font-size: 11px;
    color: #ff9800;
}

/* Post-mortem overlay on expired cards */
.lightning-postmortem {
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 700;
    flex-direction: column;
    gap: 4px;
}
.lightning-postmortem .missed-pnl { font-size: 18px; }
.lightning-postmortem .missed-pnl.positive { color: #00e676; }
.lightning-postmortem .missed-pnl.negative { color: #f44336; }

/* Dismiss button */
.lightning-dismiss {
    position: absolute;
    top: 6px;
    right: 6px;
    background: none;
    border: 1px solid rgba(255,255,255,0.15);
    color: rgba(255,255,255,0.5);
    cursor: pointer;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 10px;
}
.lightning-dismiss:hover { background: rgba(255,255,255,0.1); color: white; }
```

### 7B: Lightning Card JavaScript

```javascript
// === LIGHTNING CARDS — Frontend Logic ===

let lightningPollingInterval = null;

function initLightningCards() {
    lightningPollingInterval = setInterval(fetchLightningCards, 10000);
    fetchLightningCards();
}

async function fetchLightningCards() {
    try {
        const resp = await fetch('/api/hydra/lightning?active_only=true&limit=3', {
            headers: { 'X-API-Key': API_KEY }
        });
        if (!resp.ok) return;
        const data = await resp.json();

        renderLightningCards(data.lightning_cards || []);
    } catch (err) {
        console.error('Lightning card fetch error:', err);
    }
}

function renderLightningCards(cards) {
    const container = document.getElementById('tradeSignals');
    if (!container) return;

    // Remove existing lightning cards
    container.querySelectorAll('.lightning-card').forEach(el => el.remove());

    // Insert at top of container, before existing signal cards
    const firstChild = container.firstChild;

    cards.forEach(card => {
        const cardEl = createLightningCard(card);
        container.insertBefore(cardEl, firstChild);
    });
}

function createLightningCard(card) {
    const dir = card.direction || 'bullish';
    const color = dir === 'bullish' ? '#00e676' : '#ff9800';
    const isExpired = card.status === 'expired';

    // Calculate countdown
    const createdAt = new Date(card.created_at);
    const ageMinutes = Math.floor((Date.now() - createdAt.getTime()) / 60000);
    let countdownClass = '';
    if (ageMinutes > 90) countdownClass = 'critical';
    else if (ageMinutes > 60) countdownClass = 'urgent';

    // Lightning bolt SVG — color matches direction
    const lightningSvg = `<svg class="lightning-icon" viewBox="0 0 24 24" fill="${color}" xmlns="http://www.w3.org/2000/svg">
        <path d="M13 2L3 14h8l-1 8 10-12h-8l1-8z" stroke="${color}" stroke-width="0.5" stroke-linejoin="round"/>
    </svg>`;

    // Options section (only if data available)
    let optionsHtml = '';
    if (card.options_strike) {
        optionsHtml = `
            <div class="lightning-options">
                <div class="lightning-option-item">
                    <span class="lightning-option-label">Strike</span>
                    <span class="lightning-option-value">$${parseFloat(card.options_strike).toFixed(0)} ${(card.options_type || '').toUpperCase()}</span>
                </div>
                <div class="lightning-option-item">
                    <span class="lightning-option-label">Expiry</span>
                    <span class="lightning-option-value">${card.options_expiry || '-'}</span>
                </div>
                <div class="lightning-option-item">
                    <span class="lightning-option-label">Premium</span>
                    <span class="lightning-option-value">$${parseFloat(card.options_premium || 0).toFixed(2)}</span>
                </div>
                <div class="lightning-option-item">
                    <span class="lightning-option-label">Bid/Ask</span>
                    <span class="lightning-option-value">$${parseFloat(card.options_bid || 0).toFixed(2)} / $${parseFloat(card.options_ask || 0).toFixed(2)}</span>
                </div>
                <div class="lightning-option-item">
                    <span class="lightning-option-label">Spread</span>
                    <span class="lightning-option-value">${parseFloat(card.options_bid_ask_spread_pct || 0).toFixed(1)}%</span>
                </div>
                <div class="lightning-option-item">
                    <span class="lightning-option-label">OI / Vol</span>
                    <span class="lightning-option-value">${(card.options_open_interest || 0).toLocaleString()} / ${(card.options_volume || 0).toLocaleString()}</span>
                </div>
            </div>
        `;
    }

    // Asymmetry box
    let asymmetryHtml = '';
    if (card.max_loss && card.payoff_1_sigma) {
        const maxLoss = parseFloat(card.max_loss) * 100;
        const p1 = parseFloat(card.payoff_1_sigma);
        const p2 = parseFloat(card.payoff_2_sigma || 0);
        asymmetryHtml = `
            <div class="lightning-asymmetry">
                Risk $${maxLoss.toFixed(0)} → Reward $${Math.max(0, p1).toFixed(0)}–$${Math.max(0, p2).toFixed(0)} (${card.risk_reward_ratio || '?'})
            </div>
        `;
    }

    // Conflict warning
    let conflictHtml = '';
    if (card.conflict_detected) {
        conflictHtml = `<div class="lightning-conflict">⚠️ CONFLICTS: ${card.conflict_details || 'Open position on this ticker'}</div>`;
    }

    // Bucket 2 blocked warning
    let blockedHtml = '';
    if (card.bucket2_blocked) {
        blockedHtml = `<div class="lightning-blocked">⚠️ ${card.bucket2_block_reason || 'Bucket 2 full'}</div>`;
    }

    // Thesis impact
    let thesisHtml = '';
    if (card.thesis_impact) {
        thesisHtml = `<div class="lightning-thesis"><strong>Thesis:</strong> ${card.thesis_impact}</div>`;
    }

    // Post-mortem overlay for expired cards
    let postmortemHtml = '';
    if (isExpired && card.postmortem_actual_move_pct !== null) {
        const move = parseFloat(card.postmortem_actual_move_pct || 0);
        const missed = parseFloat(card.postmortem_estimated_missed_pnl || 0);
        const missedClass = missed > 0 ? 'positive' : 'negative';
        postmortemHtml = `
            <div class="lightning-postmortem">
                <div style="font-size:11px; opacity:0.7;">EXPIRED — ${card.ticker} moved ${move >= 0 ? '+' : ''}${move.toFixed(1)}%</div>
                <div class="missed-pnl ${missedClass}">
                    ${missed > 0 ? `Missed: +$${missed.toFixed(0)}` : `Would have lost: $${Math.abs(missed).toFixed(0)}`}
                </div>
            </div>
        `;
    }

    const div = document.createElement('div');
    div.className = `lightning-card ${dir} ${isExpired ? 'expired' : ''}`;
    div.setAttribute('data-card-id', card.id);
    div.innerHTML = `
        <button class="lightning-dismiss" onclick="dismissLightningCard('${card.id}')" title="Dismiss">✕</button>

        <div class="lightning-header">
            ${lightningSvg}
            <span class="lightning-ticker" style="color:${color}">${card.ticker}</span>
            <span class="lightning-direction-badge ${dir}">SQUEEZE ${dir === 'bullish' ? 'LONG' : 'SHORT'}</span>
            <span class="lightning-countdown ${countdownClass}">${ageMinutes}m ago</span>
        </div>

        <div class="lightning-catalyst">${card.catalyst_headline || 'Velocity breach + elevated squeeze score'}</div>

        <div class="lightning-squeeze-stats">
            <div class="lightning-stat">
                <span class="lightning-stat-label">SI%</span>
                <span class="lightning-stat-value">${parseFloat(card.squeeze_composite_score || 0).toFixed(0)}/100</span>
            </div>
            <div class="lightning-stat">
                <span class="lightning-stat-label">Short Int</span>
                <span class="lightning-stat-value">${card.short_interest_pct || '?'}%</span>
            </div>
            <div class="lightning-stat">
                <span class="lightning-stat-label">DTC</span>
                <span class="lightning-stat-value">${card.days_to_cover || '?'}</span>
            </div>
        </div>

        ${optionsHtml}
        ${asymmetryHtml}

        <div class="lightning-bucket2">Bucket 2: ${card.bucket2_slots_used || 0}/2 slots | $${parseFloat(card.bucket2_capital_deployed || 0).toFixed(0)} deployed</div>

        ${thesisHtml}
        ${conflictHtml}
        ${blockedHtml}
        ${postmortemHtml}
    `;

    // Play thunder sound on first render of a new card
    if (!isExpired && !div.dataset.soundPlayed) {
        playThunderSound();
        div.dataset.soundPlayed = 'true';
    }

    // Start countdown updater
    if (!isExpired) {
        startCountdownUpdater(div, createdAt);
    }

    return div;
}

// Track which cards have already played sound (persist across polling cycles)
const _lightningCardsSounded = new Set();

function playThunderSound() {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();

        // Low rumble layer (80Hz)
        const rumbleOsc = ctx.createOscillator();
        const rumbleGain = ctx.createGain();
        rumbleOsc.type = 'sine';
        rumbleOsc.frequency.value = 80;
        rumbleGain.gain.setValueAtTime(0.15, ctx.currentTime);
        rumbleGain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 1.5);
        rumbleOsc.connect(rumbleGain);
        rumbleGain.connect(ctx.destination);
        rumbleOsc.start();
        rumbleOsc.stop(ctx.currentTime + 1.5);

        // Mid crack layer (120Hz with noise)
        const crackOsc = ctx.createOscillator();
        const crackGain = ctx.createGain();
        crackOsc.type = 'sawtooth';
        crackOsc.frequency.value = 120;
        crackGain.gain.setValueAtTime(0.08, ctx.currentTime);
        crackGain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
        crackOsc.connect(crackGain);
        crackGain.connect(ctx.destination);
        crackOsc.start();
        crackOsc.stop(ctx.currentTime + 0.5);

        // Sharp attack (high freq burst)
        const attackOsc = ctx.createOscillator();
        const attackGain = ctx.createGain();
        attackOsc.type = 'square';
        attackOsc.frequency.value = 300;
        attackGain.gain.setValueAtTime(0.06, ctx.currentTime);
        attackGain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.15);
        attackOsc.connect(attackGain);
        attackGain.connect(ctx.destination);
        attackOsc.start();
        attackOsc.stop(ctx.currentTime + 0.2);

    } catch (e) { /* Audio not available, silent fallback */ }
}

function startCountdownUpdater(cardEl, createdAt) {
    const countdownEl = cardEl.querySelector('.lightning-countdown');
    if (!countdownEl) return;

    const interval = setInterval(() => {
        const now = Date.now();
        const ageMin = Math.floor((now - createdAt.getTime()) / 60000);
        countdownEl.textContent = `${ageMin}m ago`;

        // Update urgency classes
        countdownEl.className = 'lightning-countdown';
        if (ageMin > 90) countdownEl.classList.add('critical');
        else if (ageMin > 60) countdownEl.classList.add('urgent');

        // Stop updating if card is removed from DOM
        if (!document.contains(cardEl)) {
            clearInterval(interval);
        }
    }, 30000); // Update every 30 seconds
}

async function dismissLightningCard(cardId) {
    try {
        await fetch(`/api/hydra/lightning/${cardId}/status`, {
            method: 'PATCH',
            headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'dismissed' })
        });
        const el = document.querySelector(`[data-card-id="${cardId}"]`);
        if (el) el.remove();
    } catch (err) {
        console.error('Dismiss error:', err);
    }
}

// Sound deduplication: track which cards have played thunder
function renderLightningCards(cards) {
    const container = document.getElementById('tradeSignals');
    if (!container) return;

    container.querySelectorAll('.lightning-card').forEach(el => el.remove());

    const firstChild = container.firstChild;

    cards.forEach(card => {
        const cardEl = createLightningCard(card);

        // Only play thunder for cards we haven't seen before
        if (!_lightningCardsSounded.has(card.id) && card.status === 'active') {
            playThunderSound();
            _lightningCardsSounded.add(card.id);
        }

        container.insertBefore(cardEl, firstChild);
    });
}

// Initialize — add to existing dashboard init:
// initLightningCards();
```

**Find/replace anchor for initialization — add `initLightningCards();` wherever `initHermesFlash();` was added in Brief 1.**

---

## STEP 8: Upsert Helper

```python
async def upsert_squeeze_score(pool, ticker: str, score_data: Dict):
    """Upsert squeeze score into the database."""
    await pool.execute("""
        INSERT INTO squeeze_scores (ticker, short_interest_pct, days_to_cover,
            estimated_short_pnl, uw_call_flow_score, sector_velocity,
            composite_score, short_volume_ratio, market_cap_millions,
            avg_daily_volume, data_source, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
        ON CONFLICT (ticker) DO UPDATE SET
            short_interest_pct = EXCLUDED.short_interest_pct,
            days_to_cover = EXCLUDED.days_to_cover,
            estimated_short_pnl = EXCLUDED.estimated_short_pnl,
            uw_call_flow_score = EXCLUDED.uw_call_flow_score,
            sector_velocity = EXCLUDED.sector_velocity,
            composite_score = EXCLUDED.composite_score,
            short_volume_ratio = EXCLUDED.short_volume_ratio,
            market_cap_millions = EXCLUDED.market_cap_millions,
            avg_daily_volume = EXCLUDED.avg_daily_volume,
            data_source = EXCLUDED.data_source,
            updated_at = NOW()
    """,
        ticker,
        score_data.get("short_interest_pct"),
        score_data.get("days_to_cover"),
        score_data.get("estimated_short_pnl"),
        score_data.get("uw_call_flow_score"),
        score_data.get("sector_velocity"),
        score_data.get("composite_score"),
        score_data.get("short_volume_ratio"),
        score_data.get("market_cap_millions"),
        score_data.get("avg_daily_volume"),
        score_data.get("data_source", "polygon")
    )
```

---

## NOTES FOR CC

- **Database is Railway Postgres.** Use `get_postgres_client()` for everything.
- The `squeeze_scores` table uses `ON CONFLICT (ticker) DO UPDATE` — it's a living scoreboard, not append-only.
- **Polygon data availability:** The options snapshot endpoint (`/v3/snapshot/options/`) may require a higher tier than Stocks Starter. If so, the Lightning Card still generates — it just won't have the pre-built options structure. Nick pulls up the chain manually. The squeeze data alone (SI%, DTC, composite score) is still valuable.
- **The convergence check runs twice:** once immediately when Hermes fires (before Pivot analysis — card gets basic data), and again when Pivot's analysis arrives (card gets headline + thesis impact). This ensures the card appears fast but enriches as intel arrives.
- **Sound deduplication:** The `_lightningCardsSounded` Set ensures thunder only plays once per card, even though the frontend polls every 10 seconds and re-renders.
- The `flow_events` table query in `_get_uw_call_flow_score` — verify the actual column names. The UW Watcher pipeline may use different field names for `side`, `premium`, etc. Adjust the query to match actual schema.
- Lightning Cards expire after 2 hours. The post-mortem cron logs what happened. Over time, this builds a dataset for future V2 features (historical analogs, pattern learning).
- The `_check_bucket2_capacity` function looks for positions tagged as Bucket 2. If no tagging system exists yet, CC should add a `bucket` or `tags` field to `unified_positions`, or use a simpler heuristic (DTE < 21 + cost_basis < 350 = Bucket 2).
