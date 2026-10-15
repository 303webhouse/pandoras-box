"""TRITON-R v1 instrument -- the BACKTEST block (R-IV.1080(h)2-3). QUERY runs it read-only; LAB never sees a row.

Claim of record: TRITON-R-v1-STAMPED-R-IV.1080.md (ba9e77df...), = REV 1 (44b98cab...) + R-IV.1080(b)-(g);
amended by TRITON-R-v1-AMENDMENT-1-R-IV.1084.md (d8030b4f...): continuous EMA; small-sample kill floors;
and TRITON-R-v1-AMENDMENT-2-R-IV.1090.md (21a2c0e9...): controls from t_r + 1 min; WIN 1 bootstrap 10,000;
WIN 4 >= 5 claim events per side (named if not met); SUSPECT if > 10% of resamples skipped.
Source of record: triton-design-of-record-2026-10-12.md (12ecf72c...).

DATE CEILINGS FIRST (R-IV.1072(d), R-IV.1080): this instrument reads ONLY the backtest block
2026-09-01 .. 2026-09-24. Every source is checked against [2026-09-01, 2026-09-24] with the seal
(08-17 .. 08-31) excluded, and a row outside REFUSES the run (prints and bars are clipped by the frozen
census readers, then asserted). FX daily closes (tag only) may precede 09-01 but never reach 09-25, and
sealed dates are removed from them. The holdout / confirmation set (09-25 on) is never read here.

Pipeline, per variant (TG-ON = census window T1000, PRIMARY; TG-OFF = NOGATE, secondary):
  D1-D5 + D6  the FROZEN census (`triton_census.census`, code 74dd362 lineage) is run unchanged and its
              real-arm FRUN events are captured (kept by D4, D5 at tau, D6 geometry) -- the RNG stream of
              D4 is shared across every ticker-session, window and floor, so only the frozen loop itself
              reproduces "exactly as frozen in census run 2".
  D7          first 5-min close beyond L by >= 0.25 x ATR14(5-min) on the D6 side, volume >= the slot
              median of the 10 prior in-window sessions, closing within (t, t + 60 min].
  filters     Tue-Thu, CPI/FOMC excluded; 5-min 20-EMA side-aligned; tide slope (6 ticks) aligned;
              PYTHIA-LOC v1 PASS. A missing ingredient -> UNEVALUABLE, never FAIL, never substituted.
  endpoint    Z = d (S_close - S0) / (S0 sigma sqrt(tau)), sigma = iv_near of the prior session.
  placebo     same ticker, other eligible backtest sessions, clock time +-5 min, D5 lit pattern at a bar's
              low/high, no D3 run of any floor within +-10 min and tau, same rule; up to 5, fixed seed.
  WIN 1-4, kills, verdict  per the stamped file sec. 7. BACKTEST verdict: KILL or NO-KILL only.

Outputs are aggregates only (counts, rates, means, intervals); `assert_aggregate` refuses price/size/time.

Usage (QUERY):
  python scripts/lab/triton_r.py backtest <prints_glob> <complete_csv> <bars_glob> <polygon_glob> <adv_csv>
         <va_csv> <macro_csv> <tide_csv> <iv_csv> <fx_csv> <out_dir>
  python scripts/lab/triton_r.py count <as_of> <prints_glob> <complete_csv> <bars_glob> "<polygon_glob>;<polygon_glob2>" <va_csv>
         <macro_csv> <tide_csv> <iv_csv> <out_dir>      (COUNT-ONLY, confirmation set 09-25 .. as_of)
  python scripts/lab/triton_r.py confirmation-complete <as_of> <walk_pages_csv> <complete_csv_out>
  python scripts/lab/triton_r.py confirmation-crosscheck <as_of> <prints_glob> <complete_csv> <crosscheck_csv_out>
  python scripts/lab/triton_r.py selftest
"""
import glob
import json
import os
import sys
from datetime import date, time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import triton_census as C  # noqa: E402

CLAIM = "TRITON-R-v1-STAMPED-R-IV.1080.md ba9e77df4f110d493b6e67f44ef388d2651d88a6033cd57cf972c446d5469f5c"
BACKTEST = (date(2026, 9, 1), date(2026, 9, 24))
CEILING = date(2026, 9, 25)                       # nothing on or after this date is ever read here
VARIANTS = {"TG-ON": "T1000", "TG-OFF": "NOGATE"}  # R-IV.1080(c): TG-ON is PRIMARY
PRIMARY = "TG-ON"
FLOOR = "FRUN"                                     # R-IV.1078(b)
RTH0, RTH1 = 9 * 3600 + 30 * 60, 16 * 3600
BAR5 = 300
D7_ATR_MULT, D7_ATR_N, D7_WINDOW_S, SLOT_LOOKBACK = 0.25, 14, 3600, 10
EMA_N = 20
TIDE_TICKS, TIDE_STEP_S = 6, 300
PLACEBO_WINDOW_S, PLACEBO_MAX = 300, 5
K_CONTROLS = 20
BOOT_B, BOOT_SEED = 10000, 20261015
SEED_R = 20261015
MIN_EVENTS, MIN_SESSIONS = 30, 10
FREQ_FLOOR_TS = 20                                 # amendment 1: the frequency kill needs >= 20 evaluable ticker-sessions
AMENDMENT_1 = "TRITON-R-v1-AMENDMENT-1-R-IV.1084.md d8030b4f0602af9c54d2f3b0a393479a954b672ff3f5315f2cb478983c10aa58"
AMENDMENT_2 = "TRITON-R-v1-AMENDMENT-2-R-IV.1090.md 21a2c0e93c4db6eadfdbc1695c7d33ae61c5ff37ce4d53fb1877c9f4d784848a"
WIN4_MIN_PER_SIDE = 5                              # amendment 2 sec. 4
SUSPECT_SKIP_SHARE = 0.10                          # amendment 2 sec. 5
TUE_THU = {1, 2, 3}
MACRO_EXCLUDE = {"cpi", "fomc_decision"}
MONEY_GATE = "money gate: NOT EVALUABLE (backtest; R-IV.1080(g))"
LABEL = "out of sample, not blind (design sec. 11); backtest 2026-09-01 .. 2026-09-24 only"


# ── 0 · DATE CEILINGS (first) ────────────────────────────────────────────────────────────────────
def _sealed(d):
    return C.SEAL[0] <= d <= C.SEAL[1] or d in C.QUARANTINED


def in_block(d):
    return BACKTEST[0] <= d <= BACKTEST[1] and not _sealed(d)


def assert_block(dates, what):
    """REFUSE if any date is outside the backtest block, sealed, or on/after the ceiling."""
    bad = sorted({str(d) for d in dates if not in_block(d)})
    if bad:
        raise SystemExit(f"DATE CEILING: {what} carries {len(bad)} date(s) outside 2026-09-01..2026-09-24 "
                         f"(seal excluded; ceiling {CEILING}): {bad[:5]}. Refusing.")


def _dates(series):
    return [pd.Timestamp(x).date() for x in series]


def read_block_csv(path, date_col, what):
    df = pd.read_csv(path)
    if date_col not in df.columns:
        raise SystemExit(f"{what}: no {date_col} column")
    assert_block(_dates(df[date_col]), what)
    return df


# ── 1 · bars with open and volume (same source map as amendment 7) ───────────────────────────────
def _globs(spec):
    """One glob, or several separated by ';' (the backtest Polygon pull plus the dated reserve pull)."""
    return [g for g in str(spec).split(";") if g]


def scope_raw(raw, in_scope):
    """Prints, filtered the moment they are read: export session_date AND executed ET date in scope."""
    sd = _dates(raw.session_date)
    ex = list(pd.to_datetime(raw.executed_at, utc=True, format="ISO8601").dt.tz_convert("America/New_York").dt.date)
    return raw[[in_scope(a) and in_scope(b) for a, b in zip(sd, ex)]].reset_index(drop=True)


def scope_bars(bars, in_scope):
    """Bars (BAR_COLUMNS), filtered the moment they are read: ET date of the bar in scope."""
    if bars is None or not len(bars):
        return bars
    d = pd.to_datetime(bars.t_utc, utc=True).dt.tz_convert("America/New_York").dt.date
    return bars[[in_scope(x) for x in d]].reset_index(drop=True)


def load_polygon_multi(spec):
    parts, info = [], []
    for g in _globs(spec):
        b, i = C.load_polygon(g)                                       # amendment 7's refusals, unchanged
        parts.append(b)
        info += i
    return pd.concat(parts, ignore_index=True), info


