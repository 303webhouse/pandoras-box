"""Is it safe to deploy right now? — R-IV.997(c). Run before any push in 18:00-05:00 MT.

A deploy restarts the Railway process, which cancels the backfill task mid-walk. That is not
hypothetical: run 7 was killed that way, and because `CancelledError` derives from
BaseException none of the job's handlers recorded it, so the row still reads as in progress.

WHAT THIS DOES NOT DO: decide for you. It reports, with a non-zero exit when a run is active,
so a deploy during the window is a deliberate act rather than an accident.

    0  CLEAR            no active run, or outside the window entirely
    2  RUN_ACTIVE       a backfill run has no ended_at -- wait for it
    4  GUARD_ERROR      could not check; NOT treated as clear
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

MT = ZoneInfo("America/Denver")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The collection window, in MT. The job fires 20:30 ET (= 18:30 MT) and retries to 23:00 ET;
#: the guard opens a little earlier and closes at 05:00 MT, per the ruling.
WINDOW_OPEN, WINDOW_CLOSE = time(18, 0), time(5, 0)

EXIT_CLEAR, EXIT_RUN_ACTIVE, EXIT_GUARD_ERROR = 0, 2, 4


def _pg_dsn() -> str:
    """The write URL from the gitignored .mcp.json. NEVER printed."""
    raw = open(os.path.join(REPO, ".mcp.json"), encoding="utf-8").read()
    for m in re.finditer(r"postgres(?:ql)?://[^\"\s]+", raw):
        if "railway.internal" not in m.group(0):
            return m.group(0)
    raise RuntimeError("no usable postgres URL in .mcp.json")


async def _active():
    import asyncpg
    conn = await asyncpg.connect(_pg_dsn())
    try:
        # A null `ended_at` means "active" ONLY if no LATER run has already finished.
        # Without that clause this guard deadlocks: run 7's stale null would block the very
        # deploy that ships the reconciliation which clears it.
        return await conn.fetchrow(
            "SELECT r.id, r.started_at, r.uw_day, r.calls_spent, "
            "       EXISTS (SELECT 1 FROM darkpool_backfill_runs l "
            "                WHERE l.id > r.id AND l.ended_at IS NOT NULL) AS orphaned "
            "  FROM darkpool_backfill_runs r "
            " WHERE r.ended_at IS NULL ORDER BY r.id DESC LIMIT 1")
    finally:
        await conn.close()


def main() -> int:
    now_utc = datetime.now(timezone.utc)
    now_mt = now_utc.astimezone(MT)
    # The window wraps midnight, so it is a union of two ranges, not a single comparison.
    in_window = now_mt.time() >= WINDOW_OPEN or now_mt.time() < WINDOW_CLOSE
    print("[deploy-guard] %s UTC / %s MT -- %s the 18:00-05:00 MT window"
          % (now_utc.strftime("%H:%M:%S"), now_mt.strftime("%H:%M:%S"),
             "INSIDE" if in_window else "outside"))

    try:
        row = asyncio.run(_active())
    except Exception as exc:                                        # noqa: BLE001
        print("[deploy-guard] GUARD_ERROR: could not read the run ledger (%s: %s). NOT "
              "treating this as clear." % (type(exc).__name__, exc))
        return EXIT_GUARD_ERROR

    if row is None:
        print("[deploy-guard] CLEAR: no backfill run is active.")
        return EXIT_CLEAR

    age = (now_utc - row["started_at"]).total_seconds() / 60.0
    if row["orphaned"]:
        print("[deploy-guard] CLEAR: run %s has no ended_at, but a LATER run has already "
              "finished, so run %s's process is provably gone. Startup reconciliation will "
              "record it as KILLED_BY_DEPLOY." % (row["id"], row["id"]))
        return EXIT_CLEAR
    print("[deploy-guard] RUN_ACTIVE: run %s started %s (%.0f min ago), uw_day %s, "
          "calls_spent %s" % (row["id"], row["started_at"], age, row["uw_day"],
                              row["calls_spent"]))
    if not in_window:
        print("[deploy-guard]   ...and it is OUTSIDE the window, so this row is very likely a "
              "run whose process is already gone. Startup reconciliation closes those as "
              "KILLED_BY_DEPLOY; deploying will trigger it.")
    print("[deploy-guard] Wait for it, or deploy deliberately knowing the walk will be cut.")
    return EXIT_RUN_ACTIVE


if __name__ == "__main__":
    sys.exit(main())
