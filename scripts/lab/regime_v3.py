"""Regime v2.1 and v3 rulesets for the joint run (R-IV.1283 / R-IV.1285; REGIME-v3-PREREGISTRATION-TA-208.md,
sha256 ab015afaeb479f0c8b348771cd847e953c414b04d076e1f96483651baa5f2a96, sections 1-2).

SYNTHETIC SMOKE TESTS ONLY until Nick's PR-1 stamp. No function here is run on a real date by this commit.

v2.1 (section 1): v2 exactly (999aae43: build_inputs + regime_inputs_v2.fill + classify + regime_seed.replay), plus:
    - spy.rsi_ge_75_of_last_5 is an INTEGER COUNT of the last 5 closes with RSI(14) >= melt_up_rsi_min (rules file);
    - spy.confirmed_break_up_50dma returns None (not True) when fewer than 21 volume values exist.
v3 (section 2): the v2.1 base layer plus the design layer, coded here. Unchanged rows call v2's own row functions
    (regime_classifier._row_crash / _row_breakdown / _row_correction / _row_range); the new rules are below.
    Four points of section 2 are OPEN QUESTIONS to TA (rules JSON `open_questions_to_TA`). The code takes each as an
    explicit option and REFUSES to run with a null, so no reading is picked here.

C0 throughout (R-IV.1279): sector breadth rescaled to 11, ^NDX / ^RUT for QQQ / IWM, None handling.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "backend")))

from models import regime_classifier as RC  # noqa: E402
from models import regime_inputs as RI  # noqa: E402

RULES_DIR = os.path.join(HERE, "regime_rules")
V21_PATH = os.path.join(RULES_DIR, "regime_rules.v2.1.json")
V3_PATH = os.path.join(RULES_DIR, "regime_rules.v3.json")
OPEN_KEYS = ("Q1_bear_count_horizon_when_no_reclaim_in_window", "Q2_decay_session",
             "Q2_decay_bypasses_hold_and_range_entry", "Q3_door_b_low_window_includes_today",
             "Q3_door_b_low_tie", "Q4_capitulation_low_includes_ties", "Q4_capitulation_upper_half_inclusive")
OPTION_VALUES = {
    "Q1_bear_count_horizon_when_no_reclaim_in_window": ("count_from_window_start", "second_clause_not_evaluable"),
    "Q2_decay_session": (10, 11),
    "Q2_decay_bypasses_hold_and_range_entry": (True, False),
    "Q3_door_b_low_window_includes_today": (True, False),
    "Q3_door_b_low_tie": ("earliest", "latest"),
    "Q4_capitulation_low_includes_ties": (True, False),
    "Q4_capitulation_upper_half_inclusive": (True, False),
}


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def resolve_options(rules_v3, overrides=None):
    """The answers to the open questions. A null is REFUSED: no reading is picked by the code."""
    o = dict(rules_v3["open_questions_to_TA"])
    o.pop("rule", None)
    o.update(overrides or {})
    missing = [k for k in OPEN_KEYS if o.get(k) is None]
    if missing:
        raise SystemExit("v3 open questions unanswered (TA): " + ", ".join(missing) + ". Refusing.")
    bad = [k for k in OPEN_KEYS if o[k] not in OPTION_VALUES[k]]
    if bad:
        raise SystemExit("v3 option outside its registered alternatives: " + ", ".join(bad))
    return o


# ── v2.1: the defect pack (section 1) ───────────────────────────────────────────────────────────
def rsi_hits_count(bars, threshold, lookback=5):
    """How many of the last `lookback` closes had RSI(14) >= threshold. None if any of them cannot be computed."""
    from indicators.rsi import latest_rsi
    cs = RI._closes(bars)
    if len(cs) < 15 + lookback:
        return None
    n = 0
    for k in range(lookback):
        r = latest_rsi(cs[:len(cs) - k])
        if r is None or r.get("value") is None:
            return None
        n += int(r["value"] >= threshold)
    return n


def confirmed_break_up_50dma_v21(bars, rules):
    """regime_inputs_v2.confirmed_break_up_50dma, except: fewer than 21 volume values -> None (v2 returned True)."""
    from models.regime_inputs_v2 import confirmed_break_up_50dma
    vols = [b.v for b in bars if b.v is not None]
    if len(vols) < 21:
        return None
    return confirmed_break_up_50dma(bars, rules)


def v21_fix(inputs, spy_bars, rules_v21):
    """Apply section 1 to an inputs dict built by build_inputs + regime_inputs_v2.fill (in place)."""
    th = rules_v21["thresholds"]
    inputs["spy"]["rsi_ge_75_of_last_5"] = rsi_hits_count(spy_bars, float(th["melt_up_rsi_min"]))
    inputs["spy"]["confirmed_break_up_50dma"] = confirmed_break_up_50dma_v21(spy_bars, rules_v21)
    return inputs


# ── v3 extras: per-session series over the loaded window ─────────────────────────────────────────
def _sma_series(c, n):
    out = np.full(len(c), np.nan)
    if len(c) >= n:
        cs = np.cumsum(np.r_[0.0, c])
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def v3_extras(spy_bars, rules_v3, opts):
    """The section-2 quantities that need more than today's bar. Every comparison over 'the last N closes' uses each
    session's own average (the v2 code's convention)."""
    th = rules_v3["thresholds"]
    lb = int(rules_v3["shared"]["falling_rising_lookback_sessions"])
    c = np.array([b.c for b in spy_bars], float)
    h = np.array([b.h for b in spy_bars], float)
    lo = np.array([b.l for b in spy_bars], float)
    v = np.array([np.nan if b.v is None else b.v for b in spy_bars], float)
    t = len(c) - 1
    s20, s50, s200 = _sma_series(c, 20), _sma_series(c, 50), _sma_series(c, 200)
    buf = 1.0 + float(th["bullish_buffer_pct"]) / 100.0
    x = {}
    # BEAR (b) reclaim and (c) the count since the most recent reclaim
    above1 = c >= buf * s200                                     # NaN comparisons are False
    nrc = int(th["reclaim_closes"])
    reclaim = np.array([i >= nrc - 1 and all(above1[i - k] for k in range(nrc)) for i in range(len(c))])
    falling200 = np.array([i >= lb and not np.isnan(s200[i]) and not np.isnan(s200[i - lb]) and s200[i] < s200[i - lb]
                           for i in range(len(c))])
    x["reclaim_now"] = bool(reclaim[t]) if not np.isnan(s200[t]) and t >= 1 and not np.isnan(s200[t - 1]) else None
    rec_idx = np.flatnonzero(reclaim[:t + 1])
    below_falling = (c < s200) & falling200
    if len(rec_idx):
        x["bear_count_since_reclaim"] = int(below_falling[rec_idx[-1] + 1:t + 1].sum())
        x["bear_count_basis"] = "since the reclaim at window position %d" % rec_idx[-1]
    elif opts["Q1_bear_count_horizon_when_no_reclaim_in_window"] == "count_from_window_start":
        x["bear_count_since_reclaim"] = int(below_falling[:t + 1].sum())
        x["bear_count_basis"] = "no reclaim in the window: counted from the window start (Q1)"
    else:
        x["bear_count_since_reclaim"] = None
        x["bear_count_basis"] = "no reclaim in the window: second clause NOT EVALUABLE (Q1)"
    # BEAR tags
    nr = int(th["rally_closes_above_20_and_50"])
    x["tag_rally"] = bool(t >= nr - 1 and all(c[t - k] > s20[t - k] and c[t - k] > s50[t - k] for k in range(nr)))
    L = int(th["capitulation_low_sessions"])
    rvol = np.full(len(c), np.nan)
    for i in range(20, len(c)):
        base = np.nanmean(v[i - 20:i])
        if base > 0 and not np.isnan(v[i]):
            rvol[i] = v[i] / base
    if t >= L - 1:
        prev = c[t - L + 1:t]
        low60 = (c[t] <= prev.min()) if opts["Q4_capitulation_low_includes_ties"] else (c[t] < prev.min())
        rng = h[t] - lo[t]
        pos = (c[t] - lo[t]) / rng if rng > 0 else None
        upper = None if pos is None else (pos >= 0.5 if opts["Q4_capitulation_upper_half_inclusive"] else pos > 0.5)
        x["tag_capitulation"] = bool(low60 and rvol[t] >= float(th["capitulation_rvol_min"]) and upper)
    else:
        x["tag_capitulation"] = False
    # RECOVERY doors
    na = int(th["door_a_closes_above_200dma"])
    x["door_a"] = bool(t >= na - 1 and all(not np.isnan(s200[t - k]) and c[t - k] > s200[t - k] for k in range(na)))
    W = int(th["door_b_low_lookback_sessions"])
    if t >= W - 1 + (0 if opts["Q3_door_b_low_window_includes_today"] else 1):
        seg = c[t - W + 1:t + 1] if opts["Q3_door_b_low_window_includes_today"] else c[t - W:t]
        end = t if opts["Q3_door_b_low_window_includes_today"] else t - 1
        mn = seg.min()
        hits = np.flatnonzero(seg == mn)
        j = hits[0] if opts["Q3_door_b_low_tie"] == "earliest" else hits[-1]
        low_pos = end - (len(seg) - 1) + j             # the low's position in the window
        x["low_age_sessions"] = int(t - low_pos)
    else:
        x["low_age_sessions"] = None
    rw = int(th["door_b_rvol_window_sessions"])
    rv = rvol[t - rw + 1:t + 1] if t >= rw - 1 else np.array([])
    x["rvol_hit_last_10"] = bool(len(rv) == rw and np.nanmax(rv) >= float(th["door_b_rvol_min"])) if len(rv) else None
    x["ma200_falling"] = bool(falling200[t]) if t >= lb and not np.isnan(s200[t - lb]) else None
    return x


def build_v3_inputs(inputs_v21, spy_bars, rules_v3, opts):
    """v3 reads the v2.1 inputs dict (build_inputs + fill + v21_fix, C0) plus its own extras."""
    inp = dict(inputs_v21)
    inp["v3"] = v3_extras(spy_bars, rules_v3, opts)
    return inp


# ── v3 classifier (section 2) ───────────────────────────────────────────────────────────────────
def _g(d, path):
    return RC._get(d, path)


def classify_v3(inp, shown_prev, rules_v3, rules_v2_th):
    """Top-down, first match wins: CRASH, BEAR, BREAKDOWN, CORRECTION, RANGE_CHOP, UPTREND, RECOVERY.
    `shown_prev` is the previously SHOWN label (what the card displayed), as v2's replay injects prior_regime.
    rules_v2_th: v2's thresholds dict, for the rows that are unchanged (crash, breakdown, correction, range entry)."""
    th = rules_v3["thresholds"]
    buf = float(th["bullish_buffer_pct"])
    x = inp["v3"]
    sp = inp["spy"]
    price, ma50, ma200 = RC._f(sp.get("price")), RC._f(sp.get("ma50")), RC._f(sp.get("ma200"))
    rows, tags, not_eval = [], [], []

    def done(regime, basis):
        return {"regime": regime, "basis": basis, "tags": tags, "not_evaluable_rows": not_eval, "rows": rows}

    # R1 CRASH -- unchanged from v2, NOT EVALUABLE (no VIX input in v3)
    r1 = RC._row_crash(inp, rules_v2_th)
    rows.append(r1.as_dict())
    if not r1.evaluable:
        not_eval.append("crash_liquidation")
    elif r1.matched:
        return done("crash_liquidation", r1.basis)
    # R2 BEAR
    if price is None or ma50 is None or ma200 is None or x["reclaim_now"] is None:
        not_eval.append("bear_market")
    else:
        off = RC._f(sp.get("pct_below_52w_high"))
        cnt = x["bear_count_since_reclaim"]
        a = ma50 < ma200
        b = not x["reclaim_now"]
        c1 = off is not None and off >= th["bear_pct_below_52w_high"]
        c2 = cnt is not None and cnt >= th["bear_closes_below_falling_200dma"]
        if a and b and (c1 or c2):
            if x["tag_rally"]:
                tags.append("rally")
            if x["tag_capitulation"]:
                tags.append("capitulation")
            return done("bear_market", "50dma < 200dma, no reclaim, and " +
                        ("%.1f%% below the 52-week high" % off if c1 else "%d closes below a falling 200dma since the reclaim" % cnt))
        if a and b and not c1 and cnt is None and off is None:
            not_eval.append("bear_market")
    # R3 BREAKDOWN -- unchanged from v2, including its volume test
    r3 = RC._row_breakdown(inp, rules_v2_th)
    rows.append(r3.as_dict())
    if not r3.evaluable:
        not_eval.append("breakdown")
    elif r3.matched:
        return done("breakdown", r3.basis)
    # R4 CORRECTION -- clauses 1-2 unchanged (v2's row), clause 3 new
    r4 = RC._row_correction(inp, rules_v2_th)
    rows.append(r4.as_dict())
    narrow = RC._f(sp.get("pct_below_52w_high"))
    if r4.matched or (shown_prev == "recovery" and price is not None and ma50 is not None and price < ma50):
        if narrow is not None and narrow <= th["correction_narrow_within_pct_of_high"]:
            tags.append("narrow")
        return done("correction", r4.basis if r4.matched else "clause 3: RECOVERY is shown and the close is below the 50dma")
    if not r4.evaluable:
        not_eval.append("correction")
    # R5 RANGE_CHOP -- entry as v2; keep-prior band while RANGE_CHOP is shown
    r5 = RC._row_range(inp, rules_v2_th)
    rows.append(r5.as_dict())
    if r5.matched:
        return done("range_chop", r5.basis)
    if shown_prev == "range_chop":
        adx = RC._f(sp.get("adx"))
        below = [t for t, d in (inp.get("indices") or {}).items()
                 if RC._f(d.get("price")) is not None and RC._f(d.get("ma50")) is not None
                 and RC._f(d.get("price")) < RC._f(d.get("ma50"))]
        if adx is not None and price is not None and ma50 is not None:
            dist = abs((price - ma50) / ma50 * 100.0)
            if adx < th["range_adx_keep_prior_upper"] and dist <= th["range_within_pct_of_50dma"] \
                    and len(below) < th["correction_indices_below_50dma"]:
                return done("range_chop", "keep-prior band: ADX %.1f < %.0f, %.1f%% from the 50dma" %
                            (adx, th["range_adx_keep_prior_upper"], dist))
    if not r5.evaluable:
        not_eval.append("range_chop")
    # R6 UPTREND
    rising = sp.get("ma50_rising")
    if price is None or ma50 is None or ma200 is None or rising is None:
        not_eval.append("uptrend")
    elif price >= ma50 * (1 + buf / 100.0) and ma50 > ma200 and rising is True:
        iwm = (inp.get("indices") or {}).get("IWM") or {}
        ip, im = RC._f(iwm.get("price")), RC._f(iwm.get("ma50"))
        sec = RC._f(_g(inp, "breadth.sectors_above_50dma"))
        if (ip is not None and im is not None and ip < im) or (sec is not None and sec <= th["narrow_sectors_max"]):
            tags.append("narrow")
        ext = (price - ma200) / ma200 * 100.0
        hits = sp.get("rsi_ge_75_of_last_5")
        if ext >= th["extended_pct_above_200dma"] and hits is not None and hits >= th["extended_rsi_hits_of_last_5"]:
            tags.append("extended")
        return done("uptrend", "close >= 50dma + %.0f%%, 50dma > 200dma, 50dma rising" % buf)
    # R7 RECOVERY -- ENTER (a prior label in the set, and a door) or STAY (RECOVERY shown)
    early = (price is not None and ma200 is not None and price < ma200) or x["ma200_falling"] is True
    if shown_prev == "recovery":
        if early:
            tags.append("early")
        return done("recovery", "STAY: RECOVERY is the shown label")
    entry_from = shown_prev in ("crash_liquidation", "bear_market", "breakdown", "correction") or (
        shown_prev == "range_chop" and ma50 is not None and ma200 is not None and ma50 < ma200)
    if entry_from:
        door_a = x["door_a"]
        door_b = (x["ma200_falling"] is False and price is not None and ma50 is not None
                  and price >= ma50 * (1 + buf / 100.0) and x["low_age_sessions"] is not None
                  and x["low_age_sessions"] >= th["door_b_low_min_age_sessions"] and x["rvol_hit_last_10"] is True)
        thrust = _g(inp, "breadth.thrust")
        door_c = thrust is True and price is not None and ma50 is not None and price > ma50
        if door_a or door_b or door_c:
            if early:
                tags.append("early")
            return done("recovery", "ENTER from %s through door %s" % (
                shown_prev, "A" if door_a else ("B" if door_b else "C")))
    return done(None, "no row matched; not evaluable: " + (", ".join(not_eval) or "none"))


