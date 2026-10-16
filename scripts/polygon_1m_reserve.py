"""R-IV.1126(a) / R-IV.1064(a) — Polygon 1-minute bars for the SEALED TRITON-R reserve window.

WHAT THIS UNBLOCKS, stated because it is the reason the window matters. QUERY's own
pre-registered gate (R-IV.1070(d), SPINE-adopted) says: *no reserve read happens until BUILD's
R-IV.1064 Polygon pull for the reserve is done and its row counts are checked, counts only; a
yfinance reserve is NOT an option for the holdout.* Until this file exists, QUERY's count run
does not refuse -- **it silently substitutes**. Its command takes `"<polygon>;<polygon_reserve>"`,
the Polygon glob covers none of 09-25 onward, and `bars1m/` (yfinance) has every one of those
sessions. So the run would proceed, on the wrong vendor, for every reserve session, and the
first entry in a non-cumulative weekly series would be unfixable afterwards.

A SEPARATE DIRECTORY, NOT AN EXTENSION OF THE CALIBRATION PULL. `bars1m_polygon` holds
2026-08-28 .. 09-24 and stops deliberately the day before `RESERVE_FIRST_DATE`. Widening it
would merge calibration data with holdout data in one glob, and the whole point of the seal is
that the two are addressable separately. QUERY needs a second glob; this is it.

REUSES `polygon_1m_export`'s fetch rather than re-implementing it. That function's retry
behaviour was MEASURED against Polygon Starter's 5-req/min limit -- the first run of it fired
16 calls flat out and took eleven 429s. Re-writing that logic to avoid importing it would be
how a proven instrument gets replaced by a plausible one. `fetch` reads the window from module
globals, so they are reassigned here, explicitly, before any call.

BOTH ADJUSTMENT MODES, for the reason R-IV.1001(b) gave: the unadjusted series is the one a
print-price comparison needs, and the adjusted series is pulled beside it purely to PROVE no
corporate action fell in the window. If any bar differs, the two are not interchangeable and
this stops.

REPORTS COUNTS, SESSIONS AND HASHES ONLY. No price, no return, no outcome field, per
R-IV.1126(c). The bar-for-bar comparison prints only tallies.

Run under `railway run`: POLYGON_API_KEY lives on Railway. It is read from the injected
environment, never printed, never interpolated into output.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import polygon_1m_export as pe        # noqa: E402  the proven fetch/write/compare

ROOT = r"F:\pandora-data"

#: R-IV.1133(b): ONE DATED DIRECTORY PER WINDOW, with UNDATED basenames inside it.
#: The frozen loader tests for the exact basename suffix `_adjusted_<mode>.parquet`
#: (census :333, instrument :199/:202), so a dated FILENAME is refused outright. The window
#: therefore lives in the directory name -- and the rule that no name may overstate its
#: content now applies to the directory, which is why the name is derived from the data's
#: own span below and every later file must agree with it.
OUT_BASE = os.path.join(ROOT, "bars1m_polygon_reserve")

#: Resolved from the first file's real span, then held fixed. Not a constant, because the
#: span is not known until the vendor answers.
_out_dir = {"path": None, "span": None}


def out_dir_for(first: str, last: str) -> str:
    """The dated directory for this window. Refuses a span that disagrees with the first.

    A second span would mean one directory holding two windows, and its name could only be
    true of one of them.
    """
    span = (first, last)
    if _out_dir["path"] is None:
        _out_dir["span"] = span
        _out_dir["path"] = "%s_%s_%s" % (OUT_BASE, first.replace("-", ""),
                                         last.replace("-", ""))
        os.makedirs(_out_dir["path"], exist_ok=True)
    elif _out_dir["span"] != span:
        raise RuntimeError(
            "span %s disagrees with this directory's %s; one directory cannot name two windows"
            % (span, _out_dir["span"]))
    return _out_dir["path"]

CENSUS = list(pe.CENSUS)

#: The sealed TRITON-R reserve window. Start is `iv_term_backfill.RESERVE_FIRST_DATE`, the
#: first date no other lane may touch. End is the latest COMPLETED session, passed in rather
#: than assumed -- "today" is only a completed session after the close, and a half-delivered
#: final session in a holdout would bias every count run on it without showing up as an error.
RESERVE_FIRST = date(2026, 9, 25)


def expected_sessions(first: date, last: date) -> list:
    """Weekday dates in the window. A holiday will show up as a name-wide absence below,
    which is reported rather than silently accepted -- this function deliberately does NOT
    know the exchange calendar, so it cannot quietly excuse a missing session."""
    out, d = [], first
    while d <= last:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: polygon_1m_reserve.py <last_completed_session YYYY-MM-DD>")
        return 2
    last_session = sys.argv[1]
    try:
        last_d = date.fromisoformat(last_session)
    except ValueError:
        print("bad date: %r" % last_session)
        return 2

    if not os.path.isdir("F:\\"):
        print("F: is not mounted; nothing written")
        return 3

    key = pe._key()                       # prints "present", never the value
    pe.DATE_FROM, pe.DATE_TO = RESERVE_FIRST.isoformat(), last_session

    tag = "%s_%s" % (RESERVE_FIRST.strftime("%Y%m%d"), last_d.strftime("%Y%m%d"))
    exp = expected_sessions(RESERVE_FIRST, last_d)

    print("=" * 100)
    print("R-IV.1126(a) SEALED RESERVE PULL -- Polygon 1-minute")
    print("window %s .. %s inclusive | %d names | BOTH modes | %d calls | out: %s"
          % (pe.DATE_FROM, pe.DATE_TO, len(CENSUS), 2 * len(CENSUS),
             OUT_BASE + "_<window, from the data>"))
    print("weekday sessions expected in window: %d" % len(exp))
    print("=" * 100)
    print()

    results, findings, incomplete = [], [], []
    per_name = {}

    for ticker in CENSUS:
        series = {}
        for adjusted in (False, True):
            if pe.CALLS["n"]:
                time.sleep(pe.RATE_LIMIT_SLEEP_S)        # 5 req/min on Starter
            st, bars = pe.fetch(ticker, adjusted, key)
            df = pe.to_frame(bars, ticker, adjusted)
            series[adjusted] = df
            if df.empty:
                print("  %-5s adjusted=%-5s HTTP %-3s  NO BARS -- not written"
                      % (ticker, adjusted, st))
                incomplete.append((ticker, "adjusted=%s: HTTP %s, no bars" % (adjusted, st)))
                continue
            # THE DATED NAME COMES FROM THE DATA, NEVER FROM THE REQUESTED WINDOW.
            # The first run of this named files `..._20261015` because that is what was
            # ASKED for, while Polygon's plan withheld 2026-10-15 (403) and the files
            # actually ended 10-14. A dated name that overstates its content is worse than
            # no date at all, and this directory is read by filename glob -- so the name is
            # built from the file's own first and last session.
            # THE DIRECTORY'S DATES COME FROM THE DATA, THE BASENAME CARRIES NONE.
            # An earlier version put the window in the filename from the REQUESTED range and
            # shipped files named `..._20261015` holding data to 10-14. Now the span is read
            # from the file itself, and the loader gets the undated basename it requires.
            own = sorted(df["session_et"].unique())
            own_tag = "%s_%s" % (own[0].replace("-", ""), own[-1].replace("-", ""))
            if own_tag != tag:
                print("        directory from DATA not request: %s (requested %s)"
                      % (own_tag, tag))
            try:
                target_dir = out_dir_for(own[0], own[-1])
            except RuntimeError as exc:
                problems.append((ticker, str(exc)))
                print("  %-5s adjusted=%-5s %s" % (ticker, adjusted, exc))
                continue
            name = "%s_adjusted_%s.parquet" % (ticker, "true" if adjusted else "false")
            path = os.path.join(target_dir, name)
            r = pe.write(df, path)
            r["ticker"], r["adjusted"] = ticker, adjusted
            sess = sorted(df["session_et"].unique())
            r["sessions"], r["first"], r["last"] = len(sess), sess[0], sess[-1]
            # The last bar's ET clock. A final session that stops at 11:00 is TRUNCATED, and
            # in a sealed holdout that would bias a count run while looking like data.
            r["last_bar_et"] = str(df["timestamp_et"].max())[:19]
            r["missing"] = [s for s in exp if s not in set(sess)]
            results.append(r)
            per_name.setdefault(ticker, []).append(r)
            print("  %-5s adjusted=%-5s HTTP %-3s  %6d bars  %2d sessions  %s .. %s  "
                  "last bar %s  %s%s"
                  % (ticker, adjusted, st, r["rows"], r["sessions"], r["first"], r["last"],
                     r["last_bar_et"][11:], r["sha256"][:16],
                     "" if r["ok"] else "  READ-BACK MISMATCH"))
        n, ndiff, detail = pe.compare(series.get(False, pd.DataFrame()),
                                      series.get(True, pd.DataFrame()), ticker)
        print("        compare: %s" % detail)
        if ndiff > 0:
            findings.append((ticker, detail))
        elif ndiff < 0:
            incomplete.append((ticker, detail))

    print()
    print("CALLS: %d   HTTP: %s   retries: %d"
          % (pe.CALLS["n"], pe.CALLS["http"], pe.CALLS["retries"]))
    print()

    # ---- QUERY's four gate items, in QUERY's own order (R-IV.1126(c)) ----
    print("=" * 100)
    print("GATE REPORT -- the four things QUERY's pre-registered check reads")
    print("=" * 100)
    print()
    print("%-6s %-9s %8s %9s %-12s %-12s %s"
          % ("name", "mode", "rows", "sessions", "first ET", "last ET", "sha256"))
    for r in results:
        print("%-6s %-9s %8d %9d %-12s %-12s %s"
              % (r["ticker"], "adj" if r["adjusted"] else "unadj", r["rows"],
                 r["sessions"], r["first"], r["last"], r["sha256"]))

    print()
    print("SESSION COVERAGE vs the %d expected weekday sessions:" % len(exp))
    all_missing = {}
    for t, rs in per_name.items():
        miss = sorted({m for r in rs for m in r["missing"]})
        if miss:
            all_missing[t] = miss
            print("   %-6s MISSING %d: %s" % (t, len(miss), ", ".join(miss)))
    if not all_missing:
        print("   all %d names cover all %d expected sessions." % (len(per_name), len(exp)))
    else:
        common = set.intersection(*[set(v) for v in all_missing.values()]) \
            if len(all_missing) == len(per_name) else set()
        if common:
            print("   NOTE: %s missing for EVERY name -- consistent with an exchange holiday "
                  "or half-day, not a pull fault. Not excused here; reported." % sorted(common))

    print()
    print("FINAL-SESSION COMPLETENESS (last bar's ET clock per name):")
    for t, rs in per_name.items():
        print("   %-6s %s" % (t, " | ".join(r["last_bar_et"] for r in rs)))
    print("   A full session's last 1-minute bar is 19:59 ET with extended hours, 15:59 RTH.")
    print("   Anything materially earlier means the session was still filling when pulled.")

    print()
    if findings:
        print(">>> STOP: adjusted and unadjusted DIFFER on at least one bar.")
        for t, d in findings:
            print("      %-5s %s" % (t, d))
        return 4
    if incomplete:
        print(">>> INCOMPLETE: some bars were never fetched, so nothing is concluded about")
        print("    whether the series agree. Re-run; Polygon Starter allows 5 req/min.")
        for t, d in incomplete:
            print("      %-5s %s" % (t, d))
        return 5

    note = "no corporate action in window"
    print(">>> ADJUSTED AND UNADJUSTED IDENTICAL ON EVERY BAR, ALL %d NAMES." % len(CENSUS))
    readme = os.path.join(os.path.dirname(_out_dir["path"] or OUT_BASE),
                          "bars1m_polygon_reserve", "README.md")
    with open(readme, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            "# Polygon 1-minute bars - SEALED TRITON-R RESERVE WINDOW\n\n"
            "Pulled %s UTC under R-IV.1126(a) (the R-IV.1064(a) pull).\n"
            "Source: Polygon `/v2/aggs/ticker/{t}/range/1/minute`, Starter plan, no upgrade.\n\n"
            "Window REQUESTED: %s .. %s. **Window DELIVERED: %s .. %s.** Names: %s.\n\n"
            "## THIS IS THE HOLDOUT. DO NOT ANALYSE BEFORE STEP 8.\n\n"
            "These sessions are the sealed TRITON-R reserve. QUERY's pre-registered gate\n"
            "(R-IV.1070(d)) reads this directory as the `<polygon_reserve>` glob; a yfinance\n"
            "reserve is NOT an option for the holdout, and `bars1m/` must not be substituted.\n\n"
            "Kept SEPARATE from `bars1m_polygon/` (2026-08-28 .. 09-24, calibration) on\n"
            "purpose: one glob per set, so the seal stays addressable.\n\n"
            "## %s\n\n"
            "Both `adjusted=false` and `adjusted=true` were pulled for every name and compared\n"
            "BAR FOR BAR on a UTC-timestamp join across open/high/low/close/vwap. Identical on\n"
            "every bar, so **%s**. A print-price comparison should still read `adjusted_false`.\n\n"
            "## Clocks (convention #39)\n\n"
            "`timestamp_utc` is authoritative; `timestamp_et`/`session_et` are the same instant\n"
            "in America/New_York. Bars span 04:00-19:59 ET.\n"
            % (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
               pe.DATE_FROM, pe.DATE_TO,
               min(r["first"] for r in results), max(r["last"] for r in results),
               ", ".join(CENSUS), note.upper(), note))
    print("    README: %s" % readme)

    # a standalone hash list, so the gate can be re-checked without re-reading the parquets
    hashes = os.path.join(_out_dir["path"], "SHA256SUMS.txt")
    with open(hashes, "w", encoding="utf-8", newline="\n") as fh:
        for r in sorted(results, key=lambda x: x["path"]):
            fh.write("%s  %s\n" % (r["sha256"], os.path.basename(r["path"])))
    print("    SHA256SUMS: %s" % hashes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
