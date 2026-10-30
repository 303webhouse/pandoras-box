"""R-IV.1408(b)5 — the 1-minute bars export, DE-COUPLED from the dark-pool gate.

WHY IT HAD TO BE DE-COUPLED, and it is the answer to "why hadn't tonight's run written 10-23":

    `export_bars1m()` lived inside `f_export.py`, which only runs when
    `scripts/f_export_gate.py` opens. That gate's identity is
    `(latest_ended_run_id, eligible_count)` read from `darkpool_backfill_runs` and
    `darkpool_backfill_sessions` -- entirely about the DARK-POOL backfill, and nothing to do
    with yfinance bars. So the bars were gated on a dark-pool run counter.

    On 2026-10-23 that counter had not moved: run 19 was still the latest ended and eligible
    was still 312, so the gate printed `ALREADY_DONE: the archive is current for run 19` and
    exited 0 on all seven ticks from 19:00 to 21:00 MT. `f_export.py` never started, so
    `export_bars1m()` never ran, so session 10-23 was never written -- while every exit code a
    monitor could see said success.

    And the counter could not move again: `darkpool_backfill.ALLOWANCE_THROUGH` is
    2026-10-23, and past it both `run()` and the nightly loop refuse -- the loop RETURNS rather
    than sleeping. Confirmed from the record, not inferred: measured at 03:39 UTC (Fri 23:39
    EDT), after that night's 20:30-23:00 ET window had fully closed, the run ledger still
    showed run 19 as the latest and no run 20. So the F: export was not late for a night; it
    was shut permanently, bars included, by a date literal in an unrelated job.

WHAT THIS JOB IS, AND WHAT IT DELIBERATELY IS NOT
    It calls `export_bars1m()` and `export_bars1d()` and nothing else. Same paths, same parquet
    schema, same yfinance window -- R-IV.1408(b)5 forbids changing any of them, because
    TRITON-R and R2 both read these files.

    It does NOT read `darkpool_backfill_runs`, `_sessions` or `_pages`; it does not create or
    end a run; it does not consult `f_export_last_run.json`; and it does not write the
    archive's manifest. The manifest is `f_export.py`'s to author, and its `_archive_rows()`
    re-hashes whatever is on disk, so the next full export picks these files up. Writing it
    from here would mean reading the dark-pool completeness map to avoid dropping a section of
    it -- which is the exact coupling this job exists to remove.

    It is NOT gated on anything but F: being mounted. A bars export has no partial-night
    hazard: it rewrites a rolling 30-day window from scratch every run, so running twice is
    running once.

R-IV.1378(c) IS HONOURED BY THE EXPORT ITSELF, not by this job
    `export_bars1m()`'s window starts at `today - 29 days`, which today is 2026-09-25 -- the
    first day of the held range -- so every run would rewrite 09-25..10-15. The guard lives in
    `f_export.py` beside the one write site (`session_is_held`), so it protects the full export
    too, and this job reports what it skipped rather than discovering it silently.

EXITS, EACH DISTINGUISHABLE
    0  OK            bars written, and the run is recorded
    3  F_NOT_MOUNTED MANDARAX is a backup drive and may simply be unplugged
    4  FAILED        the export raised; the job_runs row carries the exception type
"""
from __future__ import annotations

import os
import re
import sys
import traceback
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
F_ROOT = r"F:\pandora-data"

EXIT_OK, EXIT_F_NOT_MOUNTED, EXIT_FAILED = 0, 3, 4

#: The job_runs name, imported from the one module that owns the vocabulary so the two cannot
#: drift, with a literal fallback because a scheduled task on this machine must not stop
#: exporting over an import error. A test asserts the fallback equals the constant.
try:
    sys.path.insert(0, os.path.join(REPO, "backend"))
    from jobs.job_runs import (JOB_F_EXPORT_BARS, STATUS_COMPLETED_DEFECTIVE, STATUS_ERROR,
                               STATUS_OK, STATUS_SKIPPED)
except Exception:                                                   # noqa: BLE001
    JOB_F_EXPORT_BARS = "f_export_bars"
    STATUS_OK, STATUS_ERROR, STATUS_SKIPPED = "ok", "error", "skipped"
    STATUS_COMPLETED_DEFECTIVE = "completed_defective"


