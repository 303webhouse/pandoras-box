"""F: export — R-IV.955 / R-IV.964(d)(e) / R-IV.968(c)(d).

WHAT THIS WRITES, all free and with no UW calls:
  F:\\pandora-data\\bars1m\\<YYYY-MM-DD>\\<TICKER>.parquet   1-minute bars, the 8 census names
  F:\\pandora-data\\bars1d\\<TICKER>.parquet                 BTC-USD / ETH-USD daily from 2017
  F:\\pandora-data\\darkpool\\README.md                      the Parquet fields + condition codes
  F:\\pandora-data\\MANIFEST.tsv                             path, rows, bytes, sha256
  C:\\temp\\cc-query-handoff\\lab\\triton\\F-README.md        LAB's copy (it cannot read F:)

ATOMIC WRITES, following the house convention in
docs/edge/results/2026-09-11-uw-forward-logger-transfer-plan.md: mkstemp -> to_parquet ->
os.replace, so a killed run never leaves a half-written Parquet that reads as real. Every file
is then READ BACK and its row count and sha256 recorded in the manifest -- a copy nobody
verified is not a backup.

WHAT I DO NOT HOLD: R-IV.955's own text. Nothing in the repo or the lane file references it, so
the dark-pool Parquet layout here follows the house convention above (`darkpool/<TICKER>/
<YYYYMM>.parquet`) rather than a spec I was given. Flagged in the report; say the word and I
will reshape it.
"""
from __future__ import annotations

import asyncio
import csv
import glob
import hashlib
import json
import os
import re
import sys
import tempfile
import warnings
from datetime import date, datetime, timedelta, timezone

warnings.filterwarnings("ignore")

import pandas as pd  # noqa: E402
import yfinance as yf  # noqa: E402

ROOT = r"F:\pandora-data"
LAB_COPY = r"C:\temp\cc-query-handoff\lab\triton\F-README.md"

CENSUS = ["SPY", "QQQ", "IWM", "SMH", "NVDA", "AAPL", "MSFT", "TSLA"]
CRYPTO = ["BTC-USD", "ETH-USD"]
CRYPTO_START = "2017-01-01"

