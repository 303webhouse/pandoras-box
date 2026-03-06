# Brief: Step 0 — Fix Outcome Tracking Pipeline

**Priority:** CRITICAL PREREQUISITE — Nothing else in the confluence build can be validated without this.
**Target:** VPS (`/opt/openclaw/workspace/scripts/`)
**Estimated time:** 30-60 minutes

---

## Problem

The nightly outcome matcher cron runs at 11 PM ET (4 AM UTC) but has NEVER successfully written output:
- `/var/log/pivot2_outcomes.log` does not exist
- `/var/log/pivot2_review.log` does not exist  
- `outcome_log.jsonl` is empty (0 lines)
- `autopsy_log.jsonl` is empty (0 lines)
- `lessons_bank.jsonl` has 3 entries from Feb 28, all saying "0 resolved outcomes out of 23 signals"

Without outcome data, we cannot:
- Measure strategy win rates
- Validate whether confluence improves outcomes
- Determine which strategies to keep/kill
- Tune gatekeeper thresholds

## Cron Entry (Already Exists)

```
# Nightly outcome matcher — 11 PM ET (4 AM UTC)
0 4 * * * cd /opt/openclaw/workspace/scripts && /usr/bin/python3 committee_outcomes.py >> /var/log/pivot2_outcomes.log 2>&1
```

The cron is set up. The script exists. Something in the script is failing silently.

## Diagnosis Steps

1. **Run the script manually and capture output:**
```bash
cd /opt/openclaw/workspace/scripts
/usr/bin/python3 committee_outcomes.py 2>&1 | head -100
```

2. **Check if the script can reach Railway API:**
The outcome matcher fetches signal outcomes from Railway:
```bash
curl -s "https://pandoras-box-production.up.railway.app/webhook/outcomes/test_signal_id" | head -20
```
Expected: 404 (signal not found) — confirms the endpoint is reachable.

3. **Check if `decision_log.jsonl` has entries to match:**
```bash
wc -l /opt/openclaw/workspace/data/decision_log.jsonl
```
Expected: 23 entries (confirmed in our audit).

4. **Check if `signal_outcomes` table in Postgres has PENDING entries:**
The outcome matcher joins `decision_log.jsonl` with Railway's `signal_outcomes` table. If no PENDING outcomes exist, there's nothing to match.

## Likely Failure Modes

### Mode A: Railway API URL is wrong or missing env var
The script needs `RAILWAY_API_URL` or `PANDORA_API_URL` to reach Railway. Check if the env var is set in the cron context:
```bash
env | grep -i railway
env | grep -i pandora
```
The cron environment may not have these vars. Compare with the `committee_railway_bridge.py` cron which DOES work — it hardcodes the URL.

### Mode B: No PENDING outcomes in `signal_outcomes` table
Signals need to be written to `signal_outcomes` with status `PENDING` when they're created. Check if the table has any data:
```bash
curl -s "https://pandoras-box-production.up.railway.app/webhook/outcomes/SCOUT_AAPL_20260303_150000_000000" 2>&1 | head -5
```
If the endpoint returns 404 for real signal IDs from `decision_log.jsonl`, the problem is that signals aren't being written to `signal_outcomes` at creation time.

### Mode C: Script crashes on import or early in execution
Python import error, missing dependency, or config issue. The manual run (step 1) will reveal this immediately.

## Fix Pattern

Once you identify the failure mode:

1. **If env var issue:** Add the Railway URL directly to the cron command (like the bridge cron does) or hardcode it in the script as a fallback.

2. **If no PENDING outcomes:** Check `signals/pipeline.py` → `_write_signal_outcome()` (deprecated) and the current `process_signal_unified()` to verify PENDING records are written to `signal_outcomes` table.

3. **If script crash:** Fix the error, test manually, verify log output.

## Validation

After fixing:
```bash
# Run manually
cd /opt/openclaw/workspace/scripts
/usr/bin/python3 committee_outcomes.py 2>&1

# Check output file
wc -l /opt/openclaw/workspace/data/outcome_log.jsonl

# Verify log exists
ls -la /var/log/pivot2_outcomes.log
```

Success = `outcome_log.jsonl` has entries OR the script runs cleanly and reports "0 matches" (which means the matching logic works but there are no resolved outcomes yet — that's fine, it means the pipeline is operational).

## Also Check: Weekly Review

The Saturday 9 AM MT weekly review (`committee_review.py`) also hasn't produced logs:
```
0 16 * * 6 cd /opt/openclaw/workspace/scripts && /usr/bin/python3 committee_review.py >> /var/log/pivot2_review.log 2>&1
```

This likely has the same env var / API URL issue. Fix both at the same time.

## Files

- `/opt/openclaw/workspace/scripts/committee_outcomes.py` — nightly outcome matcher
- `/opt/openclaw/workspace/scripts/committee_review.py` — weekly self-review
- `/opt/openclaw/workspace/scripts/committee_analytics.py` — analytics computation (called by review)
- Cron: `crontab -l` (root crontab)

## Deployment

VPS only. After fixing:
```bash
# No service restart needed — these are cron scripts, not services
# Just verify the next scheduled run produces output
# Or run manually to test immediately
```
