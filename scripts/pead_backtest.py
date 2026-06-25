r"""PEAD Stage-1 backtest (L1b factor #3) — OFFLINE research, no DB.

Surprise = seasonal-random-walk SUE (Bernard-Thomas / Foster-Olsen-Shevlin):
  SUE_q = (actual_q - actual_{q-4}) / stdev(past seasonal diffs, trailing K)
computed POINT-IN-TIME (only the firm's own prior earnings). Chosen because UW
analyst estimates (street_mean_est) only reach ~2022 — too shallow for the
3-regime Stage-1 bar; actual_eps reaches ~1997-2003, so a time-series SUE keeps
the full deep-history test (Nick's call 2026-06-24).

Entry T0 = first close AFTER the announcement gap (PEAD = the UNDER-reaction):
  postmarket -> T0 = close of report_date+1 session
  premarket  -> T0 = close of report_date session
  null/unknown -> default postmarket (logged; flag if >10%)
Drift measured T0 -> T0+k (k=20/40/60 trading days), adjusted closes.

Deciles: point-in-time expanding cross-section (rank vs all SUEs observed before
this event) — NEVER full-sample (look-ahead). Core tests mirror momentum XS:
  1. D10-D1 decile spread per horizon (beta-stripped drift edge).
  2. Long-only D10 vs equal-weight-all and vs SPY matched windows (alpha?).
Sub-period robustness (2004-09 / 2010-19 / 2020-26) + concentration (D10 vs D9).

Run via:  railway run --service pandoras-box python C:\temp\pead_backtest.py [universe_limit]
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from bisect import bisect_left, insort
from datetime import date

import httpx

KEY = os.environ.get("UW_API_KEY", "")
BASE = "https://api.unusualwhales.com"
H = {"Authorization": "Bearer " + KEY, "Accept": "application/json"}
CACHE = r"C:\temp\pead_cache"
os.makedirs(CACHE, exist_ok=True)

TODAY = "2026-06-25"
HORIZONS = [20, 40, 60]
SUE_LAG = 4               # seasonal (year-ago) quarter
SUE_WIN = 8              # trailing seasonal diffs for sigma (Bernard-Thomas)
SUE_MIN = 6             # min prior seasonal diffs to compute a stable sigma
MIN_XS = 200           # min prior SUEs before assigning a point-in-time decile
REGIMES = [("2004-2009", "2004-01-01", "2009-12-31"),
           ("2010-2019", "2010-01-01", "2019-12-31"),
           ("2020-2026", "2020-01-01", "2026-12-31")]


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ── universe ─────────────────────────────────────────────────────────────────
_FALLBACK = ("AAPL MSFT NVDA AMZN GOOGL META TSLA JPM XOM JNJ V PG MA HD CVX "
             "ABBV KO PEP COST WMT BAC CRM MRK ADBE NFLX AMD DIS TMO CSCO ACN "
             "ABT WFC MCD DHR INTC TXN QCOM PM CAT UNH LIN VZ NKE NEE BMY UPS "
             "HON RTX LOW INTU GS AMGN SBUX BLK DE PLD MDT GE BA MMM CVS").split()


def get_universe(limit=None):
    cf = os.path.join(CACHE, "universe.json")
    if os.path.exists(cf):
        u = json.load(open(cf))
    else:
        u = None
        # primary: datasets GitHub S&P 500 constituents CSV (no lxml dep)
        try:
            with httpx.Client(timeout=30) as c:
                r = c.get("https://raw.githubusercontent.com/datasets/"
                          "s-and-p-500-companies/main/data/constituents.csv")
            if r.status_code == 200:
                lines = r.text.strip().splitlines()[1:]
                syms = [ln.split(",")[0].replace(".", "-").strip() for ln in lines if ln]
                if len(syms) > 100:
                    u = syms
        except Exception as e:
            print("  universe: CSV pull failed (%s)" % type(e).__name__)
        if not u:                       # secondary: Wikipedia (needs lxml)
            try:
                import pandas as pd
                tbls = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
                syms = [str(s).replace(".", "-") for s in tbls[0]["Symbol"].tolist()]
                if len(syms) > 100:
                    u = syms
            except Exception as e:
                print("  universe: Wikipedia pull failed (%s)" % type(e).__name__)
        if not u:
            print("  universe: BOTH sources failed -> fallback (NOT breadth-sufficient)")
            u = _FALLBACK
        json.dump(u, open(cf, "w"))
    print(f"  universe: {len(u)} names (source={'sp500' if len(u) > 100 else 'fallback'})")
    return u[:limit] if limit else u


# ── data fetch (cached) ──────────────────────────────────────────────────────
def fetch_earnings(t):
    cf = os.path.join(CACHE, f"earn_{t}.json")
    if os.path.exists(cf):
        return json.load(open(cf))
    for attempt in range(3):
        try:
            with httpx.Client(timeout=30) as c:
                r = c.get(f"{BASE}/api/earnings/{t}", headers=H)
            if r.status_code == 200:
                rows = r.json().get("data", [])
                json.dump(rows, open(cf, "w"))
                return rows
            if r.status_code == 429:
                time.sleep(1.5)
                continue
            return []
        except Exception:
            time.sleep(1.0)
    return []


def fetch_prices(t):
    cf = os.path.join(CACHE, f"px_{t}.json")
    if os.path.exists(cf):
        return json.load(open(cf))
    import yfinance as yf
    try:
        df = yf.download(t, start="2000-01-01", auto_adjust=True, progress=False)
    except Exception:
        df = None
    out = {}
    if df is not None and len(df):
        col = None
        for c in df.columns:
            name = c[0] if isinstance(c, tuple) else c
            if name == "Close":
                col = c
                break
        if col is not None:
            for idx in df.index:
                v = f(df.loc[idx, col])
                if v is not None and v == v:
                    out[idx.strftime("%Y-%m-%d")] = v
    json.dump(out, open(cf, "w"))
    return out


# ── SUE (seasonal random walk, point-in-time per name) ───────────────────────
def name_events(t):
    """-> list of {date, report_time, sue} for one name (point-in-time SUE)."""
    rows = fetch_earnings(t)
    hist = [(r["report_date"], (r.get("report_time") or "null"), f(r.get("actual_eps")))
            for r in rows
            if r.get("report_date") and r["report_date"] <= TODAY and f(r.get("actual_eps")) is not None]
    hist.sort(key=lambda x: x[0])
    eps = [h[2] for h in hist]
    sds = []                      # seasonal diffs in chronological order
    out = []
    for i in range(len(hist)):
        if i < SUE_LAG:
            continue
        sd = eps[i] - eps[i - SUE_LAG]
        past = sds[-SUE_WIN:] if len(sds) >= SUE_MIN else None
        if past:
            mu = sum(past) / len(past)
            var = sum((x - mu) ** 2 for x in past) / (len(past) - 1) if len(past) > 1 else 0.0
            sigma = math.sqrt(var)
            if sigma > 1e-9:
                out.append({"date": hist[i][0], "report_time": hist[i][1], "sue": sd / sigma})
        sds.append(sd)
    return out


# ── T0 + forward drift ───────────────────────────────────────────────────────
def t0_index(dates_sorted, report_date, report_time):
    """Index in dates_sorted of the entry close per the report_time rule."""
    p0 = bisect_left(dates_sorted, report_date)   # first session >= report_date
    if p0 >= len(dates_sorted):
        return None
    rt = report_time if report_time in ("premarket", "postmarket") else "postmarket"
    if rt == "postmarket":
        # reaction is the next session after report_date
        if dates_sorted[p0] == report_date:
            return p0 + 1
        return p0                                 # report_date not a session -> next session is the reaction
    return p0                                     # premarket: reaction is report_date session


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    print("=" * 72)
    print(f"PEAD STAGE-1 — seasonal-random-walk SUE (lag={SUE_LAG} win={SUE_WIN}) "
          f"| horizons={HORIZONS} | UW_KEY={'Y' if KEY else 'N'}")
    print("=" * 72)

    universe = get_universe(limit)
    spy = fetch_prices("SPY")
    spy_dates = sorted(spy.keys())

    events = []
    null_rt = 0
    fetched = 0
    for i, t in enumerate(universe):
        evs = name_events(t)
        if not evs:
            continue
        px = fetch_prices(t)
        if len(px) < 300:
            continue
        pdates = sorted(px.keys())
        fetched += 1
        for e in evs:
            if e["report_time"] not in ("premarket", "postmarket"):
                null_rt += 1
            ti = t0_index(pdates, e["date"], e["report_time"])
            if ti is None or ti >= len(pdates):
                continue
            t0d = pdates[ti]
            c0 = px[t0d]
            rec = {"ticker": t, "t0": t0d, "sue": e["sue"]}
            ok = False
            for k in HORIZONS:
                j = ti + k
                if j < len(pdates):
                    rec[f"r{k}"] = px[pdates[j]] / c0 - 1.0
                    # SPY matched window (calendar dates t0 -> t0+k)
                    sp0 = spy.get(t0d) or _nearest(spy, spy_dates, t0d)
                    sp1 = spy.get(pdates[j]) or _nearest(spy, spy_dates, pdates[j])
                    rec[f"s{k}"] = (sp1 / sp0 - 1.0) if (sp0 and sp1) else None
                    ok = True
                else:
                    rec[f"r{k}"] = None
                    rec[f"s{k}"] = None
            if ok:
                events.append(rec)
        if (i + 1) % 50 == 0:
            print(f"  ...{i+1}/{len(universe)} names, {len(events)} events so far")

    print(f"\nnames with usable data: {fetched}/{len(universe)}  | events: {len(events)}")
    npct = 100.0 * null_rt / max(len(events), 1)
    print(f"null/unknown report_time (defaulted postmarket): {null_rt} ({npct:.1f}%)"
          + ("  <<< >10% FLAG" if npct > 10 else ""))

    # point-in-time expanding deciles
    events.sort(key=lambda e: e["t0"])
    seen = []
    for e in events:
        s = e["sue"]
        if len(seen) >= MIN_XS:
            rank = bisect_left(seen, s)
            pct = rank / len(seen)
            e["decile"] = min(10, int(pct * 10) + 1)
        else:
            e["decile"] = None
        insort(seen, s)
    graded = [e for e in events if e["decile"] is not None]
    print(f"events with point-in-time decile: {len(graded)} "
          f"(first {MIN_XS} dropped as XS warmup)\n")

    report(graded)
    json.dump({"n_events": len(graded), "n_names": fetched},
              open(r"C:\temp\pead_results.json", "w"))


def _nearest(m, dates_sorted, d):
    i = bisect_left(dates_sorted, d)
    if i < len(dates_sorted) and dates_sorted[i] == d:
        return m[dates_sorted[i]]
    if i > 0:
        return m[dates_sorted[i - 1]]
    return None


def _stats(xs):
    n = len(xs)
    if n == 0:
        return None
    mu = sum(xs) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n else 0.0
    t = mu / se if se else 0.0
    return {"n": n, "mean": mu, "t": t, "win": 100.0 * sum(1 for x in xs if x > 0) / n}


def report(graded):
    for k in HORIZONS:
        col = f"r{k}"
        ev = [e for e in graded if e.get(col) is not None]
        print("=" * 72)
        print(f"HORIZON k={k} trading days   (n={len(ev)} events)")
        print("-" * 72)
        print("decile |   n   | mean drift% |   t   | hit% ")
        dec_means = {}
        for d in range(1, 11):
            xs = [e[col] for e in ev if e["decile"] == d]
            st = _stats(xs)
            if st:
                dec_means[d] = st["mean"]
                print(f"  D{d:<2}  | {st['n']:5d} | {100*st['mean']:+8.2f}   | {st['t']:+5.2f} | {st['win']:.1f}")
        # D10 - D1 spread
        d10 = [e[col] for e in ev if e["decile"] == 10]
        d1 = [e[col] for e in ev if e["decile"] == 1]
        s10, s1 = _stats(d10), _stats(d1)
        if s10 and s1:
            spread = s10["mean"] - s1["mean"]
            # two-sample t (unequal var, Welch)
            import math as _m
            v10 = (_m.sqrt(sum((x-s10['mean'])**2 for x in d10)/(len(d10)-1)))**2/len(d10)
            v1 = (_m.sqrt(sum((x-s1['mean'])**2 for x in d1)/(len(d1)-1)))**2/len(d1)
            tt = spread / _m.sqrt(v10 + v1) if (v10 + v1) > 0 else 0.0
            print("-" * 72)
            print(f"  D10-D1 SPREAD: {100*spread:+.2f}%  (t={tt:.2f})   "
                  f"D10 mean {100*s10['mean']:+.2f}% / D1 mean {100*s1['mean']:+.2f}%")
            # concentration D10 vs D9
            if 9 in dec_means:
                print(f"  concentration: D10 {100*dec_means[10]:+.2f}% vs D9 {100*dec_means[9]:+.2f}% "
                      f"(monotonic={'Y' if dec_means.get(10,0)>=dec_means.get(9,-9)>=dec_means.get(8,-9) else 'N'})")
        # long-only D10 vs EW-all vs SPY-matched
        ew = _stats([e[col] for e in ev])
        spy_d10 = [e[f"s{k}"] for e in ev if e["decile"] == 10 and e.get(f"s{k}") is not None]
        spy_st = _stats(spy_d10)
        if s10 and ew:
            print(f"  LONG-ONLY D10: mean {100*s10['mean']:+.2f}%  vs EW-all {100*ew['mean']:+.2f}%  "
                  f"vs SPY-matched {100*spy_st['mean']:+.2f}%"
                  + (f"  -> alpha {100*(s10['mean']-spy_st['mean']):+.2f}%" if spy_st else ""))
        # sub-period robustness (spread + long-only D10)
        print("  sub-periods (D10-D1 spread | D10 mean | SPY-matched):")
        for label, lo, hi in REGIMES:
            sub = [e for e in ev if lo <= e["t0"] <= hi]
            a = _stats([e[col] for e in sub if e["decile"] == 10])
            b = _stats([e[col] for e in sub if e["decile"] == 1])
            sp = _stats([e[f"s{k}"] for e in sub if e["decile"] == 10 and e.get(f"s{k}") is not None])
            if a and b:
                print(f"     {label}: spread {100*(a['mean']-b['mean']):+.2f}%  "
                      f"D10 {100*a['mean']:+.2f}%  SPY {100*sp['mean'] if sp else float('nan'):+.2f}%  (D10 n={a['n']})")
        print()

    # yearly D10-D1 spread @ k=20 — confirm the recent death isn't one bad year
    col = "r20"
    ev = [e for e in graded if e.get(col) is not None]
    print("=" * 72)
    print("YEARLY D10-D1 SPREAD @ k=20  (by T0 calendar year)")
    print("-" * 72)
    for y in sorted({e["t0"][:4] for e in ev}):
        sub = [e for e in ev if e["t0"][:4] == y]
        a = _stats([e[col] for e in sub if e["decile"] == 10])
        b = _stats([e[col] for e in sub if e["decile"] == 1])
        if a and b:
            print(f"  {y}: spread {100*(a['mean']-b['mean']):+6.2f}%   "
                  f"D10 {100*a['mean']:+6.2f}% (n={a['n']:4d})   D1 {100*b['mean']:+6.2f}% (n={b['n']:4d})")
    print()


if __name__ == "__main__":
    main()
