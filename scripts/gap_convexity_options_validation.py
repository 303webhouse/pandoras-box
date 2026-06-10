"""
Gap Convexity: Options-Layer Validation
========================================
Tests whether a non-directional structure (ATM straddle / ~5% OTM strangle)
entered at T0 close (post-IV-crush) would have profited on the secondary move
characterised in Phase 1. P&L is net of the entry premium.

Two tiers -- chosen by data availability:
  Tier A (NOW Q4, PLTR Q4): actual per-contract daily OHLC + NBBO quotes from
      /api/option-contract/{id}/historic. Entry = ask; exit = bid. Real spread.
  Tier B (8 in-window events): BS-modelled from /api/stock/{ticker}/volatility/
      term-structure?date=T0. Entry and exit at mid; applies a stated -12%
      spread haircut to P&L and also reports intrinsic-only floor.

Reuses Phase 1 OHLC output (CSV) -- does NOT refetch price bars.

Output:
  docs/strategy-reviews/gap-convexity-options-validation-2026-06-02.md
  docs/strategy-reviews/gap-convexity-options-validation-2026-06-02.csv

Run: railway run --service pandoras-box python scripts/gap_convexity_options_validation.py
"""

import csv
import math
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

UW_BASE     = "https://api.unusualwhales.com"
UW_API_KEY  = os.getenv("UW_API_KEY", "")
RISK_FREE   = 0.045          # annualised, ~current 10y rate
SPREAD_HAIRCUT = 0.12        # Tier B mid-price haircut (12% of P&L)
CONVEX_THRESHOLD = 5.0       # % secondary move that flags CONVEX in Phase 1
PHASE1_CSV  = Path("docs/strategy-reviews/earnings-gap-characterization-2026-06-01.csv")
OUTPUT_DIR  = Path("docs/strategy-reviews")
OUTPUT_MD   = OUTPUT_DIR / "gap-convexity-options-validation-2026-06-02.md"
OUTPUT_CSV  = OUTPUT_DIR / "gap-convexity-options-validation-2026-06-02.csv"

# ---------------------------------------------------------------------------
# Event definitions (Phase 0 verified)
# ---------------------------------------------------------------------------
EVENTS = [
    # Tier A: actual historical quotes available (outside 30-day IV series limit)
    {"symbol":"NOW",  "label":"NOW Q4",  "t0":"2026-01-29","role":"beat-but-dropped fade",      "tier":"A"},
    {"symbol":"PLTR", "label":"PLTR Q4", "t0":"2026-02-03","role":"continuation-up",            "tier":"A"},
    # Tier B: BS-modelled from term-structure IV
    {"symbol":"NXPI", "label":"NXPI Q1", "t0":"2026-04-29","role":"monster continuation-up",    "tier":"B"},
    {"symbol":"F",    "label":"F Q1",    "t0":"2026-04-30","role":"non-tech, full window",       "tier":"B"},
    {"symbol":"TSN",  "label":"TSN Q2",  "t0":"2026-05-04","role":"non-tech up",                "tier":"B"},
    {"symbol":"PLTR", "label":"PLTR Q1", "t0":"2026-05-05","role":"FAILED gap / negative case", "tier":"B"},
    {"symbol":"NVDA", "label":"NVDA Q1", "t0":"2026-05-21","role":"MUTED control",              "tier":"B"},
    {"symbol":"WMT",  "label":"WMT Q1",  "t0":"2026-05-21","role":"non-tech, partial window",   "tier":"B"},
    {"symbol":"ZS",   "label":"ZS Q3",   "t0":"2026-05-27","role":"gap-down, short window",     "tier":"B"},
    {"symbol":"DELL", "label":"DELL Q1", "t0":"2026-05-29","role":"monster gap, minimal window","tier":"B"},
]

CONTROLS = {"PLTR Q1", "NVDA Q1"}   # must show a loss


# ---------------------------------------------------------------------------
# Black-Scholes engine (replicated from backend/utils/options_math.py primitives)
# ---------------------------------------------------------------------------

def _ncdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def bs_price(S: float, K: float, T_years: float, r: float,
             iv: float, opt_type: str) -> float | None:
    """Vanilla Black-Scholes call/put price. Returns None on degenerate input."""
    if iv is None or iv <= 0 or T_years <= 0 or S <= 0 or K <= 0:
        return None
    try:
        sqT = math.sqrt(T_years)
        d1  = (math.log(S / K) + (r + 0.5 * iv * iv) * T_years) / (iv * sqT)
        d2  = d1 - iv * sqT
        disc = math.exp(-r * T_years)
        if opt_type.lower() == "call":
            return max(0.0, S * _ncdf(d1) - K * disc * _ncdf(d2))
        else:
            return max(0.0, K * disc * _ncdf(-d2) - S * _ncdf(-d1))
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def intrinsic(S: float, K: float, opt_type: str) -> float:
    if opt_type.lower() == "call":
        return max(0.0, S - K)
    return max(0.0, K - S)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hdr():
    return {"Authorization": f"Bearer {UW_API_KEY}", "Accept": "application/json"}


