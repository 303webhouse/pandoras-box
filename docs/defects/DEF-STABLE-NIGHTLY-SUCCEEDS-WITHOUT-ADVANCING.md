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

---

## ESCALATION 2026-09-11 — IT NO LONGER SUCCEEDS. IT IS FLATLINE.

**Measured live 2026-09-11 14:52Z (08:52 MT / 10:52 ET) from `/health`:**

```
stable_jobs.jobs.nightly.status              flatline
stable_jobs.jobs.nightly.last_success_age_s  136160   = 37.8 h
stable_jobs.oldest_feed_age_s                136160
stable_jobs.any_flatline                     True
signals_freshness.any_flatline               False
/health.status                               degraded
```

**Last success: Wed 2026-09-09 21:02 ET. Thursday's 21:00 run did not succeed.**

### FIRST: IS THIS THE WEEKEND ARTIFACT? NO — and the check is mandatory here

**`DEF-NIGHTLY-FLATLINE` records that the 26 h SLO on a weekday-only job renders `flatline`
every weekend BY CONSTRUCTION** — ~104 false reds a year — **and this lane already reported a
recurrence off that artifact once, on 2026-08-24, and retracted it.** So the discriminator is
applied before any claim:

```
nightly gate   stable_jobs.py:29  NIGHTLY_TIME = (21, 0) ET
               stable_jobs.py:69  if not is_weekday(dt): return   (weekday() < 5)

Wed 2026-09-09  weekday()=2  scheduled  <- last SUCCESS, 21:02 ET
Thu 2026-09-10  weekday()=3  scheduled  <- MISSED. This is the tell.
Fri 2026-09-11  weekday()=4  scheduled  <- reading taken 10:52 ET
```

**The 37.8 h gap SPANS A SCHEDULED WEEKDAY SLOT.** The maximum legitimate gap inside a
weekday run is ~24 h; the weekend gate cannot produce 37.8 h on a Friday morning, because no
weekend intervened. **REAL, not the artifact.**

### The defect has CHANGED CHARACTER, and the new state is the better one

**This register named it for succeeding while its output stood still.** It no longer does
that. **It now fails, and says so.**

| | before | now |
|---|---|---|
| job status | `ok` | **`flatline`** |
| output | `stable_daily_bars` ending 09-04 | still stale |
| `/health.status` | `healthy` | **`degraded`** |

**A job that fails honestly is strictly more useful than one that succeeds falsely** — the
first is visible on a surface someone already watches, the second was only findable by
comparing a status against a table. **The name on this file now describes a past state.**
**Kept, so citations resolve**, with the current state on its face.

### And it is the SOLE cause of `degraded`

`signals_freshness.any_flatline` is **False**; `stable_jobs.any_flatline` is **True**.
**Nothing else on the surface is contributing.** Anyone reading `degraded` today is reading
this defect and only this defect.

### NOT DETERMINED HERE

**Why Thursday's run failed.** No log read was taken. **Whether the flatline and the stale
`stable_daily_bars` share a cause is UNREAD** — the table was already stale while the job was
still reporting `ok`, so **the staleness predates the flatline and cannot have been caused by
it.** That ordering is established; the cause is not.

**Related and still unproven as cause:** `DEF-STABLE-REGIME-FROM-N2` — `breadth.total = 1` is
the shape of a partially-written day, and a nightly that has not advanced in 37.8 h is a
candidate for why the metrics table holds one qualifying row. **Candidate, not conclusion.**

---

## CAUSE - READ FROM THURSDAY'S LOG, 2026-09-11 (R-IV.356(d))

**One line: Postgres entered RECOVERY mid-run and severed the job's connection.**

```
INFO:jobs.stable_jobs:[stable_jobs] nightly close recompute starting
WARNING:jobs.stable_jobs:[stable_jobs] nightly failed: connection already closed
WARNING:stable_engine.job_status:[job_status] mark_failure(nightly) failed:
        the database system is in recovery mode
DETAIL:  Consistent recovery state has not been yet reached.   (x3)
```

**The job STARTED.** Not skipped, not mis-scheduled, not gated off. Its connection died
underneath it, and Postgres was still replaying WAL when it tried to say so.

### THE STRUCTURAL FINDING - the failure recorder shares the failure's dependency

**`mark_failure(nightly)` ALSO FAILED, for the same reason.** So there is no error row: the
job's error channel needed the database that was down.

**Which is why this surfaced as `flatline` - an AGE - and not as an error status.** The
age-based SLO was the ONLY instrument that caught it, precisely because it is computed from
the ABSENCE of a success rather than the presence of a report. **An error channel that depends
on the resource it reports on cannot report that resource failing.**

**`DEF-NIGHTLY-FLATLINE` spends its length on that SLO's false reds. Today it earned its
keep** - and the same file carries the discrimination that proved today's red real.

### THE DEFECT IS NOT THE OUTAGE. IT IS THAT NOTHING RETRIED.

**Postgres recovered. The nightly did not re-run.** It is scheduled once, 21:00 ET on a
weekday, so a pass consumed by a transient outage is lost until the next slot - **a few
minutes of database blip costs a full day of `stable_daily_bars`.**

**FIX SHAPE - NOT a one-liner, so Saturday's first item by R-IV.356(d)'s own test.** A
catch-up needs a did-this-session's-pass-complete predicate, which is exactly what
`jobs/job_runs.has_completed()` was built for on the grader - the machinery exists, but wiring
it changes WHEN the job may run, and that is scheduling semantics rather than a patch.

**The CAUSE rides tonight. The FIX does not.**

### Ordering, restated because it constrains Saturday

**The stale `stable_daily_bars` PREDATES this outage** - already ending 09-04 while the job
still reported `ok` on 09-08. **Separate cause, separate line.** A retry recovers the lost
Thursday; it does not explain 09-04.
