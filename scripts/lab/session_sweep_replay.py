"""Session_Sweep round 2 (R-IV.1027(c)) -- replay of the live rule on Binance BTCUSDT 5m bars.

RUN-OFF check feeding the 10-30 crypto table; a pass promotes nothing (freeze to 2027-03-31); QUERY
re-computes before anything is cited. Declarations: lab\\crypto-replay\\06-ROUND2-DECLARATIONS.md
(9b99d1fe...), stamped 2026-10-15 01:29:11 UTC before any download or code.

The rule is backend/strategies/crypto_setups.py:232-341 (check_session_sweep) and :434-472
(_check_btc_regime, AS CODED -- it reads the OLDEST 15 of 24 hourly candles; a known defect, not fixed
during the run-off, R-IV.1027(c)4). The parity self-test runs the hub's own functions against this
detector on synthetic days.

Usage:
  python -I scripts/lab/session_sweep_replay.py run <perp_parquet> <spot_parquet> <out_dir>
  python -I scripts/lab/session_sweep_replay.py selftest
"""
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from crypto_replay import hac_t, plain_t, P_ONE_SIDED_T2  # noqa: E402  same statistics as round 1

DECLARATIONS = "06-ROUND2-DECLARATIONS.md 9b99d1fe23f8962f748e3437e24316b976812136368059486f86dab934c1ca25"
BARS_PER_DAY = 288
ASIA_BARS = 96                                    # 00:00 .. 07:55 UTC opens
INSTANTS = list(range(95, 119)) + list(range(155, 179))   # bar j ends at t = (j+1)*5 min: 08:00..09:55, 13:00..14:55
SWEEP = 0.001
MIN_RANGE_PCT = 0.5
COOLDOWN_S = 30 * 60
HORIZONS = {"1h": 12, "4h": 48}                   # exit = close of bar j + n (entry = open of bar j + 1)
HAC_LAGS = 1
FLOOR_FIRES, FLOOR_DATES = 30, 20
BEAR = {"perp": {2022}, "spot": {2018, 2022}}
LABEL = {"perp": "Binance perp 5m, completed bars; live reads OKX swap with the forming bar.",
         "spot": "Binance spot 5m, completed bars; live reads OKX swap with the forming bar."}
STATUS = "RUN-OFF check (10-30 crypto table); a pass promotes nothing; freeze to 2027-03-31; QUERY re-computes before citation"
REGIME_NOTE = ("regime filter AS CODED (reads hourly candles 1-14 of 24, the OLDEST; known defect, "
               "not fixed during the run-off, R-IV.1027(c)4)")


