"""Regime-filter study v1 (R-IV.1200(c); stamped R-IV.1201, amended R-IV.1208, confirmed R-IV.1218(a)).
Run under R-IV.1238(b)1.

Copy of record: C:\\temp\\cc-query-handoff\\lab\\regime-filter\\REGIME-FILTER-STUDY-v1-STAMPED-R-IV.1208.md
    sha256 6725ab86c0b026ccd8571ff8d3adea18de84f006394606d4ecdcd63b8af29f2f

Three steps; LAB runs the first two, QUERY runs the third (LAB never receives regime_snapshots rows):
    pull   one dated yfinance auto_adjust=False pull (sha256 stated). Indicators run on FULLY adjusted
           OHLC derived exactly as yfinance's auto_adjust does (x Adj Close / Close); returns on the
           split-adjusted, dividend-unadjusted Open / Close; beta on Adj Close.
    fires  each strategy's rules AS CODED today (the hub's own functions), over the seeded range
           2025-08-06 -> 2026-10-16. OUTCOME-FREE: the fire file carries no return.
    grade  (QUERY) joins regime_snapshots' shown_regime (superseded = false), grades h5 r_adj from the
           next open, in-home minus out-of-home, date-clustered t, Holm over k, the SPY guard.

STRATEGIES (§3), each through its own coded function:
    HYPNOS-LELEDC  hypnos_leledc.detect (protocol 1, main arm 250, split-adj OHLC)      RANGE
    CIRCES_STEW    scanners.circes_stew.detect (every persisted geometric trigger)    RANGE
    TRAPPED_SHORTS HECTOR, cta_scanner.check_trapped_shorts (replay_t8.masks)        TREND-UP
    GOLDEN_TOUCH   MIDAS, cta_scanner.check_golden_touch minus death cross            TREND-UP
    NEMESIS_LONG   PHOENIX as coded, wrr_buy_model (replay_t5.phoenix_masks)          TREND-UP
    TWO_CLOSE_VOLUME  PERSEPHONE, cta_scanner (replay_t5.cta_masks)                   TREND-UP
    RESISTANCE_REJECTION  SISYPHUS (replay_t8.masks)                                 TREND-DOWN/STRESS
    BEARISH_BREAKDOWN  PHAETHON (replay_t5.cta_masks)                                TREND-DOWN/STRESS
    WRR_LONG       NEMESIS, registered_shadow.nemesis_long; NOT replayed on any session >= 2026-10-12
                   (nemesis-long-v1's forward window, same principle as R-IV.1201(b)5)       RANGE
    NOT REPLAYABLE (R-IV.877(a)), so no replayed fires and they do not enter (§3): ACHILLES (all three
    variants: the scan-wide composite-bias gate has no history), ARTEMIS_SHORT (15-minute Pine).

UNIVERSE (the stamp is silent; LAB's reading, flagged for SPINE): each rule's own coded universe where
it can be rebuilt: registered_shadow.UNIVERSE for WRR_LONG; the census proxy universe
(census_expected.proxy_universe = universe.py's own fallback, first 200, SPY as benchmark only) for the
cta / wrr / CIRCE rules, whose live universes (dynamic scan, PYTHIA coverage) cannot be rebuilt for past
dates; protocol 1's main arm for HYPNOS.

Usage:
    python scripts/lab/regime_filter.py pull <out.parquet>
    python scripts/lab/regime_filter.py fires <pull.parquet> <themed.parquet> <out_dir>
    python scripts/lab/regime_filter.py grade <fires.csv> <pull.parquet> <themed.parquet> <labels.csv> <out_dir>
    python scripts/lab/regime_filter.py p1-label-counts <signals_for_label_join.csv> <labels.csv>
    python scripts/lab/regime_filter.py selftest
"""
import hashlib
import json
import logging
import os
import sys
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "backend")))
logging.disable(logging.CRITICAL)

import hypnos_leledc as HL  # noqa: E402
import lab_stats as S  # noqa: E402

COPY_OF_RECORD = "REGIME-FILTER-STUDY-v1-STAMPED-R-IV.1208.md"
COPY_SHA256 = "6725ab86c0b026ccd8571ff8d3adea18de84f006394606d4ecdcd63b8af29f2f"
PULL_START, PULL_END = "2023-01-01", "2026-10-17"      # end exclusive: bars through 2026-10-16
SEED_FIRST, SEED_LAST, SEED_ROWS = date(2025, 8, 6), date(2026, 10, 16), 302
NEMESIS_CUTOFF = date(2026, 10, 12)
H_PRIMARY = 5
MIN_HOME_DATES = 20
T_PASS, ALPHA = 2.0, 0.05

