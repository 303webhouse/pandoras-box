# CC HANDOFF: Hermes Flash Build (Briefs 1 + 2)
## Date: 2026-03-31 | Priority: P0

---

## READ FIRST — CRITICAL CORRECTION

**The database is Railway's built-in Postgres, NOT Supabase.**

The app connects via env vars:
- `DB_HOST=postgres.railway.internal`
- `DB_PORT=5432`
- `DB_NAME=railway`
- `DB_USER=postgres`
- `DB_PASSWORD=sioMAUjhdgNYWwZMZbkbcSyaAcwdJMty`

The Supabase project on Nick's account is INACTIVE and unused. All references to "Supabase" in Brief 1 and Brief 2 should be read as "Railway Postgres." Specifically:

1. **Brief 1, Step 1** — The `CREATE TABLE catalyst_events` SQL runs against Railway Postgres, not Supabase. Use the existing `get_postgres_client()` from `backend/database/postgres_client.py` for all DB operations.

2. **Brief 1, Step 2** — The `system_config` INSERT also runs against Railway Postgres. Check if this table already exists. If not, create it:
```sql
CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

3. **Brief 2, Step 4 — THIS IS THE BIG ONE.** The `push_to_supabase()` function must be replaced. The VPS cannot reach `postgres.railway.internal` (it's internal to Railway's network). Instead:

   **Option A (recommended — matches existing committee bridge pattern):**
   The VPS pushes results back through the Railway app's API. Add a new endpoint on Railway:

   ```python
   @router.post("/api/hermes/analysis")
   async def receive_hermes_analysis(request: Request):
       """
       Receives Pivot's LLM analysis and updates the catalyst_events row.
       Called by VPS after scrape burst completes.
       """
       # Auth: check X-API-Key header matches PIVOT_API_KEY env var
       payload = await request.json()
       event_id = payload.get("event_id")
       analysis = payload.get("analysis", {})

       pool = await get_postgres_client()
       await pool.execute("""
           UPDATE catalyst_events
           SET headline_summary = $1,
               catalyst_category = $2,
               pivot_analysis = $3,
               updated_at = NOW()
           WHERE id = $4
       """,
           analysis.get("headline_summary", ""),
           analysis.get("catalyst_category", "unknown"),
           json.dumps(analysis),
           event_id
       )
       return {"status": "updated", "event_id": event_id}
   ```

   **Then in Brief 2's VPS code**, replace the `push_to_supabase()` function with:
   ```python
   async def push_to_railway(event_id: str, analysis: dict):
       """Push Pivot analysis back to Railway app, which writes to Postgres."""
       railway_url = os.environ.get("PANDORA_API_URL", "https://pandoras-box-production.up.railway.app/api")
       api_key = os.environ.get("PIVOT_API_KEY")

       async with httpx.AsyncClient(timeout=10.0) as client:
           resp = await client.post(
               f"{railway_url}/hermes/analysis",
               headers={"X-API-Key": api_key, "Content-Type": "application/json"},
               json={"event_id": event_id, "analysis": analysis}
           )
           if resp.status_code not in [200, 201]:
               logger.error(f"HERMES push to Railway failed: {resp.status_code}")
   ```

   Update all calls from `push_to_supabase(event_id, analysis)` → `push_to_railway(event_id, analysis)`.

---

## WHAT'S ALREADY DONE (no action needed)

| Item | Status | Details |
|---|---|---|
| Railway env: `HERMES_VPS_KEY` | ✅ Set | `FFlSBL-YT-69cLMa8G_NtMOMYYMMo89vnQL-Az8AqI0` |
| VPS env: `HERMES_API_KEY` | ✅ Set | Same value, in `/etc/openclaw/openclaw.env` |
| VPS env: `ANTHROPIC_API_KEY` | ✅ Set | In `/etc/openclaw/openclaw.env` |
| VPS env: `PANDORA_API_URL` | ✅ Already existed | `https://pandoras-box-production.up.railway.app/api` |
| VPS env: `PIVOT_API_KEY` | ✅ Already existed | `rLl-7i2GqGjie5in9iHIlVtqlP5zpY7D5E6-8tzlNSk` |

---

## BRIEFS TO BUILD (in order)

### Brief 1: `docs/codex-briefs/brief-hermes-flash-core.md`
**System: Railway + Agora frontend**

Builds the core detection layer:
- `catalyst_events` table (Railway Postgres — use `get_postgres_client()`)
- `system_config` table + `hermes_watchlist` config entry (create table if needed)
- Webhook endpoint: `POST /api/webhook/hermes` — receives TradingView alerts
- Correlation engine — detects when 2+ related tickers breach within 5 min
- VPS trigger — pings `http://188.245.250.2:8000/api/hermes/trigger` with search terms
- **NEW** endpoint: `POST /api/hermes/analysis` — receives Pivot results (see correction above)
- `GET /api/hermes/alerts` — returns events for frontend
- `PATCH /api/hermes/alerts/{id}/dismiss` — marks event reviewed
- Agora UI: Hermes Flash banner (HTML + CSS + JS polling)