# ── v3 hysteresis (section 2) ───────────────────────────────────────────────────────────────────
class HystV3:
    """Streaming v3 hysteresis. step(raw) -> the session's shown row."""

    def __init__(self, rules_v3, opts):
        h = rules_v3["hysteresis"]
        self.need = int(h["enter_requires_settled_closes"])
        self.hold = int(h["min_sessions_before_change"])
        self.toward = set(h["toward_risk_regimes"])
        self.pairs = {tuple(p) for p in h["hold_exempt_pairs"]}
        self.range_n = int(h["range_requires_sessions"])
        self.decay_at = int(opts["Q2_decay_session"])
        self.decay_bypass = bool(opts["Q2_decay_bypasses_hold_and_range_entry"])
        self.decay_label = h["decay_label"]
        self.shown, self.held, self.pending, self.pclose, self.unmatched = None, 0, None, 0, 0

    def step(self, cand):
        change = blocked = None
        by_decay = False
        if cand is None:
            self.unmatched += 1
            self.pending, self.pclose = None, 0
            if self.shown is not None:
                self.held += 1
                if self.unmatched >= self.decay_at and self.shown != self.decay_label:
                    if self.decay_bypass or self.held >= self.hold:
                        change = "%s -> %s by decay after %d unmatched sessions" % (self.shown, self.decay_label,
                                                                                    self.unmatched)
                        self.shown, self.held, by_decay = self.decay_label, 1, True
                    else:
                        blocked = "decay held back by the %d-session hold" % self.hold
        else:
            self.unmatched = 0
            if cand == self.shown:
                self.held += 1
                self.pending, self.pclose = None, 0
            else:
                if cand == self.pending:
                    self.pclose += 1
                else:
                    self.pending, self.pclose = cand, 1
                need = self.range_n if cand == "range_chop" else self.need
                if self.shown is None:
                    if self.pclose >= self.need:
                        change = "first label after %d closes" % self.pclose
                        self.shown, self.held, self.pending, self.pclose = cand, 1, None, 0
                else:
                    exempt = cand in self.toward or (self.shown, cand) in self.pairs
                    if self.pclose >= need and (self.held >= self.hold or exempt):
                        change = "%s -> %s after %d closes%s" % (self.shown, cand, self.pclose,
                                                                 " (exempt from the hold)" if exempt and self.held < self.hold else "")
                        self.shown, self.held, self.pending, self.pclose = cand, 1, None, 0
                    else:
                        if self.pclose >= need and not (self.held >= self.hold or exempt):
                            blocked = "%s qualifies but %s has held %d of %d sessions" % (cand, self.shown, self.held,
                                                                                          self.hold)
                        self.held += 1
        stale = cand is None and self.shown is not None and not by_decay
        return {"shown_regime": self.shown, "change": change, "blocked": blocked, "stale": stale,
                "by_decay": by_decay, "unmatched_run": self.unmatched, "held_sessions": self.held}