def _get(url, params=None, timeout=15.0):
    with httpx.Client(timeout=timeout) as c:
        return c.get(url, headers=_hdr(), params=params or {})


def nearest_strike(price: float) -> float:
    """Round to nearest sensible strike increment."""
    if price < 20:
        inc = 0.50
    elif price < 100:
        inc = 2.50
    else:
        inc = 5.0
    return round(round(price / inc) * inc, 2)


def strike_to_occ(price: float) -> str:
    """Format strike as 8-digit OCC integer string (price * 1000)."""
    return f"{int(round(price * 1000)):08d}"


def build_occ(ticker: str, expiry_date: str, opt_type: str, strike: float) -> str:
    """Build OCC symbol: TICKER + YYMMDD + C/P + 8-digit-strike."""
    yy = expiry_date[2:4]
    mm = expiry_date[5:7]
    dd = expiry_date[8:10]
    t  = "C" if opt_type.lower() == "call" else "P"
    return f"{ticker.upper()}{yy}{mm}{dd}{t}{strike_to_occ(strike)}"


def load_phase1_csv() -> dict:
    """Load Phase 1 output CSV as label -> row dict."""
    rows = {}
    with open(PHASE1_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows[row["label"]] = row
    return rows


def _pct(s: str) -> float | None:
    """Parse '+12.3%' / 'PENDING' -> float or None."""
    if not s or s.strip() in ("PENDING", "N/A", "ERROR", ""):
        return None
    try:
        return float(s.replace("%", "").replace("+", "").strip())
    except ValueError:
        return None


def _fmt_rop(val) -> str:
    if val is None:
        return "PENDING"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.0f}%"


def _fmt_cost(val) -> str:
    if val is None:
        return "N/A"
    return f"{val:.1f}%"


# ---------------------------------------------------------------------------
# Phase 1 secondary-move magnitude segmentation
# ---------------------------------------------------------------------------

def secondary_move_pct(p1_row: dict) -> float | None:
    """Max abs secondary excursion from Phase 1 T+5 window (or T+3 if T+5 pending)."""
    up5 = _pct(p1_row.get("up_5", ""))
    dn5 = _pct(p1_row.get("dn_5", ""))
    if up5 is not None and dn5 is not None:
        return max(abs(up5), abs(dn5))
    up3 = _pct(p1_row.get("drift_t3", ""))
    if up3 is not None:
        return abs(up3)
    return None


def move_bucket(pct: float | None) -> str:
    if pct is None:
        return "PENDING"
    if pct > 10:
        return "big(>10%)"
    if pct >= CONVEX_THRESHOLD:
        return "moderate(5-10%)"
    return "sub-5%"


# ---------------------------------------------------------------------------
# TIER A: actual per-contract historical quotes
# ---------------------------------------------------------------------------

def fetch_contract_historic(symbol: str, limit: int = 60) -> list | None:
    """
    GET /api/option-contract/{symbol}/historic
    Returns list of daily rows sorted ascending by date, or None on error.
    """
    url = f"{UW_BASE}/api/option-contract/{symbol}/historic"
    r = _get(url, params={"limit": limit})
    if r.status_code != 200:
        return None
    rows = r.json().get("chains", r.json().get("data", []))
    if not rows:
        return None
    rows.sort(key=lambda x: x.get("date", ""))
    return rows


def find_contract_atm(ticker: str, expiry: str, opt_type: str,
                      t0_close: float) -> tuple[str | None, float | None, list | None]:
    """
    Try candidate strikes around t0_close and return the first one
    that has historic data. Returns (symbol, strike, rows) or (None, None, None).
    """
    base = nearest_strike(t0_close)
    # Build candidate strikes: nearest first, then ±1 and ±2 increments
    if t0_close < 20:
        inc = 0.50
    elif t0_close < 100:
        inc = 2.50
    else:
        inc = 5.0
    candidates = sorted(
        set([base, base - inc, base + inc, base - 2*inc, base + 2*inc,
             round(t0_close), round(t0_close * 2) / 2]),   # also try exact round
        key=lambda k: abs(k - t0_close)
    )
    for strike in candidates:
        if strike <= 0:
            continue
        sym = build_occ(ticker, expiry, opt_type, strike)
        rows = fetch_contract_historic(sym, limit=60)
        if rows:
            return sym, strike, rows
    return None, None, None