# ── data ────────────────────────────────────────────────────────────────────────────────────────
def load_grid(parquet):
    """5m bars -> per-UTC-day arrays (ndays, 288) of O/H/L/C plus a presence mask."""
    df = pd.read_parquet(parquet)
    t = pd.to_datetime(df.open_time_utc, utc=True)
    day0 = t.min().normalize()
    k = ((t - day0) // pd.Timedelta(minutes=5)).astype("int64").values
    nd = int(k.max() // BARS_PER_DAY + 1)
    G = {c: np.full(nd * BARS_PER_DAY, np.nan) for c in ("o", "h", "l", "c")}
    for c, src in zip(("o", "h", "l", "c"), ("open", "high", "low", "close")):
        G[c][k] = df[src].values.astype(float)
    G = {c: v.reshape(nd, BARS_PER_DAY) for c, v in G.items()}
    G["present"] = ~np.isnan(G["c"])
    G["days"] = [(day0 + pd.Timedelta(days=i)).date() for i in range(nd)]
    G["epoch0"] = int(day0.timestamp())
    return G


def hourly(G):
    """Hourly candles aggregated from 5m bars, as one flat series (nd*24)."""
    nd = len(G["days"])
    sh = (nd * 24, 12)
    o, h, l, c = (G[x].reshape(sh) for x in ("o", "h", "l", "c"))
    ok = G["present"].reshape(sh).all(axis=1)
    return {"o": o[:, 0], "h": h.max(axis=1), "l": l.min(axis=1), "c": c[:, -1], "ok": ok}


def regime_label(Hr, hg):
    """_check_btc_regime on the 24 hourly candles hg-23 .. hg (oldest first), AS CODED."""
    idx = list(range(hg - 23, hg + 1))
    if idx[0] < 1:
        return "UNKNOWN"
    trs = []
    for i in range(1, min(15, len(idx))):
        a, p = idx[i], idx[i - 1]
        hi, lo, pc = Hr["h"][a], Hr["l"][a], Hr["c"][p]
        trs.append(max(hi - lo, abs(hi - pc), abs(lo - pc)))
    cur = sum(trs[-7:]) / 7 if len(trs) >= 7 else sum(trs) / len(trs)
    avg = sum(trs) / len(trs)
    ratio = cur / avg if avg > 0 else 1.0
    return "QUIET" if ratio < 0.5 else "VOLATILE" if ratio > 2.0 else "TRENDING" if ratio > 1.3 else "RANGING"


def regime_hours_ok(Hr, hg):
    return hg - 23 >= 0 and bool(Hr["ok"][hg - 23: hg - 23 + 15].all())


def asia(G, d):
    ah, al = float(np.max(G["h"][d, :ASIA_BARS])), float(np.min(G["l"][d, :ASIA_BARS]))
    return ah, al, ((ah - al) / al * 100 if al > 0 else 0.0)


def day_status(G, d):
    """'gap' / 'narrow' / 'ok' per declarations sec. 4."""
    if d < 1 or not (G["present"][d].all() and G["present"][d - 1].all()):
        return "gap"
    return "narrow" if asia(G, d)[2] < MIN_RANGE_PCT else "ok"


# ── detector ────────────────────────────────────────────────────────────────────────────────────
def detect_at(G, d, j, ah, al):
    """check_session_sweep's decision at the close of bar j (no cooldown): 'SHORT' / 'LONG' / None."""
    last = G["c"][d, j]
    w = slice(j - 11, j + 1)
    if last < ah and bool((G["h"][d, w] > ah * (1 + SWEEP)).any()):
        return "SHORT"
    if last > al and bool((G["l"][d, w] < al * (1 - SWEEP)).any()):
        return "LONG"
    return None


def fires(G, Hr, regime_on=True, days=None):
    """Every fire on evaluable days, with the 30-min per-direction cooldown in replay time."""
    out, last_fired = [], {}
    for d in (days if days is not None else range(len(G["days"]))):
        if day_status(G, d) != "ok":
            continue
        ah, al, _ = asia(G, d)
        for j in INSTANTS:
            t = G["epoch0"] + d * 86400 + (j + 1) * 300
            reg = None
            if regime_on:
                hg = d * 24 + ((j + 1) * 5) // 60
                if not regime_hours_ok(Hr, hg):
                    continue
                reg = regime_label(Hr, hg)
                if reg in ("QUIET", "VOLATILE"):
                    continue
            side = detect_at(G, d, j, ah, al)
            if side is None:
                continue
            if not (t - last_fired.get(side, -1e18) > COOLDOWN_S):
                continue
            last_fired[side] = t
            out.append({"d": d, "date": G["days"][d], "j": j, "t": t, "side": side, "regime": reg,
                        "asia_high": ah, "asia_low": al})
    F = pd.DataFrame(out)
    if len(F):
        F["first_of_day"] = ~F.duplicated("d")
    return F


def raw_ret(G, d, j, n):
    return G["c"][d, j + n] / G["o"][d, j + 1] - 1


def bracket(G, d, j, side, ah, al):
    mid = al + (ah - al) * 0.5
    for b in range(j + 1, BARS_PER_DAY):
        hi, lo = G["h"][d, b], G["l"][d, b]
        if side == "SHORT":
            stop, tgt = hi >= ah * (1 + SWEEP * 2), lo <= mid
        else:
            stop, tgt = lo <= al * (1 - SWEEP * 2), hi >= mid
        if stop:
            return "stop"
        if tgt:
            return "target"
    return "open"


# ── baselines ───────────────────────────────────────────────────────────────────────────────────
def baselines(G, days):
    """B1[(j, h)] = mean raw return entered at clock j over the days; B2[h] = mean revert-to-mid return."""
    B1, B2 = {}, {}
    for h, n in HORIZONS.items():
        R = np.array([[raw_ret(G, d, j, n) for j in INSTANTS] for d in days]) if days else np.empty((0, len(INSTANTS)))
        for k, j in enumerate(INSTANTS):
            B1[(j, h)] = float(R[:, k].mean()) if len(R) else np.nan
        vals = []
        for d in days:
            ah, al, _ = asia(G, d)
            mid = al + (ah - al) * 0.5
            for j in INSTANTS:
                last = G["c"][d, j]
                w = slice(j - 11, j + 1)
                if not (al < last < ah) or last == mid:
                    continue
                if bool((G["h"][d, w] > ah * (1 + SWEEP)).any()) or bool((G["l"][d, w] < al * (1 - SWEEP)).any()):
                    continue
                vals.append((1.0 if last < mid else -1.0) * raw_ret(G, d, j, n))
        B2[h] = float(np.mean(vals)) if vals else np.nan
    return B1, B2


# ── cells ───────────────────────────────────────────────────────────────────────────────────────
def split_days(G, source, split):
    ok = [d for d in range(len(G["days"])) if day_status(G, d) == "ok"]
    yr = lambda d: G["days"][d].year  # noqa: E731
    if split == "bear":
        return [d for d in ok if yr(d) in BEAR[source]]
    if split == "bull":
        return [d for d in ok if yr(d) not in BEAR[source]]
    return ok


def cell_rows(G, F, source, label_extra="", only_first=True, side=None, is_cell=True):
    rows = []
    for split in ("bear", "bull", "ALL"):
        days = split_days(G, source, split)
        dset = set(days)
        B1, B2 = baselines(G, days)
        sub = F[F.d.isin(dset)] if len(F) else F
        if len(sub) and only_first:
            sub = sub[sub.first_of_day]
        if len(sub) and side:
            sub = sub[sub.side == side]
        for h, n in HORIZONS.items():
            r = np.array([(-1 if s == "SHORT" else 1) * raw_ret(G, d, j, n)
                          for d, j, s in zip(sub.d, sub.j, sub.side)]) if len(sub) else np.array([])
            b1 = np.array([(-1 if s == "SHORT" else 1) * B1[(j, h)] for j, s in zip(sub.j, sub.side)]) if len(sub) else np.array([])
            d1, d2 = r - b1, r - B2[h]
            n_f, n_d = int(len(sub)), int(sub.d.nunique()) if len(sub) else 0
            below = n_f < FLOOR_FIRES or n_d < FLOOR_DATES
            row = {"source": source, "h": h, "split": split, "n_fires": n_f, "n_dates": n_d,
                   "n_evaluable_days": len(days), "mean_return": float(r.mean()) if n_f else None,
                   "B2_revert_no_sweep": B2[h], "diff_B1": float(d1.mean()) if n_f else None,
                   "t_hac_B1": hac_t(d1, HAC_LAGS) if n_f else None, "t_plain_B1": plain_t(d1) if n_f else None,
                   "diff_B2": float(d2.mean()) if n_f else None,
                   "t_hac_B2": hac_t(d2, HAC_LAGS) if n_f else None, "t_plain_B2": plain_t(d2) if n_f else None,
                   "is_cell": is_cell and split in ("bear", "bull"), "below_floor": below,
                   "label": LABEL[source] + (" " + label_extra if label_extra else ""), "status": STATUS}
            if is_cell and split == "bear":
                ok = (not below and row["diff_B1"] > 0 and (row["t_hac_B1"] or 0) >= 2.0
                      and row["diff_B2"] > 0 and (row["t_hac_B2"] or 0) >= 2.0)
                row["verdict"] = "below floor - cannot pass" if below else "PASS" if ok else "no pass"
            else:
                row["verdict"] = "bull - no pass defined" if split == "bull" and is_cell else \
                    "sensitivity - cannot pass" if not is_cell else "context"
            rows.append(row)
    return rows


def pass_summary(V):
    from math import comb
    n, k, p = int(len(V)), int((V.verdict == "PASS").sum()), P_ONE_SIDED_T2
    tail = sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1)) if n else None
    label = "no pass" if k == 0 else "consistent with chance (unless QUERY's re-computation says otherwise)" \
        if k == 1 else "reported without a label; SPINE reads the count against the bound"
    return {"passes": k, "eligible_cells": n, "total_cells": 2 * n, "written": f"{k} of {n} eligible ({2 * n} cells)",
            "chance_expected_upper_bound": round(n * p, 3),
            "p_at_least_k_binomial": round(float(tail), 4) if tail is not None else None,
            "binomial_note": ("assumes independent cells; the cells are correlated (shared days, two horizons, "
                              "PERP and SPOT overlap 2020-2026), so this understates the tail"),
            "label": label}


