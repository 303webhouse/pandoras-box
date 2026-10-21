"""The evening regime-bars repair, for while Railway's builds are paused. R-IV.1284(b).

WHY THIS EXISTS. The nightly job asks Polygon for the session that has just closed, and on this
plan that session is WITHHELD while it is still current -- measured on two consecutive nights
(2026-10-19 01:31:09Z and 2026-10-20 01:33:33Z, "SPY: HTTP 403; QQQ: 403; IWM: 403"). The code
fix is written and cannot deploy, so until builds resume this script does by hand what the fixed
nightly will do by itself: fetch what the source WILL serve, store any missing bar, and label any
settled session that has a bar and no label.

A SCRIPT RATHER THAN A HAND-TYPED COMMAND, because R-IV.1284(b) says "Log each run". A command
retyped each evening is a command that drifts on the evening someone is tired, and its record is
whatever the terminal happened to keep. This appends one line per run to the log below and is
idempotent: a session that already has a bar and a label produces "nothing to do".

IT USES THE APP'S OWN CODE. `bars_polygon.fetch_daily` / `.store` and the job's own
`replay` + `_write_snapshot` -- not hand-rolled SQL and not a hand-computed label. A label
computed by any other route would be a second classifier wearing v2's name, and a bar written by
a second INSERT would be a second author of that table.

NOTHING IS INVENTED. If Polygon has not released a session, the script says so and writes
nothing for it: the one-session lag is this plan's entitlement edge, not a fault to work around.

Usage, from the repo root, after the close:

    POLYGON_API_KEY=... REGIME_DB_URL=... .venv-test/Scripts/python -B scripts/regime_bars_repair.py

Both are read from the environment and NEITHER IS EVER PRINTED. `--dry-run` reports what it
would do and writes nothing.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import io
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(os.path.dirname(_HERE), "backend")
sys.path.insert(0, _BACKEND)

#: One line per run, newest LAST. Under `C:\lane-state` because it is operational record rather
#: than repository history, and because the lane files already live there.
LOG_PATH = r"C:\lane-state\regime-bars-repair.log"

#: How far back the range request starts. A week covers a holiday weekend; only the sessions
#: that are actually missing are ever written.
LOOKBACK_DAYS = 10


def _db_url() -> str:
    """The write URL, from the environment or from `.mcp.json`. Never printed, never logged."""
    url = (os.environ.get("REGIME_DB_URL") or os.environ.get("DATABASE_URL") or "").strip()
    if url:
        return url.replace("postgresql+asyncpg://", "postgresql://")
    cfg = os.path.join(os.path.dirname(_HERE), ".mcp.json")
    found = []

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str) and o.startswith("postgres"):
            found.append(o)

    with io.open(cfg, encoding="utf-8") as fh:
        walk(json.load(fh))
    if not found:
        raise SystemExit("no postgres URL in the environment or in .mcp.json")
    return found[0].replace("postgresql+asyncpg://", "postgresql://")


def _log(line: str) -> None:
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with io.open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write("%s  %s\n" % (stamp, line))
    except Exception as exc:                                        # noqa: BLE001
        print("log write failed (%s); the run itself is unaffected" % type(exc).__name__)


async def run(dry: bool = False) -> int:
    import asyncpg

    from jobs.regime_job import (CLOSE_SOURCE, INDICES, bar_freshness, build_sessions,
                                 load_designated_series, load_rules)
    from jobs.regime_seed import _write_snapshot, replay
    from stable_engine import bars_polygon as bp
    from stable_engine.market_calendar import last_settled_session

    rules = load_rules()
    version = rules.get("version")
    conn = await asyncpg.connect(_db_url())
    notes = []
    try:
        settled = last_settled_session()
        row = await conn.fetchrow(
            "SELECT MAX(date) AS newest FROM regime_daily_bars "
            " WHERE ticker = 'SPY' AND close_source = $1", CLOSE_SOURCE)
        have = row["newest"] if row else None
        print("last settled session: %s | newest stored SPY bar: %s"
              % (settled.isoformat(), have.isoformat() if have else "none"))

        # ── 1. the bars the source will actually serve ────────────────────────
        start = (have or settled) - _dt.timedelta(days=LOOKBACK_DAYS)
        written = 0
        served_through = None
        for i, t in enumerate(INDICES):
            if i:
                await asyncio.sleep(bp.CALL_GAP_S)
            try:
                bars = await bp.fetch_daily(t, start, settled)
            except Exception as exc:                                # noqa: BLE001
                notes.append("%s fetch failed: %s" % (t, type(exc).__name__))
                continue
            if not bars:
                notes.append("%s: the range returned no bar at all" % t)
                continue
            if t == "SPY":
                served_through = bars[-1]["date"]
            missing = [b for b in bars if have is None or b["date"] > have]
            if not missing:
                continue
            print("  %-4s %d new bar(s): %s" % (
                t, len(missing), [(b["date"].isoformat(), round(b["c"], 2)) for b in missing]))
            if not dry:
                written += await bp.store(conn, t, missing, verified=False)

        if served_through is not None and served_through < settled:
            # THE EXPECTED STATE, NOT AN ERROR. Say it in the terms the reader needs.
            notes.append("polygon has not released %s yet (newest served: %s) -- this plan "
                         "withholds a session while it is still current"
                         % (settled.isoformat(), served_through.isoformat()))

        # ── 2. label every settled session that has a bar and no label ────────
        labelled = []
        series = await load_designated_series(conn)
        spy = series.get("SPY") or []
        through = spy[-1].date if spy else None
        if through is not None:
            # THE SAME BUILD THE SEED AND THE NIGHTLY USE. My first version of this script
            # called `sessions_from_series` directly, so `v2` defaulted to False and no VIX
            # pair was passed -- and the two labels it wrote for 10-19 and 10-20 are on that
            # basis, which disagrees with the 302 seeded rows. 95 of 304 sessions differ
            # between the two builds. One builder, three callers.
            sessions, build = await build_sessions(conn, series, rules=rules,
                                                   settled_through=str(through))
            notes.append("build v2_inputs=%s vix=%s" % (
                build.get("v2_inputs"),
                (build.get("vix") or {}).get("paired_dates",
                                             (build.get("vix") or {}).get("error", "n/a"))))
            out = replay(sessions, rules)
            shown = {r["as_of"]: r for r in out["shown"]}
            existing = {r["as_of"].isoformat() for r in await conn.fetch(
                "SELECT as_of FROM regime_snapshots "
                " WHERE rules_version = $1 AND superseded = FALSE", version)}
            for d in sorted(shown):
                if d in existing:
                    continue
                r = shown[d]
                print("  label %s -> %s (raw %s)%s"
                      % (d, r.get("shown_regime"), r.get("regime"),
                         "  " + r["change"] if r.get("change") else ""))
                if not dry:
                    await _write_snapshot(conn, r, seeded=False, close_source=CLOSE_SOURCE)
                labelled.append("%s=%s" % (d, r.get("shown_regime")))

        fresh = await bar_freshness(conn)
        summary = ("bars_written=%d labelled=[%s] newest_bar=%s lag=%s stale=%s%s%s"
                   % (written, ",".join(labelled) or "none", fresh.get("newest_bar"),
                      fresh.get("lag_sessions"), fresh.get("stale"),
                      " DRY-RUN" if dry else "",
                      ("  notes: " + " | ".join(notes)) if notes else ""))
        print(summary)
        _log(summary)
        # A repair that leaves the card more than one session stale is a FAILED repair, and the
        # exit status says so -- a green exit on a still-stale card is the silence this whole
        # ruling is about.
        return 1 if fresh.get("stale") else 0
    finally:
        await conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change and write nothing")
    args = ap.parse_args()
    if not (os.environ.get("POLYGON_API_KEY") or "").strip():
        raise SystemExit("POLYGON_API_KEY is missing from the environment")
    return asyncio.run(run(dry=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