GROUPS = {
    "TREND-UP": ("uptrend", "narrow_uptrend", "melt_up", "recovery"),
    "RANGE": ("range_chop", "correction"),
    "TREND-DOWN/STRESS": ("breakdown", "bear_market", "bear_market_rally", "crash_liquidation"),
}
REGIME_TO_GROUP = {r: g for g, rs_ in GROUPS.items() for r in rs_}

# strategy -> (signal_type, side, home, prior_seen, card horizon or None, source of that horizon)
STRATEGIES = {
    "HYPNOS-LELEDC": ("EXHAUSTION", "BOTH", "RANGE", False, None, "card states none"),
    "CIRCE": ("CIRCES_STEW", "BOTH", "RANGE", False, 1, "circes-stew.md horizon finding: B3 one-session"),
    "HECTOR": ("TRAPPED_SHORTS", "LONG", "TREND-UP", True, 3, "hector.md evidence at h3"),
    "MIDAS": ("GOLDEN_TOUCH", "LONG", "TREND-UP", True, 3, "midas.md evidence at h3"),
    "PHOENIX": ("NEMESIS_LONG", "LONG", "TREND-UP", False, 3, "phoenix.md evidence at h3"),
    "PERSEPHONE": ("TWO_CLOSE_VOLUME", "LONG", "TREND-UP", False, None, "card states none"),
    "SISYPHUS": ("RESISTANCE_REJECTION", "SHORT", "TREND-DOWN/STRESS", True, 3, "sisyphus.md evidence at h3"),
    "PHAETHON": ("BEARISH_BREAKDOWN", "SHORT", "TREND-DOWN/STRESS", False, None, "card states none"),
    "NEMESIS": ("WRR_LONG", "LONG", "RANGE", False, 1, "nemesis-long-v1.md §5 primary h = 1"),
}
#: R-IV.1241(b)1: each rule on its own coded universe where it can be rebuilt, the census proxy otherwise;
#: the report labels each strategy's universe.
UNIVERSE_BASIS = {
    "HYPNOS-LELEDC": "own: protocol 1's main arm (250), R-IV.1230",
    "NEMESIS": "own coded universe: registered_shadow.UNIVERSE (frozen, 196)",
    "CIRCE": "census proxy (coded universe = PYTHIA-covered tickers, not rebuildable for past dates)",
    "PHOENIX": "census proxy (coded universe = build_scan_universe(200), dynamic; the proxy is its own fallback)",
    "HECTOR": "census proxy (cta dynamic universe; the proxy is its own fallback)",
    "MIDAS": "census proxy (cta dynamic universe; the proxy is its own fallback)",
    "PERSEPHONE": "census proxy (cta dynamic universe; the proxy is its own fallback)",
    "SISYPHUS": "census proxy (cta dynamic universe; the proxy is its own fallback)",
    "PHAETHON": "census proxy (cta dynamic universe; the proxy is its own fallback)",
}
NOT_REPLAYABLE = {
    "ACHILLES (SELL_RIP_EMA, SELL_RIP_VWAP, SELL_RIP_EARLY)": "R-IV.877(a): scan-wide composite-bias gate, no history",
    "ARTEMIS (ARTEMIS_SHORT)": "R-IV.877(a): 15-minute TradingView Pine, no hub detector",
}


def sha256(path):
    return HL.sha256(path)


def assert_groups():
    keys = [r for rs_ in GROUPS.values() for r in rs_]
    assert len(keys) == 10 and len(set(keys)) == 10, keys


# ── pull ──────────────────────────────────────────────────────────────────────────────────
def universes():
    from census_expected import proxy_universe
    from strategies import registered_shadow as rs
    proxy = [t for t in proxy_universe() if t != "SPY"]
    return {"proxy": proxy, "registered": list(rs.UNIVERSE)}