def _say(msg: str) -> None:
    print("[f-export-bars] %s" % msg, flush=True)


def _pg_dsn() -> str:
    """The write URL from the gitignored .mcp.json. NEVER printed."""
    raw = open(os.path.join(REPO, ".mcp.json"), encoding="utf-8").read()
    for m in re.finditer(r"postgres(?:ql)?://[^\"\s]+", raw):
        if "railway.internal" not in m.group(0):
            return m.group(0)
    raise RuntimeError("no usable postgres URL in .mcp.json")


def session_date_for(now_local: datetime) -> date:
    """Which trading session a run belongs to.

    Same 06:00 boundary as the gate's: a nightly task that can fire either side of midnight
    must file both sides under one session, or "no row for this session" fires every night at
    midnight and the surface stops being read.
    """
    d = now_local.date()
    return d - timedelta(days=1) if now_local.hour < 6 else d


def _record(status: str, rows_touched=None, skip_reason=None, error=None) -> None:
    """One job_runs row. NEVER raises, never changes the exit code.

    Bookkeeping must not break the job it records -- and the point of this record is that
    "ran and wrote nothing", "never fired" and "failed" stop being the same thing seen from
    outside, which for this job they have been since it was written.
    """
    try:
        import asyncio
        import asyncpg

        async def _go():
            conn = await asyncpg.connect(_pg_dsn())
            try:
                await conn.execute(
                    "INSERT INTO job_runs (job_name, session_date, started_at, finished_at,"
                    " status, rows_touched, skip_reason, error)"
                    " VALUES ($1, $2, NOW(), NOW(), $3, $4, $5, $6)",
                    JOB_F_EXPORT_BARS, session_date_for(datetime.now().astimezone()),
                    status, rows_touched, skip_reason, error)
            finally:
                await conn.close()

        asyncio.run(_go())
    except Exception as exc:                                        # noqa: BLE001
        # The TYPE only. "the job did not record" and "the job did not run" are different
        # facts and only the log can separate them.
        _say("job_runs record FAILED (%s) -- the verdict above is this run's only trace"
             % type(exc).__name__)