def data_quality(G, source):
    st = pd.DataFrame({"year": [d.year for d in G["days"]],
                       "status": [day_status(G, i) for i in range(len(G["days"]))]})
    q = st.groupby(["year", "status"]).size().unstack(fill_value=0).reset_index()
    q.insert(0, "source", source)
    return q


def run(perp_parquet, spot_parquet, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    cells, sens, brk, dq, meta_src = [], [], [], [], {}
    for source, path in (("perp", perp_parquet), ("spot", spot_parquet)):
        G = load_grid(path)
        Hr = hourly(G)
        F = fires(G, Hr, regime_on=True)
        F0 = fires(G, Hr, regime_on=False)
        cells += cell_rows(G, F, source)
        sens += cell_rows(G, F0, source, "SENSITIVITY: regime filter off.", is_cell=False)
        for s in ("LONG", "SHORT"):
            sens += cell_rows(G, F, source, f"SENSITIVITY: {s} only.", side=s, is_cell=False)
        sens += cell_rows(G, F, source, "SENSITIVITY: all fires, not first per day.", only_first=False, is_cell=False)
        if len(F):
            F["bracket"] = [bracket(G, d, j, s, a, b) for d, j, s, a, b in
                            zip(F.d, F.j, F.side, F.asia_high, F.asia_low)]
            F["split"] = ["bear" if dt.year in BEAR[source] else "bull" for dt in F.date]
            b = F[F.first_of_day].groupby(["split", "side", "bracket"]).size().rename("first_fires").reset_index()
            b.insert(0, "source", source)
            b["label"] = LABEL[source] + " DESCRIPTIVE ONLY."
            brk.append(b)
        dq.append(data_quality(G, source))
        meta_src[source] = {"parquet": path, "parquet_sha256": hashlib.sha256(open(path, "rb").read()).hexdigest(),
                            "first_day": str(G["days"][0]), "last_day": str(G["days"][-1]),
                            "fires_all": int(len(F)), "fire_days": int(F.d.nunique()) if len(F) else 0,
                            "fires_regime_off": int(len(F0))}
    C = pd.DataFrame(cells)
    V = C[C.is_cell & (C.split == "bear")][["source", "h", "split", "n_fires", "n_dates", "diff_B1", "t_hac_B1",
                                            "diff_B2", "t_hac_B2", "verdict"]]
    C.to_csv(os.path.join(out_dir, "cells.csv"), index=False)
    V.to_csv(os.path.join(out_dir, "verdicts.csv"), index=False)
    pd.DataFrame(sens).to_csv(os.path.join(out_dir, "sensitivity.csv"), index=False)
    (pd.concat(brk) if brk else pd.DataFrame()).to_csv(os.path.join(out_dir, "bracket.csv"), index=False)
    pd.concat(dq).to_csv(os.path.join(out_dir, "data_quality.csv"), index=False)
    summ = pass_summary(V)
    json.dump({"declarations": DECLARATIONS, "status": STATUS, "regime": REGIME_NOTE, "sources": meta_src,
               "pass_summary": summ, "hac_lags": HAC_LAGS, "floor": [FLOOR_FIRES, FLOOR_DATES],
               "horizons": HORIZONS, "unit": "first fire per UTC day",
               "price_source": "Binance BTCUSDT 5m klines (data.binance.vision), Open entry / Close exit",
               "control": "B1 clock-and-side matched drift; B2 revert-to-mid without a sweep"},
              open(os.path.join(out_dir, "meta.json"), "w"), indent=1, default=str)
    print(json.dumps(summ, indent=1))
    print(json.dumps(meta_src, indent=1, default=str))


# ── self-test (synthetic only) ──────────────────────────────────────────────────────────────────
def _synthetic(nd=30, seed=7):
    """Random-walk 5m bars with some high-volatility hours (to reach VOLATILE / QUIET labels)."""
    rng = np.random.default_rng(seed)
    n = nd * BARS_PER_DAY
    vol = np.full(n, 0.0015)
    for _ in range(nd):
        a = rng.integers(0, n - 60)
        vol[a:a + 60] *= rng.choice([0.1, 5.0])
    lr = rng.normal(0, vol)
    c = 30000 * np.exp(np.cumsum(lr))
    o = np.r_[30000, c[:-1]]
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, vol / 2)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, vol / 2)))
    t = pd.date_range("2022-03-01", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame({"open_time_utc": t, "open": o, "high": h, "low": l, "close": c, "volume": 1.0})


def _hub_parity(G, Hr, days):
    """Run the hub's check_session_sweep and _check_btc_regime on the same bars."""
    sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "backend")))
    import strategies.crypto_setups as cs
    import integrations.binance_futures as bf
    state = {"t": 0, "kl": None, "last": None}

    class FixedDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromtimestamp(state["t"], tz=timezone.utc)

    class FixedTime:
        @staticmethod
        def time():
            return float(state["t"])

    async def fake_klines(symbol="BTCUSDT", interval="5m", limit=100):
        return state["kl"]

    async def fake_ticker(symbol="BTCUSDT"):
        return {"last_price": state["last"]}

    saved = (cs.datetime, cs.time, bf.get_klines, bf.get_ticker_24h)
    cs.datetime, cs.time, bf.get_klines, bf.get_ticker_24h = FixedDT, FixedTime, fake_klines, fake_ticker
    cs._last_fired.clear()
    flat = {c: G[c].reshape(-1) for c in ("o", "h", "l", "c")}
    hub, reg_mis, n_reg = [], 0, 0
    try:
        for d in days:
            if day_status(G, d) != "ok":
                continue
            for j in INSTANTS:
                g = d * BARS_PER_DAY + j
                state["t"] = G["epoch0"] + d * 86400 + (j + 1) * 300
                state["kl"] = [[int((G["epoch0"] + (k * 300)) * 1000), str(flat["o"][k]), str(flat["h"][k]),
                                str(flat["l"][k]), str(flat["c"][k]), "1", 0, "0", 0, "0", "0", "0"]
                               for k in range(g - BARS_PER_DAY + 1, g + 1)]
                state["last"] = float(flat["c"][g])
                hg = d * 24 + ((j + 1) * 5) // 60
                kl1h = [[int((G["epoch0"] + x * 3600) * 1000), str(Hr["o"][x]), str(Hr["h"][x]), str(Hr["l"][x]),
                         str(Hr["c"][x]), "1", 0, "0", 0, "0", "0", "0"] for x in range(hg - 23, hg + 1)]
                rh = asyncio.run(cs._check_btc_regime(kl1h))["regime"]
                n_reg += 1
                reg_mis += int(rh != regime_label(Hr, hg))
                sig = asyncio.run(cs.check_session_sweep())
                if sig:
                    e = json.loads(sig["enrichment_data"])
                    hub.append({"d": d, "j": j, "side": sig["direction"], "asia_high": e["asia_high"],
                                "asia_low": e["asia_low"]})
    finally:
        cs.datetime, cs.time, bf.get_klines, bf.get_ticker_24h = saved
        cs._last_fired.clear()
    return pd.DataFrame(hub), reg_mis, n_reg


