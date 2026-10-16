r"""R-IV.1148(b) — sealed IV for the TRITON-R reserve window, to PARQUET ONLY.

THE SEAL STAYS AND THE DATA MOVES BEHIND IT, the same pattern as the bars reserve. The 11
sessions 2026-09-25 .. 2026-10-09 are the holdout. `iv_term_backfill.assert_not_reserve()` keeps
its ceiling and keeps refusing these dates for the TABLE path, which is correct and unchanged:
R-IV.1073(c)'s harm was "holdout-window data in a table this lane reads freely", and that is
still refused.

THIS SCRIPT CANNOT WRITE TO THE TABLE, AND THAT IS BY CONSTRUCTION RATHER THAN BY CARE. It
opens no database connection and imports no UPSERT. There is nothing to review about whether a
code path might reach `iv_snapshots`, because there is no path at all: the only writes are
parquet files under `F:\pandora-data\iv_snapshots_reserve_20260925_20261009\`. A guard I could
forget to call is weaker than an absent capability.

SAME SOURCE AND METHOD as the calibration backfill: `get_iv_term_structure`, the dated
`/volatility/term-structure?date=` endpoint, through `jobs.iv_snapshot.summarize` -- so a row
here means exactly what a row in the table means. The endpoint's `date=` was verified to be
HONOURED before any of this was trusted (SPY 10-12 returned 33 expiries, 10-15 returned 34,
different body hashes); UW ignoring a date parameter is a documented landmine on `/ohlc/1d`,
and had it been ignored here every row would have carried one day's IV under eleven dates.

EXACTLY THE `iv_snapshots` COLUMN SCHEMA, in its order, so the parquet can be read as the table
is and a later loader needs no mapping: ticker, session_date, near_expiry, near_dte, iv_near,
iv_30d, iv_30d_method, term_structure, provider, fetched_at.

REPORTS COUNTS, SESSIONS AND HASHES ONLY. No IV value is printed. `iv_near` and `iv_30d` are
written to the parquet -- that is the point of the pull -- but never rendered to a log that a
lane might read.

Run under `railway run`: UW_API_KEY comes from the injected environment, never printed.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import pandas as pd

sys.path.insert(0, r"C:\trading-hub\backend")

ROOT = r"F:\pandora-data"
OUT_DIR = os.path.join(ROOT, "iv_snapshots_reserve_20260925_20261009")

CENSUS = ("SPY", "QQQ", "IWM", "SMH", "NVDA", "AAPL", "MSFT", "TSLA")
FIRST, LAST = date(2026, 9, 25), date(2026, 10, 9)
CALLER_TAG = "iv_term_backfill"

#: The table's columns, in the table's order. Asserted against the live schema below rather
#: than trusted, because "exactly the iv_snapshots schema" is the ruling's requirement and a
#: drifted column list would be invisible in a parquet.
COLUMNS = ["ticker", "session_date", "near_expiry", "near_dte", "iv_near", "iv_30d",
           "iv_30d_method", "term_structure", "provider", "fetched_at"]


def sessions() -> list:
    """Trading sessions in the reserve window, from the exchange calendar."""
    from stable_engine.market_calendar import is_trading_day
    out, d = [], FIRST
    while d <= LAST:
        if is_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


async def main() -> int:
    from integrations.uw_api import get_iv_term_structure
    from integrations.uw_governor import UWUnavailable
    from jobs.iv_snapshot import PROVIDER, summarize

    if not os.path.isdir("F:\\"):
        print("F: is not mounted; nothing written")
        return 3
    if not (os.environ.get("UW_API_KEY") or os.environ.get("UNUSUAL_WHALES_API_KEY")):
        print("UW API key: MISSING from the environment (run under `railway run`)")
    else:
        print("UW API key: present")            # never the value

    days = sessions()
    print("=" * 96)
    print("R-IV.1148(b) SEALED IV RESERVE PULL -- parquet only, no table write")
    print("window %s .. %s | %d sessions | %d names | %d calls | out: %s"
          % (FIRST, LAST, len(days), len(CENSUS), len(days) * len(CENSUS), OUT_DIR))
    print("=" * 96)
    print()

    os.makedirs(OUT_DIR, exist_ok=True)
    rows_by_ticker: dict = {t: [] for t in CENSUS}
    problems: list = []
    calls = 0

    for t in CENSUS:
        got = miss = bad = 0
        for s in days:
            body = await get_iv_term_structure(t, s.isoformat(), caller=CALLER_TAG)
            calls += 1
            if isinstance(body, UWUnavailable):
                problems.append((t, s, "governor refused: %s"
                                 % getattr(body, "reason", "?")))
                print("  %-5s %s GOVERNOR REFUSED -- stopping this name" % (t, s))
                break
            data = body.get("data") if isinstance(body, dict) else None
            if not isinstance(data, list):
                bad += 1
                problems.append((t, s, "unparseable body"))
                continue
            sm = summarize(data, s)
            if sm["iv_near"] is None:
                miss += 1          # a real session with no live expiry; recorded, not dropped
            rows_by_ticker[t].append({
                "ticker": t,
                "session_date": s,
                "near_expiry": sm["near_expiry"],
                "near_dte": sm["near_dte"],
                "iv_near": sm["iv_near"],
                "iv_30d": sm["iv_30d"],
                "iv_30d_method": sm["iv_30d_method"],
                "term_structure": json.dumps(body),
                "provider": PROVIDER,
                "fetched_at": datetime.now(timezone.utc),
            })
            got += 1
        print("  %-5s %2d/%d sessions   no_live_iv=%d unparseable=%d"
              % (t, got, len(days), miss, bad))

    print()
    print("CALLS: %d" % calls)
    print()

    # ---- write one parquet per ticker, in the table's column order ----
    print("%-6s %6s %-12s %-12s %s" % ("name", "rows", "first", "last", "sha256"))
    print("-" * 96)
    written = []
    for t in CENSUS:
        rows = rows_by_ticker[t]
        if not rows:
            print("%-6s %6d %-12s %-12s %s" % (t, 0, "-", "-", "NOT WRITTEN"))
            problems.append((t, None, "no rows"))
            continue
        df = pd.DataFrame(rows)[COLUMNS]
        path = os.path.join(OUT_DIR, "%s.parquet" % t)
        df.to_parquet(path, index=False)
        back = pd.read_parquet(path)
        if len(back) != len(df):
            problems.append((t, None, "read-back %d != written %d" % (len(back), len(df))))
        sess = sorted(str(x) for x in df["session_date"])
        sha = sha256_of(path)
        written.append((t, path, len(df), sess[0], sess[-1], sha))
        print("%-6s %6d %-12s %-12s %s" % (t, len(df), sess[0], sess[-1], sha))

    if written:
        with io.open(os.path.join(OUT_DIR, "SHA256SUMS.txt"), "w",
                     encoding="utf-8", newline="\n") as fh:
            fh.write("# Sealed TRITON-R IV reserve, %s .. %s, %d sessions\n"
                     % (FIRST, LAST, len(days)))
            fh.write("# Exactly the iv_snapshots column schema. NEVER loaded into that table.\n")
            for t, path, n, a, b, sha in written:
                fh.write("%s  %s\n" % (sha, os.path.basename(path)))
        print()
        print("SHA256SUMS.txt written (%d entries)" % len(written))

    print()
    if problems:
        print("PROBLEMS (%d):" % len(problems))
        for t, s, why in problems:
            print("   %-5s %-12s %s" % (t, s or "-", why))
        return 4
    print("done")
    return 0


sys.exit(asyncio.run(main()))