def load_ohlcv(polygon_glob, bars_glob, source_map, in_scope=None):
    """{(ticker, session): DataFrame[t_s, open, high, low, close, volume]} of RTH 1-min bars, chosen per
    ticker-session by the census's own source map. Only in-scope sessions (default: the backtest block)."""
    in_scope = in_scope or in_block
    load_polygon_multi(polygon_glob)
    pf = sorted(f for g in _globs(polygon_glob) for f in glob.glob(g)
                if os.path.basename(f).endswith("_adjusted_false.parquet"))
    poly = {}
    for f in pf:
        tk = os.path.basename(f)[: -len("_adjusted_false.parquet")]
        if tk in C.CORE8:
            b = pd.read_parquet(f)
            t = pd.to_datetime(b.timestamp_utc, utc=True).dt.tz_convert("America/New_York")
            poly.setdefault(tk, []).append(pd.DataFrame({"t_et": t, "open": b["open"].astype(float),
                                                         "high": b["high"].astype(float), "low": b["low"].astype(float),
                                                         "close": b["close"].astype(float),
                                                         "volume": b["volume"].astype(float)}))
    poly = {k: pd.concat(v, ignore_index=True).drop_duplicates("t_et") for k, v in poly.items()}
    rm = {}
    for f in sorted(glob.glob(bars_glob)):
        tk = os.path.splitext(os.path.basename(f))[0]
        if tk in C.CORE8:
            b = pd.read_parquet(f)
            idx = pd.DatetimeIndex(b.index).tz_convert("America/New_York")
            rm.setdefault(tk, []).append(pd.DataFrame({"t_et": idx, "open": b["Open"].astype(float),
                                                       "high": b["High"].astype(float), "low": b["Low"].astype(float),
                                                       "close": b["Close"].astype(float),
                                                       "volume": b["Volume"].astype(float)}))
    rm = {k: pd.concat(v, ignore_index=True) for k, v in rm.items()}
    out = {}
    for r in source_map.itertuples():
        d = date.fromisoformat(r.session)
        if r.source == "none" or not in_scope(d):
            continue
        src = poly if r.source == "polygon" else rm
        b = src.get(r.ticker)
        if b is None:
            continue
        g = b[b.t_et.dt.date == d]
        s_ = (g.t_et - g.t_et.dt.normalize()).dt.total_seconds().to_numpy()
        m = (s_ >= RTH0) & (s_ < RTH1)
        g = g[m].assign(t_s=s_[m]).sort_values("t_s")
        if len(g):
            out[(r.ticker, d)] = g[["t_s", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
    bad = [k for k in out if not in_scope(k[1])]
    if bad:
        raise SystemExit(f"DATE CEILING: 1-min bars outside scope {bad[:3]}; refusing")
    return out


def bars5(b1):
    """5-min RTH bars from 1-min bars, clock-aligned at 09:30. Columns: slot, t_close, open, high, low, close, volume."""
    slot = ((b1.t_s - RTH0) // BAR5).astype(int)
    g = b1.assign(slot=slot).groupby("slot")
    out = pd.DataFrame({"open": g.open.first(), "high": g.high.max(), "low": g.low.min(),
                        "close": g.close.last(), "volume": g.volume.sum()}).reset_index()
    out["t_close"] = RTH0 + (out.slot + 1) * BAR5
    return out


# ── 2 · D7, EMA, tide, PYTHIA, calendar, IV ─────────────────────────────────────────────────────
def atr_at(seq, i):
    """Simple mean of the 14 true ranges ending at bar i of the in-block 5-min sequence (across sessions).
    The first in-block bar's TR is high - low (its prior close lies in the seal or before the block)."""
    if i + 1 < D7_ATR_N:
        return None
    h, l, c = seq.high.to_numpy(), seq.low.to_numpy(), seq.close.to_numpy()
    trs = []
    for j in range(i - D7_ATR_N + 1, i + 1):
        tr = h[j] - l[j]
        if j > 0:
            tr = max(tr, abs(h[j] - c[j - 1]), abs(l[j] - c[j - 1]))
        trs.append(tr)
    return float(np.mean(trs))


def slot_median(prior_b5, slot):
    """Median volume of `slot` over the 10 prior in-block sessions; None unless all 10 have that slot."""
    if len(prior_b5) < SLOT_LOOKBACK:
        return None
    vols = []
    for b in prior_b5[-SLOT_LOOKBACK:]:
        v = b.volume[b.slot == slot]
        if not len(v):
            return None
        vols.append(float(v.iloc[0]))
    return float(np.median(vols))


def d7(seq, sess_mask, prior_b5, t_event, L, side):
    """('CONFIRMED', bar_index_in_seq) / ('UNCONFIRMED', None) / ('MISSING', what)."""
    idx = np.flatnonzero(sess_mask)
    for i in idx:
        tc = seq.t_close.iloc[i]
        if tc <= t_event:
            continue
        if tc > t_event + D7_WINDOW_S:
            break
        atr = atr_at(seq, i)
        med = slot_median(prior_b5, int(seq.slot.iloc[i]))
        if atr is None:
            return "MISSING", "atr14"
        if med is None:
            return "MISSING", "slot_median"
        c, v = float(seq.close.iloc[i]), float(seq.volume.iloc[i])
        beyond = c >= L + D7_ATR_MULT * atr if side == "BUYER" else c <= L - D7_ATR_MULT * atr
        if beyond and v >= med:
            if tc >= RTH1:
                return "MISSING", "horizon"
            return "CONFIRMED", int(i)
    return "UNCONFIRMED", None


def ema_at(closes, j):
    """20-EMA of 5-min closes through index j; seeded with the SMA of the first 20. Amendment 1
    (d8030b4f...): `closes` is the CONTINUOUS readable sequence across sessions (sealed dates never in it),
    so only the first 19 readable bars are UNEVALUABLE."""
    if j + 1 < EMA_N:
        return None
    a = 2.0 / (EMA_N + 1)
    e = float(np.mean(closes[:EMA_N]))
    for k in range(EMA_N, j + 1):
        e = a * closes[k] + (1 - a) * e
    return e


def tide_slope(ticks, t_conf):
    """ticks: DataFrame[t_s, net] of the session. Slope over the last 6 ticks (30 min) at confirmation."""
    if ticks is None or not len(ticks):
        return None
    k = np.flatnonzero(ticks.t_s.to_numpy() <= t_conf)
    if not len(k) or k[-1] < TIDE_TICKS:
        return None
    i = k[-1]
    if abs((ticks.t_s.iloc[i] - ticks.t_s.iloc[i - TIDE_TICKS]) - TIDE_TICKS * TIDE_STEP_S) > 1:
        return None
    return float(ticks.net.iloc[i] - ticks.net.iloc[i - TIDE_TICKS])


def pythia_pass(L, va, side):
    if va is None:
        return "MISSING"
    loc = C.pythia_loc(L, va[0], va[1], "LONG" if side == "BUYER" else "SHORT")
    return "MISSING" if loc == "UNAVAILABLE" else ("PASS" if loc in ("outside", "edge") else "FAIL")


def calendar_ok(d, macro_excl):
    if d.weekday() not in TUE_THU:
        return "FAIL_WEEKDAY"
    if d in macro_excl:
        return "FAIL_MACRO"
    return "OK"


# ── 3 · the frozen census, captured ─────────────────────────────────────────────────────────────
class _KeyedBars(dict):
    """census() calls bars.get((tk, sess)) once per ticker-session; remember that key."""
    current = None

    def get(self, k, default=None):
        _KeyedBars.current = k
        return super().get(k, default)


def run_census_captured(df, adv, bars, va, macro, n_shuffles=None):
    """Run triton_census.census UNCHANGED; capture every real-arm event_rows call with its ticker-session."""
    cap, orig = [], C.event_rows

    def wrapped(arm, wname, fl, kept, t_s, sizes, ev, b, v):
        rec, rd = orig(arm, wname, fl, kept, t_s, sizes, ev, b, v)
        if arm == "real":
            tk, sess = _KeyedBars.current
            cap.append({"ticker": tk, "session": sess, "window": wname, "floor": fl, "kept": bool(kept),
                        "t": float(ev[0]), "L": float(ev[3]), "d5": rec["d5"], "d6": rec["d6"], "m4": bool(rec["m4"])})
        return rec, rd
    C.event_rows = wrapped
    try:
        kb = _KeyedBars(bars) if bars else _KeyedBars({("__none__", None): None})
        frames = C.census(df, adv, kb, va, n_shuffles=n_shuffles or C.N_SHUFFLES, macro=macro)
    finally:
        C.event_rows = orig
    E = pd.DataFrame(cap)
    return frames, E


def capture_matches_census(frames, E):
    """The captured FRUN real events must equal the census's own counts (kept and d5), per window."""
    M = frames["events_m4_d5"]
    out = {}
    for w in ("T1000", "NOGATE"):
        r = M[(M.window == w) & (M.floor == FLOOR) & (M.arm == "real") & (M.kept.astype(str) == "True")]
        n_c = int(r.events.sum()) if len(r) else 0
        d5_c = int(r.d5_matched.sum()) if len(r) else 0
        e = E[(E.window == w) & (E.floor == FLOOR) & E.kept] if len(E) else E
        n_e = int(len(e))
        d5_e = int((e.d5 == True).sum()) if len(e) else 0  # noqa: E712
        out[w] = {"census_kept": n_c, "captured_kept": n_e, "census_d5": d5_c, "captured_d5": d5_e,
                  "match": n_c == n_e and d5_c == d5_e}
    return out


# ── 4 · one event through the recipe ────────────────────────────────────────────────────────────
class Ctx:
    """Everything the recipe reads, already ceiling-checked."""

    def __init__(self, ohlcv, tide, iv, va, macro_excl, dates):
        self.ohlcv, self.tide, self.iv, self.va, self.macro_excl = ohlcv, tide, iv, va, macro_excl
        self.dates = sorted(dates)
        self.seq, self.b5 = {}, {}
        for tk in C.CORE8:
            parts = []
            for d in self.dates:
                b = ohlcv.get((tk, d))
                if b is not None:
                    x = bars5(b).assign(session=d)
                    self.b5[(tk, d)] = x
                    parts.append(x)
            if parts:
                self.seq[tk] = pd.concat(parts, ignore_index=True)

    def prior_b5(self, tk, d):
        return [self.b5[(tk, x)] for x in self.dates if x < d and (tk, x) in self.b5]

    def prior_session(self, d):
        p = [x for x in self.dates if x < d]
        return p[-1] if p else None

    def session_missing(self, tk, d):
        """Session-level ingredients for (tk, d); a list of what is missing."""
        miss = []
        if (tk, d) not in self.ohlcv:
            miss.append("bars")
        if self.tide.get(d) is None:
            miss.append("tide")
        ps = self.prior_session(d)
        if ps is None or not np.isfinite(self.iv.get((tk, ps), np.nan)):
            miss.append("iv_prior_session")
        v = self.va.get((tk, d))
        if v is None or not (v[1] < v[0]):
            miss.append("pythia_va")
        if len(self.prior_b5(tk, d)) < SLOT_LOOKBACK:
            miss.append("slot_median_history")
        return miss


def evaluate(ctx, tk, d, t, L, side, outcome=True):
    """All ingredients for one (tk, d, t, L, side). Returns dict: missing, fails, and if claim, Z inputs.
    outcome=False (the COUNT-ONLY job, R-IV.1080(b)): S_close, sigma and Z are never read or computed."""
    res = {"missing": [], "fails": [], "z": None, "conf": None}
    cal = calendar_ok(d, ctx.macro_excl)
    if cal != "OK":
        res["fails"].append(cal)
    res["missing"] += ctx.session_missing(tk, d)
    if "bars" in res["missing"]:
        return res
    seq = ctx.seq[tk]
    mask = (seq.session == d).to_numpy()
    st, info = d7(seq, mask, ctx.prior_b5(tk, d), t, L, side)
    if st == "MISSING":
        res["missing"].append(info)
        return res
    if st == "UNCONFIRMED":
        res["fails"].append("D7_unconfirmed")
        return res
    i = info
    S0, t_conf = float(seq.close.iloc[i]), float(seq.t_close.iloc[i])
    res["conf"] = (S0, t_conf)
    e = ema_at(seq.close.to_numpy(), i)           # amendment 1: continuous across readable sessions
    if e is None:
        res["missing"].append("ema_warmup")
    elif not ((S0 > e) if side == "BUYER" else (S0 < e)):
        res["fails"].append("EMA")
    tk_ticks = ctx.tide.get(d)
    sl = tide_slope(tk_ticks, t_conf) if tk_ticks is not None else None
    if sl is None:
        if "tide" not in res["missing"]:
            res["missing"].append("tide_slope")
    elif not ((sl > 0) if side == "BUYER" else (sl < 0)):
        res["fails"].append("tide")
    pp = pythia_pass(L, ctx.va.get((tk, d)), side)
    if pp == "FAIL":
        res["fails"].append("PYTHIA")
    elif pp == "MISSING" and "pythia_va" not in res["missing"]:
        res["missing"].append("pythia_va")
    if not outcome:
        return res
    if not res["missing"] and not res["fails"]:
        b1 = ctx.ohlcv[(tk, d)]
        s_close = float(b1.close.iloc[-1])
        sigma = float(ctx.iv[(tk, ctx.prior_session(d))])
        tau_y = ((RTH1 - t_conf) / 60.0) / (390.0 * 252.0)
        im = S0 * sigma * np.sqrt(tau_y)
        dsign = 1.0 if side == "BUYER" else -1.0
        res["z"] = dsign * (s_close - S0) / im if im > 0 else None
        if res["z"] is None:
            res["missing"].append("horizon")
    return res


# ── 5 · level respect (WIN 1), placebo (WIN 2) ──────────────────────────────────────────────────
def touched_held(b1, t_from, X, ref):
    """From bars starting at/after t_from: touched = a bar's range within tau(X) of X; held = no later close
    beyond X (away from ref) by more than tau(X), after the first touch."""
    tau_x = float(C.tau(X))
    g = b1[b1.t_s >= t_from]
    if not len(g):
        return False, False
    lo, hi, cl = g.low.to_numpy(), g.high.to_numpy(), g.close.to_numpy()
    hit = np.flatnonzero((lo - tau_x <= X) & (X <= hi + tau_x))
    if not len(hit):
        return False, False
    after = cl[hit[0]:]
    broken = np.any(after < X - tau_x - 1e-9) if X <= ref else np.any(after > X + tau_x + 1e-9)
    return True, not broken


def controls(b1, eligible_starts, D, rng, k=K_CONTROLS):
    """K random equidistant control levels (R-IV.1080(e)): random t_r, random side, X = S(t_r) +- D."""
    out = []
    if not len(eligible_starts):
        return out
    for _ in range(k):
        tr = float(rng.choice(eligible_starts))
        sgn = 1.0 if rng.random() < 0.5 else -1.0
        s_tr = float(b1.close[b1.t_s == tr].iloc[0])
        X = s_tr + sgn * D
        out.append(touched_held(b1, tr + 60, X, s_tr))
    return out


def dark_runs(df_sess, t_lo, t_hi, adv):
    """Union of D2+D3 runs over all four floors in a time window: rows (end_s, L)."""
    t_all = (df_sess.t_et - df_sess.t_et.dt.normalize()).dt.total_seconds().to_numpy()
    m = (t_all >= t_lo) & (t_all < t_hi)
    t_s, p, s = t_all[m], df_sess.price.to_numpy(float)[m], df_sess["size"].to_numpy(float)[m]
    rows = [C.runs_for(t_s, p, s, adv, fl) for fl in C.FLOORS]
    rows = [r for r in rows if len(r)]
    return np.vstack(rows)[:, [0, 3]] if rows else np.empty((0, 2))


def placebos(ctx, prints_by_ts, adv, tk, d_event, t_event, wstart, rng, bars_hl, eligible_sessions):
    """Valid placebo Zs for one claim event (up to PLACEBO_MAX, fixed rng)."""
    cands = []
    for d in eligible_sessions:
        if d == d_event or (tk, d) not in ctx.ohlcv:
            continue
        b1 = ctx.ohlcv[(tk, d)]
        hl = bars_hl.get((tk, d))
        runs = dark_runs(prints_by_ts[(tk, d)], RTH0, RTH1, adv.get((tk, d))) \
            if (tk, d) in prints_by_ts else np.empty((0, 2))
        win = b1[(b1.t_s >= max(wstart, t_event - PLACEBO_WINDOW_S)) & (b1.t_s <= t_event + PLACEBO_WINDOW_S)]
        seen = set()
        for r in win.itertuples():
            for Lp in (float(r.low), float(r.high)):
                tau_p = float(C.tau(Lp))
                d5p, d6p = C.lit(hl, r.t_s, Lp, tau_p)
                if not d5p or d6p not in ("BUYER", "SELLER"):
                    continue
                if len(runs) and np.any((np.abs(runs[:, 0] - r.t_s) <= C.LIT_WINDOW_S) & (np.abs(runs[:, 1] - Lp) <= tau_p)):
                    continue
                key = (d, round(Lp, 4), d6p)
                if key in seen:
                    continue
                seen.add(key)
                ev = evaluate(ctx, tk, d, float(r.t_s), Lp, d6p)
                if ev["z"] is not None:
                    cands.append(ev["z"])
    if not cands:
        return []
    pick = rng.choice(len(cands), size=min(PLACEBO_MAX, len(cands)), replace=False)
    return [cands[i] for i in pick]


# ── 6 · statistics ──────────────────────────────────────────────────────────────────────────────
def boot_ci(groups, stat, B=BOOT_B, seed=BOOT_SEED):
    """Session-block bootstrap: resample sessions (keys of groups) with replacement; 95% percentile CI.
    Returns (point, lo, hi, n_used) or (None,...) if undefined."""
    keys = sorted(groups)
    if not keys:
        return None, None, None, 0
    point = stat([groups[k] for k in keys])
    if point is None:
        return None, None, None, 0
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(B):
        pick = rng.integers(0, len(keys), len(keys))
        v = stat([groups[keys[i]] for i in pick])
        if v is not None:
            vals.append(v)
    if not vals:
        return point, None, None, 0
    return point, float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)), len(vals)


def suspect(name, point, n_used, B=BOOT_B):
    """Amendment 2 sec. 5: SUSPECT if skipped resamples exceed 10% of B (only when the point is defined)."""
    skipped = (B - n_used) if point is not None else None
    return {f"{name}_boot_skipped": skipped,
            f"{name}_suspect": bool(skipped is not None and skipped > SUSPECT_SKIP_SHARE * B)}


def mean_stat(parts):
    x = [v for p in parts for v in p]
    return float(np.mean(x)) if x else None


def rate_diff_stat(parts):
    hl = sum(p[0] for p in parts)
    tl = sum(p[1] for p in parts)
    hc = sum(p[2] for p in parts)
    tc = sum(p[3] for p in parts)
    return (hl / tl - hc / tc) if tl and tc else None


def week_of(d):
    return pd.Timestamp(d).to_period("W-SUN").start_time.date()


def summarize(events, n_eval_ts):
    """events: list of dicts {session, side, z, zp(list), held_L(bool), touched_L(bool), ctrl[(t,h)], mirror(t,h)}."""
    out = {"claim_events": len(events), "sessions": len({e["session"] for e in events}),
           "evaluable_ticker_sessions": n_eval_ts}
    out["rate_per_week"] = (len(events) / n_eval_ts * 24) if n_eval_ts else None
    with_p = [e for e in events if e["zp"]]
    out["events_with_placebo"] = len(with_p)
    out["events_without_placebo"] = len(events) - len(with_p)
    g2 = {}
    for e in with_p:
        g2.setdefault(e["session"], []).append(e["z"] - float(np.mean(e["zp"])))
    out["win2_mean_z_event"] = float(np.mean([e["z"] for e in with_p])) if with_p else None
    out["win2_mean_z_placebo"] = float(np.mean([np.mean(e["zp"]) for e in with_p])) if with_p else None
    p, lo, hi, nb = boot_ci(g2, mean_stat)
    out.update({"win2_diff": p, "win2_lo": lo, "win2_hi": hi, "win2_boot_used": nb, **suspect("win2", p, nb)})
    g1 = {}
    for e in events:
        t = g1.setdefault(e["session"], [0, 0, 0, 0])
        t[0] += int(e["touched_L"] and e["held_L"])
        t[1] += int(e["touched_L"])
        t[2] += sum(int(a and b) for a, b in e["ctrl"])
        t[3] += sum(int(a) for a, b in e["ctrl"])
    p1, lo1, hi1, nb1 = boot_ci(g1, rate_diff_stat)
    out.update({"win1_diff": p1, "win1_lo": lo1, "win1_hi": hi1, "win1_boot_used": nb1, **suspect("win1", p1, nb1),
                "win1_L_touched": sum(v[1] for v in g1.values()), "win1_L_held": sum(v[0] for v in g1.values()),
                "win1_ctrl_touched": sum(v[3] for v in g1.values()), "win1_ctrl_held": sum(v[2] for v in g1.values())})
    gm = {}
    for e in events:
        t = gm.setdefault(e["session"], [0, 0, 0, 0])
        mt, mh = e["mirror"]
        t[0] += int(e["touched_L"] and e["held_L"])
        t[1] += int(e["touched_L"])
        t[2] += int(mt and mh)
        t[3] += int(mt)
    pm, lom, him, nbm = boot_ci(gm, rate_diff_stat)
    out.update({"secondary_mirror_diff": pm, "secondary_mirror_lo": lom, "secondary_mirror_hi": him,
                **suspect("secondary_mirror", pm, nbm),
                "secondary_mirror_note": "drift confound: a correct side drifts price toward the mirror; no verdict weight"})
    # WIN 3 / one week carries it
    wk = {}
    for s_, v in g2.items():
        wk.setdefault(week_of(s_), []).extend(v)
    if wk:
        best = max(wk, key=lambda w: sum(wk[w]))
        rest = [v for w, vv in wk.items() if w != best for v in vv]
        allv = [v for vv in wk.values() for v in vv]
        out["win3_mean_without_best_week"] = float(np.mean(rest)) if rest else None
        m_all = float(np.mean(allv))
        m_rest = float(np.mean(rest)) if rest else None
        out["kill_one_week_carries_it"] = bool(m_rest is not None and np.sign(m_all) != np.sign(m_rest))
    else:
        out["win3_mean_without_best_week"], out["kill_one_week_carries_it"] = None, False
    sides = {}
    for e in with_p:
        sides.setdefault(e["side"], []).append(e["z"] - float(np.mean(e["zp"])))
    n_side = {k: sum(1 for e in events if e["side"] == k) for k in ("BUYER", "SELLER")}
    out["win4_by_side"] = {k: {"claim_events": n_side[k], "with_placebo": len(sides.get(k, [])),
                               "mean_diff": float(np.mean(sides[k])) if sides.get(k) else None}
                           for k in ("BUYER", "SELLER")}
    # amendment 2 sec. 4: each side needs >= 5 claim events; a side below that, or empty, is NAMED
    out["win4_not_met_sides"] = [k for k in ("BUYER", "SELLER")
                                 if n_side[k] < WIN4_MIN_PER_SIDE or out["win4_by_side"][k]["mean_diff"] is None
                                 or out["win4_by_side"][k]["mean_diff"] < 0]
    # kills -- amendment 1 floors (R-IV.1084(c)): statistical kills only at >= 30 events over >= 10
    # sessions; the frequency kill only with >= 20 evaluable ticker-sessions. Raw readings kept.
    stat_floor = len(events) >= MIN_EVENTS and out["sessions"] >= MIN_SESSIONS
    freq_floor = n_eval_ts >= FREQ_FLOOR_TS
    raw_week = out["kill_one_week_carries_it"]
    out["raw_kill_readings"] = {
        "under_1_per_week": bool(out["rate_per_week"] is not None and out["rate_per_week"] < 1.0),
        "L_not_respected": bool(hi1 is not None and hi1 <= 0),
        "placebo_keeps_pace": bool(hi is not None and hi <= 0),
        "one_week_carries_it": bool(raw_week),
        "note": "raw readings; below a floor they carry no verdict weight (amendment 1)"}
    out["stat_kill_floor_met"], out["freq_kill_floor_met"] = stat_floor, freq_floor
    out["kill_under_1_per_week"] = freq_floor and out["raw_kill_readings"]["under_1_per_week"]
    out["kill_L_not_respected"] = stat_floor and out["raw_kill_readings"]["L_not_respected"]
    out["kill_placebo_keeps_pace"] = stat_floor and out["raw_kill_readings"]["placebo_keeps_pace"]
    out["kill_one_week_carries_it"] = stat_floor and bool(raw_week)
    out["kill_real_approx_shuffled"] = "inherited: satisfied by D4 as frozen (census stop (a) PASS for FRUN); not re-tested"
    out["kills_fired"] = [k for k in ("kill_under_1_per_week", "kill_L_not_respected", "kill_placebo_keeps_pace",
                                      "kill_one_week_carries_it") if out[k] is True]
    # WIN (reported; the backtest verdict is KILL / NO-KILL only)
    out["win1"] = bool(lo1 is not None and lo1 > 0)
    out["win2"] = bool(lo is not None and lo > 0)
    out["win3"] = bool(out["win3_mean_without_best_week"] is not None and out["win3_mean_without_best_week"] > 0)
    out["win4"] = not out["win4_not_met_sides"]
    out["min_n_met"] = len(events) >= MIN_EVENTS and out["sessions"] >= MIN_SESSIONS
    return out


# ── 7 · the backtest ────────────────────────────────────────────────────────────────────────────
def load_side_inputs(va_csv, macro_csv, tide_csv, iv_csv, fx_csv):
    va = read_block_csv(va_csv, "session", "va_csv")
    va = {(r.ticker, pd.Timestamp(r.session).date()): (r.vah, r.val) for r in va.itertuples()}
    mac = read_block_csv(macro_csv, "date", "macro_csv")
    macro_all = set(_dates(mac.date))
    macro_excl = {pd.Timestamp(r.date).date() for r in mac.itertuples() if str(r.event) in MACRO_EXCLUDE}
    td = read_block_csv(tide_csv, "session_date", "tide_csv")
    t = pd.to_datetime(td.tick_at, utc=True).dt.tz_convert("America/New_York")
    assert_block(list(t.dt.date), "tide_csv tick_at")
    td = td.assign(t_s=(t - t.dt.normalize()).dt.total_seconds(),
                   net=pd.to_numeric(td.net_call_premium) - pd.to_numeric(td.net_put_premium),
                   d=pd.to_datetime(td.session_date).dt.date)
    tide = {d: g.sort_values("t_s")[["t_s", "net"]].reset_index(drop=True) for d, g in td.groupby("d")}
    ivd = read_block_csv(iv_csv, "session_date", "iv_csv")
    iv = {(r.ticker, pd.Timestamp(r.session_date).date()): float(r.iv_near) if pd.notna(r.iv_near) else np.nan
          for r in ivd.itertuples()}
    return va, macro_all, macro_excl, tide, iv, read_fx(fx_csv)


def read_fx(fx_csv):
    """FX daily closes (tag only): may precede the block, never reach the ceiling; sealed dates removed."""
    fx = pd.read_csv(fx_csv)
    fxd = _dates(fx.date)
    if any(d >= CEILING for d in fxd):
        raise SystemExit(f"DATE CEILING: fx_csv reaches {max(fxd)} (>= {CEILING}). Refusing.")
    return fx[[not _sealed(d) for d in fxd]].reset_index(drop=True)


def fx_state(fx, symbol, d):
    """Tag only (R-IV.1078(d)): QUIET / RE-LEVER / UNWIND from prior-session closes, else MISSING."""
    s = fx[fx.symbol == symbol].assign(d=_dates(fx[fx.symbol == symbol].date)).sort_values("d")
    s = s[s.d < d]
    c = s.close.to_numpy(float)
    if len(c) < 66:
        return "MISSING"
    sp = np.abs(np.log(c[5:] / c[:-5]))
    cur, hist = sp[-1], sp[-61:-1]
    if cur < np.median(hist):
        return "QUIET"
    return "RE-LEVER" if c[-1] > c[-6] else "UNWIND"


def backtest(prints_glob, complete_csv, bars_glob, polygon_glob, adv_csv, va_csv, macro_csv, tide_csv,
             iv_csv, fx_csv, out_dir, n_shuffles=None):
    if not C.TAU_FINAL:
        raise SystemExit("tau is not final")
    C.set_window("calibration")
    if C.CALIBRATION != BACKTEST:
        raise SystemExit("the census calibration window is not the backtest block; refusing")
    va, macro_all, macro_excl, tide, iv, fx = load_side_inputs(va_csv, macro_csv, tide_csv, iv_csv, fx_csv)
    raw = scope_raw(C._read_parquet(prints_glob), in_block)          # the ceiling, at the read
    build_set = C.build_complete_set(raw)
    S, excluded, refusals = C.census_set(pd.read_csv(complete_csv), build_set)
    if refusals:
        raise SystemExit(C.refusal_message(refusals))
    df, n_dup, dropped = C.prepare_prints(raw, S)
    assert_block(set(df.session), "prints")
    praw, poly_info = load_polygon_multi(polygon_glob)
    praw = scope_bars(praw, in_block)
    braw, source_map = C.choose_bars(scope_bars(C.load_bars(bars_glob), in_block), praw)
    bars_hl = C.bars_by_session(braw)
    assert_block([k[1] for k in bars_hl], "census bars")
    ohlcv = load_ohlcv(polygon_glob, bars_glob, source_map)
    for k, b in ohlcv.items():                              # the same bars the census reads
        h = bars_hl.get(k)
        if h is None or len(h[0]) != len(b) or not np.allclose(h[3], b.close.to_numpy()):
            raise SystemExit(f"OHLCV bars differ from the census bars for {k}; refusing")
    adv_df = pd.read_csv(adv_csv, parse_dates=["session"])
    adv = {(r.ticker, r.session.date()): r.adv_dollars for r in adv_df.itertuples()}
    frames, E = run_census_captured(df, adv, bars_hl, va, macro_all, n_shuffles)
    cap = capture_matches_census(frames, E)
    if not all(v["match"] for v in cap.values()):
        raise SystemExit(f"captured events do not match the census counts: {cap}; refusing")
    dates = sorted({d for d in C.CALIBRATION_DATES if in_block(d)})
    ctx = Ctx(ohlcv, tide, iv, va, macro_excl, dates)
    prints_by_ts = {k: g for k, g in df.groupby(["ticker", "session"])}
    result = {"claim": CLAIM, "label": LABEL, "money_gate": MONEY_GATE, "block": [str(BACKTEST[0]), str(BACKTEST[1])],
              "ceiling": str(CEILING), "capture_check": cap, "census_set_ticker_sessions": len(S),
              "duplicate_tracking_ids_dropped": n_dup, "bar_source_map_counts": source_map.source.value_counts().to_dict(),
              "polygon_files": poly_info, "pythia_label": C.PYTHIA_LABEL, "variants": {}}
    funnel_rows = []
    eval_ts = [(tk, d) for (tk, d) in sorted(S) if in_block(d) and calendar_ok(d, macro_excl) == "OK"
               and not ctx.session_missing(tk, d)]
    eligible_sessions = sorted({d for d in dates if calendar_ok(d, macro_excl) == "OK"})
    for vname, wname in VARIANTS.items():
        ev = E[(E.window == wname) & (E.floor == FLOOR) & E.kept] if len(E) else E
        n_kept = len(ev)
        ev = ev[ev.d5 == True] if len(ev) else ev  # noqa: E712
        n_d5 = len(ev)
        ev = ev[ev.d6.isin(["BUYER", "SELLER"])] if len(ev) else ev
        n_side = len(ev)
        miss, fails, claims = {}, {}, []
        rng = np.random.default_rng(SEED_R)
        wstart = C.WINDOWS[wname][0].hour * 3600 + C.WINDOWS[wname][0].minute * 60
        tags = {"m4": 0, "fx_DXY": {}, "fx_USDJPY": {}, "eligible_but_macro_day": 0, "eligible_but_mon_fri": 0}
        for r in ev.itertuples():
            res = evaluate(ctx, r.ticker, r.session, r.t, r.L, r.d6)
            for m in res["missing"]:
                miss[m] = miss.get(m, 0) + 1
            for f in res["fails"]:
                fails[f] = fails.get(f, 0) + 1
            if not res["missing"] and res["fails"] in (["FAIL_MACRO"], ["FAIL_WEEKDAY"]):
                tags["eligible_but_macro_day" if res["fails"] == ["FAIL_MACRO"] else "eligible_but_mon_fri"] += 1
            if res["z"] is None or res["missing"] or res["fails"]:
                continue
            S0, t_conf = res["conf"]
            b1 = ctx.ohlcv[(r.ticker, r.session)]
            tL, hL = touched_held(b1, t_conf, r.L, S0)
            D = abs(r.L - S0)
            elig = b1.t_s[(b1.t_s >= wstart) & (b1.t_s < b1.t_s.max())].to_numpy()
            ctrl = controls(b1, elig, D, rng)
            mirror = touched_held(b1, t_conf, 2 * S0 - r.L, S0)
            zp = placebos(ctx, prints_by_ts, adv, r.ticker, r.session, r.t, wstart, rng, bars_hl, eligible_sessions)
            tags["m4"] += int(r.m4)
            for sym, key in (("DXY", "fx_DXY"), ("USDJPY", "fx_USDJPY")):
                stt = fx_state(fx, sym, r.session)
                tags[key][stt] = tags[key].get(stt, 0) + 1
            claims.append({"session": r.session, "side": r.d6, "z": res["z"], "zp": zp, "touched_L": tL,
                           "held_L": hL, "ctrl": ctrl, "mirror": mirror})
        summ = summarize(claims, len(eval_ts))
        summ.update({"census_frun_kept": n_kept, "d5_matched": n_d5, "side_assigned": n_side,
                     "unevaluable_by_ingredient": miss, "fails_by_ingredient": fails, "tags": tags,
                     "weight": "PRIMARY" if vname == PRIMARY else "SECONDARY (no verdict weight)"})
        result["variants"][vname] = summ
        for stage, n in (("census_frun_kept", n_kept), ("d5_matched", n_d5), ("side_assigned", n_side),
                         ("claim_events", len(claims))):
            funnel_rows.append({"variant": vname, "stage": stage, "count": n})
    p = result["variants"][PRIMARY]
    result["amendment_1"] = AMENDMENT_1
    result["amendment_2"] = AMENDMENT_2
    from datetime import datetime, timezone
    result["computed_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")   # for the outcome log
    floors_met = p["stat_kill_floor_met"] and p["freq_kill_floor_met"]
    result["verdict"] = "KILL" if p["kills_fired"] else ("NO-KILL" if floors_met else "NO-KILL (INSUFFICIENT n)")
    result["verdict_note"] = ("BACKTEST: KILL or NO-KILL only (R-IV.1080(d)). A KILL ends TRITON-R v1. "
                              "NO-KILL establishes nothing; the confirmation set stays sealed.")
    F = pd.DataFrame(funnel_rows)
    C.assert_aggregate({"funnel": F})
    os.makedirs(out_dir, exist_ok=True)
    F.to_csv(os.path.join(out_dir, "funnel.csv"), index=False)
    json.dump(result, open(os.path.join(out_dir, "backtest.json"), "w"), indent=1, default=str)
    print(json.dumps({"verdict": result["verdict"], "primary_claim_events": p["claim_events"],
                      "primary_kills": p["kills_fired"], "capture_check": cap}, indent=1, default=str))
    return result


# ── 8 · the weekly COUNT-ONLY job for the CONFIRMATION SET (R-IV.1080(b), R-IV.1084(d)) ─────────
CONFIRM_FIRST, CONFIRM_LAST = date(2026, 9, 25), date(2026, 12, 31)
NYSE_HOLIDAYS_CONFIRM = {date(2026, 11, 26), date(2026, 12, 25)}
COUNT_COLUMNS = ["variant", "weight", "as_of", "window_first", "window_last", "window_sessions",
                 "evaluable_ticker_sessions", "claim_events", "sessions_with_claim_events", "stop_rule_met"]


def confirmation_dates(as_of):
    return [d.date() for d in pd.bdate_range(CONFIRM_FIRST, as_of) if d.date() not in NYSE_HOLIDAYS_CONFIRM]


class census_window:
    """Point the frozen census readers at `dates` (the date window is the only change), then restore.
    TRITON-R only: the reserve is sealed FOR TRITON-R (amendment 9); this never computes an outcome."""

    def __init__(self, dates, name):
        self.dates, self.name = list(dates), name

    def __enter__(self):
        self.saved = (C.CALIBRATION, C.CALIBRATION_DATES, C.WINDOW_NAME)
        C.CALIBRATION, C.CALIBRATION_DATES, C.WINDOW_NAME = (min(self.dates), max(self.dates)), self.dates, self.name
        return self

    def __exit__(self, *exc):
        C.CALIBRATION, C.CALIBRATION_DATES, C.WINDOW_NAME = self.saved
        return False


def _today_et():
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    return datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York")).date()


def check_as_of(as_of, today=None):
    today = today or _today_et()
    if not (CONFIRM_FIRST <= as_of <= CONFIRM_LAST):
        raise SystemExit(f"as_of {as_of} outside the confirmation set {CONFIRM_FIRST}..{CONFIRM_LAST}; refusing")
    if as_of >= today:
        raise SystemExit(f"as_of {as_of} is not a completed session (today ET {today}); refusing")


def count(as_of, prints_glob, complete_csv, bars_glob, polygon_glob, va_csv, macro_csv, tide_csv, iv_csv, out_dir,
          n_shuffles=None, today=None):
    """Per-variant claim-event and evaluable-session counts for the confirmation set 09-25 .. as_of, and
    NOTHING else (R-IV.1084(d)). D1-D7, the sec. 5 filters and the calendar only; never S_close, Z, a move or a
    placebo outcome. History bars 09-01 .. 09-24 are read only for ATR / EMA / slot-median continuity."""
    as_of = pd.Timestamp(as_of).date()
    check_as_of(as_of, today)
    conf = confirmation_dates(as_of)
    hist = [d for d in C.CALIBRATION_DATES if in_block(d)]             # 09-01 .. 09-24, seal excluded
    scope = set(conf) | set(hist)

    def in_scope(d):
        return d in scope

    def read_scoped(path, col, what, allowed):
        df = pd.read_csv(path)
        bad = sorted({str(x) for x in _dates(df[col]) if x not in allowed})
        if bad:
            raise SystemExit(f"DATE CEILING: {what} carries dates outside its scope: {bad[:5]}. Refusing.")
        return df
    va = read_scoped(va_csv, "session", "va_csv", set(conf))
    va = {(r.ticker, pd.Timestamp(r.session).date()): (r.vah, r.val) for r in va.itertuples()}
    mac = read_scoped(macro_csv, "date", "macro_csv", set(confirmation_dates(CONFIRM_LAST)))   # public schedule
    macro_excl = {pd.Timestamp(r.date).date() for r in mac.itertuples() if str(r.event) in MACRO_EXCLUDE}
    td = read_scoped(tide_csv, "session_date", "tide_csv", set(conf))
    t = pd.to_datetime(td.tick_at, utc=True).dt.tz_convert("America/New_York")
    td = td.assign(t_s=(t - t.dt.normalize()).dt.total_seconds(),
                   net=pd.to_numeric(td.net_call_premium) - pd.to_numeric(td.net_put_premium),
                   d=pd.to_datetime(td.session_date).dt.date)
    tide = {d: g.sort_values("t_s")[["t_s", "net"]].reset_index(drop=True) for d, g in td.groupby("d")}
    ivd = read_scoped(iv_csv, "session_date", "iv_csv", scope)          # presence of the prior session only
    iv = {(r.ticker, pd.Timestamp(r.session_date).date()): float(r.iv_near) if pd.notna(r.iv_near) else np.nan
          for r in ivd.itertuples()}
    praw, _ = load_polygon_multi(polygon_glob)
    praw = scope_bars(praw, in_scope)                                  # the ceiling, at the read
    readme = scope_bars(C.load_bars(bars_glob), in_scope)
    with census_window(hist, "triton-r-history"):
        _, smap_h = C.choose_bars(readme, praw)
    with census_window(conf, "triton-r-confirmation-count"):
        raw = scope_raw(C._read_parquet(prints_glob), lambda d: d in set(conf))   # confirmation prints only
        build_set = C.build_complete_set(raw)
        S, _, refusals = C.census_set(pd.read_csv(complete_csv), build_set)
        if refusals:
            raise SystemExit(C.refusal_message(refusals))
        df, _, _ = C.prepare_prints(raw, S)
        if len(df) and not all(d in set(conf) for d in set(df.session)):
            raise SystemExit("DATE CEILING: prints outside the confirmation window; refusing")
        braw, smap_c = C.choose_bars(readme, praw)
        bars_hl = C.bars_by_session(braw)
        frames, E = run_census_captured(df, {}, bars_hl, va, set(), n_shuffles)   # F-ADV outside the claim: no ADV
    cap = capture_matches_census(frames, E)
    if not all(v["match"] for v in cap.values()):
        raise SystemExit("captured events do not match the census counts; refusing")
    ohlcv = load_ohlcv(polygon_glob, bars_glob, pd.concat([smap_h, smap_c], ignore_index=True), in_scope)
    ctx = Ctx(ohlcv, tide, iv, va, macro_excl, sorted(scope))
    eval_ts = [(tk, d) for (tk, d) in sorted(S) if d in set(conf) and calendar_ok(d, macro_excl) == "OK"
               and not ctx.session_missing(tk, d)]
    rows = []
    for vname, wname in VARIANTS.items():
        ev = E[(E.window == wname) & (E.floor == FLOOR) & E.kept] if len(E) else E
        ev = ev[(ev.d5 == True) & ev.d6.isin(["BUYER", "SELLER"])] if len(ev) else ev  # noqa: E712
        n, sess = 0, set()
        for r in ev.itertuples():
            res = evaluate(ctx, r.ticker, r.session, r.t, r.L, r.d6, outcome=False)
            if not res["missing"] and not res["fails"]:
                n += 1
                sess.add(r.session)
        primary = vname == PRIMARY
        rows.append({"variant": vname, "weight": "PRIMARY" if primary else "SECONDARY", "as_of": str(as_of),
                     "window_first": str(conf[0]), "window_last": str(conf[-1]), "window_sessions": len(conf),
                     "evaluable_ticker_sessions": len(eval_ts), "claim_events": n,
                     "sessions_with_claim_events": len(sess),
                     "stop_rule_met": bool(primary and ((n >= MIN_EVENTS and len(sess) >= MIN_SESSIONS)
                                                        or as_of >= CONFIRM_LAST)) if primary else ""})
    out = pd.DataFrame(rows, columns=COUNT_COLUMNS)
    C.assert_aggregate({"counts": out})
    os.makedirs(out_dir, exist_ok=True)
    out.to_csv(os.path.join(out_dir, "counts.csv"), index=False)
    print(out.to_string(index=False))
    return out


# ── self-test (synthetic only) ───────────────────────────────────────────────────────────────────
def _e2e():
    """`backtest` end to end on synthetic files in every input's real format."""
    import tempfile
    checks = {}
    rng = np.random.default_rng(11)
    raw, braw, sessions = C._synthetic_vendor(rng)
    cal = [d for d in C.CALIBRATION_DATES]
    with tempfile.TemporaryDirectory() as td:
        for tk, g in raw.groupby("ticker"):
            os.makedirs(os.path.join(td, "dp", tk), exist_ok=True)
            g.to_parquet(os.path.join(td, "dp", tk, "202609.parquet"), index=False)
        C._write_readme_bars(braw, os.path.join(td, "bars1m"))
        for d in ("2026-09-02", "2026-09-03"):
            C._write_polygon(os.path.join(td, "poly"), "SPY", d, {})
        bpairs = {(t, pd.Timestamp(s).date()) for t, s in zip(raw.ticker, raw.session_date)}
        pd.DataFrame([{"ticker": t, "session": e.isoformat(), "complete": (t, e) in bpairs}
                      for t in C.CORE8 for e in cal]).to_csv(os.path.join(td, "complete.csv"), index=False)
        pd.DataFrame([{"ticker": t, "session": e.isoformat(), "adv_dollars": 2.5e9}
                      for t in C.CORE8 for e in cal]).to_csv(os.path.join(td, "adv.csv"), index=False)
        pd.DataFrame([{"ticker": t, "session": e, "vah": 503.0, "val": 501.5}
                      for t in C.CORE8 for e in ("2026-09-02", "2026-09-03")]).to_csv(os.path.join(td, "va.csv"), index=False)
        pd.DataFrame({"date": ["2026-09-03"], "event": ["initial_claims"], "source": ["test"]}).to_csv(
            os.path.join(td, "macro.csv"), index=False)
        rows = []
        for d in ("2026-09-02", "2026-09-03"):
            for k in range(81):
                ts = pd.Timestamp(d + " 09:30", tz="America/New_York") + pd.Timedelta(minutes=5 * k)
                rows.append({"session_date": d, "tick_at": ts.tz_convert("UTC").isoformat(),
                             "net_call_premium": 1e6 + 1e4 * k, "net_put_premium": 1e6})
        pd.DataFrame(rows).to_csv(os.path.join(td, "tide.csv"), index=False)
        pd.DataFrame([{"ticker": t, "session_date": d, "iv_near": 0.2} for t in C.CORE8
                      for d in ("2026-09-01", "2026-09-02", "2026-09-03")]).to_csv(os.path.join(td, "iv.csv"), index=False)
        fxd = pd.bdate_range("2026-05-01", "2026-09-24")
        pd.DataFrame([{"date": d.date().isoformat(), "symbol": s, "close": 100 + 0.01 * i}
                      for s in ("DXY", "USDJPY") for i, d in enumerate(fxd)]).to_csv(os.path.join(td, "fx.csv"), index=False)
        args = [os.path.join(td, "dp", "*", "*.parquet"), os.path.join(td, "complete.csv"),
                os.path.join(td, "bars1m", "*", "*.parquet"), os.path.join(td, "poly", "*.parquet"),
                os.path.join(td, "adv.csv"), os.path.join(td, "va.csv"), os.path.join(td, "macro.csv"),
                os.path.join(td, "tide.csv"), os.path.join(td, "iv.csv"), os.path.join(td, "fx.csv")]
        res = backtest(*args, os.path.join(td, "out"), n_shuffles=40)
        out = os.path.join(td, "out")
        checks["E2E: backtest runs; capture equals the census in both windows"] = \
            all(v["match"] for v in res["capture_check"].values())
        checks["E2E: verdict is NO-KILL (INSUFFICIENT n) on a plumbing-sized run, read on TG-ON"] = \
            res["verdict"] == "NO-KILL (INSUFFICIENT n)" and res["amendment_1"].startswith("TRITON-R-v1-AMENDMENT-1") and \
            res["amendment_2"].startswith("TRITON-R-v1-AMENDMENT-2") and res["computed_at_utc"].startswith("20") and \
            res["variants"]["TG-ON"]["weight"] == "PRIMARY" and res["variants"]["TG-OFF"]["weight"].startswith("SECONDARY")
        F = pd.read_csv(os.path.join(out, "funnel.csv"))
        checks["E2E: outputs written; funnel is counts only"] = os.path.exists(os.path.join(out, "backtest.json")) and \
            set(F.columns) == {"variant", "stage", "count"}
        v = res["variants"]["TG-ON"]
        checks["E2E: side-assigned events reach the recipe and are UNEVALUABLE (no 10-session history), not FAIL"] = \
            v["side_assigned"] > 0 and v["claim_events"] == 0 and "slot_median_history" in v["unevaluable_by_ingredient"]
        checks["E2E: the money-gate label and the out-of-sample label are carried"] = \
            res["money_gate"].startswith("money gate: NOT EVALUABLE") and res["label"].startswith("out of sample, not blind")
        t2 = pd.read_csv(os.path.join(td, "tide.csv"))
        t2.loc[0, "session_date"] = "2026-09-25"
        t2.to_csv(os.path.join(td, "tide_bad.csv"), index=False)
        a2 = list(args)
        a2[7] = os.path.join(td, "tide_bad.csv")
        try:
            backtest(*a2, os.path.join(td, "out2"), n_shuffles=40)
            checks["E2E: a tide file with one 09-25 row refuses the whole run before any figure"] = False
        except SystemExit as e_:
            checks["E2E: a tide file with one 09-25 row refuses the whole run before any figure"] = \
                "DATE CEILING" in str(e_) and not os.path.exists(os.path.join(td, "out2"))
    return checks


def _count_tests():
    """The weekly COUNT-ONLY job: scope, refusals, schema, and that no outcome is ever read."""
    import tempfile
    checks = {}
    today = date(2026, 10, 15)
    for a, nm in ((date(2026, 9, 24), "before 09-25"), (date(2027, 1, 4), "after 12-31"),
                  (date(2026, 10, 15), "today (not a completed session)")):
        try:
            check_as_of(a, today)
            checks[f"COUNT: as_of {nm} refuses"] = False
        except SystemExit:
            checks[f"COUNT: as_of {nm} refuses"] = True
    cd = confirmation_dates(date(2026, 11, 30))
    checks["COUNT: confirmation dates 09-25 .. 11-30 skip Thanksgiving (46 sessions)"] = \
        date(2026, 11, 26) not in cd and cd[0] == date(2026, 9, 25) and len(cd) == 46
    saved = (C.CALIBRATION, list(C.CALIBRATION_DATES), C.WINDOW_NAME)
    with census_window(cd, "x"):
        inside = (C.CALIBRATION, C.WINDOW_NAME)
    checks["COUNT: the census window is set inside and restored after"] = inside == ((cd[0], cd[-1]), "x") and \
        (C.CALIBRATION, list(C.CALIBRATION_DATES), C.WINDOW_NAME) == saved
    # outcome=False never needs S_close: NaN closes after 12:00 do not change the claim decision
    ds = [date(2026, 9, d) for d in (1, 2, 3, 4, 8, 9, 10, 11, 14, 15, 16, 17)]

    def flat(base=100.0):
        t = np.arange(RTH0, RTH1, 60.0)
        return pd.DataFrame({"t_s": t, "open": base, "high": base + 0.05, "low": base - 0.05, "close": base,
                             "volume": 1000.0})
    oh = {("SPY", d): flat() for d in ds[:-1]}
    last = flat()
    up = last.t_s >= 10 * 3600 + 5 * 60
    last.loc[up, ["open", "high", "low", "close"]] += 1.0
    last.loc[(last.t_s >= 10 * 3600 + 5 * 60) & (last.t_s < 10 * 3600 + 10 * 60), "volume"] *= 3
    last.loc[last.t_s >= 12 * 3600, ["open", "high", "low", "close"]] = np.nan
    oh[("SPY", ds[-1])] = last
    tide = {ds[-1]: pd.DataFrame({"t_s": RTH0 + 300.0 * np.arange(81), "net": np.arange(81, dtype=float)})}
    ctx = Ctx(oh, tide, {("SPY", ds[-2]): 0.2}, {("SPY", ds[-1]): (102.0, 100.5)}, set(), ds)
    r0 = evaluate(ctx, "SPY", ds[-1], 10 * 3600, 100.0, "BUYER", outcome=False)
    r1 = evaluate(ctx, "SPY", ds[-1], 10 * 3600, 100.0, "BUYER", outcome=True)
    checks["COUNT: outcome=False decides the claim without S_close (closes after 12:00 are NaN)"] = \
        r0["missing"] == [] and r0["fails"] == [] and r0["z"] is None and r1["z"] is not None and np.isnan(r1["z"])
    # end to end on synthetic files: schema is exactly the count columns
    rng = np.random.default_rng(5)
    raw, braw, sessions = C._synthetic_vendor(rng)
    with tempfile.TemporaryDirectory() as td:
        for tk, g in raw.groupby("ticker"):
            os.makedirs(os.path.join(td, "dp", tk), exist_ok=True)
            g.to_parquet(os.path.join(td, "dp", tk, "202609.parquet"), index=False)
        C._write_readme_bars(braw, os.path.join(td, "bars1m"))
        for d in ("2026-09-02", "2026-09-03"):
            C._write_polygon(os.path.join(td, "poly_hist"), "SPY", d, {})
        C._write_polygon(os.path.join(td, "poly_conf"), "SPY", "2026-09-28", {})
        conf = confirmation_dates(date(2026, 9, 28))
        bp = {(t, pd.Timestamp(s).date()) for t, s in zip(raw.ticker, raw.session_date)}
        pd.DataFrame([{"ticker": t, "session": e.isoformat(), "complete": (t, e) in bp}
                      for t in C.CORE8 for e in conf]).to_csv(os.path.join(td, "complete.csv"), index=False)
        pd.DataFrame([{"ticker": t, "session": "2026-09-28", "vah": 503.0, "val": 501.5}
                      for t in C.CORE8]).to_csv(os.path.join(td, "va.csv"), index=False)
        pd.DataFrame({"date": ["2026-09-28"], "event": ["initial_claims"], "source": ["t"]}).to_csv(
            os.path.join(td, "macro.csv"), index=False)
        rows = [{"session_date": "2026-09-28",
                 "tick_at": (pd.Timestamp("2026-09-28 09:30", tz="America/New_York") + pd.Timedelta(minutes=5 * k))
                 .tz_convert("UTC").isoformat(), "net_call_premium": 1e6 + k, "net_put_premium": 1e6} for k in range(81)]
        pd.DataFrame(rows).to_csv(os.path.join(td, "tide.csv"), index=False)
        pd.DataFrame([{"ticker": t, "session_date": d, "iv_near": 0.2} for t in C.CORE8
                      for d in ("2026-09-24", "2026-09-25")]).to_csv(os.path.join(td, "iv.csv"), index=False)
        args = ["2026-09-28", os.path.join(td, "dp", "*", "*.parquet"), os.path.join(td, "complete.csv"),
                os.path.join(td, "bars1m", "*", "*.parquet"),
                os.path.join(td, "poly_hist", "*.parquet") + ";" + os.path.join(td, "poly_conf", "*.parquet"),
                os.path.join(td, "va.csv"), os.path.join(td, "macro.csv"), os.path.join(td, "tide.csv"),
                os.path.join(td, "iv.csv"), os.path.join(td, "out")]
        out = count(*args, n_shuffles=30, today=today)
        f = pd.read_csv(os.path.join(td, "out", "counts.csv"))
        checks["COUNT e2e: output schema is EXACTLY the count columns, one row per variant"] = \
            list(f.columns) == COUNT_COLUMNS and list(f.variant) == ["TG-ON", "TG-OFF"] and len(out) == 2
        checks["COUNT e2e: window 09-25 .. 09-28 (2 sessions); primary stop rule not met"] = \
            f.window_sessions.iloc[0] == 2 and str(f.stop_rule_met.iloc[0]) in ("False", "false")
        t2 = pd.read_csv(os.path.join(td, "tide.csv"))
        t2.loc[0, "session_date"] = "2026-10-20"
        t2.to_csv(os.path.join(td, "tide_bad.csv"), index=False)
        a2 = list(args)
        a2[7] = os.path.join(td, "tide_bad.csv")
        try:
            count(*a2, n_shuffles=30, today=today)
            checks["COUNT e2e: a tide row after as_of refuses"] = False
        except SystemExit as e_:
            checks["COUNT e2e: a tide row after as_of refuses"] = "DATE CEILING" in str(e_)
    return checks


def selftest():
    import tempfile
    checks = {}
    # 0 · DATE CEILINGS FIRST
    for bad, nm in ((date(2026, 9, 25), "the ceiling day 09-25"), (date(2026, 10, 5), "a holdout day"),
                    (date(2026, 8, 20), "a sealed day"), (date(2026, 8, 31), "a quarantined day")):
        try:
            assert_block([date(2026, 9, 2), bad], "probe")
            checks[f"CEILING: {nm} refuses"] = False
        except SystemExit:
            checks[f"CEILING: {nm} refuses"] = True
    try:
        assert_block([date(2026, 9, 1), date(2026, 9, 24)], "probe")
        checks["CEILING: 09-01 and 09-24 pass"] = True
    except SystemExit:
        checks["CEILING: 09-01 and 09-24 pass"] = False
    with tempfile.TemporaryDirectory() as td:
        for nm, frame, col in (("tide_csv", {"session_date": ["2026-09-24", "2026-09-25"]}, "session_date"),
                               ("iv_csv", {"session_date": ["2026-09-24", "2026-10-01"]}, "session_date"),
                               ("va_csv", {"session": ["2026-09-02", "2026-09-28"]}, "session"),
                               ("macro_csv", {"date": ["2026-09-11", "2026-10-14"]}, "date")):
            p = os.path.join(td, nm + ".csv")
            pd.DataFrame(frame).to_csv(p, index=False)
            try:
                read_block_csv(p, col, nm)
                checks[f"CEILING: {nm} with a row on/after 09-25 refuses"] = False
            except SystemExit:
                checks[f"CEILING: {nm} with a row on/after 09-25 refuses"] = True
        p = os.path.join(td, "fx.csv")
        pd.DataFrame({"date": ["2026-09-24", "2026-09-25"], "symbol": "DXY", "close": [100, 100]}).to_csv(p, index=False)
        try:
            read_fx(p)
            checks["CEILING: fx reaching 09-25 refuses (read_fx)"] = False
        except SystemExit:
            checks["CEILING: fx reaching 09-25 refuses (read_fx)"] = True
        pd.DataFrame({"date": ["2026-08-20", "2026-08-14", "2026-09-24"], "symbol": "DXY",
                      "close": [1, 2, 3]}).to_csv(p, index=False)
        checks["CEILING: fx keeps pre-block history but drops sealed dates"] = \
            sorted(read_fx(p).date) == ["2026-08-14", "2026-09-24"]
    checks["CEILING: census window equals the backtest block"] = C.CALIBRATION == BACKTEST and \
        all(in_block(d) for d in C.CALIBRATION_DATES) and len(C.CALIBRATION_DATES) == 17
    # 1 · the frozen census, captured: counts equal the census's own
    rng = np.random.default_rng(7)
    raw, braw, sessions = C._synthetic_vendor(rng)
    complete = {(tk, s.date()) for tk in C.CORE8 for s in sessions}
    df, _, _ = C.prepare_prints(raw, complete)
    hl = C.bars_by_session(braw)
    frames, E = run_census_captured(df, {}, hl, {}, set(), n_shuffles=40)
    cap = capture_matches_census(frames, E)
    checks["CAPTURE: real FRUN kept and D5 counts equal the frozen census's, both windows"] = \
        all(v["match"] for v in cap.values()) and len(E) > 0
    frames2 = C.census(df, {}, hl, {}, n_shuffles=40)
    checks["CAPTURE: the wrapped run leaves the census outputs byte-identical"] = \
        frames2["events_m4_d5"].equals(frames["events_m4_d5"]) and frames2["per_ticker_session"].equals(frames["per_ticker_session"])
    checks["CAPTURE: event_rows restored after the run"] = C.event_rows.__name__ == "event_rows"
    # 2 · D7 / ATR / slot median / EMA / tide / PYTHIA / calendar on hand-made bars
    def sess_b1(base=100.0, jump_at=None, jump=0.0, vol=1000.0, vol_at=None, vmult=1.0):
        t = np.arange(RTH0, RTH1, 60.0)
        c = np.full(len(t), base)
        if jump_at is not None:
            c[t >= jump_at] += jump
        v = np.full(len(t), vol)
        if vol_at is not None:
            v[(t >= vol_at) & (t < vol_at + 300)] *= vmult
        return pd.DataFrame({"t_s": t, "open": c, "high": c + 0.05, "low": c - 0.05, "close": c, "volume": v})
    ds = [date(2026, 9, d) for d in (1, 2, 3, 4, 8, 9, 10, 11, 14, 15, 16, 17)]
    ohlcv = {("SPY", d): sess_b1() for d in ds[:-1]}
    ohlcv[("SPY", ds[-1])] = sess_b1(jump_at=11 * 3600 + 20 * 60, jump=1.0, vol_at=11 * 3600 + 20 * 60, vmult=3.0)
    ctx = Ctx(ohlcv, {}, {}, {}, set(), ds)
    seq = ctx.seq["SPY"]
    mask = (seq.session == ds[-1]).to_numpy()
    st, i = d7(seq, mask, ctx.prior_b5("SPY", ds[-1]), 11 * 3600 + 15 * 60, 100.0, "BUYER")
    checks["D7: a 5-min close beyond L + 0.25 ATR on above-median volume confirms (11:25 bar)"] = \
        st == "CONFIRMED" and seq.t_close.iloc[i] == 11 * 3600 + 25 * 60
    st2, _ = d7(seq, mask, ctx.prior_b5("SPY", ds[-1]), 11 * 3600 + 15 * 60, 100.0, "SELLER")
    checks["D7: the wrong side does not confirm"] = st2 == "UNCONFIRMED"
    st3, _ = d7(seq, mask, ctx.prior_b5("SPY", ds[-1]), 9 * 3600 + 40 * 60, 100.0, "BUYER")
    checks["D7: no break within 60 min -> UNCONFIRMED"] = st3 == "UNCONFIRMED"
    ctx_short = Ctx({k: v for k, v in ohlcv.items() if k[1] >= ds[3]}, {}, {}, {}, set(), ds[3:])
    s2 = ctx_short.seq["SPY"]
    st4, what = d7(s2, (s2.session == ds[-1]).to_numpy(), ctx_short.prior_b5("SPY", ds[-1]),
                   11 * 3600 + 15 * 60, 100.0, "BUYER")
    checks["D7: fewer than 10 prior sessions -> MISSING slot_median"] = st4 == "MISSING" and what == "slot_median"
    closes = np.arange(30, dtype=float)
    checks["EMA: < 20 bars -> None; seeded by SMA20 then recursive"] = ema_at(closes, 18) is None and \
        abs(ema_at(closes, 19) - np.mean(closes[:20])) < 1e-12 and abs(ema_at(closes, 20) - (2 / 21 * 20 + 19 / 21 * 9.5)) < 1e-9
    ticks = pd.DataFrame({"t_s": RTH0 + 300.0 * np.arange(10), "net": np.arange(10, dtype=float) * 5})
    checks["TIDE: slope over 6 ticks; too early -> None"] = tide_slope(ticks, RTH0 + 300 * 7 + 10) == 30.0 and \
        tide_slope(ticks, RTH0 + 300 * 3) is None
    checks["PYTHIA: outside/edge PASS, mid FAIL, no VA MISSING"] = pythia_pass(99.0, (110.0, 100.0), "BUYER") == "PASS" and \
        pythia_pass(105.0, (110.0, 100.0), "BUYER") == "FAIL" and pythia_pass(105.0, None, "BUYER") == "MISSING"
    checks["CALENDAR: Mon/Fri FAIL, CPI/FOMC FAIL, Tue OK"] = calendar_ok(date(2026, 9, 14), set()) == "FAIL_WEEKDAY" and \
        calendar_ok(date(2026, 9, 16), {date(2026, 9, 16)}) == "FAIL_MACRO" and calendar_ok(date(2026, 9, 15), set()) == "OK"
    # 3 · Z, level respect, controls
    tk_ = ("SPY", ds[-1])
    ivd = {("SPY", ds[-2]): 0.20}
    tide = {ds[-1]: pd.DataFrame({"t_s": RTH0 + 300.0 * np.arange(81), "net": np.arange(81, dtype=float)})}
    va = {tk_: (102.0, 100.5)}                         # L = 100 below VAL -> LONG "outside" -> PASS
    o2 = dict(ohlcv)
    late = (o2[tk_].t_s >= 15 * 3600).to_numpy()
    o2[tk_] = o2[tk_].assign(close=np.where(late, o2[tk_].close + 0.5, o2[tk_].close),
                             high=np.where(late, o2[tk_].high + 0.5, o2[tk_].high),
                             low=np.where(late, o2[tk_].low + 0.5, o2[tk_].low))
    ctx2 = Ctx(o2, tide, ivd, va, set(), ds)
    res = evaluate(ctx2, "SPY", ds[-1], 11 * 3600 + 15 * 60, 100.0, "BUYER")
    tau_y = ((RTH1 - (11 * 3600 + 25 * 60)) / 60) / (390 * 252)
    z_exp = (101.5 - 101.0) / (101.0 * 0.20 * np.sqrt(tau_y))
    checks["EVALUATE: Thu claim event, all ingredients present -> Z computed"] = \
        res["missing"] == [] and res["fails"] == [] and res["z"] is not None and abs(res["z"] - z_exp) < 1e-12
    res_s = evaluate(Ctx(o2, tide, ivd, {tk_: (99.5, 98.0)}, set(), ds), "SPY", ds[-1], 11 * 3600 + 15 * 60,
                     100.0, "SELLER")
    checks["EVALUATE: SELLER on a rising tape fails D7 (no break below L)"] = res_s["fails"] == ["D7_unconfirmed"]
    # amendment 1: the EMA runs continuously -> a 10:10 confirmation is evaluable (it was not under 5.5)
    o3 = {k: v for k, v in ohlcv.items() if k != tk_}
    o3[tk_] = sess_b1(jump_at=10 * 3600 + 5 * 60, jump=1.0, vol_at=10 * 3600 + 5 * 60, vmult=3.0)
    ctx3 = Ctx(o3, tide, ivd, va, set(), ds)
    r3 = evaluate(ctx3, "SPY", ds[-1], 10 * 3600, 100.0, "BUYER")
    sess_closes = ctx3.b5[tk_].close.to_numpy()
    checks["A1 EMA: a 10:10 ET confirmation is evaluable (continuous EMA); the session-only EMA would be None"] = \
        r3["missing"] == [] and r3["fails"] == [] and r3["z"] is not None and r3["conf"][1] == 10 * 3600 + 10 * 60 \
        and ema_at(sess_closes, 7) is None
    first = ctx3.seq["SPY"]
    checks["A1 EMA: only the first 19 readable bars (from 09-01) are UNEVALUABLE"] = \
        ema_at(first.close.to_numpy(), 18) is None and ema_at(first.close.to_numpy(), 19) is not None \
        and first.session.iloc[0] == date(2026, 9, 1)
    res_m = evaluate(Ctx(o2, tide, {}, va, set(), ds), "SPY", ds[-1], 11 * 3600 + 15 * 60, 100.0, "BUYER")
    checks["EVALUATE: no prior-session IV -> UNEVALUABLE (missing), never FAIL"] = \
        "iv_prior_session" in res_m["missing"] and res_m["z"] is None
    b1 = pd.DataFrame({"t_s": [0.0, 60, 120, 180], "open": 0.0, "high": [101, 100.2, 100.1, 101], "low": [100.5, 99.98, 99.9, 100.5],
                       "close": [100.8, 100.1, 100.05, 100.9], "volume": 1.0})
    checks["RESPECT: touched and held"] = touched_held(b1, 0, 100.0, 101.0) == (True, True)
    b1b = b1.assign(close=[100.8, 100.1, 99.5, 100.9])
    checks["RESPECT: touched then closed through -> not held"] = touched_held(b1b, 0, 100.0, 101.0) == (True, False)
    checks["RESPECT: never touched"] = touched_held(b1, 0, 90.0, 101.0) == (False, False)
    cr = controls(ohlcv[tk_], ohlcv[tk_].t_s.to_numpy()[:-1], 0.5, np.random.default_rng(1))
    cr2 = controls(ohlcv[tk_], ohlcv[tk_].t_s.to_numpy()[:-1], 0.5, np.random.default_rng(1))
    checks["CONTROLS: K = 20, fixed seed reproduces"] = len(cr) == K_CONTROLS and cr == cr2
    # 4 · statistics, kills, verdict
    days10 = [date(2026, 9, d) for d in (1, 2, 3, 4, 8, 9, 10, 11, 14, 15)]
    evs = [{"session": days10[i % 10], "side": "BUYER", "z": 0.1, "zp": [0.5], "touched_L": True,
            "held_L": False, "ctrl": [(True, True)] * 20, "mirror": (True, True)} for i in range(30)]
    sm = summarize(evs, 40)
    checks["KILL (floor met: 30 events / 10 sessions): placebo keeps pace when every event trails"] = \
        sm["stat_kill_floor_met"] and sm["kill_placebo_keeps_pace"] and sm["win2_hi"] <= 0
    checks["KILL (floor met): L not respected when L never holds and controls always do"] = sm["kill_L_not_respected"]
    checks["RATE: 30 events / 40 evaluable ticker-sessions x 24 = 18 per week, no rate kill"] = \
        abs(sm["rate_per_week"] - 18.0) < 1e-9 and not sm["kill_under_1_per_week"]
    checks["KILL: one week carries it does NOT fire when every week agrees"] = sm["kill_one_week_carries_it"] is False
    wk = [dict(e, z=(3.0 if e["session"] <= date(2026, 9, 4) else -0.5), zp=[0.0]) for e in evs]
    sm4 = summarize(wk, 40)
    checks["KILL (floor met): one week carries it (a +3 week over -0.5 weeks)"] = sm4["kill_one_week_carries_it"] is True
    sm12 = summarize(evs[:12], 40)
    checks["FLOOR (amendment 1): 12 events -> statistical kills do NOT fire; raw readings kept"] = \
        not sm12["stat_kill_floor_met"] and not sm12["kill_placebo_keeps_pace"] and not sm12["kill_L_not_respected"] \
        and sm12["raw_kill_readings"]["placebo_keeps_pace"] and sm12["raw_kill_readings"]["L_not_respected"]
    wk12 = summarize(wk[:12], 40)
    checks["FLOOR: one week carries it does not fire below 30 events / 10 sessions"] = \
        wk12["raw_kill_readings"]["one_week_carries_it"] and not wk12["kill_one_week_carries_it"]
    sm2 = summarize(evs[:1], 40)
    checks["FREQUENCY KILL: 1 event / 40 evaluable ticker-sessions = 0.6 < 1 with >= 20 -> KILL"] = \
        sm2["freq_kill_floor_met"] and sm2["kill_under_1_per_week"]
    sm3 = summarize([], 19)                         # rate 0 < 1, but only 19 evaluable ticker-sessions
    checks["FREQUENCY FLOOR: 0 events / 19 evaluable ticker-sessions -> no frequency kill (raw reading kept)"] = \
        not sm3["freq_kill_floor_met"] and not sm3["kill_under_1_per_week"] and sm3["raw_kill_readings"]["under_1_per_week"]
    checks["MIN N: 12 events -> min_n_met False"] = sm12["min_n_met"] is False
    # amendment 2
    bt = pd.DataFrame({"t_s": [0.0, 60, 120, 180], "open": 0.0, "high": [100.5, 105.05, 105.05, 105.05],
                       "low": [99.5, 104.95, 104.95, 104.95], "close": [100.0, 105.0, 105.0, 105.0], "volume": 1.0})
    ct = controls(bt, np.array([0.0]), 0.2, np.random.default_rng(3))
    checks["A2 sec. 2: a control is measured from t_r + 1 min -- a touch only in the t_r bar does not count"] = \
        len(ct) == K_CONTROLS and all(c == (False, False) for c in ct)
    both = [dict(e, side=("BUYER" if i % 2 else "SELLER"), z=0.6, zp=[0.1]) for i, e in enumerate(evs[:12])]
    s_ok = summarize(both, 40)
    checks["A2 sec. 4: both sides with >= 5 claim events and non-negative -> WIN 4 met"] = \
        s_ok["win4"] and s_ok["win4_not_met_sides"] == [] and s_ok["win4_by_side"]["SELLER"]["claim_events"] == 6
    few = [dict(e, side="BUYER") for e in both[:9]] + [dict(both[0], side="SELLER")] * 3
    s_few = summarize(few, 40)
    checks["A2 sec. 4: SELLER with 3 claim events -> WIN 4 NOT MET, SELLER named"] = \
        not s_few["win4"] and s_few["win4_not_met_sides"] == ["SELLER"]
    s_none = summarize([dict(e, side="BUYER") for e in both], 40)
    checks["A2 sec. 4: an EMPTY side never satisfies WIN 4 silently (SELLER named)"] = \
        not s_none["win4"] and s_none["win4_not_met_sides"] == ["SELLER"] and \
        s_none["win4_by_side"]["SELLER"]["claim_events"] == 0
    four = [date(2026, 9, d) for d in (15, 16, 17, 22)]
    sus = [dict(evs[0], session=four[i % 4], touched_L=(i % 4 == 0), held_L=(i % 4 == 0)) for i in range(16)]
    s_sus = summarize(sus, 40)
    checks["A2 sec. 5: WIN 1 interval with > 10% skipped resamples is labelled SUSPECT"] = \
        s_sus["win1_suspect"] and s_sus["win1_boot_skipped"] > 0.10 * BOOT_B
    checks["A2 sec. 5: a well-defined interval is not SUSPECT"] = sm["win1_suspect"] is False and sm["win2_suspect"] is False
    checks["A2 sec. 3: WIN 1 uses the same 10,000 fixed-seed resamples as WIN 2"] = \
        sm["win1_boot_used"] + sm["win1_boot_skipped"] == BOOT_B == sm["win2_boot_used"] + sm["win2_boot_skipped"]
    p, lo, hi, _ = boot_ci({1: [1.0, 2.0], 2: [3.0]}, mean_stat, B=500)
    p_, lo_, hi_, _ = boot_ci({1: [1.0, 2.0], 2: [3.0]}, mean_stat, B=500)
    checks["BOOTSTRAP: fixed seed reproduces; lo <= point <= hi"] = (p, lo, hi) == (p_, lo_, hi_) and lo <= p <= hi
    try:
        C.assert_aggregate({"x": pd.DataFrame({"variant": ["a"], "L": [1.0]})})
        checks["AGGREGATE: an output with an L column refuses"] = False
    except RuntimeError:
        checks["AGGREGATE: an output with an L column refuses"] = True
    checks.update(_e2e())
    checks.update(_count_tests())
    for k, v in checks.items():
        print(("PASS " if v else "FAIL ") + k)
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "selftest":
        sys.exit(selftest())
    if mode == "backtest":
        backtest(*sys.argv[2:13])
    elif mode == "count":
        count(*sys.argv[2:12])
    elif mode == "confirmation-complete":            # 6b completeness for the confirmation window, metadata only
        a = pd.Timestamp(sys.argv[2]).date()
        check_as_of(a)
        with census_window(confirmation_dates(a), "triton-r-confirmation-count"):
            C.run_build_complete(*sys.argv[3:5])
    elif mode == "confirmation-crosscheck":          # reads only ticker and session_date
        a = pd.Timestamp(sys.argv[2]).date()
        check_as_of(a)
        with census_window(confirmation_dates(a), "triton-r-confirmation-count"):
            sys.exit(C.run_crosscheck(*sys.argv[3:6]))
    else:
        raise SystemExit("modes: backtest, count, confirmation-complete, confirmation-crosscheck, selftest")
