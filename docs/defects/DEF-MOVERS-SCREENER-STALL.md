# DEF-MOVERS-SCREENER-STALL

**Severity:** P3 · **Filed:** 2026-08-17 · **Status:** OPEN
**Surface:** `hub_get_stable_movers` (yfinance screener snapshot)

## Symptom
2026-08-05 read: `degraded: true`, `data_age` ~33k s, `as_of
2026-08-04T19:54Z`, serving Monday-session movers (ARM +17.5%, PLTR +29.5%)
into Tuesday evening. The degraded flag worked as designed; the screener
itself had stalled for ~1.5 sessions.

## Why it matters
Movers is the fastest "what is actually ripping right now" surface the Stable
Engine has. A stalled screener during the biggest rotation days of the year is
the tool failing exactly when it matters. Flag honesty ≠ feed health.

## Verification / fix path
1. Locate the screener poller (VPS cron vs Railway job), pull its logs for
   2026-08-03→05, identify stall cause (rate limit / crash / schedule gap).
2. Add restart-on-stall + alert when data_age exceeds 2 market hours during
   RTH.
3. Close on 5 consecutive RTH days with data_age < 30 min.
