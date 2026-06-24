r"""stage2_options_backtest — L1b Stage-2 options-P&L measurement harness.

OFFLINE research harness. Grades an L1b factor's Stage-1 trade ledger as an
OPTIONS strategy: per-trade 30-delta call debit spread, BS-priced with SEPARATE
entry-date and exit-date IV, beta-stripped vs a same-model SPY control, with a
recent GEX-gated slice and a Tier-B validation gate.

ZERO DB writes. Reads the Stage-1 ledger CSV + yfinance (deep-history bars +
VIX/VXN) + UW (recent IV/GEX/contracts). Writes nothing but stdout + (optional)
a JSON results dump. Run via `railway run` so UW_API_KEY is present for Tier B:

    railway run --service pandoras-box python scripts/stage2_options_backtest.py

Reuse (engine parity with the live path — Step 0):
  - backend.utils.options_math: _norm_cdf/_norm_pdf/bs_greeks_from_iv  (the live
    bs_computed engine — BS *price* added here on the SAME _norm_cdf).
  - backend.jobs.b2_options_resolver: _option_type/_spread_width/_find_expiry
    (historical expressions MUST match the live forward collector).

Tiering (Step 0b probe, 2026-06-23): UW historical IV is plan-gated to the most
recent 180 trading days — earliest accessible date = 2025-10-02 = the WALL.
  - entry_date >= WALL  -> Tier B: UW interpolated-iv at the trade DTE.
  - entry_date <  WALL  -> Tier A: VIX (SPY) / VXN (QQQ) close / 100 (yfinance).
Entry IV and exit IV are ALWAYS looked up separately (DAEDALUS rule #3).

Blessed v1 simplifications (flagged in the output doc):
  - r = 4% constant (FRED 3M is a later refinement).
  - ATM IV only (skew/25-delta RR deferred unless Step-5 overlap error >~5%).
  - No slippage / BS-mid fills — blessed for SPY/QQQ only (penny-wide).
  - Synthetic $1 strike grid for deep history (no historical chain pre-wall).
"""

from __future__ import annotations

import csv
import json
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime

# ── reuse targets (engine parity) ────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from utils.options_math import _norm_cdf, bs_greeks_from_iv  # noqa: E402
from jobs.b2_options_resolver import _spread_width, _find_expiry  # noqa: E402

# ── config ───────────────────────────────────────────────────────────────────
LEDGER = r"C:\temp\rsi2_stage1_trades.csv"
FACTOR = "RSI-2"
WALL = "2025-10-02"            # Tier-A/B boundary (UW 180-trading-day gate)
R = 0.04                       # risk-free, v1 constant
IV_FLOOR, IV_CAP = 0.05, 2.5   # sane IV guards
PROXY = {"SPY": "^VIX", "QQQ": "^VXN"}
UW_BASE = "https://api.unusualwhales.com"
UW_KEY = os.environ.get("UW_API_KEY", "")
UW_CACHE_PATH = r"C:\temp\uw_iv_cache.json"

# canonical Connors RSI-2 = entry5_sma5; all four graded, this one headlined.
HEADLINE_CONFIG = "entry5_sma5"


# ── BS price (same _norm_cdf as the live Greeks engine) ──────────────────────
def bs_price(S, K, T, r, sigma, opt="call"):
    """European BS price, zero-dividend. T<=0 or sigma<=0 -> intrinsic."""
    if S <= 0 or K <= 0:
        return 0.0
    if T <= 0 or sigma <= 0:
        return max(0.0, (S - K) if opt == "call" else (K - S))
    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    if opt == "call":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def spread_value(S, long_k, short_k, T, r, iv, opt="call"):
    """Debit-spread value = long leg − short leg."""
    return bs_price(S, long_k, T, r, iv, opt) - bs_price(S, short_k, T, r, iv, opt)


