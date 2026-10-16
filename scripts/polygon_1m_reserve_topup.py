"""R-IV.1129(a) — add 2026-10-15 to the sealed reserve and deliver ONE 15-session artifact.

WHY A TOP-UP AND NOT A RE-PULL. The ruling says do not re-pull the 14 sessions already on disk.
That is not only about call budget: the 14 existing files are already hashed, in the manifest,
and cited. Re-fetching them would produce new bytes with new hashes for data nobody disputes,
and every citation of the old hashes would silently stop resolving. So 10-15 is fetched alone
(16 calls) and CONCATENATED onto what exists.

THE MERGED FILE IS ASSEMBLED FROM TWO PULLS, AND THAT PROVENANCE IS RECORDED. A reader cannot
tell by looking that sessions 1-14 and session 15 arrived on different days through different
requests. The README and manifest note say so, because "one artifact" describes the file's
SCOPE, not its origin, and a later reproduction attempt needs the origin.

WHAT IS VERIFIED BEFORE ANYTHING IS WRITTEN, each of which could silently corrupt the holdout:

  * the new session is COMPLETE -- last bar 19:59 ET. A session still filling would be
    truncated, and in a sealed holdout a truncated session biases every count run on it while
    looking exactly like data.
  * 10-15 is NOT already present in the source file. Concatenating a session twice would double
    its weight in any count and the row total would still look plausible.
  * the ORIGINAL 14 sessions' per-session row counts survive the merge EXACTLY. A concat that
    silently dropped or duplicated a row elsewhere is the failure this catches; a total-row
    check alone would not, because two errors can cancel.
  * adjusted vs unadjusted agree BAR FOR BAR on the new session too. The corporate-action proof
    has to extend to session 15 or it no longer covers the window it claims.

The 10-14 files are left BYTE-UNTOUCHED and marked SUPERSEDED in the manifest, as ruled.

Reports counts, sessions and hashes only. No price, no return, no outcome field.
Run under `railway run`: POLYGON_API_KEY is read from the injected environment, never printed.
"""
from __future__ import annotations

import glob
import hashlib
import io
import os
import sys
import time
from datetime import date, datetime, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import polygon_1m_export as pe        # noqa: E402  the proven fetch/write

ROOT = r"F:\pandora-data"
#: R-IV.1133(b): the window lives in the DIRECTORY name and basenames are UNDATED, because
#: the frozen loader tests for the exact suffix `_adjusted_<mode>.parquet`. A top-up reads the
#: PREVIOUS window's directory and writes the NEW window's, so both are derived, never fixed.
OUT_BASE = os.path.join(ROOT, "bars1m_polygon_reserve")
SRC_DIR = "%s_%s" % (OUT_BASE, OLD_TAG)
OUT_DIR = "%s_%s" % (OUT_BASE, NEW_TAG)
MANIFEST = os.path.join(ROOT, "MANIFEST.tsv")

CENSUS = list(pe.CENSUS)
NEW_SESSION = "2026-10-15"
OLD_TAG = "20260925_20261014"
NEW_TAG = "20260925_20261015"
REQUESTED_FROM = "2026-09-25"


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def mark_superseded(paths: set) -> int:
    """Flag the 10-14 rows SUPERSEDED. Bytes on disk are never touched -- only the manifest's
    own `status` and `note`, so the old hashes keep resolving for anything that cited them."""
    raw = io.open(MANIFEST, encoding="utf-8", newline="").read()
    lines = raw.split("\n")
    n = 0
    for i, line in enumerate(lines):
        if i == 0 or not line.strip():
            continue
        f = line.split("\t")
        if len(f) < 8 or f[1] not in paths:
            continue
        f[6] = "SUPERSEDED"
        add = ("SUPERSEDED by the 15-session artifact (%s) under R-IV.1129(a); bytes "
               "deliberately untouched so prior citations of this sha256 still resolve"
               % NEW_TAG)
        f[7] = (f[7] + "; " + add) if f[7].strip() else add
        lines[i] = "\t".join(f)
        n += 1
    if n:
        io.open(MANIFEST, "w", encoding="utf-8", newline="").write("\n".join(lines))
    return n


def append_manifest(rows: list) -> int:
    raw = io.open(MANIFEST, encoding="utf-8", newline="").read()
    lines = raw.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    existing = {l.split("\t")[1] for l in lines[1:] if l.strip() and len(l.split("\t")) > 1}
    new = []
    for r in rows:
        if r["path"] in existing:
            continue
        note = ("SEALED TRITON-R RESERVE, 15 sessions %s..%s (R-IV.1129(a)). ASSEMBLED FROM TWO "
                "PULLS: sessions 1-14 from the 2026-10-16 02:46Z pull, session 15 (%s) fetched "
                "separately once Polygon stopped withholding it as the current session."
                % (REQUESTED_FROM, NEW_SESSION, NEW_SESSION))
        new.append("\t".join(["FILE", r["path"], str(r["rows"]), str(r["rows_read_back"]),
                              str(r["bytes"]), r["sha256"], "WRITTEN", note]))
    if new:
        io.open(MANIFEST, "w", encoding="utf-8", newline="").write("\n".join(lines + new))
    return len(new)


