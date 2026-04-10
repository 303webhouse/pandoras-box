# BRIEF: ARGUS P1A HOTFIX — Price Range Enrichment for Freshness Penalty
## Priority: P0 (blocks P1A from working) | System: Backend pipeline
## Date: 2026-04-10
## Depends on: ARGUS P1 already deployed (commit 117c87b)

---

## THE PROBLEM

The freshness penalty code in `trade_ideas_scorer.py` (lines ~440-480) is correct
but will NEVER fire. It looks for `metadata.range_consumed` or `metadata.ten_day_high`
/ `metadata.ten_day_low`, but nothing in the pipeline populates these values.

The CTA Scanner PineScript doesn't send 10-day range data. The webhook handler
doesn't compute it. There is no Polygon or yfinance call to fetch it.

**Result: The highest-impact change from the entire ARGUS brief is dead code.**

## THE FIX

Add a price range enrichment step in `backend/signals/pipeline.py` BEFORE the
`apply_scoring()` call. This step fetches 10-day daily bars from Polygon (primary)
or yfinance (fallback), computes the range, and injects it into signal metadata.

### File: `backend/signals/pipeline.py`

Find the section where `apply_scoring(signal_data)` is called. BEFORE that call,
add a new function call:

```python
# Enrich with 10-day price range for freshness penalty
signal_data = await enrich_price_range(signal_data)
```

### New function — add to `pipeline.py` or a new file `backend/signals/price_enrichment.py`:

```python
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("pipeline")

async def enrich_price_range(signal_data: dict) -> dict:
    """
    Fetch 10-day daily bars for the signal's ticker and inject
    ten_day_high, ten_day_low, and range_consumed into metadata.
    This feeds the freshness penalty in trade_ideas_scorer.py.
    """
    ticker = (signal_data.get("ticker") or "").upper()
    entry_price = signal_data.get("entry_price")
    direction = (signal_data.get("direction") or "").upper()

    if not ticker or not entry_price or float(entry_price) <= 0:
        return signal_data

    metadata = signal_data.get("metadata") or {}
    if isinstance(metadata, str):
        import json
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}

    # Skip if already enriched
    if "ten_day_high" in metadata:
        return signal_data

    try:
        # Try Polygon first (primary data source)
        ten_day_high, ten_day_low = await _fetch_range_polygon(ticker)
    except Exception as e:
        logger.debug("Polygon range fetch failed for %s: %s", ticker, e)
        try:
            # Fallback to yfinance
            ten_day_high, ten_day_low = await _fetch_range_yfinance(ticker)
        except Exception as e2:
            logger.debug("yfinance range fetch also failed for %s: %s", ticker, e2)
            return signal_data

    if ten_day_high is None or ten_day_low is None or ten_day_high <= ten_day_low:
        return signal_data

    # Compute range_consumed
    entry = float(entry_price)
    rng = ten_day_high - ten_day_low
    if direction in ("LONG", "BUY", "BULLISH"):
        range_consumed = (entry - ten_day_low) / rng
    else:
        range_consumed = (ten_day_high - entry) / rng
    range_consumed = max(0.0, min(1.0, range_consumed))

    metadata["ten_day_high"] = round(ten_day_high, 4)
    metadata["ten_day_low"] = round(ten_day_low, 4)
    metadata["range_consumed"] = round(range_consumed, 4)
    signal_data["metadata"] = metadata

    logger.info("Price range enriched for %s: hi=%.2f lo=%.2f consumed=%.0f%%",
                ticker, ten_day_high, ten_day_low, range_consumed * 100)
    return signal_data
```

### Helper: Polygon fetch

```python
import httpx
import os

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")

async def _fetch_range_polygon(ticker: str) -> tuple:
    """Fetch 10-day high/low from Polygon daily bars."""
    end = datetime.utcnow().strftime("%Y-%m-%d")
    start = (datetime.utcnow() - timedelta(days=15)).strftime("%Y-%m-%d")
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day"
        f"/{start}/{end}?adjusted=true&sort=desc&limit=10"
        f"&apiKey={POLYGON_API_KEY}"
    )
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    results = data.get("results", [])
    if not results or len(results) < 3:
        raise ValueError(f"Not enough bars for {ticker}: {len(results)}")
    highs = [bar["h"] for bar in results]
    lows = [bar["l"] for bar in results]
    return max(highs), min(lows)
```

### Helper: yfinance fallback

```python
import asyncio

def _fetch_range_yfinance_sync(ticker: str) -> tuple:
    """Synchronous yfinance fetch (run in executor)."""
    import yfinance as yf
    tk = yf.Ticker(ticker)
    hist = tk.history(period="10d")
    if hist.empty or len(hist) < 3:
        raise ValueError(f"Not enough yfinance data for {ticker}")
    return float(hist["High"].max()), float(hist["Low"].min())

async def _fetch_range_yfinance(ticker: str) -> tuple:
    """Async wrapper for yfinance."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_range_yfinance_sync, ticker)
```

---

## WHERE TO WIRE IT IN

In `pipeline.py`, find the line where `apply_scoring` is called. It should look
something like:

```python
signal_data = await apply_scoring(signal_data)
```

Add the enrichment call BEFORE it:

```python
# P1A hotfix: fetch 10-day price range for freshness penalty
from signals.price_enrichment import enrich_price_range
signal_data = await enrich_price_range(signal_data)

signal_data = await apply_scoring(signal_data)
```

## VERIFICATION

After deploying, wait for the next CTA Scanner signal to fire during market hours.
Check the signal's `triggering_factors` in the DB:

```sql
SELECT ticker, score, triggering_factors->'freshness' as freshness
FROM signals ORDER BY timestamp DESC LIMIT 5;
```

The `freshness` field should now show:
```json
{"range_consumed": 0.45, "penalty": 0}
```

or for a late signal:
```json
{"range_consumed": 0.82, "penalty": -15}
```

If `range_consumed` is still null, the enrichment step isn't reaching the signal
before scoring. Check Railway logs for "Price range enriched" log lines.

## DEFINITION OF DONE

- [ ] `enrich_price_range` function exists and is called before `apply_scoring`
- [ ] Polygon API key is set in Railway env vars (check `POLYGON_API_KEY`)
- [ ] First signal after deploy shows `range_consumed` in triggering_factors
- [ ] Late signals (range_consumed > 0.70) show negative freshness_penalty in score
