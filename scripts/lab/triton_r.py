"""TRITON-R v1 instrument -- the BACKTEST block (R-IV.1080(h)2-3). QUERY runs it read-only; LAB never sees a row.

Claim of record: TRITON-R-v1-STAMPED-R-IV.1080.md (ba9e77df...), = REV 1 (44b98cab...) + R-IV.1080(b)-(g);
amended by TRITON-R-v1-AMENDMENT-1-R-IV.1084.md (d8030b4f...): continuous EMA; small-sample kill floors;
and TRITON-R-v1-AMENDMENT-2-R-IV.1090.md (21a2c0e9...): controls from t_r + 1 min; WIN 1 bootstrap 10,000;
WIN 4 >= 5 claim events per side (named if not met); SUSPECT if > 10% of resamples skipped;
and TRITON-R-v1-AMENDMENT-3-R-IV.1093.md (c491c196...): a SUSPECT interval carries no verdict weight;
amendment 4 (6d26a90e..., PYTHIA data note); amendment 5 (8f5931a9..., secondaries, confirmation set only:
secs. 2-3 coded as horizon_z / evaluate(horizons=True) / placebos(horizons=True) / summarize_secondaries, which
the backtest and the count job never call; sec. 4, the money gate, NOT CODED pending a ruling, R-IV.1238(b)3);
amendment 6 (b8a5ff38...): the slot median counts the 10 most recent prior sessions in which the slot EXISTS.
LOAD (R-IV.1116(b)2a): run 2's frozen path itself -- _read_parquet -> census_set -> prepare_prints (dedup first).
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
         <macro_csv> <tide_csv> <iv_csv> <out_dir> <state_dir>   (COUNT-ONLY, confirmation set 09-25 .. as_of;
         state_dir keeps the frozen stop trigger across weekly runs; refuses until amendment 5 is stamped)
  python scripts/lab/triton_r.py read <as_of> <prints_glob> <complete_csv> <bars_glob> "<polygon_glob>;<polygon_glob2>"
         <va_csv> <macro_csv> <tide_csv> <iv_csv> <fx_csv> <counts_csv> <out_dir> <state_dir>
         (the CONFIRMATION-SET READ, ONCE, in the 11-20 decision run, R-IV.1241(d): counts_csv = the count job's
         output for the SAME as_of, which a count-only first pass must reproduce before any outcome)
  python scripts/lab/triton_r.py confirmation-complete <as_of> <walk_pages_csv> <complete_csv_out>
  python scripts/lab/triton_r.py confirmation-crosscheck <as_of> <prints_glob> <complete_csv> <crosscheck_csv_out>
  python scripts/lab/triton_r.py selftest
"""
import glob
import shutil
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
#: NYSE early closes in the TRITON-R span (13:00 ET). Stamped sec. 6: S_close is the 13:00 close on half-days,
#: and tau runs to the actual close; QUERY R-IV.1094 sec. 8 ask 4: half sessions are counted and MARKED.
HALF_DAYS = {date(2026, 11, 27), date(2026, 12, 24)}


def session_close(d):
    """Regular-session close of `d` in seconds after midnight ET (13:00 on a half-day, else 16:00)."""
    return 13 * 3600 if d in HALF_DAYS else RTH1


# ── amendment 5 (8f5931a9...): SECONDARY declarations, confirmation set only, no verdict weight ─────
#: sec. 2 -- Z - placebo at +30m, +60m and the next-session close; IM recomputed for each tau; same placebo.
A5_HORIZONS = (("30m", 1800), ("60m", 3600), ("next_close", None))
A5_STALE_S = 300            # LAB reading: the horizon price is the last 1-min close at or before T, within 5 min
#: sec. 3 -- the asset-group split; a group needs >= 30 sessions with claim events, else UNDERPOWERED.
A5_GROUPS = {"index_etfs": ("SPY", "QQQ", "IWM", "SMH"), "megacap_singles": ("NVDA", "AAPL", "MSFT", "TSLA")}
A5_GROUP_MIN_SESSIONS = 30
A5_LABEL = "SECONDARY (amendment 5): propose-only, NO verdict weight; computed on the confirmation set only"
A5_MONEY_GATE = ("amendment 5 sec. 4 NOT CODED: the modeled 0-3 DTE debit spread (strikes, width, entry slot, "
                 "fill and cost model, slot mapping of +30m / +60m) is not defined by the stamp; a ruling is needed")


def next_session(d):
    """The next NYSE session after d on the confirmation calendar (weekdays minus its holidays)."""
    x = pd.Timestamp(d) + pd.offsets.BDay(1)
    while x.date() in NYSE_HOLIDAYS_CONFIRM:
        x += pd.offsets.BDay(1)
    return x.date()


def horizon_z(ohlcv, tk, d, S0, t_conf, sigma, dsign):
    """Amendment 5 sec. 2: {horizon: z or None} and {horizon: reason} for one claim event.
    z = d (S_h - S0) / (S0 sigma sqrt(tau_h)), tau_h in years on 390 x 252 trading minutes."""
    z, why = {}, {}
    b1 = ohlcv.get((tk, d))
    for name, off in A5_HORIZONS:
        if off is not None:
            T = t_conf + off
            if T > session_close(d):
                z[name], why[name] = None, "beyond_session_close"
                continue
            if b1 is None:
                z[name], why[name] = None, "bars"
                continue
            done = b1[(b1.t_s + 60 <= T) & (b1.t_s + 60 >= T - A5_STALE_S)]
            if done.empty:
                z[name], why[name] = None, "horizon_bar"
                continue
            S, tau_min = float(done.close.iloc[-1]), off / 60.0
        else:
            nd = next_session(d)
            b2 = ohlcv.get((tk, nd))
            if b2 is None or b2.empty:
                z[name], why[name] = None, "next_session_bars"
                continue
            S = float(b2.close.iloc[-1])
            tau_min = (session_close(d) - t_conf) / 60.0 + (session_close(nd) - RTH0) / 60.0
        im = S0 * sigma * np.sqrt(tau_min / (390.0 * 252.0))
        z[name] = dsign * (S - S0) / im if im > 0 else None
        if z[name] is None:
            why[name] = "im"
    return z, why
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
AMENDMENT_3 = "TRITON-R-v1-AMENDMENT-3-R-IV.1093.md c491c196ed3bec75b21f91e31956a98b2c0bdad55f52decc74e57909410e483c"
AMENDMENT_4 = "TRITON-R-v1-AMENDMENT-4-R-IV.1111.md 6d26a90e7a2ae6c7cb20620ca5c15ee7dbae1b3a2a298f1a588f7c93bd630b53 (data note)"
AMENDMENT_5 = "TRITON-R-v1-AMENDMENT-5-R-IV.1114.md 8f5931a9af4e7c459f4cf77d6dc988703b782e5844783d5011b2914e33fb7b2d"
AMENDMENT_6 = "TRITON-R-v1-AMENDMENT-6-R-IV.1116.md b8a5ff389ffa796f6b2fc1e37ed37859892dae64c2a5ffc0d483fd3d71b5918d"
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


#: The counts and output hashes of record (R-IV.1112(b)): census run 2, `triton-a7\out\` (QUERY R-IV.1057).
RUN2_COUNTS = {"T1000": {"census_kept": 288, "census_d5": 258}, "NOGATE": {"census_kept": 362, "census_d5": 306}}
RUN2_HASHES = {
    "events_m4_d5": "5e496738a5033c03af78c8176d8c24a2683c0985dc8ef7ac2314325e3a8f5a1d",
    "d6_direction": "0fdbaa84d9d90a545c05d131fc1dd9bace19ac155acb536e25d559b3b9c8b03d",
    "per_ticker_session": "b4787e54183bb73693edbe58bd298952cc48bf02ae68f6361ba1258b25afb05d",
    "time_of_day": "43f8261bbadf3535bceaf7b1845cdc19f4401f2d96adf3017d61b1ad452d76ca",
    "weekday": "a261504df009d144cba663790d9fc14b82d7e3e00822f0c17d10c5890a8c2558",
    "macro_day": "a8b2a06c16b6415222fea60257e6d8248af1eec548bc323faef6825a53ec2539",
    "pythia_loc": "0515ca0388f5ad6740b066c3eece16a704e0e8b2b5f5186f8d0f3753f11b6a8f"}


def frame_hashes(frames):
    """sha256 of each census frame written exactly as `triton_census._write` writes it."""
    import hashlib
    import tempfile
    out = {}
    with tempfile.TemporaryDirectory() as td:
        for k, f in frames.items():
            p = os.path.join(td, f"{k}.csv")
            f.to_csv(p, index=False)
            out[k] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


def identity_guard(frames, cap, expected_counts=None, expected_hashes=None):
    """D1-D5 'exactly as frozen in census run 2' (stamped sec. 3): the captured FRUN counts must equal the
    NAMED counts of record and every census output must hash to run 2's. Returns the list of mismatches."""
    expected_counts = RUN2_COUNTS if expected_counts is None else expected_counts
    expected_hashes = RUN2_HASHES if expected_hashes is None else expected_hashes
    bad = []
    for w, exp in expected_counts.items():
        got = cap.get(w, {})
        for k, v in exp.items():
            if got.get(k) != v:
                bad.append(f"{w} {k}: got {got.get(k)}, record {v}")
    hs = frame_hashes(frames)
    for k, v in expected_hashes.items():
        if hs.get(k) != v:
            bad.append(f"{k}.csv sha256 {str(hs.get(k))[:16]}... != record {v[:16]}...")
    return bad


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


def slot_lookback_skips(prior_b5, slot, prior_dates):
    """R-IV.1122(b): the trading sessions (from `prior_dates`, the readable sessions before the event's)
    that the amendment 6 lookback stepped over for `slot` -- no bars at all, or bars without that slot --
    between the event and the oldest contributing session. [] when the 10 contributors are the 10 most recent
    sessions; None when there are fewer than 10 contributors (the median is MISSING anyway)."""
    by_date = {b.session.iloc[0]: b for b in prior_b5 if len(b)}
    used = []
    for d in reversed(sorted(prior_dates)):
        b = by_date.get(d)
        if b is not None and len(b.volume[b.slot == slot]):
            used.append(d)
            if len(used) == SLOT_LOOKBACK:
                break
    if len(used) < SLOT_LOOKBACK:
        return None
    oldest = used[-1]
    return [d for d in prior_dates if oldest < d and d not in used]


def classify_skips(skips):
    """'half_day' if any skipped session is an early close, 'data_gap' if any is a regular session."""
    return {"half_day": any(d in HALF_DAYS for d in skips), "data_gap": any(d not in HALF_DAYS for d in skips)}


def skip_counts(claim_results):
    """(claim events whose lookback skipped >= 1 session, of which half-day, of which data gap)."""
    a = h = g = 0
    for res in claim_results:
        if res["slot_skips"]:
            c_ = classify_skips(res["slot_skips"])
            a, h, g = a + 1, h + int(c_["half_day"]), g + int(c_["data_gap"])
    return a, h, g


