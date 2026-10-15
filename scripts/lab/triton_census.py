"""TRITON-FP v1 census -- outcome-blind, counts only. QUERY runs it read-only on BUILD's F: Parquet;
LAB never sees a row (rule 8; R-IV.959(a)).

Protocol (all stamped before this file existed or was changed):
  lab\\triton\\TRITON-FP-v1-CENSUS-DRAFT.md          9eff2bc6...  (approved in principle, R-IV.923(d))
  lab\\triton\\TRITON-FP-v1-AMENDMENT-1-R-IV.937.md  79dcd607...  (NO-GATE window; 12 definitions)
  lab\\triton\\TRITON-FP-v1-AMENDMENT-2-R-IV.959.md  e7e363ec...  (8 names; QUERY runs; pro-rata stop)
  lab\\triton\\TRITON-FP-v1-AMENDMENT-3-R-IV.966.md  152745bd...  (D6 by geometry)
  lab\\triton\\TRITON-FP-v1-AMENDMENT-4-R-IV.969.md  5adadaec...  (tau for D5+D6; anchor A0;
                                                                   calibration window; ADV$)
  lab\\triton\\TRITON-FP-v1-AMENDMENT-4a-R-IV.974.md bb4f43a1...  (exact median + p75, decision at
                                                                   p75; floor counts post-D5 events;
                                                                   README field map, D1 codes, dedup,
                                                                   session completeness)
  lab\\triton\\TRITON-FP-v1-AMENDMENT-4c-R-IV.981.md 324d086c...  (D1 adds 6, 9, L; linear quantiles;
                                                                   floor = kept AND D5-matched)
  lab\\triton\\TRITON-FP-v1-AMENDMENT-5-R-IV.989.md  822c84c5...  (group by EXECUTED date; dedup across
                                                                   all files; completeness by walk)
  lab\\triton\\TRITON-FP-v1-AMENDMENT-6-FINAL-R-IV.1012.md 0a4f116d...  (b1 / b2 / SUSPECT; D1 drops
                                                                   non-regular settlement)
  R-IV.1019(b): BUILD's reached_floor is the completeness source of record; this script cross-checks
  it per ticker-session.
  lab\\triton\\TRITON-FP-v1-AMENDMENT-6b-R-IV.1045.md d6b4a0b5...  (census set = BUILD AND LAB, both
                                                                   from Q = E; later-Q and cursor causes
                                                                   excluded; export lag and UNLABELLED
                                                                   REFUSE)
  lab\\triton\\TRITON-FP-v1-AMENDMENT-7-R-IV.1054.md e7d96d47...  (D5/D6 bars: Polygon unadjusted where
                                                                   it covers (T, E), else bars1m/; fixed
                                                                   by coverage, never by outcome)
  Field reference: lab\\triton\\F-README.md e72ea5b9... (BUILD)

Modes:
  anchor  A0 (amendment 4 sec. 2): per-name median NBBO spread vs 0.02% x median print price, on the
          CALIBRATION sessions only, before any D3/D4. Aggregate only.
  run     the census: D1, 3 windows, 4 floors, D3 runs, D4 shuffles, M4, D5 lit match, D6 direction,
          PYTHIA-LOC readings (counts only, stamped). Needs tau final (TAU_PCT) first.
  selftest  synthetic prints/bars/VA only.

Guards in code: seal + quarantine dropped first; ONLY 2026-09-01..2026-09-24 is read (the reserve,
2026-09-25 on, is dropped before anything is computed); outputs refuse price/size/time columns.
Prints are read in the vendor's own fields (F-README) through `from_vendor`. 1-minute bars are read
as F-README states them (R-IV.985(b)): bars1m/<YYYY-MM-DD>/<TICKER>.parquet, one row per minute,
a tz-aware US/Eastern index = the minute the bar OPENS, columns Open/High/Low/Close/.../source,
04:00-19:59 ET included. The ticker comes from the file name. Bars are clipped to 09:30-16:00 ET,
because the D5/D6 window is clipped to the regular session (amendment 2 sec. 4).

Usage (QUERY):
  python scripts/lab/triton_census.py build-complete <walk_pages_csv> <complete_csv_out>
  python scripts/lab/triton_census.py crosscheck <prints_glob> <complete_csv> <crosscheck_csv_out>
  python scripts/lab/triton_census.py --window reserve <any mode> ...   (amendment 8: reserve dates ONLY)
  python scripts/lab/triton_census.py verdict-a8 <census_out_dir> [<comparisons_csv outside it>]
  python scripts/lab/triton_census.py anchor <prints_glob> <complete_csv> <out_dir>
  python scripts/lab/triton_census.py run <prints_glob> <bars_glob> <polygon_glob> <adv_csv> <va_csv|-> <complete_csv> <macro_csv> <out_dir>
  (polygon_glob: bars1m_polygon/*_adjusted_false.parquet -- amendment 7; bars1m/ is read only where Polygon
   does not cover a ticker-session)
  (complete_csv: LAB's cross-check from `build-complete` (ticker, session, complete, route, ...). BUILD's
   export is the source of record (R-IV.1019(b)): `run` reads BUILD's set from the prints' session_date
   and REFUSES on any per-ticker-session disagreement with complete_csv.)
  python scripts/lab/triton_census.py selftest
"""
import glob
import hashlib
import json
import os
import re
import sys
from datetime import date, time

import numpy as np
import pandas as pd

CORE8 = ("SPY", "QQQ", "IWM", "SMH", "NVDA", "AAPL", "MSFT", "TSLA")
SEAL = (date(2026, 8, 17), date(2026, 8, 31))
QUARANTINED = {date(2026, 8, 28), date(2026, 8, 31)}
CALIBRATION = (date(2026, 9, 1), date(2026, 9, 24))     # amendment 4 sec. 3; reserve = 2026-09-25 on
NYSE_HOLIDAYS_IN_WINDOW = {date(2026, 9, 7)}             # Labor Day
CALIBRATION_DATES = [d.date() for d in pd.bdate_range(CALIBRATION[0], CALIBRATION[1])
                     if d.date() not in NYSE_HOLIDAYS_IN_WINDOW]               # 17 executed dates
#: Amendment 8 (TRITON-FP-v1-AMENDMENT-8-R-IV.1062.md dccbd9b8...): the reserve, spent ONCE. Selected
#: only by `--window reserve` on the command line; the default is calibration.
RESERVE = (date(2026, 9, 25), date(2026, 10, 9))
RESERVE_HOLIDAYS = set()                                 # none in 09-25 .. 10-09
WINDOW_NAME = "calibration"
CURSOR_TOL_S = 1.0                                       # amendment 5 sec. 3 (iii)
TICK = 0.01
TAU_PCT = 0.0002                    # amendment 4 sec. 1; final only after A0 (and 4b if triggered)
TAU_FINAL = True                    # A0: tau STANDS (QUERY R-IV.1002); confirmed by SPINE R-IV.1015 (relayed R-IV.1019(a))
TAU_CONFIRMATION = {"ruling": "R-IV.1015 (relayed in R-IV.1019(a))", "covers_p75": "5 of 8",
                    "flagged_names": ["MSFT", "SMH", "TSLA"]}
MAX_GAP_S = 600
REPRO_WINDOW_S = 600
N_SHUFFLES, KEEP_MAX_SHARE = 1000, 0.05
M4_WINDOW_S, M4_TOL, M4_MIN_GAP_S = 1800, 0.10, 30
LIT_WINDOW_S = 600                  # D5 / D6: bars starting within +-10 min of the event time
N_CONTROL_SHUFFLES = 20             # shuffles that supply control events for M4 / D5 / D6
SEED = 20261013
WINDOWS = {"T0945": (time(9, 45), time(16, 0)), "T1000": (time(10, 0), time(16, 0)),
           "NOGATE": (time(9, 30), time(16, 0))}
FLOORS = ("F500K", "FADV", "FRUN", "F100K")
NORMAL_COLUMNS = ("ticker", "t_utc", "price", "size", "nbbo_bid", "nbbo_ask",
                  "canceled", "ext_hours", "excluded_condition")
BAR_COLUMNS = ("ticker", "t_utc", "high", "low", "close", "source")   # normalised; t_utc = bar open
BAR_COLUMNS_README = ("High", "Low", "Close", "source")     # F-README 0478cd78..., bars1m/
TAU_PROVENANCE = "print-time NBBO, calibration sessions 09-01 -> 09-24, biased tight; decision at p75"
VENDOR_FIELDS = ("ticker", "executed_at", "price", "size", "nbbo_bid", "nbbo_ask", "canceled",
                 "sale_cond_codes", "trade_code", "ext_hour_sold_codes", "trade_settlement", "tracking_id")
# amendments 4a sec. 3 + 4c sec. 1: D1 exclusions -- CTA/UTP single-letter codes and vendor word forms
D1_LETTERS = {"T", "U", "Z", "B", "P", "V", "4", "7", "6", "9", "L", "C", "N", "R"}   # + 6-final: C N R
D1_WORDS = ("extended_hours", "out_of_sequence", "average_price", "prior_reference", "contingent",
            "derivative", "qualified_contingent", "corrected", "sold_last", "late_report",
            "cash", "next_day", "seller")
B2_GUARD = "04:15"                                       # amendment 6-final: b2 needs R <= E 04:15 ET
PYTHIA_LABEL = "PYTHIA v2.5 levels, binning under review"
KEEP_LINE = "per-run keep admits about 29% of chance runs in synthetic noise"
VA_EDGE_FRACTION = 0.25             # PYTHIA-LOC v1 (0b406425...): gate v2's directional location


def tau(L, pct=TAU_PCT):
    return np.maximum(TICK, pct * np.asarray(L, float))


# ── load and clean ──────────────────────────────────────────────────────────────────────────────
def normalise(raw, field_map, cols):
    return pd.DataFrame({k: raw[v] for k, v in field_map.items()})[list(cols)]


def _truthy(x):
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    return str(x).strip().lower() in ("t", "true", "1", "y", "yes")


def _blank(x):
    return x is None or (isinstance(x, float) and np.isnan(x)) or str(x).strip() in ("", "None", "null", "nan", "{}", "[]")


def _d1_codes_hit(text):
    """True if a code string carries any D1 exclusion, as a single-letter token or a word form."""
    if _blank(text):
        return False
    t = str(text)
    if set(re.split(r"[^A-Za-z0-9@]+", t)) & D1_LETTERS:
        return True
    low = t.lower()
    return any(w in low for w in D1_WORDS)


def _settlement_bad(x):
    """Amendment 6-final sec. 2: a non-blank trade_settlement that is not regular. 'regular' is matched
    as a substring, case-insensitive, so 'regular' and 'regular_settlement' are both regular."""
    return (not _blank(x)) and "regular" not in str(x).strip().lower()


def from_vendor(raw):
    """F-README fields -> NORMAL_COLUMNS. Dedup on tracking_id (first kept). Returns (df, n_dup)."""
    missing = [c for c in VENDOR_FIELDS if c not in raw.columns]
    if missing:
        raise SystemExit(f"vendor fields missing from the Parquet: {missing} (F-README 8010d73d...)")
    n0 = len(raw)
    raw = raw.drop_duplicates(subset="tracking_id", keep="first")
    codes = raw.sale_cond_codes.map(lambda x: "" if _blank(x) else str(x)) + " " + \
        raw.trade_code.map(lambda x: "" if _blank(x) else str(x))
    df = pd.DataFrame({"ticker": raw.ticker.astype(str), "t_utc": raw.executed_at,
                       "price": raw.price.astype(float), "size": raw["size"].astype(float),
                       "nbbo_bid": pd.to_numeric(raw.nbbo_bid, errors="coerce"),
                       "nbbo_ask": pd.to_numeric(raw.nbbo_ask, errors="coerce"),
                       "canceled": raw.canceled.map(_truthy).astype(bool),
                       "ext_hours": raw.ext_hour_sold_codes.map(lambda x: not _blank(x)).astype(bool),
                       "excluded_condition": (codes.map(_d1_codes_hit) |
                                              raw.trade_settlement.map(_settlement_bad)).astype(bool)})
    return df[list(NORMAL_COLUMNS)].reset_index(drop=True), int(n0 - len(raw))


def code_census(raw):
    """Aggregate distinct-value counts of the code fields, so the D1 map is checked on the data."""
    out = []
    for f in ("sale_cond_codes", "trade_code", "ext_hour_sold_codes", "trade_settlement"):
        vals = raw[f].map(lambda x: "<null>" if _blank(x) else str(x))
        for v, n in vals.value_counts().items():
            vv = v.replace("<null>", "")
            hit = (not _blank(vv)) if f == "ext_hour_sold_codes" else \
                _settlement_bad(vv) if f == "trade_settlement" else _d1_codes_hit(vv)
            out.append({"field": f, "value": v, "prints": int(n), "d1_excluded": bool(hit)})
    return pd.DataFrame(out)


def complete_set(complete_csv):
    c = pd.read_csv(complete_csv, parse_dates=["session"])
    return {(r.ticker, r.session.date()) for r in c.itertuples() if _truthy(r.complete)}


def drop_incomplete(df, complete):
    key = list(zip(df.ticker, df.session))
    keep = np.array([k in complete for k in key], bool)
    dropped = sorted({f"{k[0]} {k[1]}" for k, m in zip(key, keep) if not m})
    return df[keep], dropped