def group_v3(rules_v3, label):
    for g, ls in rules_v3["groups"].items():
        if label in ls:
            return g
    return None


def walk_v3(sessions_v3, rules_v3, rules_v2_th, opts):
    """Sequential v3 walk: each session is classified with the previously SHOWN label, then the hysteresis steps."""
    hy = HystV3(rules_v3, opts)
    out, prev = [], None
    for inp in sessions_v3:
        v = classify_v3(inp, prev, rules_v3, rules_v2_th)
        s = hy.step(v["regime"])
        s.update({"as_of": inp.get("as_of"), "regime": v["regime"], "tags": v["tags"], "basis": v["basis"],
                  "not_evaluable_rows": v["not_evaluable_rows"]})
        s["m1_stress_blocked"] = bool(s["blocked"] and (v["regime"] in rules_v3["groups"]["TREND-DOWN/STRESS"]))
        out.append(s)
        prev = s["shown_regime"]
    return out


# ── the joint-run label pipeline (runs only after PR-1; refuses without a stamp file) ──────────────
_J = {}


def _j_init(series, dates, vix, rules_v21, rules_v3, opts):
    import regime_scorecard as RS
    RS._w_init(series, dates, vix, "share")                 # C0: the rescaled count also feeds the thrust
    _J.update(series=series, dates=dates, vix=vix, r21=rules_v21, r3=rules_v3, opts=opts)


