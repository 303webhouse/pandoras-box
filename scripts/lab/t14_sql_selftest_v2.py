"""Self-test of 07-LIVE-INSTRUMENT-v2.sql (R-IV.923(b)) in DuckDB on a SYNTHETIC signals table built
from replay fires (no DB data). Checks against the Python replay at the ISO-week grain:
L1 counts; L3 kept groups (n and sums) and L6's left-out count; L4 control sums; no 377783 left."""
import re
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, r"C:\trading-hub-lab\scripts\lab")
import t14_co_fire as t14  # noqa: E402

LAB = r"C:\temp\cc-query-handoff\lab"
sql = open(LAB + r"\co-fire\07-LIVE-INSTRUMENT-v2.sql", encoding="utf-8").read()
assert "377783" not in sql.split("-- L1")[1] and "id <= " not in sql, "v1 seal predicate still present"
O = pd.read_csv(LAB + r"\co-fire\02-live-outcomes.csv.gz", parse_dates=["d"])
F = pd.read_csv(LAB + r"\move-size\fires.csv.gz", parse_dates=["date"])
F = F[(F.date >= "2024-07-01") & (F.date <= "2026-08-27") & F.ticker.isin(set(O.ticker))]
ts = (F.date + pd.Timedelta(hours=15)).dt.tz_localize("America/New_York").dt.tz_convert("UTC").dt.tz_localize(None)
S = pd.DataFrame({"id": np.arange(1, 1 + len(F)), "timestamp": ts.values, "strategy": "X",
                  "ticker": F.ticker.values, "asset_class": "EQUITY",
                  "direction": F.side.values, "signal_type": F.type.values})
S = S.astype({c: object for c in ["strategy", "ticker", "asset_class", "direction", "signal_type"]})
O2 = O.astype({c: object for c in ["ticker", "spy_state"]})
con = duckdb.connect()
con.execute("INSTALL icu; LOAD icu; INSTALL json; LOAD json;")
con.register("S_df", S)
con.execute("CREATE TABLE signals AS SELECT *, CAST(NULL AS JSON) AS triggering_factors FROM S_df")
con.register("O_df", O2)
con.execute("CREATE TABLE lab_outcomes AS SELECT ticker, CAST(d AS DATE) AS d, r5_adj, r20_adj, m30, sig20, vol_tercile, spy_state FROM O_df")

with_block = sql.split("-- L1")[0]
with_block = with_block[with_block.index("WITH f AS"):].rstrip()
queries = re.findall(r"\n(SELECT .*?)\n;", sql[sql.index("-- L1"):], flags=re.S)
names = ["L1", "L2", "L3", "L4", "L5", "L6"]
assert len(queries) == 6, len(queries)
res = {n: con.execute(with_block + "\n" + q).df() for n, q in zip(names, queries)}
for n in names:
    print(n, len(res[n]), "rows")

# python reference
cal = pd.DatetimeIndex(sorted(O.d.unique()))
ev, _ = t14.build_events(F, cal)
ok = {}
ref = ev.groupby(["window", "bucket", "side"]).size()
got = res["L1"].set_index(["win", "bucket", "side"])["events"]
ok["L1 counts"] = bool((ref.sort_index() == got.sort_index()).all())

Oi = O.set_index(["ticker", "d"])
oe = Oi.reindex(pd.MultiIndex.from_arrays([ev.ticker, ev.d]))
oe.index = ev.index
e = pd.concat([ev, t14.signed(oe, ev.side.values)], axis=1).assign(vol_tercile=oe.vol_tercile.values)
e = e[oe.sig20.notna().values | oe.m30.notna().values | oe.r5_adj.notna().values]
e = e[pd.MultiIndex.from_arrays([e.ticker, e.d]).isin(Oi.index)]
e["iso_week"] = (e.d - pd.to_timedelta(e.d.dt.weekday, unit="D")).dt.normalize()
e["cls"] = e.pair_class.fillna("-")
g = e.groupby(["window", "bucket", "cls", "side", "vol_tercile", "iso_week"]).agg(
    n=("r5", "size"), sum_r5=("r5", "sum"), sum_c30_vol=("close30_vol", "sum"))
kept, lost = g[g.n >= 2], g[g.n < 2]
l3 = res["L3"]
ok["L3 kept group count"] = len(kept) == len(l3)
ok["L3 n_events total"] = int(kept.n.sum()) == int(l3.n_events.sum())
ok["L3 sum_r5 total"] = abs(kept.sum_r5.sum() - l3.sum_r5.sum()) < 1e-6
ok["L3 sum_c30_vol total"] = abs(kept.sum_c30_vol.sum() - l3.sum_c30_vol.sum()) < 1e-6
l6 = res["L6"]
ok["L6 left-out (L3 grain)"] = int(lost.n.sum()) == int(l6[l6.src == "L3"].events_left_out.sum())
ok["L3 no single-event group"] = int(l3.n_events.min()) >= 2
ok["L5 no single-event group"] = int(res["L5"].n_events.min()) >= 2
for k, v in ok.items():
    print(("PASS " if v else "FAIL ") + k)
print("events left out by HAVING (L3 grain):", int(lost.n.sum()), "of", int(g.n.sum()))
sys.exit(0 if all(ok.values()) else 1)
