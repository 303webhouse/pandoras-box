"""Test 03-LIVE-INSTRUMENT.sql in DuckDB on a SYNTHETIC signals table built from replay fires
(no DB data), and compare L1 / L3 / L4 with the Python replay logic on the same fires."""
import re
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, r"C:\trading-hub-lab\scripts\lab")
import t14_co_fire as t14  # noqa: E402

LAB = r"C:\temp\cc-query-handoff\lab"
sql = open(LAB + r"\co-fire\03-LIVE-INSTRUMENT.sql", encoding="utf-8").read()
O = pd.read_csv(LAB + r"\co-fire\02-live-outcomes.csv.gz", parse_dates=["d"])
F = pd.read_csv(LAB + r"\move-size\fires.csv.gz", parse_dates=["date"])
F = F[(F.date >= "2024-07-01") & (F.date <= "2026-08-27") & F.ticker.isin(set(O.ticker))]
# synthetic signals: fire at 15:00 ET = 19:00/20:00 UTC (naive UTC), ids above the seal
ts = (F.date + pd.Timedelta(hours=15)).dt.tz_localize("America/New_York").dt.tz_convert("UTC").dt.tz_localize(None)
S = pd.DataFrame({"id": np.arange(500000, 500000 + len(F)), "timestamp": ts.values, "strategy": "X",
                  "ticker": F.ticker.values, "asset_class": "EQUITY",
                  "direction": F.side.values, "signal_type": F.type.values})
S = S.astype({c: object for c in ["strategy", "ticker", "asset_class", "direction", "signal_type"]})
O = O.astype({c: object for c in ["ticker", "spy_state"]})
con = duckdb.connect()
con.execute("INSTALL icu; LOAD icu; INSTALL json; LOAD json;")
con.register("S_df", S)
con.execute("CREATE TABLE signals AS SELECT *, CAST(NULL AS JSON) AS triggering_factors FROM S_df")
con.register("O_df", O)
con.execute("CREATE TABLE lab_outcomes AS SELECT ticker, CAST(d AS DATE) AS d, r5_adj, r20_adj, m30, sig20, vol_tercile, spy_state FROM O_df")

body = sql.split("-- L1")[0]
with_block = body[body.index("WITH f AS"):].rstrip()
queries = re.findall(r"\n(SELECT .*?)\n;", sql[sql.index("-- L1"):], flags=re.S)
res = {}
for name, q in zip(["L1", "L2", "L3", "L4", "L5"], queries):
    res[name] = con.execute(with_block + "\n" + q).df()
    print(name, len(res[name]), "rows")

# Python reference on the same fires, calendar = outcome-table sessions
cal = pd.DatetimeIndex(sorted(O.d.unique()))
ev, pr = t14.build_events(F, cal)
ref = ev.groupby(["window", "bucket", "side"]).size().rename("py")
got = res["L1"].set_index(["win", "bucket", "side"])["events"].rename("sql")
cmp = pd.concat([ref, got], axis=1)
print(cmp.to_string())
print("L1 match:", bool((cmp.py == cmp.sql).all()))

# L3 total r5 sum vs python
Oi = O.set_index(["ticker", "d"])
oe = Oi.reindex(pd.MultiIndex.from_arrays([ev.ticker, ev.d]))
oe.index = ev.index
sg = t14.signed(oe, ev.side.values)
py = pd.concat([ev, sg], axis=1).groupby(["window", "bucket"])[["r5", "close30_vol"]].sum()
l3 = res["L3"].groupby(["win", "bucket"])[["sum_r5", "sum_c30_vol"]].sum()
print(pd.concat([py, l3.rename_axis(["window", "bucket"])], axis=1).round(6).to_string())

# classes for k2 W5
pc = ev[(ev.window == "W5") & (ev.bucket == "k2")].pair_class.value_counts()
sc = res["L3"][(res["L3"].win == "W5") & (res["L3"].bucket == "k2")].groupby("cls").n_r5.sum()
print("k2 W5 classes py:", pc.to_dict(), " sql (events with r5):", sc.to_dict())
print(res["L2"].head(8).to_string())
print(res["L4"].head(3).to_string())