def _j_build(as_of):
    import bisect
    from models.regime_inputs_v2 import fill
    import regime_scorecard as RS
    series, dates = _J["series"], _J["dates"]
    w = {}
    for t, bars in series.items():
        j = bisect.bisect_right(dates[t], as_of)
        w[t] = bars[max(0, j - RS.WINDOW):j]
    k = len(w["SPY"]) - 1
    inp = RI.build_inputs(w, k, settled=True)
    if inp is None:
        return None
    cnt, _ = RS.share_count(w, as_of)
    if cnt is not None:
        inp["breadth"]["sectors_above_50dma"] = cnt
    fill(inp, w, k, rules=_J["r21"], vix=_J["vix"].get(as_of), window_dates=[b.date for b in w["SPY"]])
    v21_fix(inp, w["SPY"], _J["r21"])
    return inp, v3_extras(w["SPY"], _J["r3"], _J["opts"])


def labels_joint(bars_path, vix_path, out_dir, pr1_stamp_path, workers=20, _opts_for_tests=None, _label_from=None):
    """v2.1 and v3 labels over the C0 replay, from ONE input build. NOT TO BE RUN on a real date before PR-1:
    it refuses without `pr1_stamp_path`, and refuses while any v3 open question is unanswered in the rules JSON."""
    import copy
    from multiprocessing import Pool

    import pandas as pd
    import regime_scorecard as RS
    from jobs.regime_seed import replay
    if not pr1_stamp_path or not os.path.exists(pr1_stamp_path):
        raise SystemExit("no PR-1 stamp file: v2.1 / v3 do not run on any date before Nick's PR-1 stamp")
    r21, r3 = load(V21_PATH), load(V3_PATH)
    opts = resolve_options(r3, _opts_for_tests)
    os.makedirs(out_dir, exist_ok=True)
    assert not os.listdir(out_dir), "out_dir must be empty (one run)"
    df = pd.read_parquet(bars_path)
    df["date"] = pd.to_datetime(df["date"])
    series = RS.bars_from(df, "index")
    dates = {t: [b.date for b in v] for t, v in series.items()}
    vix = RS.vix_pairs(vix_path)
    todo = [d for d in dates["SPY"] if d >= (_label_from or RS.LABEL_FROM)]
    with Pool(workers, initializer=_j_init, initargs=(series, dates, vix, r21, r3, opts)) as pool:
        built = [b for b in pool.map(_j_build, todo, chunksize=25) if b is not None]
    s21 = [b[0] for b in built]
    s3 = [dict(copy.deepcopy(b[0]), vix={}, v3=b[1], prior_regime=None) for b in built]
    out21 = replay(s21, r21)
    v2th = RC.load_rules("v2")["thresholds"]
    w3 = walk_v3(s3, r3, v2th, opts)
    l21 = pd.DataFrame({"as_of": [r["as_of"] for r in out21["shown"]], "regime": [r.get("regime") for r in out21["shown"]],
                        "shown_regime": [r.get("shown_regime") for r in out21["shown"]],
                        "change": [r.get("change") for r in out21["shown"]], "blocked": [r.get("blocked") for r in out21["shown"]]})
    l3 = pd.DataFrame([{k: (",".join(v) if isinstance(v, list) else v) for k, v in r.items() if k != "basis"} for r in w3])
    p21, p3 = os.path.join(out_dir, "labels_v2.1.csv"), os.path.join(out_dir, "labels_v3.csv")
    l21.to_csv(p21, index=False)
    l3.to_csv(p3, index=False)
    meta = {"pr1_stamp": {"file": os.path.basename(pr1_stamp_path), "sha256": RS.sha256(pr1_stamp_path)},
            "rules": {"v2.1": RS.sha256(V21_PATH), "v3": RS.sha256(V3_PATH)}, "options": opts,
            "bars_sha256": RS.sha256(bars_path), "vix_sha256": RS.sha256(vix_path),
            "labels_v2.1_sha256": RS.sha256(p21), "labels_v3_sha256": RS.sha256(p3), "sessions": len(l3)}
    json.dump(meta, open(os.path.join(out_dir, "labels_meta.json"), "w"), indent=1, default=str)
    return meta, l21, l3