def tier_a_contracts(ticker: str, t0: str, t0_close: float) -> dict | None:
    """
    Discover the nearest expiry >=14 days and find working call/put contracts
    for ATM straddle and ~5% OTM strangle.
    Returns a dict of contract data or None if discovery fails.
    """
    # Determine expiry: scan forward until we find a Friday >=14 days out
    # then pick the nearest monthly/weekly that has data
    t0_dt = date.fromisoformat(t0)
    expiry_candidates = []
    d = t0_dt + timedelta(days=14)
    while len(expiry_candidates) < 6:
        if d.weekday() == 4:   # Friday
            expiry_candidates.append(d.isoformat())
        d += timedelta(days=1)

    # Try to find an ATM call on each candidate expiry
    atm_call_sym = atm_call_rows = atm_expiry = atm_strike = None
    for exp in expiry_candidates:
        sym, strike, rows = find_contract_atm(ticker, exp, "call", t0_close)
        if sym and rows:
            atm_call_sym, atm_strike, atm_call_rows, atm_expiry = sym, strike, rows, exp
            break
    if not atm_call_sym:
        return None

    dte = (date.fromisoformat(atm_expiry) - t0_dt).days

    # ATM put at same strike + expiry
    atm_put_sym = build_occ(ticker, atm_expiry, "put", atm_strike)
    atm_put_rows = fetch_contract_historic(atm_put_sym, limit=60)

    # OTM strangle: call at +5%, put at -5%
    otm_call_strike = nearest_strike(t0_close * 1.05)
    otm_put_strike  = nearest_strike(t0_close * 0.95)
    if otm_call_strike == atm_strike:
        inc = 5.0 if t0_close >= 100 else 2.5
        otm_call_strike = atm_strike + inc
    if otm_put_strike == atm_strike:
        inc = 5.0 if t0_close >= 100 else 2.5
        otm_put_strike = atm_strike - inc

    otm_call_sym  = build_occ(ticker, atm_expiry, "call", otm_call_strike)
    otm_call_rows = fetch_contract_historic(otm_call_sym, limit=60)
    otm_put_sym   = build_occ(ticker, atm_expiry, "put",  otm_put_strike)
    otm_put_rows  = fetch_contract_historic(otm_put_sym, limit=60)

    return {
        "expiry":        atm_expiry,
        "dte":           dte,
        "atm_strike":    atm_strike,
        "otm_call_strike": otm_call_strike,
        "otm_put_strike":  otm_put_strike,
        "atm_call":      {"sym": atm_call_sym,  "rows": atm_call_rows},
        "atm_put":       {"sym": atm_put_sym,   "rows": atm_put_rows},
        "otm_call":      {"sym": otm_call_sym,  "rows": otm_call_rows},
        "otm_put":       {"sym": otm_put_sym,   "rows": otm_put_rows},
    }


def quote_at_date(rows: list | None, target_date: str, side: str) -> float | None:
    """
    Get bid or ask for a contract on a specific date.
    side: 'ask' for entry, 'bid' for exit.
    Falls back to last_price if nbbo is missing.
    """
    if not rows:
        return None
    for row in rows:
        if row.get("date") == target_date:
            nbbo = row.get(f"nbbo_{side}")
            if nbbo is not None:
                try:
                    v = float(nbbo)
                    if v > 0:
                        return v
                except (ValueError, TypeError):
                    pass
            # fallback: last price (use for both bid/ask)
            lp = row.get("last_price")
            if lp is not None:
                try:
                    return float(lp)
                except (ValueError, TypeError):
                    pass
    return None


def tn_date_from_rows(rows: list, t0: str, n: int) -> str | None:
    """Find the date of T+n trading session from a contract's historic rows."""
    dates = sorted(set(r.get("date", "") for r in rows))
    if t0 not in dates:
        return None
    idx = dates.index(t0)
    target_idx = idx + n
    if target_idx < len(dates):
        return dates[target_idx]
    return None


