# Brief: Immediate Trading Issues (3 items)

**Priority:** HIGH — These directly affect signal quality and bias accuracy during active trading.
**Target:** Railway backend (`backend/`)
**Estimated time:** 60–90 minutes total across all 3 items

---

## Item 1: tick_breadth Late-Session Close Bounce Fix

### Problem

Late in the trading session, the TICK close reading often bounces positive as market-on-close (MOC) buy orders execute. This single data point can overpower a full day of bearish average TICK, pulling the factor score toward neutral/bullish even when the session was decisively bearish.

The current blending is 40% range-based score + 60% directional modifier. The directional modifier uses both `tick_close` and `tick_avg`, but `tick_close` carries too much weight relative to `tick_avg`.

### Current Code

**File: `backend/bias_filters/tick_breadth.py`** in `compute_tick_score()`:

The directional modifier section (around line 390) scores `tick_close` and `tick_avg` independently, then blends them. The conflict handler (around line 416) tries to dampen the close signal when it contradicts the average, but it only scales by 0.25x — still too much leakage.

### Fix

Change the conflict dampening to nearly eliminate the close signal when it contradicts the session average. The average represents 6+ hours of data; the close is a 1-second snapshot.

Find the conflict handling block (around line 416):
```python
    # Conflict: average says selling but close says buying (late bounce)
    # Average represents full session, close is a snapshot — trust the average
    if tick_avg < -100 and dir_mod > 0:
        dir_mod = min(dir_mod * 0.25, 0.05)  # Nearly zero out bullish close signal
    elif tick_avg > 100 and dir_mod < 0:
        dir_mod = max(dir_mod * 0.25, -0.05)  # Nearly zero out bearish close signal
```

Replace with:
```python
    # Conflict: average says selling but close says buying (late bounce)
    # Average represents full session, close is a snapshot — trust the average
    # Late-session MOC orders commonly cause close bounces that contradict the day
    if tick_avg < -100 and dir_mod > 0:
        # Bearish session with bullish close — nearly fully override close
        # Use average direction instead, scaled down
        avg_dir = -0.3 if tick_avg < -200 else -0.15
        dir_mod = avg_dir  # Replace bullish close signal with mild bearish from avg
    elif tick_avg > 100 and dir_mod < 0:
        # Bullish session with bearish close — same logic, mirror
        avg_dir = 0.3 if tick_avg > 200 else 0.15
        dir_mod = avg_dir  # Replace bearish close signal with mild bullish from avg
```

This completely replaces the close-derived signal with the average-derived signal when they conflict, instead of just dampening it. The result: a day of -200 average TICK with a +300 close bounce will read as mildly bearish (from the avg) instead of mildly bullish (from the close).

### Also: Add average-weighted amplification when they agree

Below the conflict block (around line 420), BEFORE the final blend, add:

```python
    # Reinforcement: when close and avg agree, strengthen the signal
    if tick_avg < -200 and dir_mod < 0:
        dir_mod *= 1.2  # Strong bearish session, amplify
    elif tick_avg > 200 and dir_mod > 0:
        dir_mod *= 1.2  # Strong bullish session, amplify
    dir_mod = max(-1.0, min(1.0, dir_mod))  # Re-clamp
```

### Verification

After deploying, wait for the next TICK webhook during market hours. Then check:
```
curl https://pandoras-box-production.up.railway.app/api/bias/tick
```

During a bearish session (avg TICK < -100), the tick_breadth factor should read negative even if the close reading bounces positive. Compare with what you see on your TradingView TICK chart.

---

## Item 2: Hub Sniper VWAP Validation Harness

### Problem

Hub Sniper is the only active strategy still running exclusively on TradingView (not server-side). Before porting it, we need to verify that server-side VWAP calculation matches TradingView's VWAP closely enough. VWAP is notoriously sensitive to bar boundaries and volume bucketing.

### What to build

