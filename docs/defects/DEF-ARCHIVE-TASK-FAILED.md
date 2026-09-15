# DEF-ARCHIVE-TASK-FAILED · P3

**Registered 2026-09-15 by R-IV.390(b). Status: OPEN — chase after the panels.**
**A local scheduled job has failed 38 consecutive nights and nothing read the result.**

---

## Measured

```
TradingHub-PriceHistoryArchive     daily 02:15, state Ready
  LastTaskResult 1  (non-zero = failure)      LastRunTime 2026-09-14 02:15:15

logs at data/archives/price_history/logs/   92 daily files, 2026-02-22 -> 2026-09-14
  runs carrying "archive failure"            73
  runs without                               19   (last clean: 2026-07-15)
  UNBROKEN FAILURE STREAK                    38   2026-07-16 -> 2026-09-14
```

**The job has not completed successfully in two months.** It ran every night, wrote a
log every night, exited non-zero every night, and the last archive output directory is
`run_20260715T081503Z`.

## Why P3 and not higher

**It archives `price_history` to local gzipped CSV.** Nothing downstream reads the
archive; the source table is intact and the job's `--purge` has evidently not been
purging, since it fails before it gets there. **No data has been lost — the archiving
simply has not happened.**

**If `--purge` had been reached and the archive write had then failed, this would be P1.**
It was not, and the ordering is luck rather than design: `purge=True` is in the arguments
of every failed run.

## THE LOG RECORDS THAT IT FAILED AND NOT WHY

```
2026-09-14T02:15:02 archive start | purge=True dry_run=False older_than_days=2 batch_size=25000
2026-09-14T02:15:03 archive failure: Traceback (most recent call last):
```

**342 bytes. The traceback's first line and nothing after it.**

**So even a reader would learn nothing.** The one artifact the job produces for a human
records the existence of a failure and discards its cause — **which is the
compute-then-discard shape, in a log file.** Twelfth instance.

## THE PATTERN — for the supervision brief

> **LOCAL SCHEDULED JOBS HAVE NO SENTINEL AND NO READER.**

**Everything inside the hub acquired supervision this month** — `job_runs`, the freshness
SLOs, `/health.stable_jobs`, the grader sentinel, the out-of-band failure channel.
**Every one of those watches a job running INSIDE the deployment.**

**A Windows scheduled task on the principal's machine has:**

- **no sentinel** — nothing computes its age or its expected cadence;
- **no reader** — `LastTaskResult` is written by the OS and consulted by nobody;
- **no alarm** — a non-zero exit is recorded and produces no signal anywhere;
- **and no surface** — it appears on no `/health` block, because `/health` is the
  deployment's health, and this does not run in the deployment.

**38 nights is the measure of that gap**, and the only reason it was found today is that
the task list was compiled to answer a question about something else entirely.

**The supervision brief's scope is therefore wrong as currently drawn**: it covers jobs
the hub schedules. **The hub is not the only thing that schedules jobs for the hub.**

## How it was found, recorded because the finding nearly did not survive its own check

**The first pass at this analysis used `iconv | grep` and reported "92 logs WITHOUT a
failure line" — including the file whose failure line had been read directly, minutes
earlier, by eye.** The logs are UTF-16; the pipeline failed silently and returned a clean
negative for every file.

**A check that returns "nothing found" for an input known to contain the thing is a null
verifier**, and it was built and run by the lane that has spent the week filing instances
of exactly that. **Caught only because the earlier direct read contradicted it.**

**The corrected read decodes UTF-16 explicitly and counts both classes — 73 failed, 19
clean — so the two numbers must sum to the file count, and they do.** A check that
reports both sides of a partition cannot silently return the empty set for one of them.
