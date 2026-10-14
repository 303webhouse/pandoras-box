"""Crypto replay (R-IV.999): HECTOR (TRAPPED_SHORTS) and PERSEPHONE (TWO_CLOSE_VOLUME) as the hub's
crypto path codes them, on BTC-USD and ETH-USD daily bars from BUILD's bars1d (source A).
RUN-OFF check feeding the 10-30 crypto table: a pass promotes nothing (freeze to 2027-03-31); results
go to QUERY for independent re-computation before they are cited.

Declarations (stamped 2026-10-14 02:12:40 UTC before this file existed):
  lab\\crypto-replay\\01-DECLARATIONS.md  25ee7add...   scope 00-SCOPE-R-IV.995.md  aaed8c0c...
  lab\\crypto-replay\\03-REPORTING-ADDENDUM-R-IV.1003.md  1dbc36f7...  (pass count vs chance; reporting only)

The crypto path (cta_scanner.analyze_ticker_cta -> analyze_ticker_cta_from_df): trailing 365-day window
(period="1y"), calculate_cta_indicators on it, candidates in code order GOLDEN_TOUCH(100),
TWO_CLOSE_VOLUME(80), PULLBACK_ENTRY(50), TRAPPED_SHORTS(80; 100 if RVOL>2 and ADX>30); NO death-cross
strip; allow_shorts off; emitted = the highest priority, ties to the first in code order.
Mode D = the type's check fires; mode P = the type is the emitted (top-priority) candidate.

Usage: python scripts/lab/crypto_replay.py run <btc.parquet> <eth.parquet> <out_dir>
       python scripts/lab/crypto_replay.py selftest
"""
import hashlib
import json
import logging
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "backend")))
logging.disable(logging.CRITICAL)

LABEL = "completed bars only; live scanner fires on the unfinished bar."
STATUS = "RUN-OFF check (10-30 crypto table); a pass promotes nothing; freeze to 2027-03-31; QUERY re-computes before citation"
HS = (3, 10)
BEAR_YEARS = {2018, 2022}
WINDOW_DAYS = 365
MIN_ROWS = 150
FLOOR_N, FLOOR_DATES = 30, 20
TYPES = ("TRAPPED_SHORTS", "TWO_CLOSE_VOLUME")
NAMES = {"TRAPPED_SHORTS": "HECTOR", "TWO_CLOSE_VOLUME": "PERSEPHONE"}


def hac_t(x, lags):
    x = np.asarray(x, float)
    n = len(x)
    if n < 3:
        return None
    e = x - x.mean()
    lrv = e @ e / n
    for lag in range(1, min(lags, n - 1) + 1):
        lrv += 2 * (1 - lag / (lags + 1)) * (e[lag:] @ e[:-lag]) / n
    return float(x.mean() / np.sqrt(lrv / n)) if lrv > 0 else None


def plain_t(x):
    x = np.asarray(x, float)
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) >= 3 and x.std(ddof=1) > 0 else None


CLOCK = "UTC calendar day (bars1d DatetimeIndex, tz=UTC, stamped 00:00); converted explicitly"


