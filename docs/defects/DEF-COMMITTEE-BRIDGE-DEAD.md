# DEF-COMMITTEE-BRIDGE-DEAD

**Severity:** P1 (ops) · **Filed:** 2026-08-18 · **Status:** OPEN
**Surface:** Olympus committee bridge (VPS/OpenClaw cron -> hub write-back)

## Symptom
STRIKE-Q2 Q2.5: `committee_requested_at` set on 171 signals across the full
2026-07-30->08-16 window; `committee_completed_at` set on ZERO. Every day, all
window. COMMITTEE_REVIEW is a waiting room no one has ever exited.

## Why it matters
The review tier is the pipeline's premium surface; a dead bridge means every
promoted signal ages out ungraded by the committee path, and
`outcome_source='COMMITTEE_REVIEW'` logging (queued feature) has no live path.

## Investigation pointers
VPS `/opt/openclaw` committee bridge cron (*/3 market hours, Mon-Fri
13:00-20:00 UTC); token budget 50K/hr / 200K/day; audit log
`/var/log/committee_audit.log`. Check: cron alive? auth valid? write-back
endpoint reachable? errors in audit log?

## Fix path
Separate VPS-side session (A3). Acceptance: a signal requested during RTH
receives `committee_completed_at` within one cron cycle, two consecutive days.