def _et(df):
    t = pd.to_datetime(df.t_utc, utc=True, format="ISO8601").dt.tz_convert("America/New_York")
    return t, t.dt.date


def set_window(name):
    """Amendment 8 sec. 1-2: the ONLY change for the reserve run is the date window. Every reader
    (in_calibration, CALIBRATION_DATES) then reads only that window; all other dates are dropped."""
    global CALIBRATION, CALIBRATION_DATES, WINDOW_NAME
    if name == "reserve":
        CALIBRATION = RESERVE
        CALIBRATION_DATES = [d.date() for d in pd.bdate_range(*RESERVE) if d.date() not in RESERVE_HOLIDAYS]
    elif name == "calibration":
        CALIBRATION = (date(2026, 9, 1), date(2026, 9, 24))
        CALIBRATION_DATES = [d.date() for d in pd.bdate_range(*CALIBRATION) if d.date() not in NYSE_HOLIDAYS_IN_WINDOW]
    else:
        raise SystemExit(f"unknown window {name!r}: calibration or reserve")
    WINDOW_NAME = name


#: Amendment 8 sec. 3: the 9 definitions, fixed (non-empty on calibration), and the verdict.
A8_DEFINITIONS = [(w, f) for f in ("F100K", "F500K", "FRUN") for w in ("NOGATE", "T0945", "T1000")]
A8_KILL = "TRITON-FP v1: KILL"
A8_NOT_REPLICATED = "calibration kill not replicated, returned to SPINE"


def a8_comparisons(E, D):
    """The 27 real-vs-placebo comparisons of amendment 8 sec. 3, from events_m4_d5 (E) and
    d6_direction (D). 'exceeds' = real strictly greater; undefined (no testable event in an arm)
    does not exceed and is named."""
    rows = []

    def ratio(num, den):
        return (float(num) / float(den)) if den and den > 0 else None
    for w, f in A8_DEFINITIONS:
        e = E[(E.window == w) & (E.floor == f)]
        rk = e[(e.arm == "real") & (e.kept.astype(str) == "True")]
        pl = e[e.arm == "shuffled"]
        tr, tp = (rk.events - rk.no_bars).sum(), (pl.events - pl.no_bars).sum()
        d = D[(D.window == w) & (D.floor == f) & (D.tolerance == "tau")]
        dr, dp = d[d.arm == "real"], d[d.arm == "shuffled"]

        def dir_share(x):
            t = x[x.d6 != "NO_BARS"].events.sum()
            return ratio(x[x.d6.isin(["BUYER", "SELLER"])].events.sum(), t)
        for m, r_, p_ in (("D5_tau", ratio(rk.d5_matched.sum(), tr), ratio(pl.d5_matched.sum(), tp)),
                          ("D5_1tick", ratio(rk.d5_matched_1tick.sum(), tr), ratio(pl.d5_matched_1tick.sum(), tp)),
                          ("D6_directional", dir_share(dr), dir_share(dp))):
            undef = r_ is None or p_ is None
            rows.append({"window": w, "floor": f, "measure": m, "real": r_, "placebo": p_,
                         "undefined": undef, "exceeds": (not undef) and r_ > p_})
    C = pd.DataFrame(rows)
    k = int(C.exceeds.sum())
    return C, k, (A8_NOT_REPLICATED if k >= 14 else A8_KILL)


def a8_sanity(P, E, n_dates):
    """Stop rules (a) and (b), reported beside the verdict (amendment 8 sec. 3); they do not change it."""
    g = P.groupby(["window", "floor"]).agg(real=("real_runs", "sum"), kept=("kept_runs", "sum"),
                                           p95=("shuffled_p95", "sum")).reset_index()
    approx = [(r.real == 0) or (r.kept / r.real < 0.10) or (r.real <= r.p95) for r in g.itertuples()]
    fl = E[(E.arm == "real") & (E.kept.astype(str) == "True")]
    best = int(fl.d5_matched.max()) if len(fl) else 0
    per_week = best / (n_dates / 5.0) if n_dates else 0.0
    return {"stop_a_fires": bool(all(approx)), "definitions_approx_shuffled": int(sum(approx)),
            "stop_b_best_floor": best, "stop_b_per_week": round(per_week, 1), "stop_b_fires": per_week < 0.5}


def run_verdict_a8(census_dir, comparisons_csv=None):
    """Read a census output folder (read-only; nothing is written into it) and print amendment 8's
    k, verdict and sanity check. The 27 comparisons go to comparisons_csv only if a path is given,
    and that path must be outside census_dir. Aggregates only."""
    E = pd.read_csv(os.path.join(census_dir, "events_m4_d5.csv"))
    D = pd.read_csv(os.path.join(census_dir, "d6_direction.csv"))
    P = pd.read_csv(os.path.join(census_dir, "per_ticker_session.csv"))
    C, k, verdict = a8_comparisons(E, D)
    if comparisons_csv:
        if os.path.abspath(os.path.dirname(comparisons_csv)) == os.path.abspath(census_dir):
            raise SystemExit("verdict-a8 never writes into the census folder it reads")
        C.to_csv(comparisons_csv, index=False)
    out = {"k_real_exceeds_placebo": k, "of": len(C), "verdict": verdict,
           "undefined": C[C.undefined][["window", "floor", "measure"]].to_dict("records"),
           "sanity": a8_sanity(P, E, P.session.nunique()), "amendment_8": "dccbd9b8..."}
    print(json.dumps(out, indent=1))
    return out


def in_calibration(sessions):
    s = pd.Series(sessions)
    sealed = (s >= SEAL[0]) & (s <= SEAL[1])
    return ((s >= CALIBRATION[0]) & (s <= CALIBRATION[1]) & ~sealed & ~s.isin(QUARANTINED)).to_numpy()


def d1_clean(df):
    """D1 + universe + RTH + the calibration window (seal, quarantine and reserve dropped)."""
    df = df[~df.canceled.astype(bool) & ~df.ext_hours.astype(bool) & ~df.excluded_condition.astype(bool)]
    df = df[df.ticker.isin(CORE8)].copy()
    df["t_et"], df["session"] = _et(df)
    tod = df.t_et.dt.time
    df = df[(tod >= time(9, 30)) & (tod < time(16, 0))]
    df = df[in_calibration(df.session)]
    return df.sort_values(["ticker", "t_et"], kind="stable")


def load_bars(globpat):
    """bars1m/<YYYY-MM-DD>/<TICKER>.parquet (F-README) -> BAR_COLUMNS. The index is tz-aware ET."""
    files = sorted(glob.glob(globpat))
    if not files:
        raise SystemExit(f"no bar files match {globpat}")
    parts = []
    for f in files:
        tk = os.path.splitext(os.path.basename(f))[0]
        if tk not in CORE8:
            continue
        b = pd.read_parquet(f)
        missing = [c for c in BAR_COLUMNS_README if c not in b.columns]
        if missing:
            raise SystemExit(f"{f}: bar columns missing {missing} (F-README 0478cd78...)")
        idx = pd.DatetimeIndex(b.index)
        if idx.tz is None:
            raise SystemExit(f"{f}: bar index is not tz-aware (F-README says US/Eastern)")
        parts.append(pd.DataFrame({"ticker": tk, "t_utc": idx.tz_convert("UTC"), "high": b["High"].to_numpy(float),
                                   "low": b["Low"].to_numpy(float), "close": b["Close"].to_numpy(float),
                                   "source": b["source"].astype(str).to_numpy()}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=list(BAR_COLUMNS))


def load_polygon(globpat):
    """Amendment 7 sec. 2: bars1m_polygon/<TICKER>_adjusted_false.parquet -> BAR_COLUMNS, source
    'polygon'. adjusted_true files are never read. Returns (bars, per-file info). Refuses on no file,
    a ticker that does not match its file name, or an adjusted value that is not False."""
    files = sorted(f for f in glob.glob(globpat) if os.path.basename(f).endswith("_adjusted_false.parquet"))
    if not files:
        raise SystemExit(f"no unadjusted Polygon bar files match {globpat} (amendment 7 sec. 2: refusing)")
    parts, info = [], []
    for f in files:
        tk = os.path.basename(f)[: -len("_adjusted_false.parquet")]
        if tk not in CORE8:
            continue
        b = pd.read_parquet(f)
        if set(b.ticker.astype(str)) != {tk}:
            raise SystemExit(f"{f}: holds {sorted(set(b.ticker.astype(str)))}, not {tk} (amendment 7 sec. 2)")
        if "adjusted" in b.columns and bool(b.adjusted.astype(bool).any()):
            raise SystemExit(f"{f}: carries adjusted=True rows in an unadjusted file (amendment 7 sec. 2)")
        t = pd.to_datetime(b.timestamp_utc, utc=True)
        et = t.dt.tz_convert("America/New_York").dt.date
        info.append({"file": os.path.basename(f), "sha256": hashlib.sha256(open(f, "rb").read()).hexdigest(),
                     "rows_read": int(len(b)), "first_session_et": str(et.min()), "last_session_et": str(et.max())})
        parts.append(pd.DataFrame({"ticker": tk, "t_utc": t.to_numpy(), "high": b["high"].to_numpy(float),
                                   "low": b["low"].to_numpy(float), "close": b["close"].to_numpy(float),
                                   "source": "polygon"}))
    return (pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=list(BAR_COLUMNS))), info


def _rth_keys(bars):
    """(ticker, ET date) pairs holding at least one bar opening 09:30-15:59 ET."""
    if bars is None or not len(bars):
        return set()
    t = pd.to_datetime(bars.t_utc, utc=True).dt.tz_convert("America/New_York")
    tod = t.dt.time
    m = (tod >= time(9, 30)) & (tod < time(16, 0))
    return set(zip(bars.ticker[m], t.dt.date[m]))


def choose_bars(readme_bars, polygon_bars):
    """Amendment 7 sec. 1, FIXED, by coverage only: per calibration (T, E), Polygon unadjusted if it
    covers (T, E), else bars1m/ if it holds RTH bars, else none. Never mixed within a ticker-session.
    Returns (bars, source_map) -- the map holds ticker, session, source and no price."""
    pk, rk = _rth_keys(polygon_bars), _rth_keys(readme_bars)
    rows = []
    for tk in CORE8:
        for e in CALIBRATION_DATES:
            src = "polygon" if (tk, e) in pk else "bars1m" if (tk, e) in rk else "none"
            rows.append({"ticker": tk, "session": e.isoformat(), "source": src})
    M = pd.DataFrame(rows)
    use_p = {(r.ticker, date.fromisoformat(r.session)) for r in M[M.source == "polygon"].itertuples()}
    use_r = {(r.ticker, date.fromisoformat(r.session)) for r in M[M.source == "bars1m"].itertuples()}

    def pick(b, keys):
        if b is None or not len(b) or not keys:
            return b.iloc[0:0] if b is not None else pd.DataFrame(columns=list(BAR_COLUMNS))
        d = pd.to_datetime(b.t_utc, utc=True).dt.tz_convert("America/New_York").dt.date
        return b[[k in keys for k in zip(b.ticker, d)]]
    bars = pd.concat([pick(polygon_bars, use_p), pick(readme_bars, use_r)], ignore_index=True)
    return bars, M


def bars_by_session(bars):
    """{(ticker, session): (start_s, high, low, close)}: calibration sessions only, bars opening
    09:30-15:59 ET only (the D5/D6 window is clipped to the regular session)."""
    if bars is None or not len(bars):
        return {}
    b = bars[bars.ticker.isin(CORE8)].copy()
    b["t_et"] = pd.to_datetime(b.t_utc, utc=True).dt.tz_convert("America/New_York")
    b["session"] = b.t_et.dt.date
    b = b[in_calibration(b.session)]
    tod = b.t_et.dt.time
    b = b[(tod >= time(9, 30)) & (tod < time(16, 0))]
    out = {}
    for k, g in b.groupby(["ticker", "session"]):
        g = g.sort_values("t_et")
        s_ = (g.t_et - g.t_et.dt.normalize()).dt.total_seconds().to_numpy()
        out[k] = (s_, g["high"].to_numpy(float), g["low"].to_numpy(float), g["close"].to_numpy(float))
    return out


def bar_sources(bars):
    """Calibration ticker-sessions with bars, by source (yfinance / uw), for the run metadata."""
    if bars is None or not len(bars):
        return {}
    t = pd.to_datetime(bars.t_utc, utc=True).dt.tz_convert("America/New_York")
    d = pd.DataFrame({"ticker": bars.ticker, "session": t.dt.date, "source": bars.source})
    d = d[in_calibration(d.session)].drop_duplicates(["ticker", "session", "source"])
    return d.groupby("source").size().to_dict()


# ── amendment 5: completeness per (ticker, EXECUTED date), from the walk metadata ────────────────
def _instant(x):
    """A cursor / timestamp as a UTC Timestamp. Epoch numbers (s or ms) or ISO strings; None if not."""
    if x is None or (isinstance(x, float) and np.isnan(x)) or str(x).strip() in ("", "None", "null", "nan"):
        return None
    t = str(x).strip()
    try:
        v = float(t)
        return pd.Timestamp(v, unit="ms" if v > 1e11 else "s", tz="UTC")
    except ValueError:
        pass
    try:
        return pd.Timestamp(t).tz_convert("UTC") if pd.Timestamp(t).tzinfo else pd.Timestamp(t, tz="UTC")
    except (ValueError, TypeError):
        return None