def load_bars(path, today_utc=None):
    """bars1d Parquet (F-README e72ea5b9...): Open/High/Low/Close/Volume (+ ticker), one bar per UTC
    calendar day, 7 days a week. The DatetimeIndex is converted explicitly to its UTC date (no date
    column exists). Completed bars only: any bar dated on or after today's UTC date is dropped as
    unfinished. Returns (bars, n_unfinished_dropped)."""
    b = pd.read_parquet(path)
    if not isinstance(b.index, pd.DatetimeIndex):
        for c in ("Date", "date", "Datetime"):
            if c in b.columns:
                b = b.set_index(c)
                break
    idx = pd.DatetimeIndex(b.index)
    idx = (idx.tz_convert("UTC").tz_localize(None) if idx.tz is not None else idx).normalize()
    b = b.set_axis(idx)[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    b = b[~b.index.duplicated(keep="last")].sort_index().dropna(subset=["Open", "Close"])
    if today_utc is None:
        today_utc = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    unfinished = b.index >= today_utc
    return b[~unfinished], int(unfinished.sum())


def candidates(ind, ticker, checks):
    """The crypto path's candidate list on one indicator frame, in code order: (type, priority)."""
    out = []
    for fn in checks:
        s = fn(ind, ticker)
        if s:
            out.append((s["signal_type"], float(s.get("priority", 0))))
    return out


def emitted(cands):
    """Python max keeps the FIRST maximum: ties go to the earlier candidate in code order."""
    return max(cands, key=lambda c: c[1])[0] if cands else None


def fires(bars, ticker, checks=None, calc=None):
    """Per evaluable day t: {type: (fired_D, fired_P)}."""
    if checks is None or calc is None:
        from scanners import cta_scanner as cta
        checks = checks or (cta.check_golden_touch, cta.check_two_close_volume, cta.check_pullback_entry,
                            cta.check_trapped_shorts)
        calc = calc or cta.calculate_cta_indicators
    rows = []
    for t in bars.index:
        w = bars[(bars.index > t - pd.Timedelta(days=WINDOW_DAYS)) & (bars.index <= t)]
        if len(w) < MIN_ROWS:
            continue
        ind = calc(w.copy())
        c = candidates(ind, ticker, checks)
        top = emitted(c)
        kinds = {k for k, _ in c}
        rows.append({"t": t, **{f"D_{k}": k in kinds for k in TYPES}, **{f"P_{k}": top == k for k in TYPES}})
    return pd.DataFrame(rows)


def outcomes(bars):
    """Per day t: r_h = Close(t+h) / Open(t+1) - 1, and Close(t) > SMA200 (simple, last 200 Closes)."""
    o, c = bars.Open, bars.Close
    out = pd.DataFrame(index=bars.index)
    for h in HS:
        out[f"r{h}"] = c.shift(-h) / o.shift(-1) - 1
    out["above200"] = c > c.rolling(200).mean()
    return out


def split_of(t):
    return "bear" if t.year in BEAR_YEARS else "bull"


def cells(F, O, asset):
    F = F.set_index("t").join(O, how="left")
    F["split"] = [split_of(t) for t in F.index]
    rows = []
    for h in HS:
        r = f"r{h}"
        ev = F.dropna(subset=[r])
        for sp in ("bear", "bull", "ALL"):
            pool = ev if sp == "ALL" else ev[ev.split == sp]
            b1 = float(pool[r].mean()) if len(pool) else float("nan")
            b2 = float(pool[pool.above200][r].mean()) if pool.above200.any() else float("nan")
            for ty in TYPES:
                for mode in ("P", "D"):
                    fr = pool[pool[f"{mode}_{ty}"]]
                    rec = {"name": NAMES[ty], "type": ty, "mode": mode, "asset": asset, "h": h, "split": sp,
                           "n_fires": int(len(fr)), "n_dates": int(fr.index.nunique()),
                           "mean_return": round(float(fr[r].mean()), 6) if len(fr) else None,
                           "B1_always_long": round(b1, 6), "B2_close_gt_sma200": round(b2, 6),
                           "label": LABEL, "status": STATUS, "is_cell": sp != "ALL"}
                    below = len(fr) < FLOOR_N or fr.index.nunique() < FLOOR_DATES
                    rec["below_floor"] = bool(below)
                    for bn, bv in (("B1", b1), ("B2", b2)):
                        if below or np.isnan(bv):
                            rec.update({f"diff_{bn}": None, f"t_hac_{bn}": None, f"t_plain_{bn}": None})
                            continue
                        x = (fr[r] - bv).to_numpy()
                        th, tp = hac_t(x, h - 1), plain_t(x)
                        rec.update({f"diff_{bn}": round(float(x.mean()), 6),
                                    f"t_hac_{bn}": round(th, 3) if th is not None else None,
                                    f"t_plain_{bn}": round(tp, 3) if tp is not None else None})
                    rows.append(rec)
    return rows


def verdicts(C):
    """PASS for (type, mode, asset, h) only if the BEAR cell beats BOTH baselines: diff > 0 and HAC t >= 2."""
    out = []
    for (ty, mode, asset, h), g in C[C.split == "bear"].groupby(["type", "mode", "asset", "h"]):
        r = g.iloc[0]
        if r.below_floor:
            v = "below floor - cannot pass"
        else:
            ok = all((r[f"diff_{b}"] is not None and r[f"diff_{b}"] > 0 and r[f"t_hac_{b}"] is not None
                      and r[f"t_hac_{b}"] >= 2.0) for b in ("B1", "B2"))
            v = "PASS (run-off fact only)" if ok else "no pass"
        out.append({"name": NAMES[ty], "type": ty, "mode": mode, "asset": asset, "h": h, "verdict": v,
                    "label": LABEL, "status": STATUS})
    return pd.DataFrame(out)


P_ONE_SIDED_T2 = 0.0228          # P(Z >= 2), one-sided: the chance bound for one cell's pass (addendum)


def pass_summary(V):
    """Addendum R-IV.1003(b): k passes of the eligible (bear) cells, the chance bound and the label."""
    from math import comb
    n = int(len(V))
    k = int(V.verdict.str.startswith("PASS").sum())
    p = P_ONE_SIDED_T2
    tail = sum(comb(n, j) * p ** j * (1 - p) ** (n - j) for j in range(k, n + 1)) if n else None
    label = "no pass" if k == 0 else "consistent with chance (unless QUERY's re-computation says otherwise)" \
        if k == 1 else "reported without a label; SPINE reads the count against the bound"
    return {"passes": k, "eligible_cells": n, "total_cells": 2 * n,
            "written": f"{k} of {n} eligible ({2 * n} cells)",
            "chance_expected_upper_bound": round(n * p, 3),
            "p_at_least_k_binomial": round(float(tail), 4) if tail is not None else None,
            "binomial_note": "assumes independent cells; the cells are correlated, so this understates the tail",
            "label": label}


def run(btc_path, eth_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    meta = {"label": LABEL, "status": STATUS, "inputs": {}}
    allrows = []
    for asset, path in (("BTC-USD", btc_path), ("ETH-USD", eth_path)):
        meta["inputs"][asset] = {"file": path, "sha256": hashlib.sha256(open(path, "rb").read()).hexdigest()}
        bars, n_unf = load_bars(path)
        meta["inputs"][asset].update({"clock": CLOCK, "unfinished_bars_dropped": n_unf,
                                      "first": str(bars.index.min().date()), "last": str(bars.index.max().date()),
                                      "rows": int(len(bars))})
        F = fires(bars, asset)
        meta["inputs"][asset]["first_evaluable"] = str(F.t.min().date()) if len(F) else None
        allrows += cells(F, outcomes(bars), asset)
    C = pd.DataFrame(allrows)
    V = verdicts(C)
    comps = int(C[C.is_cell & ~C.below_floor].shape[0] * 2)
    cc = C[C.is_cell]
    crosses = int(sum((pd.to_numeric(cc[f"t_hac_{b}"], errors="coerce").abs() >= 2).sum() for b in ("B1", "B2")))
    meta.update({"cells": int(C.is_cell.sum()), "comparisons_sufficient": comps, "abs_hac_t_ge_2": crosses,
                 "chance_expected": round(0.0455 * comps, 1), "pass_summary": pass_summary(V)})
    C.to_csv(os.path.join(out_dir, "cells.csv"), index=False)
    V.to_csv(os.path.join(out_dir, "verdicts.csv"), index=False)
    json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w"), indent=1, default=str)
    print(json.dumps(meta, indent=1, default=str))
    print(V.to_string(index=False))


# ── self-test (synthetic bars and stubbed checks; no real data) ─────────────────────────────────
def selftest():
    import tempfile
    rng = np.random.default_rng(3)
    checks = {}
    # tie-break and no-strip: stubbed candidate checks
    def mk(ty, pr):
        return lambda ind, tk: {"signal_type": ty, "priority": pr}
    none = lambda ind, tk: None  # noqa: E731
    c = candidates(None, "BTC", (none, mk("TWO_CLOSE_VOLUME", 80), none, mk("TRAPPED_SHORTS", 80)))
    checks["tie 80/80: TWO_CLOSE_VOLUME emitted (first in code order)"] = emitted(c) == "TWO_CLOSE_VOLUME"
    c = candidates(None, "BTC", (mk("GOLDEN_TOUCH", 100), none, none, mk("TRAPPED_SHORTS", 100)))
    checks["tie 100/100: GOLDEN_TOUCH emitted, TRAPPED_SHORTS not"] = emitted(c) == "GOLDEN_TOUCH"
    c = candidates(None, "BTC", (none, mk("TWO_CLOSE_VOLUME", 80), none, mk("TRAPPED_SHORTS", 100)))
    checks["TRAPPED_SHORTS at 100 beats TWO_CLOSE_VOLUME at 80"] = emitted(c) == "TRAPPED_SHORTS"
    # synthetic daily bars (7-day calendar), 2017-01-01 .. 2023-12-31
    idx = pd.date_range("2017-01-01", "2023-12-31", freq="D")
    px = 1000 * np.exp(np.cumsum(rng.normal(0.0005, 0.03, len(idx))))
    bars = pd.DataFrame({"Open": px * (1 + rng.normal(0, 0.002, len(idx))), "High": px * 1.02,
                         "Low": px * 0.98, "Close": px, "Volume": rng.uniform(1e6, 2e6, len(idx))}, index=idx)
    # stubbed detector: TRAPPED_SHORTS fires every 7th day, TWO_CLOSE_VOLUME every 11th (to test plumbing)
    def ts(ind, tk):
        return {"signal_type": "TRAPPED_SHORTS", "priority": 80} if ind.index[-1].dayofyear % 7 == 0 else None
    def tc(ind, tk):
        return {"signal_type": "TWO_CLOSE_VOLUME", "priority": 80} if ind.index[-1].dayofyear % 11 == 0 else None
    F = fires(bars, "BTC-USD", checks=(none, tc, none, ts), calc=lambda w: w)
    checks["window: first evaluable day = 150th calendar day (2017-05-30)"] = F.t.min() == pd.Timestamp("2017-05-30")
    both = F[F.D_TRAPPED_SHORTS & F.D_TWO_CLOSE_VOLUME]
    checks["when both fire, D counts both but P gives it to TWO_CLOSE_VOLUME"] = \
        bool(len(both)) and bool(both.P_TWO_CLOSE_VOLUME.all()) and not bool(both.P_TRAPPED_SHORTS.any())
    O = outcomes(bars)
    t0 = pd.Timestamp("2018-03-01")
    exp = bars.Close.loc[t0 + pd.Timedelta(days=3)] / bars.Open.loc[t0 + pd.Timedelta(days=1)] - 1
    checks["r3 = Close(t+3) / Open(t+1) - 1"] = abs(O.loc[t0, "r3"] - exp) < 1e-12
    checks["SMA200 baseline flag uses the last 200 closes"] = \
        bool(O.loc[t0, "above200"] == (bars.Close.loc[t0] > bars.Close.loc[:t0].tail(200).mean()))
    C = pd.DataFrame(cells(F, O, "BTC-USD"))
    checks["32 cells per asset? -> 16 per asset (2 types x 2 modes x 2 h x 2 splits)"] = int(C.is_cell.sum()) == 16
    checks["every row carries the completed-bars label and run-off status"] = \
        bool((C.label == LABEL).all() and (C.status == STATUS).all())
    bear = C[(C.split == "bear") & (C.type == "TRAPPED_SHORTS") & (C["mode"] == "D") & (C.h == 3)].iloc[0]
    checks["bear split = 2018 + 2022 only"] = bear.n_fires == int(
        F[F.t.dt.year.isin([2018, 2022]) & F.D_TRAPPED_SHORTS].shape[0])
    V = verdicts(C)
    checks["random-walk stub produces no PASS (null data)"] = not V.verdict.str.startswith("PASS").any()
    tiny = C.copy()
    tiny.loc[tiny.split == "bear", "below_floor"] = True
    checks["below floor -> 'cannot pass'"] = (verdicts(tiny).verdict == "below floor - cannot pass").all()
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "BTC-USD.parquet")
        bars.assign(ticker="BTC-USD").set_axis(bars.index.tz_localize("UTC")).to_parquet(p)   # tz=UTC index
        lb, nu = load_bars(p, today_utc=pd.Timestamp("2023-12-31"))
        checks["load_bars reads the bars1d layout (tz-aware UTC index + OHLCV + ticker)"] = \
            list(lb.columns) == ["Open", "High", "Low", "Close", "Volume"] and lb.index.tz is None
        checks["unfinished bar (today's UTC day) dropped and counted"] = \
            nu == 1 and lb.index.max() == pd.Timestamp("2023-12-30")
    ps = pass_summary(V)
    checks["addendum: 16 eligible of 32 cells per 2 assets; bound 16 x 0.0228"] = \
        pass_summary(pd.concat([V, V.assign(asset="ETH-USD")]))["chance_expected_upper_bound"] == round(16 * 0.0228, 3)
    checks["addendum: k = 0 -> 'no pass'"] = ps["label"] == "no pass" and ps["passes"] == 0
    one = pd.concat([V, V.assign(asset="ETH-USD")]).reset_index(drop=True)
    one.loc[0, "verdict"] = "PASS (run-off fact only)"
    s1 = pass_summary(one)
    checks["addendum: k = 1 -> 'consistent with chance'"] = s1["passes"] == 1 and s1["label"].startswith("consistent with chance")
    two = one.copy()
    two.loc[1, "verdict"] = "PASS (run-off fact only)"
    s2 = pass_summary(two)
    checks["addendum: k = 2 -> unlabelled, with P(X >= 2) reported"] = s2["passes"] == 2 and s2["label"].startswith(
        "reported without a label") and 0 < s2["p_at_least_k_binomial"] < 0.1
    for k, v in checks.items():
        print(("PASS " if v else "FAIL ") + k)
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    if sys.argv[1] == "selftest":
        sys.exit(selftest())
    run(*sys.argv[2:5])
