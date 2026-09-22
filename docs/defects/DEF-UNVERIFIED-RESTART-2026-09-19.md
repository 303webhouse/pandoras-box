# DEF-UNVERIFIED-RESTART — a process restarted and nothing could say why

**Registered:** R-IV.464(f). **Observed:** CC-BUILD, 2026-09-19 16:50 UTC (10:50 MDT).
**Status:** CAUSE UNKNOWN. A boot record is now written (migration 051) so the next one is
visible; this one cannot be recovered.

> An unverified restart on a system whose state is partly in memory is not a footnote.

## WHAT WAS OBSERVED

| reading | value |
|---|---|
| build running | `aaf9163` (deployed by CC-BUILD earlier that day) |
| uptime at 16:50 UTC | **1,099 s** -- so the process started at about **16:32 UTC (10:32 MDT)** |
| deploys by this lane between those times | none; the previous push was hours earlier |
| health status | `degraded` before and after, unchanged (factor staleness, a standing condition) |

**The cause could not be read at all.** `railway logs` and `railway deployment list` both refused:
the CLI in this working copy is linked to the project but **not to a service**, so the deployment
and restart history was unreachable from here. `railway variables` works, which is why the reads
that need credentials kept working and this one did not.

## WHY IT MATTERS

Part of this system's state lives in the process, not in the database:
- the mark-to-market loop's own timer, and the stable-jobs schedule;
- the SWR caches in front of several read paths;
- the circuit breaker's in-process reading (its ARMED state is persisted in Redis, which is why
  the latch survives a restart -- DEF-KILLSWITCH-LATCH -- but the reading behind it is not);
- anything holding a vendor session.

A restart silently re-derives all of it. If the restart was an OOM kill or a platform eviction,
it will recur, and a lane reading "uptime 1,099 s" without noticing would read the re-derived
state as continuous.

## WHAT IS NOW IN PLACE

`service_boots` (migration 051, mirrored in the boot DDL): every start of the app inserts a row
with its commit SHA. A restart is then visible in the book's own store, in SQL, without a console:

```sql
SELECT booted_at, commit_sha FROM service_boots ORDER BY booted_at DESC LIMIT 20;
```

Two boots of the same commit with no deploy between them is a restart, and its instant is the row.

## THE RECORD MISSED THE NEXT ONE (measured 2026-09-22)

`service_boots` recorded the two deploys of 2026-09-20 (04:21:24 and 06:53:58 UTC) and **missed a
restart**: `/health` reports the running process started **2026-09-20 15:21:32 UTC** and has run
since (53 hours at the time of measurement), and no row exists for it.

**The record sat behind the work it was meant to witness.** The insert was one entry in
`init_database`'s guarded statement loop, so it was written only when the schema work reached it.
A boot whose schema init aborts earlier -- a lock timeout on an ALTER is the likely way -- boots
anyway, serves traffic, and leaves no trace.

**Fixed:** the row is now the FIRST write of the boot, in its own transaction, before any schema
work, and a failure to record is logged rather than fatal. The row gains a completion note at the
end of `init_database`, so **a row without it is a boot whose schema init did not finish** -- also
readable in SQL, without a console. Both are what the next restart will be read from.

> A record that exists only when everything else worked is not a record of what happened.

## STILL OPEN

- **This restart's cause.** Not recoverable from here.
- **The CLI is not linked to a service** in either working copy, so logs and deployment history
  are unreachable to this lane. Linking it is a one-line change to the local checkout and is not
  done here, because it is the principal's account and the link is an environment change, not a
  repo one.