def pick_long_strike(spot, T, iv, opt="call"):
    """0.30-|delta| strike on a synthetic $1 grid; fallback ~2% OTM (b2 rule)."""
    best_k, best_diff = None, float("inf")
    lo = int(math.floor(spot * (0.90 if opt == "call" else 0.85)))
    hi = int(math.ceil(spot * (1.15 if opt == "call" else 1.10)))
    for k in range(max(lo, 1), hi + 1):
        g = bs_greeks_from_iv(spot, float(k), T, R, iv, opt)
        d = g.get("delta")
        if d is None:
            continue
        diff = abs(abs(d) - 0.30)
        if diff < best_diff:
            best_diff, best_k = diff, float(k)
    if best_k is None:  # degenerate IV/T -> moneyness fallback
        best_k = round(spot * (1.02 if opt == "call" else 0.98), 2)
    return best_k


# ── data sources ─────────────────────────────────────────────────────────────
def yf_close_map(symbol, start="2002-01-01", adjust=True):
    """{‘YYYY-MM-DD’: close} via yfinance. adjust=False -> RAW close (the actual
    traded price), required for option pricing — options trade vs the unadjusted
    underlying, NOT the dividend-back-adjusted series (Step-5 P0 fix 2026-06-23)."""
    import yfinance as yf
    df = yf.download(symbol, start=start, auto_adjust=adjust, progress=False)
    out = {}
    if df is None or len(df) == 0:
        return out
    close_col = None
    for c in df.columns:
        name = c[0] if isinstance(c, tuple) else c
        if name == "Close":
            close_col = c
            break
    if close_col is None:
        return out
    for idx in df.index:
        try:
            v = float(df.loc[idx, close_col])
        except Exception:
            continue
        if v == v:
            out[idx.strftime("%Y-%m-%d")] = v
    return out


def _nearest_on_or_before(dmap, dstr, max_back=6):
    """Calendar-tolerant lookup: dstr, else nearest prior within max_back days."""
    if dstr in dmap:
        return dmap[dstr]
    d0 = datetime.strptime(dstr, "%Y-%m-%d").date()
    from datetime import timedelta
    for k in range(1, max_back + 1):
        dk = (d0 - timedelta(days=k)).isoformat()
        if dk in dmap:
            return dmap[dk]
    return None


# ── UW Tier-B IV (direct, cached, governor-bypassing) ────────────────────────
_uw_cache = {}


def _uw_cache_load():
    global _uw_cache
    try:
        _uw_cache = json.load(open(UW_CACHE_PATH))
    except Exception:
        _uw_cache = {}


def _uw_cache_save():
    try:
        json.dump(_uw_cache, open(UW_CACHE_PATH, "w"))
    except Exception:
        pass


def _uw_get(path):
    """httpx GET (the codebase's client — passes UW's Cloudflare bot filter on
    the option-contracts/historic endpoints that block a plain urllib client)."""
    if not UW_KEY:
        return None
    import httpx
    try:
        with httpx.Client(timeout=25) as c:
            r = c.get(UW_BASE + path,
                      headers={"Authorization": "Bearer " + UW_KEY,
                               "Accept": "application/json"})
            if r.status_code == 200:
                return r.json()
    except Exception:
        return None
    return None


def _occ(ticker, expiry_iso, cp, strike):
    """OCC option symbol, e.g. SPY260413C00679000."""
    y, m, d = expiry_iso.split("-")
    return f"{ticker}{y[2:]}{m}{d}{cp}{int(round(strike * 1000)):08d}"


_hist_cache = {}