def slot_median(prior_b5, slot):
    """Median volume of `slot` over the 10 most recent prior sessions in which that slot EXISTS (amendment 6,
    b8a5ff38...): a half-day (or any session lacking the slot) is skipped for it. Fewer than 10 -> None."""
    vols = []
    for b in reversed(prior_b5):
        v = b.volume[b.slot == slot]
        if len(v):
            vols.append(float(v.iloc[0]))
            if len(vols) == SLOT_LOOKBACK:
                return float(np.median(vols))
    return None


def d7(seq, sess_mask, prior_b5, t_event, L, side, prior_dates=None, skips=None):
    """('CONFIRMED', bar_index_in_seq) / ('UNCONFIRMED', None) / ('MISSING', what). If `skips` is a list, the
    sessions the slot-median lookback skipped on every scanned bar are added to it (R-IV.1122(b))."""
    idx = np.flatnonzero(sess_mask)
    for i in idx:
        tc = seq.t_close.iloc[i]
        if tc <= t_event:
            continue
        if tc > t_event + D7_WINDOW_S:
            break
        atr = atr_at(seq, i)
        med = slot_median(prior_b5, int(seq.slot.iloc[i]))
        if skips is not None and prior_dates is not None and med is not None:
            sk = slot_lookback_skips(prior_b5, int(seq.slot.iloc[i]), prior_dates)
            if sk:
                skips.extend(sk)
        if atr is None:
            return "MISSING", "atr14"
        if med is None:
            return "MISSING", "slot_median"
        c, v = float(seq.close.iloc[i]), float(seq.volume.iloc[i])
        beyond = c >= L + D7_ATR_MULT * atr if side == "BUYER" else c <= L - D7_ATR_MULT * atr
        if beyond and v >= med:
            if tc >= session_close(seq.session.iloc[i]):
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


def evaluate(ctx, tk, d, t, L, side, outcome=True, horizons=False):
    """All ingredients for one (tk, d, t, L, side). Returns dict: missing, fails, and if claim, Z inputs.
    outcome=False (the COUNT-ONLY job, R-IV.1080(b)): S_close, sigma and Z are never read or computed.
    horizons=True (amendment 5 sec. 2, the confirmation-set READ only): a claim also carries z_h / z_h_why.
    The default (False) is the backtest's path, unchanged."""
    res = {"missing": [], "fails": [], "z": None, "conf": None, "slot_skips": []}
    cal = calendar_ok(d, ctx.macro_excl)
    if cal != "OK":
        res["fails"].append(cal)
    res["missing"] += ctx.session_missing(tk, d)
    if "bars" in res["missing"]:
        return res
    seq = ctx.seq[tk]
    mask = (seq.session == d).to_numpy()
    skips = []
    st, info = d7(seq, mask, ctx.prior_b5(tk, d), t, L, side, prior_dates=[x for x in ctx.dates if x < d], skips=skips)
    res["slot_skips"] = sorted(set(skips))
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
        tau_y = ((session_close(d) - t_conf) / 60.0) / (390.0 * 252.0)   # to the ACTUAL close
        im = S0 * sigma * np.sqrt(tau_y)
        dsign = 1.0 if side == "BUYER" else -1.0
        res["z"] = dsign * (s_close - S0) / im if im > 0 else None
        if res["z"] is None:
            res["missing"].append("horizon")
        elif horizons:
            res["z_h"], res["z_h_why"] = horizon_z(ctx.ohlcv, tk, d, S0, t_conf, sigma, dsign)
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


def placebos(ctx, prints_by_ts, adv, tk, d_event, t_event, wstart, rng, bars_hl, eligible_sessions, outcome=True,
             horizons=False):
    """Valid placebo Zs for one claim event (up to PLACEBO_MAX, fixed rng). outcome=False (the COUNT job):
    only whether valid placebos EXIST -- each is a claim-passing candidate under evaluate(outcome=False);
    no Z is computed and S_close is never read.
    horizons=True (amendment 5 sec. 2, "the same placebo is used"): the SAME candidates and the SAME draw,
    each returned as {"z", "z_h"} instead of z. A candidate qualifies on its primary z alone, so the pick
    cannot depend on the flag."""
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
                ev = evaluate(ctx, tk, d, float(r.t_s), Lp, d6p, outcome=outcome, horizons=horizons)
                if outcome and ev["z"] is not None:
                    cands.append({"z": ev["z"], "z_h": ev.get("z_h", {})} if horizons else ev["z"])
                elif not outcome and not ev["missing"] and not ev["fails"]:
                    cands.append(1.0)                                  # existence only
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


def verdict_of(p):
    """BACKTEST verdict from the primary summary (R-IV.1080(d); amendments 1 and 3)."""
    if p["kills_fired"]:
        return "KILL"
    if p.get("kills_suppressed_suspect"):
        return "NO-KILL (SUSPECT)"
    if not (p["stat_kill_floor_met"] and p["freq_kill_floor_met"]):
        return "NO-KILL (INSUFFICIENT n)"
    return "NO-KILL"


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
    # amendment 3 (c491c196...): a SUSPECT interval carries no verdict weight in either direction
    s1, s2 = out["win1_suspect"], out["win2_suspect"]
    out["kill_L_not_respected"] = stat_floor and out["raw_kill_readings"]["L_not_respected"] and not s1
    out["kill_placebo_keeps_pace"] = stat_floor and out["raw_kill_readings"]["placebo_keeps_pace"] and not s2
    out["kill_one_week_carries_it"] = stat_floor and bool(raw_week)
    out["kills_suppressed_suspect"] = [k for k, raw_, sus in (
        ("kill_L_not_respected", out["raw_kill_readings"]["L_not_respected"], s1),
        ("kill_placebo_keeps_pace", out["raw_kill_readings"]["placebo_keeps_pace"], s2)) if stat_floor and raw_ and sus]
    out["kill_real_approx_shuffled"] = "inherited: satisfied by D4 as frozen (census stop (a) PASS for FRUN); not re-tested"
    out["kills_fired"] = [k for k in ("kill_under_1_per_week", "kill_L_not_respected", "kill_placebo_keeps_pace",
                                      "kill_one_week_carries_it") if out[k] is True]
    # WIN (reported; the backtest verdict is KILL / NO-KILL only). Amendment 3: a SUSPECT interval -> NOT MET.
    out["win1"] = bool(lo1 is not None and lo1 > 0) and not s1
    out["win2"] = bool(lo is not None and lo > 0) and not s2
    out["win_not_met_suspect"] = [w for w, sus in (("win1", s1), ("win2", s2)) if sus]
    out["win3"] = bool(out["win3_mean_without_best_week"] is not None and out["win3_mean_without_best_week"] > 0)
    out["win4"] = not out["win4_not_met_sides"]
    out["min_n_met"] = len(events) >= MIN_EVENTS and out["sessions"] >= MIN_SESSIONS
    return out


def _a5_diffs(events, horizon=None):
    """{session: [z_event - mean(z_placebo)]} for the primary (horizon=None) or one A5 horizon, and the
    count of events that could not be evaluated there (no event z, or no placebo with that horizon's z)."""
    g, n_un = {}, 0
    for e in events:
        if horizon is None:
            ze, zp = e["z"], [p["z"] if isinstance(p, dict) else p for p in e["zp"]]
        else:
            ze = (e.get("z_h") or {}).get(horizon)
            zp = [p["z_h"].get(horizon) for p in e["zp"] if isinstance(p, dict) and p.get("z_h")]
        zp = [x for x in zp if x is not None]
        if ze is None or not zp:
            n_un += 1
            continue
        g.setdefault(e["session"], []).append(ze - float(np.mean(zp)))
    return g, n_un


def _a5_block(events, horizon=None):
    g, n_un = _a5_diffs(events, horizon)
    p, lo, hi, nb = boot_ci(g, mean_stat)
    return {"events_evaluable": sum(len(v) for v in g.values()), "sessions_evaluable": len(g),
            "events_unevaluable": n_un, "diff": p, "lo": lo, "hi": hi, "boot_used": nb, **suspect("diff", p, nb)}


def summarize_secondaries(events):
    """Amendment 5 secs. 2-4 on CONFIRMATION-SET claim events. events: dicts {session, ticker, side, z,
    z_h, z_h_why, zp: [{"z", "z_h"}]} as evaluate(..., horizons=True) / placebos(..., horizons=True) build
    them. Refuses any event dated before 09-25: these are never computed on the backtest."""
    early = sorted({e["session"] for e in events if e["session"] < CONFIRM_FIRST})
    if early:
        raise SystemExit(f"AMENDMENT 5: secondaries are confirmation-set only; events dated {early[:3]} refuse")
    out = {"label": A5_LABEL, "amendment_5": AMENDMENT_5, "claim_events": len(events),
           "sessions_with_claim_events": len({e["session"] for e in events}), "horizons": {}, "groups": {},
           "money_gate": A5_MONEY_GATE}
    for name, _ in A5_HORIZONS:
        b = _a5_block(events, name)
        why = {}
        for e in events:
            r = (e.get("z_h_why") or {}).get(name)
            if r:
                why[r] = why.get(r, 0) + 1
        b["event_unevaluable_reasons"] = why
        out["horizons"][name] = b
    for gname, tickers in A5_GROUPS.items():
        ge = [e for e in events if e["ticker"] in tickers]
        sess = len({e["session"] for e in ge})
        blk = {"tickers": list(tickers), "claim_events": len(ge), "sessions_with_claim_events": sess,
               "events_with_placebo": sum(1 for e in ge if e["zp"])}
        if sess < A5_GROUP_MIN_SESSIONS:
            blk["status"] = f"UNDERPOWERED (< {A5_GROUP_MIN_SESSIONS} sessions with claim events); no result"
        else:
            blk["status"] = "COMPUTED"
            blk["primary"] = _a5_block(ge, None)
            blk["horizons"] = {name: _a5_block(ge, name) for name, _ in A5_HORIZONS}
        out["groups"][gname] = blk
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


