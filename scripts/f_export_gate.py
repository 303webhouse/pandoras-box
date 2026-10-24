"""The gate in front of the F: export — R-IV.997(b). Never export a partial night.

WHY A GATE AND NOT A CLOCK. `PandoraFExportNightly` fired at a fixed 21:30 MT while the
backfill starts 18:30 MT and runs for a length that varies with how much is left: run 5 took
34 minutes, run 8 took 6, run 7 was still walking when a deploy killed it. A fixed time is a
guess about a duration nobody controls, and the cost of guessing wrong is a PARTIAL night on a
permanent archive, which a reader cannot tell from a whole one.

THREE EXITS, EACH DISTINGUISHABLE. A single non-zero code would make "the drive is unplugged"
look like "the run is still going", and those want opposite responses: one is waiting, the
other is a person plugging something in.

    0  EXPORTED or ALREADY_DONE   the archive is current for this night's run
    2  RUN_IN_PROGRESS            a backfill run has no ended_at; retry (scheduler repeats)
    3  F_NOT_MOUNTED              MANDARAX is a backup drive and may simply be unplugged
    4  GATE_ERROR                 the gate itself could not decide -- NOT treated as clear

4 IS NOT 0 ON PURPOSE. A gate that cannot reach the database does not know whether a run is
active, and "I could not check" must never be allowed to read as "nothing is running".

AND AS OF R-IV.1398(b)4, EVERY TICK WRITES A `job_runs` ROW. The five exits above were
distinguishable to a PERSON reading the log and to nothing else: the scheduler keeps no
history, so six ticks on 2026-10-23 that each returned 0 for ALREADY_DONE looked exactly like
six successful exports, and the bars for that session were never written. The record makes the
three states the ruling names separable by query:

    ran and did nothing   status `skipped`, with the verdict in `skip_reason`
    late / never fired    NO ROW for the session -- absence is the signal
    failed                status `error` (the gate could not decide) or
                          `completed_defective` (it exported, and the match report disagreed)

ONE LIMIT, STATED RATHER THAN HIDDEN: a GATE_ERROR caused by an unreachable database cannot
be recorded, because recording needs that database. Such a tick leaves no row and is therefore
indistinguishable from a tick that never fired. The log still carries it. Fixing that would
need a second, independent store, which is a bigger change than this ruling asked for.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
F_ROOT = r"F:\pandora-data"
#: Which run the archive was last exported for. A plain file, because the scheduler fires this
#: every 30 minutes and re-exporting 1.2 million prints on each tick would be absurd.
STATE = r"C:\lane-state\f_export_last_run.json"

EXIT_OK, EXIT_RUN_IN_PROGRESS, EXIT_F_NOT_MOUNTED, EXIT_GATE_ERROR = 0, 2, 3, 4

#: The `job_runs.job_name` this gate records under. Imported from the one module that owns the
#: job-name vocabulary so the two cannot drift, with a literal fallback because this script
#: runs from a scheduler on a machine where an import failure must not stop the export. A test
#: asserts the fallback equals the constant -- a silent fallback to a DIFFERENT name would
#: write rows nobody queries, which is the fault this record exists to fix, one level up.
try:
    sys.path.insert(0, os.path.join(REPO, "backend"))
    from jobs.job_runs import (JOB_F_EXPORT, STATUS_COMPLETED_DEFECTIVE, STATUS_ERROR,
                               STATUS_OK, STATUS_SKIPPED)
except Exception:                                                   # noqa: BLE001
    JOB_F_EXPORT = "f_export"
    STATUS_OK, STATUS_ERROR, STATUS_SKIPPED = "ok", "error", "skipped"
    STATUS_COMPLETED_DEFECTIVE = "completed_defective"


def _say(msg: str) -> None:
    print("[f-export-gate] %s" % msg, flush=True)


def _pg_dsn() -> str:
    """The write URL from the gitignored .mcp.json. NEVER printed."""
    raw = open(os.path.join(REPO, ".mcp.json"), encoding="utf-8").read()
    for m in re.finditer(r"postgres(?:ql)?://[^\"\s]+", raw):
        if "railway.internal" not in m.group(0):
            return m.group(0)
    raise RuntimeError("no usable postgres URL in .mcp.json")


async def _active_run():
    """(active_run_row_or_None, latest_ended_run_id_or_None). Raises on a DB failure."""
    import asyncpg
    conn = await asyncpg.connect(_pg_dsn())
    try:
        # Same discriminator as deploy_guard: a null `ended_at` is only "in progress" when
        # no LATER run has finished. Otherwise a single stale row (run 7) would hold the
        # nightly export shut forever, which is a silence that looks like a wait.
        active = await conn.fetchrow(
            "SELECT r.id, r.started_at, r.uw_day FROM darkpool_backfill_runs r "
            " WHERE r.ended_at IS NULL "
            "   AND NOT EXISTS (SELECT 1 FROM darkpool_backfill_runs l "
            "                    WHERE l.id > r.id AND l.ended_at IS NOT NULL) "
            " ORDER BY r.id DESC LIMIT 1")
        latest = await conn.fetchval(
            "SELECT id FROM darkpool_backfill_runs "
            "WHERE ended_at IS NOT NULL ORDER BY id DESC LIMIT 1")
        # THE ELIGIBLE SET, not just the run id. Completeness can change WITHOUT a new run:
        # R-IV.1005(d)'s b2 route made 40 ticker-sessions newly exportable from pages already
        # stored, and a gate keyed only on run_id would have reported ALREADY_DONE and left
        # the archive short until the next night. A stale archive that reports itself current
        # is the failure this whole gate exists to avoid.
        eligible = await conn.fetchval(
            "SELECT COUNT(*) FROM darkpool_backfill_sessions "
            " WHERE exhausted = TRUE AND reached_floor = TRUE AND prints_received > 0")
        return (dict(active) if active else None), (latest, int(eligible or 0))
    finally:
        await conn.close()


def session_date_for(now_local: datetime) -> "date":
    """Which trading session a tick belongs to.

    The scheduler fires every 30 minutes from 19:00 to 05:00 MT, so a single night's ticks
    straddle midnight and a naive `date.today()` would file the 01:00 tick under tomorrow --
    splitting one night across two session dates and making "no row for this session" fire
    every night at midnight. Everything before 06:00 local belongs to the previous session.

    06:00, not midnight, because the boundary only has to sit between the last tick of a night
    (05:00) and the first of the next (19:00); anywhere in that gap is correct, and a boundary
    in the middle of it cannot be tripped by a tick running a few minutes late.
    """
    d = now_local.date()
    return d - timedelta(days=1) if now_local.hour < 6 else d


def _record_job_run(status: str, skip_reason=None, error=None, rows_touched=None) -> None:
    """Write one job_runs row for this tick. NEVER raises, never changes the exit code.

    Bookkeeping must not break the job it records -- the same posture `jobs/job_runs.py`
    argues for, and for the same reason: a recorder that can fail the run it watches is a
    worse outage than the blindness it was added to cure.
    """
    try:
        import asyncio as _asyncio
        import asyncpg as _asyncpg

        async def _go():
            conn = await _asyncpg.connect(_pg_dsn())
            try:
                await conn.execute(
                    "INSERT INTO job_runs (job_name, session_date, started_at, finished_at,"
                    " status, rows_touched, skip_reason, error)"
                    " VALUES ($1, $2, NOW(), NOW(), $3, $4, $5, $6)",
                    JOB_F_EXPORT, session_date_for(datetime.now().astimezone()),
                    status, rows_touched, skip_reason, error)
            finally:
                await conn.close()

        _asyncio.run(_go())
    except Exception as exc:                                        # noqa: BLE001
        # Named in the log rather than swallowed in silence: "the gate did not record" and
        # "the gate did not run" are different facts, and only the log can tell them apart.
        _say("job_runs record FAILED (%s) -- the verdict above is the only trace of this tick"
             % type(exc).__name__)


def _last_exported():
    """(run_id, eligible_count) last exported, or (None, None)."""
    try:
        with open(STATE, encoding="utf-8") as fh:
            d = json.load(fh)
        return d.get("run_id"), d.get("eligible")
    except Exception:                                               # noqa: BLE001
        return None, None


def _record(run_id, eligible: int, mismatches: int) -> None:
    """Write the run's bookkeeping, temp-then-replace (Convention #45, R-IV.1213(c)).

    FOUND BY #45's OWN SELF-CHECK, not by a failure. This file is a small JSON regenerated on
    every run, so truncating it loses one run's bookkeeping rather than thousands of lines of
    history -- nothing like the BUILD.md incident. But the hazard is identical in shape:
    `open(STATE, "w")` truncates before anything is serialised, so an exception while building
    the payload leaves an empty file where a reader expects JSON, and the next read fails on a
    file that exists.

    Serialise first, then write a temp, then replace. A payload that cannot be built cannot
    destroy the previous one.
    """
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    payload = json.dumps({"run_id": run_id, "eligible": eligible, "mismatches": mismatches,
                          "exported_at": datetime.now(timezone.utc).isoformat()}, indent=2)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(payload)
    os.replace(tmp, STATE)


def main() -> int:
    _say("checking at %s UTC" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))

    # F: FIRST. There is no point asking the database whether a run finished if the archive
    # cannot be written either way, and an unplugged drive is the likeliest of the three.
    if not os.path.isdir("F:\\"):
        _say("F_NOT_MOUNTED: F: is not present. MANDARAX is a backup drive; plug it in.")
        # SKIPPED, not error: the gate ran and declined correctly, and an unplugged backup
        # drive is the most ordinary state this gate meets. `error` here would cry wolf most
        # nights and the real alarm would stop being read. The reason carries the verdict.
        _record_job_run(STATUS_SKIPPED, skip_reason="F_NOT_MOUNTED: F: is not present")
        return EXIT_F_NOT_MOUNTED
    if not os.path.isdir(F_ROOT):
        _say("F_NOT_MOUNTED: F: is mounted but %s is absent -- refusing to create the "
             "archive root on what may be the wrong drive." % F_ROOT)
        _record_job_run(STATUS_SKIPPED,
                        skip_reason="F_NOT_MOUNTED: %s absent on a mounted F:" % F_ROOT)
        return EXIT_F_NOT_MOUNTED

    try:
        active, (latest_ended, eligible) = asyncio.run(_active_run())
    except Exception as exc:                                        # noqa: BLE001
        _say("GATE_ERROR: could not read the run ledger (%s: %s). NOT treating this as "
             "'nothing is running'." % (type(exc).__name__, exc))
        # This is the one tick that may leave NO ROW: the record needs the database that just
        # refused to answer. Attempted anyway -- the failure may have been in the query rather
        # than the connection -- and the header states the limit.
        _record_job_run(STATUS_ERROR,
                        error="GATE_ERROR: run ledger unreadable (%s)" % type(exc).__name__)
        return EXIT_GATE_ERROR

    if active:
        _say("RUN_IN_PROGRESS: run %s started %s has no ended_at. Not exporting a partial "
             "night; the scheduler will retry." % (active["id"], active["started_at"]))
        _record_job_run(STATUS_SKIPPED,
                        skip_reason="RUN_IN_PROGRESS: run %s has no ended_at" % active["id"])
        return EXIT_RUN_IN_PROGRESS

    if latest_ended is None:
        _say("GATE_ERROR: no completed backfill run exists at all. Refusing to export "
             "against a ledger with nothing in it.")
        _record_job_run(STATUS_ERROR,
                        error="GATE_ERROR: no completed backfill run exists")
        return EXIT_GATE_ERROR

    was_run, was_eligible = _last_exported()
    if was_run == latest_ended and was_eligible == eligible:
        _say("ALREADY_DONE: the archive is current for run %s (%d eligible ticker-sessions)."
             % (latest_ended, eligible))
        # THE STATE THAT WAS INVISIBLE, and the reason this ruling exists. Six ticks returned
        # this on 2026-10-23 with exit 0, which any monitor reads as success, while the bars
        # for that session were never written -- `export_bars1m` runs inside `f_export.py`,
        # behind this gate, so the yfinance bars are gated on a DARK-POOL run counter that had
        # not moved. `skipped` with the verdict in `skip_reason` is now queryable.
        _record_job_run(STATUS_SKIPPED, rows_touched=0,
                        skip_reason="ALREADY_DONE: archive current for run %s (%d eligible)"
                                    % (latest_ended, eligible))
        return EXIT_OK

    if was_run == latest_ended:
        _say("run %s unchanged but the eligible set moved %s -> %d -- exporting."
             % (latest_ended, was_eligible, eligible))
    else:
        _say("run %s has ended and is not yet exported (%d eligible) -- exporting."
             % (latest_ended, eligible))
    proc = subprocess.run([sys.executable, "-B", os.path.join(HERE, "f_export.py")],
                          cwd=REPO)
    # f_export returns 0 only when DB-complete and F: AGREE on every in-window date.
    _record(latest_ended, eligible, proc.returncode)
    if proc.returncode == 0:
        _say("EXPORTED: run %s, and the match report agrees." % latest_ended)
        _record_job_run(STATUS_OK, rows_touched=eligible)
        return EXIT_OK
    _say("EXPORTED run %s but the match report did NOT agree (exit %d) -- see the log."
         % (latest_ended, proc.returncode))
    # `completed_defective` is the existing vocabulary for exactly this (R-IV.426(b)): the
    # pass ran to the end and its OWN output check failed. No new label (R-IV.925(b)).
    _record_job_run(STATUS_COMPLETED_DEFECTIVE, rows_touched=eligible,
                    error="match report disagreed (f_export exit %d)" % proc.returncode)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
