# Brief: Outcome Tracking Fix — Close the Learning Loop

**Date:** 2026-04-22
**Priority:** P0 (system is flying blind; no other measurement-dependent work can proceed without this)
**Target:** Claude Code (VSCode)
**Estimated effort:** 1-2 hours (investigation + fix + backfill)
**Origin:** Post-deploy verification on 2026-04-22 showed **0 outcomes tracked across 1,526 signals in 14 days**. Every score band (60s through 90+) shows wins=0, losses=0, unresolved=all. Outcome tracking is non-functional.

---

## Why this blocks everything else

Without outcome data you cannot:

- Measure committee accuracy (the `committee_accuracy` view in `postgres_client.py:1214` is empty)
- Run URSA gates on future Olympus design decisions (we did this for ADX filter with n=3; future filters need real n)
- Backtest strategy changes
- Justify threshold tuning decisions
- Compute agent confidence priors for Olympus calibration
- Determine whether `score_v2` is actually predictive

Every other optimization we're doing is theoretical without the feedback loop closed.

---

## Investigate first (30 min)

### Step 1: Is `outcome_resolver.py` running?

`backend/jobs/outcome_resolver.py` exists. Check Railway cron jobs — is it scheduled? When did it last run? Last successful resolution?

From prior session note: "outcome_resolver only resolves ACCEPTED signals." If this is still true, that's the bug. Most signals never get explicit ACCEPT (they age out, get dismissed, or just expire). We need the resolver to work on any signal with a valid `expires_at` in the past, regardless of whether a human clicked Accept.

### Step 2: What does the resolver actually do?

Inspect `outcome_resolver.py`. Expected behavior:

```
For each signal where:
  - outcome IS NULL
  - expires_at < NOW()
  - status NOT IN ('DISMISSED')  # DISMISSED = user said no, don't measure
Do:
  - Compute win/loss based on direction + entry_price + price at expires_at
  - UPDATE outcome, outcome_pnl_pct, outcome_resolved_at
```

If the current version requires `status = 'ACCEPTED_*'`, that's the bug. Change it to process all non-DISMISSED signals that have passed their expiry.

### Step 3: Is price data available at expiry time?

Resolver needs OHLCV at signal expiry to compute outcome. Confirm:
- yfinance fetch works for the tickers in question (per data hierarchy #11 — OHLCV is yfinance territory)
- Resolver can handle pre-market / after-hours expiries (use daily close if intraday data unavailable)

---

## Implementation

### Fix 1: Broaden resolver scope

In `outcome_resolver.py`, change the query from accepted-only to include all unresolved signals:

```python
# OLD (suspected)
SELECT * FROM signals WHERE status LIKE 'ACCEPTED_%' AND outcome IS NULL AND expires_at < NOW()

# NEW
SELECT * FROM signals 
WHERE outcome IS NULL 
  AND expires_at IS NOT NULL 
  AND expires_at < NOW()
  AND status NOT IN ('DISMISSED')  -- user explicitly rejected; don't score
```

### Fix 2: Handle signals without explicit expires_at

Some signals have NULL `expires_at`. Compute implicit expiry from timeframe:

```python
# If expires_at is NULL, use timeframe to derive:
# - intraday signals (1m-1H): expire 4 hours after timestamp
# - swing (4H-1D): expire 24 hours after timestamp  
# - weekly: expire 7 days after timestamp
# (already in pipeline.py `calculate_expiry` — reuse it)
```

### Fix 3: Win/loss logic must match strategy type

- **Momentum LONG:** win if close >= entry_price * (1 + target_pct) within window, loss if close <= entry_price * (1 - stop_pct)
- **Momentum SHORT:** inverse
- **Options signals:** if signal has an implied strike/expiry, compute based on option value at resolution
- **Default:** use 1% as win threshold / -1% as loss threshold if strategy-specific targets not defined

Don't over-engineer on round 1 — a simple "did price move in the signal's direction by X% before expiry" is fine. Make targets configurable per strategy in a lookup, iterate later.

### Fix 4: Schedule the resolver

If it's not currently scheduled on Railway:

```
Cron: 0 */6 * * *   # every 6 hours, resolves anything expired since last run
```

Or run it once at end-of-day (22:00 UTC weekdays) if every-6-hours is too aggressive.

### Fix 5: Backfill historical outcomes

After the fix is deployed, run a one-shot backfill:

```python
# One-off script: resolve all unresolved signals from last 30 days
python -m backend.jobs.outcome_resolver --backfill --days 30
```

This populates outcome data for all the 1,526 signals currently sitting at outcome=NULL, giving us real data to drive URSA gates on future work.

---

## Verification

1. Run the query that originally showed 0 outcomes — confirm numbers now appear:
   ```sql
   SELECT 
     CASE WHEN score < 60 THEN '<60' WHEN score < 80 THEN '60-80' ELSE '80+' END as band,
     COUNT(*) as n,
     COUNT(*) FILTER (WHERE outcome = 'WIN') as wins,
     COUNT(*) FILTER (WHERE outcome = 'LOSS') as losses
   FROM signals
   WHERE timestamp > NOW() - INTERVAL '14 days'
   GROUP BY band;
   ```
   Expect: wins + losses > 0 in every band.

2. Spot-check 5 recent resolved signals manually. For each, verify the win/loss call matches what actually happened in the ticker's price.

3. Check `committee_accuracy` view (if it references outcome data) — should now populate.

---

## Out of scope (follow-up briefs)

- Strategy-specific outcome definitions (different % thresholds for Artemis vs Holy_Grail)
- Partial-win handling (signal hit 50% of target — half win?)
- MAE/MFE tracking (maximum adverse / favorable excursion during the hold window)

---

## Done when

- [ ] `outcome_resolver.py` diagnosed, root cause documented in PR
- [ ] Scope broadened to non-ACCEPTED signals
- [ ] Scheduled on Railway cron
- [ ] Backfill script run on 30 days of historical signals
- [ ] Verification query shows non-zero outcomes across score bands
- [ ] Spot-check of 5 recent resolved signals confirms correct win/loss calls