def uw_contract_mark_map(sym):
    """{date: mid} for one contract from /option-contract/{sym}/historic. Mid =
    nbbo midpoint when present, else last_price. Cached per symbol."""
    if sym in _hist_cache:
        return _hist_cache[sym]
    resp = _uw_get(f"/api/option-contract/{sym}/historic")
    rows = []
    if isinstance(resp, dict):
        rows = resp.get("chains") or resp.get("data") or []
    out = {}
    for row in rows:
        d = row.get("date")
        if not d:
            continue
        bid = row.get("nbbo_bid") or row.get("bid")
        ask = row.get("nbbo_ask") or row.get("ask")
        mid = None
        try:
            if bid is not None and ask is not None and float(bid) > 0 and float(ask) > 0:
                mid = (float(bid) + float(ask)) / 2.0
            elif row.get("last_price") not in (None, "", "0", "0.0"):
                mid = float(row["last_price"])
        except Exception:
            mid = None
        if mid is not None:
            out[d] = mid
    _hist_cache[sym] = out
    return out


def uw_interp_iv(ticker, dstr, dte):
    """UW interpolated-iv at `dstr` for the row nearest `dte` DTE. Cached.
    Returns IV decimal or None (None => caller falls back / skips)."""
    key = f"{ticker}:{dstr}"
    if key not in _uw_cache:
        resp = _uw_get(f"/api/stock/{ticker}/interpolated-iv?date={dstr}")
        rows = (resp or {}).get("data") if isinstance(resp, dict) else resp
        self_rows = []
        for row in rows or []:
            try:
                self_rows.append((int(row["days"]), float(row["volatility"])))
            except Exception:
                continue
        _uw_cache[key] = self_rows  # may be [] => no coverage, cached as miss
    rows = _uw_cache[key]
    if not rows:
        return None
    return min(rows, key=lambda dv: abs(dv[0] - dte))[1]


# ── per-trade pricing ────────────────────────────────────────────────────────
def iv_for(ticker, dstr, dte, vix_map, vxn_map, force_proxy=False):
    """Tier-routed IV with the tier label. (iv, tier)."""
    if (not force_proxy) and dstr >= WALL:
        iv = uw_interp_iv(ticker, dstr, dte)
        if iv is not None:
            return max(IV_FLOOR, min(IV_CAP, iv)), "B-uw"
    pmap = vix_map if ticker == "SPY" else vxn_map
    raw = _nearest_on_or_before(pmap, dstr)
    if raw is None:
        return None, "none"
    return max(IV_FLOOR, min(IV_CAP, raw / 100.0)), "A-proxy"