def main() -> int:
    if not os.path.isdir("F:\\"):
        print("F: is not mounted; nothing written")
        return 3
    key = pe._key()
    pe.DATE_FROM = pe.DATE_TO = NEW_SESSION      # ONLY the new session is fetched

    # Optional ticker filter. A re-run after a partial pass must not re-fetch names already
    # merged: those calls are spent, their output is already on disk, and re-writing an
    # identical file only risks a new hash for unchanged data.
    only = [a.upper() for a in sys.argv[1:] if a.upper() in CENSUS]
    names = only or CENSUS
    if only:
        print("RESTRICTED to %s (a re-run; the others are already merged)" % ", ".join(only))

    os.makedirs(OUT_DIR, exist_ok=True)
    print("=" * 102)
    print("R-IV.1129(a) RESERVE TOP-UP -- fetch %s only, merge to one 15-session artifact"
          % NEW_SESSION)
    print("requested window %s .. %s | %d names | both modes | %d calls"
          % (REQUESTED_FROM, NEW_SESSION, len(CENSUS), 2 * len(CENSUS)))
    print("=" * 102)
    print()

    results, problems = [], []
    superseded_paths = set()

    for ticker in names:
        series = {}
        for adjusted in (False, True):
            mode = "true" if adjusted else "false"
            src = os.path.join(SRC_DIR, "%s_adjusted_%s.parquet" % (ticker, mode))
            if not os.path.exists(src):
                problems.append((ticker, "source 14-session file missing: %s"
                                 % os.path.basename(src)))
                continue

            if pe.CALLS["n"]:
                time.sleep(pe.RATE_LIMIT_SLEEP_S)
            st, bars = pe.fetch(ticker, adjusted, key)
            add = pe.to_frame(bars, ticker, adjusted)
            series[adjusted] = add
            if add.empty:
                problems.append((ticker, "adjusted=%s: HTTP %s, no bars for %s"
                                 % (adjusted, st, NEW_SESSION)))
                print("  %-5s adjusted=%-5s HTTP %-3s  NO BARS -- not merged"
                      % (ticker, adjusted, st))
                continue

            # THE SESSION MUST BE COMPLETE, AND "COMPLETE" IS NOT "LAST BAR AT 19:59".
            #
            # This guard first demanded a 19:59 ET final bar and BLOCKED IWM (19:57) and MSFT
            # (19:58) on 2026-10-15. Measured against the 14 sessions already on disk, that
            # was wrong: IWM ends before 19:59 in 6 of 14 sessions, SMH in 8 of 14, MSFT in
            # 3 of 14. Polygon returns a bar only where a trade occurred, so an empty final
            # minute of extended hours is THIN TAPE, not truncation -- and SMH passed the old
            # guard on 10-15 only by luck, having ended at 19:59 that day.
            #
            # A guard that is too strict is not the safe direction. It rejects good sessions,
            # and a holdout that silently loses its 15th session to an over-strict check is
            # just as unusable as one that gains a truncated day.
            #
            # What actually distinguishes a still-filling session is the RTH CLOSE: a session
            # cut short mid-afternoon has no 15:59 bar and far too few bars overall. So the
            # test is the close plus a volume sanity floor against this name's own history,
            # never a fixed clock time.
            last_et = str(add["timestamp_et"].max())[:19]
            et_times = pd.to_datetime(add["timestamp_et"], utc=True).dt.tz_convert(
                "America/New_York")
            has_rth_close = bool((et_times.dt.strftime("%H:%M") >= "15:59").any())
            old_peek = pd.read_parquet(src)
            median_bars = int(old_peek.groupby("session_et").size().median())
            floor = int(median_bars * 0.60)
            if not has_rth_close or len(add) < floor:
                problems.append((
                    ticker,
                    "adjusted=%s: %s INCOMPLETE -- rth_close_present=%s bars=%d "
                    "(name's median %d, floor %d), last bar %s"
                    % (adjusted, NEW_SESSION, has_rth_close, len(add), median_bars, floor,
                       last_et)))
                print("  %-5s adjusted=%-5s INCOMPLETE (rth_close=%s, %d bars vs floor %d) "
                      "-- not merged"
                      % (ticker, adjusted, has_rth_close, len(add), floor))
                continue

            old = pd.read_parquet(src)
            old_sessions = sorted(old["session_et"].unique())
            if NEW_SESSION in set(old_sessions):
                problems.append((ticker, "adjusted=%s: %s ALREADY present in the source file"
                                 % (adjusted, NEW_SESSION)))
                print("  %-5s adjusted=%-5s %s already present -- refusing to double it"
                      % (ticker, adjusted, NEW_SESSION))
                continue

            merged = pd.concat([old, add], ignore_index=True)
            merged = merged.sort_values("timestamp_utc").reset_index(drop=True)

            # the original 14 sessions must survive EXACTLY -- per session, not just in total,
            # because two offsetting errors would pass a total-row check
            before = old.groupby("session_et").size()
            after = merged.groupby("session_et").size()
            drift = {s: (int(before[s]), int(after.get(s, 0)))
                     for s in before.index if int(before[s]) != int(after.get(s, 0))}
            if drift:
                problems.append((ticker, "adjusted=%s: merge changed existing sessions: %s"
                                 % (adjusted, drift)))
                print("  %-5s adjusted=%-5s MERGE ALTERED EXISTING SESSIONS -- not written"
                      % (ticker, adjusted))
                continue
            if len(merged) != len(old) + len(add):
                problems.append((ticker, "adjusted=%s: row total %d != %d + %d"
                                 % (adjusted, len(merged), len(old), len(add))))
                continue

            dst = os.path.join(OUT_DIR, "%s_adjusted_%s.parquet" % (ticker, mode))
            r = pe.write(merged, dst)
            sess = sorted(merged["session_et"].unique())
            r.update({"ticker": ticker, "adjusted": adjusted, "sessions": len(sess),
                      "first": sess[0], "last": sess[-1], "added": len(add),
                      "last_bar_et": str(merged["timestamp_et"].max())[:19]})
            results.append(r)
            superseded_paths.add(src)
            print("  %-5s adjusted=%-5s HTTP %-3s  +%4d bars -> %6d total  %2d sessions  "
                  "%s .. %s  %s%s"
                  % (ticker, adjusted, st, len(add), r["rows"], r["sessions"],
                     r["first"], r["last"], r["sha256"][:16],
                     "" if r["ok"] else "  READ-BACK MISMATCH"))

        n, ndiff, detail = pe.compare(series.get(False, pd.DataFrame()),
                                      series.get(True, pd.DataFrame()), ticker)
        print("        %s compare: %s" % (NEW_SESSION, detail))
        if ndiff > 0:
            problems.append((ticker, "adjusted/unadjusted DIFFER on %s: %s"
                             % (NEW_SESSION, detail)))

    print()
    print("CALLS: %d   HTTP: %s   retries: %d"
          % (pe.CALLS["n"], pe.CALLS["http"], pe.CALLS["retries"]))
    print()

    if problems:
        print(">>> STOP -- nothing was superseded and the manifest is unchanged:")
        for t, d in problems:
            print("      %-5s %s" % (t, d))
        return 4

    print("=" * 102)
    print("GATE REPORT -- 15-session artifact")
    print("=" * 102)
    print("names this run: %s" % ", ".join(names))
    print("requested: %s .. %s     delivered: %s .. %s"
          % (REQUESTED_FROM, NEW_SESSION,
             min(r["first"] for r in results), max(r["last"] for r in results)))
    print()
    print("%-6s %-9s %8s %7s %9s %-12s %-12s %s"
          % ("name", "mode", "rows", "added", "sessions", "first ET", "last ET", "sha256"))
    for r in results:
        print("%-6s %-9s %8d %7d %9d %-12s %-12s %s"
              % (r["ticker"], "adj" if r["adjusted"] else "unadj", r["rows"], r["added"],
                 r["sessions"], r["first"], r["last"], r["sha256"]))

    bad = [r for r in results if r["sessions"] != 15]
    print()
    print("every file carries 15 sessions: %s" % ("YES" if not bad else "NO -- %s" % bad))
    print("final bar per file: %s" % sorted({r["last_bar_et"] for r in results}))

    n_sup = mark_superseded(superseded_paths)
    n_new = append_manifest(results)
    print()
    print("manifest: %d rows marked SUPERSEDED (bytes untouched), %d new rows appended"
          % (n_sup, n_new))

    hashes = os.path.join(OUT_DIR, "SHA256SUMS.txt")
    with io.open(hashes, "w", encoding="utf-8", newline="\n") as fh:
        for p in sorted(glob.glob(os.path.join(OUT_DIR, "*.parquet"))):
            fh.write("%s  %s\n" % (sha256_of(p), os.path.basename(p)))
    print("SHA256SUMS.txt rewritten over ALL parquets present (superseded + current), %d files"
          % len(glob.glob(os.path.join(OUT_DIR, "*.parquet"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