MANIFEST = os.path.join(ROOT, "MANIFEST.tsv")
_manifest_rows: list = []


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_parquet(df: pd.DataFrame, path: str) -> dict:
    """mkstemp -> to_parquet -> os.replace, then READ BACK. Returns the manifest row."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".parquet", dir=os.path.dirname(path))
    os.close(fd)
    try:
        df.to_parquet(tmp, index=True)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    back = pd.read_parquet(path)
    row = {"path": path, "rows_written": len(df), "rows_read_back": len(back),
           "bytes": os.path.getsize(path), "sha256": sha256_of(path)}
    # A copy nobody verified is not a backup.
    if len(back) != len(df):
        row["MISMATCH"] = "wrote %d, read back %d" % (len(df), len(back))
    _manifest_rows.append(row)
    return row


def write_text(path: str, text: str) -> dict:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".md", dir=os.path.dirname(path))
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)
    row = {"path": path, "rows_written": text.count("\n") + 1,
           "rows_read_back": open(path, encoding="utf-8").read().count("\n") + 1,
           "bytes": os.path.getsize(path), "sha256": sha256_of(path)}
    _manifest_rows.append(row)
    return row


# ── 1-minute bars, the 8 census names ───────────────────────────────────

def export_bars1m() -> None:
    """Every 1-minute bar yfinance still holds, split per session date.

    YFINANCE'S WINDOW IS ABOUT 30 DAYS, measured 2026-10-13: a request starting 2026-09-14
    returned bars and one starting 2026-09-08 returned none. The banked dark-pool sessions
    (08-28 to 09-04) are OUTSIDE it and return zero -- so this archives what still exists and
    cannot recover what has already gone. UW's /ohlc/1m does reach 08-28 and is the only route
    back, at a UW cost.

    Requested in 7-day chunks because that is the per-request cap for 1-minute data.
    """
    today = date.today()
    start = today - timedelta(days=29)
    print("=== bars1m: %s .. %s (yfinance window) ===" % (start, today))
    for ticker in CENSUS:
        frames = []
        chunk_start = start
        while chunk_start < today:
            chunk_end = min(chunk_start + timedelta(days=7), today + timedelta(days=1))
            try:
                # prepost=True, and it is not a detail. RTH-only returns 390 bars for a
                # session (09:30-15:59 ET); with extended hours it is 675 (04:00-19:59 ET).
                # The dark-pool prints this is meant to be matched against run to 19:59 ET --
                # the UW probe for 2026-08-28 spanned 13:45Z-23:59Z -- so RTH-only bars would
                # leave every after-hours print with no lit price to match. The ruling also
                # says EVERY bar yfinance still holds, and RTH-only is not that.
                df = yf.Ticker(ticker).history(
                    start=chunk_start.isoformat(), end=chunk_end.isoformat(),
                    interval="1m", auto_adjust=False, prepost=True, raise_errors=False)
                if df is not None and len(df):
                    frames.append(df)
            except Exception as exc:
                print("  %-5s %s..%s ERROR %s" % (ticker, chunk_start, chunk_end,
                                                  type(exc).__name__))
            chunk_start = chunk_end
        if not frames:
            print("  %-5s no bars returned" % ticker)
            continue
        all_df = pd.concat(frames)
        all_df = all_df[~all_df.index.duplicated(keep="first")].sort_index()
        # R-IV.973(c): say WHICH vendor every row came from. yfinance reaches back only ~30
        # days, so older sessions arrive from UW's /ohlc/1m instead -- two vendors with
        # different adjustment conventions, and a row that does not name its source cannot be
        # reconciled against the other. Written here so the README's column list is TRUE of the
        # files rather than a promise about them.
        all_df["source"] = "yfinance"
        by_day = {}
        for ts, row in all_df.iterrows():
            by_day.setdefault(ts.date(), []).append((ts, row))
        written = 0
        for d, rows in sorted(by_day.items()):
            sub = all_df.loc[[ts for ts, _ in rows]]
            path = os.path.join(ROOT, "bars1m", d.isoformat(), "%s.parquet" % ticker)
            write_parquet(sub, path)
            written += 1
        print("  %-5s %6d bars -> %d session files" % (ticker, len(all_df), written))


# ── BTC / ETH daily, 7 days a week, from 2017 ───────────────────────────

def export_bars1d() -> None:
    """R-IV.964(e). Explicit tickers, so a reader never has to infer which series this is."""
    print("=== bars1d: BTC-USD / ETH-USD daily from %s ===" % CRYPTO_START)
    for ticker in CRYPTO:
        try:
            df = yf.Ticker(ticker).history(start=CRYPTO_START, interval="1d",
                                           auto_adjust=False, raise_errors=False)
        except Exception as exc:
            print("  %-8s ERROR %s" % (ticker, type(exc).__name__))
            continue
        if df is None or not len(df):
            print("  %-8s no bars returned" % ticker)
            continue
        df = df.copy()
        df["ticker"] = ticker          # EXPLICIT, as ruled
        path = os.path.join(ROOT, "bars1d", "%s.parquet" % ticker)
        row = write_parquet(df, path)
        days = len({ts.date() for ts in df.index})
        print("  %-8s %5d daily bars (%s .. %s), %d distinct dates, %d bytes"
              % (ticker, len(df), df.index.min().date(), df.index.max().date(), days,
                 row["bytes"]))


# ── the dark-pool README LAB needs ──────────────────────────────────────

README = r"""# Dark-pool export — field reference and condition-code map

Written by `scripts/f_export.py`. **Generated, not hand-maintained** — if it disagrees with the
data, the data is right and this file is stale.

## Where the data is

```
F:\pandora-data\darkpool\<TICKER>\<YYYYMM>.parquet
```

One row per PRINT. The hub also keeps the raw vendor pages in Postgres
(`darkpool_backfill_pages`), where one row is one vendor RESPONSE of up to 500 prints — not one
print. The Parquet here is the flattened per-print form.

## Parquet field names

Every field is the vendor's own. Nothing here is derived, computed or renamed.

| field | meaning |
|---|---|
| `ticker` | the symbol the print is for |
| `executed_at` | execution timestamp (the ordering key; the feed is newest-first) |
| `trf_executed_at` | the TRF's own timestamp, which can differ from `executed_at` |
| `price` | print price |
| `size` | shares |
| `premium` | notional (price x size, as the vendor reports it) |
| `volume` | the symbol's cumulative session volume at the print |
| `market_center` | reporting venue code |
| `nbbo_bid` / `nbbo_ask` | the national best bid/offer AT the print |
| `nbbo_bid_quantity` / `nbbo_ask_quantity` | size at each side of the NBBO |
| `sale_cond_codes` | sale-condition codes — **the D1 cleaning field** |
| `trade_code` | trade code |
| `ext_hour_sold_codes` | extended-hours sold codes |
| `trade_settlement` | settlement type |
| `canceled` | whether the print was cancelled |
| `tracking_id` | the vendor's per-print id, so dedup needs no heuristic |