def pull(out_path):
    import yfinance as yf
    u = universes()
    tickers = sorted(set(u["proxy"]) | set(u["registered"]) | {"SPY"})
    rows = []
    for i in range(0, len(tickers), 25):
        part = tickers[i:i + 25]
        raw = yf.download(part, start=PULL_START, end=PULL_END, auto_adjust=False, group_by="ticker",
                          threads=True, progress=False)
        for t in part:
            try:
                df = raw[t].dropna(how="all")
            except KeyError:
                continue
            df = df.dropna(subset=["Open", "High", "Low", "Close", "Adj Close"])
            if not len(df):
                continue
            df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
            rows.append(pd.DataFrame({"ticker": t, "date": df.index, "open": df["Open"].values,
                                      "high": df["High"].values, "low": df["Low"].values,
                                      "close": df["Close"].values, "adj_close": df["Adj Close"].values,
                                      "volume": df["Volume"].values}))
    out = pd.concat(rows, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)
    assert (out.close != out.adj_close).mean() > 0.3, "adj_close == close: the beta basis would be vacuous"
    out.to_parquet(out_path, index=False)
    meta = {"file": os.path.basename(out_path), "sha256": sha256(out_path), "rows": int(len(out)),
            "tickers": int(out.ticker.nunique()), "requested": len(tickers),
            "missing": sorted(set(tickers) - set(out.ticker.unique())),
            "span": [str(out.date.min().date()), str(out.date.max().date())],
            "source": f"yfinance {yf.__version__} daily, auto_adjust=False, pulled "
                      + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "columns": "open/high/low/close split-adjusted dividend-unadjusted; adj_close split+dividend"}
    with open(out_path + ".meta.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    return meta


def frames_from_pull(path):
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    spy = df[df.ticker == "SPY"].set_index("date").sort_index()
    cal = spy.index
    out = {}
    for t, g in df.groupby("ticker"):
        g = g.set_index("date").sort_index().reindex(cal)
        fac = g["adj_close"] / g["close"]
        out[t] = pd.DataFrame({"O": g["open"] * fac, "H": g["high"] * fac, "L": g["low"] * fac,
                               "C": g["adj_close"], "V": g["volume"],
                               "rO": g["open"], "rC": g["close"]}, index=cal)
    return out, cal


# ── fires (outcome-free) ──────────────────────────────────────────────────────────────────
def in_seed(cal):
    d = cal.date
    return (d >= SEED_FIRST) & (d <= SEED_LAST)


def circe_mask(df):
    from scanners import circes_stew as cs
    fr = pd.DataFrame({"date": df.index.date, "h": df.H.values, "l": df.L.values, "c": df.C.values})
    have = fr[["h", "l", "c"]].notna().all(axis=1).values
    out = {"LONG": np.zeros(len(fr), bool), "SHORT": np.zeros(len(fr), bool)}
    win = cs.N_BARS + cs.CONFIRM_BARS + 6
    seed = in_seed(df.index)
    for i in np.flatnonzero(seed & have):
        sub = fr.iloc[max(0, i - win + 1): i + 1]
        sub = sub[sub[["h", "l", "c"]].notna().all(axis=1)]
        for trig in cs.detect(sub):
            if trig.fire_date == fr["date"].iat[i]:
                out[trig.direction][i] = True
    return out


def nemesis_mask(df):
    from strategies import registered_shadow as rs
    keep = df.index.date < NEMESIS_CUTOFF
    f = pd.DataFrame({"o": df.O, "h": df.H, "l": df.L, "c": df.C, "v": df.V})[keep]
    f = f.dropna()
    m = rs.nemesis_long(f) if len(f) else pd.Series(dtype=bool)
    full = pd.Series(False, index=df.index)
    full.loc[m.index[m.values]] = True
    skipped = int((~keep & df.C.notna().values).sum())
    return full.values, skipped


def strategy_masks(df, ticker, which):
    import replay_t5 as rp
    import replay_t8 as r8
    out = {}
    if "proxy" in which:
        p = rp.phoenix_masks(df.dropna(subset=["O", "H", "L", "C", "V"]))["LONG"].reindex(df.index, fill_value=False)
        out[("PHOENIX", "LONG")] = p.values
        cm = rp.cta_masks(df, ticker)
        out[("PERSEPHONE", "LONG")] = cm["PERSEPHONE"].values
        out[("PHAETHON", "SHORT")] = cm["PHAETHON"].values
        m8 = r8.masks(df, ticker)
        out[("SISYPHUS", "SHORT")] = m8[("SISYPHUS", "SHORT")].values
        out[("MIDAS", "LONG")] = m8[("MIDAS", "LONG")].values
        out[("HECTOR", "LONG")] = m8[("HECTOR", "LONG")].values
        ci = circe_mask(df)
        out[("CIRCE", "LONG")] = ci["LONG"]
        out[("CIRCE", "SHORT")] = ci["SHORT"]
    return out


def fires(pull_path, themed_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    assert not os.listdir(out_dir), "out_dir must be empty"
    assert_groups()
    started = datetime.now(timezone.utc)
    data, cal = frames_from_pull(pull_path)
    u = universes()
    seed = in_seed(cal)
    rows = []
    nemesis_skipped = 0
    for t in sorted(set(u["proxy"]) | set(u["registered"])):
        if t not in data:
            continue
        df = data[t]
        which = (["proxy"] if t in u["proxy"] else [])
        for (strat, side), m in strategy_masks(df, t, which).items():
            m = np.asarray(m, bool) & seed
            for i in np.flatnonzero(m):
                rows.append({"strategy": strat, "signal_type": STRATEGIES[strat][0], "side": side,
                             "ticker": t, "date": cal[i].date(), "universe": "proxy", "bars": "pull"})
        if t in u["registered"]:
            m, sk = nemesis_mask(df)
            nemesis_skipped += sk
            for i in np.flatnonzero(m & seed):
                rows.append({"strategy": "NEMESIS", "signal_type": "WRR_LONG", "side": "LONG", "ticker": t,
                             "date": cal[i].date(), "universe": "registered_shadow.UNIVERSE", "bars": "pull"})
    # HYPNOS-LELEDC: protocol 1's detector on its own data and main arm
    frames, themes, tcal = HL.load_equity(themed_path)
    arms = HL.arms_from_themes(themes)
    tseed = in_seed(tcal)
    for t in arms["main"]:
        f = frames[t]
        have = f[["open", "high", "low", "close"]].notna().all(axis=1)
        g = f[have]
        if len(g) < HL.BURN_IN:
            continue
        det = HL.detect(g.open.values, g.high.values, g.low.values, g.close.values)
        pos = np.flatnonzero(have.values)
        for key, side in (("sig_bear", "SHORT"), ("sig_bull", "LONG")):
            for k in np.flatnonzero(det[key]):
                p = pos[k]
                if tseed[p]:
                    rows.append({"strategy": "HYPNOS-LELEDC", "signal_type": "EXHAUSTION_BEAR" if side == "SHORT"
                                 else "EXHAUSTION_BULL", "side": side, "ticker": t, "date": tcal[p].date(),
                                 "universe": "protocol-1 main arm (250)", "bars": "themed"})
    fr = pd.DataFrame(rows).sort_values(["strategy", "date", "ticker", "side"]).reset_index(drop=True)
    fpath = os.path.join(out_dir, "fires.csv")
    fr.to_csv(fpath, index=False)
    counts = (fr.groupby("strategy").agg(fires=("ticker", "size"), dates=("date", "nunique"))
              .reindex(list(STRATEGIES)).fillna(0).astype(int))
    meta = {"copy_of_record": COPY_OF_RECORD, "copy_sha256": COPY_SHA256,
            "inputs": {"pull": {"file": os.path.basename(pull_path), "sha256": sha256(pull_path)},
                       "themed": {"file": os.path.basename(themed_path), "sha256": sha256(themed_path)}},
            "fires_csv_sha256": sha256(fpath), "window": [str(SEED_FIRST), str(SEED_LAST)],
            "fire_counts": counts.reset_index().to_dict("records"),
            "not_replayable_do_not_enter": NOT_REPLAYABLE,
            "nemesis_ticker_sessions_not_replayed_on_or_after_2026_10_12": nemesis_skipped,
            "universe_reading": "LAB's reading, flagged for SPINE (see module doc)",
            "universes": {"proxy": len(u["proxy"]), "registered": len(u["registered"]),
                          "proxy_with_bars": sum(t in data for t in u["proxy"]),
                          "registered_with_bars": sum(t in data for t in u["registered"]),
                          "hypnos_main": len(arms["main"])},
            "outcome_free": "no return, price or label column is written",
            "started_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "finished_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    with open(os.path.join(out_dir, "fires_meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1, default=str)
    return meta


# ── grade (QUERY) ─────────────────────────────────────────────────────────────────────────
def read_labels(path):
    lab = pd.read_csv(path, dtype={"shown_regime": "string"})
    assert list(lab.columns[:2]) == ["as_of", "shown_regime"], list(lab.columns)
    lab["as_of"] = pd.to_datetime(lab["as_of"]).dt.date
    assert lab.as_of.is_unique, "one row per session (superseded = false)"
    assert len(lab) == SEED_ROWS and lab.as_of.min() == SEED_FIRST and lab.as_of.max() == SEED_LAST, \
        (len(lab), lab.as_of.min(), lab.as_of.max())
    bad = set(lab.shown_regime.dropna()) - set(REGIME_TO_GROUP)
    assert not bad, f"unknown regime keys {bad}"
    return dict(zip(lab.as_of, lab.shown_regime))


def grade_rows(fr, data, themed, h):
    """Per-fire h-session returns: next-open entry, exit at session h's close (entry = session 1)."""
    out = []
    for (src, t), g in fr.groupby(["bars", "ticker"]):
        if src == "pull":
            df, spy = data[t], data["SPY"]
            o, c, adj, so, sc, sadj = df.rO, df.rC, df.C, spy.rO, spy.rC, spy.C
        else:
            df, spy = themed[t], themed["SPY"]
            o, c, adj, so, sc, sadj = df.open, df.close, df.adj_close, spy.open, spy.close, spy.adj_close
        badj, flag = HL.beta_adj(adj, sadj)
        pos = {d: i for i, d in enumerate(df.index.date)}
        ov, cv, sov, scv = o.values, c.values, so.values, sc.values
        for _, r in g.iterrows():
            p = pos[r["date"]]
            e, x = p + 1, p + h
            sign = -1.0 if r["side"] == "SHORT" else 1.0
            if x >= len(df) or any(v != v for v in (ov[e], cv[x], sov[e], scv[x])):
                out.append({**r, "gradeable": False})
                continue
            rr, rs_ = cv[x] / ov[e] - 1, scv[x] / sov[e] - 1
            out.append({**r, "gradeable": True, "r": sign * rr, "r_adj": sign * (rr - badj.values[p] * rs_),
                        "spy_signed": sign * rs_, "beta_flagged": bool(flag.values[p])})
    return pd.DataFrame(out)


def strategy_result(gr, home):
    g = gr[gr.gradeable & gr.group.notna()]
    inn, out = g[g.group == home], g[g.group != home]
    res = {"home": home, "n_in": int(len(inn)), "dates_in": int(inn.date.nunique()),
           "n_out": int(len(out)), "dates_out": int(out.date.nunique()),
           "mean_in_pct": round(100 * inn.r_adj.mean(), 4) if len(inn) else None,
           "mean_out_pct": round(100 * out.r_adj.mean(), 4) if len(out) else None,
           "raw_in_minus_out_pct": (round(100 * (inn.r.mean() - out.r.mean()), 4) if len(inn) and len(out) else None),
           "spy_in_minus_out_pct": (round(100 * (inn.spy_signed.mean() - out.spy_signed.mean()), 4)
                                    if len(inn) and len(out) else None)}
    if res["dates_in"] < MIN_HOME_DATES or res["dates_out"] < 2:
        res.update({"diff_pct": None, "t": None, "p": None, "status": "INSUFFICIENT"})
        return res
    st = S.diff_t_clustered(g.r_adj.values, (g.group == home).astype(float).values, g.date.astype(str).values)
    b, se, t, G = st
    res.update({"diff_pct": round(100 * b, 4), "se_pct": round(100 * se, 4), "t": round(t, 3),
                "clusters": G, "p": S.t_sf_two_sided(t, G - 1), "status": "TESTED"})
    return res


def grade(fires_path, pull_path, themed_path, labels_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    assert not os.listdir(out_dir), "out_dir must be empty"
    assert_groups()
    labels = read_labels(labels_path)
    fr = pd.read_csv(fires_path)
    fr["date"] = pd.to_datetime(fr["date"]).dt.date
    data, _ = frames_from_pull(pull_path)
    themed, _, _ = HL.load_equity(themed_path)
    gr = grade_rows(fr, data, themed, H_PRIMARY)
    gr["regime"] = gr.date.map(labels)
    gr["no_label_row"] = ~gr.date.isin(set(labels))
    gr["group"] = gr.regime.map(lambda r: REGIME_TO_GROUP.get(r) if isinstance(r, str) else None)
    results, pvals = {}, []
    for name, (stype, side, home, prior, ch, ch_src) in STRATEGIES.items():
        g = gr[gr.strategy == name]
        r = strategy_result(g, home) if len(g) else {"home": home, "status": "NO FIRES"}
        r.update({"signal_type": stype, "prior_seen": prior, "fires": int(len(g)),
                  "universe": (", ".join(sorted(g.universe.astype(str).unique())) if len(g) else None),
                  "universe_basis": UNIVERSE_BASIS.get(name),
                  "ungradeable": int((~g.gradeable).sum()) if len(g) else 0,
                  "null_label": int((g.gradeable & g.group.isna() & ~g.no_label_row).sum()) if len(g) else 0,
                  "no_label_row": int(g.no_label_row.sum()) if len(g) else 0,
                  "group_counts": g[g.gradeable].group.fillna("NULL").value_counts().to_dict() if len(g) else {}})
        results[name] = r
    entering = [n for n, r in results.items() if r["fires"] > 0]
    adj = S.holm([results[n].get("p") for n in entering])
    for n, a in zip(entering, adj):
        r = results[n]
        r["holm_p"] = a
        if r["status"] != "TESTED":
            r["verdict"] = r["status"]
        else:
            guard = r["spy_in_minus_out_pct"] is not None and r["diff_pct"] > r["spy_in_minus_out_pct"]
            r["beta_guard_passed"] = bool(guard)
            r["verdict"] = "PASS" if (a < ALPHA and r["t"] >= T_PASS and guard) else "NO PASS"
        if r["prior_seen"]:
            r["tag"] = "PRIOR-SEEN: a pass cannot support a gate ruling without a later forward look"
    sec = {}
    for name, (_, _, home, _, ch, ch_src) in STRATEGIES.items():
        g = fr[fr.strategy == name]
        if ch is None or g.empty:
            sec[name] = {"horizon": None, "source": ch_src}
            continue
        gh = grade_rows(g, data, themed, ch)
        gh["group"] = gh.date.map(labels).map(lambda r: REGIME_TO_GROUP.get(r) if isinstance(r, str) else None)
        sec[name] = {"horizon": ch, "source": ch_src, **strategy_result(gh, home),
                     "weight": "none; outside the Holm family (R-IV.1201(c)2)"}
    gr.to_csv(os.path.join(out_dir, "graded_fires.csv.gz"), index=False, compression="gzip")
    out = {"copy_of_record": COPY_OF_RECORD, "copy_sha256": COPY_SHA256,
           "inputs": {k: {"file": os.path.basename(p), "sha256": sha256(p)} for k, p in
                      (("fires", fires_path), ("pull", pull_path), ("themed", themed_path), ("labels", labels_path))},
           "k_holm_family": len(entering), "family": entering, "alpha": ALPHA,
           "primary_h5": results, "secondary_card_horizon": sec,
           "not_replayable_do_not_enter": NOT_REPLAYABLE,
           "grade_source_B": "QUERY counts DB grades written after ce46628's deploy separately (count only); "
                             "the Triton seal does NOT apply to signals / signal_outcomes (R-IV.1205(b))",
           "finished_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, default=str)
    return out


def p1_label_counts(signals_path, labels_path):
    """Protocol 1 §6 (QUERY): labelled vs unlabelled counts per arm, kind and group. Counts only."""
    labels = read_labels(labels_path)
    s = pd.read_csv(signals_path)
    s["date"] = pd.to_datetime(s["date"]).dt.date
    j = s.label_status == "JOIN"
    s.loc[j, "regime"] = s.loc[j, "date"].map(labels)
    s["group"] = s["regime"].map(lambda r: REGIME_TO_GROUP.get(r) if isinstance(r, str) else None)
    s["status"] = np.where(~j, s.label_status,
                           np.where(s.group.notna(), "LABELLED", np.where(s.date.isin(set(labels)),
                                                                          "NULL label", "no label row")))
    out = s.groupby(["arm", "kind", "status", s.group.fillna("-")]).size().rename("n").reset_index()
    return out.rename(columns={"group": "group"})


# ── selftest (synthetic only) ─────────────────────────────────────────────────────────────
def selftest():
    ok = fail = 0

    def check(name, cond):
        nonlocal ok, fail
        ok, fail = ok + bool(cond), fail + (not cond)
        print(("PASS " if cond else "FAIL ") + name)

    assert_groups()
    check("10 regime keys, each in exactly one group", len(REGIME_TO_GROUP) == 10)
    check("every home is a declared group", all(v[2] in GROUPS for v in STRATEGIES.values()))
    check("PRIOR-SEEN tags: HECTOR, MIDAS, SISYPHUS only (ACHILLES / ARTEMIS do not enter)",
          sorted(n for n, v in STRATEGIES.items() if v[3]) == ["HECTOR", "MIDAS", "SISYPHUS"])
    # synthetic grading: 30 home dates with +1%, 30 out dates with 0%, SPY flat -> PASS
    rng = np.random.default_rng(3)
    rows = []
    d0 = date(2025, 9, 1)
    for i in range(60):
        home = i < 30
        rows.append({"date": d0 + pd.Timedelta(days=i), "gradeable": True,
                     "group": "RANGE" if home else "TREND-UP",
                     "r_adj": (0.01 if home else 0.0) + 0.002 * rng.standard_normal(),
                     "r": 0.01 if home else 0.0, "spy_signed": 0.0})
    gr = pd.DataFrame(rows)
    gr["date"] = gr.date.map(lambda x: x.date() if hasattr(x, "date") else x)
    r = strategy_result(gr, "RANGE")
    check("in-home edge: TESTED with t > 2", r["status"] == "TESTED" and r["t"] > 2)
    check("diff = mean in - mean out", abs(r["diff_pct"] - (r["mean_in_pct"] - r["mean_out_pct"])) < 1e-3)
    r2 = strategy_result(gr[gr.group == "TREND-UP"].append(gr[gr.group == "RANGE"].head(10))
                         if hasattr(gr, "append") else pd.concat([gr[gr.group == "TREND-UP"], gr[gr.group == "RANGE"].head(10)]),
                         "RANGE")
    check("< 20 home dates -> INSUFFICIENT", r2["status"] == "INSUFFICIENT")
    # beta guard: same edge but SPY moved +2% more in home -> guard fails
    gr3 = gr.copy()
    gr3.loc[gr3.group == "RANGE", "spy_signed"] = 0.02
    r3 = strategy_result(gr3, "RANGE")
    check("beta guard input: SPY in - out = +2%", abs(r3["spy_in_minus_out_pct"] - 2.0) < 1e-9)
    check("beta guard would fail (diff < SPY's)", r3["diff_pct"] < r3["spy_in_minus_out_pct"])
    # NULL labels are excluded
    gr4 = gr.copy()
    gr4.loc[:4, "group"] = None
    r4 = strategy_result(gr4, "RANGE")
    check("NULL-label fires are excluded from in/out", r4["n_in"] == 25)
    # labels validation
    import tempfile
    days = pd.bdate_range(SEED_FIRST, SEED_LAST)[:SEED_ROWS]
    tmp = tempfile.mkdtemp()
    p = os.path.join(tmp, "labels.csv")
    lab = pd.DataFrame({"as_of": list(days.date[:-1]) + [SEED_LAST],
                        "shown_regime": ["uptrend"] * (SEED_ROWS - 1) + [None]})
    lab.to_csv(p, index=False)
    m = read_labels(p)
    check("labels: 302 unique rows, first 2025-08-06, last 2026-10-16, NULL kept", len(m) == SEED_ROWS)
    lab2 = pd.concat([lab, lab.tail(1)])
    lab2.to_csv(p, index=False)
    try:
        read_labels(p)
        dup_ok = False
    except AssertionError:
        dup_ok = True
    check("labels: a duplicated as_of (both generations mixed) is refused", dup_ok)
    lab3 = lab.copy()
    lab3.loc[0, "shown_regime"] = "sideways"
    lab3.to_csv(p, index=False)
    try:
        read_labels(p)
        key_ok = False
    except AssertionError:
        key_ok = True
    check("labels: an unknown regime key is refused", key_ok)
    # grade_rows: sign, entry next open, exit session-h close, ungradeable at the end
    cal = pd.bdate_range("2025-01-01", periods=300)
    px = pd.DataFrame({"O": 1.0, "H": 1.0, "L": 1.0, "C": np.linspace(100, 130, 300), "V": 1.0,
                       "rO": np.linspace(100, 130, 300), "rC": np.linspace(100, 130, 300) + 0.5}, index=cal)
    data = {"AAA": px, "SPY": px.copy()}
    fr = pd.DataFrame({"strategy": ["X", "X", "X"], "side": ["LONG", "SHORT", "LONG"], "ticker": "AAA",
                       "date": [cal[100].date(), cal[100].date(), cal[297].date()], "bars": "pull"})
    g = grade_rows(fr, data, {}, 5)
    e, x = 101, 105
    exp = px.rC.iat[x] / px.rO.iat[e] - 1
    check("grade: r = close[t+5] / open[t+1] - 1", abs(g.r.iat[0] - exp) < 1e-12)
    check("grade: SHORT is sign-flipped", abs(g.r.iat[1] + exp) < 1e-12)
    check("grade: beyond the data -> ungradeable", not bool(g.gradeable.iat[2]))
    check("grade: ticker == SPY -> r_adj ~ 0 (beta 1)", abs(g.r_adj.iat[0]) < 1e-9)
    # NEMESIS cutoff: the rule is never evaluated on a session >= 2026-10-12
    cal2 = pd.bdate_range("2025-01-01", "2026-10-16")
    rng2 = np.random.default_rng(5)
    c = 100 * np.exp(np.cumsum(0.01 * rng2.standard_normal(len(cal2))))
    df = pd.DataFrame({"O": c * 1.001, "H": c * 1.01, "L": c * 0.99, "C": c, "V": 1e6}, index=cal2)
    m, sk = nemesis_mask(df)
    check("NEMESIS: no fire on or after 2026-10-12", not m[cal2.date >= NEMESIS_CUTOFF].any())
    check("NEMESIS: the skipped sessions are counted", sk == int((cal2.date >= NEMESIS_CUTOFF).sum()) and sk > 0)
    # CIRCE: a clean failed breakout up, confirmed on the 2nd bar, fires SHORT that day only
    n = 300
    cal3 = pd.bdate_range("2025-06-02", periods=n)
    base = np.full(n, 100.0)
    hi, lo, cl = base + 1, base - 1, base.copy()
    j = 200
    assert SEED_FIRST <= cal3[j + 1].date() <= SEED_LAST
    hi[j], cl[j] = 105.0, 102.0                 # breach and close outside the 20-bar high (101)
    hi[j + 1], cl[j + 1] = 103.0, 100.5          # back inside: confirmation on bar 2
    df3 = pd.DataFrame({"O": cl, "H": hi, "L": lo, "C": cl, "V": 1e6}, index=cal3)
    ci = circe_mask(df3)
    check("CIRCE: SHORT fires on the confirmation bar", ci["SHORT"][j + 1] and ci["SHORT"].sum() == 1)
    check("CIRCE: no LONG", ci["LONG"].sum() == 0)
    # END TO END grade() on synthetic files only
    tmp2 = tempfile.mkdtemp()
    eq, _, _ = HL.synthetic_files(tmp2)
    th = pd.read_parquet(eq)
    pull_p = os.path.join(tmp2, "pull.parquet")
    th[th.ticker.isin(["SPY", "AAA", "BBB"])].drop(columns="theme").to_parquet(pull_p, index=False)
    days = [d for d in pd.to_datetime(th[th.ticker == "SPY"].date).dt.date if SEED_FIRST <= d <= SEED_LAST]
    lab = pd.DataFrame({"as_of": days, "shown_regime": [("range_chop" if i % 3 == 0 else "uptrend") if i % 17
                                                        else None for i in range(len(days))]})
    lab = lab.iloc[:SEED_ROWS - 1]
    lab = pd.concat([lab, pd.DataFrame({"as_of": [SEED_LAST], "shown_regime": ["uptrend"]})]).drop_duplicates("as_of")
    lab = lab.iloc[-SEED_ROWS:] if len(lab) >= SEED_ROWS else lab
    lab_p = os.path.join(tmp2, "labels.csv")
    lab.to_csv(lab_p, index=False)
    if len(lab) == SEED_ROWS:
        fr_rows = []
        for i, d in enumerate(days[:-10]):
            fr_rows.append({"strategy": "CIRCE", "signal_type": "CIRCES_STEW", "side": "SHORT" if i % 2 else "LONG",
                            "ticker": "AAA", "date": d, "universe": "proxy", "bars": "pull"})
            fr_rows.append({"strategy": "HYPNOS-LELEDC", "signal_type": "EXHAUSTION_BULL", "side": "LONG",
                            "ticker": "BBB", "date": d, "universe": "main", "bars": "themed"})
        fires_p = os.path.join(tmp2, "fires.csv")
        pd.DataFrame(fr_rows).to_csv(fires_p, index=False)
        res = grade(fires_p, pull_p, eq, lab_p, os.path.join(tmp2, "g"))
        c_ = res["primary_h5"]["CIRCE"]
        check("e2e grade: CIRCE tested, Holm family = the two strategies with fires",
              c_["status"] == "TESTED" and res["k_holm_family"] == 2 and "verdict" in c_)
        check("e2e grade: NULL-label fires are counted", c_["null_label"] > 0)
        check("e2e grade: strategies without fires report NO FIRES", res["primary_h5"]["MIDAS"]["status"] == "NO FIRES")
        check("e2e grade: each strategy's universe is labelled (R-IV.1241(b)1)",
              c_["universe"] == "proxy" and c_["universe_basis"].startswith("census proxy")
              and set(UNIVERSE_BASIS) == set(STRATEGIES))
        check("e2e grade: the card-horizon secondary is outside Holm (CIRCE h1)",
              res["secondary_card_horizon"]["CIRCE"]["horizon"] == 1)
        sig = pd.DataFrame({"arm": ["main", "main", "crypto", "crypto"], "ticker": "X",
                            "date": [days[0], days[16], days[1], date(2025, 1, 2)],
                            "kind": "signal", "side": "BEAR",
                            "label_status": ["JOIN", "JOIN", "NO LABEL (no US session)", "NO LABEL (pre-seed)"]})
        sp = os.path.join(tmp2, "sig.csv")
        sig.to_csv(sp, index=False)
        lc = p1_label_counts(sp, lab_p)
        st_ = dict(zip(lc.status, lc.n))
        check("p1 label counts: LABELLED / NULL / NO LABEL kept apart",
              st_.get("LABELLED") == 1 and st_.get("NULL label") == 1
              and st_.get("NO LABEL (no US session)") == 1 and st_.get("NO LABEL (pre-seed)") == 1)
    else:
        check("e2e grade: synthetic label file has 302 rows", False)
    print(f"{ok}/{ok + fail}")
    return fail == 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["selftest"]:
        sys.exit(0 if selftest() else 1)
    if a[:1] == ["pull"] and len(a) == 2:
        print(json.dumps(pull(a[1]), indent=1))
        sys.exit(0)
    if a[:1] == ["fires"] and len(a) == 4:
        print(json.dumps(fires(*a[1:4]), indent=1, default=str))
        sys.exit(0)
    if a[:1] == ["p1-label-counts"] and len(a) == 3:
        print(p1_label_counts(a[1], a[2]).to_string(index=False))
        sys.exit(0)
    if a[:1] == ["grade"] and len(a) == 6:
        out = grade(*a[1:6])
        print(json.dumps({"written": a[5], "finished": out["finished_utc"]}))
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