def backtest_census(prints_glob, complete_csv, bars_glob, polygon_glob, adv_csv, va, macro_all, n_shuffles=None):
    """The census half of the backtest. R-IV.1116(b)2a: it calls RUN 2'S OWN frozen load + dedup path
    (`triton_census.run`, line for line: _read_parquet -> build_complete_set -> census_set -> prepare_prints,
    whose from_vendor dedups on tracking_id keep='first' over the WHOLE read, then d1_clean drops by executed
    date). Nothing is re-implemented and nothing is filtered before the frozen dedup. Walk files reaching
    past the block are opened; no row executed outside the block survives prepare_prints (asserted).
    Returns a dict; no outcome is computed here."""
    raw = C._read_parquet(prints_glob)                               # run 2: the whole read, as is
    build_set = C.build_complete_set(raw)
    S, excluded, refusals = C.census_set(pd.read_csv(complete_csv), build_set)
    if refusals:
        raise SystemExit(C.refusal_message(refusals))
    df, n_dup, dropped = C.prepare_prints(raw, S)                    # run 2's dedup, then the executed-date drop
    assert_block(set(df.session), "prints after the frozen load")    # the ceiling, on what survives the load
    praw, poly_info = C.load_polygon(polygon_glob)                    # run 2's bar path, line for line
    braw, source_map = C.choose_bars(C.load_bars(bars_glob), praw)
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
    return {"frames": frames, "E": E, "cap": cap, "S": S, "df": df, "n_dup": n_dup, "bars_hl": bars_hl,
            "ohlcv": ohlcv, "source_map": source_map, "poly_info": poly_info, "adv": adv}


def backtest(prints_glob, complete_csv, bars_glob, polygon_glob, adv_csv, va_csv, macro_csv, tide_csv,
             iv_csv, fx_csv, out_dir, n_shuffles=None, expected_counts=None, expected_hashes=None):
    if not C.TAU_FINAL:
        raise SystemExit("tau is not final")
    C.set_window("calibration")
    if C.CALIBRATION != BACKTEST:
        raise SystemExit("the census calibration window is not the backtest block; refusing")
    va, macro_all, macro_excl, tide, iv, fx = load_side_inputs(va_csv, macro_csv, tide_csv, iv_csv, fx_csv)
    bc = backtest_census(prints_glob, complete_csv, bars_glob, polygon_glob, adv_csv, va, macro_all, n_shuffles)
    frames, E, cap, S, df, n_dup = bc["frames"], bc["E"], bc["cap"], bc["S"], bc["df"], bc["n_dup"]
    bars_hl, ohlcv, source_map, poly_info, adv = bc["bars_hl"], bc["ohlcv"], bc["source_map"], bc["poly_info"], bc["adv"]
    guard = identity_guard(frames, cap, expected_counts, expected_hashes)   # R-IV.1112(b): the counts of record
    if guard:
        raise SystemExit("IDENTITY GUARD: D1-D5 are not census run 2's (stamped sec. 3): " + "; ".join(guard) +
                         ". Refusing.")
    dates = sorted({d for d in C.CALIBRATION_DATES if in_block(d)})
    ctx = Ctx(ohlcv, tide, iv, va, macro_excl, dates)
    prints_by_ts = {k: g for k, g in df.groupby(["ticker", "session"])}
    result = {"claim": CLAIM, "label": LABEL, "money_gate": MONEY_GATE, "block": [str(BACKTEST[0]), str(BACKTEST[1])],
              "ceiling": str(CEILING), "capture_check": cap, "census_set_ticker_sessions": len(S),
              "identity_guard": {"counts_of_record": expected_counts or RUN2_COUNTS,
                                 "hashes_of_record": "RUN2_HASHES (7 census outputs)" if expected_hashes is None
                                 else "self-test expected", "mismatches": []},
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
    result["amendment_3"] = AMENDMENT_3
    result["amendments_4_to_6"] = [AMENDMENT_4, AMENDMENT_5, AMENDMENT_6]
    result["verdict"] = verdict_of(p)
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
COUNT_COLUMNS = ["variant", "weight", "as_of", "window_first", "window_last", "window_sessions", "half_sessions",
                 "evaluable_ticker_sessions", "claim_events", "sessions_with_claim_events",
                 "events_with_placebo", "events_without_placebo", "stop_rule_met", "stop_rule_frozen_as_of",
                 "state_dir", "state_dir_status", "stop_trigger_sha256",
                 "claim_events_lookback_skipped", "lookback_skipped_half_day", "lookback_skipped_data_gap"]
UNEVAL_COLUMNS = ["variant", "session_date", "ingredient", "events_unevaluable"]     # R-IV.1120(b)2: a date axis
RUN_LOG = "runs.jsonl"                        # one line per count run in this state dir (R-IV.1120(b)1)
PLACEBO_WARN_SHARE = 0.20                     # R-IV.1120(b)3
TRIGGER_FILE = "stop_trigger.json"            # R-IV.1114(c): once true, frozen; the flag never reverts


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


def state_identity(state_dir):
    """R-IV.1120(b)1: the state directory on the face of every output. FRESH = no earlier count run is
    recorded there, so a run pointed at a new or wrong directory says so visibly."""
    import hashlib
    trig = os.path.join(state_dir, TRIGGER_FILE)
    runs = os.path.join(state_dir, RUN_LOG)
    n_runs = sum(1 for _ in open(runs, encoding="utf-8")) if os.path.exists(runs) else 0
    return {"path": os.path.abspath(state_dir),
            "status": (f"EXISTING ({n_runs} earlier count run(s) recorded)" if n_runs
                       else "FRESH: no earlier count run recorded in this state dir"),
            "earlier_runs": n_runs,
            "stop_trigger_sha256": hashlib.sha256(open(trig, "rb").read()).hexdigest() if os.path.exists(trig) else "none"}


def count(as_of, prints_glob, complete_csv, bars_glob, polygon_glob, va_csv, macro_csv, tide_csv, iv_csv, out_dir,
          state_dir, n_shuffles=None, today=None):
    """Per-variant counts for the confirmation set 09-25 .. as_of (R-IV.1084(d), R-IV.1114(c)): claim events,
    evaluable ticker-sessions, per-ingredient UNEVALUABLE counts, and events with / without a valid placebo
    (existence only). D1-D7, the sec. 5 filters and the calendar only; never S_close, Z, a move or a placebo
    outcome. History bars 09-01 .. 09-24 are read only for ATR / EMA / slot-median continuity.
    STOP TRIGGER: once a run reports stop_rule_met, its window is written to state_dir/stop_trigger.json and
    FROZEN as the read window; every later call reports the frozen trigger and reads NO data."""
    as_of = pd.Timestamp(as_of).date()
    check_as_of(as_of, today)
    trig_path = os.path.join(state_dir, TRIGGER_FILE)
    state = state_identity(state_dir)
    if os.path.exists(trig_path):
        trig = json.load(open(trig_path))
        os.makedirs(out_dir, exist_ok=True)
        json.dump({"stop_rule_met": True, "frozen": True, "trigger": trig, "state": state,
                   "note": "the stop rule fired earlier; the read window is frozen; no data was read by this call"},
                  open(os.path.join(out_dir, "trigger_frozen.json"), "w"), indent=1, default=str)
        print(f"STOP TRIGGER FROZEN at as_of {trig.get('as_of')}; no data read")
        return None
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
        raw = C._read_parquet(prints_glob)                    # the frozen path, as the backtest (R-IV.1116(b))
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
    prints_by_ts = {k: g for k, g in df.groupby(["ticker", "session"])}
    eligible = sorted({d for d in conf if calendar_ok(d, macro_excl) == "OK"})
    halves = [d for d in conf if d in HALF_DAYS]
    rows, unev = [], []
    for vname, wname in VARIANTS.items():
        ev = E[(E.window == wname) & (E.floor == FLOOR) & E.kept] if len(E) else E
        ev = ev[(ev.d5 == True) & ev.d6.isin(["BUYER", "SELLER"])] if len(ev) else ev  # noqa: E712
        wstart = C.WINDOWS[wname][0].hour * 3600 + C.WINDOWS[wname][0].minute * 60
        rng = np.random.default_rng(SEED_R)
        n, sess, with_p, miss = 0, set(), 0, {}
        claim_res = []
        for r in ev.itertuples():
            res = evaluate(ctx, r.ticker, r.session, r.t, r.L, r.d6, outcome=False)
            for m in res["missing"]:
                miss[(str(r.session), m)] = miss.get((str(r.session), m), 0) + 1
            if not res["missing"] and not res["fails"]:
                n += 1
                sess.add(r.session)
                claim_res.append(res)
                pl = placebos(ctx, prints_by_ts, {}, r.ticker, r.session, r.t, wstart, rng, bars_hl, eligible,
                              outcome=False)
                with_p += int(len(pl) > 0)
        sk_any, sk_half, sk_gap = skip_counts(claim_res)                # R-IV.1122(b): count only
        for (sd, m), k in sorted(miss.items()):
            unev.append({"variant": vname, "session_date": sd, "ingredient": m, "events_unevaluable": k})
        primary = vname == PRIMARY
        met = bool(primary and ((n >= MIN_EVENTS and len(sess) >= MIN_SESSIONS) or as_of >= CONFIRM_LAST))
        rows.append({"variant": vname, "weight": "PRIMARY" if primary else "SECONDARY", "as_of": str(as_of),
                     "window_first": str(conf[0]), "window_last": str(conf[-1]), "window_sessions": len(conf),
                     "half_sessions": len(halves), "evaluable_ticker_sessions": len(eval_ts), "claim_events": n,
                     "sessions_with_claim_events": len(sess), "events_with_placebo": with_p,
                     "events_without_placebo": n - with_p, "stop_rule_met": met if primary else "",
                     "stop_rule_frozen_as_of": str(as_of) if met else "", "state_dir": state["path"],
                     "state_dir_status": state["status"], "stop_trigger_sha256": state["stop_trigger_sha256"],
                     "claim_events_lookback_skipped": sk_any, "lookback_skipped_half_day": sk_half,
                     "lookback_skipped_data_gap": sk_gap})
    out = pd.DataFrame(rows, columns=COUNT_COLUMNS)
    U = pd.DataFrame(unev, columns=UNEVAL_COLUMNS)
    C.assert_aggregate({"counts": out, "unevaluable": U})
    os.makedirs(out_dir, exist_ok=True)
    out.to_csv(os.path.join(out_dir, "counts.csv"), index=False)
    U.to_csv(os.path.join(out_dir, "unevaluable.csv"), index=False)
    from datetime import datetime, timezone
    meta = {
        "claim": CLAIM,
        "amendments": [AMENDMENT_1, AMENDMENT_2, AMENDMENT_3, AMENDMENT_4, AMENDMENT_5, AMENDMENT_6],
        "computed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count_scope": ("claim events = FRUN runs kept by D4, D5-matched, D6-sided, D7-confirmed, passing every "
                        "sec. 5 filter, no ingredient missing; CORE8 x confirmation sessions 09-25 .. as_of"),
        "asset_class": "EQUITY (CORE8: SPY QQQ IWM SMH NVDA AAPL MSFT TSLA)",
        "grid_cell": "floor FRUN x window T1000 (TG-ON, PRIMARY) / NOGATE (TG-OFF, SECONDARY)",
        "measurement_system": ("TRITON-R v1 claim of record + the amendments listed; COUNTS ONLY "
                               "(no S_close, Z, move or placebo outcome)"),
        "distinct_dates": {"window_sessions": len(conf), "first": str(conf[0]), "last": str(conf[-1]),
                           "half_sessions_marked": [str(d) for d in halves]},
        "guards_applied": ["execution-date ceiling at the load (prints, bars, side files)",
                           "as_of must be a completed session within 09-25 .. 12-31",
                           "6b completeness: export lag / unlabelled refuse", "capture == in-run census",
                           "evaluate(outcome=False): S_close and sigma never read",
                           "no ADV (F-ADV outside the claim)", "stop trigger frozen once met (R-IV.1114(c))"],
        "not_monotone": ("weekly counts are NOT strictly cumulative: D4's shuffle stream is drawn in (ticker, session) "
                         "order over the window, so adding sessions can change which earlier runs are kept"),
        "d7_boundary": ("as_of is a completed session, so every D7 window (t, t+60 min] lies inside its own completed "
                        "session: a window reaching the close is scanned to the close; a confirmation at the close is "
                        "UNEVALUABLE (no horizon). No event is pending."),
        "half_sessions": ("early closes (13:00 ET: 2026-11-27, 2026-12-24) are counted in window_sessions and marked; "
                          "they hold fewer 5-min bars, so the slot median is MISSING for afternoon slots for the 10 "
                          "sessions after one; the EMA runs across them as across any session"),
        "placebo_columns": "existence of >= 1 valid placebo per claim event (evaluate(outcome=False)); no Z",
        "lookback_skip_columns": ("claim events whose D7 slot-median lookback (amendment 6) reached beyond the 10 "
                                  "consecutive prior sessions on any scanned bar, i.e. skipped >= 1 session; split by "
                                  "whether a skipped session was a half-day or a regular session (data gap). An event "
                                  "can be in both splits. Count only (R-IV.1122(b))."),
        "state": state,
        "placebo_warning": [
            {"variant": r["variant"], "claim_events": r["claim_events"], "events_with_placebo": r["events_with_placebo"],
             "warning": "kill 4 / WIN 2 may be undecidable."}
            for r in rows if r["events_with_placebo"] == 0 or r["events_with_placebo"] < PLACEBO_WARN_SHARE * r["claim_events"]]}
    json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w"), indent=1, default=str)
    os.makedirs(state_dir, exist_ok=True)
    with open(os.path.join(state_dir, RUN_LOG), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"as_of": str(as_of), "computed_at_utc": meta["computed_at_utc"]}) + "\n")
    prim = rows[[r["variant"] for r in rows].index(PRIMARY)]
    if prim["stop_rule_met"] is True:
        os.makedirs(state_dir, exist_ok=True)
        json.dump({"as_of": str(as_of), "window_first": str(conf[0]), "window_last": str(conf[-1]),
                   "claim_events": prim["claim_events"], "sessions_with_claim_events": prim["sessions_with_claim_events"],
                   "frozen_at_utc": meta["computed_at_utc"], "read_window_rule": "R-IV.1090(c)2 / R-IV.1114(c)"},
                  open(trig_path, "w"), indent=1)
    print(out.to_string(index=False))
    return out


