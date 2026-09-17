# DEF-COMMITTEE-REVIEW-STRANDED — filed, not fixed

**Registered:** R-IV.442(c). **Filed by:** CC-BUILD, 2026-09-17. **Status:** OPEN, deliberately
not remediated tonight. **Measured against the database**, not against the code that writes it.

> **A producer with no consumer does not fail. It accumulates.** Nothing errored, no alert
> fired, no count went to zero — rows entered a status that nothing has taken them out of
> since 2026-05-01, and the system carried on looking exactly as it does when it is working.

---

## THE MEASUREMENT (2026-09-17)

| reading | value |
|---|---|
| `signals` rows at `status = 'COMMITTEE_REVIEW'` | **704** |
| …older than 30 days | **502** |
| oldest | **2026-05-01** — the day the consuming pipeline last produced output |
| newest | **today**, minutes before this file was written |
| created in the last 7 days | **22** |
| created in the last 24 hours | **7** |
| distinct days on which one was created | **89** |
| carrying `user_action` | **697 of 704**, all `DISMISSED` |
| carrying an `expires_at` | **2** |

**The ruling counted 702; the live table holds 704.** The difference is not an error in either
count — **it is the finding restated.** Two more arrived between the census and this filing.

## WHAT IS ACTUALLY WRONG, IN THREE PARTS

**1. The status is terminal by accident.** `COMMITTEE_REVIEW` means *"waiting for the
committee"*. Nothing moves a row out of it. The 24-hour sweep that ages signals writes
`user_action` and leaves `status` exactly where it was, so 697 rows are simultaneously
**dismissed and still awaiting review** — two fields telling two different stories about the
same row, and only one of them is what a status filter reads.

**2. The producer outlived the consumer by four and a half months.** Rows are still being
created — 22 in the last week — into a queue whose reader stopped on 2026-05-01. Every one of
them is a request for a decision that nothing is going to make.

**3. Nobody noticed, and that is the part worth keeping.** There is no surface on which
"committee output" going to zero is visible. The queue has no age alarm, the status has no
expiry, and a dead consumer presents identically to an idle one. **Four months of silence read
the same as four months of quiet.**

> This is the supervision argument in one line: **a pipeline is not observed by the existence
> of its inputs.** Something has to read its OUTPUT and say when it stopped.

## WHY IT IS NOT FIXED TONIGHT

Ruled: file it. And the remedy is not obvious enough to take unilaterally — three different
fixes are defensible and they are not the same fix:

- **expire the status** (rows age out of `COMMITTEE_REVIEW` like every other pending state),
- **stop producing** (the writer stops queueing for a consumer that is gone), or
- **restore the consumer** (the committee pipeline runs again, and the 502 are its backlog).

Choosing among them decides whether 502 rows are *garbage*, *evidence*, or *work*. That is a
ruling, not a build decision, and writing the wrong one is irreversible for the rows it
touches.

## WHAT MUST NOT BE DONE FIRST

**Do not clear the 502 to make a count look healthy.** They are the only record that the
consumer died on 2026-05-01 and that nothing has read the queue since. Deleting them removes
the evidence of the defect while leaving the defect — the producer would keep writing, and the
next reader would find a small, fresh, entirely convincing pile.