def _synthetic_files(tmp):
    """Synthetic bars (SPY, QQQ, IWM, ^NDX, ^RUT, 11 SPDRs) and a synthetic VIX file, in the replay's layouts."""
    import pandas as pd
    rng = np.random.default_rng(29)
    d = pd.bdate_range("1997-01-02", periods=720)
    rows = []
    path = np.r_[np.linspace(0, 0.5, 300), np.linspace(0.5, 0.1, 120), np.linspace(0.1, 0.6, 300)]
    for t in ("SPY", "QQQ", "IWM", "^NDX", "^RUT") + tuple(RI.SECTORS):
        c = 100 * np.exp(path + 0.01 * np.cumsum(rng.standard_normal(len(d))))
        start = 0 if t not in ("XLRE", "XLC") else 500
        rows.append(pd.DataFrame({"ticker": t, "date": d[start:], "open": c[start:] * 0.999, "high": c[start:] * 1.01,
                                  "low": c[start:] * 0.99, "close": c[start:], "adj_close": c[start:],
                                  "volume": 1e6 * (1 + rng.random(len(d) - start))}))
    bp = os.path.join(tmp, "bars.parquet")
    pd.concat(rows, ignore_index=True).to_parquet(bp, index=False)
    vp = os.path.join(tmp, "vix.parquet")
    pd.concat([pd.DataFrame({"ticker": t, "date": d, "close": 20.0 + i}) for i, t in enumerate(("^VIX", "^VIX3M"))]).to_parquet(vp, index=False)
    return bp, vp