# ── 9 · the CONFIRMATION-SET READ, run ONCE (R-IV.1080(b)/(d), R-IV.1241(d)) ─────────────────────────
READ_MARKER = "read_once.json"                # written before the first outcome; a second read refuses
HOLDOUT_LAST, FORWARD_FIRST = date(2026, 10, 15), date(2026, 10, 16)     # stamped sec. 2 (R-IV.1080(a))
MONEY_GATE_READ = ("money gate (WIN 5): NOT EVALUATED at this read -- deferred by R-IV.1241(d): the money test "
                   "follows only a passed census (salvage plan sec. 3). ESTABLISHED promotes nothing to money.")
READ_LABEL = "CONFIRMATION SET (holdout 09-25..10-15 + forward 10-16..), pooled, read once (R-IV.1080(b))"
COUNT_GUARD_COLUMNS = ("claim_events", "sessions_with_claim_events", "evaluable_ticker_sessions", "events_with_placebo")


def verdict_confirmation(p):
    """Stamped sec. 7 / R-IV.1080(d), on the PRIMARY summary: KILLED if any kill holds (kills carry
    amendment 1's floors and amendment 3's SUSPECT rule inside summarize); ESTABLISHED if WIN 1-4 hold at
    >= 30 events over >= 10 sessions; otherwise INSUFFICIENT. Returns (verdict, reasons)."""
    if p["kills_fired"]:
        return "KILLED", list(p["kills_fired"])
    wins = {w: bool(p[w]) for w in ("win1", "win2", "win3", "win4")}
    if p["min_n_met"] and all(wins.values()):
        return "ESTABLISHED", []
    why = []
    if not p["min_n_met"]:
        why.append(f"n: {p['claim_events']} claim events over {p['sessions']} sessions (needs >= {MIN_EVENTS} "
                   f"over >= {MIN_SESSIONS})")
    why += [f"{w} not met" for w, ok in wins.items() if not ok]
    why += [f"{k} suppressed (SUSPECT, amendment 3)" for k in p.get("kills_suppressed_suspect", [])]
    return "INSUFFICIENT", why


def _read_scoped(path, col, what, allowed):
    df = pd.read_csv(path)
    bad = sorted({str(x) for x in _dates(df[col]) if x not in allowed})
    if bad:
        raise SystemExit(f"DATE CEILING: {what} carries dates outside its scope: {bad[:5]}. Refusing.")
    return df


def _confirmation_inputs(as_of, prints_glob, complete_csv, bars_glob, polygon_glob, va_csv, macro_csv, tide_csv,
                         iv_csv, fx_csv, n_shuffles):
    """Exactly the count job's load (count() lines, unchanged there), plus the FX tag file scoped to <= as_of."""
    conf = confirmation_dates(as_of)
    hist = [d for d in C.CALIBRATION_DATES if in_block(d)]
    scope = set(conf) | set(hist)

    def in_scope(d):
        return d in scope
    va = _read_scoped(va_csv, "session", "va_csv", set(conf))
    va = {(r.ticker, pd.Timestamp(r.session).date()): (r.vah, r.val) for r in va.itertuples()}
    mac = _read_scoped(macro_csv, "date", "macro_csv", set(confirmation_dates(CONFIRM_LAST)))
    macro_excl = {pd.Timestamp(r.date).date() for r in mac.itertuples() if str(r.event) in MACRO_EXCLUDE}
    td = _read_scoped(tide_csv, "session_date", "tide_csv", set(conf))
    t = pd.to_datetime(td.tick_at, utc=True).dt.tz_convert("America/New_York")
    td = td.assign(t_s=(t - t.dt.normalize()).dt.total_seconds(),
                   net=pd.to_numeric(td.net_call_premium) - pd.to_numeric(td.net_put_premium),
                   d=pd.to_datetime(td.session_date).dt.date)
    tide = {d: g.sort_values("t_s")[["t_s", "net"]].reset_index(drop=True) for d, g in td.groupby("d")}
    ivd = _read_scoped(iv_csv, "session_date", "iv_csv", scope)
    iv = {(r.ticker, pd.Timestamp(r.session_date).date()): float(r.iv_near) if pd.notna(r.iv_near) else np.nan
          for r in ivd.itertuples()}
    fx = pd.read_csv(fx_csv)
    fxd = _dates(fx.date)
    if any(d > as_of for d in fxd):
        raise SystemExit(f"DATE CEILING: fx_csv reaches {max(fxd)} (> as_of {as_of}). Refusing.")
    fx = fx[[not _sealed(d) for d in fxd]].reset_index(drop=True)
    praw, _ = load_polygon_multi(polygon_glob)
    praw = scope_bars(praw, in_scope)
    readme = scope_bars(C.load_bars(bars_glob), in_scope)
    with census_window(hist, "triton-r-history"):
        _, smap_h = C.choose_bars(readme, praw)
    with census_window(conf, "triton-r-confirmation-count"):
        raw = C._read_parquet(prints_glob)
        build_set = C.build_complete_set(raw)
        S, _, refusals = C.census_set(pd.read_csv(complete_csv), build_set)
        if refusals:
            raise SystemExit(C.refusal_message(refusals))
        df, n_dup, _ = C.prepare_prints(raw, S)
        if len(df) and not all(d in set(conf) for d in set(df.session)):
            raise SystemExit("DATE CEILING: prints outside the confirmation window; refusing")
        braw, smap_c = C.choose_bars(readme, praw)
        bars_hl = C.bars_by_session(braw)
        frames, E = run_census_captured(df, {}, bars_hl, va, set(), n_shuffles)
    cap = capture_matches_census(frames, E)
    if not all(v["match"] for v in cap.values()):
        raise SystemExit("captured events do not match the census counts; refusing")
    ohlcv = load_ohlcv(polygon_glob, bars_glob, pd.concat([smap_h, smap_c], ignore_index=True), in_scope)
    ctx = Ctx(ohlcv, tide, iv, va, macro_excl, sorted(scope))
    eval_ts = [(tk, d) for (tk, d) in sorted(S) if d in set(conf) and calendar_ok(d, macro_excl) == "OK"
               and not ctx.session_missing(tk, d)]
    return {"conf": conf, "ctx": ctx, "E": E, "cap": cap, "df": df, "n_dup": n_dup, "bars_hl": bars_hl,
            "eval_ts": eval_ts, "macro_excl": macro_excl, "fx": fx,
            "prints_by_ts": {k: g for k, g in df.groupby(["ticker", "session"])},
            "eligible": sorted({d for d in conf if calendar_ok(d, macro_excl) == "OK"})}


def _variant_events(E, wname):
    ev = E[(E.window == wname) & (E.floor == FLOOR) & E.kept] if len(E) else E
    n_kept = len(ev)
    ev = ev[ev.d5 == True] if len(ev) else ev  # noqa: E712
    n_d5 = len(ev)
    ev = ev[ev.d6.isin(["BUYER", "SELLER"])] if len(ev) else ev
    return ev, n_kept, n_d5