def selftest():
    import tempfile
    checks = {}
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "s.parquet")
        S = _synthetic()
        S.to_parquet(p, index=False)
        G = load_grid(p)
        Hr = hourly(G)
        checks["grid: 30 days x 288 bars, all present"] = G["c"].shape == (30, 288) and G["present"].all()
        checks["instants: 48 per day, 08:00..09:55 and 13:00..14:55 closes"] = \
            len(INSTANTS) == 48 and (INSTANTS[0] + 1) * 5 == 480 and (INSTANTS[23] + 1) * 5 == 595 \
            and (INSTANTS[24] + 1) * 5 == 780 and (INSTANTS[-1] + 1) * 5 == 895
        checks["day 0 is a gap (no D-1)"] = day_status(G, 0) == "gap"
        # parity with the hub, detector + cooldown (regime filter off: the hub's check has none)
        Fn = fires(G, Hr, regime_on=False)
        hub, reg_mis, n_reg = _hub_parity(G, Hr, range(len(G["days"])))
        m = Fn.merge(hub, on=["d", "j"], how="outer", suffixes=("", "_hub"), indicator=True)
        checks["parity: replay fires == hub check_session_sweep fires (same instants)"] = \
            len(Fn) > 10 and bool((m._merge == "both").all())
        checks["parity: same side and Asia range at every fire"] = \
            bool((m.side == m.side_hub).all()) and bool(np.allclose(m.asia_high, m.asia_high_hub)) \
            and bool(np.allclose(m.asia_low, m.asia_low_hub))
        checks["parity: both sides occur in the synthetic set"] = set(Fn.side) == {"LONG", "SHORT"}
        checks["parity: regime label == hub _check_btc_regime at every instant"] = n_reg > 100 and reg_mis == 0
        Fr = fires(G, Hr, regime_on=True)
        checks["regime filter removes some fires (QUIET / VOLATILE reached)"] = 0 < len(Fr) < len(Fn)
        # cooldown: same direction never within 1800 s
        ok = True
        for s in ("LONG", "SHORT"):
            ts = Fn[Fn.side == s].t.sort_values().values
            ok &= bool((np.diff(ts) > COOLDOWN_S).all())
        checks["cooldown: same side > 1800 s apart"] = ok
        checks["first_of_day: one per fire day"] = int(Fn.first_of_day.sum()) == Fn.d.nunique()
        # returns and baselines
        d, j = int(Fn.d.iloc[0]), int(Fn.j.iloc[0])
        checks["return: close(j+12) / open(j+1) - 1"] = \
            np.isclose(raw_ret(G, d, j, 12), G["c"][d, j + 12] / G["o"][d, j + 1] - 1)
        days = split_days(G, "perp", "ALL")
        B1, B2 = baselines(G, days)
        checks["B1: mean over every evaluable day at that clock"] = \
            np.isclose(B1[(INSTANTS[0], "1h")], np.mean([raw_ret(G, x, INSTANTS[0], 12) for x in days]))
        checks["B2: finite for both horizons"] = np.isfinite(B2["1h"]) and np.isfinite(B2["4h"])
        # bracket: a bar touching both lines counts as stop
        G2 = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in G.items()}
        ah, al, _ = asia(G2, d)
        G2["h"][d, j + 1], G2["l"][d, j + 1] = ah * 1.01, al * 0.99
        checks["bracket: both touched in one bar -> stop"] = bracket(G2, d, j, "SHORT", ah, al) == "stop"
        # cells, floor, splits
        rows = cell_rows(G, Fr, "perp")
        bear = [r for r in rows if r["split"] == "bear"]
        checks["cells: bear rows carry a verdict; synthetic 2022 is below floor"] = \
            len(bear) == 2 and all(r["verdict"] == "below floor - cannot pass" for r in bear)
        checks["splits: 2018 is bear for SPOT only"] = 2018 in BEAR["spot"] and 2018 not in BEAR["perp"]
        checks["labels: venue line on every row"] = all("live reads OKX swap" in r["label"] for r in rows)
        V = pd.DataFrame([{"verdict": "no pass"}] * 3 + [{"verdict": "PASS"}])
        ps = pass_summary(V)
        checks["pass summary: '1 of 4 eligible (8 cells)', bound 0.091, chance label"] = \
            ps["written"] == "1 of 4 eligible (8 cells)" and ps["chance_expected_upper_bound"] == 0.091 \
            and ps["label"].startswith("consistent with chance")
        # end to end
        run(p, p, os.path.join(td, "out"))
        files = set(os.listdir(os.path.join(td, "out")))
        checks["end-to-end: all outputs written"] = {"cells.csv", "verdicts.csv", "sensitivity.csv", "bracket.csv",
                                                     "data_quality.csv", "meta.json"} <= files
    for k, v in checks.items():
        print(("PASS " if v else "FAIL ") + k)
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "selftest":
        sys.exit(selftest())
    elif mode == "run":
        run(*sys.argv[2:5])