# ── self-test (SYNTHETIC ONLY) ──────────────────────────────────────────────────────────────────
def selftest():
    ok = fail = 0

    def check(name, cond):
        nonlocal ok, fail
        ok, fail = ok + bool(cond), fail + (not cond)
        print(("PASS " if cond else "FAIL ") + name)

    r21, r3 = load(V21_PATH), load(V3_PATH)
    v2 = RC.load_rules("v2")
    check("v2.1 JSON: thresholds, hysteresis and order are v2's; version v2.1",
          r21["thresholds"] == v2["thresholds"] and r21["hysteresis"] == v2["hysteresis"]
          and r21["order"] == v2["order"] and r21["version"] == "v2.1")
    check("v3 JSON: the 7 rows in section 2's order", r3["order"] == ["crash_liquidation", "bear_market", "breakdown",
                                                                     "correction", "range_chop", "uptrend", "recovery"])
    check("v3 JSON: bear_market added to the toward-risk (hold-exempt) set",
          set(r3["hysteresis"]["toward_risk_regimes"]) == {"breakdown", "crash_liquidation", "bear_market"})
    try:
        resolve_options(r3)
        refused = False
    except SystemExit as e:
        refused = "unanswered" in str(e)
    check("v3: the open questions are null and the code REFUSES to run without TA's answers", refused)
    base_opts = {"Q1_bear_count_horizon_when_no_reclaim_in_window": "count_from_window_start", "Q2_decay_session": 10,
                 "Q2_decay_bypasses_hold_and_range_entry": True, "Q3_door_b_low_window_includes_today": True,
                 "Q3_door_b_low_tie": "latest", "Q4_capitulation_low_includes_ties": False,
                 "Q4_capitulation_upper_half_inclusive": True}
    opts = resolve_options(r3, base_opts)
    try:
        resolve_options(r3, dict(base_opts, Q2_decay_session=7))
        bad = False
    except SystemExit:
        bad = True
    check("v3: an option outside the registered alternatives is refused", bad)

    def bars_from(c, v=None, h=None, lo=None):
        return [RI.Bar("2001-%02d-%02d" % (1 + i // 28 % 12, 1 + i % 28), cc, (h[i] if h is not None else cc * 1.002),
                       (lo[i] if lo is not None else cc * 0.998), cc, (v[i] if v is not None else 1e6))
                for i, cc in enumerate(c)]

    # v2.1 rsi count
    up = list(np.linspace(100, 200, 260))
    check("v2.1: RSI hits are an INTEGER count (a steady rise: 5 of 5)", rsi_hits_count(bars_from(up), 75.0) == 5)
    check("v2.1: the count reads its threshold (101 -> 0)", rsi_hits_count(bars_from(up), 101.0) == 0)
    short = bars_from(up[:30])
    for b in short[:15]:
        b.v = None
    check("v2.1: up-side volume check -> None with < 21 volume values", confirmed_break_up_50dma_v21(short, r21) is None)
    # v3 extras: the bear count persists through a single close above the 200dma; only a 2-close reclaim resets
    c = list(np.linspace(150, 200, 250)) + list(np.linspace(200, 140, 60))
    c2 = c + [c[-1] * 0.99] * 5
    n0 = v3_extras(bars_from(c2), r3, opts)["bear_count_since_reclaim"]
    s200 = _sma_series(np.array(c2), 200)
    c3 = list(c2)
    c3[-3] = s200[-3] * 1.005                              # one close above the 200dma (not 1% above): no reset
    n1 = v3_extras(bars_from(c3), r3, opts)["bear_count_since_reclaim"]
    c4 = list(c2)
    c4[-4], c4[-3] = s200[-4] * 1.02, s200[-3] * 1.02      # a 2-close >= 1% reclaim: resets
    x4 = v3_extras(bars_from(c4), r3, opts)
    check("v3 BEAR(c): a single close above the 200dma does NOT reset the count", n1 is not None and n1 >= n0 - 1 and n1 > 15)
    check("v3 BEAR(c): a 2-close reclaim resets it (only the 2 later closes can count)",
          x4["bear_count_since_reclaim"] <= 2 and "since the reclaim" in x4["bear_count_basis"])
    dn = list(np.linspace(200, 100, 320))                 # always below its 200dma: no reclaim anywhere
    xa = v3_extras(bars_from(dn), r3, opts)
    xb = v3_extras(bars_from(dn), r3, dict(opts, Q1_bear_count_horizon_when_no_reclaim_in_window="second_clause_not_evaluable"))
    check("v3 Q1 'count_from_window_start': no reclaim -> counted over the window (> 15)",
          xa["bear_count_since_reclaim"] is not None and xa["bear_count_since_reclaim"] > 15 and "window start" in xa["bear_count_basis"])
    check("v3 Q1 'second_clause_not_evaluable': no reclaim -> None", xb["bear_count_since_reclaim"] is None)
    # door A / door B quantities computed from a series
    base = list(np.linspace(100, 90, 230)) + list(np.linspace(90, 80, 20)) + list(np.linspace(80.5, 95, 30))
    vol = [1e6] * len(base)
    vol[-5] = 1.5e6                                         # one RVOL >= 1.2 inside the last 10 sessions
    xs = v3_extras(bars_from(base, v=vol), r3, opts)
    check("v3 door B input: the 60-session low (index 249) is 30 sessions old", xs["low_age_sessions"] == len(base) - 1 - 249)
    check("v3 door B input: an RVOL >= 1.2 among the last 10 sessions", xs["rvol_hit_last_10"] is True)
    vol2 = [1e6] * len(base)
    check("v3 door B input: no RVOL hit with flat volume",
          v3_extras(bars_from(base, v=vol2), r3, opts)["rvol_hit_last_10"] is False)
    flat = [100.0] * 250 + [100.0] * 5
    tie_e = v3_extras(bars_from(flat), r3, dict(opts, Q3_door_b_low_tie="earliest"))["low_age_sessions"]
    tie_l = v3_extras(bars_from(flat), r3, dict(opts, Q3_door_b_low_tie="latest"))["low_age_sessions"]
    check("v3 Q3 tie option: earliest -> 59 sessions old, latest -> 0", tie_e == 59 and tie_l == 0)
    ex_today = v3_extras(bars_from(flat), r3, dict(opts, Q3_door_b_low_tie="earliest",
                                                   Q3_door_b_low_window_includes_today=False))["low_age_sessions"]
    check("v3 Q3 window option: excluding today shifts the earliest tie to 60 sessions old", ex_today == 60)
    up200 = list(np.linspace(80, 100, 250)) + [101, 102, 103, 104, 105]
    check("v3 door A input: the last 5 closes each above their own 200dma", v3_extras(bars_from(up200), r3, opts)["door_a"] is True)
    # capitulation tag (display only)
    cap = list(np.linspace(120, 100, 260)) + [95.0]
    hv = [1e6] * len(cap)
    hv[-1] = 3e6
    hh = [x * 1.002 for x in cap]
    ll = [x * 0.998 for x in cap]
    hh[-1], ll[-1] = 96.0, 93.0                            # close 95 sits in the upper third of 93..96
    check("v3 capitulation tag: a 60-session closing low, RVOL >= 2, close in the upper half",
          v3_extras(bars_from(cap, v=hv, h=hh, lo=ll), r3, opts)["tag_capitulation"] is True)
    hh2 = list(hh)
    hh2[-1] = 97.0                                          # close exactly at the midpoint of 93..97
    check("v3 Q4 option: the midpoint is in the upper half only if inclusive",
          v3_extras(bars_from(cap, v=hv, h=hh2, lo=ll), r3, opts)["tag_capitulation"] is True and
          v3_extras(bars_from(cap, v=hv, h=hh2, lo=ll), r3, dict(opts, Q4_capitulation_upper_half_inclusive=False))["tag_capitulation"] is False)
    # handcrafted inputs for the rows
    th2 = v2["thresholds"]

    def inp(price, ma50, ma200, **kw):
        sp = {"price": price, "ma50": ma50, "ma200": ma200, "ma20": kw.get("ma20", ma50), "ma50_rising": kw.get("rising", True),
              "ma50_falling": kw.get("ma50_falling", False), "pct_below_52w_high": kw.get("off", 2.0),
              "confirmed_break_down_50dma": kw.get("brk", False), "adx": kw.get("adx", 30.0),
              "adx_below_20_sessions": kw.get("adx_run", 0), "market_state": kw.get("state", "trend"),
              "rsi_ge_75_of_last_5": kw.get("hits", 0)}
        idx = kw.get("indices", {"SPY": {"price": price, "ma50": ma50}, "QQQ": {"price": 10, "ma50": 9},
                                 "IWM": {"price": 10, "ma50": 9}})
        x = {"reclaim_now": kw.get("reclaim", False), "bear_count_since_reclaim": kw.get("cnt", 0), "tag_rally": kw.get("rally", False),
             "tag_capitulation": False, "door_a": kw.get("door_a", False), "low_age_sessions": kw.get("low_age", 0),
             "rvol_hit_last_10": kw.get("rvol", False), "ma200_falling": kw.get("f200", False)}
        return {"spy": sp, "indices": idx, "breadth": {"sectors_above_50dma": kw.get("sec", 8), "thrust": kw.get("thrust", False)},
                "vix": {}, "families": {}, "v3": x, "settled": True}

    cl = lambda i, prev=None: classify_v3(i, prev, r3, th2)  # noqa: E731
    check("v3 R2 BEAR: 50 < 200, no reclaim, 25% off the high", cl(inp(80, 90, 100, off=25.0))["regime"] == "bear_market")
    check("v3 R2 BEAR: a reclaim blocks it", cl(inp(80, 90, 100, off=25.0, reclaim=True))["regime"] != "bear_market")
    check("v3 R2 BEAR: 15 closes below a falling 200dma since the reclaim", cl(inp(95, 97, 100, off=8.0, cnt=15))["regime"] == "bear_market")
    check("v3 R2 BEAR tag rally stays STRESS", cl(inp(80, 90, 100, off=25.0, rally=True))["tags"] == ["rally"])
    check("v3 R3 BREAKDOWN: v2's row (confirmed break + below the 200dma)",
          cl(inp(95, 97, 96, off=8.0, brk=True))["regime"] == "breakdown")
    check("v3 R4 CORRECTION clause 1 (v2's)", cl(inp(105, 107, 100, off=8.0))["regime"] == "correction")
    check("v3 R4 CORRECTION clause 3: RECOVERY shown and close below the 50dma",
          cl(inp(99, 100, 102, off=8.0, rising=False), "recovery")["regime"] == "correction")
    rg = inp(101, 100, 95, adx=18.0, adx_run=12, state="range", indices={"SPY": {"price": 101, "ma50": 100}})
    check("v3 R5 RANGE entry (v2's: ADX < 20 for 10+, within 3%)", cl(rg)["regime"] == "range_chop")
    kp = inp(100.5, 100, 95, adx=22.0, adx_run=0, rising=False, indices={"SPY": {"price": 100.5, "ma50": 100}})
    check("v3 R5 keep-prior band: ADX 22 < 25 holds RANGE only while RANGE is shown",
          cl(kp, "range_chop")["regime"] == "range_chop" and cl(kp, "uptrend")["regime"] != "range_chop")
    check("v3 R6 UPTREND: >= 1% over the 50dma, 50 > 200, rising", cl(inp(102, 100, 90))["regime"] == "uptrend")
    check("v3 R6 UPTREND: 0.5% over the 50dma is not enough (bullish buffer)", cl(inp(100.5, 100, 90))["regime"] != "uptrend")
    ex = cl(inp(115, 100, 100 / 1.15, hits=2, sec=3))
    check("v3 R6 tags: narrow (sectors <= 4) and extended (>= 12% over the 200dma, 2 RSI hits)",
          ex["regime"] == "uptrend" and set(ex["tags"]) == {"narrow", "extended"})
    rec = inp(101.5, 100, 103, off=8.0, rising=False, door_a=True)
    check("v3 R7 RECOVERY: ENTER from bear_market through door A", cl(rec, "bear_market")["regime"] == "recovery")
    check("v3 R7 RECOVERY: no entry from uptrend (not in the entry set)", cl(rec, "uptrend")["regime"] != "recovery")
    check("v3 R7 RECOVERY: tag early (close below the 200dma)", "early" in cl(rec, "bear_market")["tags"])
    db = inp(101.5, 100, 103, off=8.0, rising=False, low_age=12, rvol=True, f200=False)
    check("v3 R7 door B: 200dma not falling, +1% over the 50dma, low 12 sessions old, an RVOL hit",
          cl(db, "correction")["basis"].endswith("door B"))
    check("v3 R7 door B fails when the low is only 9 sessions old",
          cl(inp(101.5, 100, 103, off=8.0, rising=False, low_age=9, rvol=True), "correction")["regime"] is None)
    check("v3 R7 STAY: RECOVERY shown and nothing above matches", cl(inp(101.5, 100, 103, off=8.0, rising=False), "recovery")["regime"] == "recovery")
    dc = inp(100.5, 100, 103, off=8.0, rising=False, thrust=True)
    check("v3 R7 door C: the breadth thrust and the close above the 50dma",
          cl(dc, "breakdown")["basis"].endswith("door C"))
    check("v3 R7 entry from range_chop only with the 50dma below the 200dma",
          cl(dc, "range_chop")["regime"] == "recovery" and cl(inp(100.5, 100, 99, off=8.0, rising=False, thrust=True),
                                                              "range_chop")["regime"] != "recovery")
    check("v3: crash is NOT EVALUABLE (no VIX input)", "crash_liquidation" in cl(inp(102, 100, 90))["not_evaluable_rows"])
    # hysteresis
    hy = HystV3(r3, opts)
    seq = ["uptrend", "uptrend", "uptrend", "correction", "correction"]
    sh = [hy.step(x)["shown_regime"] for x in seq]
    check("hysteresis: 2 closes to enter; correction after 3 sessions of uptrend is HELD (5-session hold)",
          sh == [None, "uptrend", "uptrend", "uptrend", "uptrend"])
    hy = HystV3(r3, opts)
    for x in ["uptrend", "uptrend", "uptrend"]:
        hy.step(x)
    a = hy.step("bear_market")
    b = hy.step("bear_market")
    check("hysteresis: bear_market is exempt from the hold (2 closes, no hold)", b["shown_regime"] == "bear_market" and a["shown_regime"] == "uptrend")
    hy = HystV3(r3, opts)
    for x in ["recovery", "recovery", "recovery"]:
        hy.step(x)
    hy.step("correction")
    check("hysteresis: CORRECTION from RECOVERY is exempt from the hold", hy.step("correction")["shown_regime"] == "correction")
    hy = HystV3(r3, opts)
    for x in ["correction"] * 8:
        hy.step(x)
    out = [hy.step("range_chop")["shown_regime"] for _ in range(10)]
    check("hysteresis: RANGE_CHOP entry needs 10 consecutive closes", out[:9] == ["correction"] * 9 and out[9] == "range_chop")

    def decay_run(at):
        h = HystV3(r3, dict(opts, Q2_decay_session=at))
        for x in ["bear_market"] * 8:
            h.step(x)
        return [h.step(None) for _ in range(12)]
    d10, d11 = decay_run(10), decay_run(11)
    check("decay Q2=10: STALE on unmatched 1-9, range_chop by decay on the 10th",
          all(r["stale"] for r in d10[:9]) and d10[9]["by_decay"] and d10[9]["shown_regime"] == "range_chop")
    check("decay Q2=11: STALE on unmatched 1-10, range_chop by decay on the 11th",
          all(r["stale"] for r in d11[:10]) and d11[10]["by_decay"] and d11[9]["shown_regime"] == "bear_market")
    h = HystV3(r3, opts)
    for x in ["uptrend"] * 6 + [None] * 10:
        h.step(x)
    check("decay never produces an UP label", h.shown == "range_chop")
    w = walk_v3([inp(102, 100, 90)] * 3 + [inp(80, 90, 100, off=25.0)] * 3, r3, th2, opts)
    check("walk: uptrend then bear_market (exempt): M1 = 0 STRESS blocked",
          [r["shown_regime"] for r in w] == [None, "uptrend", "uptrend", "uptrend", "bear_market", "bear_market"]
          and not any(r["m1_stress_blocked"] for r in w))
    # the joint-run pipeline, end to end, on SYNTHETIC files only
    import tempfile
    tmp = tempfile.mkdtemp()
    bp, vp = _synthetic_files(tmp)
    try:
        labels_joint(bp, vp, os.path.join(tmp, "x"), None, workers=2, _opts_for_tests=opts, _label_from="1999-01-04")
        nostamp = False
    except SystemExit as e:
        nostamp = "PR-1" in str(e)
    check("pipeline: refuses to run without a PR-1 stamp file", nostamp)
    stamp = os.path.join(tmp, "synthetic-stamp.md")
    open(stamp, "w").write("synthetic test stamp")
    try:
        labels_joint(bp, vp, os.path.join(tmp, "y"), stamp, workers=2, _label_from="1999-01-04")
        noans = False
    except SystemExit as e:
        noans = "unanswered" in str(e)
    check("pipeline: refuses while TA's answers are not in the v3 JSON", noans)
    meta, l21, l3 = labels_joint(bp, vp, os.path.join(tmp, "z"), stamp, workers=2, _opts_for_tests=opts,
                                 _label_from="1998-09-01")
    check("pipeline e2e (synthetic): v2.1 and v3 labels for every session, from one input build",
          len(l21) == len(l3) == meta["sessions"] > 100 and set(l3.columns) >= {"shown_regime", "tags", "stale", "by_decay",
                                                                                   "m1_stress_blocked"})
    check("pipeline e2e (synthetic): v3 shows only its 7 regimes (and None before the first label)",
          set(l3.shown_regime.dropna()) <= set(r3["order"]))
    check("pipeline e2e (synthetic): v2.1 shows only v2's regimes", set(l21.shown_regime.dropna()) <= set(r21["order"]))
    print(f"{ok}/{ok + fail}")
    return fail == 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["selftest"]:
        sys.exit(0 if selftest() else 1)
    print(__doc__)
    sys.exit(2)
