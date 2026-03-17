# Brief 5A: STRC Circuit Breaker

**Target Agent:** Claude Code (VSCode)
**Phase:** 5 — Nemesis / STRC Circuit Breaker
**Depends On:** Nothing (standalone)
**Build Plan:** `docs/build-plans/phase-5-countertrend-lane.md`
**Olympus Approved:** March 16, 2026
**Titans Approved:** March 17, 2026

---

## What This Does

Adds a visual circuit breaker to the Stater Swap (crypto trading) UI that monitors STRC (Strategy Stretch Preferred Stock, ticker `STRC`). When STRC trades below $100 par value, a persistent warning banner appears above the Stater Swap price bar. This warns Nick that Strategy's ability to issue preferred stock and buy BTC (~$1.5B/week) is impaired — the structural BTC bid is weakening.

---

## Step 1: Backend — STRC Price Poller + Redis Cache

### 1A. Create `backend/circuit_breakers/strc_monitor.py` (NEW FILE)

This module fetches the STRC price from Polygon.io, caches it in Redis, and provides a helper for the frontend to query.

```python
"""
STRC Circuit Breaker Monitor

Polls STRC (Strategy Stretch Preferred Stock) price via Polygon.io.
Caches result in Redis. Frontend polls alongside existing crypto data.
When STRC < $100, Strategy's BTC buying mechanism is impaired.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
POLYGON_BASE = "https://api.polygon.io"
STRC_TICKER = "STRC"
STRC_PAR_VALUE = 100.0
STRC_CACHE_KEY = "circuit_breaker:strc"
STRC_ALERTED_KEY = "circuit_breaker:strc:alerted"
STRC_CACHE_TTL = 300  # 5 minutes
STRC_STALE_THRESHOLD = 900  # 15 minutes — if older, frontend shows stale warning


async def fetch_strc_price() -> Optional[float]:
    """Fetch STRC last trade price from Polygon.io. Falls back to yfinance if Polygon fails."""
    if not POLYGON_API_KEY:
        logger.warning("POLYGON_API_KEY not set — falling back to yfinance for STRC")
        return await _fetch_strc_yfinance()

    try:
        url = f"{POLYGON_BASE}/v2/last/trade/{STRC_TICKER}"
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, params={"apiKey": POLYGON_API_KEY})
            resp.raise_for_status()
            data = resp.json()
            price = data.get("results", {}).get("p")  # "p" = price in Polygon last trade
            if price is not None:
                return float(price)
            # Fallback: try snapshot endpoint
            url2 = f"{POLYGON_BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{STRC_TICKER}"
            resp2 = await client.get(url2, params={"apiKey": POLYGON_API_KEY})
            resp2.raise_for_status()
            data2 = resp2.json()
            day_data = data2.get("ticker", {}).get("day", {})
            return float(day_data.get("c") or day_data.get("vw") or 0) or None
    except Exception as e:
        logger.warning(f"Polygon STRC fetch failed: {e} — falling back to yfinance")
        return await _fetch_strc_yfinance()


async def _fetch_strc_yfinance() -> Optional[float]:
    """yfinance fallback for STRC price."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(STRC_TICKER)
        hist = ticker.history(period="1d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        logger.error(f"yfinance STRC fallback also failed: {e}")
        return None


async def update_strc_cache() -> Dict[str, Any]:
    """Fetch STRC price and update Redis cache. Called by scheduler."""
    from database.redis_client import get_redis

    price = await fetch_strc_price()
    now = datetime.now(timezone.utc).isoformat()

    if price is None:
        logger.warning("STRC price unavailable — cache not updated")
        return {"ok": False, "error": "price_unavailable"}

    payload = {
        "price": round(price, 2),
        "below_par": price < STRC_PAR_VALUE,
        "par_level": STRC_PAR_VALUE,
        "severity": "red" if price < 95 else ("amber" if price < 100 else "none"),
        "last_updated": now,
    }

    try:
        redis = await get_redis()
        await redis.set(STRC_CACHE_KEY, json.dumps(payload), ex=STRC_CACHE_TTL)
        logger.info(f"STRC cached: ${price:.2f} (below_par={payload['below_par']})")

        # One-time Discord alert on crossing below par
        if payload["below_par"]:
            alerted = await redis.get(STRC_ALERTED_KEY)
            if not alerted:
                await _send_strc_discord_alert(price)
                await redis.set(STRC_ALERTED_KEY, "1", ex=86400)  # 24h dedup
        else:
            # Reset alert flag when STRC recovers above par
            await redis.delete(STRC_ALERTED_KEY)

    except Exception as e:
        logger.error(f"Redis cache update failed for STRC: {e}")
        return {"ok": False, "error": str(e)}

    return {"ok": True, "data": payload}


async def get_strc_status() -> Optional[Dict[str, Any]]:
    """Read STRC status from Redis cache. Returns None if no data."""
    from database.redis_client import get_redis

    try:
        redis = await get_redis()
        raw = await redis.get(STRC_CACHE_KEY)
        if raw:
            data = json.loads(raw)
            # Check staleness
            last_updated = datetime.fromisoformat(data["last_updated"])
            age_seconds = (datetime.now(timezone.utc) - last_updated).total_seconds()
            data["stale"] = age_seconds > STRC_STALE_THRESHOLD
            return data
    except Exception as e:
        logger.warning(f"Failed to read STRC cache: {e}")
    return None


async def _send_strc_discord_alert(price: float) -> None:
    """One-time Discord alert when STRC crosses below par."""
    try:
        from utils.discord_sender import send_discord_message
        await send_discord_message(
            channel="signals",
            content=(
                f"\u26a0\ufe0f **STRC CIRCUIT BREAKER** \u26a0\ufe0f\n"
                f"STRC is below par at **${price:.2f}** (par = $100.00)\n"
                f"Strategy's preferred stock issuance mechanism is impaired.\n"
                f"BTC structural bid (~$1.5B/week) at risk."
            ),
        )
    except Exception as e:
        logger.warning(f"Discord STRC alert failed: {e}")
```