**Auth notes:**
- The webhook from TradingView has no auth (TV doesn't support custom headers) — validate by checking `alert_type == "hermes_flash"` in payload
- The VPS trigger uses `HERMES_VPS_KEY` env var → sent as `X-API-Key` header
- The `/api/hermes/analysis` endpoint (receiving from VPS) validates `X-API-Key` against `PIVOT_API_KEY` env var — same pattern as the existing committee bridge

**The `hermes_watchlist` config value to insert** (with the real VPS key):
```json
{
    "tickers": {
        "SPY":  {"threshold_pct": 1.0, "timeframe_min": 30, "category": "broad_market"},
        "QQQ":  {"threshold_pct": 1.0, "timeframe_min": 30, "category": "tech"},
        "SMH":  {"threshold_pct": 1.5, "timeframe_min": 30, "category": "semis"},
        "XLF":  {"threshold_pct": 1.0, "timeframe_min": 30, "category": "financials"},
        "HYG":  {"threshold_pct": 0.5, "timeframe_min": 30, "category": "credit"},
        "IYR":  {"threshold_pct": 1.0, "timeframe_min": 30, "category": "real_estate"},
        "TLT":  {"threshold_pct": 1.0, "timeframe_min": 30, "category": "bonds"},
        "USO":  {"threshold_pct": 2.0, "timeframe_min": 30, "category": "oil"},
        "GLD":  {"threshold_pct": 1.0, "timeframe_min": 30, "category": "safe_haven"},
        "IBIT": {"threshold_pct": 2.0, "timeframe_min": 30, "category": "crypto"}
    },
    "correlation_groups": {
        "credit_event":  ["XLF", "HYG", "IYR"],
        "risk_off":      ["SPY", "QQQ", "SMH"],
        "deescalation":  ["USO", "GLD", "TLT"],
        "full_reversal":  ["SPY", "QQQ", "SMH", "XLF", "HYG"]
    },
    "correlation_window_minutes": 5,
    "correlation_min_tickers": 2,
    "vps_trigger_url": "http://188.245.250.2:8000/api/hermes/trigger",
    "vps_api_key": "FFlSBL-YT-69cLMa8G_NtMOMYYMMo89vnQL-Az8AqI0",
    "cooldown_minutes": 15
}
```

---

### Brief 2: `docs/codex-briefs/brief-hermes-flash-pivot-intel.md`
**System: VPS at 188.245.250.2, /opt/openclaw**

Builds the intelligence layer on Pivot:
- Trigger endpoint: `POST /api/hermes/trigger` on the VPS
- Twitter/X scrape burst (every 2 min × 15 min — check what scraper already exists)
- RSS feed polling (Reuters, Bloomberg, CNBC, WSJ, AP, etc.)
- Haiku LLM analysis of scraped content (model: `claude-haiku-4-5-20251001`)
- Push results back to Railway via `POST /api/hermes/analysis` (**NOT** Supabase — see correction above)

**VPS file to check first:** `pivot2_twitter.py` exists at `/opt/openclaw/workspace/scripts/pivot2_twitter.py` — this may be an existing Twitter scraper that can be reused.

**Key correction:** Replace ALL `push_to_supabase()` calls with `push_to_railway()` per the correction section above. The VPS already has `PANDORA_API_URL` and `PIVOT_API_KEY` env vars for this exact purpose.

---

## NICK'S TASKS (after CC deploys)

1. Add the PineScript indicator (in Brief 1, Step 3) to ten 1-minute TradingView charts
2. Set per-chart thresholds: HYG=0.5%, SMH=1.5%, USO=2.0%, IBIT=2.0%, everything else=1.0%
3. Create alerts on each chart → webhook URL: `https://pandoras-box-production.up.railway.app/api/webhook/hermes`
4. End-to-end test per Brief 2, Step 5

---

## QUICK REFERENCE: The Full Real-Time Chain

```
TV detects velocity breach (e.g., HYG drops 0.5% in 30 min)
    ↓ webhook (instant)
Railway /api/webhook/hermes receives alert
    ↓ checks correlation window (did XLF also breach? → Tier 2)
    ↓ writes to catalyst_events table (Railway Postgres)
    ↓ HTTP POST (instant)
VPS /api/hermes/trigger starts scrape burst
    ↓ Twitter + RSS every 2 min for 15 min
    ↓ feeds scraped content to Haiku
    ↓ HTTP POST back to Railway
Railway /api/hermes/analysis receives Pivot's analysis
    ↓ updates catalyst_events row with headline + category
    ↓ frontend polls every 10 sec
Agora banner updates: "Pivot analyzing..." → actual headline + thesis impact
```

No crons in the critical path. Total latency from TV alert to first scrape: 2-5 seconds.