## Reading it safely

- **A session is only complete when `darkpool_backfill_sessions.exhausted = TRUE` AND
  `prints_received > 0`.** Anything else was cut short by the nightly budget and will be
  resumed — a census that ignores this reads a partial session as a real one.
- **`quarantined = TRUE` marks 2026-08-28 and 2026-08-31** (R-IV.921(b)4). Collected and kept,
  **never joined to `triton_flow_shadow`**.
- The census universe is the 8 core names only (R-IV.958(f)): SPY, QQQ, IWM, SMH, NVDA, AAPL,
  MSFT, TSLA.

## D1 condition-code map

**These are the vendor's codes as they arrive. The hub does not translate them, and this table
is the CTA/UTP meaning rather than anything the hub asserts** — treat it as a reading aid and
confirm against the vendor's own documentation before a published figure rests on it.

`sale_cond_codes` is a multi-code string; a print can carry several.

| code | CTA/UTP meaning | why D1 cares |
|---|---|---|
| `@` | regular sale | the ordinary case |
| `F` | intermarket sweep | not a single resting block |
| `T` / `U` | extended-hours trade (pre / post) | outside the lit session |
| `I` | odd lot | too small to be a block |
| `4` | derivatively priced | the price is not an independent print |
| `6` | corrected consolidated close | a correction, not a trade |
| `7` | qualified contingent trade | tied to another leg |
| `9` | corrected last | a correction |
| `B` | average price trade | an average, not a traded price |
| `C` | cash trade | non-standard settlement |
| `L` | sold last | reported late |
| `N` | next day | non-standard settlement |
| `O` | opening print | auction, not continuous |
| `M` | closing print | auction, not continuous |
| `R` | seller | non-standard settlement |
| `Z` | sold out of sequence | the timestamp is not the sequence |

**The two that matter most for a lit-price match:** `B` (average price) is not a price anyone
traded at, and `Z` / `L` mean the timestamp cannot be trusted as the sequence — so a
minute-bar join on `executed_at` will put them in the wrong minute.

## `bars1m/` — 1-minute bar Parquet columns (R-IV.978(e))

```
F:\pandora-data\bars1m\<YYYY-MM-DD>\<TICKER>.parquet
```

One row per MINUTE. The **index** is a timezone-aware timestamp in **US/Eastern** (not UTC, and
not naive) — the bar's OPENING minute. Columns, exactly as the source provides them:

| column | meaning |
|---|---|
| *(index)* | tz-aware ET timestamp, the minute the bar opens |
| `Open` / `High` / `Low` / `Close` | the minute's OHLC |
| `Adj Close` | split/dividend-adjusted close |
| `Volume` | shares in the minute |
| `Dividends` | dividend on that bar, usually 0.0 |
| `Stock Splits` | split factor on that bar, usually 0.0 |
| `Capital Gains` | fund capital gains, usually 0.0 (present for ETFs) |
| `source` | **`yfinance`** or **`uw`** — which vendor the bar came from |

**EXTENDED HOURS ARE INCLUDED: 04:00–19:59 ET**, not just the regular session. A session is
about 675 rows (≈275 pre-market, 390 regular, ≈10 after-hours), not 390. That matters because
the dark-pool prints these are matched against run to 19:59 ET, so an RTH-only archive would
leave every after-hours print with no lit price.

**`source` is why this column exists.** yfinance reaches back only ~30 days, so older sessions
come from UW's `/ohlc/1m` instead (R-IV.973(c)). The two are different vendors with different
adjustment conventions, and a row that does not say which it came from cannot be reconciled
against the other.

## `bars1d/` — daily bar Parquet columns

```
F:\pandora-data\bars1d\<TICKER>.parquet
```

One row per CALENDAR DAY, seven days a week for crypto. Same OHLC columns as above, plus an
explicit **`ticker`** column so a reader never has to infer which series a file holds.

- `BTC-USD`: from **2017-01-01**
- `ETH-USD`: from **2017-11-09** — yfinance holds nothing earlier, so this is not the same start
  date as BTC and should not be assumed to be.

## 1-minute lit prices — READ THIS BEFORE PLANNING D5

Measured 2026-10-13:

- **yfinance's 1-minute window is about 30 days.** A request starting 2026-09-14 returned bars;
  2026-09-08 returned none.
- **Every banked dark-pool session (08-28 to 09-04) returns ZERO 1-minute bars from yfinance.**
  Those lit prices are already gone from that source.
- **UW's `/ohlc/1m` DOES reach 2026-08-28** — a probe for that date returned 500 bars spanning
  13:45Z-23:59Z with `market_time`, so RTH can be separated. It is the only route back, and it
  costs UW calls (~2 per ticker-session at the 500-row cap).

So `bars1m/` here covers roughly the last 30 days only. Anything older has to come from UW, and
that is a budget decision rather than a free one.
"""


def export_readme() -> None:
    print("=== darkpool README + LAB copy ===")
    r1 = write_text(os.path.join(ROOT, "darkpool", "README.md"), README)
    print("  F: copy  %d bytes  sha256 %s" % (r1["bytes"], r1["sha256"][:16]))
    # R-IV.968(c): LAB may not read F: (its rule 13), so it gets a copy where it can.
    r2 = write_text(LAB_COPY, README)
    print("  LAB copy %d bytes  sha256 %s" % (r2["bytes"], r2["sha256"][:16]))
    print("  identical: %s" % (r1["sha256"] == r2["sha256"]))


# ── the dark-pool rows ──────────────────────────────────────────────────

#: COMPLETE SESSIONS ONLY (R-IV.955). `exhausted` alone is not enough: a session the vendor
#: served empty is also "exhausted", and an empty Parquet on the permanent archive reads as a
#: session with no prints rather than one never collected.
COMPLETE_SESSIONS_SQL = """
    SELECT ticker, session_date, prints_received, pages_fetched, quarantined
      FROM darkpool_backfill_sessions
     WHERE exhausted = TRUE AND reached_floor = TRUE AND prints_received > 0
     ORDER BY session_date, ticker
"""

PAGES_SQL = """
    SELECT page_no, payload, quarantined
      FROM darkpool_backfill_pages
     WHERE ticker = $1 AND session_date = $2
     ORDER BY page_no