def price_trade(t, vix_map, vxn_map, close_maps, as_ticker=None, force_proxy=False):
    """Price one debit spread. as_ticker overrides the underlying (the SPY
    control reuses this exact model on SPY). Spots come from close_maps, which
    MUST be UNADJUSTED closes (option pricing vs the actual underlying).

    Expiry settlement: if the signal's exit_date falls ON/AFTER the option
    expiry (RSI-2 max-hold tail vs the 8-21d expiry), the spread is settled at
    INTRINSIC using the underlying close on the expiry date (you cannot hold an
    expired option to the signal's later exit) — not at the exit-date spot."""
    ticker = as_ticker or t["ticker"]
    entry_d, exit_d = t["entry_date"], t["exit_date"]
    cmap = close_maps.get(ticker, {})
    spot_e = _nearest_on_or_before(cmap, entry_d)
    spot_x = _nearest_on_or_before(cmap, exit_d)
    if spot_e is None or spot_x is None:
        return None

    expiry = _find_expiry(datetime.strptime(entry_d, "%Y-%m-%d").date())
    if not expiry:
        return None
    exp_d = datetime.strptime(expiry, "%Y-%m-%d").date()
    dte_e = (exp_d - datetime.strptime(entry_d, "%Y-%m-%d").date()).days
    dte_x = (exp_d - datetime.strptime(exit_d, "%Y-%m-%d").date()).days
    if dte_e <= 0:
        return None
    T_e = dte_e / 365.0
    T_x = max(dte_x, 0) / 365.0
    expired = dte_x <= 0
    if expired:                         # settle at expiry intrinsic, expiry-date spot
        exp_spot = _nearest_on_or_before(close_maps.get(ticker, {}), expiry)
        if exp_spot is not None:
            spot_x = exp_spot

    iv_e, tier_e = iv_for(ticker, entry_d, dte_e, vix_map, vxn_map, force_proxy)
    if expired:                         # T_x=0 -> intrinsic, exit IV irrelevant
        iv_x, tier_x = iv_e, "expiry-intrinsic"
    else:
        iv_x, tier_x = iv_for(ticker, exit_d, max(dte_x, 1), vix_map, vxn_map, force_proxy)
    if iv_e is None or iv_x is None:
        return None

    long_k = pick_long_strike(spot_e, T_e, iv_e)
    width = _spread_width(spot_e)
    short_k = long_k + width

    entry_spread = spread_value(spot_e, long_k, short_k, T_e, R, iv_e)
    exit_spread = spread_value(spot_x, long_k, short_k, T_x, R, iv_x)
    if entry_spread <= 0:               # degenerate (deep OTM / zero-vol) — skip
        return None
    pnl = (exit_spread - entry_spread) * 100.0

    return {
        "ticker": ticker, "entry_date": entry_d, "exit_date": exit_d,
        "spot_e": round(spot_e, 2), "spot_x": round(spot_x, 2),
        "long_k": long_k, "short_k": round(short_k, 2), "width": width,
        "dte_e": dte_e, "dte_x": dte_x, "expired_before_exit": expired,
        "iv_e": round(iv_e, 4), "iv_x": round(iv_x, 4), "tier_e": tier_e, "tier_x": tier_x,
        "entry_spread": round(entry_spread, 4), "exit_spread": round(exit_spread, 4),
        "options_pnl": round(pnl, 4), "underlying_ret": float(t["underlying_ret"]),
        "return_on_risk": round(pnl / (entry_spread * 100.0), 4),
    }


# ── aggregation ──────────────────────────────────────────────────────────────
def agg(pnls):
    n = len(pnls)
    if n == 0:
        return None
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gp, gl = sum(wins), abs(sum(losses))
    eq, peak, mdd = 0.0, 0.0, 0.0
    for p in pnls:
        eq += p
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    return {
        "n": n, "total_pnl": round(sum(pnls), 2),
        "win_pct": round(100.0 * len(wins) / n, 1),
        "pf": round(gp / gl, 3) if gl > 0 else 999.0,
        "avg": round(sum(pnls) / n, 2),
        "avg_win": round(gp / len(wins), 2) if wins else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "max_dd_$": round(mdd, 2),
    }


def fmt(a):
    if not a:
        return "  (no trades)"
    return ("  n=%d  total=$%.0f  win%%=%.1f  PF=%.2f  avg=$%.2f  (W $%.2f / L $%.2f)  maxDD=$%.0f"
            % (a["n"], a["total_pnl"], a["win_pct"], a["pf"], a["avg"],
               a["avg_win"], a["avg_loss"], a["max_dd_$"]))


# ── GEX (Step 4) ─────────────────────────────────────────────────────────────
def gex_sign_map():
    """{date: +1/-1} SPY net-GEX sign from UW greek-exposure (~1yr series)."""
    resp = _uw_get("/api/stock/SPY/greek-exposure")
    rows = (resp or {}).get("data") if isinstance(resp, dict) else resp
    out = {}
    for row in rows or []:
        try:
            net = float(row["call_gamma"]) + float(row["put_gamma"])  # put_gamma<0
            out[row["date"]] = 1 if net > 0 else -1
        except Exception:
            continue
    return out


