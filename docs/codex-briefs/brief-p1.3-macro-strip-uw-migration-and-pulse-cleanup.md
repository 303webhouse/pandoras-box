# Brief — P1.3: Macro Strip Polygon→UW Migration + Drop Redundant LIVE Pulse

**Status:** Ready for CC — TIME-SENSITIVE backend bug
**Source:** Tonight's verification 2026-04-27 — Nick noticed the macro ticker tape isn't visible. Diagnostic via direct curl revealed root cause is NOT a CSS/layout bug.
**Estimated effort:** ~30 min (small backend migration + small frontend cleanup)
**Dependencies:** Builds on P1.2 (commit `5c26923`). Apply ASAP — this is a backend regression that's been live since this morning.

---

## What's actually broken

The macro ticker tape isn't a CSS issue. **The backend has been silently returning `{"tickers": []}` since this morning.**

Direct curl from VPS to the production endpoint just now:
```
$ curl -s "https://pandoras-box-production.up.railway.app/api/macro/strip"
{"tickers":[],"is_market_hours":false,"timestamp":"2026-04-28T02:59:12.740131+00:00"}
```

**Root cause:** `backend/api/macro_strip.py` was **missed by today's UW migration cleanup**. The file makes raw HTTP calls to Polygon's snapshot API (`https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers`). Polygon's plan was canceled this morning. The fetch silently fails (likely a 403), the `for t in data.get("tickers", [])` loop runs zero iterations, and an empty `result_data` is returned.

**Why we missed it in cleanup commit `eb3a250`:** Today's grep targeted `polygon_options|polygon_equities|mtm_compare|polygon_health` (deleted module names). `macro_strip.py` doesn't import any of those — it makes raw `aiohttp.ClientSession()` calls directly to the Polygon URL. The cleanup grep was scoped too narrowly.

**Lesson for future cleanup briefs:** Always grep for both module names AND raw URLs/API keys (`polygon.io`, `POLYGON_API_KEY`, `SNAPSHOT_URL`). Captured for TODO.

