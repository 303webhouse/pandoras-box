"""Session_Sweep round 2 (R-IV.1027(c)) -- fetch Binance BTCUSDT 5m monthly klines, verify, build Parquet.

Declarations: lab\\crypto-replay\\06-ROUND2-DECLARATIONS.md (9b99d1fe...), sec. 2. Stamped before any
download.
  PERP  data/futures/um/monthly/klines/BTCUSDT/5m/   2019-09 .. 2026-09
  SPOT  data/spot/monthly/klines/BTCUSDT/5m/         2017-07 .. 2026-09
Every month in range is requested (no listing); a 404 is "not archived". Each zip comes with its
.CHECKSUM; a zip whose SHA-256 does not match is discarded and counted, never parsed. <= 1 request/s.
HARD STOP at 250 MB cumulative download. Storage is local and git-ignored (data/archives/).

Usage (run with python -I from the repo root):
  python -I scripts/lab/session_sweep_fetch.py fetch-all <out_root>      (perp then spot, cumulative stop)
  python -I scripts/lab/session_sweep_fetch.py fetch <perp|spot> <out_root>
  python -I scripts/lab/session_sweep_fetch.py build <perp|spot> <out_root>
  python -I scripts/lab/session_sweep_fetch.py selftest
"""
import csv
import hashlib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile

import numpy as np
import pandas as pd

BASE = "https://data.binance.vision/"
SOURCES = {
    "perp": ("data/futures/um/monthly/klines/BTCUSDT/5m/", (2019, 9)),
    "spot": ("data/spot/monthly/klines/BTCUSDT/5m/", (2017, 7)),
}
LAST_MONTH = (2026, 9)
HARD_STOP_BYTES = 250 * 1024 * 1024
MIN_INTERVAL_S = 1.0
BAR_MS = 5 * 60 * 1000
_last_req = [0.0]


def months(start, end=LAST_MONTH):
    y, m = start
    while (y, m) <= end:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _get(url):
    """One throttled GET. Returns (status, bytes)."""
    wait = MIN_INTERVAL_S - (time.monotonic() - _last_req[0])
    if wait > 0:
        time.sleep(wait)
    _last_req[0] = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": "trading-hub-lab/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def checksum_of(text):
    """Binance .CHECKSUM: '<sha256>  <filename>'."""
    return text.strip().split()[0].lower() if text.strip() else ""


