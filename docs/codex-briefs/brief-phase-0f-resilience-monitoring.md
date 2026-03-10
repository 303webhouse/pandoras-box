# Brief: Phase 0F — Resilience & Monitoring

**Priority:** Phase 0 — Code hygiene / infrastructure protection
**Target:** VPS (`/opt/openclaw/workspace/scripts/`) + Railway backend
**Estimated time:** 2-3 hours
**Source:** GPT-5.4 audit (March 9) + operational experience
**Repo:** `303webhouse/pandoras-box` (branch: `main`)

---

## Overview

Build four lightweight monitoring and resilience features that prevent silent failures across the signal pipeline. Right now if the committee stops running, a factor goes stale, or duplicate signals flood in, there's no alert — Nick just doesn't see signals and doesn't know why.

---

## 1. Committee Heartbeat (VPS)

**Problem:** If the committee pipeline crashes, hangs, or the cron stops firing, there's no alert. Nick discovers it hours later when he notices no signals in Discord.

**Solution:** A heartbeat check that alerts to Discord if no committee run has occurred in 2 hours during market hours.

**File:** `scripts/committee_heartbeat.py` (~40 lines)

```python
# Runs every 30 minutes via cron during market hours (9:30 AM - 4:00 PM ET)
# Checks: when was the last committee_log.jsonl entry written?
# If >2 hours old AND market is open → post warning to Discord #signals channel
# If >4 hours old AND market is open → post CRITICAL to Discord + include last error from journalctl

import json, os, time, requests
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path("/opt/openclaw/workspace/scripts/data")
COMMITTEE_LOG = DATA_DIR / "committee_log.jsonl"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_HEARTBEAT_WEBHOOK")

def get_last_committee_time():
    """Read last line of committee_log.jsonl, parse timestamp."""
    if not COMMITTEE_LOG.exists():
        return None
    # Read last line efficiently
    with open(COMMITTEE_LOG, "rb") as f:
        f.seek(0, 2)  # End of file
        pos = f.tell()
        if pos == 0:
            return None
        # Scan backwards for last newline
        while pos > 0:
            pos -= 1
            f.seek(pos)
            if f.read(1) == b"\n" and pos < f.tell() - 1:
                break
        last_line = f.readline().decode("utf-8").strip()
    if not last_line:
        return None
    try:
        entry = json.loads(last_line)
        return datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
    except (json.JSONDecodeError, KeyError):
        return None

def is_market_hours():
    """Check if current time is within US market hours (9:30 AM - 4:00 PM ET)."""
    # Use America/New_York for market hours
    from zoneinfo import ZoneInfo
    now_et = datetime.now(ZoneInfo("America/New_York"))
    # Skip weekends
    if now_et.weekday() >= 5:
        return False
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_et <= market_close

def send_discord_alert(level, message):
    """Post heartbeat alert to Discord."""
    if not DISCORD_WEBHOOK_URL:
        print(f"[HEARTBEAT] No webhook configured. {level}: {message}")
        return
    color = 0xFF0000 if level == "CRITICAL" else 0xFFAA00  # Red or orange
    payload = {
        "embeds": [{
            "title": f"{'🔴' if level == 'CRITICAL' else '🟡'} Committee Heartbeat — {level}",
            "description": message,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)

def main():
    if not is_market_hours():
        return  # Silent outside market hours

    last_run = get_last_committee_time()
    if last_run is None:
        send_discord_alert("CRITICAL", "No committee_log.jsonl found or file is empty. Committee may have never run.")
        return

    now = datetime.now(timezone.utc)
    gap_hours = (now - last_run).total_seconds() / 3600

    if gap_hours > 4:
        send_discord_alert("CRITICAL", f"No committee run in {gap_hours:.1f} hours. Last run: {last_run.isoformat()}. Check `systemctl status openclaw` and `journalctl -u openclaw -n 50`.")
    elif gap_hours > 2:
        send_discord_alert("WARNING", f"No committee run in {gap_hours:.1f} hours. Last run: {last_run.isoformat()}. Pipeline may be stalled — no signals reaching Discord.")

if __name__ == "__main__":
    main()
```

**Cron (VPS):** Add to openclaw user's crontab:
```
# Committee heartbeat — every 30 min during market hours (ET)
*/30 13-20 * * 1-5 cd /opt/openclaw/workspace/scripts && python3 committee_heartbeat.py
```

Note: 13-20 UTC covers 9:00 AM - 4:00 PM ET (with DST buffer). The script itself checks `is_market_hours()` precisely.

**Environment:** Set `DISCORD_HEARTBEAT_WEBHOOK` in `/home/openclaw/.openclaw/openclaw.json` or export in the cron environment. Can reuse the existing signals webhook URL or create a dedicated one.

---

## 2. Factor Staleness Monitor (Railway)

**Problem:** The bias engine has 20 factors from multiple sources (yfinance, FRED, TradingView webhooks, UW). If any source fails silently, that factor stays at its last value indefinitely. A stale VIX or credit spread distorts the composite bias for hours without anyone knowing.