While we're in there, drop the LIVE pulse from the macro strip. Per Nick's UX feedback tonight: when the ticker tape is scrolling, that motion IS the live signal. A separate pulse is redundant. Heatmap pulse stays (cells don't move).

---

## Pre-flight checks

```bash
cd /c/trading-hub
git status                                    # Should be clean
git pull --rebase                             # Pull latest

# Confirm the bug — these grep results explain everything
grep -n "POLYGON_API_KEY\|SNAPSHOT_URL\|polygon.io" backend/api/macro_strip.py
# Should appear multiple times — that's what we're removing

# Confirm UW alternative exists
grep -n "^async def get_snapshot" backend/integrations/uw_api.py
# Should output one line

# Confirm endpoint is currently broken
curl -s "https://pandoras-box-production.up.railway.app/api/macro/strip" | python3 -m json.tool
# Should show "tickers": [] (the bug)
```

If any check fails, abort and report. If `get_snapshot` is missing from `uw_api.py`, do not proceed.

---

## Phase A — Migrate macro_strip.py from Polygon to UW

**File:** `backend/api/macro_strip.py`

This is a full file rewrite — small enough that a complete replacement is cleaner than line-by-line edits.

### A.1 — Replace the entire file contents

Read the existing file first to confirm structure, then replace with:

```python
"""
Macro Strip — persistent cross-asset ticker strip.

Fetches latest quotes for ~16 macro ETF proxies in parallel via UW snapshot.
Cached 10s during market hours, 5min when closed.

Migration history:
- Originally Polygon batch snapshot endpoint
- Migrated to UW (via get_snapshot) on 2026-04-28 after Polygon plan cancellation
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter

from database.redis_client import get_redis_client
from integrations.uw_api import get_snapshot

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/macro", tags=["macro"])

# Macro tickers: ETF proxies for cross-asset monitoring
MACRO_TICKERS = {
    "SPY":  {"label": "SPY",  "name": "S&P 500"},
    "QQQ":  {"label": "QQQ",  "name": "Nasdaq"},
    "IWM":  {"label": "IWM",  "name": "Russell 2K"},
    "USO":  {"label": "OIL",  "name": "Crude Oil"},
    "GLD":  {"label": "GOLD", "name": "Gold"},
    "SHY":  {"label": "2Y",   "name": "2Y Treasury"},
    "IEF":  {"label": "10Y",  "name": "7-10Y Treasury"},
    "TLT":  {"label": "20Y",  "name": "20Y Treasury"},
    "UUP":  {"label": "DXY",  "name": "US Dollar"},
    "HYG":  {"label": "HY",   "name": "High Yield"},
    "EWG":  {"label": "DE",   "name": "Germany (DAX)"},
    "EWU":  {"label": "UK",   "name": "United Kingdom (FTSE)"},
    "FXI":  {"label": "CN",   "name": "China Large-Cap"},
    "EWY":  {"label": "KR",   "name": "South Korea (KOSPI)"},
    "EWJ":  {"label": "JP",   "name": "Japan (Nikkei)"},
    "INDA": {"label": "IN",   "name": "India (Nifty)"},
}

MACRO_CACHE_KEY = "macro:strip"
MACRO_CACHE_TTL_LIVE = 10     # 10s during market hours
MACRO_CACHE_TTL_CLOSED = 300  # 5 min when closed


def _is_market_hours():
    import pytz
    et = datetime.now(pytz.timezone("America/New_York"))
    if et.weekday() >= 5:
        return False
    if et.hour == 9 and et.minute >= 30:
        return True
    if 10 <= et.hour < 16:
        return True
    return False


async def _fetch_one(ticker: str) -> dict | None:
    """Fetch one snapshot via UW; return ticker entry or None on failure."""
    try:
        snap = await get_snapshot(ticker)
        if not snap:
            return None
        info = MACRO_TICKERS[ticker]
        # get_snapshot returns Polygon-compatible schema: day.c (close), prevDay.c (prev close)
        day = snap.get("day") or {}
        prev = snap.get("prevDay") or {}
        price = day.get("c") or prev.get("c") or 0
        prev_close = prev.get("c") or 0
        change_pct = (
            round((price - prev_close) / prev_close * 100, 2)
            if prev_close
            else 0
        )
        return {
            "ticker": ticker,
            "label": info["label"],
            "name": info["name"],
            "price": round(price, 2) if price else 0,
            "change_pct": change_pct,
        }
    except Exception as e:
        logger.warning("Macro strip UW fetch failed for %s: %s", ticker, e)
        return None


@router.get("/strip")
async def get_macro_strip():
    """Return cross-asset macro data for the persistent ticker strip."""
    redis = await get_redis_client()

    if redis:
        try:
            cached = await redis.get(MACRO_CACHE_KEY)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    tickers = list(MACRO_TICKERS.keys())

    # Fetch all snapshots in parallel via UW
    results = await asyncio.gather(
        *(_fetch_one(t) for t in tickers),
        return_exceptions=False,
    )
    result_data = [r for r in results if r is not None]

    # Sort by MACRO_TICKERS order (gather() may return in any order)
    ticker_order = list(MACRO_TICKERS.keys())
    result_data.sort(
        key=lambda x: ticker_order.index(x["ticker"]) if x["ticker"] in ticker_order else 99
    )

    result = {
        "tickers": result_data,
        "is_market_hours": _is_market_hours(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if redis and result_data:
        ttl = MACRO_CACHE_TTL_LIVE if _is_market_hours() else MACRO_CACHE_TTL_CLOSED
        try:
            await redis.set(MACRO_CACHE_KEY, json.dumps(result), ex=ttl)
        except Exception:
            pass

    return result
```

**Key changes vs the broken version:**
- ❌ Removed: `import aiohttp`, `import os`, `POLYGON_API_KEY`, `SNAPSHOT_URL`
- ✅ Added: `import asyncio`, `from integrations.uw_api import get_snapshot`
- ✅ Replaced batch Polygon HTTP call with `asyncio.gather()` over 16 parallel `get_snapshot()` calls
- ✅ Added `_fetch_one()` helper that gracefully handles per-ticker failures (one failed ticker doesn't kill the whole strip)
- ✅ Logger now says "Macro strip UW fetch failed" instead of "Macro strip Polygon fetch failed"
- ✅ Updated module docstring to reflect the migration
- ✅ Cache TTL behavior unchanged (10s live / 5min closed)
- ✅ Response schema unchanged — frontend `renderMacroStrip` continues to work without modification

### A.2 — Verify the file syntax-checks

```bash
python3 -c "import ast; ast.parse(open('backend/api/macro_strip.py').read())"
```

If this errors, abort and report.

### A.3 — Clear the empty cache entry

The current empty result is cached in Redis. If we don't clear it, Railway will serve stale empty data for up to 5 minutes after deploy.

```bash
# After Railway redeploy completes (~90s), curl the endpoint twice:
# First call may return empty cache; second call should return fresh UW data.
sleep 95
curl -s "https://pandoras-box-production.up.railway.app/api/macro/strip" | python3 -m json.tool
sleep 5
curl -s "https://pandoras-box-production.up.railway.app/api/macro/strip" | python3 -m json.tool
```

**Expected:** Second call returns a `tickers` array with 16 entries (or close to it — some thin tickers might fail individual fetches and be excluded). If both calls return empty, the migration didn't work — abort and roll back.

If you want to force-clear the cache without waiting:
```bash
# From any process with Redis access:
# DEL macro:strip
# But waiting 5min after deploy is simpler.
```

---

## Phase B — Drop the LIVE pulse from the macro strip

**Files:** `frontend/app.js` + `frontend/styles.css`

**Why:** When the ticker tape is scrolling horizontally, that motion is the live signal. Adding a pulsing dot is redundant. The heatmap pulse stays (cells don't have inherent motion).

### B.1 — Remove pulse wire from `loadMacroStrip`

**File:** `frontend/app.js`, around line 12024

**Find:**

```javascript
// ===== MACRO TICKER STRIP =====
async function loadMacroStrip() {
    try {
        const resp = await fetch(`${API_URL}/macro/strip`);
        if (!resp.ok) return;
        const data = await resp.json();
        renderMacroStrip(data.tickers);

        // P1.1: live refresh pulse — anchor to parent of scrolling element
        var stripInner = document.getElementById('macroStripInner');
        var stripContainer = stripInner ? stripInner.parentElement : null;
        var pulseTarget = stripContainer
            ? (stripContainer.querySelector('.macro-strip-status') || stripContainer)
            : null;
        ensureLiveDataIndicator(pulseTarget, 'macroStrip', 'LIVE');
        pulseLiveDataIndicator('macroStrip');
    } catch (e) {
        console.error('Macro strip load failed:', e);
    }
}
```

**Replace with:**

```javascript
// ===== MACRO TICKER STRIP =====
async function loadMacroStrip() {
    try {
        const resp = await fetch(`${API_URL}/macro/strip`);
        if (!resp.ok) return;
        const data = await resp.json();
        renderMacroStrip(data.tickers);
        // P1.3: dropped LIVE pulse — scrolling ticker motion IS the live signal
    } catch (e) {
        console.error('Macro strip load failed:', e);
    }
}
```

### B.2 — Remove the macro-strip-specific CSS rules

**File:** `frontend/styles.css`

**Find:**

```css
/* P1.2: Macro strip live indicator positioning (fixes ticker disappearance) */
.macro-strip {
    position: relative;
}

.macro-strip .live-data-indicator {
    position: absolute;
    top: 50%;
    right: 12px;
    transform: translateY(-50%);
    z-index: 2;
    background: rgba(10, 14, 39, 0.7);
    -webkit-backdrop-filter: blur(4px);
    backdrop-filter: blur(4px);
    padding: 2px 8px;
    border-radius: 10px;
    pointer-events: none;
    margin-left: 0;  /* Override the 12px default margin from .live-data-indicator */
}
```

**Replace with:**

```css
/* P1.3: Macro strip pulse removed — scrolling ticker motion IS the live signal.
   The .macro-strip's existing display:flex/overflow:hidden behavior is unchanged. */
```

### B.3 — Clean up any orphaned indicator in the live DOM

The pulse element may already be in the DOM from the previous deploy. Add a one-shot cleanup at the start of `loadMacroStrip` to remove any existing indicator:

**File:** `frontend/app.js`

**Find** (the function as just edited in B.1):

```javascript
async function loadMacroStrip() {
    try {
        const resp = await fetch(`${API_URL}/macro/strip`);
        if (!resp.ok) return;
        const data = await resp.json();
        renderMacroStrip(data.tickers);
        // P1.3: dropped LIVE pulse — scrolling ticker motion IS the live signal
    } catch (e) {
        console.error('Macro strip load failed:', e);
    }
}
```

**Replace with:**

```javascript
async function loadMacroStrip() {
    try {
        // P1.3: cleanup any leftover LIVE indicator from prior deploys
        var leftover = document.querySelector('.macro-strip .live-data-indicator');
        if (leftover) leftover.remove();

        const resp = await fetch(`${API_URL}/macro/strip`);
        if (!resp.ok) return;
        const data = await resp.json();
        renderMacroStrip(data.tickers);
        // P1.3: scrolling ticker motion IS the live signal — no separate pulse
    } catch (e) {
        console.error('Macro strip load failed:', e);
    }
}
```

The cleanup runs once on first call after deploy and idempotently every refresh after.

---

## Sequenced commit plan

Two commits — backend migration first (with deploy wait), then frontend cleanup (no wait).

**Commit 1 — Backend migration (Phase A)**

```bash
# Apply Phase A.1 (full file replacement)
python3 -c "import ast; ast.parse(open('backend/api/macro_strip.py').read())"
git add backend/api/macro_strip.py
git commit -m "P1.3: migrate macro_strip from Polygon (cancelled plan) to UW snapshots"
git push origin main
# Wait ~95s for Railway deploy
sleep 95
# Phase A.3 verification
curl -s "https://pandoras-box-production.up.railway.app/api/macro/strip" | python3 -m json.tool
# May still show empty cache — wait another 5s and retry
sleep 5
curl -s "https://pandoras-box-production.up.railway.app/api/macro/strip" | python3 -m json.tool
```

If the second curl still returns `tickers: []`, abort and roll back. The migration didn't work and we need to debug before continuing.

**Commit 2 — Frontend cleanup (Phase B)**

```bash
# Apply Phase B.1, B.2, B.3
node --check frontend/app.js
git add frontend/app.js frontend/styles.css
git commit -m "P1.3 frontend: drop redundant LIVE pulse from macro strip (motion is the signal)"
git push origin main
# No deploy wait — frontend served as static files
```

---

## Verification checklist

After both commits land. Run all 7 checks:

### Backend — direct curl

1. **Macro strip endpoint returns ticker data** (NOT empty):
   ```bash
   curl -s "https://pandoras-box-production.up.railway.app/api/macro/strip" \
     | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'tickers: {len(d[\"tickers\"])}'); print(d['tickers'][:2] if d['tickers'] else 'EMPTY')"
   ```
   PASS if output shows `tickers: 12` or higher (out of 16). FAIL if `EMPTY` or `tickers: 0`.

2. **A SPY entry exists** (smoke test for the most-watched ticker):
   ```bash
   curl -s "https://pandoras-box-production.up.railway.app/api/macro/strip" \
     | python3 -c "import json,sys; d=json.load(sys.stdin); spy=[t for t in d['tickers'] if t['ticker']=='SPY']; print(spy[0] if spy else 'NO_SPY')"
   ```
   PASS if SPY entry has `price` (not 0) and `change_pct` populated. FAIL if `NO_SPY` or zero price.

3. **No Polygon references remain in macro_strip.py**:
   ```bash
   grep -i "polygon" backend/api/macro_strip.py
   ```
   PASS if zero matches (only comments/history allowed).

### Frontend — browser

4. **Macro ticker tape is visible and scrolling** across the top of Agora. PASS/FAIL.
   *(The whole point of this brief.)*

5. **No LIVE pulse on macro strip** — the ticker scrolls without any separate pulse indicator. PASS/FAIL.

6. **Heatmap pulse still works** — small pulsing dot in the top-left of the sector heatmap, flashes every ~10s. PASS/FAIL.
   *(Confirms we only removed the macro-specific pulse, not the heatmap pulse.)*

7. **No console errors** mentioning `macroStrip`, `live-data`, `pulseLiveData`. PASS/FAIL.

---

## Known risks & non-goals

- **UW basic plan rate limit (120/min):** Adding 16 parallel UW calls per refresh cycle. With 10s cache TTL during market hours, that's 6 cycles/min × 16 calls = 96 calls/min on the macro strip alone. Well under 120 limit but tight if combined with other busy endpoints. Daily count was 9,470/20,000 today; this will add ~150–200/day. Comfortable headroom remains.
- **Some macro tickers may fail individual fetches.** EWG, FXI, EWY, EWJ, INDA are international ETFs — UW data quality varies. The `_fetch_one` helper handles per-ticker failures gracefully — one bad ticker doesn't kill the strip. Verify in check 1 that we get ≥12/16 tickers.
- **The 5-minute closed-market cache means tomorrow's 9:30 AM ET reload may take up to 5 min to refresh.** Accept this — bumping to 30s when closed is overkill.
- **Non-goal: backfilling missing extended-hours data.** UW's snapshot returns last close + previous close. During pre-market and after-hours, prices may not move. That's fine; the ticker tape's purpose is "what did the day do," not "what is happening this exact second."
- **Non-goal: adding new macro tickers (DXY direct, BTC, etc).** The 16-ticker list is unchanged from Polygon era. Future expansion is a separate feature request.

---

## Rollback plan

If P1.3 makes things worse:

```bash
# Revert backend (Commit 1):
git revert <commit-1-sha>
git push origin main
# Wait for redeploy. The endpoint will return to "broken (empty)" state but at least
# nothing else is affected.

# Revert frontend (Commit 2):
git revert <commit-2-sha>
git push origin main
# This restores the LIVE pulse code, which we already know was working visually
# but creating UX clutter.
```

---

## What this delivers

After P1.3 lands:

- **Macro ticker tape is back** — scrolling 16 cross-asset tickers (SPY/QQQ/IWM/oil/gold/Treasuries/DXY/HY/global ETFs) with live prices and daily change %
- **Backend is fully off Polygon** for the macro strip (the last surviving Polygon dependency in the hub, now eliminated)
- **No redundant LIVE pulse** on the ticker tape — motion IS the signal
- **Heatmap pulse retained** — for visualizations without inherent motion, the pulse still serves its purpose

**Total code change: ~120 lines backend rewrite, ~25 lines frontend cleanup.** Zero new dependencies. Same response schema.

---

## Follow-ups for TODO (not in P1.3)

- **Cleanup grep discipline:** Today's UW migration cleanup grep targeted module names only. The macro_strip.py bug shows we also need to grep for raw URLs and API key env vars when deprecating a data source. Capture as a permanent operational reminder.
- **Add a "no fully-empty data feeds" health check:** If a major endpoint like `/api/macro/strip` ever returns `tickers: []` for >2 consecutive cycles, fire a Discord alert. Different scope than AE2 budget alarms — captured for AE6 or similar follow-up.
- **PROJECT_RULES.md update next time it's touched:** The "When deprecating a data source" section should explicitly call out: also grep for the deprecated provider's URLs (e.g. `polygon.io`, `financialmodelingprep.com`) and env var names (e.g. `POLYGON_API_KEY`, `FMP_API_KEY`) — not just module names.