def price_tier_a(contracts: dict, t0: str) -> dict:
    """
    Compute entry and exit prices using Tier A actual quotes.
    Entry: ask at T0.  Exit: bid at T+3, T+5, T+10.
    """
    def _entry(leg_rows, leg_sym):
        q = quote_at_date(leg_rows, t0, "ask")
        if q is None:
            print(f"    WARNING: no ask on T0 for {leg_sym}")
        return q

    def _exit(leg_rows, t0_rows_ref, n, leg_sym):
        # Use ATM call rows as the trading-calendar reference
        tgt_date = tn_date_from_rows(t0_rows_ref, t0, n)
        if tgt_date is None:
            return None, None
        q = quote_at_date(leg_rows, tgt_date, "bid")
        return tgt_date, q

    ref_rows = contracts["atm_call"]["rows"] or []

    # ATM call/put entries
    ac_e = _entry(contracts["atm_call"]["rows"], contracts["atm_call"]["sym"])
    ap_e = _entry(contracts["atm_put"]["rows"],  contracts["atm_put"]["sym"])
    straddle_entry = (ac_e or 0) + (ap_e or 0) if (ac_e and ap_e) else None

    # OTM call/put entries
    oc_e = _entry(contracts["otm_call"]["rows"], contracts["otm_call"]["sym"])
    op_e = _entry(contracts["otm_put"]["rows"],  contracts["otm_put"]["sym"])
    strangle_entry = (oc_e or 0) + (op_e or 0) if (oc_e and op_e) else None

    exits = {}
    for n in (3, 5, 10):
        t3_date, ac_x = _exit(contracts["atm_call"]["rows"], ref_rows, n, contracts["atm_call"]["sym"])
        _,        ap_x = _exit(contracts["atm_put"]["rows"],  ref_rows, n, contracts["atm_put"]["sym"])
        _,        oc_x = _exit(contracts["otm_call"]["rows"], ref_rows, n, contracts["otm_call"]["sym"])
        _,        op_x = _exit(contracts["otm_put"]["rows"],  ref_rows, n, contracts["otm_put"]["sym"])

        straddle_exit  = (ac_x or 0) + (ap_x or 0) if (ac_x is not None and ap_x is not None) else None
        strangle_exit  = (oc_x or 0) + (op_x or 0) if (oc_x is not None and op_x is not None) else None
        exits[n] = {
            "date":           t3_date,
            "straddle_exit":  straddle_exit,
            "strangle_exit":  strangle_exit,
        }

    return {
        "tier":           "A",
        "expiry":         contracts["expiry"],
        "dte":            contracts["dte"],
        "atm_strike":     contracts["atm_strike"],
        "otm_call_strike": contracts["otm_call_strike"],
        "otm_put_strike":  contracts["otm_put_strike"],
        "straddle_entry": straddle_entry,
        "strangle_entry": strangle_entry,
        "exits":          exits,
        "spread_note":    "entry=ask, exit=bid (actual NBBO)",
    }


# ---------------------------------------------------------------------------
# TIER B: BS-modelled from term-structure IV
# ---------------------------------------------------------------------------

def fetch_term_structure(ticker: str, t0: str) -> list | None:
    """GET /api/stock/{ticker}/volatility/term-structure?date=T0"""
    url = f"{UW_BASE}/api/stock/{ticker}/volatility/term-structure"
    r = _get(url, params={"date": t0})
    if r.status_code != 200:
        return None
    rows = r.json().get("data", [])
    return rows if rows else None


def pick_expiry_row(ts_rows: list, t0: str, min_dte: int = 14) -> dict | None:
    """Nearest expiry row with DTE >= min_dte."""
    t0_dt = date.fromisoformat(t0)
    valid = []
    for row in ts_rows:
        dte = row.get("dte")
        if dte is None:
            expiry_str = row.get("expiry")
            if expiry_str:
                dte = (date.fromisoformat(expiry_str) - t0_dt).days
        if dte is not None and int(dte) >= min_dte:
            valid.append((int(dte), row))
    if not valid:
        return None
    valid.sort(key=lambda x: x[0])
    return valid[0][1]


def price_tier_b(ticker: str, t0: str, t0_close: float,
                 ts_rows: list, p1_row: dict) -> dict:
    """
    Price entry and exits using BS model.
    """
    exp_row = pick_expiry_row(ts_rows, t0)
    if not exp_row:
        return {"tier": "B", "error": "no expiry >=14 DTE in term-structure"}

    expiry    = exp_row.get("expiry", "?")
    dte       = int(exp_row.get("dte", 0))
    iv_entry  = float(exp_row.get("volatility", 0))
    T_entry   = dte / 365.0

    atm_strike  = nearest_strike(t0_close)
    otm_call_k  = nearest_strike(t0_close * 1.05)
    otm_put_k   = nearest_strike(t0_close * 0.95)
    if otm_call_k == atm_strike:
        inc = 5.0 if t0_close >= 100 else 2.5
        otm_call_k = atm_strike + inc
    if otm_put_k == atm_strike:
        inc = 5.0 if t0_close >= 100 else 2.5
        otm_put_k = atm_strike - inc

    # Entry prices at T0 (mid, no spread)
    atm_call_e  = bs_price(t0_close, atm_strike,  T_entry, RISK_FREE, iv_entry, "call")
    atm_put_e   = bs_price(t0_close, atm_strike,  T_entry, RISK_FREE, iv_entry, "put")
    otm_call_e  = bs_price(t0_close, otm_call_k,  T_entry, RISK_FREE, iv_entry, "call")
    otm_put_e   = bs_price(t0_close, otm_put_k,   T_entry, RISK_FREE, iv_entry, "put")

    straddle_entry = (atm_call_e + atm_put_e) if (atm_call_e and atm_put_e) else None
    strangle_entry = (otm_call_e + otm_put_e) if (otm_call_e and otm_put_e) else None

    exits = {}
    for n in (3, 5, 10):
        drift_val = _pct(p1_row.get(f"drift_t{n}", "PENDING"))
        if drift_val is None:
            exits[n] = {"straddle_exit": None, "strangle_exit": None,
                        "straddle_intr": None, "strangle_intr": None,
                        "T_remaining": None}
            continue

        S_exit       = t0_close * (1.0 + drift_val / 100.0)
        # Approximate remaining calendar days: each trading day ~1.4 calendar days
        remaining_cd = max(0.0, dte - n * 1.4)
        T_remaining  = remaining_cd / 365.0

        # IV flat assumption
        ac_x = bs_price(S_exit, atm_strike, T_remaining, RISK_FREE, iv_entry, "call")
        ap_x = bs_price(S_exit, atm_strike, T_remaining, RISK_FREE, iv_entry, "put")
        oc_x = bs_price(S_exit, otm_call_k, T_remaining, RISK_FREE, iv_entry, "call")
        op_x = bs_price(S_exit, otm_put_k,  T_remaining, RISK_FREE, iv_entry, "put")

        straddle_exit = (ac_x + ap_x) if (ac_x is not None and ap_x is not None) else None
        strangle_exit = (oc_x + op_x) if (oc_x is not None and op_x is not None) else None

        # Intrinsic floor
        straddle_intr = intrinsic(S_exit, atm_strike, "call") + intrinsic(S_exit, atm_strike, "put")
        strangle_intr = intrinsic(S_exit, otm_call_k, "call") + intrinsic(S_exit, otm_put_k,  "put")

        exits[n] = {
            "S_exit":          S_exit,
            "T_remaining_d":   remaining_cd,
            "straddle_exit":   straddle_exit,
            "strangle_exit":   strangle_exit,
            "straddle_intr":   straddle_intr,
            "strangle_intr":   strangle_intr,
        }

    return {
        "tier":            "B",
        "expiry":          expiry,
        "dte":             dte,
        "iv_entry":        iv_entry,
        "atm_strike":      atm_strike,
        "otm_call_strike": otm_call_k,
        "otm_put_strike":  otm_put_k,
        "straddle_entry":  straddle_entry,
        "strangle_entry":  strangle_entry,
        "exits":           exits,
        "spread_note":     f"MODELED mid; -{SPREAD_HAIRCUT*100:.0f}% P&L haircut for spread",
    }


