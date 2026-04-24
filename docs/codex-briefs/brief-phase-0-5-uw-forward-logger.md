# CC Build Brief — Phase 0.5: UW Forward-Logger Cron + Rate-Limit Burst-Test

**Upstream context:**
- Titans review (Pass 2 locked): `docs/strategy-reviews/backtest/titans-review-backtest-module-v1.md`
- Phase 0 UW findings: `docs/strategy-reviews/backtest/uw-historical-depth-findings.md` (§11 ATHENA sign-off, §12 Phase 0.75 GEX variants)
- Original backtest module brief: `docs/strategy-reviews/backtest/titans-brief-backtest-module-v1.md`

**Build type:** Small infrastructure build on the VPS. Two parts bundled into one brief:
1. Rate-limit burst-test script (prerequisite — must run before the cron goes to production volume)
2. Daily forward-logger cron on VPS (the actual deliverable)

**Estimate:** ~4-6 hours CC work total (rate-limit probe ~1h, logger cron ~3-5h with testing).

**Why this is the highest priority item:** Basic UW plan only retains 30 trading days of history for flow, dark pool, intraday GEX, and net-premium ticks. Every day without this logger running is one day of proprietary history permanently lost to the rolling cutoff. The backtest module's forward-test lane (Phase 2 bifurcation) depends entirely on this accumulating data.


---

## Prime Directives

1. **Read `PROJECT_RULES.md` and `CLAUDE.md` at repo root before touching code.**
2. **This runs on the VPS (`188.245.250.2`, OpenClaw at `/opt/openclaw`) — NOT on Railway.** Railway is for the live trading hub + backtest engine (future Phase 1+). The forward-logger is VPS territory, sitting alongside the existing committee pipeline crons.
3. **Direct REST to UW API.** No MCP, no wrappers. `Authorization: Bearer $UW_API_KEY` header. The key is already in VPS environment (verify at `/opt/openclaw/.env` or wherever existing UW calls source it).
4. **Cache format per AEGIS §9.2:** Parquet files at `data/cache/uw/{data_type}/{symbol}/{YYYYMM}.parquet`. Monthly partitioned. Immutable once written for closed months.
5. **Rate-limit burst-test MUST complete before logger cron goes to production volume.** The burst-test deliverable is numbers, not code that ships. The logger cron then uses those numbers to throttle itself.
6. **Fail loud, not silent.** If a data type returns empty for 2+ consecutive days, alert Nick. If an endpoint starts 403'ing on data we used to get, alert Nick. Silent data gaps poison the forward-test dataset for months.
7. **All exact commands and file paths are copy-paste-verbatim.** If a path doesn't exist or a structure has drifted, STOP and ask Nick.

---

## Phase A — Rate-Limit Burst-Test (prerequisite, ~1 hour)

Goal: characterize UW's actual rate-limit behavior on the basic plan so the logger cron can throttle accurately. UW doesn't publish per-tier limits.

### A.1 Script location

Create `scripts/uw_rate_limit_probe.py` on the VPS (single-use script, not shipping to production).

### A.2 Script behavior

Fire N requests in rapid succession against a low-cost endpoint and record exactly when 429 responses start appearing. Use `/api/stock/SPY/flow-alerts` (no date param) — returns fast, small payload, already verified working in Phase 0.


Probe sequence:
1. Fire 10 requests as fast as possible (no sleep). Record: (a) number succeeded, (b) any 429s, (c) wall-clock elapsed time.
2. If no 429s: fire 30 in a tight loop. Record same.
3. If no 429s: fire 100 in a tight loop. Record same.
4. If 429s hit at any step: note the request number where they started, record any `Retry-After` header values, stop.
5. Wait 60 seconds.
6. Fire 60 requests over 60 seconds (1 per second). Record success rate. This tests sustained-rate behavior.
7. Stop. Write findings to `docs/strategy-reviews/backtest/uw-rate-limit-findings.md`.

### A.3 Findings doc template

```markdown
# UW Rate Limit Findings — 2026-04-23

**Endpoint tested:** `/api/stock/SPY/flow-alerts`
**Plan tier:** Basic ($150/mo)

## Burst behavior
- 10 requests @ max speed: [N succeeded, N 429s, elapsed Xs]
- 30 requests @ max speed: [...]
- 100 requests @ max speed: [...]

## Sustained behavior
- 60 requests over 60s (1 rps): [N succeeded, N 429s]

## First 429 trigger point
- Fired at request #[N] in burst mode
- Retry-After header: [value or "none"]

## Recommended logger throttle
- Max burst: [N] requests before pausing
- Steady-state rate: [N] requests per minute
- Safety margin: use [X%] below observed limit to avoid live-committee contention
```

### A.4 Hard rules

