# Brief: Clear stuck stale committee signals (SNOW + CRM)

**Date:** 2026-04-21
**Priority:** P0 (blocks today's committee queue, 2-minute fix)
**Target:** Claude Code (VSCode)
**Estimated effort:** 5 min

---

## Context

Two signals are stuck in `status='COMMITTEE_REVIEW'` with retry counter maxed (3/3) after the 2026-04-16 Anthropic credit exhaustion. They are now >5 days old — the underlying setups are stale. Nick confirmed: discard.

A third stuck signal (LCID, from 2026-04-21) is current and should remain in the queue for re-attempt tomorrow once credits are restored (done 2026-04-21 evening).

---

## Stuck signals

| signal_id | Ticker | Strategy | Age | Action |
|---|---|---|---|---|
| `HG_SNOW_20260414_131507` | SNOW | Holy_Grail LONG @ $134.28 | 7 days | DISCARD |
| `ARTEMIS_CRM_20260416_141203_140577` | CRM | Artemis LONG @ $179.01 | 5 days | DISCARD |
| `HG_LCID_20260421_143922` | LCID | Holy_Grail LONG @ $7.51 | 0 days | KEEP — reset retry counter |

---

## Execution

Run the following SQL against Railway Postgres. Use `backend/database/postgres_client.py::get_postgres_client()` from a one-off script, or psql directly with the public URL (see `PROJECT_RULES.md` and memory #12).

```sql
-- 1. Mark stale stuck signals as EXPIRED (audit-preserving, non-destructive)
UPDATE signals
SET status = 'EXPIRED',
    expired_at = NOW(),
    notes = COALESCE(notes, '') || ' | Auto-discarded 2026-04-21: stuck in COMMITTEE_REVIEW due to credit exhaustion, setup stale'
WHERE signal_id IN (
    'HG_SNOW_20260414_131507',
    'ARTEMIS_CRM_20260416_141203_140577'
)
  AND status = 'COMMITTEE_REVIEW';

-- 2. Verify update
SELECT signal_id, ticker, status, expired_at
FROM signals
WHERE signal_id IN (
    'HG_SNOW_20260414_131507',
    'ARTEMIS_CRM_20260416_141203_140577',
    'HG_LCID_20260421_143922'
);
```

---

## VPS-side retry counter reset (for LCID only)

The bridge retry tracker lives in a JSON file on the VPS at `/opt/openclaw/workspace/data/bridge_signal_attempts.json`. Need to:

1. SSH to VPS: `ssh openclaw@188.245.250.2`
2. Edit the file: `nano /opt/openclaw/workspace/data/bridge_signal_attempts.json`
3. Find the entries for the three signal IDs above
4. For SNOW + CRM: leave them alone (committee bridge will skip them now that status=EXPIRED)
5. For `HG_LCID_20260421_143922`: reset `attempts` to 0 and `last_error` to null, OR just delete the entry entirely (bridge treats missing entry as fresh signal)

Example JSON edit for LCID:
```json
{
  "HG_LCID_20260421_143922": {
    "attempts": 0,
    "last_attempt": null,
    "last_error": null
  }
}
```

Also reset the daily-count dedup key if LCID appears in `/opt/openclaw/workspace/data/bridge_daily_count.json` — the bridge skips signals already processed today. If `HG_LCID_20260421_143922` is in the `signal_ids` array for today's date, remove it so the bridge tries again.

---

## Verification

After SQL runs and VPS file edits are done:

1. Hit `GET /api/committee/queue` from the VPS (curl with X-API-Key header) — should return only `HG_LCID_20260421_143922`
2. Wait for next bridge cron tick (every 3 min during market hours, 13:00-20:00 UTC weekdays)
3. Check `/var/log/committee_bridge.log` for `Running committee on LCID...` line
4. If credits are present (check via new credit monitor when that brief lands), LCID should run successfully and post to Discord

---

## Done when

- [ ] SNOW + CRM signals have `status='EXPIRED'` in signals table
- [ ] LCID retry counter reset in `bridge_signal_attempts.json`
- [ ] LCID removed from today's `bridge_daily_count.json` dedup list
- [ ] Next bridge cron run processes LCID (check log)