**Solution:** A periodic check that compares each factor's last-updated timestamp against its expected update frequency. Alert if stale.

**File:** `backend/monitoring/factor_staleness.py` (~80 lines)

**Expected TTLs per factor source:**

```python
FACTOR_TTLS = {
    # Factors updated via yfinance (every ~15 min during market hours)
    "spy_rsi": 1800,           # 30 min (2x expected)
    "spy_50sma_distance": 1800,
    "spy_200sma_distance": 1800,
    "vix_regime": 1800,
    "vix_term_structure": 1800,
    "put_call_ratio": 1800,
    "iv_regime": 1800,
    "sector_rotation": 1800,
    "gex_regime": 1800,

    # Factors updated via FRED (daily, pre-market)
    "credit_spreads": 90000,   # 25 hours
    "yield_curve": 90000,
    "claims_trend": 90000,
    "excess_cape": 604800,     # 7 days (weekly data)

    # Factors updated via TradingView webhooks (event-driven)
    "tick_breadth": 7200,      # 2 hours (should fire multiple times per session)
    "breadth_intraday": 7200,
    "mcclellan": 86400,        # 24 hours (daily signal, has 40-day warmup)
    "circuit_breaker": 86400,  # 24 hours (event-driven, may not fire daily)

    # Factors updated via UW / external
    "dark_pool_flow": 7200,    # 2 hours
    "savita": 604800,          # 7 days (weekly BofA indicator)

    # Sector RS (new — from sell the rip scanner)
    # Checked separately via sector_rs:updated_at in Redis
}
```

**Logic:**
```python
def check_factor_staleness():
    """Read all factor timestamps from Redis, compare to expected TTL."""
    stale_factors = []
    for factor, max_age in FACTOR_TTLS.items():
        key = f"factor:{factor}:updated_at"
        last_updated = redis_client.get(key)
        if last_updated is None:
            stale_factors.append((factor, "NEVER_SET", max_age))
            continue
        age = time.time() - float(last_updated)
        if age > max_age:
            stale_factors.append((factor, f"{age/3600:.1f}h old", max_age))

    if stale_factors:
        # Post to Discord via webhook
        # Group by severity: >2x TTL = CRITICAL, >1x TTL = WARNING
        # Include factor name, age, expected TTL
        post_staleness_alert(stale_factors)

    return stale_factors
```

**Integration:** Add to Railway's scan loop in `main.py`. Run every 15 minutes during market hours. Alternatively, run as a standalone function called from the existing hourly sector_rs_loop.

**Prerequisite:** Each factor computation must write `factor:{name}:updated_at = time.time()` to Redis when it updates. **Check which factors already do this.** If they don't, the brief for this feature includes adding the timestamp write to each factor's update function in `backend/bias_engine/`. This is the majority of the work — the monitor itself is simple.

**FIND** the pattern in existing factor computation (likely in `backend/bias_engine/factors/` or `backend/bias_engine/compute.py`):
```python
# After computing factor value:
redis_client.set(f"bias:factor:{factor_name}", json.dumps(result))
```

**ADD** after each factor write:
```python
redis_client.set(f"factor:{factor_name}:updated_at", str(time.time()))
```

If factors are computed in a batch function, a single timestamp write per batch run covering all factors in that batch is acceptable.

---

## 3. Webhook Dedup in tradingview.py (Railway)

**Problem:** TradingView can fire duplicate alerts (retries on timeout, double-triggers on bar close). The webhook handler inserts every signal into Postgres and processes it through the pipeline, creating duplicate trade ideas and potentially duplicate committee runs.

**Solution:** Check for existing signal with matching (ticker, strategy, direction, timeframe) within a configurable dedup window before processing.

**File:** Modify `backend/webhooks/tradingview.py`

**FIND** the main webhook handler function (likely `process_tradingview_webhook` or similar).

**ADD** dedup check early in the handler, before signal processing:

```python
import hashlib
from datetime import datetime, timedelta

DEDUP_WINDOW_SECONDS = 300  # 5 minutes

def is_duplicate_signal(signal: dict) -> bool:
    """Check if this signal was already processed recently."""
    # Create a dedup key from the signal's identifying fields
    dedup_fields = f"{signal.get('ticker')}:{signal.get('strategy')}:{signal.get('direction')}:{signal.get('timeframe', 'default')}"
    dedup_key = f"dedup:{hashlib.md5(dedup_fields.encode()).hexdigest()}"

    # Check Redis
    if redis_client.get(dedup_key):
        logger.info(f"Duplicate signal filtered: {dedup_fields}")
        return True

    # Set dedup key with TTL
    redis_client.setex(dedup_key, DEDUP_WINDOW_SECONDS, "1")
    return False
```

**In the handler, add early return:**
```python
# At the top of the webhook processing, after parsing the payload:
if is_duplicate_signal(signal_data):
    return {"status": "duplicate_filtered", "message": "Signal already processed within dedup window"}
```