Also create the `__init__.py`:

```python
# backend/circuit_breakers/__init__.py
```

### 1B. Add STRC endpoint to crypto market router

**File:** `backend/api/crypto_market.py`

**Find** the last route in the file (the `@router.get("/binance/klines")` function). **After the entire function**, append:

```python


@router.get("/circuit-breakers")
async def get_circuit_breakers():
    """Return circuit breaker status for crypto-relevant risk monitors."""
    from circuit_breakers.strc_monitor import get_strc_status
    strc = await get_strc_status()
    return {
        "status": "success",
        "circuit_breakers": {
            "strc": strc,
        },
    }
```

This makes it available at `GET /crypto/circuit-breakers`.

### 1C. Add STRC poller to scheduler

**Find** the scheduler file that runs periodic tasks. Search for:
```
grep -rn "scheduler\|cron\|periodic\|apscheduler" backend/ --include="*.py" -l
```

In the scheduler that handles periodic market data tasks, add:

```python
from circuit_breakers.strc_monitor import update_strc_cache
```

And schedule it to run every 5 minutes during market hours (9:30 AM - 4:00 PM ET, weekdays). If using APScheduler:
```python
scheduler.add_job(update_strc_cache, 'interval', minutes=5, id='strc_circuit_breaker')
```

If using a different scheduling pattern, match the existing pattern.

---

## Step 2: Frontend — STRC Warning Banner in Stater Swap

### 2A. Find the Stater Swap section

**Search for the injection point:**
```
grep -n "Stater\|stater\|crypto-section\|crypto-header\|btc-price\|cryptoSection" frontend/index.html frontend/app.js
```

The STRC warning banner goes **above** the main price bar in the Stater Swap section. It should be the first child of the crypto section container.

### 2B. Add banner HTML

**In `frontend/index.html`**, find the Stater Swap / crypto section container. **Immediately inside** the opening tag of that container (before the price bar), insert:

```html
<!-- STRC Circuit Breaker Banner -->
<div id="strc-circuit-breaker" class="strc-banner" style="display: none;">
    <div class="strc-banner-content">
        <span class="strc-banner-icon">\u26a0\ufe0f</span>
        <span class="strc-banner-text">
            <strong>STRC BELOW PAR (<span id="strc-price">--</span>)</strong>
            \u2014 Strategy funding at risk. Structural BTC bid weakening.
        </span>
    </div>
</div>
```

### 2C. Add banner CSS

**In `frontend/styles.css`**, add at the end of the file:

```css
/* ===== STRC Circuit Breaker Banner ===== */
.strc-banner {
    padding: 8px 16px;
    border-radius: 6px;
    margin-bottom: 8px;
    font-size: 13px;
    line-height: 1.4;
    transition: background-color 0.3s ease;
}

.strc-banner.severity-amber {
    background: rgba(245, 158, 11, 0.15);
    border: 1px solid rgba(245, 158, 11, 0.4);
    color: #f59e0b;
}

.strc-banner.severity-red {
    background: rgba(239, 68, 68, 0.15);
    border: 1px solid rgba(239, 68, 68, 0.4);
    color: #ef4444;
}

.strc-banner.severity-stale {
    background: rgba(156, 163, 175, 0.15);
    border: 1px solid rgba(156, 163, 175, 0.4);
    color: #9ca3af;
}

.strc-banner-content {
    display: flex;
    align-items: center;
    gap: 8px;
}

.strc-banner-icon {
    font-size: 16px;
    flex-shrink: 0;
}

.strc-banner-text strong {
    font-weight: 600;
}
```

### 2D. Add banner JavaScript

**In `frontend/app.js`**, find the function that polls crypto market data (likely fetches from `/crypto/market`). Search for:
```
grep -n "crypto/market\|fetchCrypto\|loadCrypto\|updateCrypto" frontend/app.js
```

**Inside or after** that polling function, add a call to fetch circuit breakers:

```javascript
// STRC Circuit Breaker polling
async function updateSTRCBanner() {
    try {
        const resp = await fetch('/crypto/circuit-breakers', {
            headers: { 'Authorization': `Bearer ${getAuthToken()}` }
        });
        if (!resp.ok) return;
        const data = await resp.json();
        const strc = data?.circuit_breakers?.strc;
        const banner = document.getElementById('strc-circuit-breaker');
        if (!banner) return;

        if (!strc || strc.severity === 'none') {
            banner.style.display = 'none';
            return;
        }

        // Show banner
        banner.style.display = 'block';
        banner.className = 'strc-banner';

        if (strc.stale) {
            banner.classList.add('severity-stale');
            document.getElementById('strc-price').textContent = 'DATA STALE';
        } else {
            banner.classList.add(`severity-${strc.severity}`);
            document.getElementById('strc-price').textContent = `$${strc.price.toFixed(2)}`;
        }
    } catch (e) {
        console.warn('STRC circuit breaker fetch failed:', e);
    }
}
```

**Then**, find where the crypto market data polling interval is set (e.g., `setInterval` for `/crypto/market`). Add `updateSTRCBanner()` to the same interval, or create a separate interval:

```javascript
// Poll STRC every 60 seconds (doesn't need to be as fast as crypto market data)
setInterval(updateSTRCBanner, 60000);
updateSTRCBanner(); // initial load
```

**Important:** If the frontend uses `getAuthToken()` or similar for API calls, use the same pattern. Search for existing `fetch('/crypto/` calls to match the auth pattern.

---

## Step 3: Add STRC to Watchlist (DB)

Run this SQL against the Supabase PostgreSQL database to add STRC to the watchlist:

```sql
INSERT INTO watchlist_tickers (ticker, name, sector, list_name)
VALUES ('STRC', 'Strategy Stretch Preferred Stock', 'Financials', 'circuit_breaker')
ON CONFLICT (ticker) DO NOTHING;
```

If the `watchlist_tickers` table doesn't have these exact columns, adapt to match the existing schema. Search:
```
grep -rn "watchlist_tickers\|CREATE TABLE.*watchlist" migrations/ backend/ --include="*.sql" --include="*.py"
```

---

## Testing Checklist

1. **STRC price fetch:** Call `update_strc_cache()` manually or hit `GET /crypto/circuit-breakers` — should return STRC price and `below_par` status
2. **Banner visibility:** When STRC < $100, banner should appear in Stater Swap with amber ($95-100) or red (<$95) styling
3. **Banner hidden:** When STRC >= $100, banner should be completely hidden (`display: none`)
4. **Staleness:** If Redis key is >15 min old, banner should show "DATA STALE" with gray styling
5. **Discord alert:** First time STRC crosses below $100, a one-time Discord alert fires. Does NOT fire again until STRC recovers and re-crosses.

## Definition of Done
- [ ] `backend/circuit_breakers/strc_monitor.py` created and fetches STRC via Polygon.io (yfinance fallback)
- [ ] `GET /crypto/circuit-breakers` endpoint returns STRC status
- [ ] STRC poller scheduled every 5 minutes
- [ ] Redis cache with 5-min TTL + staleness detection at 15 min
- [ ] Stater Swap UI shows sticky warning banner when STRC < $100
- [ ] Amber/red color coding based on severity
- [ ] Banner hidden when STRC >= $100
- [ ] Discord one-time alert on par crossing
- [ ] STRC added to watchlist
