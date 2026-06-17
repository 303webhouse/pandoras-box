# Brief: Raise auto-promote to 85, clean stale PENDING_REVIEW backlog, kill the pending-queue pattern

**Date:** 2026-04-22
**Priority:** P1 (not blocking trading, but kills a 156-signal dead-letter queue and reduces cognitive noise)
**Target:** Claude Code (VSCode)
**Estimated effort:** 20-30 min
**Origin:** Post-deploy verification on 2026-04-22 showed:
- **161 signals stuck in PENDING_REVIEW**, of which 156 are more than 7 days old
- 24 of those 161 were scored 80+ at creation but never got auto-promoted (likely pre-dates ZEUS Phase 3 deploy)
- Nick has never been clicking manual Analyze on these — the queue is backlog, not workflow
- 2026-04-22 MO committee output (score 82) came back unanimously LOW conviction — confirming that 80-84 band is noisy enough to not be worth committee cycles

---

## Decisions (Nick approved 2026-04-22)

1. **Raise auto-promote threshold from 80 to 85.** Signals scoring <85 never enter the committee pipeline. They still appear in feed (via `feed_tier` classification) but don't trigger Olympus.
2. **Kill `PENDING_REVIEW` as a holding state for new signals.** Either auto-promote to `COMMITTEE_REVIEW` (score >= 85) or go directly to `ACTIVE` with feed_tier routing (score < 85). No middle ground.
3. **Sweep existing backlog.** All signals currently in PENDING_REVIEW older than 7 days get auto-expired.

---

## Implementation

### Change 1: Raise threshold in `pipeline.py`

Current (line ~116):
```python
AUTO_PROMOTE_THRESHOLD = 80.0
new_status = "COMMITTEE_REVIEW" if score >= AUTO_PROMOTE_THRESHOLD else "PENDING_REVIEW"
```

New:
```python
AUTO_PROMOTE_THRESHOLD = 85.0
# No PENDING_REVIEW tier — either committee-review or active-in-feed
new_status = "COMMITTEE_REVIEW" if score >= AUTO_PROMOTE_THRESHOLD else "ACTIVE"
```

Also bump the `COMMITTEE_SCORE_THRESHOLD` (line ~106, the gate that skips the flag function entirely) from whatever current value to 85.0 so we don't waste cycles on flagging signals that can't qualify.

### Change 2: Verify feed_tier still works correctly with ACTIVE status

`feed_tier_classifier.py` shouldn't care about status — confirm by reading the classifier logic. `feed_tier` is set during signal creation based on score + Tier 1 triggers, regardless of status. Skipping PENDING_REVIEW just means the signal stays ACTIVE longer but still routes to its proper feed (watchlist, ta_feed, research_log) for Nick to see in the UI.

### Change 3: Backlog cleanup migration

Add to `postgres_client.py` startup migration (one-time, same pattern as stuck-signal-cleanup):

```sql
-- One-time sweep of stale PENDING_REVIEW backlog (2026-04-22)
UPDATE signals
SET status = 'EXPIRED',
    notes = COALESCE(notes, '') || ' | Auto-expired 2026-04-22: stale PENDING_REVIEW backlog cleanup (pre-threshold-raise)'
WHERE status = 'PENDING_REVIEW'
  AND timestamp < NOW() - INTERVAL '7 days';
```

For signals in PENDING_REVIEW less than 7 days old (should be ~5), leave them alone. They'll either age out or Nick can manually review.

### Change 4: Update docs

In `PROJECT_RULES.md` and any relevant architecture docs, update the committee-flow description:
- OLD: "signals >= 80 auto-promote, 60-79 go to PENDING_REVIEW for manual click, <60 stays ACTIVE"
- NEW: "signals >= 85 auto-promote to COMMITTEE_REVIEW. All others go to ACTIVE with feed_tier routing. No PENDING_REVIEW state is used for new signals."

---

## Verification

1. After deploy, create a test signal at score 84 (via test script or wait for a natural one):
   - Expected: `status='ACTIVE'`, `feed_tier='watchlist'` or similar based on tier classifier
   - NOT: `status='PENDING_REVIEW'`

2. Create/wait for a test signal at score 86:
   - Expected: `status='COMMITTEE_REVIEW'`, `committee_requested_at=NOW()`
   - VPS bridge picks it up on next cron tick

3. Query for lingering PENDING_REVIEW:
   ```sql
   SELECT COUNT(*), MIN(timestamp), MAX(timestamp) 
   FROM signals 
   WHERE status = 'PENDING_REVIEW';
   ```
   Expected: count <= 5, all with recent timestamps (< 7 days old).

4. Spot-check feed: open Pandora dashboard, confirm watchlist and ta_feed are still populated with ACTIVE signals — they shouldn't have been affected by the status change.

---

## Expected impact

- **Committee runs per day:** drops from current ~10/day attempted to ~2-4/day actual (based on score distribution showing ~2-3 signals/day at 85+)
- **Credit burn:** drops by ~60% (from ~$1.30/day to ~$0.50/day)
- **PENDING_REVIEW queue:** empty most of the time
- **Cognitive noise for Nick:** eliminated — no backlog to mentally track

---

## Out of scope

- Adding a second tier "double-pass committee for 90+ signals" — separate follow-up brief if desired
- Re-running committee on the 24 stale 80+ signals that never got reviewed — they're expired now, water under the bridge

---

## Done when

- [ ] `pipeline.py` threshold raised to 85, PENDING_REVIEW eliminated as new-signal destination
- [ ] Migration cleans backlog older than 7 days
- [ ] `PROJECT_RULES.md` updated
- [ ] One test signal above and below threshold confirms correct routing
- [ ] PENDING_REVIEW count drops to ≤ 5 after deploy