**Note:** This only deduplicates identical signals from TradingView. Different strategies firing on the same ticker (e.g., Holy Grail + Scout Sniper both on SPY) should NOT be deduped — they're independent signals. The dedup key includes `strategy` to prevent this.

**Also apply to** `backend/webhooks/whale.py` and any other webhook entry points that accept external signals.

---

## 4. Polygon Degradation Handling (Railway)

**Problem:** When Polygon.io is unreachable or returns errors, scanners that depend on it (CTA, Holy Grail, Scout, Sell the Rip) crash or return empty results. This fails silently — no signals fire and no alert is raised.

**Solution:** Wrap Polygon API calls with fallback behavior. On failure, return last-known cached values with a `stale: true` flag. Alert once per failure episode.

**File:** Modify `backend/data/polygon_client.py` (or wherever Polygon calls are centralized)

**Pattern:**
```python
import time
import logging

logger = logging.getLogger(__name__)

# Track degradation state
_polygon_degraded = False
_polygon_last_alert = 0
POLYGON_ALERT_COOLDOWN = 3600  # Alert at most once per hour

def get_ticker_snapshot(ticker: str) -> dict:
    """Fetch ticker snapshot from Polygon with fallback to cache."""
    global _polygon_degraded, _polygon_last_alert

    cache_key = f"polygon:snapshot:{ticker}"

    try:
        # Attempt live fetch
        response = requests.get(
            f"https://api.polygon.io/v3/snapshot?ticker.any_of={ticker}",
            params={"apiKey": POLYGON_API_KEY},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        # Cache successful response
        redis_client.setex(cache_key, 3600, json.dumps(data))  # 1 hour TTL

        # Clear degradation state if it was set
        if _polygon_degraded:
            logger.info("Polygon connection restored")
            _polygon_degraded = False

        return {"data": data, "stale": False}

    except (requests.RequestException, ValueError) as e:
        logger.warning(f"Polygon API error for {ticker}: {e}")
        _polygon_degraded = True

        # Alert to Discord (max once per hour)
        now = time.time()
        if now - _polygon_last_alert > POLYGON_ALERT_COOLDOWN:
            _polygon_last_alert = now
            # Post degradation alert (use same webhook as heartbeat)
            alert_polygon_degradation(str(e))

        # Fallback to cached data
        cached = redis_client.get(cache_key)
        if cached:
            logger.info(f"Using cached Polygon data for {ticker}")
            return {"data": json.loads(cached), "stale": True}

        # No cache available — return None, let caller handle
        logger.error(f"No cached data for {ticker}, Polygon unavailable")
        return None
```

**Scanner integration:** Scanners that receive `stale: True` data should:
- Still process the signal (stale data is better than no data for daily-bar indicators)
- Add `"data_stale": true` to the signal metadata
- The embed builder should show a warning: `⚠️ Using cached market data — Polygon unavailable`

**yfinance fallback:** If Polygon is degraded AND the scanner already has a yfinance fallback path, prefer the yfinance path over stale Polygon cache. The existing fallback logic in each scanner should be checked to ensure it activates properly.

---

## Files Changed Summary

| File | Action | Location | Est. Lines |
|------|--------|----------|------------|
| `scripts/committee_heartbeat.py` | **NEW** | VPS | ~40 |
| `backend/monitoring/factor_staleness.py` | **NEW** | Railway | ~80 |
| `backend/webhooks/tradingview.py` | MODIFY | Railway | ~20 added |
| `backend/data/polygon_client.py` | MODIFY | Railway | ~40 added |
| `backend/bias_engine/` (multiple) | MODIFY | Railway | ~1-2 lines per factor (timestamp writes) |
| VPS crontab | MODIFY | VPS | 1 line added |

---

## Verification Steps

1. **Heartbeat:** SSH to VPS. Run `python3 committee_heartbeat.py` manually outside market hours — should exit silently. Temporarily set the 2-hour threshold to 0 and run during market hours — should post WARNING to Discord. Restore threshold.

2. **Factor staleness:** Manually delete one factor's `updated_at` key from Redis. Run staleness check — should flag that factor as NEVER_SET. Restore the key.

3. **Webhook dedup:** Send the same TradingView webhook payload twice within 5 minutes. First should process normally, second should return `duplicate_filtered`. Send a different strategy on the same ticker — should process (not filtered).

4. **Polygon fallback:** Temporarily set an invalid Polygon API key. Run a scanner — should fall back to cached data and post a degradation alert to Discord. Restore key — next run should log "connection restored."

---

## Environment Variables Needed

| Variable | Location | Purpose |
|----------|----------|---------|
| `DISCORD_HEARTBEAT_WEBHOOK` | VPS (openclaw env) | Discord webhook URL for heartbeat/monitoring alerts |

Can reuse the existing signals webhook or create a dedicated `#monitoring` channel webhook. Dedicated channel recommended to avoid alert fatigue in the signals channel.

---

## Dependencies

No new packages. Uses existing: `requests`, `redis`, `json`, `datetime`, `zoneinfo`.