def walk_reach(pages):
    """One (ticker, query_date) walk. Returns a dict: reach (oldest print of the unbroken prefix, UTC),
    n_ok, n_pages, last_rc (row count of the prefix's final page), cap (MAX(row_count) over the walk's
    stored pages -- READ, never hardcoded), exhausted (the prefix is the whole walk and its final page
    is below the cap), brk (why the prefix stopped short of the whole walk, "" if it did not:
    page_gap / empty_page / no_executed_at / cursor_missing / cursor_gap) and cursor_gap_s."""
    g = pages.sort_values("page_no")
    first = int(g.page_no.iloc[0])
    oldest, n_ok, last_rc, brk, gap_s = None, 0, None, "", None
    for j, r in enumerate(g.itertuples()):
        if int(r.page_no) != first + j:
            brk = "page_gap"
            break
        if not (r.row_count and r.row_count > 0):
            brk = "empty_page"
            break
        lo = _instant(r.min_executed_at)
        if lo is None:
            brk = "no_executed_at"
            break
        if j >= 1:
            c = _instant(r.older_than_cursor)
            if c is None:
                brk = "cursor_missing"
                break
            if abs((c - oldest).total_seconds()) > CURSOR_TOL_S:
                brk, gap_s = "cursor_gap", round(abs((c - oldest).total_seconds()), 3)
                break
        oldest = lo if oldest is None else min(oldest, lo)
        n_ok += 1
        last_rc = int(r.row_count)
    cap = int(pd.to_numeric(g.row_count, errors="coerce").max())
    exhausted = bool(n_ok and n_ok == len(g) and last_rc is not None and last_rc < cap)
    return {"reach": oldest, "n_ok": n_ok, "n_pages": int(len(g)), "last_rc": last_rc, "cap": cap,
            "exhausted": exhausted, "brk": brk, "cursor_gap_s": gap_s}


def _route(w, e):
    """b1 / b2 / SUSPECT / None for one walk w and executed date e (amendment 6-final sec. 1)."""
    r = w["reach"]
    if r is None:
        return None
    t0400 = pd.Timestamp(e.isoformat() + " 04:00", tz="America/New_York").tz_convert("UTC")
    tguard = pd.Timestamp(e.isoformat() + " " + B2_GUARD, tz="America/New_York").tz_convert("UTC")
    if r < t0400:
        return "b1"
    if w["exhausted"] and r <= tguard:
        return "b2"
    if w["exhausted"] and r.tz_convert("America/New_York").date() == e:
        return "SUSPECT"
    return None


def build_complete(wp):
    """walk_pages -> complete.csv rows for CORE8 x CALIBRATION_DATES (route b1 / b2 / SUSPECT / none),
    plus the anchor-trigger count. Amendment 6b sec. 1: complete and route come from the walk with
    Q = E ONLY (BUILD's same-date rule governs); SUSPECT is NOT complete. Amendment 5's any-Q >= E
    credit is kept as a diagnostic (any_q_route, best_query_date) and credits nothing."""
    walks = {}
    for (tk, q), g in wp.groupby(["ticker", "query_date"]):
        walks.setdefault(tk, []).append((pd.Timestamp(q).date(), walk_reach(g)))
    order = {"b1": 0, "b2": 1, "SUSPECT": 2}
    rows = []
    for tk in CORE8:
        for e in CALIBRATION_DATES:
            cands = [(order[rt], q, w) for q, w in walks.get(tk, []) if q >= e
                     for rt in [_route(w, e)] if rt]
            best = min(cands, key=lambda x: (x[0], x[1])) if cands else None
            any_q = {v: k for k, v in order.items()}[best[0]] if best else "none"
            same = [w for q, w in walks.get(tk, []) if q == e]      # the walk BUILD judges E by (Q = E)
            sw = same[0] if same else None
            route = (_route(sw, e) or "none") if sw else "none"
            rows.append({"ticker": tk, "session": e.isoformat(), "complete": route in ("b1", "b2"),
                         "route": route,
                         "same_date_route": route if sw else "no_walk",
                         "same_date_break": sw["brk"] if sw else "",
                         "same_date_cursor_gap_s": sw["cursor_gap_s"] if sw and sw["cursor_gap_s"] is not None else "",
                         "best_reach_et": sw["reach"].tz_convert("America/New_York").strftime(
                             "%Y-%m-%d %H:%M:%S") if sw and sw["reach"] is not None else "",
                         "cap_used": sw["cap"] if sw else "",
                         "n_walks": int(sum(1 for q, _ in walks.get(tk, []) if q >= e)),
                         "any_q_route": any_q,                        # diagnostic only (amendment 5)
                         "best_query_date": best[1].isoformat() if best else ""})
    C = pd.DataFrame(rows)
    per_date = C.groupby("session").complete.all()
    return C, {"calibration_dates": len(CALIBRATION_DATES),
               "dates_complete_for_all_8": int(per_date.sum()),
               "anchor_trigger_met_12_of_17": bool(per_date.sum() >= 12),
               "suspect_ticker_sessions": int((C.route == "SUSPECT").sum())}


def build_complete_set(raw):
    """BUILD's source of record (R-IV.1019(b)): the export writes ONLY complete sessions
    (exhausted AND reached_floor AND prints_received > 0) and stamps each print with its session_date,
    so the exported (ticker, session_date) pairs ARE BUILD's complete set. Calibration x CORE8 only."""
    if "session_date" not in raw.columns:
        raise SystemExit("the export carries no session_date column: BUILD's completeness cannot be read; refusing")
    sd = pd.to_datetime(raw.session_date).dt.date
    keys = set(zip(raw.ticker.astype(str), sd))
    return {(t, d) for t, d in keys if t in CORE8 and d in set(CALIBRATION_DATES)}


def cross_check(lab_complete, build_set):
    """REFUSE on any per-ticker-session disagreement between LAB's cross-check and BUILD's record."""
    lab = {(r.ticker, pd.Timestamp(r.session).date()): _truthy(r.complete) for r in lab_complete.itertuples()}
    dis = []
    for tk in CORE8:
        for e in CALIBRATION_DATES:
            a, b = lab.get((tk, e), False), (tk, e) in build_set
            if a != b:
                dis.append(f"{tk} {e}: LAB={a} BUILD={b}")
    return dis


def _cell(x):
    """A CSV cell as text: NaN / None -> ''."""
    return "" if x is None or (isinstance(x, float) and np.isnan(x)) else str(x)


def crosscheck_table(lab_complete, build_set):
    """Per CORE8 x calibration ticker-session: LAB vs BUILD, with the likely cause of a disagreement.
    BUILD decides reached_floor per (ticker, Q) against Q's OWN 04:00 ET floor, so it credits E only
    from the walk with Q = E, and its 'unbroken' is page numbering only. Amendment 5 sec. 3 lets LAB
    credit E from any Q >= E and also requires each cursor within 1 s. Metadata only, no prints."""
    lab = {(r.ticker, pd.Timestamp(r.session).date()): r for r in lab_complete.itertuples()}
    rows = []
    for tk in CORE8:
        for e in CALIBRATION_DATES:
            r = lab.get((tk, e))
            a, b = (_truthy(r.complete) if r is not None else False), (tk, e) in build_set
            route = _cell(getattr(r, "route", "")) if r is not None else ""
            bq = _cell(getattr(r, "best_query_date", "")) if r is not None else ""
            sroute = _cell(getattr(r, "same_date_route", "")) if r is not None else ""
            sbrk = _cell(getattr(r, "same_date_break", "")) if r is not None else ""
            cause = "" if a == b else \
                ("LAB complete from Q = E; BUILD not" if sroute in ("b1", "b2") else
                 "LAB credits via a later query date; BUILD does not") if a and bq and bq != e.isoformat() else \
                "LAB complete from Q = E; BUILD not" if a else \
                "BUILD credits; LAB refuses on cursor continuity (> 1 s)" if sbrk == "cursor_gap" else \
                f"UNLABELLED: BUILD credits; LAB same-date route {sroute or route or 'none'}, break {sbrk or 'none'}"
            rows.append({"ticker": tk, "session": e.isoformat(), "lab": a, "build": b, "agree": a == b,
                         "lab_route": route, "lab_best_query_date": bq, "lab_same_date_route": sroute,
                         "lab_same_date_break": sbrk,
                         "lab_same_date_cursor_gap_s": _cell(getattr(r, "same_date_cursor_gap_s", "")) if r is not None else "",
                         "cause": cause, "disposition": disposition(cause)})
    return pd.DataFrame(rows)


#: Amendment 6b sec. 2 (TRITON-FP-v1-AMENDMENT-6b-R-IV.1045.md d6b4a0b5...): what each cause does.
EXCLUDED_CAUSES = ("LAB credits via a later query date; BUILD does not",
                   "BUILD credits; LAB refuses on cursor continuity (> 1 s)")
EXPORT_LAG = "LAB complete from Q = E; BUILD not"            # R-IV.1039(b): REFUSE; the remedy is a re-export


def disposition(cause):
    """'' (agree) / 'excluded' / 'refuse'. Anything not named, including UNLABELLED, refuses."""
    return "" if not cause else "excluded" if cause in EXCLUDED_CAUSES else "refuse"


def census_set(lab_complete, build_set):
    """Amendment 6b sec. 1: the ticker-sessions BOTH rules call complete (from Q = E). Returns the set,
    the exclusions [{ticker, session, cause}], and the refusals [same]. A non-empty refusal list means
    `run` must not read a print."""
    T = crosscheck_table(lab_complete, build_set)
    both = T[T.lab & T.build]
    S = {(r.ticker, date.fromisoformat(r.session)) for r in both.itertuples()}
    rec = lambda df: [{"ticker": r.ticker, "session": r.session, "cause": r.cause} for r in df.itertuples()]  # noqa: E731
    return S, rec(T[T.disposition == "excluded"]), rec(T[T.disposition == "refuse"])


def refusal_message(refusals):
    lag = [f"{r['ticker']} {r['session']}" for r in refusals if r["cause"] == EXPORT_LAG]
    other = [f"{r['ticker']} {r['session']}: {r['cause']}" for r in refusals if r["cause"] != EXPORT_LAG]
    parts = []
    if lag:
        parts.append(f"EXPORT LAG on {len(lag)} ticker-session(s) -- LAB's same-date walk is complete but "
                     f"BUILD's export lacks them; BUILD re-exports, then crosscheck again: {lag}")
    if other:
        parts.append(f"{len(other)} unlabelled disagreement(s): {other}")
    return "amendment 6b: refusing. " + " | ".join(parts)


def run_crosscheck(prints_glob, complete_csv, out_csv):
    """Before the overnight `run`: BUILD's set (the export's session_date) vs LAB's complete.csv.
    Reads only the ticker and session_date columns. Amendment 6b: exit 1 when any disagreement's
    disposition is 'refuse' (`run` would refuse); excluded causes alone exit 0."""
    files = sorted(glob.glob(prints_glob))
    if not files:
        raise SystemExit(f"no files match {prints_glob}")
    try:
        raw = pd.concat([pd.read_parquet(f, columns=["ticker", "session_date"]) for f in files], ignore_index=True)
    except Exception:
        raw = pd.DataFrame({"ticker": []})                  # no session_date -> build_complete_set refuses
    T = crosscheck_table(pd.read_csv(complete_csv), build_complete_set(raw))
    T.to_csv(out_csv, index=False)
    print(json.dumps({"ticker_sessions": int(len(T)), "agree": int(T.agree.sum()),
                      "disagree": int((~T.agree).sum()),
                      "by_cause": T[~T.agree].cause.value_counts().to_dict(),
                      "excluded": int((T.disposition == "excluded").sum()),
                      "refuse": int((T.disposition == "refuse").sum())}, indent=1))
    return 1 if bool((T.disposition == "refuse").any()) else 0


def run_build_complete(walk_csv, out_csv):
    wp = pd.read_csv(walk_csv)
    C, info = build_complete(wp)
    C.to_csv(out_csv, index=False)
    print(json.dumps(info, indent=1))


# ── A0: the tau anchor (aggregate only) ──────────────────────────────────────────────────────────
def anchor(df):
    """Amendment 4a: EXACT quantiles over every qualifying print (pandas): median AND p75 of the
    print-time NBBO spread per name; the decision uses p75."""
    rows = []
    for tk, g in df.groupby("ticker"):
        bid, ask, px = g.nbbo_bid.to_numpy(float), g.nbbo_ask.to_numpy(float), g["price"].to_numpy(float)
        ok = (bid > 0) & (ask > 0) & (ask >= bid)
        spr = pd.Series((ask - bid)[ok])
        med_px = float(np.median(px))
        has = len(spr) > 0
        med_spr = float(spr.quantile(0.5, interpolation="linear")) if has else float("nan")    # 4c sec. 2
        p75_spr = float(spr.quantile(0.75, interpolation="linear")) if has else float("nan")
        rows.append({"ticker": tk, "n_prints": int(len(g)), "n_with_nbbo": int(ok.sum()),
                     "median_spread": round(med_spr, 6), "p75_spread": round(p75_spr, 6),
                     "median_print_price": round(med_px, 4), "tau_pct_x_median": round(TAU_PCT * med_px, 6),
                     "covers_p75": bool(has and TAU_PCT * med_px >= p75_spr),
                     "covers_median": bool(has and TAU_PCT * med_px >= med_spr)})
    A = pd.DataFrame(rows)
    stands = int(A.covers_p75.sum()) if len(A) else 0
    p_star = None
    if stands < 5 and len(A):
        for p in np.arange(0.00005, 0.0101, 0.00005):         # 0.5 bp steps
            if int((p * A.median_print_price >= A.p75_spread).sum()) >= 5:
                p_star = round(float(p), 6)
                break
    return A, {"decision_statistic": "p75", "names_where_tau_covers_p75": stands,
               "names_where_tau_covers_median": int(A.covers_median.sum()) if len(A) else 0,
               "tau_stands": stands >= 5, "proposed_p_star_if_not": p_star, "tau_pct": TAU_PCT,
               "tau_provenance": TAU_PROVENANCE}


