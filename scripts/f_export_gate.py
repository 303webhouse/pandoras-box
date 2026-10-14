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
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
F_ROOT = r"F:\pandora-data"
#: Which run the archive was last exported for. A plain file, because the scheduler fires this
#: every 30 minutes and re-exporting 1.2 million prints on each tick would be absurd.
STATE = r"C:\lane-state\f_export_last_run.json"

EXIT_OK, EXIT_RUN_IN_PROGRESS, EXIT_F_NOT_MOUNTED, EXIT_GATE_ERROR = 0, 2, 3, 4


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
        return (dict(active) if active else None), latest
    finally:
        await conn.close()


def _last_exported_run():
    try:
        with open(STATE, encoding="utf-8") as fh:
            return json.load(fh).get("run_id")
    except Exception:                                               # noqa: BLE001
        return None


def _record(run_id, mismatches: int) -> None:
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump({"run_id": run_id, "mismatches": mismatches,
                   "exported_at": datetime.now(timezone.utc).isoformat()}, fh, indent=2)


def main() -> int:
    _say("checking at %s UTC" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))

    # F: FIRST. There is no point asking the database whether a run finished if the archive
    # cannot be written either way, and an unplugged drive is the likeliest of the three.
    if not os.path.isdir("F:\\"):
        _say("F_NOT_MOUNTED: F: is not present. MANDARAX is a backup drive; plug it in.")
        return EXIT_F_NOT_MOUNTED
    if not os.path.isdir(F_ROOT):
        _say("F_NOT_MOUNTED: F: is mounted but %s is absent -- refusing to create the "
             "archive root on what may be the wrong drive." % F_ROOT)
        return EXIT_F_NOT_MOUNTED

    try:
        active, latest_ended = asyncio.run(_active_run())
    except Exception as exc:                                        # noqa: BLE001
        _say("GATE_ERROR: could not read the run ledger (%s: %s). NOT treating this as "
             "'nothing is running'." % (type(exc).__name__, exc))
        return EXIT_GATE_ERROR

    if active:
        _say("RUN_IN_PROGRESS: run %s started %s has no ended_at. Not exporting a partial "
             "night; the scheduler will retry." % (active["id"], active["started_at"]))
        return EXIT_RUN_IN_PROGRESS

    if latest_ended is None:
        _say("GATE_ERROR: no completed backfill run exists at all. Refusing to export "
             "against a ledger with nothing in it.")
        return EXIT_GATE_ERROR

    if _last_exported_run() == latest_ended:
        _say("ALREADY_DONE: the archive is already current for run %s." % latest_ended)
        return EXIT_OK

    _say("run %s has ended and is not yet exported -- exporting." % latest_ended)
    proc = subprocess.run([sys.executable, "-B", os.path.join(HERE, "f_export.py")],
                          cwd=REPO)
    # f_export returns 0 only when DB-complete and F: AGREE on every in-window date.
    _record(latest_ended, proc.returncode)
    if proc.returncode == 0:
        _say("EXPORTED: run %s, and the match report agrees." % latest_ended)
        return EXIT_OK
    _say("EXPORTED run %s but the match report did NOT agree (exit %d) -- see the log."
         % (latest_ended, proc.returncode))
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
