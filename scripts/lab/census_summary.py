"""Summarise expected fires by detector type, side and market state (census amendments 5-6).

Daily types take the state of the evaluated session; intraday families (hg1h, scout15m) take the
PRIOR completed session's state. Ticker-days are the unit. Both regime rules are reported:
state_stack (C1, R-IV.838(e)) and state_adx (continuity).

Usage: python scripts/lab/census_summary.py <census_dir> <fires.csv> [<fires.csv> ...] <out.csv>
"""
import os
import sys

import pandas as pd

INTRADAY = {"hg1h", "scout15m"}


def summarise(census_dir, fire_files, out_csv):
    s = pd.read_csv(os.path.join(census_dir, "spy_states.csv"), index_col=0)
    s.index = s.index.astype(str)
    prior = pd.Series(list(s.index[:-1]), index=list(s.index[1:]))
    e = pd.concat([pd.read_csv(f) for f in fire_files], ignore_index=True)
    e["et_date"] = pd.to_datetime(e["et_date"]).dt.date.astype(str)
    e = e.drop_duplicates(["ticker", "et_date", "detector_type", "direction"])
    state_day = e["et_date"].where(~e["family"].isin(INTRADAY), e["et_date"].map(prior))
    e["stack"] = state_day.map(s["state_stack"])
    e["adx"] = state_day.map(s["state_adx"])
    e["stack_dir"] = state_day.map(s["stack"])
    g = e.groupby(["detector_type", "direction"])
    out = pd.DataFrame({"ticker_days": g.size(), "distinct_dates": g["et_date"].nunique(),
                        "first": g["et_date"].min(), "last": g["et_date"].max()})
    for col in ("stack", "adx"):
        for st in ("trend", "range", "transition"):
            out[f"{col}_{st}"] = g[col].apply(lambda x, st=st: int((x == st).sum()))
    out["trend_bear_stack"] = g.apply(lambda x: int(((x["stack"] == "trend") & (x["stack_dir"] == "bear")).sum()))
    out["unmapped_state"] = g["stack"].apply(lambda x: int(x.isna().sum()))
    out.to_csv(out_csv)
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    print(summarise(a[0], a[1:-1], a[-1]).to_string())