# ── D3 runs ─────────────────────────────────────────────────────────────────────────────────────
def find_runs(t_s, price, size):
    n = len(size)
    if n < 2:
        return np.empty(0, int), np.empty(0, int)
    same = (size[1:] == size[:-1]) & (np.abs(price[1:] - price[:-1]) <= TICK + 1e-9) \
        & ((t_s[1:] - t_s[:-1]) <= MAX_GAP_S)
    brk = np.r_[True, ~same]
    starts = np.flatnonzero(brk)
    ends = np.r_[starts[1:] - 1, n - 1]
    need = np.where(size[starts] % 1000 == 0, 3, 2)
    ok = (ends - starts + 1) >= need
    return starts[ok], ends[ok]


def runs_for(t_s, price, size, adv_dollars, floor):
    """D2 then D3. Returns rows (end_time_s, size, length, L)."""
    notional = price * size
    if floor == "F500K":
        m = notional >= 500_000
    elif floor == "F100K":
        m = notional >= 100_000
    elif floor == "FADV":                                     # amendment 4 sec. 4: dollars
        m = notional >= 0.001 * adv_dollars if adv_dollars and adv_dollars > 0 else np.zeros(len(size), bool)
    else:
        m = np.ones(len(size), bool)
    ts, p, s = t_s[m], price[m], size[m]
    st, en = find_runs(ts, p, s)
    if not len(st):
        return np.empty((0, 4))
    cs = np.r_[0.0, np.cumsum(p * s)]
    tot = cs[en + 1] - cs[st]
    L = tot / (s[st] * (en - st + 1))
    out = np.c_[ts[en], s[st], en - st + 1, L]
    return out[tot >= 2_000_000] if floor == "FRUN" else out


def reproduced(real, shuf):
    if not len(real) or not len(shuf):
        return np.zeros(len(real), bool)
    dt = np.abs(real[:, None, 0] - shuf[None, :, 0]) <= REPRO_WINDOW_S
    same = (real[:, None, 1] == shuf[None, :, 1]) & (shuf[None, :, 2] >= real[:, None, 2])
    near = np.abs(real[:, None, 3] - shuf[None, :, 3]) <= TICK + 1e-9
    return (dt & same & near).any(axis=1)


# ── M4, D5, D6, PYTHIA-LOC on one event ─────────────────────────────────────────────────────────
def m4_present(t_s, size, t_event):
    w = (t_s >= t_event - M4_WINDOW_S) & (t_s <= t_event + M4_WINDOW_S)
    tt, ss = t_s[w], size[w]
    for s in np.unique(ss):
        ts = tt[ss == s]
        if len(ts) < 3:
            continue
        g = np.diff(ts)
        g1, g2 = g[:-1], g[1:]
        if np.any((np.minimum(g1, g2) >= M4_MIN_GAP_S) & (np.abs(g1 - g2) <= M4_TOL * np.maximum(g1, g2))):
            return True
    return False


def lit(bars, t_event, L, tol):
    """D5 matched? and the D6 class, at tolerance `tol`. bars = (start_s, high, low, close) or None."""
    if bars is None:
        return None, "NO_BARS"
    s, hi, lo, cl = bars
    w = (s >= t_event - LIT_WINDOW_S) & (s <= t_event + LIT_WINDOW_S)
    hi, lo, cl = hi[w], lo[w], cl[w]
    if not len(cl):
        return None, "NO_BARS"
    n_lo = int(np.sum(np.abs(lo - L) <= tol + 1e-9))
    n_hi = int(np.sum(np.abs(hi - L) <= tol + 1e-9))
    d5 = n_lo >= 2 or n_hi >= 2
    buyer = n_lo >= 2 and not np.any(cl < L - tol - 1e-9)
    seller = n_hi >= 2 and not np.any(cl > L + tol + 1e-9)
    d6 = "AMBIGUOUS" if (buyer and seller) else "BUYER" if buyer else "SELLER" if seller else "NONE"
    return d5, d6


def pythia_loc(P, vah, val, direction):
    """PYTHIA-LOC v1 = circes_stew.va_location_directional (gate v2), edge fraction 0.25."""
    if P is None or vah is None or val is None or not (vah > val):
        return "UNAVAILABLE"
    band = (vah - val) * VA_EDGE_FRACTION
    if direction == "SHORT":
        if P > vah:
            return "outside"
        if P >= vah - band:
            return "edge"
        return "opposite" if P <= val + band else "mid"
    if P < val:
        return "outside"
    if P <= val + band:
        return "edge"
    return "opposite" if P >= vah - band else "mid"


def event_rows(arm, wname, fl, kept, t_s, sizes, ev, bars, va):
    t_e, L = ev[0], ev[3]
    tau_L = float(tau(L))
    d5, d6 = lit(bars, t_e, L, tau_L)
    d5_1, d6_1 = lit(bars, t_e, L, TICK)
    rec = {"arm": arm, "window": wname, "floor": fl, "kept": kept, "m4": m4_present(t_s, sizes, t_e),
           "d5": d5, "d6": d6, "d5_1tick": d5_1, "d6_1tick": d6_1}
    readings = []
    if va is not None:
        dirs = {"BUYER": ["LONG"], "SELLER": ["SHORT"]}.get(d6, ["LONG", "SHORT"])
        for d in dirs:
            readings.append({"arm": arm, "window": wname, "floor": fl, "d6": d6, "reading": d,
                             "location": pythia_loc(L, va[0], va[1], d)})
    return rec, readings