def read(as_of, prints_glob, complete_csv, bars_glob, polygon_glob, va_csv, macro_csv, tide_csv, iv_csv, fx_csv,
         counts_csv, out_dir, state_dir, n_shuffles=None, today=None):
    """The single read of the CONFIRMATION SET (09-25 .. as_of), R-IV.1241(d): it runs ONCE, in the 11-20
    decision run. Order:
      1. as_of is a completed confirmation session; if the stop trigger fired, as_of must be ITS as_of
         (the frozen read window); a read marker in state_dir refuses (read once).
      2. the count job's exact load; a COUNT-ONLY first pass (outcome=False) must reproduce QUERY's
         counts.csv for the same as_of on every guard column, both variants -- else refuse, no outcome.
      3. the read marker is written; only then are outcomes computed (the backtest's own loop, plus
         amendment 5's horizons with the same placebo draw).
    Verdict on TG-ON per R-IV.1080(d); holdout-only and forward-only figures and amendment 5 are
    secondaries with no verdict weight; the money gate is NOT EVALUATED (R-IV.1241(d))."""
    from datetime import datetime, timezone
    as_of = pd.Timestamp(as_of).date()
    check_as_of(as_of, today)
    marker = os.path.join(state_dir, READ_MARKER)
    if os.path.exists(marker):
        raise SystemExit(f"READ ONCE: a confirmation read already started ({json.load(open(marker))}). Refusing.")
    trig_path = os.path.join(state_dir, TRIGGER_FILE)
    trig = json.load(open(trig_path)) if os.path.exists(trig_path) else None
    if trig is not None and trig["as_of"] != str(as_of):
        raise SystemExit(f"FROZEN READ WINDOW: the stop trigger fixed as_of {trig['as_of']}; got {as_of}. Refusing.")
    if os.path.exists(out_dir) and os.listdir(out_dir):
        raise SystemExit("out_dir is not empty; refusing")
    cnt = pd.read_csv(counts_csv)
    if set(cnt.as_of.astype(str)) != {str(as_of)}:
        raise SystemExit(f"IDENTITY GUARD: counts.csv is for {sorted(set(cnt.as_of.astype(str)))}, not {as_of}. Refusing.")
    I = _confirmation_inputs(as_of, prints_glob, complete_csv, bars_glob, polygon_glob, va_csv, macro_csv, tide_csv,
                             iv_csv, fx_csv, n_shuffles)
    ctx, E, conf = I["ctx"], I["E"], I["conf"]
    # pass 1: COUNT ONLY, the count job's own arithmetic; must equal QUERY's counts of record
    mism = []
    for vname, wname in VARIANTS.items():
        ev, _, _ = _variant_events(E, wname)
        wstart = C.WINDOWS[wname][0].hour * 3600 + C.WINDOWS[wname][0].minute * 60
        rng = np.random.default_rng(SEED_R)
        n, sess, with_p = 0, set(), 0
        for r in ev.itertuples():
            res = evaluate(ctx, r.ticker, r.session, r.t, r.L, r.d6, outcome=False)
            if not res["missing"] and not res["fails"]:
                n += 1
                sess.add(r.session)
                pl = placebos(ctx, I["prints_by_ts"], {}, r.ticker, r.session, r.t, wstart, rng, I["bars_hl"],
                              I["eligible"], outcome=False)
                with_p += int(len(pl) > 0)
        mine = {"claim_events": n, "sessions_with_claim_events": len(sess),
                "evaluable_ticker_sessions": len(I["eval_ts"]), "events_with_placebo": with_p}
        rec = cnt[cnt.variant == vname]
        if len(rec) != 1:
            mism.append(f"{vname}: counts.csv has {len(rec)} rows")
            continue
        for k in COUNT_GUARD_COLUMNS:
            if int(rec[k].iloc[0]) != mine[k]:
                mism.append(f"{vname} {k}: read {mine[k]} vs counts of record {int(rec[k].iloc[0])}")
    if mism:
        raise SystemExit("IDENTITY GUARD: the read's count-only pass differs from counts.csv: " + "; ".join(mism) +
                         ". Refusing; no outcome was computed.")
    os.makedirs(state_dir, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    json.dump({"as_of": str(as_of), "started_at_utc": started, "counts_csv": os.path.abspath(counts_csv)},
              open(marker, "w"), indent=1)
    # pass 2: OUTCOMES -- the backtest's own loop on the confirmation set
    result = {"claim": CLAIM, "label": READ_LABEL, "money_gate": MONEY_GATE_READ, "as_of": str(as_of),
              "window": [str(conf[0]), str(conf[-1])], "window_sessions": len(conf),
              "frozen_trigger": trig, "capture_check": I["cap"], "duplicate_tracking_ids_dropped": I["n_dup"],
              "count_guard": "PASSED (count-only pass == counts.csv on " + ", ".join(COUNT_GUARD_COLUMNS) + ")",
              "amendments": [AMENDMENT_1, AMENDMENT_2, AMENDMENT_3, AMENDMENT_4, AMENDMENT_5, AMENDMENT_6],
              "pythia_label": C.PYTHIA_LABEL, "read_started_at_utc": started, "variants": {}}
    funnel_rows = []
    for vname, wname in VARIANTS.items():
        ev, n_kept, n_d5 = _variant_events(E, wname)
        n_side = len(ev)
        miss, fails, claims, sec = {}, {}, [], []
        rng = np.random.default_rng(SEED_R)
        wstart = C.WINDOWS[wname][0].hour * 3600 + C.WINDOWS[wname][0].minute * 60
        tags = {"m4": 0, "fx_DXY": {}, "fx_USDJPY": {}}
        for r in ev.itertuples():
            res = evaluate(ctx, r.ticker, r.session, r.t, r.L, r.d6, horizons=True)
            for m in res["missing"]:
                miss[m] = miss.get(m, 0) + 1
            for f in res["fails"]:
                fails[f] = fails.get(f, 0) + 1
            if res["z"] is None or res["missing"] or res["fails"]:
                continue
            S0, t_conf = res["conf"]
            b1 = ctx.ohlcv[(r.ticker, r.session)]
            tL, hL = touched_held(b1, t_conf, r.L, S0)
            D = abs(r.L - S0)
            elig = b1.t_s[(b1.t_s >= wstart) & (b1.t_s < b1.t_s.max())].to_numpy()
            ctrl = controls(b1, elig, D, rng)
            mirror = touched_held(b1, t_conf, 2 * S0 - r.L, S0)
            zpd = placebos(ctx, I["prints_by_ts"], {}, r.ticker, r.session, r.t, wstart, rng, I["bars_hl"],
                           I["eligible"], horizons=True)
            tags["m4"] += int(r.m4)
            for sym, key in (("DXY", "fx_DXY"), ("USDJPY", "fx_USDJPY")):
                stt = fx_state(I["fx"], sym, r.session)
                tags[key][stt] = tags[key].get(stt, 0) + 1
            claims.append({"session": r.session, "side": r.d6, "z": res["z"], "zp": [p["z"] for p in zpd],
                           "touched_L": tL, "held_L": hL, "ctrl": ctrl, "mirror": mirror})
            sec.append({"session": r.session, "ticker": r.ticker, "side": r.d6, "z": res["z"],
                        "z_h": res.get("z_h", {}), "z_h_why": res.get("z_h_why", {}), "zp": zpd})
        summ = summarize(claims, len(I["eval_ts"]))
        summ.update({"census_frun_kept": n_kept, "d5_matched": n_d5, "side_assigned": n_side,
                     "unevaluable_by_ingredient": miss, "fails_by_ingredient": fails, "tags": tags,
                     "weight": "PRIMARY" if vname == PRIMARY else "SECONDARY (no verdict weight)"})
        ev_ts = I["eval_ts"]
        for part, keep in (("holdout_only", lambda d: d <= HOLDOUT_LAST), ("forward_only", lambda d: d >= FORWARD_FIRST)):
            sub = [c for c in claims if keep(c["session"])]
            ps = summarize(sub, sum(1 for _, d in ev_ts if keep(d)))
            summ[part] = {"weight": "SECONDARY (stamped sec. 2): no verdict weight",
                          **{k: ps[k] for k in ("claim_events", "sessions", "evaluable_ticker_sessions", "win2_diff",
                                                "win2_lo", "win2_hi", "win1_diff", "win1_lo", "win1_hi",
                                                "rate_per_week")}}
        summ["amendment_5"] = summarize_secondaries(sec)
        result["variants"][vname] = summ
        for stage, k in (("census_frun_kept", n_kept), ("d5_matched", n_d5), ("side_assigned", n_side),
                         ("claim_events", len(claims))):
            funnel_rows.append({"variant": vname, "stage": stage, "count": k})
    v, why = verdict_confirmation(result["variants"][PRIMARY])
    result["verdict"], result["verdict_reasons"] = v, why
    result["verdict_note"] = ("CONFIRMATION SET at the single read (R-IV.1080(d)): ESTABLISHED / KILLED / "
                              "INSUFFICIENT on TG-ON. Every result carries the money-gate label.")
    result["computed_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    F = pd.DataFrame(funnel_rows)
    C.assert_aggregate({"funnel": F})
    os.makedirs(out_dir, exist_ok=True)
    F.to_csv(os.path.join(out_dir, "funnel.csv"), index=False)
    json.dump(result, open(os.path.join(out_dir, "read.json"), "w"), indent=1, default=str)
    json.dump({"as_of": str(as_of), "started_at_utc": started, "finished_at_utc": result["computed_at_utc"],
               "verdict": v, "counts_csv": os.path.abspath(counts_csv)}, open(marker, "w"), indent=1)
    print(json.dumps({"verdict": v, "reasons": why, "computed_at_utc": result["computed_at_utc"]}, indent=1))
    return result


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
        # R-IV.1112(b): the identity guard against NAMED counts and output hashes of record
        va_, mac_, _, _, _, _ = load_side_inputs(*args[5:10])
        bc = backtest_census(*args[:5], va_, mac_, n_shuffles=40)
        exp_c = {w: {"census_kept": v["census_kept"], "census_d5": v["census_d5"]} for w, v in bc["cap"].items()}
        exp_h = frame_hashes(bc["frames"])
        try:
            backtest(*args, os.path.join(td, "out_run2"), n_shuffles=40)
            checks["GUARD: run 2's real constants refuse a synthetic run (the guard is live)"] = False
        except SystemExit as e_:
            checks["GUARD: run 2's real constants refuse a synthetic run (the guard is live)"] = \
                "IDENTITY GUARD" in str(e_) and "record 288" in str(e_) and not os.path.exists(os.path.join(td, "out_run2"))
        res = backtest(*args, os.path.join(td, "out"), n_shuffles=40, expected_counts=exp_c, expected_hashes=exp_h)
        checks["GUARD: matching counts and hashes of record pass"] = res["identity_guard"]["mismatches"] == []
        pert = os.path.join(td, "dp_pert")
        shutil.copytree(os.path.join(td, "dp"), pert)
        fpath = os.path.join(pert, "NVDA", "202609.parquet")
        g = pd.read_parquet(fpath)
        i0 = int(np.flatnonzero((g.session_date == "2026-09-02").to_numpy())[100])
        g.loc[g.index[i0], "size"] = int(g["size"].iloc[i0]) + 1           # ONE row, one field
        g.to_parquet(fpath, index=False)
        a3 = list(args)
        a3[0] = os.path.join(pert, "*", "*.parquet")
        try:
            backtest(*a3, os.path.join(td, "out_pert"), n_shuffles=40, expected_counts=exp_c, expected_hashes=exp_h)
            checks["GUARD: a ONE-ROW perturbation of the prints refuses (R-IV.1096(c)4)"] = False
        except SystemExit as e_:
            checks["GUARD: a ONE-ROW perturbation of the prints refuses (R-IV.1096(c)4)"] = \
                "IDENTITY GUARD" in str(e_) and "sha256" in str(e_)
        out = os.path.join(td, "out")
        checks["E2E: backtest runs; capture equals the census in both windows"] = \
            all(v["match"] for v in res["capture_check"].values())
        checks["E2E: verdict is NO-KILL (INSUFFICIENT n) on a plumbing-sized run, read on TG-ON"] = \
            res["verdict"] == "NO-KILL (INSUFFICIENT n)" and res["amendment_1"].startswith("TRITON-R-v1-AMENDMENT-1") and \
            res["amendment_2"].startswith("TRITON-R-v1-AMENDMENT-2") and res["computed_at_utc"].startswith("20") and \
            res["amendment_3"].startswith("TRITON-R-v1-AMENDMENT-3") and \
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
        state = os.path.join(td, "state")
        out = count(*args, state, n_shuffles=30, today=today)
        f = pd.read_csv(os.path.join(td, "out", "counts.csv"))
        checks["COUNT e2e: output schema is EXACTLY the count columns, one row per variant"] = \
            list(f.columns) == COUNT_COLUMNS and list(f.variant) == ["TG-ON", "TG-OFF"] and len(out) == 2
        checks["COUNT e2e: window 09-25 .. 09-28 (2 sessions); primary stop rule not met; no trigger written"] = \
            f.window_sessions.iloc[0] == 2 and str(f.stop_rule_met.iloc[0]) in ("False", "false") and \
            not os.path.exists(os.path.join(state, TRIGGER_FILE))
        U = pd.read_csv(os.path.join(td, "out", "unevaluable.csv"))
        mj = json.load(open(os.path.join(td, "out", "meta.json")))
        checks["COUNT e2e (ask 1): per-ingredient UNEVALUABLE counts written, schema exact"] = \
            list(U.columns) == UNEVAL_COLUMNS and int(U.events_unevaluable.sum()) >= 0
        checks["R-IV.1120(b)2: unevaluable.csv has a session_date axis, inside the window"] = \
            "session_date" in U.columns and len(U) > 0 and all(str(x) in ("2026-09-25", "2026-09-28") for x in U.session_date)
        checks["R-IV.1120(b)1: a FRESH state dir says so on the face (counts.csv and meta.json)"] = \
            str(f.state_dir_status.iloc[0]).startswith("FRESH") and f.stop_trigger_sha256.iloc[0] == "none" and \
            mj["state"]["status"].startswith("FRESH") and mj["state"]["path"] == os.path.abspath(state)
        checks["R-IV.1120(b)3: placebo warning when events_with_placebo is 0 / < 20% of claim events"] = \
            all(w["warning"] == "kill 4 / WIN 2 may be undecidable." for w in mj["placebo_warning"]) and \
            len(mj["placebo_warning"]) == int(((f.events_with_placebo == 0) |
                                               (f.events_with_placebo < 0.2 * f.claim_events)).sum())
        checks["COUNT e2e: events with + without placebo = claim events"] = \
            bool(((f.events_with_placebo + f.events_without_placebo) == f.claim_events).all())
        checks["COUNT e2e (ask 5): meta.json carries the six-item label + the not-monotone and D7 notes"] = \
            all(k in mj for k in ("count_scope", "asset_class", "grid_cell", "measurement_system", "distinct_dates",
                                  "guards_applied", "not_monotone", "d7_boundary", "half_sessions"))
        t2 = pd.read_csv(os.path.join(td, "tide.csv"))
        t2.loc[0, "session_date"] = "2026-10-20"
        t2.to_csv(os.path.join(td, "tide_bad.csv"), index=False)
        a2 = list(args)
        a2[7] = os.path.join(td, "tide_bad.csv")
        try:
            count(*a2, state, n_shuffles=30, today=today)
            checks["COUNT e2e: a tide row after as_of refuses"] = False
        except SystemExit as e_:
            checks["COUNT e2e: a tide row after as_of refuses"] = "DATE CEILING" in str(e_)
        # ask 2: the stop rule FIRES (as_of 12-31) -> trigger written; every later call is frozen and reads no data
        conf_all = confirmation_dates(CONFIRM_LAST)
        pd.DataFrame([{"ticker": t, "session": e.isoformat(), "complete": (t, e) in bp}
                      for t in C.CORE8 for e in conf_all]).to_csv(os.path.join(td, "complete_all.csv"), index=False)
        a4 = list(args)
        a4[0], a4[2], a4[9] = "2026-12-31", os.path.join(td, "complete_all.csv"), os.path.join(td, "out_end")
        o4 = count(*a4, state, n_shuffles=30, today=date(2027, 1, 5))
        f4 = pd.read_csv(os.path.join(td, "out_end", "counts.csv"))
        checks["COUNT (ask 2): the stop rule fires at the 12-31 session and its trigger is written"] = \
            o4 is not None and str(f4.stop_rule_met.iloc[0]) in ("True", "true") and \
            os.path.exists(os.path.join(state, TRIGGER_FILE))
        checks["COUNT (ask 4): half sessions counted and marked (11-27, 12-24)"] = \
            int(f4.half_sessions.iloc[0]) == 2 and \
            json.load(open(os.path.join(td, "out_end", "meta.json")))["distinct_dates"]["half_sessions_marked"] == \
            ["2026-11-27", "2026-12-24"]
        bogus = ["2026-10-02"] + [os.path.join(td, "nowhere", "x")] * 8 + [os.path.join(td, "out_frozen")]
        o5 = count(*bogus, state, n_shuffles=30, today=today)
        checks["COUNT (ask 2): once the trigger exists, the flag never reverts and NO data is read"] = \
            o5 is None and json.load(open(os.path.join(td, "out_frozen", "trigger_frozen.json")))["trigger"]["as_of"] \
            == "2026-12-31"
        checks["R-IV.1120(b)1: a later run in the same state dir reads EXISTING; the frozen output names the trigger hash"] = \
            str(f4.state_dir_status.iloc[0]).startswith("EXISTING") and \
            json.load(open(os.path.join(td, "out_frozen", "trigger_frozen.json")))["state"]["stop_trigger_sha256"] != "none"
    # half-day closes (stamped sec. 6: S_close and tau at 13:00 ET on a half-day)
    checks["HALF-DAY: session close is 13:00 on 11-27 and 12-24, 16:00 otherwise"] = \
        session_close(date(2026, 11, 27)) == 13 * 3600 and session_close(date(2026, 12, 24)) == 13 * 3600 \
        and session_close(date(2026, 11, 25)) == RTH1
    return checks


def _a5_tests():
    """Amendment 5 secs. 2-3 on synthetic bars; the backtest path is proven unchanged."""
    import inspect
    checks = {}
    tk, d, nd = "SPY", date(2026, 10, 6), date(2026, 10, 7)

    def b1_for(day, base):
        k = np.arange(int((session_close(day) - RTH0) // 60))
        return pd.DataFrame({"t_s": RTH0 + 60.0 * k, "open": base + 0.01 * k, "high": base + 0.01 * k + 0.02,
                             "low": base + 0.01 * k - 0.02, "close": base + 0.01 * k, "volume": 1000.0})
    oh = {(tk, d): b1_for(d, 100.0), (tk, nd): b1_for(nd, 102.0)}
    S0, t_conf, sig = 100.5, float(RTH0 + 3600), 0.2
    z, why = horizon_z(oh, tk, d, S0, t_conf, sig, 1.0)
    exp30 = (100.0 + 0.01 * 89 - S0) / (S0 * sig * np.sqrt(30 / (390 * 252)))
    checks["A5: +30m z = d(S_h - S0)/(S0 sigma sqrt(30 min)), S_h = the 1-min close AT t+30m"] = abs(z["30m"] - exp30) < 1e-9
    exp60 = (100.0 + 0.01 * 119 - S0) / (S0 * sig * np.sqrt(60 / (390 * 252)))
    checks["A5: +60m z, IM recomputed for its own tau"] = abs(z["60m"] - exp60) < 1e-9
    tau_n = (RTH1 - t_conf) / 60 + 390
    expn = (float(oh[(tk, nd)].close.iloc[-1]) - S0) / (S0 * sig * np.sqrt(tau_n / (390 * 252)))
    checks["A5: next-session close z, tau = rest of today + the whole next session"] = abs(z["next_close"] - expn) < 1e-9
    zs, _ = horizon_z(oh, tk, d, S0, t_conf, sig, -1.0)
    checks["A5: SELLER side flips the sign"] = abs(zs["30m"] + z["30m"]) < 1e-12
    zl, wl = horizon_z(oh, tk, d, S0, float(RTH1 - 600), sig, 1.0)
    checks["A5: +30m past the close -> None, reason beyond_session_close (never truncated)"] = \
        zl["30m"] is None and wl["30m"] == "beyond_session_close" and zl["next_close"] is not None
    hd, hn = date(2026, 11, 27), date(2026, 11, 30)
    oh2 = {(tk, hd): b1_for(hd, 100.0), (tk, hn): b1_for(hn, 100.0)}
    zh, wh = horizon_z(oh2, tk, hd, 100.0, float(12 * 3600 + 45 * 60), sig, 1.0)
    tau_h = 15 + 390
    exph = (float(oh2[(tk, hn)].close.iloc[-1]) - 100.0) / (100.0 * sig * np.sqrt(tau_h / (390 * 252)))
    checks["A5: half-day 11-27 -- +30m past its 13:00 close; next close tau = 15 + 390 min"] = \
        wh["30m"] == "beyond_session_close" and abs(zh["next_close"] - exph) < 1e-9
    checks["A5: next_session skips Thanksgiving and the weekend"] = \
        next_session(date(2026, 11, 25)) == date(2026, 11, 27) and next_session(date(2026, 10, 9)) == date(2026, 10, 12)
    zm, wm = horizon_z({(tk, d): oh[(tk, d)]}, tk, d, S0, t_conf, sig, 1.0)
    checks["A5: next session without bars -> None, reason next_session_bars"] = \
        zm["next_close"] is None and wm["next_close"] == "next_session_bars"
    gap = oh[(tk, d)][(oh[(tk, d)].t_s < t_conf + 1200) | (oh[(tk, d)].t_s > t_conf + 1800)]
    zg, wg = horizon_z({(tk, d): gap, (tk, nd): oh[(tk, nd)]}, tk, d, S0, t_conf, sig, 1.0)
    checks["A5: no 1-min close within 5 min of the horizon -> None, reason horizon_bar (no stale price)"] = \
        zg["30m"] is None and wg["30m"] == "horizon_bar"

    # evaluate(): horizons=False is the backtest path, byte-for-byte; horizons=True only ADDS z_h
    class FakeCtx:
        def __init__(self):
            self.ohlcv, self.tide, self.va, self.macro_excl = oh, {d: object()}, {(tk, d): (101.0, 99.0)}, set()
            self.iv = {(tk, date(2026, 10, 5)): sig}
            self.seq = {tk: bars5(oh[(tk, d)]).assign(session=d)}
            self.dates = [date(2026, 10, 5), d, nd]

        def session_missing(self, tk_, d_):
            return []
        def prior_b5(self, tk_, d_):
            return []
        def prior_session(self, d_):
            return date(2026, 10, 5)
    g = globals()
    saved = {k: g[k] for k in ("calendar_ok", "d7", "ema_at", "tide_slope", "pythia_pass")}
    i_conf = int(np.flatnonzero((FakeCtx().seq[tk].t_close == t_conf).to_numpy())[0])
    try:
        g["calendar_ok"] = lambda d_, m_: "OK"
        g["d7"] = lambda *a, **k: ("CONFIRMED", i_conf)
        g["ema_at"] = lambda c_, j_: 0.0
        g["tide_slope"] = lambda t_, s_: 1.0
        g["pythia_pass"] = lambda L_, va_, s_: "PASS"
        r0 = evaluate(FakeCtx(), tk, d, t_conf - 600, 100.0, "BUYER")
        r1 = evaluate(FakeCtx(), tk, d, t_conf - 600, 100.0, "BUYER", horizons=True)
    finally:
        g.update(saved)
    same = {k: v for k, v in r1.items() if k not in ("z_h", "z_h_why")} == r0
    checks["A5: evaluate(horizons=True) == the default on every existing key (z, missing, fails, conf)"] = \
        same and r0["z"] is not None and "z_h" not in r0 and set(r1["z_h"]) == {"30m", "60m", "next_close"}

    # placebos(): the SAME draw with and without horizons
    saved_c = (C.lit, C.tau)
    saved_e = g["evaluate"]
    try:
        C.lit = lambda hl, t_s, Lp, tau: (True, "BUYER")
        C.tau = lambda Lp: 0.01
        g["evaluate"] = lambda ctx, tk_, d_, t_, L_, s_, outcome=True, horizons=False: dict(
            {"z": d_.day + t_ / 1e5 + L_ / 1e9, "missing": [], "fails": []},
            **({"z_h": {"30m": 1.0, "60m": 2.0, "next_close": 3.0}} if horizons else {}))
        fc = FakeCtx()
        fc.ohlcv = {(tk, x): b1_for(x, 100.0) for x in (date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8))}
        args = (fc, {}, {}, tk, date(2026, 10, 6), t_conf, RTH0, None, {}, sorted(x for _, x in fc.ohlcv))
        p0 = placebos(*args[:7], np.random.default_rng(5), *args[8:])
        p1 = placebos(*args[:7], np.random.default_rng(5), *args[8:], horizons=True)
    finally:
        C.lit, C.tau = saved_c
        g["evaluate"] = saved_e
    checks["A5: placebos(horizons=True) draws the SAME placebos ('the same placebo is used')"] = \
        len(p0) == PLACEBO_MAX and [x["z"] for x in p1] == p0 and all("z_h" in x for x in p1)

    # summarize_secondaries
    def ev(s, t, z, zp, zh=None, zph=None):
        return {"session": s, "ticker": t, "side": "BUYER", "z": z, "z_h": zh or {}, "z_h_why": {},
                "zp": [{"z": q, "z_h": zph or {}} for q in zp]}
    try:
        summarize_secondaries([ev(date(2026, 9, 24), "SPY", 1.0, [0.0])])
        checks["A5: a backtest-dated event refuses (confirmation set only)"] = False
    except SystemExit as e_:
        checks["A5: a backtest-dated event refuses (confirmation set only)"] = "confirmation-set only" in str(e_)
    days = confirmation_dates(date(2026, 12, 31))
    few = [ev(days[i], "NVDA", 1.0, [0.0], {"30m": 1.0}, {"30m": 0.5}) for i in range(5)]
    s5 = summarize_secondaries(few)
    checks["A5: a group under 30 sessions reports UNDERPOWERED with its counts, never a result"] = \
        s5["groups"]["megacap_singles"]["status"].startswith("UNDERPOWERED") and \
        "primary" not in s5["groups"]["megacap_singles"] and s5["groups"]["megacap_singles"]["claim_events"] == 5
    many = [ev(days[i], "SPY", 1.0 + 0.01 * i, [0.0], {"30m": 1.0, "60m": None}, {"30m": 0.25, "60m": 0.1})
            for i in range(31)]
    s31 = summarize_secondaries(many + few)
    gi = s31["groups"]["index_etfs"]
    checks["A5: a group with >= 30 sessions is COMPUTED on the primary and each horizon"] = \
        gi["status"] == "COMPUTED" and gi["primary"]["events_evaluable"] == 31 and \
        abs(gi["horizons"]["30m"]["diff"] - 0.75) < 1e-12
    checks["A5: a horizon with no event z counts every event as unevaluable"] = \
        s31["horizons"]["60m"]["events_unevaluable"] == 36 and s31["horizons"]["60m"]["diff"] is None
    checks["A5: the label, the amendment hash and the money-gate status are carried"] = \
        s31["label"].startswith("SECONDARY (amendment 5)") and "8f5931a9" in s31["amendment_5"] and \
        s31["money_gate"].startswith("amendment 5 sec. 4 NOT CODED")
    src = inspect.getsource(backtest) + inspect.getsource(backtest_census) + inspect.getsource(count)
    checks["A5: backtest / count never call the secondaries (no horizons=True, no summarize_secondaries)"] = \
        "horizons=True" not in src and "summarize_secondaries" not in src and "horizon_z" not in src
    return checks


def _read_tests():
    """The confirmation-set READ (R-IV.1241(d)), synthetic only: guards, read-once, verdict rules."""
    import tempfile
    checks = {}
    base = {"kills_fired": [], "min_n_met": True, "win1": True, "win2": True, "win3": True, "win4": True,
            "claim_events": 31, "sessions": 10, "kills_suppressed_suspect": []}
    checks["READ verdict: WIN 1-4 at >= 30 / >= 10 -> ESTABLISHED"] = verdict_confirmation(base)[0] == "ESTABLISHED"
    checks["READ verdict: any kill -> KILLED (and it is named)"] = \
        verdict_confirmation(dict(base, kills_fired=["kill_placebo_keeps_pace"])) == ("KILLED", ["kill_placebo_keeps_pace"])
    v, why = verdict_confirmation(dict(base, min_n_met=False, claim_events=9, sessions=4))
    checks["READ verdict: below 30 / 10 -> INSUFFICIENT, with the n stated"] = v == "INSUFFICIENT" and "9 claim events" in why[0]
    v, why = verdict_confirmation(dict(base, win3=False))
    checks["READ verdict: a WIN not met, no kill -> INSUFFICIENT, naming the WIN"] = v == "INSUFFICIENT" and why == ["win3 not met"]
    v, why = verdict_confirmation(dict(base, win2=False, kills_suppressed_suspect=["kill_placebo_keeps_pace"]))
    checks["READ verdict: a SUSPECT-suppressed kill is not a KILL (amendment 3) and is named"] = \
        v == "INSUFFICIENT" and any("SUSPECT" in w for w in why)
    rng = np.random.default_rng(5)
    raw, braw, sessions = C._synthetic_vendor(rng)
    today = date(2026, 10, 15)
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
        fxd = pd.bdate_range("2026-05-01", "2026-09-28")
        pd.DataFrame([{"date": d.date().isoformat(), "symbol": s, "close": 100 + 0.01 * i}
                      for s in ("DXY", "USDJPY") for i, d in enumerate(fxd)]).to_csv(os.path.join(td, "fx.csv"), index=False)
        common = [os.path.join(td, "dp", "*", "*.parquet"), os.path.join(td, "complete.csv"),
                  os.path.join(td, "bars1m", "*", "*.parquet"),
                  os.path.join(td, "poly_hist", "*.parquet") + ";" + os.path.join(td, "poly_conf", "*.parquet"),
                  os.path.join(td, "va.csv"), os.path.join(td, "macro.csv"), os.path.join(td, "tide.csv"),
                  os.path.join(td, "iv.csv")]
        state = os.path.join(td, "state")
        count("2026-09-28", *common, os.path.join(td, "cnt"), state, n_shuffles=30, today=today)
        cnt = os.path.join(td, "cnt", "counts.csv")
        fx = os.path.join(td, "fx.csv")
        # the guard refuses BEFORE any outcome: a counts file that differs by one
        bad = pd.read_csv(cnt)
        bad.loc[0, "evaluable_ticker_sessions"] += 1
        badp = os.path.join(td, "counts_bad.csv")
        bad.to_csv(badp, index=False)
        try:
            read("2026-09-28", *common, fx, badp, os.path.join(td, "r_bad"), state, n_shuffles=30, today=today)
            checks["READ: counts differing by one refuse; no marker, no output"] = False
        except SystemExit as e_:
            checks["READ: counts differing by one refuse; no marker, no output"] = \
                "IDENTITY GUARD" in str(e_) and not os.path.exists(os.path.join(state, READ_MARKER)) and \
                not os.path.exists(os.path.join(td, "r_bad"))
        try:
            read("2026-09-25", *common, fx, cnt, os.path.join(td, "r_asof"), state, n_shuffles=30, today=today)
            checks["READ: counts.csv for another as_of refuses"] = False
        except SystemExit as e_:
            checks["READ: counts.csv for another as_of refuses"] = "IDENTITY GUARD" in str(e_)
        fx2 = pd.read_csv(fx)
        fx2.loc[len(fx2)] = {"date": "2026-10-01", "symbol": "DXY", "close": 101.0}
        fx2.to_csv(os.path.join(td, "fx_bad.csv"), index=False)
        try:
            read("2026-09-28", *common, os.path.join(td, "fx_bad.csv"), cnt, os.path.join(td, "r_fx"), state,
                 n_shuffles=30, today=today)
            checks["READ: an FX row after as_of refuses (date ceiling)"] = False
        except SystemExit as e_:
            checks["READ: an FX row after as_of refuses (date ceiling)"] = "DATE CEILING" in str(e_)
        res = read("2026-09-28", *common, fx, cnt, os.path.join(td, "r"), state, n_shuffles=30, today=today)
        mk = json.load(open(os.path.join(state, READ_MARKER)))
        checks["READ e2e: completes; the count guard passed; marker written with start and finish"] = \
            res["count_guard"].startswith("PASSED") and mk["as_of"] == "2026-09-28" and "finished_at_utc" in mk
        checks["READ e2e: a plumbing-sized set reads INSUFFICIENT on TG-ON, the n stated"] = \
            res["verdict"] == "INSUFFICIENT" and res["verdict_reasons"][0].startswith("n:")
        p = res["variants"][PRIMARY]
        checks["READ e2e: holdout-only, forward-only and amendment 5 blocks carried, no verdict weight"] = \
            p["holdout_only"]["weight"].startswith("SECONDARY") and p["forward_only"]["weight"].startswith("SECONDARY") \
            and p["amendment_5"]["label"].startswith("SECONDARY (amendment 5)")
        checks["READ e2e: the money gate is NOT EVALUATED (R-IV.1241(d)) and the label is carried"] = \
            res["money_gate"].startswith("money gate (WIN 5): NOT EVALUATED") and res["label"].startswith("CONFIRMATION SET")
        F = pd.read_csv(os.path.join(td, "r", "funnel.csv"))
        checks["READ e2e: outputs are aggregates only (funnel = variant, stage, count)"] = \
            set(F.columns) == {"variant", "stage", "count"} and os.path.exists(os.path.join(td, "r", "read.json"))
        try:
            read("2026-09-28", *common, fx, cnt, os.path.join(td, "r2"), state, n_shuffles=30, today=today)
            checks["READ: a second read refuses (READ ONCE)"] = False
        except SystemExit as e_:
            checks["READ: a second read refuses (READ ONCE)"] = "READ ONCE" in str(e_)
        # the OUTCOME loop with claims in it: evaluate stubbed to pass every side-assigned event (synthetic z)
        g = globals()
        saved_e = g["evaluate"]

        def fake_eval(ctx_, tk_, d_, t_, L_, s_, outcome=True, horizons=False):
            b = ctx_.ohlcv.get((tk_, d_))
            if b is None:
                return {"missing": ["bars"], "fails": [], "z": None, "conf": None, "slot_skips": []}
            j = int(np.searchsorted(b.t_s.to_numpy(), t_))
            j = min(j, len(b) - 2)
            out_ = {"missing": [], "fails": [], "z": None, "conf": (float(b.close.iloc[j]), float(b.t_s.iloc[j] + 60)),
                    "slot_skips": []}
            if outcome:
                out_["z"] = 0.1 + (t_ % 7) / 10.0
                if horizons:
                    out_["z_h"], out_["z_h_why"] = {"30m": 0.2, "60m": None, "next_close": 0.3}, {"60m": "beyond_session_close"}
            return out_
        st3 = os.path.join(td, "state3")
        try:
            g["evaluate"] = fake_eval
            count("2026-09-28", *common, os.path.join(td, "cnt3"), st3, n_shuffles=30, today=today)
            c3 = pd.read_csv(os.path.join(td, "cnt3", "counts.csv"))
            r3 = read("2026-09-28", *common, fx, os.path.join(td, "cnt3", "counts.csv"), os.path.join(td, "r_claims"),
                      st3, n_shuffles=30, today=today)
        finally:
            g["evaluate"] = saved_e
        pc = r3["variants"][PRIMARY]
        n_c = int(c3[c3.variant == PRIMARY].claim_events.iloc[0])
        checks["READ e2e WITH CLAIMS: the guard passes and the outcome loop runs on every claim"] = \
            n_c > 0 and pc["claim_events"] == n_c and pc["amendment_5"]["claim_events"] == n_c
        checks["READ e2e WITH CLAIMS: WIN 1 controls, placebos and A5 horizons are all computed"] = \
            pc["win1_ctrl_touched"] >= 0 and pc["events_with_placebo"] + pc["events_without_placebo"] == n_c and \
            pc["amendment_5"]["horizons"]["60m"]["event_unevaluable_reasons"].get("beyond_session_close") == n_c
        checks["READ e2e WITH CLAIMS: holdout-only + forward-only events add up to the pooled set"] = \
            pc["holdout_only"]["claim_events"] + pc["forward_only"]["claim_events"] == n_c
        st2 = os.path.join(td, "state2")
        os.makedirs(st2)
        json.dump({"as_of": "2026-12-31"}, open(os.path.join(st2, TRIGGER_FILE), "w"))
        try:
            read("2026-09-28", *common, fx, cnt, os.path.join(td, "r3"), st2, n_shuffles=30, today=today)
            checks["READ: with a frozen stop trigger, any other as_of refuses"] = False
        except SystemExit as e_:
            checks["READ: with a frozen stop trigger, any other as_of refuses"] = "FROZEN READ WINDOW" in str(e_)
    import inspect
    src = inspect.getsource(count)
    checks["READ: the count job is untouched by the read (it never calls read / the A5 code)"] = \
        "read(" not in src.replace("pd.read_csv(", "").replace("_read_parquet(", "").replace("read_scoped(", "") \
        and "horizons=True" not in src
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
    # R-IV.1116(b)2a: the load is run 2's FROZEN path (prepare_prints: dedup keep='first' over the whole read,
    # then the executed-date drop). Nothing is filtered before the dedup.
    rng0 = np.random.default_rng(3)
    raw0, _, sess0 = C._synthetic_vendor(rng0)
    comp0 = {(tk, s.date()) for tk in C.CORE8 for s in sess0}
    df0, _, _ = C.prepare_prints(raw0, comp0)
    checks["CEILING (R-IV.1112(b)): no row executed on/after 09-25 (or sealed) survives the frozen load"] = \
        len(df0) > 0 and all(in_block(d) for d in set(df0.session)) and not any(d >= CEILING for d in set(df0.session))
    x = raw0[(raw0.session_date == "2026-09-02") & (raw0.ticker == "SPY")].iloc[[200]].copy()
    xd = x.copy()
    xd["executed_at"] = (pd.to_datetime(x.executed_at, utc=True) + pd.Timedelta(days=26)).dt.strftime(
        "%Y-%m-%dT%H:%M:%S.%f+00:00")                          # the SAME tracking_id, executed 09-28 in this copy
    xd["session_date"] = "2026-09-28"
    first_out = pd.concat([xd, raw0], ignore_index=True)       # the out-of-block copy comes FIRST
    last_out = pd.concat([raw0, xd], ignore_index=True)        # ... or LAST
    n_first = len(C.prepare_prints(first_out, comp0)[0])
    n_last = len(C.prepare_prints(last_out, comp0)[0])
    checks["FROZEN DEDUP (run 2's semantics): keep='first' -- an out-of-block FIRST copy drops the print"] = \
        n_first == len(df0) - 1
    checks["FROZEN DEDUP: an out-of-block LATER copy leaves the in-block print in place"] = n_last == len(df0)
    pre = first_out[[in_block(d) for d in pd.to_datetime(first_out.executed_at, utc=True,
                                                         format="ISO8601").dt.tz_convert("America/New_York").dt.date]]
    checks["WHY THE GUARD REFUSED: pre-filtering before the dedup KEEPS that print (differs from run 2)"] = \
        len(C.prepare_prints(pre, comp0)[0]) == len(df0)
    # amendment 6: the slot median counts sessions in which the slot EXISTS
    full = pd.DataFrame({"slot": np.arange(78), "volume": 100.0})
    half = pd.DataFrame({"slot": np.arange(42), "volume": 999.0})       # a 13:00 close: slots 0..41 only
    hist11 = [full] * 9 + [half, full]                                  # oldest .. newest; the half-day is 2nd newest
    checks["A6: an afternoon slot after a half-day uses the 10 most recent sessions that HAVE it"] = \
        slot_median(hist11, 60) == 100.0
    checks["A6: a morning slot still counts the half-day's volume (it has the slot)"] = \
        slot_median(hist11, 10) == float(np.median([100.0] * 9 + [999.0]))
    checks["A6: fewer than 10 sessions with the slot -> MISSING"] = slot_median([full] * 8 + [half], 60) is None
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
    checks["R-IV.1122(b): with no gap, the lookback skips nothing"] = r3["slot_skips"] == [] and \
        skip_counts([r3]) == (0, 0, 0)
    # a constructed DATA GAP: one regular prior session lacks the 10:05-10:10 slot the event confirms on
    o_gap = dict(o3)
    gk = ("SPY", ds[5])
    gb = o_gap[gk]
    o_gap[gk] = gb[~((gb.t_s >= 10 * 3600 + 5 * 60) & (gb.t_s < 10 * 3600 + 10 * 60))].reset_index(drop=True)
    r_gap = evaluate(Ctx(o_gap, tide, ivd, va, set(), ds), "SPY", ds[-1], 10 * 3600, 100.0, "BUYER")
    checks["R-IV.1122(b): a constructed data gap -> still a claim (A6), lookback skipped exactly that session"] = \
        r_gap["missing"] == [] and r_gap["fails"] == [] and r_gap["slot_skips"] == [ds[5]]
    checks["R-IV.1122(b): the count is NON-ZERO on the constructed gap, split 'data gap' (not half-day)"] = \
        skip_counts([r_gap, r3]) == (1, 0, 1)
    checks["R-IV.1122(b): a skipped early close classifies as half-day"] = \
        classify_skips([date(2026, 11, 27)]) == {"half_day": True, "data_gap": False}
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
    # amendment 3: SUSPECT intervals carry no verdict weight
    a3 = [dict(e, z=0.6, zp=[0.1], touched_L=(e["session"] == days10[0]), held_L=False) for e in evs]
    s3 = summarize(a3, 40)
    checks["A3: floor met, raw 'L not respected', interval SUSPECT -> kill does NOT fire, raw kept, named"] = \
        s3["stat_kill_floor_met"] and s3["win1_suspect"] and s3["raw_kill_readings"]["L_not_respected"] \
        and not s3["kill_L_not_respected"] and s3["kills_suppressed_suspect"] == ["kill_L_not_respected"]
    checks["A3: the block reads NO-KILL (SUSPECT)"] = verdict_of(s3) == "NO-KILL (SUSPECT)"
    checks["A3: a WIN whose interval is SUSPECT is NOT MET, named"] = s3["win1"] is False and \
        s3["win_not_met_suspect"] == ["win1"]
    checks["A3: a non-SUSPECT floor-met kill still fires -> KILL"] = not sm["win1_suspect"] and \
        sm["kill_L_not_respected"] and verdict_of(sm) == "KILL"
    base = {"kills_fired": [], "kills_suppressed_suspect": [], "stat_kill_floor_met": True, "freq_kill_floor_met": True}
    checks["A3: verdict branches KILL / NO-KILL (SUSPECT) / NO-KILL (INSUFFICIENT n) / NO-KILL"] = \
        verdict_of(dict(base, kills_fired=["x"])) == "KILL" and \
        verdict_of(dict(base, kills_suppressed_suspect=["x"])) == "NO-KILL (SUSPECT)" and \
        verdict_of(dict(base, stat_kill_floor_met=False)) == "NO-KILL (INSUFFICIENT n)" and \
        verdict_of(base) == "NO-KILL"
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
    checks.update(_a5_tests())
    checks.update(_read_tests())
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
        if not AMENDMENT_5:
            raise SystemExit("amendment 5 is not stamped yet; the first count run waits for it (R-IV.1114(e))")
        count(*sys.argv[2:13])
    elif mode == "read":                             # ONCE, in the 11-20 decision run (R-IV.1241(d))
        read(*sys.argv[2:15])
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