A lightweight validation script that:
1. Fetches SPY 15-minute bars from yfinance (or Polygon)
2. Computes VWAP + standard deviation bands server-side
3. Records the computed VWAP/VAH/VAL values every 15 minutes during market hours
4. Stores them in a simple JSONL log

Nick will compare these values against his TradingView chart manually for 5 trading days. If mean error < 0.1% and max error < 0.5%, the port is greenlit.

**File: `backend/scanners/vwap_validator.py`** (new file)

```python
"""
VWAP Validation Harness
Computes server-side VWAP + ±2 stddev bands for SPY on 15-min bars.
Stores readings to a JSONL log for comparison against TradingView.

Run: called by background loop in main.py every 15 min during market hours.
After 5 trading days, compare log against TV chart.
Acceptance: mean error < 0.1%, max error < 0.5%.
"""

import json
import logging
import numpy as np
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)

VWAP_LOG = Path("data/vwap_validation.jsonl")
VWAP_LOG.parent.mkdir(parents=True, exist_ok=True)

VALIDATOR_AVAILABLE = False
try:
    import yfinance as yf
    import pandas as pd
    VALIDATOR_AVAILABLE = True
except ImportError:
    logger.warning("VWAP Validator: yfinance or pandas not available")


def compute_vwap_bands(ticker: str = "SPY") -> Optional[Dict]:
    """Compute current-session VWAP + ±2σ bands from 15-min bars."""
    if not VALIDATOR_AVAILABLE:
        return None

    try:
        # Fetch today's intraday bars
        t = yf.Ticker(ticker)
        df = t.history(period="1d", interval="15m")

        if df.empty or len(df) < 2:
            return None

        # Standard VWAP calculation
        typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
        cum_tp_vol = (typical_price * df["Volume"]).cumsum()
        cum_vol = df["Volume"].cumsum()

        vwap = cum_tp_vol / cum_vol

        # Rolling standard deviation of typical price from VWAP
        # TV uses cumulative variance from session start
        cum_tp2_vol = ((typical_price ** 2) * df["Volume"]).cumsum()
        variance = (cum_tp2_vol / cum_vol) - (vwap ** 2)
        stddev = np.sqrt(np.maximum(variance, 0))

        current_vwap = float(vwap.iloc[-1])
        current_stddev = float(stddev.iloc[-1])
        current_price = float(df["Close"].iloc[-1])
        bar_time = df.index[-1].strftime("%Y-%m-%d %H:%M")

        return {
            "ticker": ticker,
            "bar_time": bar_time,
            "price": round(current_price, 2),
            "vwap": round(current_vwap, 4),
            "vah": round(current_vwap + 2 * current_stddev, 4),  # +2σ
            "val": round(current_vwap - 2 * current_stddev, 4),  # -2σ
            "stddev": round(current_stddev, 4),
            "bars_in_session": len(df),
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.warning("VWAP validation failed for %s: %s", ticker, e)
        return None


async def run_vwap_validation() -> Optional[Dict]:
    """Compute and log VWAP readings. Called from background loop."""
    result = compute_vwap_bands("SPY")
    if result:
        try:
            with open(VWAP_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(result) + "\n")
            logger.info(
                "VWAP validation: SPY VWAP=%.2f VAH=%.2f VAL=%.2f (%d bars)",
                result["vwap"], result["vah"], result["val"], result["bars_in_session"]
            )
        except Exception as e:
            logger.warning("Failed to write VWAP validation log: %s", e)
    return result
```

### Wire into main.py background loops

Add a new background loop in `main.py` lifespan, alongside the other scanner loops:

```python
    # VWAP validation harness: log VWAP readings for Hub Sniper port validation
    async def vwap_validation_loop():
        """Log SPY VWAP every 15 min for comparison with TradingView."""
        import pytz
        from datetime import datetime as dt_cls

        await asyncio.sleep(240)  # 4 min offset from other scanners

        while True:
            try:
                et = dt_cls.now(pytz.timezone("America/New_York"))
                # Market hours: 9:30 AM - 4:00 PM ET, weekdays
                if et.weekday() < 5 and 9 <= et.hour < 16:
                    from scanners.vwap_validator import run_vwap_validation, VALIDATOR_AVAILABLE
                    if VALIDATOR_AVAILABLE:
                        await run_vwap_validation()
                else:
                    logger.debug("VWAP validation: outside market hours, skipping")
            except Exception as e:
                logger.warning("VWAP validation loop error: %s", e)
            await asyncio.sleep(900)  # 15 minutes
```

Add to the task creation block:
```python
    vwap_validation_task = asyncio.create_task(vwap_validation_loop())
```

And to the shutdown block:
```python
    vwap_validation_task.cancel()
```

### Add a read endpoint for checking results

**File: `backend/main.py`** — add a quick endpoint:

```python
@app.get("/api/monitoring/vwap-validation")
async def vwap_validation_status():
    """Get recent VWAP validation readings."""
    from pathlib import Path
    import json

    log_path = Path("data/vwap_validation.jsonl")
    if not log_path.exists():
        return {"status": "no_data", "readings": []}

    lines = log_path.read_text().strip().split("\n")
    readings = []
    for line in lines[-20:]:  # Last 20 readings
        try:
            readings.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    return {
        "status": "collecting",
        "total_readings": len(lines),
        "recent": readings,
    }
```

### Nick's part (manual, after 5 trading days)

At end of each day, compare the VWAP/VAH/VAL values from:
- `GET /api/monitoring/vwap-validation` (server-side)
- Your TradingView Hub Sniper chart (TV VWAP indicator)

Calculate % error. If mean < 0.1% and max < 0.5%, Hub Sniper server-side port is greenlit.

---

## Item 3: Confluence Validation Gate

### Problem

The confluence engine is live and classifying signals as STANDALONE / CONFIRMED / CONVICTION, but we don't know if it actually improves outcomes. We need to compare performance of confluent signals vs standalone signals.

### What to build

A validation query endpoint that pulls from the existing `signals` table and `outcome_log.jsonl` (or `closed_positions` table) to compute:

1. Win rate: CONFIRMED/CONVICTION vs STANDALONE
2. Average R:R achieved: confluent vs standalone
3. Total signals in each bucket
4. Whether the 12% win rate improvement / 0.3R average improvement threshold is met

**File: `backend/analytics/confluence_validation.py`** (new file)