# ---------------------------------------------------------------------------
# P&L calculation
# ---------------------------------------------------------------------------

def compute_pnl(entry, exit_val, tier: str) -> tuple[float | None, float | None]:
    """
    Returns (pnl_dollars, return_on_premium_pct).
    Tier B applies spread haircut to exit value.
    """
    if entry is None or exit_val is None:
        return None, None
    if tier == "B":
        # Haircut: entry at ask is ~mid*(1+half_spread), exit at bid is ~mid*(1-half_spread)
        # Approximate with flat haircut on P&L
        pnl = exit_val - entry
        pnl_adj = pnl - abs(entry) * SPREAD_HAIRCUT   # deduct haircut from exit
    else:
        pnl = exit_val - entry
        pnl_adj = pnl
    rop = (pnl_adj / entry * 100) if entry > 0 else None
    return pnl_adj, rop


# ---------------------------------------------------------------------------
# Per-event analysis
# ---------------------------------------------------------------------------

def analyse_event(event: dict, p1_row: dict,
                  tier_a_data: dict, tier_b_iv: dict) -> dict:
    label  = event["label"]
    ticker = event["symbol"]
    t0     = event["t0"]
    tier   = event["tier"]
    role   = event["role"]

    t0_close = float(p1_row.get("t0_close", 0) or 0)
    gap_pct  = _pct(p1_row.get("gap_pct",  "0")) or 0.0
    move_pct = secondary_move_pct(p1_row)
    bucket   = move_bucket(move_pct)

    if tier == "A":
        contracts = tier_a_data.get(label)
        if not contracts:
            return _err(event, "Tier A contract discovery failed")
        priced = price_tier_a(contracts, t0)
    else:
        ts_rows = tier_b_iv.get(label)
        if not ts_rows:
            return _err(event, "No term-structure IV returned")
        priced = price_tier_b(ticker, t0, t0_close, ts_rows, p1_row)
        if "error" in priced:
            return _err(event, priced["error"])

    straddle_e = priced.get("straddle_entry")
    strangle_e = priced.get("strangle_entry")
    straddle_cost_pct = (straddle_e / t0_close * 100) if (straddle_e and t0_close) else None
    strangle_cost_pct = (strangle_e / t0_close * 100) if (strangle_e and t0_close) else None

    rows_by_n = {}
    for n in (3, 5, 10):
        ex = priced["exits"].get(n, {})
        straddle_pl, straddle_rop = compute_pnl(straddle_e, ex.get("straddle_exit"), tier)
        strangle_pl, strangle_rop = compute_pnl(strangle_e, ex.get("strangle_exit"), tier)
        # Intrinsic floor (Tier B only)
        straddle_intr_rop = strangle_intr_rop = None
        if tier == "B":
            _, straddle_intr_rop = compute_pnl(straddle_e, ex.get("straddle_intr"), tier)
            _, strangle_intr_rop = compute_pnl(strangle_e, ex.get("strangle_intr"), tier)
        rows_by_n[n] = {
            "straddle_rop":      straddle_rop,
            "strangle_rop":      strangle_rop,
            "straddle_intr_rop": straddle_intr_rop,
            "strangle_intr_rop": strangle_intr_rop,
        }

    # Verdict: at T+5, does the primary structure (straddle) profit?
    t5_rop = rows_by_n[5]["straddle_rop"]
    if t5_rop is None:
        verdict = "PENDING"
    elif t5_rop > 0:
        verdict = "WIN"
    else:
        verdict = "LOSS"

    return {
        "label":              label,
        "symbol":             ticker,
        "t0":                 t0,
        "role":               role,
        "tier":               tier,
        "move_bucket":        bucket,
        "move_pct":           f"{move_pct:.1f}%" if move_pct is not None else "PENDING",
        "gap_pct":            p1_row.get("gap_pct", ""),
        "hold_fail":          p1_row.get("hold_fail", ""),
        "expiry":             priced.get("expiry", "?"),
        "dte":                priced.get("dte", "?"),
        "iv_entry":           f"{priced.get('iv_entry',0)*100:.1f}%" if tier == "B" else "actual",
        "atm_strike":         priced.get("atm_strike", "?"),
        "otm_call_strike":    priced.get("otm_call_strike", "?"),
        "otm_put_strike":     priced.get("otm_put_strike", "?"),
        "straddle_cost_pct":  _fmt_cost(straddle_cost_pct),
        "strangle_cost_pct":  _fmt_cost(strangle_cost_pct),
        # T+3
        "straddle_rop_t3":    _fmt_rop(rows_by_n[3]["straddle_rop"]),
        "strangle_rop_t3":    _fmt_rop(rows_by_n[3]["strangle_rop"]),
        # T+5 (primary result)
        "straddle_rop_t5":    _fmt_rop(rows_by_n[5]["straddle_rop"]),
        "strangle_rop_t5":    _fmt_rop(rows_by_n[5]["strangle_rop"]),
        "straddle_intr_t5":   _fmt_rop(rows_by_n[5]["straddle_intr_rop"]),
        "strangle_intr_t5":   _fmt_rop(rows_by_n[5]["strangle_intr_rop"]),
        # T+10
        "straddle_rop_t10":   _fmt_rop(rows_by_n[10]["straddle_rop"]),
        "strangle_rop_t10":   _fmt_rop(rows_by_n[10]["strangle_rop"]),
        "verdict":            verdict,
        "spread_note":        priced.get("spread_note", ""),
        "error":              "",
    }