def fetch(source, out_root, spent=0):
    prefix, start = SOURCES[source]
    raw_dir = os.path.join(out_root, "raw", source)
    os.makedirs(raw_dir, exist_ok=True)
    rows = []
    for y, m in months(start):
        name = f"BTCUSDT-5m-{y:04d}-{m:02d}.zip"
        st, body = _get(BASE + prefix + name)
        row = {"source": source, "month": f"{y:04d}-{m:02d}", "zip_status": st, "zip_bytes": len(body),
               "checksum_status": "", "sha256": "", "verified": False}
        spent += len(body)
        if st == 200:
            cst, cbody = _get(BASE + prefix + name + ".CHECKSUM")
            spent += len(cbody)
            row["checksum_status"] = cst
            got = hashlib.sha256(body).hexdigest()
            row["sha256"] = got
            want = checksum_of(cbody.decode("utf-8", "replace")) if cst == 200 else ""
            row["verified"] = bool(want) and want == got
            if row["verified"]:
                with open(os.path.join(raw_dir, name), "wb") as fh:
                    fh.write(body)
        rows.append(row)
        print(f"{source} {row['month']} zip={st} {len(body):>9} B verified={row['verified']} total={spent / 1e6:.1f} MB",
              flush=True)
        if spent > HARD_STOP_BYTES:
            print(f"HARD STOP: {spent} bytes > {HARD_STOP_BYTES}")
            break
    man = os.path.join(out_root, f"manifest_{source}.csv")
    with open(man, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return rows, spent


def parse_zip_bytes(body):
    """The CSV inside one verified zip -> DataFrame(open_time_utc, open, high, low, close, volume)."""
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"expected one CSV in the zip, found {names}")
        text = z.read(names[0]).decode("utf-8")
    df = pd.read_csv(io.StringIO(text), header=None, dtype=str)
    if not str(df.iloc[0, 0]).strip().isdigit():          # a header row (later futures files)
        df = df.iloc[1:]
    ot = pd.to_numeric(df[0]).astype("int64")
    ms = np.where(ot >= 10 ** 15, ot // 1000, ot)          # microseconds (spot from 2025) -> ms
    out = pd.DataFrame({"open_time_ms": ms.astype("int64")})
    for i, c in zip(range(1, 6), ("open", "high", "low", "close", "volume")):
        out[c] = pd.to_numeric(df[i].values, errors="coerce")
    return out


def build(source, out_root):
    raw_dir = os.path.join(out_root, "raw", source)
    files = sorted(f for f in os.listdir(raw_dir) if f.endswith(".zip"))
    parts = [parse_zip_bytes(open(os.path.join(raw_dir, f), "rb").read()) for f in files]
    df = pd.concat(parts, ignore_index=True)
    n0 = len(df)
    df = df.dropna(subset=["open", "high", "low", "close"])
    n_nan = n0 - len(df)
    off = df.open_time_ms % BAR_MS != 0
    n_off = int(off.sum())
    df = df[~off]
    n1 = len(df)
    df = df.sort_values("open_time_ms").drop_duplicates("open_time_ms", keep="first")
    n_dup = n1 - len(df)
    df["open_time_utc"] = pd.to_datetime(df.open_time_ms, unit="ms", utc=True)
    df = df[["open_time_utc", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
    path = os.path.join(out_root, f"btcusdt_{source}_5m.parquet")
    df.to_parquet(path, index=False)
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    info = {"source": source, "zips": len(files), "rows": len(df), "dropped_nan": n_nan,
            "dropped_off_grid": n_off, "dropped_duplicates": n_dup,
            "first": str(df.open_time_utc.iloc[0]), "last": str(df.open_time_utc.iloc[-1]),
            "parquet": path, "parquet_sha256": sha, "parquet_bytes": os.path.getsize(path)}
    print(json.dumps(info, indent=1))
    json.dump(info, open(os.path.join(out_root, f"build_{source}.json"), "w"), indent=1)
    return info


def selftest():
    checks = {}
    checks["months: 2019-09..2026-09 is 85"] = len(list(months((2019, 9)))) == 85
    checks["months: 2017-07..2026-09 is 111"] = len(list(months((2017, 7)))) == 111
    checks["checksum line parsed"] = checksum_of("ABCdef  BTCUSDT-5m-2020-01.zip\n") == "abcdef"

    def mkzip(lines):
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr("BTCUSDT-5m-2025-01.csv", "\n".join(lines) + "\n")
        return b.getvalue()
    ms_rows = ["1577836800000,7195.2,7196.2,7178.6,7179.8,95.5,1577837099999,0,0,0,0,0",
               "1577837100000,7179.8,7180.0,7170.0,7175.0,80.1,1577837399999,0,0,0,0,0"]
    a = parse_zip_bytes(mkzip(ms_rows))
    checks["ms timestamps read"] = a.open_time_ms.tolist() == [1577836800000, 1577837100000]
    hdr = ["open_time,open,high,low,close,volume,close_time,quote_volume,count,tb_base,tb_quote,ignore"] + ms_rows
    checks["a header row is skipped"] = len(parse_zip_bytes(mkzip(hdr))) == 2
    us_rows = ["1735689600000000,93576.0,93610.9,93537.5,93567.8,10.1,1735689899999999,0,0,0,0,0"]
    checks["microsecond timestamps (spot 2025+) converted to ms"] = \
        parse_zip_bytes(mkzip(us_rows)).open_time_ms.iloc[0] == 1735689600000
    for k, v in checks.items():
        print(("PASS " if v else "FAIL ") + k)
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "selftest":
        sys.exit(selftest())
    elif mode == "fetch":
        fetch(sys.argv[2], sys.argv[3])
    elif mode == "fetch-all":                    # perp then spot; the 250 MB stop is cumulative across both
        _, spent_ = fetch("perp", sys.argv[2])
        if spent_ <= HARD_STOP_BYTES:
            fetch("spot", sys.argv[2], spent=spent_)
    elif mode == "build":
        build(sys.argv[2], sys.argv[3])
