# DEF-STABLE-NIGHTLY-SUCCEEDS-WITHOUT-ADVANCING · P1

**Found** 2026-09-09 by CC-BUILD answering R-IV.331(e)'s liveness question. **Status:** OPEN.
**P1: a job reports success while its output is five days stale, and nothing can tell.**

---

## The question, and the answer that is worse than "no"

**R-IV.331(e) asked: `stable_daily_bars` ends 09-04 — did the stable job run after Tuesday's session?**

**IT RAN.**

```
nightly       last success  Tue 2026-09-08 21:02:23 ET   17.9 h ago
              status ok  ·  consecutive_failures 0  ·  last_error null
provisional   last success  Wed 2026-09-09 09:45:34 ET    5.2 h
movers/strip  last success  Wed 2026-09-09 14:56:06 ET    0.0 h
overall /health: healthy   any_flatline: false
```

**Tuesday 21:02 ET is the documented ~21:00 nightly slot, after the 16:00 close.** The job
fired on schedule, completed, and reported success with zero failures and no error.

**And `stable_daily_bars` still ends 2026-09-04** (spine's datum). **Five sessions of bars are missing
from a job that has reported success on every one of them.**

## The mechanism, and it is a familiar one

**`last_success_age_s` is a JOB-COMPLETION marker, not a DATA-ADVANCEMENT check.** It records that the
coroutine returned without raising. It does not ask whether a single row was written, nor
whether the newest bar is newer than the last one.

**So the probe cannot fail when the data stops.** That is conventions #12 — *a liveness
probe is a consumer that fails when the source dies* — and this probe is not a consumer of
the output at all. It watches the job, and **the job is fine.**

**Third instance of that law this week**, after the UW burn counter and the grader's
`signals_freshness` age source. **Every one of them measured the wrong quantity in the
right place.**

## Why P1

**`stable_daily_bars` is the recompute path's input**, and per the census it is also the **UUP series
Amendment 1's S2 stratum reads** for the DXY proxy. A five-day-stale bar table means:

- the nightly's theme scores and structural metrics are computed on stale closes;
- **S2's proxy would be stamped from a series that stopped on 09-04**, and the registration
  declares it stamped at fire.

**And `/health` says `healthy`** — which is the reason this is P1 rather than P2. A stale
output behind a green light is not a degraded system, it is **a system reporting the wrong
state**, and every consumer downstream is entitled to believe it.

## Not determined here

**WHY the bars stopped advancing on 09-04.** The job succeeds, so the failure is inside a
path that swallows. **Candidates, unread:** the yfinance fetch returning empty for the
bar symbols; a write that no-ops on conflict; a date-window bound that stopped moving.
**This lane read the job's status, not its body** — and the whole point of the finding is
that status was the wrong thing to read.

## Fix shape — not chosen here

**The nightly's success predicate must include its output.** *"Ran without raising"* is not
success for a job whose purpose is to advance a table; **"the newest bar is newer than it
was"** is. Same correction as the grader's: a job that ran and wrote nothing is a job that
ran and wrote nothing, and it should say so.
