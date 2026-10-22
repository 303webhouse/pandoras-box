"""Forward test of HYPNOS-LELEDC v2 (InSilico, 4-hour crypto): paper only (R-IV.1317). No orders, no live job.

The FROZEN graded code is hypnos_leledc.py at 60b4469 (blob 18db1521...; LF sha256 195ce62c...), imported unchanged:
load_1h, to_4h (UTC 4h, a window missing any hourly candle dropped), events_4h (v1's detector 10 / 40 / 4, burn-in 250,
the placebo, raw returns: next-bar open to the close of bar 6 / bar 30), arm_result (signal - placebo, HAC h - 1 lags,
the one-sided decision with both 20-day floors). This file adds ONLY the declared forward rules:

  1. HISTORY = the two stamped Coinbase 1h files (to 2026-10-17 23:00 UTC) + a continuation fetched from Coinbase's public
     candles from 2026-10-18 00:00 UTC, so the detector's cumulative counters run unbroken, exactly as graded.
  2. CLOSED CANDLES ONLY: an hourly candle counts only if its hour closed before the fetch instant (Coinbase also
     returns the forming candle).
  3. FORWARD EVENTS: a signal or placebo counts only if its 4h bar OPENS strictly after the start instant (the stamp).
  4. GRADEABLE: its exit bar (bar 6 for the primary) must exist, i.e. have closed by the checkpoint; otherwise it is
     counted as ungradeable and excluded.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hypnos_leledc as HL  # noqa: E402  (frozen at 60b4469)

CONT_FROM = pd.Timestamp("2026-10-18T00:00:00Z")
STAMPED_LAST = pd.Timestamp("2026-10-17T23:00:00Z")
PRODUCTS = ("BTC-USD", "ETH-USD")


def fetch_continuation(product, end_utc, start=CONT_FROM):
    """Coinbase Exchange public 1h candles from `start` to `end_utc` (closed candles only). Internal research only
    (R-IV.1245(b)3)."""
    end_utc = pd.Timestamp(end_utc)
    rows, s = [], start
    while s < end_utc:
        e = min(s + pd.Timedelta(hours=300), end_utc)
        url = (f"https://api.exchange.coinbase.com/products/{product}/candles?granularity=3600"
               f"&start={s.strftime('%Y-%m-%dT%H:%M:%SZ')}&end={(e - pd.Timedelta(seconds=1)).strftime('%Y-%m-%dT%H:%M:%SZ')}")
        for attempt in range(6):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "trading-hub-lab research"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    rows += json.loads(r.read().decode())
                break
            except urllib.error.HTTPError as err:
                if err.code != 429:
                    raise
                time.sleep(1.5 * (attempt + 1))
        s = e
        time.sleep(0.15)
    df = pd.DataFrame(rows, columns=["ts", "low", "high", "open", "close", "volume"]).drop_duplicates("ts")
    df["ts"] = pd.to_datetime(df.ts, unit="s", utc=True)
    return df[["ts", "open", "high", "low", "close", "volume"]].sort_values("ts").reset_index(drop=True)


def closed_only(h1, fetch_instant):
    return h1[h1.ts + pd.Timedelta(hours=1) <= pd.Timestamp(fetch_instant)].reset_index(drop=True)


def history(stamped_path, cont_df, fetch_instant):
    st = HL.load_1h(stamped_path)
    assert st.ts.max() == STAMPED_LAST, "the stamped file must end at 2026-10-17 23:00 UTC"
    cont = closed_only(cont_df, fetch_instant)
    if len(cont):
        assert cont.ts.min() >= CONT_FROM, "the continuation must start at or after 2026-10-18 00:00 UTC (no overlap)"
    return pd.concat([st, cont], ignore_index=True).sort_values("ts").drop_duplicates("ts").reset_index(drop=True)


def forward_events(h1_by_asset, start_instant):
    start = pd.Timestamp(start_instant)
    rows, bars = [], {}
    for name, h1 in h1_by_asset.items():
        b4, dropped, total = HL.to_4h(h1)
        bars[name] = {"complete_4h_bars": int(len(b4)), "dropped_incomplete": dropped,
                      "forward_bars": int((b4.index > start).sum()), "last_bar_open": str(b4.index.max())}
        rows += HL.events_4h(name, b4)
    ev = pd.DataFrame(rows)
    fwd = ev[pd.to_datetime(ev.ts, utc=True) > start].reset_index(drop=True) if len(ev) else ev
    return ev, fwd, bars


def forward_score(stamped_btc, stamped_eth, cont_btc, cont_eth, start_instant, fetch_instant, out_dir, check_hashes=True):
    if check_hashes:
        assert HL.sha256(stamped_btc) == HL.V2_BTC_SHA256 and HL.sha256(stamped_eth) == HL.V2_ETH_SHA256, "stamped files"
    os.makedirs(out_dir, exist_ok=True)
    assert not os.listdir(out_dir), "out_dir must be empty (one scoring)"
    h1 = {"BTC-USD": history(stamped_btc, cont_btc, fetch_instant), "ETH-USD": history(stamped_eth, cont_eth, fetch_instant)}
    ev, fwd, bars = forward_events(h1, start_instant)
    g6 = fwd[fwd.r6.notna()] if len(fwd) else fwd
    prim = HL.arm_result(fwd, HL.V2_H_PRIMARY, "raw", hac_lags=HL.V2_H_PRIMARY - 1, bar_col="bar") if len(fwd) else \
        {"decision": "INSUFFICIENT", "n_signal": 0, "n_signal_dates": 0, "n_placebo": 0, "n_placebo_dates": 0}
    sec = HL.arm_result(fwd, HL.V2_H_SECONDARY, "raw", hac_lags=HL.V2_H_SECONDARY - 1, bar_col="bar") if len(fwd) else {}
    if sec:
        sec["decision"] = "no weight · t = %s" % ("n/a" if sec.get("t") is None else sec["t"])   # R-IV.1248 display rule
    res = {"registration": "FORWARD-REG-INSILICO-4H-R-IV.1317.md", "start_instant": str(pd.Timestamp(start_instant)),
           "fetch_instant": str(pd.Timestamp(fetch_instant)), "bars": bars,
           "forward_events": int(len(fwd)), "ungradeable_h6": int(fwd.r6.isna().sum()) if len(fwd) else 0,
           "gradeable_h6": int(len(g6)), "primary_h6_24h": prim, "secondary_h30_5d_no_weight": sec,
           "frozen_code": "hypnos_leledc.py @ 60b4469 (18db1521...)"}
    fwd.to_csv(os.path.join(out_dir, "forward_events.csv"), index=False)
    json.dump(res, open(os.path.join(out_dir, "forward_result.json"), "w"), indent=1, default=str)
    return res


def selftest():
    import tempfile
    ok = fail = 0

    def check(name, cond):
        nonlocal ok, fail
        ok, fail = ok + bool(cond), fail + (not cond)
        print(("PASS " if cond else "FAIL ") + name)

    tmp = tempfile.mkdtemp()
    rng = np.random.default_rng(41)
    ts = pd.date_range(end=STAMPED_LAST, periods=24 * 6 * 300, freq="h", tz="UTC")
    c = 100 * np.exp(np.cumsum(0.004 * rng.standard_normal(len(ts))))
    o = np.r_[c[0], c[:-1]]
    st = pd.DataFrame({"ts": ts, "open": o, "high": np.maximum(o, c) * 1.001, "low": np.minimum(o, c) * 0.999, "close": c,
                       "volume": 1.0})
    sp = os.path.join(tmp, "st.parquet")
    st.to_parquet(sp, index=False)
    tc = pd.date_range(CONT_FROM, periods=24 * 120, freq="h", tz="UTC")
    cc = c[-1] * np.exp(np.cumsum(0.004 * rng.standard_normal(len(tc))))
    oc = np.r_[c[-1], cc[:-1]]
    cont = pd.DataFrame({"ts": tc, "open": oc, "high": np.maximum(oc, cc) * 1.001, "low": np.minimum(oc, cc) * 0.999,
                         "close": cc, "volume": 1.0})
    fetch = tc[-1] + pd.Timedelta(minutes=30)                       # the last candle is still forming
    h = history(sp, cont, fetch)
    check("closed candles only: the forming hour is dropped", h.ts.max() == tc[-2])
    check("history is the stamped file + the continuation, unbroken", len(h) == len(st) + len(tc) - 1 and h.ts.is_monotonic_increasing)
    try:
        history(sp, pd.concat([st.tail(3), cont]), fetch)
        overlap = False
    except AssertionError:
        overlap = True
    check("a continuation overlapping the stamped file is refused", overlap)
    start = pd.Timestamp("2026-11-01T06:00:00Z")
    ev, fwd, bars = forward_events({"BTC-USD": h, "ETH-USD": h}, start)
    check("forward events: only bars opening STRICTLY after the start instant",
          len(fwd) == 0 or pd.to_datetime(fwd.ts, utc=True).min() > start)
    full = HL.events_4h("X", HL.to_4h(h)[0])
    check("the frozen detector runs over the whole history (forward events are a subset of the full run)",
          len(fwd) <= 2 * len(full) and len(ev) == 2 * len(full))
    if len(fwd):
        last_bar = HL.to_4h(h)[0].index.max()
        late = fwd[pd.to_datetime(fwd.ts, utc=True) > last_bar - pd.Timedelta(hours=4 * 6)]
        check("an event whose bar 6 has not closed by the checkpoint is ungradeable", late.r6.isna().all())
    else:
        check("synthetic forward window produced events", False)
    r = forward_score(sp, sp, cont, cont, start, fetch, os.path.join(tmp, "out"), check_hashes=False)
    check("forward_score writes its result; the primary carries the frozen one-sided decision",
          r["primary_h6_24h"]["decision"] in ("SUPPORTED", "NOT SUPPORTED", "INSUFFICIENT"))
    check("the secondary is labelled no weight", (not r["secondary_h30_5d_no_weight"])
          or r["secondary_h30_5d_no_weight"]["decision"].startswith("no weight"))
    try:
        forward_score(sp, sp, cont, cont, start, fetch, os.path.join(tmp, "out2"), check_hashes=True)
        refused = False
    except AssertionError:
        refused = True
    check("forward_score refuses files that are not the stamped Coinbase files", refused)
    print(f"{ok}/{ok + fail}")
    return fail == 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["selftest"]:
        sys.exit(0 if selftest() else 1)
    print(__doc__)
    sys.exit(2)