def _err(event: dict, msg: str) -> dict:
    base = {k: "ERROR" for k in (
        "straddle_cost_pct","strangle_cost_pct",
        "straddle_rop_t3","strangle_rop_t3",
        "straddle_rop_t5","strangle_rop_t5",
        "straddle_intr_t5","strangle_intr_t5",
        "straddle_rop_t10","strangle_rop_t10",
    )}
    base.update({
        "label": event["label"], "symbol": event["symbol"], "t0": event["t0"],
        "role": event["role"], "tier": event["tier"],
        "move_bucket": "ERROR", "move_pct": "ERROR",
        "gap_pct": "", "hold_fail": "", "expiry": "?", "dte": "?",
        "iv_entry": "?", "atm_strike": "?", "otm_call_strike": "?", "otm_put_strike": "?",
        "verdict": "ERROR", "spread_note": "", "error": msg,
    })
    return base


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

BUCKET_ORDER = ["big(>10%)", "moderate(5-10%)", "sub-5%", "PENDING"]

MD_LEAD_COLS = [
    ("STRADDLE$",   "straddle_cost_pct",  9),
    ("STRANGLE$",   "strangle_cost_pct",  9),
    ("STR.ROP@T5",  "straddle_rop_t5",   11),
    ("SNG.ROP@T5",  "strangle_rop_t5",   11),
    ("STR.ROP@T3",  "straddle_rop_t3",   11),
    ("SNG.ROP@T3",  "strangle_rop_t3",   11),
    ("STR.ROP@T10", "straddle_rop_t10",  11),
    ("SNG.ROP@T10", "strangle_rop_t10",  11),
    ("INTR.FL@T5",  "straddle_intr_t5",  10),
    ("VERDICT",     "verdict",            7),
]

MD_TRAILING_COLS = [
    ("LABEL",  "label",     9),
    ("TIER",   "tier",      4),
    ("MOVE%",  "move_pct",  7),
    ("BUCKET", "move_bucket", 12),
    ("GAP%",   "gap_pct",   7),
    ("H/F",    "hold_fail", 5),
    ("EXPIRY", "expiry",    10),
    ("DTE",    "dte",       4),
    ("IV",     "iv_entry",  8),
    ("ATM_K",  "atm_strike",6),
]