"""


def _pg_dsn() -> str:
    """The write URL from the gitignored .mcp.json. NEVER printed."""
    raw = open(r"C:\trading-hub\.mcp.json", encoding="utf-8").read()
    for m in re.finditer(r"postgres(?:ql)?://[^\"\s]+", raw):
        if "railway.internal" not in m.group(0):
            return m.group(0)
    raise RuntimeError("no usable postgres URL in .mcp.json")


async def export_darkpool() -> None:
    """One Parquet per (TICKER, YYYYMM), one ROW PER PRINT, vendor fields only.

    Grouped by ticker-month rather than per session because that is the house layout, and
    written per ticker-month rather than all at once because a single SPY session is ~55,000
    prints and the whole archive is over a million.
    """
    import asyncpg

    print("=== darkpool rows: complete sessions only ===")
    conn = await asyncpg.connect(_pg_dsn())
    try:
        sessions = [dict(r) for r in await conn.fetch(COMPLETE_SESSIONS_SQL)]
        if not sessions:
            print("  no COMPLETE ticker-sessions yet; nothing exported")
            return
        # group by (ticker, YYYYMM)
        groups: dict = {}
        for s in sessions:
            key = (s["ticker"], s["session_date"].strftime("%Y%m"))
            groups.setdefault(key, []).append(s)
        print("  %d complete ticker-sessions -> %d ticker-month files"
              % (len(sessions), len(groups)))

        for (ticker, ym), rows in sorted(groups.items()):
            prints = []
            for s in rows:
                pages = await conn.fetch(PAGES_SQL, ticker, s["session_date"])
                for pg in pages:
                    payload = pg["payload"]
                    if isinstance(payload, str):
                        try:
                            payload = json.loads(payload)
                        except ValueError:
                            continue
                    data = (payload or {}).get("data")
                    if not isinstance(data, list):
                        continue
                    for rec in data:
                        if not isinstance(rec, dict):
                            continue
                        rec = dict(rec)
                        # provenance the vendor does not supply, kept explicit
                        rec["session_date"] = s["session_date"].isoformat()
                        rec["quarantined"] = bool(pg["quarantined"])
                        prints.append(rec)
            if not prints:
                print("  %-5s %s  no prints flattened" % (ticker, ym))
                continue
            df = pd.DataFrame(prints)
            path = os.path.join(ROOT, "darkpool", ticker, "%s.parquet" % ym)
            row = write_parquet(df, path)
            q = df["quarantined"].any() if "quarantined" in df.columns else False
            print("  %-5s %s  %7d prints  %9d bytes%s"
                  % (ticker, ym, len(df), row["bytes"], "  [QUARANTINED]" if q else ""))
    finally:
        await conn.close()


def _archive_rows() -> list:
    """Every file on F: that THIS run did not write, hashed — R-IV.1001(b).

    Without this the manifest described the RUN rather than the archive, so a file written by
    another process (the Polygon pull, which runs under `railway run` because the key is not
    on this machine) would be dropped from MANIFEST.tsv by the next nightly export while
    still sitting on the drive. An archive whose manifest omits part of it is worse than no
    manifest: it reads as a complete inventory.

    These rows carry `rows_written = -1`, NOT 0: this process did not write them, which is not
    the same as having written nothing.
    """
    written = {os.path.normcase(r["path"]) for r in _manifest_rows}
    out = []
    for dirpath, _dirs, files in os.walk(ROOT):
        for name in sorted(files):
            path = os.path.join(dirpath, name)
            if os.path.normcase(path) == os.path.normcase(MANIFEST):
                continue                       # the manifest does not list itself
            if os.path.normcase(path) in written:
                continue
            try:
                rows_back = -1
                if name.endswith(".parquet"):
                    rows_back = len(pd.read_parquet(path))
                out.append({"path": path, "rows_written": -1, "rows_read_back": rows_back,
                            "bytes": os.path.getsize(path), "sha256": sha256_of(path),
                            "note": "not written this run; hash verified"})
            except Exception as exc:                                # noqa: BLE001
                out.append({"path": path, "rows_written": -1, "rows_read_back": -1,
                            "bytes": os.path.getsize(path) if os.path.exists(path) else -1,
                            "sha256": "", "MISMATCH": "unreadable: %s" % type(exc).__name__})
    return out


def write_manifest() -> None:
    os.makedirs(ROOT, exist_ok=True)
    rows = list(_manifest_rows) + _archive_rows()
    rows.sort(key=lambda r: os.path.normcase(r["path"]))
    lines = ["path\trows_written\trows_read_back\tbytes\tsha256\tnote"]
    for r in rows:
        lines.append("\t".join([
            r["path"], str(r["rows_written"]), str(r["rows_read_back"]),
            str(r["bytes"]), r["sha256"], r.get("MISMATCH", r.get("note", ""))]))
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    bad = [r for r in rows if "MISMATCH" in r]
    carried = [r for r in rows if r["rows_written"] == -1]
    print()
    print("=== MANIFEST: %s ===" % MANIFEST)
    print("  files: %d (%d written this run, %d carried and hash-verified)   total bytes: %s"
          % (len(rows), len(rows) - len(carried), len(carried),
             f"{sum(max(r['bytes'], 0) for r in rows):,}"))
    print("  read-back mismatches: %s" % (len(bad) if bad else "NONE"))
    for r in bad:
        print("    %s -> %s" % (r["path"], r["MISMATCH"]))


# -- the match report (R-IV.993(d)) -------------------------------------

#: QUERY's A0 input. Produced by QUERY, not by this script, and read-only here.
QUERY_COMPLETE_CSV = r"C:\temp\cc-query-handoff\triton-a0\complete.csv"


def _read_query_complete():
    """{session_date: set(tickers marked complete)} from QUERY's file, or {} if absent.

    Absent is reported, never treated as "nothing is complete": the two mean different
    things, and a missing input that reads as an empty one is how a gap becomes a pass.
    """
    if not os.path.isfile(QUERY_COMPLETE_CSV):
        return None
    out = {}
    with open(QUERY_COMPLETE_CSV, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if (row.get("complete") or "").strip().lower() == "true":
                out.setdefault(row["session"], set()).add(row["ticker"])
    return out


def _on_f_by_session():
    """{session_date: set(tickers)} actually present on F:, by the QUERIED session_date."""
    out = {}
    for path in glob.glob(os.path.join(ROOT, "darkpool", "*", "*.parquet")):
        ticker = os.path.basename(os.path.dirname(path))
        try:
            col = pd.read_parquet(path, columns=["session_date"])["session_date"]
        except Exception:                                           # noqa: BLE001
            continue
        for sd in col.astype(str).unique():
            out.setdefault(sd, set()).add(ticker)
    return out


def match_report() -> int:
    """Print DB-complete vs on-F:. Returns the number of MISMATCHED dates in the overlap."""
    print()
    print("=== R-IV.993(d) MATCH REPORT: dates complete in DB vs dates on F: ===")
    census = set(CENSUS)
    q = _read_query_complete()
    on_f = _on_f_by_session()
    f_dates = sorted(d for d, t in on_f.items() if census <= t)
    f_partial = sorted((d, sorted(census - t)) for d, t in on_f.items() if t and not census <= t)

    if q is None:
        print("  QUERY's complete.csv is ABSENT at %s" % QUERY_COMPLETE_CSV)
        print("  -> cannot compute the match. This is NOT the same as 'nothing is complete'.")
        print("  on F:, all %d names: %d dates: %s"
              % (len(census), len(f_dates), ", ".join(f_dates) or "none"))
        return -1

    q_dates = sorted(d for d, t in q.items() if census <= t)
    q_partial = sorted((d, sorted(census - t)) for d, t in q.items() if t and not census <= t)

    # The verdict is computed on the OVERLAP of the two windows, for the reason in the
    # module docstring: different windows guarantee a mismatch that means nothing.
    lo, hi = (min(q.keys()), max(q.keys())) if q else (None, None)
    in_window = [d for d in f_dates if lo <= d <= hi]
    missing = [d for d in q_dates if d not in f_dates]
    extra = [d for d in in_window if d not in q_dates]
    outside = [d for d in f_dates if not (lo <= d <= hi)]

    print("  complete.csv window        : %s .. %s" % (lo, hi))
    print("  NOTE: the left-hand side is QUERY's complete.csv, NOT this hub's DB. F: is")
    print("        written from the DB's `reached_floor`, which since R-IV.1005(d) accepts")
    print("        the b2 exhaustion route. A disagreement therefore means complete.csv has")
    print("        not been regenerated under b2 yet -- not that F: is wrong.")
    print("  per QUERY complete.csv, all %d names: %d dates: %s"
          % (len(census), len(q_dates), ", ".join(q_dates) or "none"))
    print("  on F:,       all %d names   : %d dates in window: %s"
          % (len(census), len(in_window), ", ".join(in_window) or "none"))
    if outside:
        print("  on F: but OUTSIDE the window: %s  (not a mismatch)" % ", ".join(outside))
    for d, miss in q_partial:
        print("  DB partial  %s: missing %s" % (d, ", ".join(miss)))
    for d, miss in f_partial:
        print("  F: partial  %s: missing %s" % (d, ", ".join(miss)))

    if missing:
        print("  >>> MISMATCH: complete per complete.csv but NOT all-%d on F:: %s"
              % (len(census), ", ".join(missing)))
        print("      This direction IS a problem: the archive is missing something QUERY "
              "considers whole.")
    if extra:
        print("  >>> on F: all-%d but NOT marked complete in complete.csv: %s"
              % (len(census), ", ".join(extra)))
        print("      Expected while QUERY's file predates the b2 route (R-IV.1005(d)): these "
              "are b2-proved sessions. Regenerate complete.csv under b2 to clear it.")
    if not missing and not extra:
        print("  >>> MATCH: every in-window date agrees. QUERY's A0 may run.")
    return len(missing) + len(extra)


def main() -> int:
    started = datetime.now(timezone.utc)
    print("F: export starting %s UTC" % started.strftime("%Y-%m-%d %H:%M:%S"))
    if not os.path.isdir("F:\\"):
        print("F: is not available; nothing written")
        return 1
    os.makedirs(ROOT, exist_ok=True)
    export_readme()
    print()
    export_bars1d()
    print()
    export_bars1m()
    print()
    try:
        asyncio.run(export_darkpool())
    except Exception as exc:                                        # noqa: BLE001
        # The bars and the README are already on disk and verified; a database failure must not
        # discard them or skip the manifest that proves they are there.
        print("  darkpool export FAILED: %s: %s" % (type(exc).__name__, exc))
    write_manifest()
    try:
        mismatches = match_report()
    except Exception as exc:                                        # noqa: BLE001
        print("  match report FAILED: %s: %s" % (type(exc).__name__, exc))
        mismatches = -1
    print()
    print("done in %.1fs" % (datetime.now(timezone.utc) - started).total_seconds())
    # A non-zero exit means the archive and the DB disagree, so a scheduler run that nobody
    # reads still leaves a signal. 0 only when they MATCH.
    return 0 if mismatches == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
