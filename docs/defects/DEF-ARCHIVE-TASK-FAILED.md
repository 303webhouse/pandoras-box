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

---

## CAUSE FOUND, AND IT IS NOT WHAT THE LOG SUGGESTED (R-IV.391(a))

**Reproduced by running the job exactly as the task runs it — bare, `--dry-run`:**

```
ModuleNotFoundError: No module named 'database'
  -> fallback: from backend.database.postgres_client import ...
  -> backend/database/postgres_client.py:15
         from utils.json_sanitize import sanitize_for_json
ModuleNotFoundError: No module named 'utils'
```

**The dual-import fallback works one level deep and breaks at the next.**
`archive_price_history.py` guards its OWN import with a try/except — `database.` then
`backend.database.` — and the fallback succeeds in reaching the module. **But that module
uses unqualified imports (`from utils...`, `from database...`) which resolve only when
`backend/` is the path root**, which is how the app runs in the container and is not how
`python -m backend.jobs.archive_price_history` runs from the repo root.

**So the job has never been able to run under its own scheduled invocation** in the
configuration that has been in place since the 07-16 streak began. **It is a path
problem, not a database problem, not a data problem.**

**Fourteen traceback lines. The log kept one.**

## THE TWO FIXES TAKEN NOW

**1. PURGE DISABLED AT THE TASK — done and verified:**

```
BEFORE  -NoProfile -ExecutionPolicy Bypass -File ...un_price_history_archive.ps1
AFTER   -NoProfile -ExecutionPolicy Bypass -File ...un_price_history_archive.ps1 -NoPurge
```

**`purge` defaulted to TRUE** (`Read-BoolEnv -Name PRICE_HISTORY_ARCHIVE_PURGE -Default
$true`) and the task passed no switch — so the flag was never IN the arguments to remove;
it was a default, and the fix is the suppressing switch. **Applied to the live task and
read back to confirm.**

**Archive → verify → purge ordering is NOT yet implemented** — that is the chase. Purge
is off until it is.

**2. THE LOG NOW KEEPS THE TRACEBACK.** `$ErrorActionPreference = 'Continue'` around the
native call, so PowerShell 5.1's `NativeCommandError` wrapping of each stderr line is
non-terminating and the whole stream reaches `Tee-Object`. **The exit code decides
success, not the presence of a stderr line.**

### NOT YET IN EFFECT — stated so it is not assumed

**The logging fix is in the repo. The scheduled task runs from `C:	rading-hub`, which
is CC-POSITIONS' checkout**, and it will pick the change up when that tree next syncs.
**The purge change IS live immediately** — it was made on the task object, not in a file.

**So as of this filing: purge off everywhere, better logging in the repo only.**
