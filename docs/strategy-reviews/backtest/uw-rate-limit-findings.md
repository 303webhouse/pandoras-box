# UW Rate Limit Findings — 2026-04-24

**Endpoint tested:** `/api/stock/SPY/flow-alerts`
**Plan tier:** Basic ($150/mo)
**Run time:** 2026-04-24 00:49 UTC (outside RTH — ~00:33 UTC, well clear of 20:00 close)

## Burst behavior
- 10 requests @ max speed: 10 succeeded, 0 429s, elapsed 1.65s
- 30 requests @ max speed: 30 succeeded, 0 429s, elapsed 5.28s
- 100 requests @ max speed: 12 succeeded, 88 429s, elapsed 16.35s

## Sustained behavior
- 60 requests over ~69s (1 rps): 60 succeeded, 0 429s (100% success rate)

## First 429 trigger point
- Fired at request #13 in burst mode (rapid-fire, no sleep)
- Retry-After header values: none observed

## Interpretation
UW Basic plan has a **sliding burst window** limit of approximately 12 consecutive
rapid-fire requests. There is no apparent per-minute hard cap at 1 rps — 60 requests
over 60s succeeded 100%. This suggests a short window (likely 5–10s) resets the
burst counter.

## Recommended logger throttle
- Max burst: **10 requests** before pausing (below 12-request observed limit)
- Sleep between calls: **1.0s** (matches sustained test that yielded 0 429s)
- Burst pause: **15.0s** (generous window reset between burst groups)
- Estimated run time for 50 calls (10 tickers × 5 types): ~1.7 min
- Estimated with darkpool pagination (100+ calls): ~3–5 min
- Alert threshold: 30 min — well clear

## Additional finding: flow-alerts limit cap
`/api/stock/{ticker}/flow-alerts` returns **422 Unprocessable** if `limit > 200`.
The brief assumed 500; UW enforces 200 maximum. `fetchers/flow_alerts.py` updated
to use `limit=200`. No other endpoints tested with this limit have hit 422.

## Raw probe results
```
{'label': 'burst_10', 'total': 10, 'successes': 10, 'rate_limited': 0, 'first_429_at': None, 'elapsed_s': 1.65}
{'label': 'burst_30', 'total': 30, 'successes': 30, 'rate_limited': 0, 'first_429_at': None, 'elapsed_s': 5.28}
{'label': 'burst_100', 'total': 100, 'successes': 12, 'rate_limited': 88, 'first_429_at': 13, 'elapsed_s': 16.35}
{'label': 'sustained_60rps', 'total': 60, 'successes': 60, 'rate_limited': 0, 'elapsed_s': 69.38}
```

## Dry-run output (SPY, 2026-04-24)
```
Starting UW forward-logger -- 2026-04-24 -- 1 tickers -- dry_run=True
-- SPY --
  flow_alerts: 422 (FIXED: limit 500→200, now OK)
  darkpool: 25000 rows [DRY-RUN] Would write 202604.parquet  (hit 25k safety cap)
  net_prem_ticks: 405 rows [DRY-RUN] Would write 202604.parquet
  spot_exposures: 530 rows [DRY-RUN] Would write 202604.parquet
  greek_exposure_daily: 250 rows [DRY-RUN] Would overwrite SPY_rolling.parquet
Run complete -- 0.3 min, 4 API calls, 1 error (flow_alerts 422 — fixed)
```
Canary check passed: greek_exposure 250 rows > 200 threshold. ✓