CSV_COLS = [
    "label","symbol","t0","role","tier","move_bucket","move_pct","gap_pct","hold_fail",
    "expiry","dte","iv_entry","atm_strike","otm_call_strike","otm_put_strike",
    "straddle_cost_pct","strangle_cost_pct",
    "straddle_rop_t3","strangle_rop_t3",
    "straddle_rop_t5","strangle_rop_t5","straddle_intr_t5","strangle_intr_t5",
    "straddle_rop_t10","strangle_rop_t10",
    "verdict","spread_note","error",
]


def bucket_stats(results: list, bucket: str, col: str) -> str:
    """Mean ROP for a bucket+column where data is available and not ERROR."""
    vals = []
    for r in results:
        if r.get("move_bucket") != bucket:
            continue
        v = r.get(col, "")
        if v in ("PENDING", "ERROR", ""):
            continue
        try:
            vals.append(float(v.replace("%","").replace("+","")))
        except ValueError:
            pass
    if not vals:
        return "—"
    return f"{sum(vals)/len(vals):+.0f}%"


def write_markdown(results: list, run_date: str, path: Path):
    lines = []
    lines += [
        "# Gap Convexity: Options-Layer Validation",
        "",
        f"**Brief date:** 2026-06-02  |  **Run date:** {run_date}",
        "",
        "**Primary question:** does a non-directional structure entered at T0 close",
        "(post-IV-crush) cost less than the secondary move it captures?",
        "",
        "**Tier A** (NOW Q4, PLTR Q4): actual NBBO bid/ask from `/api/option-contract/{id}/historic`.",
        "Entry = ask, exit = bid. Real spread, no modelling.",
        "",
        f"**Tier B** (8 events): BS-modelled from `/volatility/term-structure`. Entry/exit at mid;",
        f"P&L adjusted -{SPREAD_HAIRCUT*100:.0f}% for spread. Intrinsic floor shown separately.",
        "",
        "ROP = return on premium = (exit − entry) / entry. Positive = profitable.",
        "",
        "---",
        "",
    ]

    # Segment by move bucket
    for bucket in BUCKET_ORDER:
        bucket_rows = [r for r in results if r.get("move_bucket") == bucket]
        if not bucket_rows:
            continue

        lines.append(f"## {bucket} secondary move")
        lines.append("")

        all_cols = MD_LEAD_COLS + MD_TRAILING_COLS
        hdr = "| " + " | ".join(h for h,_,_ in all_cols) + " |"
        sep = "| " + " | ".join("-"*max(w,len(h)) for h,_,w in all_cols) + " |"
        lines += [hdr, sep]

        for r in bucket_rows:
            cells = [str(r.get(k,"")) for _,k,_ in all_cols]
            lines.append("| " + " | ".join(cells) + " |")

        lines.append("")
        # Bucket aggregate
        st_mean = bucket_stats(bucket_rows, bucket, "straddle_rop_t5")
        sn_mean = bucket_stats(bucket_rows, bucket, "strangle_rop_t5")
        wins_st = sum(1 for r in bucket_rows if r.get("verdict")=="WIN")
        losses_st = sum(1 for r in bucket_rows if r.get("verdict")=="LOSS")
        pend = sum(1 for r in bucket_rows if r.get("verdict")=="PENDING")
        lines.append(f"**Bucket aggregate (T+5):** "
                     f"straddle avg ROP={st_mean}, strangle avg ROP={sn_mean} | "
                     f"{wins_st} WIN / {losses_st} LOSS / {pend} PENDING")
        lines.append("")

    lines += [
        "---",
        "",
        "## Overall aggregate (T+5, excludes PENDING)",
        "",
    ]

    conv_rows = [r for r in results if r.get("move_bucket") != "PENDING"
                 and r.get("verdict") not in ("PENDING","ERROR")]
    wins = sum(1 for r in conv_rows if r.get("verdict") == "WIN")
    losses = sum(1 for r in conv_rows if r.get("verdict") == "LOSS")

    all_rop_st = []
    all_rop_sn = []
    for r in conv_rows:
        v = r.get("straddle_rop_t5","")
        try:
            all_rop_st.append(float(v.replace("%","").replace("+","")))
        except ValueError:
            pass
        v = r.get("strangle_rop_t5","")
        try:
            all_rop_sn.append(float(v.replace("%","").replace("+","")))
        except ValueError:
            pass

    avg_st = f"{sum(all_rop_st)/len(all_rop_st):+.0f}%" if all_rop_st else "—"
    avg_sn = f"{sum(all_rop_sn)/len(all_rop_sn):+.0f}%" if all_rop_sn else "—"

    lines += [
        f"- Straddle: {wins}/{wins+losses} WIN | avg ROP = {avg_st}",
        f"- Strangle: avg ROP = {avg_sn}",
        "",
    ]

    # Controls check
    controls = [r for r in results if r["label"] in CONTROLS]
    lines.append("## Controls check (must be LOSS)")
    lines.append("")
    for r in controls:
        verdict = r.get("verdict","?")
        ok_flag = "PASS" if verdict == "LOSS" else "FAIL — BUG" if verdict == "WIN" else verdict
        lines.append(f"- **{r['label']}** ({r['role']}): verdict={verdict} straddle_rop_t5={r.get('straddle_rop_t5')} → **{ok_flag}**")
    lines.append("")

    lines += [
        "---",
        "",
        "## Assumptions and caveats",
        "",
        "- **Expiry rule:** nearest listed standard expiry >=14 calendar days after T0.",
        f"- **Strike rule:** ATM = nearest ${5} or ${2.5} increment; strangle = ±5% OTM from ATM.",
        "- **Tier B IV:** post-crush ATM IV from UW `volatility/term-structure` at T0 date. IV held flat to exit (conservative; IV decay improves strangle, hurts straddle slightly).",
        f"- **Tier B spread:** -{SPREAD_HAIRCUT*100:.0f}% of entry cost deducted as spread proxy. Intrinsic floor = max(0, |S-K|) with no time value — the worst-case P&L.",
        "- **Tier A spread:** actual NBBO bid (entry=ask, exit=bid). Covers real transaction cost.",
        "- **Risk-free rate:** 4.5% annualised throughout.",
        "- **No dividends / American exercise adjustment:** <5% error for near-ATM short-DTE equity options.",
        "*Re-run ~2026-06-15 to fill PENDING cells for ZS and DELL.*",
        "",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Markdown written: {path}")


def write_csv(results: list, path: Path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for r in results:
            w.writerow(r)
    print(f"  CSV written: {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not UW_API_KEY:
        print("ERROR: UW_API_KEY not set. Run with: railway run --service pandoras-box ...")
        sys.exit(1)

    today_str = date.today().isoformat()
    print(f"Gap Convexity Options Validation -- {today_str}")
    print()

    # Load Phase 1 output
    if not PHASE1_CSV.exists():
        print(f"ERROR: Phase 1 CSV not found at {PHASE1_CSV}")
        sys.exit(1)
    p1 = load_phase1_csv()
    print(f"Phase 1 CSV loaded: {len(p1)} events")

    # ── Tier A: fetch actual contract data ──
    print()
    print("Fetching Tier A contract data (NOW Q4, PLTR Q4)...")
    tier_a_data = {}
    for ev in [e for e in EVENTS if e["tier"] == "A"]:
        label     = ev["label"]
        p1_row    = p1.get(label, {})
        t0_close  = float(p1_row.get("t0_close", 0) or 0)
        print(f"  {label}: t0_close={t0_close}")
        contracts = tier_a_contracts(ev["symbol"], ev["t0"], t0_close)
        if contracts:
            tier_a_data[label] = contracts
            print(f"    expiry={contracts['expiry']} DTE={contracts['dte']} "
                  f"atm_strike={contracts['atm_strike']} "
                  f"otm_call={contracts['otm_call_strike']} otm_put={contracts['otm_put_strike']}")
        else:
            print(f"    FAILED -- no contracts found")

    # ── Tier B: fetch term-structure IV ──
    print()
    print("Fetching Tier B term-structure IV (8 in-window events)...")
    tier_b_iv = {}
    for ev in [e for e in EVENTS if e["tier"] == "B"]:
        label  = ev["label"]
        ticker = ev["symbol"]
        t0     = ev["t0"]
        rows = fetch_term_structure(ticker, t0)
        if rows:
            exp_row = pick_expiry_row(rows, t0)
            if exp_row:
                iv = float(exp_row.get("volatility", 0))
                dte = exp_row.get("dte", "?")
                expiry = exp_row.get("expiry", "?")
                print(f"  {label}: expiry={expiry} DTE={dte} IV={iv:.3f}")
                tier_b_iv[label] = rows
            else:
                print(f"  {label}: OK but no expiry >=14 DTE")
        else:
            print(f"  {label}: FAILED")

    # ── Analyse all events ──
    print()
    print("Pricing structures...")
    results = []
    for ev in EVENTS:
        label = ev["label"]
        p1_row = p1.get(label, {})
        r = analyse_event(ev, p1_row, tier_a_data, tier_b_iv)
        if r["error"]:
            print(f"  {label}: ERROR -- {r['error']}")
        else:
            print(f"  {label}: straddle$={r['straddle_cost_pct']} "
                  f"rop@T5={r['straddle_rop_t5']} "
                  f"verdict={r['verdict']} bucket={r['move_bucket']}")
        results.append(r)

    # ── Controls check ──
    print()
    print("Controls check:")
    for r in results:
        if r["label"] in CONTROLS:
            ok = "PASS" if r["verdict"] == "LOSS" else f"!!! FAIL (verdict={r['verdict']})"
            print(f"  {r['label']}: {ok}  rop_t5={r['straddle_rop_t5']}")

    # ── Output ──
    print()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_markdown(results, today_str, OUTPUT_MD)
    write_csv(results, OUTPUT_CSV)
    print()
    print(f"Done. Output at {OUTPUT_MD}")


if __name__ == "__main__":
    main()