# ── the census ──────────────────────────────────────────────────────────────────────────────────
def census(df, adv, bars=None, va=None, n_shuffles=N_SHUFFLES, macro=None):
    rng = np.random.default_rng(SEED)
    bars = bars or {}
    va = va or {}
    macro = macro or set()
    per_ts, tod, wkd, evs, pyl, mac = [], [], [], [], [], []
    for (tk, sess), g in df.groupby(["ticker", "session"], sort=True):
        t_all = (g.t_et - g.t_et.dt.normalize()).dt.total_seconds().to_numpy()
        p_all, s_all = g["price"].to_numpy(float), g["size"].to_numpy(float)
        a = adv.get((tk, sess))
        b = bars.get((tk, sess))
        v = va.get((tk, sess))
        perms = [rng.permutation(len(s_all)) for _ in range(n_shuffles)]
        wd = pd.Timestamp(sess).day_name()[:3]
        for wname, (w0, w1) in WINDOWS.items():
            lo, hi = w0.hour * 3600 + w0.minute * 60, w1.hour * 3600 + w1.minute * 60
            wm = (t_all >= lo) & (t_all < hi)
            t_s, p, s = t_all[wm], p_all[wm], s_all[wm]
            for fl in FLOORS:
                real = runs_for(t_s, p, s, a, fl)
                hits = np.zeros(len(real), int)
                shuf_counts = np.empty(n_shuffles, int)
                pool = []
                for k, pm in enumerate(perms):
                    s_sh = s_all[pm][wm]
                    sh = runs_for(t_s, p, s_sh, a, fl)
                    shuf_counts[k] = len(sh)
                    hits += reproduced(real, sh)
                    if k < N_CONTROL_SHUFFLES:
                        pool.extend((e, s_sh) for e in sh)
                kept = hits <= KEEP_MAX_SHARE * n_shuffles
                per_ts.append({"ticker": tk, "session": str(sess), "window": wname, "floor": fl,
                               "real_runs": int(len(real)),
                               "shuffled_mean": round(float(shuf_counts.mean()), 3),
                               "shuffled_p95": float(np.percentile(shuf_counts, 95)),
                               "excess_real_minus_shuffled": round(float(len(real) - shuf_counts.mean()), 3),
                               "kept_runs": int(kept.sum()), "kept_note": KEEP_LINE})
                for r, kp in zip(real, kept):
                    tod.append({"window": wname, "floor": fl, "kept": bool(kp), "bucket_min": int(r[0] // 1800) * 30})
                    wkd.append({"window": wname, "floor": fl, "kept": bool(kp), "weekday": wd})
                    mac.append({"window": wname, "floor": fl, "kept": bool(kp), "macro_day": sess in macro})
                    rec, rd = event_rows("real", wname, fl, bool(kp), t_s, s, r, b, v)
                    evs.append(rec)
                    pyl.extend(rd)
                if len(real) and pool:
                    pick = rng.choice(len(pool), size=min(len(real), len(pool)), replace=False)
                    for i in pick:
                        e, ssh = pool[i]
                        rec, rd = event_rows("shuffled", wname, fl, None, t_s, ssh, e, b, v)
                        evs.append(rec)
                        pyl.extend(rd)
    A = pd.DataFrame(per_ts)
    T = (pd.DataFrame(tod).groupby(["window", "floor", "kept", "bucket_min"]).size().rename("events").reset_index()
         if tod else pd.DataFrame())
    W = (pd.DataFrame(wkd).groupby(["window", "floor", "kept", "weekday"]).size().rename("events").reset_index()
         if wkd else pd.DataFrame())
    E = pd.DataFrame(evs)
    if len(E):
        E["d5"] = E.d5.astype("object")
        E["d5_1tick"] = E.d5_1tick.astype("object")
        M = E.groupby(["window", "floor", "arm", "kept"], dropna=False).agg(
            events=("m4", "size"), m4=("m4", "sum"),
            d5_matched=("d5", lambda x: int((x == True).sum())),          # noqa: E712
            d5_matched_1tick=("d5_1tick", lambda x: int((x == True).sum())),  # noqa: E712
            no_bars=("d6", lambda x: int((x == "NO_BARS").sum()))).reset_index()
        D6 = pd.concat([E.groupby(["window", "floor", "arm", "d6"]).size().rename("events").reset_index()
                        .assign(tolerance="tau"),
                        E.groupby(["window", "floor", "arm", "d6_1tick"]).size().rename("events").reset_index()
                        .rename(columns={"d6_1tick": "d6"}).assign(tolerance="1tick_sensitivity")])
    else:
        M, D6 = pd.DataFrame(), pd.DataFrame()
    P = (pd.DataFrame(pyl).groupby(["window", "floor", "arm", "d6", "reading", "location"]).size()
         .rename("readings").reset_index().assign(label=PYTHIA_LABEL) if pyl else pd.DataFrame())
    MD = (pd.DataFrame(mac).groupby(["window", "floor", "kept", "macro_day"]).size().rename("events").reset_index()
          if mac else pd.DataFrame())
    return {"per_ticker_session": A, "time_of_day": T, "weekday": W, "macro_day": MD, "events_m4_d5": M,
            "d6_direction": D6, "pythia_loc": P}


FORBIDDEN = {"price", "size", "t_utc", "t_et", "L", "notional", "nbbo_bid", "nbbo_ask"}


def assert_aggregate(frames):
    for name, f in frames.items():
        bad = FORBIDDEN & set(map(str, getattr(f, "columns", [])))
        if bad:
            raise RuntimeError(f"{name} carries row-level columns {bad}; refusing to write")


def _read_parquet(globpat):
    files = sorted(glob.glob(globpat))
    if not files:
        raise SystemExit(f"no files match {globpat}")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _write(frames, out_dir, meta):
    assert_aggregate(frames)
    os.makedirs(out_dir, exist_ok=True)
    for k, f in frames.items():
        f.to_csv(os.path.join(out_dir, f"{k}.csv"), index=False)
    json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w"), indent=1, default=str)


def prepare_prints(raw, complete):
    """vendor rows -> D1-clean calibration prints of complete ticker-sessions. Returns the frame,
    the duplicate count, and the incomplete ticker-sessions dropped."""
    raw = raw[raw.ticker.isin(CORE8)]
    df, n_dup = from_vendor(raw)
    df = d1_clean(df)
    df, dropped = drop_incomplete(df, complete)
    return df, n_dup, dropped


def run_anchor(prints_glob, complete_csv, out_dir):
    raw = _read_parquet(prints_glob)
    df, n_dup, dropped = prepare_prints(raw, complete_set(complete_csv))
    raw = raw[raw.ticker.isin(CORE8)]
    t = pd.to_datetime(raw.executed_at, utc=True, format="ISO8601").dt.tz_convert("America/New_York").dt.date
    A, decision = anchor(df)
    comp = pd.read_csv(complete_csv, parse_dates=["session"])
    comp = comp[comp.session.dt.date.isin(CALIBRATION_DATES)]
    decision["dates_complete_for_all_8"] = int(comp.groupby("session").complete.apply(
        lambda x: all(_truthy(v) for v in x) and len(x) == len(CORE8)).sum())
    _write({"anchor_tau": A, "code_census": code_census(raw[in_calibration(t)])}, out_dir,
           {"calibration": CALIBRATION, "sessions_read": sorted({str(x) for x in df.session}),
            "duplicate_tracking_ids_dropped": n_dup, "incomplete_ticker_sessions_dropped": dropped, **decision})


def run(prints_glob, bars_glob, polygon_glob, adv_csv, va_csv, complete_csv, macro_csv, out_dir):
    if not TAU_FINAL:
        raise SystemExit("tau is not final: run `anchor` first and record SPINE's confirmation (amendment 4/4a)")
    raw = _read_parquet(prints_glob)
    build_set = build_complete_set(raw)
    lab_c = pd.read_csv(complete_csv)
    S, excluded, refusals = census_set(lab_c, build_set)        # amendment 6b: the intersection
    if refusals:
        raise SystemExit(refusal_message(refusals))
    df, n_dup, dropped = prepare_prints(raw, S)
    sess = pd.DataFrame(sorted(S), columns=["ticker", "session"]) if S else pd.DataFrame(columns=["ticker", "session"])
    census_all8 = int((sess.groupby("session").ticker.nunique() == len(CORE8)).sum()) if len(sess) else 0
    praw, poly_info = load_polygon(polygon_glob)                # amendment 7: Polygon unadjusted first
    braw, source_map = choose_bars(load_bars(bars_glob), praw)  # fixed by coverage, before any D5
    os.makedirs(out_dir, exist_ok=True)
    source_map.to_csv(os.path.join(out_dir, "bar_source_map.csv"), index=False)
    bars = bars_by_session(braw)
    adv_df = pd.read_csv(adv_csv, parse_dates=["session"])
    adv = {(r.ticker, r.session.date()): r.adv_dollars for r in adv_df.itertuples()}
    va = {}
    if va_csv != "-":
        v = pd.read_csv(va_csv, parse_dates=["session"])
        va = {(r.ticker, r.session.date()): (r.vah, r.val) for r in v.itertuples()}
    macro = set(pd.read_csv(macro_csv, parse_dates=["date"]).date.dt.date)
    frames = census(df, adv, bars, va, macro=macro)
    _write(frames, out_dir, {"calibration": CALIBRATION, "window_name": WINDOW_NAME,
                             "tau_pct": TAU_PCT, "tau_provenance": TAU_PROVENANCE,
                             "tau_confirmation": TAU_CONFIRMATION,
                             "seed": SEED, "n_shuffles": N_SHUFFLES, "keep_note": KEEP_LINE,
                             "pythia_label": PYTHIA_LABEL, "sessions_read": sorted({str(x) for x in df.session}),
                             "sessions_with_bars": len(bars), "bar_sessions_by_source": bar_sources(braw),  # chosen bars
                             "duplicate_tracking_ids_dropped": n_dup,
                             "incomplete_ticker_sessions_dropped": dropped,
                             "amendment_6b": "TRITON-FP-v1-AMENDMENT-6b-R-IV.1045.md d6b4a0b5...",
                             "amendment_7": "TRITON-FP-v1-AMENDMENT-7-R-IV.1054.md e7d96d47... (bars: Polygon "
                                            "unadjusted where it covers the ticker-session, else bars1m/)",
                             "bar_source_map_counts": source_map.source.value_counts().to_dict(),
                             "polygon_files": poly_info,
                             "census_set_ticker_sessions": len(S),
                             "census_dates_complete_for_all_8": census_all8,
                             "completeness_exclusions": excluded,
                             "completeness_exclusions_by_cause": pd.Series(
                                 [x["cause"] for x in excluded], dtype=object).value_counts().to_dict(),
                             "floor_counts": "post-D5 = kept by D4 AND D5-matched at tau "
                                             "(events_m4_d5: arm=real, kept=True, d5_matched); beside it: "
                                             "D5-matched over all real runs (kept True + False) and the "
                                             "post-D4 kept count (per_ticker_session)"})


# ── self-test on SYNTHETIC data only ────────────────────────────────────────────────────────────
def _synthetic_vendor(rng):
    """Vendor-format prints (F-README field names) and 1-minute bars, synthetic."""
    rows, brows, tid = [], [], 0
    sessions = [pd.Timestamp(d) for d in ("2026-09-02", "2026-09-03", "2026-08-20", "2026-09-28")]
    for sess in sessions:
        b0 = pd.Timestamp(sess.strftime("%Y-%m-%d") + " 13:30", tz="UTC")     # 09:30 ET (EDT)
        for tk in ("SPY", "NVDA", "XYZ"):
            def add(ts, px, sz, bid, ask, canceled="f", scc=None, tc=None, ext=None):
                nonlocal tid
                tid += 1
                rows.append({"ticker": tk, "executed_at": ts.isoformat(), "price": px, "size": sz,
                             "premium": px * sz, "nbbo_bid": bid, "nbbo_ask": ask, "canceled": canceled,
                             "sale_cond_codes": scc, "trade_code": tc, "ext_hour_sold_codes": ext,
                             "trade_settlement": "regular_settlement", "tracking_id": f"t{tid}",
                             "session_date": sess.strftime("%Y-%m-%d")})
            n = 1500
            tt = np.sort(rng.uniform(0, 6.5 * 3600, n))
            px = 500 + np.cumsum(rng.normal(0, 0.02, n))
            sz = rng.choice([100, 200, 300, 500, 700, 1100, 1300, 2500, 4100], n)
            for k in range(n):
                q = round(px[k], 2)
                add(b0 + pd.Timedelta(seconds=float(tt[k])), q, int(sz[k]), q - 0.03, q + 0.06)
            for k in range(4):                                # planted run, 11:00 ET, L = 501.25
                add(b0 + pd.Timedelta(minutes=90 + 2 * k), 501.25, 7777, 501.24, 501.26)
            for k in range(3):                                # planted M4 cadence
                add(b0 + pd.Timedelta(minutes=80 + 5 * k), 499.0 + k, 3333, 498.99 + k, 499.01 + k)
            add(b0 + pd.Timedelta(minutes=91), 501.25, 7777, 0, 0, canceled="t")     # D1: canceled
            for k in range(3):                                # D1: letter code 'B' (average price)
                add(b0 + pd.Timedelta(minutes=200 + k), 502.0, 8888, 0, 0, scc="@ B")
            for k in range(3):                                # D1: word form 'qualified_contingent_trade'
                add(b0 + pd.Timedelta(minutes=210 + k), 503.0, 9999, 0, 0, tc="qualified_contingent_trade")
            for k in range(3):                                # D1: extended-hours code
                add(b0 + pd.Timedelta(minutes=220 + k), 504.0, 6666, 0, 0, ext="extended_hours_trade")
            add(b0 + pd.Timedelta(minutes=240), 506.0, 4444, 0, 0, scc="6")      # 4c: correction
            add(b0 + pd.Timedelta(minutes=241), 506.0, 4445, 0, 0, scc="@ 9")    # 4c: correction
            add(b0 + pd.Timedelta(minutes=242), 506.0, 4446, 0, 0, scc="L")      # 4c: sold last
            add(b0 + pd.Timedelta(minutes=243), 506.0, 4447, 0, 0, tc="sold_last")
            for k in range(2):                                # kept: 'F' sweep is not a D1 code
                add(b0 + pd.Timedelta(minutes=230 + k * 3), 505.0, 5555, 504.99, 505.01, scc="F")
            rows.append(dict(rows[-1]))                       # an exact duplicate tracking_id
            src = "uw" if sess < pd.Timestamp("2026-09-12") else "yfinance"
            for m in range(-330, 630):                         # 04:00-19:59 ET, as F-README states
                ts = b0 + pd.Timedelta(minutes=m)
                if m in (92, 95):
                    brows.append((tk, ts, 501.60, 501.25, 501.40, src))
                elif 80 <= m <= 110:
                    brows.append((tk, ts, 501.70, 501.35, 501.50, src))
                elif -12 <= m < 0:                            # pre-market bars that would break D6
                    brows.append((tk, ts, 501.30, 499.00, 499.00, src))
                else:
                    brows.append((tk, ts, 500.5, 499.5, 500.0, src))
    return pd.DataFrame(rows), pd.DataFrame(brows, columns=list(BAR_COLUMNS)), sessions


def _write_readme_bars(braw, root):
    """Write synthetic bars exactly in the F-README layout: <root>/<YYYY-MM-DD>/<TICKER>.parquet,
    tz-aware ET index, Open/High/Low/Close/Adj Close/Volume/Dividends/Stock Splits/Capital Gains/source."""
    t = pd.to_datetime(braw.t_utc, utc=True).dt.tz_convert("America/New_York")
    b = braw.assign(t_et=t, d=t.dt.strftime("%Y-%m-%d"))
    for (d, tk), g in b.groupby(["d", "ticker"]):
        os.makedirs(os.path.join(root, d), exist_ok=True)
        out = pd.DataFrame({"Open": g.close.values, "High": g.high.values, "Low": g.low.values,
                            "Close": g.close.values, "Adj Close": g.close.values, "Volume": 1000.0,
                            "Dividends": 0.0, "Stock Splits": 0.0, "Capital Gains": 0.0,
                            "source": g.source.values}, index=pd.DatetimeIndex(g.t_et).tz_convert("America/New_York"))
        out.to_parquet(os.path.join(root, d, f"{tk}.parquet"))


def _write_polygon(root, tk, session, lows_at, base=500.0, adjusted=False, ticker_in_file=None):
    """Synthetic bars in BUILD's bars1m_polygon layout (scripts/polygon_1m_export.py): one file per
    ticker and adjustment, 04:00-19:59 ET, timestamp_utc = bar open. lows_at = {"HH:MM": low}."""
    et = pd.date_range(f"{session} 04:00", f"{session} 19:59", freq="1min", tz="America/New_York")
    low = np.full(len(et), base)
    for hm, v in lows_at.items():
        low[et.strftime("%H:%M") == hm] = v
    df = pd.DataFrame({"open": base + 0.2, "high": base + 0.5, "low": low, "close": base + 0.2, "volume": 100.0,
                       "vwap": base + 0.2, "transactions": 10, "timestamp_utc": et.tz_convert("UTC"),
                       "timestamp_et": et, "session_et": et.strftime("%Y-%m-%d"),
                       "ticker": ticker_in_file or tk, "source": "polygon_v2_aggs_1minute", "adjusted": adjusted})
    path = os.path.join(root, f"{tk}_adjusted_{'true' if adjusted else 'false'}.parquet")
    if os.path.exists(path):
        df = pd.concat([pd.read_parquet(path), df], ignore_index=True)
    os.makedirs(root, exist_ok=True)
    df.to_parquet(path, index=False)


def selftest():
    import tempfile
    set_window("calibration")                    # the self-test always runs on the calibration window
    rng = np.random.default_rng(7)
    raw, braw, sessions = _synthetic_vendor(rng)
    checks = {}
    complete = {(tk, s.date()) for tk in CORE8 for s in sessions} - {("NVDA", date(2026, 9, 3))}
    df, n_dup, dropped = prepare_prints(raw, complete)
    checks["XYZ (not CORE8) dropped"] = "XYZ" not in set(df.ticker)
    checks["seal session 2026-08-20 dropped"] = date(2026, 8, 20) not in set(df.session)
    checks["reserve session 2026-09-28 dropped at load"] = date(2026, 9, 28) not in set(df.session)
    checks["incomplete ticker-session (NVDA 09-03) dropped and listed"] = \
        ("NVDA", date(2026, 9, 3)) not in set(zip(df.ticker, df.session)) and "NVDA 2026-09-03" in dropped
    checks["duplicate tracking_id dropped (one per CORE8 ticker-session: 2 x 4 = 8)"] = n_dup == 8
    checks["D1: canceled 't' print (7,777 at 11:01 ET) dropped"] =         not ((df["size"] == 7777) & (df.t_et.dt.hour == 11) & (df.t_et.dt.minute == 1)).any()
    checks["D1: letter code 'B' dropped"] = not (df["size"] == 8888).any()
    checks["D1: word form 'qualified_contingent_trade' dropped"] = not (df["size"] == 9999).any()
    checks["D1: ext_hour_sold_codes non-empty dropped"] = not (df["size"] == 6666).any()
    checks["non-D1 code 'F' (sweep) kept"] = bool((df["size"] == 5555).any())
    checks["4c: corrections 6 / 9 and sold-last L (letter and word) dropped"] = \
        not df["size"].isin([4444, 4445, 4446, 4447]).any()
    checks["4c: quantiles are linear (median of 1,2,3,10 = 2.5; p75 = 4.75)"] = \
        pd.Series([1.0, 2, 3, 10]).quantile(0.5, interpolation="linear") == 2.5 and \
        pd.Series([1.0, 2, 3, 10]).quantile(0.75, interpolation="linear") == 4.75
    checks["reserve bars dropped at load"] = not any(k[1] == date(2026, 9, 28) for k in bars_by_session(braw))
    A0, dec = anchor(df)
    checks["A0: exact median and p75 present"] = {"median_spread", "p75_spread"} <= set(A0.columns)
    checks["A0: spreads 0.09 noise -> p75 0.09; tau 0.10 covers p75 on both names"] = \
        dec["names_where_tau_covers_p75"] == 2 and dec["decision_statistic"] == "p75"
    checks["A0: provenance recorded"] = dec["tau_provenance"] == TAU_PROVENANCE
    checks["A0 is aggregate only"] = not (FORBIDDEN & set(A0.columns))
    cc = code_census(raw)
    checks["code census: aggregate value counts, D1 flags right"] = \
        bool(cc[(cc.field == "sale_cond_codes") & (cc.value == "@ B")].d1_excluded.all()) and \
        not bool(cc[(cc.field == "sale_cond_codes") & (cc.value == "F")].d1_excluded.any()) and \
        bool(cc[(cc.field == "trade_code") & (cc.value == "qualified_contingent_trade")].d1_excluded.all())
    bars = bars_by_session(braw)
    adv = {(tk, s.date()): 2_500_000_000.0 for tk in CORE8 for s in sessions}
    va = {(tk, s.date()): (502.0, 501.0) for tk in CORE8 for s in sessions}
    macro = {date(2026, 9, 3)}
    out = census(df, adv, bars, va, n_shuffles=200, macro=macro)
    A = out["per_ticker_session"]
    frun = A[(A.floor == "FRUN") & (A.window == "NOGATE")]
    checks["planted run found and kept (FRUN, NOGATE)"] = bool((frun.real_runs >= 1).all() and (frun.kept_runs >= 1).all())
    checks["kept never alone: shuffled mean, excess and the 29% line present"] = \
        {"shuffled_mean", "excess_real_minus_shuffled", "kept_note"} <= set(A.columns) and (A.kept_note == KEEP_LINE).all()
    M = out["events_m4_d5"]
    full = M[(M.arm == "real") & (M.kept == True) & (M.floor == "FADV") & (M.window == "NOGATE")]  # noqa: E712
    checks["post-D5 (kept AND D5-matched) count available for the floor"] = bool(len(full) and full.d5_matched.sum() >= 1)
    allr = M[(M.arm == "real") & (M.floor == "FADV") & (M.window == "NOGATE")]
    checks["beside it: D5-matched over ALL real runs (kept and not kept)"] = \
        bool(len(allr) and allr.d5_matched.sum() >= full.d5_matched.sum())
    D6 = out["d6_direction"]
    b = D6[(D6.arm == "real") & (D6.floor == "FADV") & (D6.window == "NOGATE") & (D6.tolerance == "tau")]
    checks["D6 = BUYER on the planted run"] = bool(len(b) and (b[b.d6 == "BUYER"].events.sum() >= 1))
    checks["D6 1-tick sensitivity line present"] = (D6.tolerance == "1tick_sensitivity").any()
    P = out["pythia_loc"]
    pr = P[(P.arm == "real") & (P.floor == "FADV") & (P.window == "NOGATE") & (P.d6 == "BUYER")]
    checks["PYTHIA-LOC: BUYER at L=501.25 vs VAL 501.0 = 'edge', LONG, stamped"] = \
        bool(len(pr) and set(pr.reading) == {"LONG"} and (pr[pr.location == "edge"].readings.sum() >= 1)
             and (P.label == PYTHIA_LABEL).all())
    MD = out["macro_day"]
    checks["macro-day tag counts present (09-03 tagged)"] = bool(len(MD) and MD.macro_day.any())
    checks["shuffled-control events present"] = (M.arm == "shuffled").any()
    try:
        assert_aggregate(out)
        checks["census outputs are aggregate only"] = True
    except RuntimeError:
        checks["census outputs are aggregate only"] = False
    try:
        assert_aggregate({"x": pd.DataFrame({"nbbo_bid": [1.0]})})
        checks["the row-level guard refuses an NBBO column"] = False
    except RuntimeError:
        checks["the row-level guard refuses an NBBO column"] = True
    # end to end through Parquet (pyarrow), the way QUERY will run `anchor`
    with tempfile.TemporaryDirectory() as td:
        for tk, g in raw.groupby("ticker"):
            os.makedirs(os.path.join(td, tk), exist_ok=True)
            g.to_parquet(os.path.join(td, tk, "202609.parquet"), index=False)
        comp = pd.DataFrame([{"ticker": t, "session": str(s), "complete": (t, s) in complete}
                             for t in CORE8 for s in [x.date() for x in sessions]])
        comp.to_csv(os.path.join(td, "complete.csv"), index=False)
        run_anchor(os.path.join(td, "*", "*.parquet"), os.path.join(td, "complete.csv"), os.path.join(td, "out"))
        meta = json.load(open(os.path.join(td, "out", "meta.json")))
        checks["end-to-end anchor via Parquet: runs, reads calibration only, writes aggregates"] = \
            meta["sessions_read"] == ["2026-09-02", "2026-09-03"] and os.path.exists(os.path.join(td, "out", "code_census.csv"))
    checks["tau is final and its confirmation recorded (R-IV.1015)"] = TAU_FINAL is True and \
        TAU_CONFIRMATION["flagged_names"] == ["MSFT", "SMH", "TSLA"]
    # amendment 6-final: b2 / SUSPECT / settlement / BUILD cross-check
    def walk(q, first_utc, n, step_min, last_rows, cap=500, gap_at=None):
        out, oldest, hi = [], None, pd.Timestamp(first_utc, tz="UTC")
        for j in range(n):
            lo = hi - pd.Timedelta(minutes=step_min)
            cur = "" if j == 0 else (oldest + pd.Timedelta(minutes=30 if j == gap_at else 0)).isoformat()
            out.append({"ticker": "SPY", "query_date": q, "page_no": j + 1, "older_than_cursor": cur,
                        "row_count": last_rows if j == n - 1 else cap,
                        "min_executed_at": lo.isoformat(), "max_executed_at": hi.isoformat()})
            oldest = lo if oldest is None else min(oldest, lo)
            hi = lo
        return out
    # 09-15: walk ends SHORT with earliest print 08:00:16 UTC = 04:00:16 ET -> b2 (complete)
    w_b2 = walk("2026-09-15", "2026-09-15 23:59:00", 4, 958.733333 / 4, 137)   # reach 08:00:16 UTC
    # 09-21 shape (synthetic; the real 09-21 was a deficient EXPORT, R-IV.1019(c)): short final page,
    # earliest print 15:20:57 ET -> SUSPECT, NOT complete
    w_sus = walk("2026-09-21", "2026-09-21 23:59:00", 2, 278.05 / 2, 53)      # reach 19:20:57 UTC = 15:20:57 ET
    # 09-22: a short page but the prefix BREAKS before it (cursor gap) -> not exhausted -> none
    w_brk = walk("2026-09-22", "2026-09-22 23:59:00", 6, 240, 90, gap_at=3)
    # 09-23: the cap is READ: pages of 300 with a final page of 200 is exhaustion even though 300 < 500
    w_cap = walk("2026-09-23", "2026-09-23 23:59:00", 4, 958.733333 / 4, 200, cap=300)
    C6, info6 = build_complete(pd.DataFrame(w_b2 + w_sus + w_brk + w_cap))
    r6 = C6[C6.ticker == "SPY"].set_index("session")
    checks["A6: exhausted walk reaching 04:00:16 ET is complete via b2"] = \
        bool(r6.loc["2026-09-15", "complete"]) and r6.loc["2026-09-15", "route"] == "b2"
    checks["A6: 09-21-shaped walk (short page, starts 15:20 ET) is SUSPECT, not complete"] = \
        r6.loc["2026-09-21", "route"] == "SUSPECT" and not bool(r6.loc["2026-09-21", "complete"])
    checks["A6: a cursor gap before the short page is not exhaustion (route none)"] = \
        r6.loc["2026-09-22", "route"] == "none"
    checks["A6: the cap is read from stored pages (300-row pages, 200 final -> b2)"] = \
        r6.loc["2026-09-23", "route"] == "b2" and int(r6.loc["2026-09-23", "cap_used"]) == 300
    checks["A6: SUSPECT counted separately"] = info6["suspect_ticker_sessions"] == 1
    checks["R-IV.1027: the same-date walk's break is recorded (cursor_gap, 1800 s)"] = \
        r6.loc["2026-09-22", "same_date_break"] == "cursor_gap" and \
        float(r6.loc["2026-09-22", "same_date_cursor_gap_s"]) == 1800.0 and \
        r6.loc["2026-09-15", "same_date_break"] == "" and r6.loc["2026-09-15", "same_date_route"] == "b2"
    xg = crosscheck_table(C6, {("SPY", date(2026, 9, 22))}).set_index(["ticker", "session"])
    checks["R-IV.1027: BUILD credits, LAB cursor gap -> labelled cursor continuity"] = \
        xg.loc[("SPY", "2026-09-22"), "cause"] == "BUILD credits; LAB refuses on cursor continuity (> 1 s)"
    lab_sd = pd.DataFrame([{"ticker": "SPY", "session": "2026-09-02", "complete": True, "route": "b1",
                            "best_query_date": "2026-09-03", "same_date_route": "b2", "same_date_break": ""}])
    checks["R-IV.1027: LAB-only with the same-date walk complete is NOT the later-query-date cause"] = \
        crosscheck_table(lab_sd, set()).set_index(["ticker", "session"]).loc[
            ("SPY", "2026-09-02"), "cause"] == "LAB complete from Q = E; BUILD not"
    st = raw.copy()
    st.loc[st.index[:5], "trade_settlement"] = "seller"
    st.loc[st.index[5:8], "trade_settlement"] = "cash"
    nv, _ = from_vendor(st[st.ticker.isin(CORE8)])
    checks["A6: non-regular settlement (seller / cash) is excluded by D1"] = \
        int(nv.excluded_condition.sum()) - int(from_vendor(raw[raw.ticker.isin(CORE8)])[0].excluded_condition.sum()) \
        == int(st.loc[st.index[:8]].ticker.isin(CORE8).sum())
    cc6 = code_census(st)
    checks["A6: code census flags seller / cash, keeps regular"] = \
        bool(cc6[(cc6.field == "trade_settlement") & cc6.value.isin(["seller", "cash"])].d1_excluded.all()) and \
        not bool(cc6[(cc6.field == "trade_settlement") & (cc6.value == "regular_settlement")].d1_excluded.any())
    bset = {("SPY", date(2026, 9, 2))}
    lab_ok = pd.DataFrame([{"ticker": "SPY", "session": "2026-09-02", "complete": True}])
    lab_bad = pd.DataFrame([{"ticker": "SPY", "session": "2026-09-02", "complete": True},
                            {"ticker": "QQQ", "session": "2026-09-02", "complete": True}])
    checks["A6: cross-check agrees when LAB and BUILD match"] = cross_check(lab_ok, bset) == []
    checks["A6: cross-check lists a disagreement (run REFUSES on it)"] = \
        cross_check(lab_bad, bset) == ["QQQ 2026-09-02: LAB=True BUILD=False"]
    lab_q = pd.DataFrame([{"ticker": "SPY", "session": "2026-09-02", "complete": True, "route": "b1",
                           "best_query_date": "2026-09-02"},
                          {"ticker": "QQQ", "session": "2026-09-02", "complete": True, "route": "b1",
                           "best_query_date": "2026-09-03"},
                          {"ticker": "IWM", "session": "2026-09-02", "complete": False, "route": "none",
                           "best_query_date": ""}])
    xt = crosscheck_table(lab_q, bset | {("IWM", date(2026, 9, 2))}).set_index(["ticker", "session"])
    checks["A6 crosscheck: one row per CORE8 x calibration date"] = len(xt) == len(CORE8) * len(CALIBRATION_DATES)
    checks["A6 crosscheck: LAB credited by a later Q is named as the cause"] = \
        xt.loc[("QQQ", "2026-09-02"), "cause"] == "LAB credits via a later query date; BUILD does not"
    checks["A6 crosscheck: BUILD-only complete is named with LAB's route"] = \
        xt.loc[("IWM", "2026-09-02"), "cause"].startswith("UNLABELLED: BUILD credits")
    checks["A6 crosscheck: agreement carries no cause"] = \
        bool(xt.loc[("SPY", "2026-09-02"), "agree"]) and xt.loc[("SPY", "2026-09-02"), "cause"] == ""
    # amendment 6b: the census set and one test per row of sec. 2
    d2 = "2026-09-02"
    lab6 = pd.DataFrame([
        {"ticker": "SPY", "session": d2, "complete": True, "same_date_route": "b1", "same_date_break": "", "best_query_date": d2},
        {"ticker": "QQQ", "session": d2, "complete": True, "best_query_date": "2026-09-03"},     # old format, later Q
        {"ticker": "IWM", "session": d2, "complete": False, "same_date_route": "none", "same_date_break": "cursor_gap"},
        {"ticker": "AAPL", "session": d2, "complete": True, "same_date_route": "b1", "same_date_break": "", "best_query_date": d2}])
    b6 = {("SPY", date(2026, 9, 2)), ("IWM", date(2026, 9, 2)), ("AAPL", date(2026, 9, 2))}
    S6, ex6, rf6 = census_set(lab6, b6)
    checks["6b sec. 1: census set = BOTH rules complete (SPY, AAPL); excluded never enter it"] = \
        S6 == {("SPY", date(2026, 9, 2)), ("AAPL", date(2026, 9, 2))}
    checks["6b sec. 2 row 1: later query date -> excluded and logged with its cause"] = \
        {"ticker": "QQQ", "session": d2, "cause": EXCLUDED_CAUSES[0]} in ex6
    checks["6b sec. 2 row 2: cursor continuity (> 1 s) -> excluded and logged"] = \
        {"ticker": "IWM", "session": d2, "cause": EXCLUDED_CAUSES[1]} in ex6 and len(ex6) == 2 and rf6 == []
    lab6u = pd.concat([lab6, pd.DataFrame([{"ticker": "NVDA", "session": d2, "complete": False,
                                             "same_date_route": "none", "same_date_break": "page_gap"}])])
    _, _, rfu = census_set(lab6u, b6 | {("NVDA", date(2026, 9, 2))})
    checks["6b sec. 2 row 3: UNLABELLED (BUILD credits, LAB page gap) -> refuse"] = \
        len(rfu) == 1 and rfu[0]["ticker"] == "NVDA" and rfu[0]["cause"].startswith("UNLABELLED")
    _, _, rfl = census_set(lab6, b6 - {("AAPL", date(2026, 9, 2))})
    msg = refusal_message(rfl)
    checks["6b sec. 2 row 4: export lag -> refuse, and the message NAMES the ticker-session"] = \
        len(rfl) == 1 and rfl[0]["cause"] == EXPORT_LAG and "EXPORT LAG" in msg and "AAPL 2026-09-02" in msg
    checks["6b: unknown causes refuse by default"] = disposition("something new") == "refuse" and disposition("") == ""
    with tempfile.TemporaryDirectory() as tdx:
        # export holds SPY 09-02 only: LAB's QQQ 09-02 (True, via a later Q) has no BUILD row -> 1
        # disagreement, which 6b EXCLUDES -> exit 0
        pd.DataFrame({"ticker": ["SPY", "SPY"], "session_date": ["2026-09-02", "2026-09-02"],
                      "price": [1.0, 2.0]}).to_parquet(os.path.join(tdx, "a.parquet"), index=False)
        lab_q.to_csv(os.path.join(tdx, "c.csv"), index=False)
        rc_ = run_crosscheck(os.path.join(tdx, "*.parquet"), os.path.join(tdx, "c.csv"), os.path.join(tdx, "x.csv"))
        xo = pd.read_csv(os.path.join(tdx, "x.csv"))
        checks["6b crosscheck e2e: one later-Q disagreement is EXCLUDED, exit 0, no price out"] = \
            rc_ == 0 and int((~xo.agree).sum()) == 1 and int(xo.build.sum()) == 1 and "price" not in xo.columns \
            and xo[~xo.agree].disposition.tolist() == ["excluded"]
        # export lag: LAB's same-date walk complete, BUILD's export lacks it -> refuse, exit 1
        lab_lag = lab_q.assign(same_date_route=["b1", "b1", "none"], best_query_date=["2026-09-02", "2026-09-02", ""])
        lab_lag.to_csv(os.path.join(tdx, "c.csv"), index=False)
        rc_ = run_crosscheck(os.path.join(tdx, "*.parquet"), os.path.join(tdx, "c.csv"), os.path.join(tdx, "x.csv"))
        xo = pd.read_csv(os.path.join(tdx, "x.csv"))
        checks["6b crosscheck e2e: an export lag is labelled, disposition refuse, exit 1"] = \
            rc_ == 1 and xo[~xo.agree].cause.tolist() == [EXPORT_LAG] and xo[~xo.agree].disposition.tolist() == ["refuse"]
        pd.DataFrame({"ticker": ["SPY"], "price": [1.0]}).to_parquet(os.path.join(tdx, "a.parquet"), index=False)
        try:
            run_crosscheck(os.path.join(tdx, "*.parquet"), os.path.join(tdx, "c.csv"), os.path.join(tdx, "x.csv"))
            checks["A6 crosscheck e2e: an export without session_date refuses"] = False
        except SystemExit:
            checks["A6 crosscheck e2e: an export without session_date refuses"] = True
    try:
        build_complete_set(raw.drop(columns="session_date"))
        checks["A6: no session_date in the export -> refuse"] = False
    except SystemExit:
        checks["A6: no session_date in the export -> refuse"] = True
    checks["17 calibration executed dates (Labor Day excluded)"] = len(CALIBRATION_DATES) == 17
    # amendment 5: files that cross session boundaries the way BUILD found
    base = []
    days = [date(2026, 8, 27), date(2026, 8, 28), date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 2),
            date(2026, 9, 3)]
    for d in days:
        b0 = pd.Timestamp(d.isoformat() + " 13:30", tz="UTC")
        for k in range(50):
            base.append({"ticker": "SPY", "executed_at": (b0 + pd.Timedelta(minutes=5 * k)).isoformat(),
                         "price": 500.0, "size": 100 + k, "premium": 5e4, "nbbo_bid": 499.99, "nbbo_ask": 500.01,
                         "canceled": "f", "sale_cond_codes": None, "trade_code": None,
                         "ext_hour_sold_codes": None, "trade_settlement": "regular_settlement",
                         "tracking_id": f"{d}-{k}"})
    B = pd.DataFrame(base)
    B["E"] = pd.to_datetime(B.executed_at, utc=True).dt.tz_convert("America/New_York").dt.date
    files = []
    for qi, q in enumerate(days[2:], start=2):          # each query file holds its date + the 2 before
        files.append(B[B.E.isin(days[qi - 2:qi + 1])].drop(columns="E").assign(_q=q))
    X = pd.concat(files, ignore_index=True)
    n_dup_expected = len(X) - X.tracking_id.nunique()
    comp_all = {("SPY", d) for d in days}
    dfx, ndx, _ = prepare_prints(X.drop(columns="_q"), comp_all)
    checks["A5: dedup across all files removes exactly the cross-file repeats"] = ndx == n_dup_expected
    checks["A5: grouping is by EXECUTED date (09-01, 09-02, 09-03 read; not the file's date)"] = \
        sorted({str(x) for x in dfx.session}) == ["2026-09-01", "2026-09-02", "2026-09-03"]
    checks["A5: prints executed 08-27..08-31 excluded although they sit in 09-01..09-03 files"] = \
        not any(x < date(2026, 9, 1) for x in dfx.session)
    # walk metadata: one good walk, one broken cursor, one that stops short
    def pg(q, n, first_min, step_min, break_at=None, rows=50):
        out, oldest = [], None
        hi = pd.Timestamp(first_min, tz="UTC")
        for j in range(n):
            lo = hi - pd.Timedelta(minutes=step_min)
            cur = "" if j == 0 else (oldest + pd.Timedelta(minutes=30 if j == break_at else 0)).isoformat()
            out.append({"ticker": "SPY", "query_date": q, "page_no": j + 1, "older_than_cursor": cur,
                        "row_count": rows, "min_executed_at": lo.isoformat(), "max_executed_at": hi.isoformat()})
            oldest = lo if oldest is None else min(oldest, lo)
            hi = lo
        return out
    wp = pd.DataFrame(
        pg("2026-09-03", 40, "2026-09-03 23:59", 120)                 # 80 h back: 08-31 19:59 UTC, before 09-01 04:00 ET
        + pg("2026-09-10", 30, "2026-09-10 23:59", 120, break_at=3)   # broken at page 3: reach only ~09-10 20:00
        + pg("2026-09-16", 3, "2026-09-16 23:59", 60))                # stops short: never before 09-16 04:00
    C, info = build_complete(wp)
    spy = C[C.ticker == "SPY"].set_index("session").complete
    short = build_complete(pd.DataFrame(pg("2026-09-03", 30, "2026-09-03 23:59", 120)))[0]
    sq = short.set_index(["ticker", "session"])
    checks["A5 reach (diagnostic): a 60-h walk stops at 09-01 07:59 ET -> any-Q route none for 09-01, b1 for 09-02"] = \
        sq.any_q_route[("SPY", "2026-09-01")] == "none" and sq.any_q_route[("SPY", "2026-09-02")] == "b1"
    checks["6b: that 09-03 walk credits ONLY 09-03 (no walk for 09-02 -> 09-02 not complete)"] = \
        bool(sq.complete[("SPY", "2026-09-03")]) and not bool(sq.complete[("SPY", "2026-09-02")]) \
        and sq.same_date_route[("SPY", "2026-09-02")] == "no_walk"
    anyq = C[C.ticker == "SPY"].set_index("session").any_q_route
    checks["A5 reach (diagnostic): the 80-h walk from 09-03 reaches 09-01, 09-02, 09-03 (any-Q b1)"] = \
        all(anyq[x] == "b1" for x in ("2026-09-01", "2026-09-02", "2026-09-03"))
    checks["6b: ... but completes only 09-03, its own date"] = \
        bool(spy["2026-09-03"]) and not (spy["2026-09-01"] or spy["2026-09-02"])
    checks["A5: a cursor gap breaks the walk (09-08..09-10 not complete)"] = \
        not (spy["2026-09-08"] or spy["2026-09-09"] or spy["2026-09-10"])
    checks["A5: a walk that never reaches 04:00 ET leaves the date incomplete (09-16)"] = not spy["2026-09-16"]
    checks["A5: other names without walks are incomplete; trigger counts all-8 dates (0)"] = \
        not C[C.ticker == "QQQ"].complete.any() and info["dates_complete_for_all_8"] == 0
    checks["A5: cursor parsing accepts epoch ms and ISO"] = \
        _instant("1789000000000") is not None and _instant("2026-09-03T12:00:00+00:00") is not None
    # bars read in the README layout; extended hours present on disk but clipped to RTH
    with tempfile.TemporaryDirectory() as td:
        _write_readme_bars(braw, os.path.join(td, "bars1m"))
        lb = load_bars(os.path.join(td, "bars1m", "*", "*.parquet"))
        checks["README bars: ticker from file name, tz-aware ET index read, XYZ skipped"] = \
            set(lb.ticker) == {"SPY", "NVDA"} and len(lb) > 0
        bs = bars_by_session(lb)
        k = ("SPY", date(2026, 9, 2))
        checks["README bars: extended hours on disk (~960 rows), clipped to 390 RTH bars"] = \
            (lb[(lb.ticker == "SPY")].shape[0] // 4 >= 900) and len(bs[k][0]) == 390
        checks["README bars: source tally exact (2 names x 2 calibration sessions, all uw)"] = \
            bar_sources(lb) == {"uw": 4}
        # an event at 09:31 ET with L = 499.00: only the clipped-off pre-market bars (09:18-09:29)
        # have lows at 499.00; the RTH bars' lows are 499.50. With the clip, D5 must NOT match.
        d5, d6 = lit(bs[k], 9 * 3600 + 31 * 60, 499.00, 0.10)
        checks["pre-market bars cannot reach the D5/D6 window (clip holds)"] = d5 is False
        s_, hi, lo, cl = bs[k]
        checks["no bar before 09:30 ET survives the clip"] = float(s_.min()) >= 9.5 * 3600
        # amendment 7: Polygon unadjusted where it covers (T, E), else bars1m/; fixed by coverage
        pr = os.path.join(td, "bars1m_polygon")
        _write_polygon(pr, "SPY", "2026-09-04", {"10:00": 499.00, "10:02": 499.00})   # Polygon ONLY (no bars1m/)
        _write_polygon(pr, "SPY", "2026-09-02", {"11:00": 488.00, "11:02": 488.00})   # both sources hold 09-02
        _write_polygon(pr, "SPY", "2026-09-04", {}, base=400.0, adjusted=True)          # never read
        pb, pinfo = load_polygon(os.path.join(pr, "*.parquet"))
        checks["A7: only *_adjusted_false files are read (adjusted_true ignored)"] = \
            [x["file"] for x in pinfo] == ["SPY_adjusted_false.parquet"] and set(pb.source) == {"polygon"} \
            and float(pb.low.min()) == 488.00
        chosen, smap = choose_bars(lb, pb)
        sm = smap.set_index(["ticker", "session"]).source
        checks["A7: source map -- Polygon-only date -> polygon; both -> polygon; bars1m-only -> bars1m; else none"] = \
            sm[("SPY", "2026-09-04")] == "polygon" and sm[("SPY", "2026-09-02")] == "polygon" \
            and sm[("NVDA", "2026-09-02")] == "bars1m" and sm[("QQQ", "2026-09-02")] == "none" \
            and set(smap.columns) == {"ticker", "session", "source"}
        bs7 = bars_by_session(chosen)
        k4 = ("SPY", date(2026, 9, 4))
        d5_7, _ = lit(bs7.get(k4), 10 * 3600 + 60, 499.00, 0.10)
        d5_old, cls_old = lit(bars_by_session(lb).get(k4), 10 * 3600 + 60, 499.00, 0.10)
        checks["A7: a date present ONLY in Polygon matches (D5 True); bars1m/ alone gives NO_BARS"] = \
            d5_7 is True and d5_old is None and cls_old == "NO_BARS" and len(bs7[k4][0]) == 390
        d5_both, _ = lit(bs7.get(k), 11 * 3600 + 60, 488.00, 0.10)
        d5_r1, _ = lit(bars_by_session(lb).get(k), 11 * 3600 + 60, 488.00, 0.10)
        checks["A7: on a date both hold, Polygon's bars are used and never mixed with bars1m/"] = \
            d5_both is True and d5_r1 is False and len(bs7[k][0]) == 390
        checks["A7: NVDA (no Polygon file) keeps its bars1m/ bars"] = \
            len(bs7[("NVDA", date(2026, 9, 2))][0]) == len(bars_by_session(lb)[("NVDA", date(2026, 9, 2))][0])
        bad = os.path.join(td, "poly_bad")
        _write_polygon(bad, "QQQ", "2026-09-04", {}, ticker_in_file="SPY")
        for nm, pat in (("a file holding another ticker", os.path.join(bad, "*.parquet")),
                        ("no Polygon file at all", os.path.join(td, "nowhere", "*.parquet"))):
            try:
                load_polygon(pat)
                checks[f"A7: refuses on {nm}"] = False
            except SystemExit:
                checks[f"A7: refuses on {nm}"] = True
        bad2 = os.path.join(td, "poly_bad2")
        _write_polygon(bad2, "SPY", "2026-09-04", {}, adjusted=True)
        os.replace(os.path.join(bad2, "SPY_adjusted_true.parquet"), os.path.join(bad2, "SPY_adjusted_false.parquet"))
        try:
            load_polygon(os.path.join(bad2, "*.parquet"))
            checks["A7: refuses on adjusted=True rows inside an unadjusted file"] = False
        except SystemExit:
            checks["A7: refuses on adjusted=True rows inside an unadjusted file"] = True
        # end to end: `run` through Parquet with tau forced final inside the test only
        complete_e2e = {k for k in complete if k[0] in set(raw.ticker)}   # only names the export holds
        exp = raw[[(t_, pd.Timestamp(d_).date()) in complete_e2e for t_, d_ in zip(raw.ticker, raw.session_date)]]
        for tk, g in exp.groupby("ticker"):                  # BUILD exports complete sessions only
            os.makedirs(os.path.join(td, "dp", tk), exist_ok=True)
            g.to_parquet(os.path.join(td, "dp", tk, "202609.parquet"), index=False)
        cal_e2e = sorted(k for k in complete_e2e if k[1] in CALIBRATION_DATES)
        gap_pair = [k for k in cal_e2e if sum(1 for x in cal_e2e if x[1] == k[1]) >= 2][0]   # its date stays read
        # 6b: BUILD exports gap_pair, LAB's same-date walk has a cursor gap -> excluded
        pd.DataFrame([{"ticker": t_, "session": str(x.date()),
                       "complete": (t_, x.date()) in complete_e2e and (t_, x.date()) != gap_pair,
                       "same_date_route": "none" if (t_, x.date()) == gap_pair else "",
                       "same_date_break": "cursor_gap" if (t_, x.date()) == gap_pair else ""}
                      for t_ in CORE8 for x in sessions]).to_csv(os.path.join(td, "complete.csv"), index=False)
        pd.DataFrame([{"ticker": t_, "session": str(x.date()), "adv_dollars": 2.5e9}
                      for t_ in CORE8 for x in sessions]).to_csv(os.path.join(td, "adv.csv"), index=False)
        pd.DataFrame([{"ticker": t_, "session": str(x.date()), "vah": 502.0, "val": 501.0}
                      for t_ in CORE8 for x in sessions]).to_csv(os.path.join(td, "va.csv"), index=False)
        pd.DataFrame({"date": ["2026-09-03"], "event": ["initial_claims"], "source": ["test"]}).to_csv(
            os.path.join(td, "macro.csv"), index=False)
        g_ = globals()
        saved = (g_["TAU_FINAL"], g_["N_SHUFFLES"])
        g_["TAU_FINAL"], g_["N_SHUFFLES"] = True, 100
        try:
            run(os.path.join(td, "dp", "*", "*.parquet"), os.path.join(td, "bars1m", "*", "*.parquet"),
                os.path.join(td, "bars1m_polygon", "*.parquet"),
                os.path.join(td, "adv.csv"), os.path.join(td, "va.csv"), os.path.join(td, "complete.csv"),
                os.path.join(td, "macro.csv"), os.path.join(td, "out"))
        finally:
            g_["TAU_FINAL"], g_["N_SHUFFLES"] = saved
        meta = json.load(open(os.path.join(td, "out", "meta.json")))
        files = set(os.listdir(os.path.join(td, "out")))
        checks["end-to-end `run` via Parquet: all outputs written, calibration only"] = \
            {"per_ticker_session.csv", "events_m4_d5.csv", "d6_direction.csv", "pythia_loc.csv",
             "macro_day.csv"} <= files and meta["sessions_read"] == ["2026-09-02", "2026-09-03"]
        checks["end-to-end `run`: bar sessions by source recorded"] = bool(meta["bar_sessions_by_source"])
        sm_e2e = pd.read_csv(os.path.join(td, "out", "bar_source_map.csv"))
        checks["A7 e2e: source map written (no price), Polygon files hashed in meta, polygon counted"] = \
            set(sm_e2e.columns) == {"ticker", "session", "source"} and len(sm_e2e) == len(CORE8) * len(CALIBRATION_DATES) \
            and meta["bar_source_map_counts"].get("polygon") == 2 and meta["polygon_files"][0]["sha256"] \
            and meta["bar_sessions_by_source"].get("polygon") == 2 and meta["amendment_7"].startswith("TRITON-FP-v1-AMENDMENT-7")
        checks["6b e2e: the cursor-gap session is excluded, logged with its cause, and the run completes"] = \
            meta["completeness_exclusions"] == [{"ticker": gap_pair[0], "session": gap_pair[1].isoformat(),
                                                 "cause": EXCLUDED_CAUSES[1]}] \
            and meta["census_set_ticker_sessions"] == len(cal_e2e) - 1
        # 6b e2e export lag: LAB's same-date walk complete for a name BUILD's export does not hold
        lag_tk = [t_ for t_ in CORE8 if t_ not in set(raw.ticker)][0]
        cc = pd.read_csv(os.path.join(td, "complete.csv"))
        cc.loc[(cc.ticker == lag_tk) & (cc.session == str(sessions[0].date())), ["complete", "same_date_route"]] = [True, "b1"]
        cc.to_csv(os.path.join(td, "complete_lag.csv"), index=False)
        g_["TAU_FINAL"] = True
        try:
            run(os.path.join(td, "dp", "*", "*.parquet"), os.path.join(td, "bars1m", "*", "*.parquet"),
                os.path.join(td, "bars1m_polygon", "*.parquet"),
                os.path.join(td, "adv.csv"), os.path.join(td, "va.csv"), os.path.join(td, "complete_lag.csv"),
                os.path.join(td, "macro.csv"), os.path.join(td, "out_lag"))
            checks["6b e2e: an export lag REFUSES the run and names the ticker-session"] = False
        except SystemExit as e_:
            checks["6b e2e: an export lag REFUSES the run and names the ticker-session"] = \
                "EXPORT LAG" in str(e_) and f"{lag_tk} {sessions[0].date()}" in str(e_) \
                and not os.path.exists(os.path.join(td, "out_lag"))
        finally:
            g_["TAU_FINAL"] = saved[0]
        checks["tau gate restored after the test"] = TAU_FINAL is True
        g_["TAU_FINAL"] = False
        try:
            run(*["unused"] * 8)
            checks["`run` still refuses when tau is not final (gate intact)"] = False
        except SystemExit as e_:
            checks["`run` still refuses when tau is not final (gate intact)"] = "tau is not final" in str(e_)
        finally:
            g_["TAU_FINAL"] = saved[0]
    # amendment 8: the reserve window and the verdict
    try:
        set_window("reserve")
        want = ["09-25", "09-28", "09-29", "09-30", "10-01", "10-02", "10-05", "10-06", "10-07", "10-08", "10-09"]
        checks["A8: reserve window = the 11 executed dates 09-25 .. 10-09"] = \
            [d.strftime("%m-%d") for d in CALIBRATION_DATES] == want and WINDOW_NAME == "reserve"
        probe = [date(2026, 9, 24), date(2026, 9, 25), date(2026, 10, 9), date(2026, 10, 12), date(2026, 9, 1)]
        checks["A8: reserve run reads ONLY reserve dates (09-24, 10-12, 09-01 dropped)"] = \
            list(in_calibration(probe)) == [False, True, True, False, False]
        dfr, _, _ = prepare_prints(raw, {(tk, s.date()) for tk in CORE8 for s in sessions})
        checks["A8: synthetic prints -> only the reserve session (09-28) survives"] = \
            sorted({str(x) for x in dfr.session}) == ["2026-09-28"]
    finally:
        set_window("calibration")
    checks["A8: window restored to calibration (17 dates)"] = len(CALIBRATION_DATES) == 17 and WINDOW_NAME == "calibration"
    try:
        set_window("everything")
        checks["A8: an unknown window refuses"] = False
    except SystemExit:
        checks["A8: an unknown window refuses"] = True

    def a8_frames(real_hi):
        """Synthetic outputs: real beats placebo on exactly real_hi of the 27 comparisons."""
        er, dr, n = [], [], 0
        for w, f in A8_DEFINITIONS:
            hi = []
            for _ in range(3):
                hi.append(n < real_hi)
                n += 1
            er += [{"window": w, "floor": f, "arm": "real", "kept": True, "events": 100, "m4": 99,
                    "d5_matched": 90 if hi[0] else 80, "d5_matched_1tick": 30 if hi[1] else 20, "no_bars": 0},
                   {"window": w, "floor": f, "arm": "shuffled", "kept": np.nan, "events": 100, "m4": 99,
                    "d5_matched": 85, "d5_matched_1tick": 25, "no_bars": 0}]
            dr += [{"window": w, "floor": f, "arm": "real", "d6": "BUYER", "events": 30 if hi[2] else 10, "tolerance": "tau"},
                   {"window": w, "floor": f, "arm": "real", "d6": "NONE", "events": 70 if hi[2] else 90, "tolerance": "tau"},
                   {"window": w, "floor": f, "arm": "shuffled", "d6": "SELLER", "events": 20, "tolerance": "tau"},
                   {"window": w, "floor": f, "arm": "shuffled", "d6": "NONE", "events": 80, "tolerance": "tau"}]
        return pd.DataFrame(er), pd.DataFrame(dr)
    C0, k0, v0 = a8_comparisons(*a8_frames(0))
    checks["A8 verdict: real below placebo everywhere -> k = 0 -> KILL"] = len(C0) == 27 and k0 == 0 and v0 == A8_KILL
    C13, k13, v13 = a8_comparisons(*a8_frames(13))
    C14, k14, v14 = a8_comparisons(*a8_frames(14))
    checks["A8 verdict: k = 13 -> KILL; k = 14 -> not replicated, returned to SPINE"] = \
        k13 == 13 and v13 == A8_KILL and k14 == 14 and v14 == A8_NOT_REPLICATED
    Et, Dt = a8_frames(0)
    Et.loc[(Et.arm == "real"), "d5_matched"] = 85                     # ties with the placebo on D5 at tau
    Ct, kt, _ = a8_comparisons(Et, Dt)
    checks["A8 verdict: a tie does NOT exceed"] = kt == 0 and int((Ct.measure == "D5_tau").sum()) == 9
    Eu, Du = a8_frames(27)
    Eu.loc[(Eu.arm == "shuffled") & (Eu.window == "NOGATE") & (Eu.floor == "FRUN"), ["events", "no_bars"]] = [0, 0]
    Cu, ku, _ = a8_comparisons(Eu, Du)
    und = Cu[Cu.undefined]
    checks["A8 verdict: an undefined comparison does not exceed and is named"] = \
        ku == 25 and len(und) == 2 and set(und.measure) == {"D5_tau", "D5_1tick"} and set(und.floor) == {"FRUN"}
    with tempfile.TemporaryDirectory() as tdv:
        cdir = os.path.join(tdv, "census")
        os.makedirs(cdir)
        E0, D0 = a8_frames(0)
        E0.to_csv(os.path.join(cdir, "events_m4_d5.csv"), index=False)
        D0.to_csv(os.path.join(cdir, "d6_direction.csv"), index=False)
        pd.DataFrame([{"ticker": "SPY", "session": "2026-09-25", "window": w, "floor": f, "real_runs": 100,
                       "shuffled_mean": 40.0, "shuffled_p95": 50.0, "kept_runs": 90} for w, f in A8_DEFINITIONS]
                     ).to_csv(os.path.join(cdir, "per_ticker_session.csv"), index=False)
        before = sorted(os.listdir(cdir))
        res = run_verdict_a8(cdir, os.path.join(tdv, "a8.csv"))
        checks["A8 verdict-a8: reads the folder, writes NOTHING into it, comparisons go elsewhere"] = \
            sorted(os.listdir(cdir)) == before and os.path.exists(os.path.join(tdv, "a8.csv")) \
            and res["verdict"] == A8_KILL and res["sanity"]["stop_a_fires"] is False
        try:
            run_verdict_a8(cdir, os.path.join(cdir, "a8.csv"))
            checks["A8 verdict-a8: refuses to write into the census folder"] = False
        except SystemExit:
            checks["A8 verdict-a8: refuses to write into the census folder"] = \
                sorted(os.listdir(cdir)) == before
    for k, v in checks.items():
        print(("PASS " if v else "FAIL ") + k)
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    if sys.argv[1] == "--window":                        # amendment 8: `--window reserve <mode> ...`
        set_window(sys.argv[2])
        del sys.argv[1:3]
    mode = sys.argv[1]
    if mode == "verdict-a8":
        run_verdict_a8(*sys.argv[2:4])
        sys.exit(0)
    if mode == "selftest":
        sys.exit(selftest())
    if mode == "build-complete":
        run_build_complete(*sys.argv[2:4])
    elif mode == "crosscheck":
        sys.exit(run_crosscheck(*sys.argv[2:5]))
    elif mode == "anchor":
        run_anchor(*sys.argv[2:5])
    elif mode == "run":
        run(*sys.argv[2:10])