```python
"""
Confluence Validation Gate

Compares 24-hour outcomes of CONFIRMED/CONVICTION signals vs STANDALONE.
Success criteria: confluence beats standalone by ≥12% win rate or ≥0.3R avg.

Endpoint: GET /api/analytics/confluence-validation
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)


async def compute_confluence_validation(days: int = 30) -> Dict:
    """
    Compare outcomes of confluent vs standalone signals.

    Reads from:
    - signals table: confluence_tier, created_at
    - closed_positions table: pnl_dollars, signal_id
    - trades table: pnl_dollars, signal_id

    Returns stats for CONFIRMED+CONVICTION vs STANDALONE.
    """
    pool = await get_postgres_client()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with pool.acquire() as conn:
        # Get all signals with outcomes that have confluence_tier
        rows = await conn.fetch("""
            SELECT
                s.signal_id,
                s.ticker,
                s.confluence_tier,
                s.score_v2 AS score,
                s.created_at,
                s.trade_outcome,
                t.pnl_dollars,
                t.entry_price,
                t.exit_price,
                t.stop_loss
            FROM signals s
            LEFT JOIN trades t ON t.signal_id = s.signal_id AND t.status = 'closed'
            WHERE s.created_at > $1
              AND s.trade_outcome IS NOT NULL
              AND s.confluence_tier IS NOT NULL
            ORDER BY s.created_at DESC
        """, cutoff)

    if not rows:
        return {
            "status": "insufficient_data",
            "message": f"No signals with both outcomes and confluence tiers in last {days} days",
            "total_signals": 0,
            "verdict": "WAITING",
        }

    # Bucket signals
    confluent = {"wins": 0, "losses": 0, "total": 0, "pnl_sum": 0.0, "r_sum": 0.0}
    standalone = {"wins": 0, "losses": 0, "total": 0, "pnl_sum": 0.0, "r_sum": 0.0}

    for row in rows:
        tier = row["confluence_tier"] or "STANDALONE"
        outcome = row["trade_outcome"] or ""
        pnl = float(row["pnl_dollars"] or 0)

        # Compute R:R if we have the data
        r_achieved = 0.0
        if row["entry_price"] and row["stop_loss"] and row["exit_price"]:
            risk = abs(float(row["entry_price"]) - float(row["stop_loss"]))
            if risk > 0:
                r_achieved = (float(row["exit_price"]) - float(row["entry_price"])) / risk

        bucket = confluent if tier in ("CONFIRMED", "CONVICTION") else standalone
        bucket["total"] += 1
        bucket["pnl_sum"] += pnl
        bucket["r_sum"] += r_achieved
        if outcome == "WIN":
            bucket["wins"] += 1
        elif outcome == "LOSS":
            bucket["losses"] += 1

    # Compute stats
    def stats(b):
        if b["total"] == 0:
            return {"win_rate": 0, "avg_r": 0, "avg_pnl": 0, "count": 0}
        return {
            "win_rate": round(b["wins"] / b["total"] * 100, 1),
            "avg_r": round(b["r_sum"] / b["total"], 2),
            "avg_pnl": round(b["pnl_sum"] / b["total"], 2),
            "count": b["total"],
            "wins": b["wins"],
            "losses": b["losses"],
        }

    conf_stats = stats(confluent)
    stan_stats = stats(standalone)

    # Verdict
    win_rate_diff = conf_stats["win_rate"] - stan_stats["win_rate"]
    r_diff = conf_stats["avg_r"] - stan_stats["avg_r"]

    total = confluent["total"] + standalone["total"]
    min_sample = 20  # Need at least 20 confluent signals

    if confluent["total"] < min_sample:
        verdict = "WAITING"
        verdict_detail = f"Need {min_sample - confluent['total']} more confluent signals with outcomes"
    elif win_rate_diff >= 12.0 or r_diff >= 0.3:
        verdict = "PASS"
        verdict_detail = f"Confluence adds value: +{win_rate_diff:.1f}% win rate, +{r_diff:.2f}R"
    else:
        verdict = "FAIL"
        verdict_detail = f"Confluence not adding enough: +{win_rate_diff:.1f}% win rate (need 12%), +{r_diff:.2f}R (need 0.3)"

    return {
        "status": "evaluated" if confluent["total"] >= min_sample else "collecting",
        "verdict": verdict,
        "verdict_detail": verdict_detail,
        "confluent": conf_stats,
        "standalone": stan_stats,
        "win_rate_diff": round(win_rate_diff, 1),
        "r_diff": round(r_diff, 2),
        "total_signals": total,
        "days_analyzed": days,
    }
```

### Wire the endpoint

**File: `backend/main.py`** — add:

```python
@app.get("/api/analytics/confluence-validation")
async def confluence_validation_endpoint(days: int = 30):
    """Compare outcomes: confluent (CONFIRMED/CONVICTION) vs STANDALONE signals."""
    from analytics.confluence_validation import compute_confluence_validation
    return await compute_confluence_validation(days=days)
```

### Shadow Mode Validation (combined)

The TODO also mentions "Shadow mode validation — compare Holy Grail + Scout server-side vs TV signal overlap." This is related: the server-side scanners are already running and producing signals. To validate them, add a log that records every server-side signal alongside the TV-originated signals for the same ticker/timeframe.

This doesn't need a separate script — both server-side and TV signals already land in the `signals` table with different `source` values. A query comparing them:

```python
# Add to confluence_validation.py or a new file
async def compute_shadow_validation(days: int = 5) -> Dict:
    """Compare server-side vs TradingView signal overlap."""
    pool = await get_postgres_client()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with pool.acquire() as conn:
        # Server-side signals (Holy Grail + Scout scanners)
        server_rows = await conn.fetch("""
            SELECT ticker, direction, strategy, created_at
            FROM signals
            WHERE created_at > $1
              AND source IN ('holy_grail_scanner', 'scout_scanner', 'SCANNER')
        """, cutoff)

        # TV-originated signals
        tv_rows = await conn.fetch("""
            SELECT ticker, direction, strategy, created_at
            FROM signals
            WHERE created_at > $1
              AND source IN ('tradingview', 'TRADINGVIEW', 'TV')
              AND strategy ILIKE ANY(ARRAY['%holy%grail%', '%scout%'])
        """, cutoff)

    # Match by ticker + direction within 30-min window
    matches = 0
    server_only = 0
    tv_only = 0

    server_set = set()
    for r in server_rows:
        key = (r["ticker"], r["direction"], r["created_at"].strftime("%Y-%m-%d %H"))
        server_set.add(key)

    tv_set = set()
    for r in tv_rows:
        key = (r["ticker"], r["direction"], r["created_at"].strftime("%Y-%m-%d %H"))
        tv_set.add(key)

    matches = len(server_set & tv_set)
    server_only = len(server_set - tv_set)
    tv_only = len(tv_set - server_set)
    total = matches + server_only + tv_only

    overlap_pct = round(matches / total * 100, 1) if total > 0 else 0

    return {
        "days_analyzed": days,
        "server_signals": len(server_rows),
        "tv_signals": len(tv_rows),
        "matches": matches,
        "server_only": server_only,
        "tv_only": tv_only,
        "overlap_pct": overlap_pct,
        "target_overlap_pct": 80,
        "verdict": "PASS" if overlap_pct >= 80 else ("WAITING" if total < 10 else "NEEDS_TUNING"),
    }
```

Add endpoint:
```python
@app.get("/api/analytics/shadow-validation")
async def shadow_validation_endpoint(days: int = 5):
    """Compare server-side scanner signals vs TradingView signals."""
    from analytics.confluence_validation import compute_shadow_validation
    return await compute_shadow_validation(days=days)
```

---

## Definition of Done

### tick_breadth
1. Late-session close bounces no longer overpower bearish average
2. Conflict handler replaces close signal with average-derived signal (not just dampening)
3. Agreement amplification added when close and avg confirm each other
4. Factor reads bearish during bearish sessions regardless of late close bounce

### Hub Sniper VWAP Validation
1. `vwap_validator.py` computes VWAP + ±2σ bands from yfinance 15-min bars
2. Background loop logs readings every 15 min during market hours
3. `GET /api/monitoring/vwap-validation` returns recent readings
4. After 5 trading days, Nick compares vs TradingView values manually

### Confluence Validation Gate
1. `confluence_validation.py` computes win rate + R:R for confluent vs standalone
2. `GET /api/analytics/confluence-validation` returns comparison + verdict
3. `GET /api/analytics/shadow-validation` returns server-side vs TV overlap %
4. Both endpoints self-report when insufficient data exists ("WAITING" verdict)

---

## What this brief does NOT do

- Does NOT port Hub Sniper to server-side (that's Phase A.3, gated on VWAP validation passing)
- Does NOT change the confluence engine itself (just measures its value)
- Does NOT auto-act on the validation results (Nick reviews manually)
- Does NOT touch VPS scripts

---

## Deployment

All Railway — push to `main`, auto-deploys. No VPS work needed.

## Verification

1. `curl .../api/bias/tick` during market hours — verify tick_breadth responds to avg, not just close
2. `curl .../api/monitoring/vwap-validation` — should return readings after first 15-min cycle
3. `curl .../api/analytics/confluence-validation` — should return stats or "WAITING" verdict
4. `curl .../api/analytics/shadow-validation` — should return overlap stats or "WAITING"