def main() -> int:
    started = datetime.now(timezone.utc)
    _say("starting %s UTC" % started.strftime("%Y-%m-%d %H:%M:%S"))

    # F: FIRST, and it is the only gate. An unplugged backup drive is the likeliest reason
    # this cannot run, and it needs a person rather than a retry.
    if not os.path.isdir("F:\\"):
        _say("F_NOT_MOUNTED: F: is not present. MANDARAX is a backup drive; plug it in.")
        _record(STATUS_SKIPPED, skip_reason="F_NOT_MOUNTED: F: is not present")
        return EXIT_F_NOT_MOUNTED
    if not os.path.isdir(F_ROOT):
        _say("F_NOT_MOUNTED: F: is mounted but %s is absent -- refusing to create the archive "
             "root on what may be the wrong drive." % F_ROOT)
        _record(STATUS_SKIPPED,
                skip_reason="F_NOT_MOUNTED: %s absent on a mounted F:" % F_ROOT)
        return EXIT_F_NOT_MOUNTED

    sys.path.insert(0, HERE)
    try:
        from f_export import (R1378C_HOLD_ACTIVE, export_bars1d, export_bars1m,
                              export_polygon_bars1m)
    except Exception as exc:                                        # noqa: BLE001
        _say("FAILED: cannot import the export (%s)" % type(exc).__name__)
        _record(STATUS_ERROR, error="import failed: %s" % type(exc).__name__)
        return EXIT_FAILED

    try:
        summary = export_bars1m()
        print()
        export_bars1d()
    except Exception as exc:                                        # noqa: BLE001
        _say("FAILED: %s: %s" % (type(exc).__name__, str(exc)[:200]))
        traceback.print_exc()
        _record(STATUS_ERROR, error="%s: %s" % (type(exc).__name__, str(exc)[:200]))
        return EXIT_FAILED

    # R-IV.1456(g)2: the Polygon reference copy. Its own folder, never read by TRITON
    # (R-IV.1456(g)3), so a failure here is reported but does not fail the yfinance export.
    print()
    try:
        poly = export_polygon_bars1m()
    except Exception as exc:                                        # noqa: BLE001
        traceback.print_exc()
        poly = {"status": "error", "files_written": 0, "calls": 0,
                "reason": "%s: %s" % (type(exc).__name__, str(exc)[:160])}
    poly_line = "POLYGON %s: %d files, %d calls%s" % (
        str(poly.get("status")).upper(), poly.get("files_written", 0), poly.get("calls", 0),
        (" (%s)" % poly["reason"]) if poly.get("reason") else "")

    written = summary.get("files_written", 0)
    held = summary.get("sessions_held", 0)
    sessions = summary.get("sessions_written") or []
    empty = summary.get("tickers_empty") or []
    # R-IV.1456(g)1: write-once. Kept files and the sessions whose vendor copy differed.
    kept = summary.get("files_kept", 0)
    revised = summary.get("revised_sessions") or []

    # R-IV.1415(b)1: ONE LINE, carrying the held sessions it skipped -- COUNT AND RANGE -- and
    # the sessions it wrote. One line because this log is read by scrolling to the end of a
    # file, and a verdict spread over three lines is a verdict that gets half-read.
    #
    # The RANGE is what makes it checkable: a bare count cannot be compared against
    # R-IV.1378(c)'s 09-25..10-15, so a hold that silently widened or slipped would look
    # identical to one working correctly.
    held_dates = summary.get("held_dates") or []

    # R-IV.1417(d): NAME THE SESSIONS, never a RANGE. A range is what let a fabricated line
    # pass my own reading: "WROTE 56 files across 3 sessions (2026-10-16..2026-10-23)" is
    # self-contradictory -- that range spans six sessions -- and I quoted it as a run's output
    # when it came from a format-rendering snippet with hand-written numbers. A range invites
    # the reader to infer a count; a list cannot disagree with itself.
    #
    # The counts come from what was actually written: `files_written` is incremented per
    # write_parquet call and `sessions_written` is the set of sessions those writes landed in.
    if held != len(held_dates):
        # The count and the list are the SAME FACT from two places. If they ever disagree the
        # line must say so rather than print the prettier of the two.
        _say("INTERNAL INCONSISTENCY: held count %d but %d held dates recorded -- reporting "
             "both, trust neither" % (held, len(held_dates)))
    held_span = ("%s..%s" % (held_dates[0], held_dates[-1])) if held_dates else "none"
    _say("HELD %d (%s) | WROTE %d files across %d sessions: %s | KEPT %d | REVISED %d "
         "logged (%s) | window %s..%s%s | %s"
         % (len(held_dates), held_span, written, len(sessions),
            ",".join(sessions) if sessions else "NONE", kept,
            summary.get("revisions_logged", 0), ",".join(revised) if revised else "none",
            summary.get("window_start"), summary.get("window_end"),
            (" | %d tickers empty: %s" % (len(empty), ",".join(empty))) if empty else "",
            poly_line))

    # ZERO FILES IS A FAULT, NOT A SUCCESS, and saying so is the whole reason this record
    # exists. `completed_defective` is the existing vocabulary for it (R-IV.426(b)): the pass
    # ran to the end and its OWN output check failed. No new label (R-IV.925(b)).
    #
    # R-IV.1456(g)1: under write-once a night with no NEW session (a weekend, or a rerun) writes
    # nothing and keeps everything, which is correct. Zero is still a fault when nothing was
    # KEPT either -- the vendor served no session at all -- or a name came back empty.
    if written == 0:
        if not kept or empty:
            reason = ("wrote 0 session files and kept %d (%d held by R-IV.1378(c), %d tickers "
                      "empty)" % (kept, held, len(empty)))
            _say("COMPLETED BUT DEFECTIVE: %s" % reason)
            _record(STATUS_COMPLETED_DEFECTIVE, rows_touched=0, error=reason)
            return EXIT_OK

    notes = []
    if held:
        notes.append("%d sessions held by R-IV.1378(c)" % held)
    notes.append("kept %d, %d revisions logged" % (kept, summary.get("revisions_logged", 0)))
    notes.append(poly_line)
    _record(STATUS_OK, rows_touched=written, skip_reason="; ".join(notes)[:1000])
    _say("done in %.1fs" % (datetime.now(timezone.utc) - started).total_seconds())
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
