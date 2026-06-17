# Brief: Diagnose and fix silent-failing uw_flow_poller on Railway

**Date:** 2026-04-21
**Priority:** P0 (blocks signal quality — every signal has flow.bonus=None because flow_events is stale)
**Target:** Claude Code (VSCode)
**Estimated effort:** 30-60 min (diagnosis), unknown (fix depends on root cause)

---

## Context

ZEUS Phase 1A (commit `2ed3f61`) shipped the UW flow poller — `backend/jobs/uw_flow_poller.py` — along with the `flow_events` Postgres table and scoring logic that reads from it.

**The table has not been updated since 2026-03-26.** That's 26 days of missing flow data. Meanwhile:
- The poller code exists in the repo
- Scoring code in `score_v2.py` references `flow_events` and computes the flow bonus from it
- Every signal passing through `process_signal_unified` gets `flow.bonus=None` because there's nothing recent to join against
- This degrades score_v2 across the board and contributes to signals landing in lower tiers

This is infrastructure silent-failure, not a code bug — the code works, it's just not running (or is running and failing without alerting).

---

## Diagnostic workflow

### Step 1: Is the job scheduled on Railway?

Check Railway project → pandoras-box-production → Cron Jobs (or Workers/Deployments tab). Look for any entry invoking `uw_flow_poller`. Screenshot or note:
- Schedule (cron expression)
- Last run timestamp
- Last run status (success/failed)
- Last run logs

If no job is scheduled: that's the root cause. Schedule it per Step 5.

### Step 2: If scheduled, is it succeeding?

Check Railway logs for the service running the poller. Filter on `uw_flow_poller`, `flow_poller`, or `flow_events`. Look for:
- Last successful INSERT timestamp (should match flow_events.captured_at)
- Any exceptions/tracebacks
- HTTP errors from UW API (rate limits, auth failures)
- Timeouts

### Step 3: Manual invocation from Railway shell

Shell into the Railway app and run:

```bash
python -m backend.jobs.uw_flow_poller
```

Expected: pulls current flow data from UW, INSERTs into `flow_events`, exits cleanly. Any stack trace reveals the root cause.

### Step 4: Check the code is reading the right env vars

`backend/jobs/uw_flow_poller.py` should use `UW_API_KEY` env var per the data hierarchy memory (#11 + #17). Confirm:
- `UW_API_KEY` is set in Railway environment variables
- The poller imports and uses the same UW client pattern as `backend/integrations/uw_api.py` (bearer auth, 120 req/min rate limit)
- Not accidentally using a deprecated Polygon/FMP path

### Step 5: Schedule the poller if not already

Per the architecture, the poller should run frequently during market hours to keep `flow_events` fresh for the scoring pipeline. Recommended schedule:

```
*/5 13-21 * * 1-5   # every 5 min, 9am-5pm ET weekdays (includes 30 min post-close for late prints)
```

Configure via Railway cron jobs feature, pointing at the module entry point.

---

## Likely root causes (ranked)

1. **Not scheduled on Railway at all.** Code shipped, scheduling step missed. Most likely given the exact 26-day gap (~ZEUS Phase 1A deploy date).
2. **Scheduled but missing `UW_API_KEY` env var on Railway.** 401 on every call, silent failure.
3. **Scheduled, auth works, but table schema mismatch** causing every INSERT to throw. Check column types against what the poller writes.
4. **Rate limit lockout** — if the poller somehow loops aggressively, UW may have temp-banned. Check UW dashboard for rate limit alerts.

---

## After fixing: verify end-to-end

1. Force a run, confirm `flow_events` has rows with `captured_at >= NOW() - INTERVAL '10 minutes'`:
   ```sql
   SELECT ticker, captured_at, flow_sentiment, total_premium 
   FROM flow_events 
   WHERE captured_at >= NOW() - INTERVAL '10 minutes' 
   ORDER BY captured_at DESC 
   LIMIT 20;
   ```
2. Wait for next live signal to be processed; confirm its `triggering_factors` JSON has a populated `flow` key with `bonus > 0` where flow data supports the direction:
   ```sql
   SELECT signal_id, ticker, score, score_v2, triggering_factors->'flow' as flow_factor
   FROM signals
   WHERE timestamp >= NOW() - INTERVAL '2 hours'
   ORDER BY timestamp DESC
   LIMIT 10;
   ```
3. Confirm at least one signal shows `flow.bonus` as a non-null number (not "None" or null).

---

## Out of scope for this brief

- Adding a health-check alert when `flow_events` goes stale >1 hour. That belongs in a follow-up brief once the root cause is known — we'll build a generic "Railway job freshness monitor" rather than a one-off.
- Re-running scoring on historical signals that were graded with `flow.bonus=None`. Those are water under the bridge.

---

## Done when

- [ ] Root cause identified and documented in a comment on the PR
- [ ] Fix deployed to Railway
- [ ] `flow_events` has rows with timestamps within the last 10 minutes during market hours
- [ ] A live signal processed after the fix shows populated `flow.bonus` in `triggering_factors`
- [ ] Poller's Railway schedule is documented in `PROJECT_RULES.md`