- **Run this probe OUTSIDE RTH (13:30–20:00 UTC weekdays) if at all possible** — during RTH, the live committee pipeline is actively consuming UW quota. Rate-limit probing during RTH risks starving live signal generation. If Phase 0.5 goes out before market close, run the probe in extended hours / overnight.
- If 429s hit immediately on request #1, STOP. Something is wrong (possibly the live committee is mid-burst). Wait 10 minutes, try again.
- Never use the probe script in any automated cron — it's a one-shot diagnostic.


---

## Phase B — Forward-Logger Cron (main deliverable, ~3-5 hours)

### B.1 Deploy target

VPS at `188.245.250.2`, working directory `/opt/openclaw/`. Existing cron schedule lives in `/etc/cron.d/` and `/opt/openclaw/scripts/` per the committee pipeline structure. Match that pattern.

### B.2 What the logger pulls

Daily at 21:00 UTC (roughly 1 hour after US market close, after day-close data settles), for each ticker in the configured watchlist:

| Endpoint | Query | Cache path |
|---|---|---|
| `/api/stock/{TICKER}/flow-alerts` | no date (current day's stream, limit=500) | `data/cache/uw/flow_alerts/{TICKER}/{YYYYMM}.parquet` |
| `/api/darkpool/{TICKER}` | `date={YESTERDAY}`, cursor-paginate to full day | `data/cache/uw/darkpool/{TICKER}/{YYYYMM}.parquet` |
| `/api/stock/{TICKER}/net-prem-ticks` | no date (current day's intraday ticks) | `data/cache/uw/net_prem_ticks/{TICKER}/{YYYYMM}.parquet` |
| `/api/stock/{TICKER}/spot-exposures` | no date (current day's intraday GEX 1-min ticks) | `data/cache/uw/spot_exposures/{TICKER}/{YYYYMM}.parquet` |
| `/api/stock/{TICKER}/greek-exposure` | no date (refreshes rolling 1-year daily series) | `data/cache/uw/greek_exposure_daily/{TICKER}/{TICKER}_rolling.parquet` (special: overwrites, not monthly-partitioned, since it's a rolling 1yr series) |

**Note on `greek-exposure`**: This one uses a different cache pattern because its response shape IS the 1-year time series. Overwriting a single file daily is cheaper than trying to partition it monthly. The rolling file is the canonical source; prior daily GEX data is retained in git-ignored backups if Phase 1 backtest finds value in version history (not yet — defer).

### B.3 Watchlist configuration

Create `config/uw_logger_watchlist.yaml`:

```yaml
# UW forward-logger watchlist. Start small, expand once proven.
# Phase 0.5 launch set (10 tickers):
tickers:
  - SPY   # baseline — primary test symbol throughout Phase 0 spike
  - QQQ   # Nasdaq proxy
  - IWM   # Small cap
  - DIA   # Dow
  - XLK   # Tech sector
  - XLF   # Financials
  - NVDA  # Flow-heavy mega-cap
  - TSLA  # Flow-heavy mega-cap
  - AAPL  # Flow-heavy mega-cap
  - AMZN  # Flow-heavy mega-cap

# Future expansion candidates (do NOT add yet — rate limits unknown):
# XLE, XLY, XLV, AMD, META, GOOGL, MSFT, plus top 20 active options names
```

**Do not expand the watchlist beyond 10 tickers without re-running the rate-limit burst-test.** 10 tickers × 5 data types × ~1 call per data type = ~50 calls per cron run (with pagination, dark pool could balloon to 100+ — see B.6). Expanding to 20+ tickers without characterizing rate limits is how we take down the live committee pipeline.


### B.4 Script structure

```
/opt/openclaw/scripts/uw_forward_logger/
├── __init__.py
├── logger.py              # main entry point
├── fetchers/
│   ├── __init__.py
│   ├── base.py            # shared: auth header, retry, 429 backoff
│   ├── flow_alerts.py
│   ├── darkpool.py        # includes cursor-pagination loop
│   ├── net_prem_ticks.py
│   ├── spot_exposures.py
│   └── greek_exposure.py  # the daily 1yr series fetcher
├── cache.py               # parquet read/write helpers
├── alerts.py              # 2-day-empty detection + notification
└── config.py              # loads watchlist.yaml + rate limits from findings doc
```

### B.5 Per-fetcher behavior

Each fetcher implements a simple contract:

```python
def fetch(ticker: str, api_key: str) -> pd.DataFrame:
    """
    Pull one day's data for this data type for this ticker.
    Returns a DataFrame (possibly empty). Raises on HTTP error.
    """
```

The main `logger.py` loop:
1. Load watchlist
2. Load rate-limit config from `uw-rate-limit-findings.md` (parsed from the findings doc — or hardcoded after Phase A resolves)
3. For each (ticker, data_type) combination:
   - Call the fetcher
   - If empty response AND prior day was also empty, queue an alert
   - Merge returned DataFrame with existing parquet cache file (if present)
   - Write back to cache
   - Sleep per rate-limit config between calls
4. After all fetches: if any alerts queued, send them via the existing VPS notification channel (check `/opt/openclaw/scripts/` for the existing alert pattern — probably Discord webhook or similar)

### B.6 Dark pool cursor pagination

Per Phase 0 findings §3.2, dark pool uses `older_than=<ISO timestamp>` cursor pagination, NOT page numbers. Single SPY trading day can have thousands of prints. Logger must loop until the response returns fewer than the limit:

```python
def fetch_darkpool_full_day(ticker: str, date: str, api_key: str) -> pd.DataFrame:
    all_rows = []
    cursor = None  # start with no cursor = newest first
    while True:
        params = {"date": date, "limit": 500}
        if cursor:
            params["older_than"] = cursor
        response = _request(f"/api/darkpool/{ticker}", params, api_key)
        rows = response.get("data", [])
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < 500:
            break  # final page
        # Take oldest timestamp in batch as next cursor
        cursor = rows[-1]["executed_at"]
        # Safety limit: max 50 pages per day to prevent runaway loops
        if len(all_rows) > 25000:
            logger.warning(f"Dark pool for {ticker} on {date} exceeded 25k rows — truncating")
            break
    return pd.DataFrame(all_rows)
```


### B.7 Response envelope handling

Per Phase 0 findings §5.4, UW response envelopes vary:
- `{"data": [...]}` — most endpoints (flow-alerts, darkpool, net-prem-ticks, spot-exposures, greek-exposure)
- Bare array `[...]` — flow-per-expiry, flow-per-strike (not in Phase 0.5 scope, but worth noting for future)
- `{"chains": [...]}` — option-contract/historic (not in Phase 0.5 scope)

For Phase 0.5 logger, all 5 endpoints use `{"data": [...]}`. Implement defensively anyway:

```python
def _extract_rows(response_json) -> list:
    if isinstance(response_json, list):
        return response_json
    for key in ("data", "chains"):
        if key in response_json:
            return response_json[key]
    logger.warning(f"Unexpected response envelope: {list(response_json.keys())}")
    return []
```

### B.8 Retry and backoff logic

Per findings §5.5 and §9.3:
- On 429: respect `Retry-After` header if present, else exponential backoff starting at 2s, max 5 retries, then fail loud (log + alert)
- On 5xx: retry up to 3 times with 5s backoff
- On 403 with `historic_data_access_missing`: LOG AS WARNING and skip this data point (expected for out-of-window dates) — do NOT alert
- On 403 with any other code: ALERT (could indicate plan downgrade or API key issue)
- On network error / timeout: retry 3 times with 2s backoff, then fail loud

### B.9 Alert rules

Alert Nick (via existing VPS notification channel — match the committee pipeline pattern) when:
1. Any data type returns empty for 2+ consecutive days for the SAME ticker (data quality)
2. Any 429 results in a fully-failed fetch (rate limits too aggressive or UW tightened)
3. Any unexpected 403 or 401 (credential issue or plan change)
4. The full cron run takes longer than 30 minutes (something's wrong)
5. A new response envelope key is observed (`_extract_rows` prints the warning)

DO NOT alert on:
- Expected 403s for historic-depth errors (these are WARNINGS, not ALERTS)
- Empty responses when the market was closed (holidays, weekends — the cron should skip weekends anyway)
- Individual retries that eventually succeeded


### B.10 Cron schedule

Add to `/etc/cron.d/uw_forward_logger` (match existing VPS cron file naming):

```
# UW Forward-Logger — daily pull at 21:00 UTC (post US market close + settle)
# Skip weekends (market closed)
0 21 * * 1-5 openclaw cd /opt/openclaw && /opt/openclaw/venv/bin/python -m scripts.uw_forward_logger.logger >> /var/log/uw_forward_logger.log 2>&1
```

**Important:** Phase 0.5 only runs Monday–Friday. Saturdays and Sundays are skipped because market is closed. Holidays are NOT filtered at the cron level — the logger itself should check if the market was open and skip the full day's pull with a log note if not. Use `pandas_market_calendars` (already a dep elsewhere in the project, verify) or a simple NYSE holiday list.

### B.11 Log rotation

Mirror the existing VPS log-rotation pattern. Check `/etc/logrotate.d/` for the committee pipeline pattern — typical setup is daily rotation, 14 days retention, gzip after 1 day. Match that.

### B.12 The canary test (§12.8 of Phase 0 findings)

Integrate the `/greek-exposure` carve-out canary into the logger. On every run, after the greek-exposure fetch:

```python
if len(df) < 200:
    logger.warning(
        f"CARVE_OUT_CANARY: {ticker} greek-exposure returned only {len(df)} rows. "
        f"UW may have tightened the no-date carve-out. Check with ATHENA."
    )
    # Also queue an alert (but only once per ticker per week — don't spam)
```

This is the early-warning system for UW silently changing the 1-year carve-out. Fire once per week max per ticker (use a simple flag file to track last alert time).

---

## Phase C — Verification & Deployment

### C.1 Local verification before deploy

Run the logger manually in dry-run mode (fetch but don't write to the real cache path — use a temp dir):

```bash
cd /opt/openclaw
./venv/bin/python -m scripts.uw_forward_logger.logger --dry-run --ticker SPY
```

Expected output:
- 5 successful fetches (flow-alerts, darkpool, net-prem-ticks, spot-exposures, greek-exposure)
- Row counts printed for each
- No errors, no 429s
- Rate-limit sleep times shown between calls


### C.2 First production run

Once dry-run validates:
1. Install the cron entry
2. Wait for the next 21:00 UTC window (or trigger manually once, outside RTH, to seed data)
3. Verify cache files land in the expected paths:
   ```bash
   find /opt/openclaw/data/cache/uw -name "*.parquet" -mmin -60
   ```
4. Spot-check row counts match expectations (darkpool should have 500+ rows for SPY full day; greek-exposure should have ~251 rows)
5. Verify alert channel is armed (trigger a test alert during deployment — send a "logger online" notification on first successful run)

### C.3 .gitignore

Add these paths to the repo `.gitignore` if not already present (per AEGIS §10.2 — cached UW data is paid content):

```
# UW forward-logger cache (paid data, do not commit)
data/cache/uw/
*.parquet
```

Check existing `.gitignore` first — parquet exclusion may already be there from Phase 0 scoping.

---

## Phase D — Commit & Merge

Branch: `feature/uw-forward-logger-phase-0-5`

Commit message:

```
feat(vps): Phase 0.5 UW forward-logger cron + rate-limit burst-test

Deploys daily UW data logger to VPS to accumulate proprietary
history for the backtest module's Phase 2 forward-test lane.
Critical path — every day of delay is permanent data loss to
the 30-day rolling cutoff on basic plan.

Components:
- scripts/uw_rate_limit_probe.py (one-shot diagnostic)
- scripts/uw_forward_logger/ (daily cron at 21:00 UTC)
- config/uw_logger_watchlist.yaml (10-ticker launch set)
- /etc/cron.d/uw_forward_logger (weekday schedule)
- docs/strategy-reviews/backtest/uw-rate-limit-findings.md

Refs:
- docs/strategy-reviews/backtest/titans-review-backtest-module-v1.md (§11 ATHENA sign-off)
- docs/strategy-reviews/backtest/uw-historical-depth-findings.md (§12.8 canary)
- docs/codex-briefs/brief-phase-0-5-uw-forward-logger.md (this brief)
```


Do NOT merge to main yet. Nick reviews the PR + watches the first production cron run before greenlighting merge.

---

## Output to Nick

Phase A (rate-limit probe):
1. Path to `uw-rate-limit-findings.md` with burst-test results
2. Recommended throttle values (max burst, steady-state rate)
3. Whether any 429s were observed

Phase B (logger cron):
1. Branch HEAD SHA + PR link
2. File tree created (`scripts/uw_forward_logger/` contents)
3. Dry-run output showing 5 successful fetches on SPY
4. Cron entry contents
5. Alert channel test (screenshot or log snippet of the test alert landing)

Phase C (deployment):
1. First production cron run log excerpt
2. `find` output showing cache files landed
3. Sample row counts per data type per ticker
4. Any surprises or scope-creep tempted but not taken

---

## Constraints

- **Strict scope:** 10-ticker watchlist, 5 data types. Do NOT add endpoints beyond the 5 listed (flow-per-expiry, flow-per-strike, max-pain, news, earnings are all tempting but out of scope for Phase 0.5 — they can ship in a follow-up brief after 2-4 weeks of operation).
- **Do NOT modify anything in the live committee pipeline.** The forward-logger is a NEW cron, not a modification of existing infrastructure. It should share nothing with the committee pipeline except the UW API key and the alert channel.
- **Do NOT deploy the cron during RTH.** First production run after 21:00 UTC minimum. Verify outside-RTH timing in the deploy log.
- **Do NOT commit cache files.** The `.gitignore` update is mandatory.
- **Rate-limit burst-test must run BEFORE the production cron.** Sequence: Phase A probe → update rate limits in config → Phase B deploy.
- **No shortcuts on the canary test.** The §12.8 canary is the only thing that catches UW silently tightening the 1-year GEX carve-out. Skipping it means we wake up with a broken backtest one day with no warning.

---

**End of brief.**
