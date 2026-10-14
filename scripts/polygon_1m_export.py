"""Polygon 1-minute bars for TRITON's D6 calibration window — R-IV.1001(b).

WHY POLYGON. Measured under R-IV.997(d): UW `/ohlc/1m` ignores `date_from`/`date_to`, has no
backward cursor of any kind (nine candidates all returned HTTP 200 and the identical newest
window) and caps at `limit=2000`, reaching 4.52 days. yfinance 1-minute is a hard 30-day roll
whose edge was 2026-09-14 — so 09-01..09-11 had already fallen off it before R-IV.973(c) was
written. Polygon serves the whole window today.

WHY BOTH ADJUSTMENT MODES. D6 compares 1-minute LOWS against dark-pool PRINT PRICES, and
prints are raw executed prices. Like must be compared with like, so the unadjusted series is
the one D6 needs — and the adjusted series is pulled beside it purely to PROVE there was no
corporate action in the window. If any bar differs, the two are not interchangeable and this
script STOPS: LAB amends §3.3 before D6 reads either series.

THE COMPARISON IS BAR-FOR-BAR ON A JOIN, NOT A ROW COUNT. Two series can have identical
lengths and different prices, and a count would call that a match.

RUN IT UNDER `railway run`: POLYGON_API_KEY lives on Railway, not on this machine. The key is
read from the injected environment, never printed, and never interpolated into output.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone

import pandas as pd

ROOT = r"F:\pandora-data"
OUT_DIR = os.path.join(ROOT, "bars1m_polygon")

#: R-IV.958(f): the census is these eight names.
CENSUS = ["SPY", "QQQ", "IWM", "SMH", "NVDA", "AAPL", "MSFT", "TSLA"]

#: R-IV.1001(b). Inclusive, and wider than the 09-01..09-11 calibration range on purpose:
#: 08-28 is the vendor's oldest dark-pool session and 09-24 is the newest date QUERY's
#: complete.csv covers, so the bars span every session the census can be graded on.
DATE_FROM, DATE_TO = "2026-08-28", "2026-09-24"

#: 50,000 is Polygon's documented aggregate page limit. The whole window for one ticker is
#: ~25,000 one-minute bars, so one call per (ticker, adjustment) suffices -- 16 calls.
PAGE_LIMIT = 50000

#: Polygon Starter allows 5 requests per minute. The first run of this script fired 16 calls
#: flat out: 5 returned 200 and ELEVEN returned 429. Paced at 13s, 16 calls take ~3.5 minutes.
RATE_LIMIT_SLEEP_S = 13.0
MAX_429_RETRIES = 4

CALLS = {"n": 0, "http": {}, "retries": 0}


def _key() -> str:
    k = os.environ.get("POLYGON_API_KEY") or ""
    if not k:
        print("POLYGON_API_KEY: MISSING from the environment. Run this under "
              "`railway run`, which injects it.")
        sys.exit(2)
    print("POLYGON_API_KEY: present")            # never the value
    return k


def fetch(ticker: str, adjusted: bool, key: str):
    """One call. Returns (status, bars list). Never raises."""
    url = ("https://api.polygon.io/v2/aggs/ticker/%s/range/1/minute/%s/%s"
           "?adjusted=%s&sort=asc&limit=%d"
           % (ticker, DATE_FROM, DATE_TO, "true" if adjusted else "false", PAGE_LIMIT))
    for attempt in range(MAX_429_RETRIES + 1):
        req = urllib.request.Request(url)
        req.add_header("Authorization", "Bearer " + key)   # built apart from anything printed
        CALLS["n"] += 1
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                CALLS["http"][r.status] = CALLS["http"].get(r.status, 0) + 1
                body = json.loads(r.read().decode("utf-8"))
                return r.status, body.get("results") or []
        except urllib.error.HTTPError as e:
            CALLS["http"][e.code] = CALLS["http"].get(e.code, 0) + 1
            if e.code == 429 and attempt < MAX_429_RETRIES:
                CALLS["retries"] += 1
                wait = RATE_LIMIT_SLEEP_S * (attempt + 2)
                print("    %s adjusted=%s 429 -- waiting %.0fs (attempt %d)"
                      % (ticker, adjusted, wait, attempt + 1))
                time.sleep(wait)
                continue
            return e.code, []
        except Exception as exc:                                    # noqa: BLE001
            print("    %s adjusted=%s FAILED %s: %s" % (ticker, adjusted,
                                                        type(exc).__name__, exc))
            return 0, []
    return 429, []


def to_frame(bars, ticker: str, adjusted: bool) -> pd.DataFrame:
    df = pd.DataFrame(bars)
    if df.empty:
        return df
    # `t` is epoch milliseconds UTC. Both clocks are carried, because convention #39 says a
    # comparison states its basis and D6 will join these against ET session dates.
    ts = pd.to_datetime(df["t"], unit="ms", utc=True)
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close",
                            "v": "volume", "n": "transactions", "vw": "vwap"})
    df["timestamp_utc"] = ts
    df["timestamp_et"] = ts.dt.tz_convert("America/New_York")
    df["session_et"] = df["timestamp_et"].dt.date.astype(str)
    df["ticker"] = ticker
    df["source"] = "polygon_v2_aggs_1minute"
    df["adjusted"] = adjusted
    return df.drop(columns=[c for c in ("t",) if c in df.columns])


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write(df: pd.DataFrame, path: str) -> dict:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".parquet", dir=os.path.dirname(path))
    os.close(fd)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    back = pd.read_parquet(path)
    return {"path": path, "rows": len(df), "rows_read_back": len(back),
            "bytes": os.path.getsize(path), "sha256": sha256_of(path),
            "ok": len(back) == len(df)}


PRICE_COLS = ["open", "high", "low", "close", "vwap"]


def compare(raw: pd.DataFrame, adj: pd.DataFrame, ticker: str):
    """Bar-for-bar on a timestamp join. Returns (n_compared, n_differing, detail)."""
    if raw.empty or adj.empty:
        return 0, -1, "one series is empty, so nothing was compared"
    a = raw.set_index("timestamp_utc")[PRICE_COLS].sort_index()
    b = adj.set_index("timestamp_utc")[PRICE_COLS].sort_index()
    common = a.index.intersection(b.index)
    only_raw, only_adj = len(a.index.difference(b.index)), len(b.index.difference(a.index))
    aa, bb = a.loc[common], b.loc[common]
    diff = (aa != bb) & ~(aa.isna() & bb.isna())
    n_bars = int(diff.any(axis=1).sum())
    detail = "bars compared %d; differing %d; timestamps only-raw %d only-adjusted %d" % (
        len(common), n_bars, only_raw, only_adj)
    if only_raw or only_adj:
        # A timestamp present in one series and not the other is itself a difference.
        n_bars += only_raw + only_adj
    return len(common), n_bars, detail


def main() -> int:
    if not os.path.isdir("F:\\"):
        print("F: is not mounted; nothing written")
        return 3
    key = _key()
    print("Polygon 1-minute, %s .. %s, %d names, BOTH adjustment modes (%d calls)"
          % (DATE_FROM, DATE_TO, len(CENSUS), 2 * len(CENSUS)))
    print()

    rows, findings, incomplete = [], [], []
    for ticker in CENSUS:
        series = {}
        for adjusted in (False, True):
            if CALLS["n"]:
                time.sleep(RATE_LIMIT_SLEEP_S)      # 5 req/min on Starter
            st, bars = fetch(ticker, adjusted, key)
            df = to_frame(bars, ticker, adjusted)
            series[adjusted] = df
            path = os.path.join(OUT_DIR, "%s_adjusted_%s.parquet"
                                % (ticker, "true" if adjusted else "false"))
            if df.empty:
                print("  %-5s adjusted=%-5s HTTP %-3s  NO BARS -- not written"
                      % (ticker, adjusted, st))
                # NOT a `findings` entry. A fetch that did not happen is not evidence that
                # the two series disagree, and the first run of this script reported exactly
                # that -- it would have triggered a LAB §3.3 amendment over a rate limit.
                incomplete.append((ticker, "adjusted=%s: HTTP %s, no bars" % (adjusted, st)))
                continue
            r = write(df, path)
            rows.append(r)
            print("  %-5s adjusted=%-5s HTTP %-3s  %6d bars  %2d sessions  %9d bytes  %s%s"
                  % (ticker, adjusted, st, r["rows"],
                     df["session_et"].nunique(), r["bytes"], r["sha256"][:16],
                     "" if r["ok"] else "  READ-BACK MISMATCH"))
        n, ndiff, detail = compare(series.get(False, pd.DataFrame()),
                                   series.get(True, pd.DataFrame()), ticker)
        print("        compare: %s" % detail)
        if ndiff > 0:
            findings.append((ticker, detail))
        elif ndiff < 0:
            incomplete.append((ticker, detail))

    print()
    print("CALLS: %d   HTTP: %s" % (CALLS["n"], CALLS["http"]))
    print()
    # THREE OUTCOMES, AND THEY ARE NOT INTERCHANGEABLE. Only the middle one is a LAB matter.
    if findings:
        print(">>> STOP (R-IV.1001(b)): the two series DIFFER on at least one bar.")
        for t, d in findings:
            print("      %-5s %s" % (t, d))
        print("    D6 must not read either series until LAB amends §3.3.")
        return 4
    if incomplete:
        print(">>> INCOMPLETE: some bars were never fetched, so nothing is concluded about")
        print("    whether the series agree. This is NOT a difference and NOT a LAB matter;")
        print("    re-run. (Polygon Starter allows 5 requests/minute.)")
        for t, d in incomplete:
            print("      %-5s %s" % (t, d))
        return 5

    note = "no corporate action in window"
    print(">>> ADJUSTED AND UNADJUSTED ARE IDENTICAL ON EVERY BAR, ALL %d NAMES."
          % len(CENSUS))
    print("    Artifact statement: \"%s\" (%s .. %s)" % (note, DATE_FROM, DATE_TO))
    readme = os.path.join(OUT_DIR, "README.md")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(readme, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            "# Polygon 1-minute bars - TRITON D6 calibration\n\n"
            "Pulled %s UTC. Source: Polygon `/v2/aggs/ticker/{t}/range/1/minute`.\n\n"
            "Window: **%s .. %s** inclusive. Names: %s.\n\n"
            "## %s\n\n"
            "Both `adjusted=false` and `adjusted=true` were pulled for every name and compared\n"
            "BAR FOR BAR on a UTC-timestamp join across open/high/low/close/vwap. They are\n"
            "identical on every bar, so **%s** and either series may be used.\n\n"
            "**D6 should still read `adjusted_false`**: it compares 1-minute lows against\n"
            "dark-pool print prices, and prints are raw executed prices (R-IV.1001(b)).\n\n"
            "## Clocks (convention #39)\n\n"
            "`timestamp_utc` is authoritative. `timestamp_et` and `session_et` are the same\n"
            "instant in America/New_York, carried so a join against an exchange session date\n"
            "needs no conversion by the reader. Bars span 04:00-19:59 ET.\n"
            % (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
               DATE_FROM, DATE_TO, ", ".join(CENSUS), note.upper(), note))
    print("    README: %s" % readme)
    print()
    print("Run scripts/f_export.py to fold these into MANIFEST.tsv (it now hashes the whole "
          "archive, not just what one process wrote).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
