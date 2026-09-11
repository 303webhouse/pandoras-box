# uw_forward_logger — OUTPUT INVENTORY AND TRANSFER PLAN

**CC-BUILD, 2026-09-11. R-IV.371(a).** Derived from `gen_vps_writer.py`, the script that
deployed it. **The VPS is unreachable from this workstation (22/443/80 all time out), so
this is a plan for the principal to execute, not a report of a copy taken.**

**THE BOX RETIRES AFTER THIS. An incomplete copy is unrecoverable** — these are forward
collections; UW does not sell back the days you did not keep.

---

## 1. WHAT IT WROTE, AND WHERE

```
/opt/openclaw/workspace/data/cache/uw/
├── darkpool/<TICKER>/<YYYYMM>.parquet
├── flow_alerts/<TICKER>/<YYYYMM>.parquet
├── greek_exposure/<TICKER>/<YYYYMM>.parquet
├── net_prem_ticks/<TICKER>/<YYYYMM>.parquet
├── spot_exposures/<TICKER>/<YYYYMM>.parquet
├── greek_exposure_daily/<TICKER>/<TICKER>_rolling.parquet   ← DIFFERENT, see §2
└── .canary_flags/
```

**Format:** Parquet, `engine="pyarrow"`, `index=False`, written atomically
(`mkstemp` → `to_parquet` → `os.replace`).

**Tickers:** whatever is in `/opt/openclaw/workspace/config/uw_logger_watchlist.yaml`
(`tickers:` list). **Copy that file too — without it the directory names are the only
record of what was being collected, and a ticker that was removed mid-life leaves a
directory with no explanation.**

**Date range:** one file per ticker per calendar month, named `YYYYMM`. **The range is
whatever months exist on disk; it is not recorded anywhere else.**

## 2. THE ONE FILE THAT BEHAVES DIFFERENTLY — read this before stopping anything

**Monthly files are MERGE-AND-APPEND:**

```python
existing = pd.read_parquet(path)
combined = pd.concat([existing, new_df]).drop_duplicates()
```

**Cumulative and safe.** A month's file only grows.

**`greek_exposure_daily` is NOT:**

```python
if data_type == "greek_exposure_daily":
    path = _rolling_path(ticker)
    _write_atomic(path, new_df)      # OVERWRITE. No merge, no concat.
```

**Every run REPLACES it with whatever the fetcher just returned.**

**So its retained history is exactly one fetch wide, and what that window contains is
not determinable from this script** — it depends on how much history
`/api/stock/{ticker}/greek-exposure` returns per call. **If the endpoint returns a
rolling N-day series, the file holds N days. If it returns only the current day, every
prior day is already gone.**

**THIS IS THE FILE MOST WORTH HAVING** — it is the GEX series, the factor that went dark
today — **and it is the one with no guarantee of depth.** Verify it first (§4), not last.

## 3. THE COPY — order matters

**STOP FIRST, THEN COPY.** A run landing mid-copy cannot corrupt a file (`os.replace` is
atomic) but it can change `greek_exposure_daily` between the listing and the transfer,
so the manifest would describe something you did not take.

```bash
# 1 — stop the collector (principal, on the VPS)
systemctl stop <unit>            # or kill the process; confirm nothing restarts it
ps -eo pid,etime,cmd | grep -i uw_forward_logger     # expect nothing

# 2 — manifest BEFORE the copy, so completeness is checkable afterwards
cd /opt/openclaw/workspace/data/cache
find uw -type f -name '*.parquet' -printf '%p %s %TY-%Tm-%Td\n' | sort > /tmp/uw_manifest.txt
wc -l /tmp/uw_manifest.txt
du -sh uw

# 3 — copy, preserving structure and timestamps
tar czf /tmp/uw_cache_$(date +%Y%m%d).tar.gz uw \
    /opt/openclaw/workspace/config/uw_logger_watchlist.yaml
sha256sum /tmp/uw_cache_*.tar.gz

# 4 — pull it down (from the workstation)
scp root@188.245.250.2:/tmp/uw_cache_*.tar.gz .
scp root@188.245.250.2:/tmp/uw_manifest.txt .
sha256sum uw_cache_*.tar.gz        # must match step 3
```

**Also copy, because they are not in the archive above:** the collector's own logs
(wherever `logger.py` writes), and `/etc/openclaw/openclaw.env` **is NOT to be copied —
it holds the API key.**

## 4. VERIFY AFTER THE COPY, BEFORE THE BOX GOES

**A transfer is not done when the bytes land. It is done when you know what you have.**

```python
import pandas as pd, pathlib
root = pathlib.Path("uw")
for dt in sorted(p.name for p in root.iterdir() if p.is_dir()):
    files = list((root/dt).rglob("*.parquet"))
    rows = 0; lo = hi = None
    for f in files:
        d = pd.read_parquet(f); rows += len(d)
        for col in ("date","timestamp","ts","start_time"):
            if col in d.columns and len(d):
                c = pd.to_datetime(d[col], errors="coerce")
                lo = min(lo, c.min()) if lo is not None else c.min()
                hi = max(hi, c.max()) if hi is not None else c.max()
                break
    print("%-24s files=%-5d rows=%-9d %s -> %s" % (dt, len(files), rows, lo, hi))
```

**Record the output. It is the only description of this dataset that will exist** once
the box is gone.

**Expected shape, stated so a miss is visible:** five monthly data types each with one
directory per watchlist ticker, plus `greek_exposure_daily`. **A data type with zero
files, or a ticker present in the YAML with no directory, is a gap — find out whether it
never collected or whether the copy missed it, BEFORE retiring the box.**

## 5. WHAT NOT TO DO

- **Do not delete anything on the VPS until the checksum matches and §4 has run.**
- **Do not copy `/etc/openclaw/openclaw.env`** or any file containing the UW key.
- **Do not restart the collector "just to check something"** — it is the 23,417-request
  consumer, and the 8 PM ET reset is the measurement (§6).

## 6. THE MEASUREMENT THIS UNLOCKS

**With the logger stopped, the next reset gives hub-only demand against the 40,000 cap
for the first time.** Our own counter read 16,583 today against an account that hit
40,000; **after the stop those two numbers should converge.**

**If they do not converge, there is a THIRD consumer** — and that is worth knowing
before any plan decision. **The convergence check IS the verification that this
identification was right**; until it runs, `uw_forward_logger` is a strongly-evidenced
candidate and nothing more.

**Report Saturday, per R-IV.371(a).**