# ── Step 5: validation gate (NON-ARBITRABLE) ─────────────────────────────────
def validation(trades, vix, vxn, close_maps, results):
    out = {}

    # 5a. Proxy-vs-UW: on Tier-B trades (entry AND exit >= wall, so the normal
    # run uses UW for both legs), re-price with VIX/VXN proxy. The delta bounds
    # the Tier-A (deep-history) modeling error.
    seen, deltas, prem = set(), [], []
    uw_total, px_total = 0.0, 0.0
    for t in trades:
        if t["entry_date"] < WALL or t["exit_date"] < WALL:
            continue
        key = (t["ticker"], t["entry_date"], t["exit_date"], t["entry_close"], t["exit_close"])
        if key in seen:
            continue
        seen.add(key)
        a = price_trade(t, vix, vxn, close_maps)                    # UW
        b = price_trade(t, vix, vxn, close_maps, force_proxy=True)  # VIX/VXN
        if not a or not b or a["tier_e"] != "B-uw":
            continue
        deltas.append(a["options_pnl"] - b["options_pnl"])
        prem.append(a["entry_spread"] * 100.0)
        uw_total += a["options_pnl"]
        px_total += b["options_pnl"]
    n = len(deltas)
    if n:
        mean_abs = sum(abs(d) for d in deltas) / n
        mean_prem = sum(prem) / n
        out["proxy_vs_uw"] = {
            "n": n,
            "uw_total_pnl": round(uw_total, 2),
            "proxy_total_pnl": round(px_total, 2),
            "agg_pnl_delta": round(uw_total - px_total, 2),
            "mean_abs_pnl_delta_$": round(mean_abs, 2),
            "mean_entry_premium_$": round(mean_prem, 2),
            "mean_abs_delta_pct_of_premium": round(100.0 * mean_abs / mean_prem, 1) if mean_prem else None,
        }
    else:
        out["proxy_vs_uw"] = {"n": 0, "note": "no Tier-B trades with both legs >= wall"}

    # 5b. Modeled-vs-real: BS-mid vs real UW contract marks on a Tier-B sample.
    sample, checks = [], []
    for cfg in results:
        for p in results[cfg]["_priced"]:
            if p["tier_e"] == "B-uw" and not p["expired_before_exit"]:
                sample.append(p)
    # de-dup by (entry_date, long_k) and cap the httpx sample
    uniq, sample2 = set(), []
    for p in sample:
        k = (p["entry_date"], p["long_k"], p["short_k"])
        if k in uniq:
            continue
        uniq.add(k)
        sample2.append(p)
    for p in sample2[:8]:
        expiry = _find_expiry(datetime.strptime(p["entry_date"], "%Y-%m-%d").date())
        if not expiry:
            continue
        long_sym = _occ(p["ticker"], expiry, "C", p["long_k"])
        short_sym = _occ(p["ticker"], expiry, "C", p["short_k"])
        lm = uw_contract_mark_map(long_sym)
        sm = uw_contract_mark_map(short_sym)
        le = _nearest_on_or_before(lm, p["entry_date"])
        se = _nearest_on_or_before(sm, p["entry_date"])
        if le is None or se is None:
            continue
        real_entry = le - se
        if real_entry <= 0:
            continue
        err = abs(p["entry_spread"] - real_entry) / real_entry
        checks.append({
            "ticker": p["ticker"], "entry_date": p["entry_date"],
            "long_k": p["long_k"], "short_k": p["short_k"],
            "bs_entry_spread": p["entry_spread"], "real_entry_spread": round(real_entry, 4),
            "abs_pct_err": round(100.0 * err, 1),
        })
    if checks:
        out["modeled_vs_real"] = {
            "n": len(checks),
            "mean_abs_pct_err_entry_spread": round(sum(c["abs_pct_err"] for c in checks) / len(checks), 1),
            "max_abs_pct_err": round(max(c["abs_pct_err"] for c in checks), 1),
            "detail": checks,
        }
    else:
        out["modeled_vs_real"] = {"n": 0, "note": "no real contract marks resolved for sample"}
    return out


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("=" * 70)
    print(f"STAGE-2 OPTIONS BACKTEST — {FACTOR}   (wall={WALL}, r={R}, UW_KEY={'Y' if UW_KEY else 'N'})")
    print("=" * 70)

    trades = list(csv.DictReader(open(LEDGER)))
    configs = sorted({t["config"] for t in trades})
    print(f"ledger: {len(trades)} trades, configs={configs}\n")

    print("loading yfinance (VIX, VXN, SPY+QQQ spots)...")
    vix = yf_close_map("^VIX")
    vxn = yf_close_map("^VXN")
    spy = yf_close_map("SPY", adjust=False)   # RAW close — option pricing spot
    qqq = yf_close_map("QQQ", adjust=False)
    close_maps = {"SPY": spy, "QQQ": qqq}
    print(f"  VIX={len(vix)} VXN={len(vxn)} SPY={len(spy)} QQQ={len(qqq)} bars\n")

    _uw_cache_load()
    gex = gex_sign_map() if UW_KEY else {}
    print(f"GEX series days: {len(gex)} (UW greek-exposure)\n")

    results = {}
    for cfg in configs:
        ctrades = [t for t in trades if t["config"] == cfg]
        priced, control_pnls, alpha_pnls = [], [], []
        gex_pos_alpha, skipped = [], 0
        for t in ctrades:
            pr = price_trade(t, vix, vxn, close_maps)
            if pr is None:
                skipped += 1
                continue
            # SPY same-model control over the identical window
            ctrl = price_trade(t, vix, vxn, close_maps, as_ticker="SPY")
            priced.append(pr)
            if ctrl is not None:
                control_pnls.append(ctrl["options_pnl"])
                alpha = pr["options_pnl"] - ctrl["options_pnl"]
                alpha_pnls.append(alpha)
                if gex.get(t["entry_date"]) == 1:
                    gex_pos_alpha.append(alpha)
        results[cfg] = {
            "factor": agg([p["options_pnl"] for p in priced]),
            "control": agg(control_pnls),
            "alpha": agg(alpha_pnls),
            "gex_pos_alpha": agg(gex_pos_alpha),
            "skipped": skipped,
            "tierB_entries": sum(1 for p in priced if p["tier_e"] == "B-uw"),
            "expired_before_exit": sum(1 for p in priced if p["expired_before_exit"]),
            "_priced": priced,
        }

    _uw_cache_save()

    for cfg in configs:
        r = results[cfg]
        flag = "  <<< HEADLINE (canonical Connors)" if cfg == HEADLINE_CONFIG else ""
        print("-" * 70)
        print(f"CONFIG {cfg}{flag}")
        print(f"  skipped={r['skipped']}  tierB_entries={r['tierB_entries']}  "
              f"expired_before_exit={r['expired_before_exit']}")
        print(f"  FACTOR  options-P&L:{fmt(r['factor'])}")
        print(f"  CONTROL SPY same-model :{fmt(r['control'])}")
        print(f"  ALPHA   (factor-control):{fmt(r['alpha'])}")
        print(f"  GEX+ slice (DIRECTIONAL-ONLY, small N):{fmt(r['gex_pos_alpha'])}")

    print("\n" + "=" * 70)
    print("STEP 5 — VALIDATION GATE (non-arbitrable)")
    print("=" * 70)
    val = validation(trades, vix, vxn, close_maps, results)
    pv, mr = val["proxy_vs_uw"], val["modeled_vs_real"]
    print("5a proxy(VIX/VXN)-vs-UW  :", json.dumps(pv))
    print("5b modeled(BS-mid)-vs-real:", json.dumps({k: v for k, v in mr.items() if k != "detail"}))
    for c in mr.get("detail", []):
        print("     ", c)

    # strip the heavy per-trade lists before dumping
    dump = {"configs": {c: {k: v for k, v in results[c].items() if k != "_priced"} for c in configs},
            "validation": val}
    json.dump(dump, open(r"C:\temp\stage2_results.json", "w"), indent=2)
    print("\nresults -> C:\\temp\\stage2_results.json")
    return results, val


if __name__ == "__main__":
    main()
