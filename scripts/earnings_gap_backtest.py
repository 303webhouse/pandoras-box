"""
Earnings Gap Behavior Backtest -- 10-event, 2-season characterization.

Headline question: how often does a big gap produce a fast secondary move
(>=5% in either direction) that makes a cheap OTM option pay?

Metrics per event:
  Gap %, magnitude, hold/fail, volume ratio, gap fill day,
  PEAD drift at T+3 / T+5 / T+10, and the convexity check over T+1..T+5
  and T+1..T+10 (max up/down excursion from T0 close, flagged CONVEX if >=5%).

HARD RULE (Nick): only cells with a confirmed completed close are populated.
Today's session is always PENDING -- the data cutoff is derived from the last
completed bar UW returns, not a hardcoded date.

Run with:
  railway run --service pandoras-box python scripts/earnings_gap_backtest.py

Output:
  docs/strategy-reviews/earnings-gap-characterization-2026-06-01.md
  docs/strategy-reviews/earnings-gap-characterization-2026-06-01.csv
"""

import csv
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

UW_BASE = "https://api.unusualwhales.com"
UW_API_KEY = os.getenv("UW_API_KEY", "")
CONVEX_THRESHOLD = 5.0  # % move from T0 close that flags CONVEX

OUTPUT_DIR = Path("docs/strategy-reviews")
OUTPUT_MD  = OUTPUT_DIR / "earnings-gap-characterization-2026-06-01.md"
OUTPUT_CSV = OUTPUT_DIR / "earnings-gap-characterization-2026-06-01.csv"

# Phase 0 verified (UW authoritative). PLTR appears twice -- two events, same ticker.
# NXPI corrected: report_date 04-28 (not 04-27 per brief), T0 = 04-29.
EVENTS = [
    {"symbol": "NOW",  "label": "NOW Q4",  "report_date": "2026-01-28", "session": "AMC", "t0": "2026-01-29", "role": "beat-but-dropped fade"},
    {"symbol": "PLTR", "label": "PLTR Q4", "report_date": "2026-02-02", "session": "AMC", "t0": "2026-02-03", "role": "continuation-up"},
    {"symbol": "NXPI", "label": "NXPI Q1", "report_date": "2026-04-28", "session": "AMC", "t0": "2026-04-29", "role": "monster continuation-up"},
    {"symbol": "F",    "label": "F Q1",    "report_date": "2026-04-29", "session": "AMC", "t0": "2026-04-30", "role": "non-tech, full window"},
    {"symbol": "TSN",  "label": "TSN Q2",  "report_date": "2026-05-04", "session": "BMO", "t0": "2026-05-04", "role": "non-tech up"},
    {"symbol": "PLTR", "label": "PLTR Q1", "report_date": "2026-05-04", "session": "AMC", "t0": "2026-05-05", "role": "FAILED gap / negative case"},
    {"symbol": "NVDA", "label": "NVDA Q1", "report_date": "2026-05-20", "session": "AMC", "t0": "2026-05-21", "role": "MUTED control"},
    {"symbol": "WMT",  "label": "WMT Q1",  "report_date": "2026-05-21", "session": "BMO", "t0": "2026-05-21", "role": "non-tech, partial window"},
    {"symbol": "ZS",   "label": "ZS Q3",   "report_date": "2026-05-26", "session": "AMC", "t0": "2026-05-27", "role": "gap-down, short window"},
    {"symbol": "DELL", "label": "DELL Q1", "report_date": "2026-05-28", "session": "AMC", "t0": "2026-05-29", "role": "monster gap, minimal window"},
]


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_regular_bars(ticker: str) -> list | None:
    """
    Fetch regular-session daily bars from UW /api/stock/{ticker}/ohlc/1d.
    Returns bars sorted ascending by date (YYYY-MM-DD strings), or None on error.

    Field discovery from Phase 0: daily bars use 'date' field (start_time is None).
    All UW numeric values returned as strings -- cast explicitly.
    """
    symbol = ticker.upper()
    url = f"{UW_BASE}/api/stock/{symbol}/ohlc/1d"
    # date_from adds a server-side hint; UW may return ~1 year regardless.
    # Set it far back so we always cover the earliest event (NOW Q4, T0=2026-01-29).
    date_from = (date.today() - timedelta(days=400)).isoformat()
    params = {"date_from": date_from}
    headers = {"Authorization": f"Bearer {UW_API_KEY}", "Accept": "application/json"}

    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url, headers=headers, params=params)
    except Exception as e:
        print(f"  [{symbol}] request failed: {e}")
        return None

    if resp.status_code == 429:
        print(f"  [{symbol}] 429 rate limited -- aborting")
        return None
    if resp.status_code != 200:
        print(f"  [{symbol}] HTTP {resp.status_code}: {resp.text[:200]}")
        return None

    all_bars = resp.json().get("data", [])

    normalized = []
    for b in all_bars:
        if b.get("market_time") != "r":
            continue
        # 'date' field on daily bars; fall back to start_time just in case
        raw_date = b.get("date") or b.get("start_time")
        if not raw_date:
            continue
        date_str = str(raw_date)[:10]
        try:
            date.fromisoformat(date_str)
        except ValueError:
            continue
        try:
            o = float(b.get("open") or 0)
            h = float(b.get("high") or 0)
            l = float(b.get("low") or 0)
            c = float(b.get("close") or 0)
            v = int(b.get("total_volume") or b.get("volume") or 0)
        except (TypeError, ValueError):
            continue
        if o <= 0 or h <= 0 or l <= 0 or c <= 0:
            continue
        normalized.append({"date": date_str, "open": o, "high": h, "low": l, "close": c, "volume": v})

    normalized.sort(key=lambda b: b["date"])
    return normalized if normalized else None


def get_data_cutoff(bars: list) -> str | None:
    """
    Last confirmed-complete bar date: the most recent regular-session bar whose
    date is strictly before today (system date). Today's session may be open --
    any bar on today is treated as PENDING per Nick's hard rule.
    """
    today_str = date.today().isoformat()
    confirmed = [b for b in bars if b["date"] < today_str]
    return confirmed[-1]["date"] if confirmed else None


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def find_t0_index(bars: list, t0_date: str) -> int | None:
    """
    Index of T0 in sorted bars: first bar with date >= t0_date.
    For BMO events the bar date matches t0_date exactly.
    For AMC events the gap appears on the next trading session.
    """
    for i, b in enumerate(bars):
        if b["date"] >= t0_date:
            return i
    return None


def get_bar(bars: list, idx: int, data_cutoff: str):
    """
    Return bar at idx, "PENDING" if beyond cutoff, None if out of range.
    """
    if idx < 0 or idx >= len(bars):
        return None
    bar = bars[idx]
    if bar["date"] > data_cutoff:
        return "PENDING"
    return bar


def _fmt_pct(val: float, plus: bool = True) -> str:
    sign = "+" if (plus and val >= 0) else ""
    return f"{sign}{val:.1f}%"


def compute_gap_pct(t0_bar: dict, tm1_bar: dict) -> float:
    """(T0 open - T-1 close) / T-1 close * 100."""
    base = tm1_bar["close"]
    if base == 0:
        return 0.0
    return (t0_bar["open"] - base) / base * 100


def classify_magnitude(gap_pct: float) -> str:
    a = abs(gap_pct)
    if a < 3:
        return "small"
    if a <= 7:
        return "medium"
    return "large"


def compute_hold_fail(t0_bar: dict, gap_pct: float) -> str:
    """
    Classify T0 reaction.
    close_position = (close - low) / (high - low)
    Gap-up:   HOLD if >= 2/3, FAIL if <= 1/3, else NEUTRAL
    Gap-down: HOLD if <= 1/3, FAIL if >= 2/3, else NEUTRAL
    """
    h, l, c = t0_bar["high"], t0_bar["low"], t0_bar["close"]
    if h == l:
        return "NEUTRAL"
    cp = (c - l) / (h - l)
    if gap_pct > 0:
        if cp >= 2 / 3:
            return "HOLD"
        if cp <= 1 / 3:
            return "FAIL"
    else:
        if cp <= 1 / 3:
            return "HOLD"
        if cp >= 2 / 3:
            return "FAIL"
    return "NEUTRAL"


def compute_gap_fill(bars: list, t0_idx: int, tm1_close: float,
                     gap_pct: float, data_cutoff: str) -> str:
    """
    First session in T0..T+10 where the bar's range crosses back through T-1 close.
    Gap-up:   fill when bar low  <= T-1 close (stock pulled back to/through it).
    Gap-down: fill when bar high >= T-1 close (stock bounced back to/through it).
    Returns "T0", "T+N", "unfilled", or "PENDING" if window is incomplete.
    """
    gap_up = gap_pct > 0
    for offset in range(0, 11):
        bar = get_bar(bars, t0_idx + offset, data_cutoff)
        if bar is None:
            break
        if bar == "PENDING":
            return "PENDING"
        if gap_up and bar["low"] <= tm1_close:
            return "T0" if offset == 0 else f"T+{offset}"
        if not gap_up and bar["high"] >= tm1_close:
            return "T0" if offset == 0 else f"T+{offset}"
    return "unfilled"


def compute_drift(bars: list, t0_idx: int, t0_close: float,
                  n: int, data_cutoff: str) -> str:
    """
    % move from T0 close to T+n close.
    Returns "+X.X%" / "-X.X%" or "PENDING".
    Sign is absolute (+ = up, - = down regardless of gap direction).
    """
    bar = get_bar(bars, t0_idx + n, data_cutoff)
    if bar is None:
        return "PENDING"
    if bar == "PENDING":
        return "PENDING"
    if t0_close == 0:
        return "N/A"
    return _fmt_pct((bar["close"] - t0_close) / t0_close * 100)


def compute_volume_ratio(bars: list, t0_idx: int) -> str:
    """T0 volume / mean of prior 30 regular sessions."""
    t0_vol = bars[t0_idx]["volume"]
    prior = bars[max(0, t0_idx - 30):t0_idx]
    if not prior:
        return "N/A"
    avg = sum(b["volume"] for b in prior) / len(prior)
    if avg == 0:
        return "N/A"
    return f"{t0_vol / avg:.1f}x"


def compute_convexity(bars: list, t0_idx: int, t0_close: float,
                      gap_pct: float, data_cutoff: str) -> dict:
    """
    Max up and max down excursion from T0 close over T+1..T+5 and T+1..T+10.
    Uses each bar's HIGH for up excursion, LOW for down excursion.
    CONVEX if either direction hits >= CONVEX_THRESHOLD.

    Returns dict with keys: convex_5, up_5, dn_5, dir_5, convex_10, up_10, dn_10, dir_10.
    Any key may be "PENDING" if the window is incomplete.
    """
    gap_up = gap_pct > 0

    def _window(end_offset):
        max_high = None
        min_low  = None
        for off in range(1, end_offset + 1):
            bar = get_bar(bars, t0_idx + off, data_cutoff)
            if bar is None:
                # ran off the end of available data entirely
                return None, None, True
            if bar == "PENDING":
                return None, None, True
            if max_high is None or bar["high"] > max_high:
                max_high = bar["high"]
            if min_low is None or bar["low"] < min_low:
                min_low = bar["low"]
        return max_high, min_low, False

    def _direction(up_pct, dn_pct, pending):
        if pending or up_pct is None or dn_pct is None:
            return "PENDING"
        cont = (gap_up and up_pct >= CONVEX_THRESHOLD) or (not gap_up and dn_pct >= CONVEX_THRESHOLD)
        rev  = (gap_up and dn_pct >= CONVEX_THRESHOLD) or (not gap_up and up_pct >= CONVEX_THRESHOLD)
        if cont and rev:
            return "both"
        if cont:
            return "continuation"
        if rev:
            return "reversal"
        return "none"

    def _build(end_offset):
        max_h, min_l, pending = _window(end_offset)
        if pending or max_h is None or min_l is None:
            return {
                "convex":  "PENDING",
                "up":      "PENDING",
                "dn":      "PENDING",
                "dir":     "PENDING",
                "up_raw":  None,
                "dn_raw":  None,
            }
        if t0_close == 0:
            return {"convex": "N/A", "up": "N/A", "dn": "N/A", "dir": "N/A",
                    "up_raw": None, "dn_raw": None}
        up_pct = (max_h - t0_close) / t0_close * 100
        dn_pct = (t0_close - min_l)  / t0_close * 100
        convex = "Y" if (up_pct >= CONVEX_THRESHOLD or dn_pct >= CONVEX_THRESHOLD) else "N"
        return {
            "convex":  convex,
            "up":      _fmt_pct(up_pct),
            "dn":      _fmt_pct(-dn_pct, plus=False),   # show as negative for readability
            "dir":     _direction(up_pct, dn_pct, pending=False),
            "up_raw":  up_pct,
            "dn_raw":  dn_pct,
        }

    w5  = _build(5)
    w10 = _build(10)
    return {
        "convex_5":  w5["convex"],
        "up_5":      w5["up"],
        "dn_5":      w5["dn"],
        "dir_5":     w5["dir"],
        "convex_10": w10["convex"],
        "up_10":     w10["up"],
        "dn_10":     w10["dn"],
        "dir_10":    w10["dir"],
    }


# ---------------------------------------------------------------------------
# Per-event analysis
# ---------------------------------------------------------------------------

def analyse_event(event: dict, bars: list) -> dict:
    """
    Run all metrics for a single event against its ticker's bar list.
    Returns a flat dict suitable for both the markdown table and the CSV.
    """
    label      = event["label"]
    symbol     = event["symbol"]
    t0_date    = event["t0"]
    role       = event["role"]
    session    = event["session"]

    # Data cutoff: last confirmed-complete session (before today)
    cutoff = get_data_cutoff(bars)
    if not cutoff:
        return _error_row(event, "no confirmed bars before today")

    # Locate T0 index
    t0_idx = find_t0_index(bars, t0_date)
    if t0_idx is None:
        return _error_row(event, f"T0 date {t0_date} not found in bars")

    # T-1 bar (session immediately before T0)
    tm1_idx = t0_idx - 1
    if tm1_idx < 0:
        return _error_row(event, "no T-1 bar available")

    t0_bar  = bars[t0_idx]
    tm1_bar = bars[tm1_idx]

    # Verify T0 date alignment
    actual_t0_date = t0_bar["date"]
    if actual_t0_date != t0_date:
        t0_note = f"(nearest bar: {actual_t0_date})"
    else:
        t0_note = ""

    # Verify T0 bar itself is confirmed (not today's open session)
    if t0_bar["date"] > cutoff:
        return _error_row(event, f"T0 bar ({t0_bar['date']}) is beyond data cutoff ({cutoff})")

    gap_pct   = compute_gap_pct(t0_bar, tm1_bar)
    magnitude = classify_magnitude(gap_pct)
    hold_fail = compute_hold_fail(t0_bar, gap_pct)
    vol_ratio = compute_volume_ratio(bars, t0_idx)
    gap_fill  = compute_gap_fill(bars, t0_idx, tm1_bar["close"], gap_pct, cutoff)
    drift_t3  = compute_drift(bars, t0_idx, t0_bar["close"], 3, cutoff)
    drift_t5  = compute_drift(bars, t0_idx, t0_bar["close"], 5, cutoff)
    drift_t10 = compute_drift(bars, t0_idx, t0_bar["close"], 10, cutoff)
    convex    = compute_convexity(bars, t0_idx, t0_bar["close"], gap_pct, cutoff)

    gap_dir = "up" if gap_pct > 0 else "down"

    return {
        # Identity
        "label":    label,
        "symbol":   symbol,
        "session":  session,
        "t0_date":  actual_t0_date,
        "t0_note":  t0_note,
        "role":     role,
        "cutoff":   cutoff,
        # Convexity (lead columns)
        "convex_5":  convex["convex_5"],
        "up_5":      convex["up_5"],
        "dn_5":      convex["dn_5"],
        "dir_5":     convex["dir_5"],
        "convex_10": convex["convex_10"],
        "up_10":     convex["up_10"],
        "dn_10":     convex["dn_10"],
        "dir_10":    convex["dir_10"],
        # Gap metrics
        "gap_pct":  _fmt_pct(gap_pct),
        "gap_dir":  gap_dir,
        "mag":      magnitude,
        "hold_fail": hold_fail,
        "vol_ratio": vol_ratio,
        "fill":      gap_fill,
        # Drift
        "drift_t3":  drift_t3,
        "drift_t5":  drift_t5,
        "drift_t10": drift_t10,
        # Raw prices for CSV
        "tm1_close": f"{tm1_bar['close']:.2f}",
        "t0_open":   f"{t0_bar['open']:.2f}",
        "t0_close":  f"{t0_bar['close']:.2f}",
        "error":     "",
    }


def _error_row(event: dict, msg: str) -> dict:
    return {
        "label":    event["label"],
        "symbol":   event["symbol"],
        "session":  event["session"],
        "t0_date":  event["t0"],
        "t0_note":  "",
        "role":     event["role"],
        "cutoff":   "N/A",
        "convex_5": "ERROR", "up_5": "ERROR", "dn_5": "ERROR", "dir_5": "ERROR",
        "convex_10": "ERROR", "up_10": "ERROR", "dn_10": "ERROR", "dir_10": "ERROR",
        "gap_pct": "ERROR", "gap_dir": "ERROR", "mag": "ERROR",
        "hold_fail": "ERROR", "vol_ratio": "ERROR", "fill": "ERROR",
        "drift_t3": "ERROR", "drift_t5": "ERROR", "drift_t10": "ERROR",
        "tm1_close": "ERROR", "t0_open": "ERROR", "t0_close": "ERROR",
        "error": msg,
    }


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

# Column display names and widths for the markdown table.
# Order: convexity first, then event identity and gap metrics.
MD_COLS = [
    ("C5",       "convex_5",  4),
    ("UP(T5)",   "up_5",      8),
    ("DN(T5)",   "dn_5",      8),
    ("DIR5",     "dir_5",     13),
    ("C10",      "convex_10", 4),
    ("UP(T10)",  "up_10",     8),
    ("DN(T10)",  "dn_10",     8),
    ("DIR10",    "dir_10",    13),
    ("LABEL",    "label",     9),
    ("ROLE",     "role",      28),
    ("GAP%",     "gap_pct",   7),
    ("MAG",      "mag",       7),
    ("H/F",      "hold_fail", 7),
    ("VOL",      "vol_ratio", 5),
    ("FILL",     "fill",      9),
    ("T+3",      "drift_t3",  8),
    ("T+5",      "drift_t5",  8),
    ("T+10",     "drift_t10", 8),
]

CSV_COLS = [
    "label", "symbol", "session", "t0_date", "role",
    "convex_5", "up_5", "dn_5", "dir_5",
    "convex_10", "up_10", "dn_10", "dir_10",
    "gap_pct", "gap_dir", "mag", "hold_fail",
    "vol_ratio", "fill",
    "drift_t3", "drift_t5", "drift_t10",
    "tm1_close", "t0_open", "t0_close",
    "cutoff", "error",
]


def write_markdown(results: list, run_date: str, skipped: list, path: Path):
    lines = []
    lines.append(f"# Earnings Gap Characterization -- 10-event study")
    lines.append(f"")
    lines.append(f"**Brief date:** 2026-06-01  |  **Run date:** {run_date}  |  **Events:** 10 across 9 symbols (PLTR x2)")
    lines.append(f"")
    lines.append(f"**Headline question:** how often does a big gap produce a fast secondary move (>=5%)  ")
    lines.append(f"that makes a cheap OTM option pay? Convexity columns are left-anchored.")
    lines.append(f"")
    lines.append(f"**Data cutoff rule:** only confirmed closed sessions (bar date < run date).  ")
    lines.append(f"PENDING = session not yet closed. Cells are never estimated from partial data.")
    lines.append(f"")

    if skipped:
        lines.append(f"**Skipped (data error):** {', '.join(skipped)}")
        lines.append(f"")

    # Per-event cutoff summary
    lines.append(f"**Data cutoffs (last confirmed bar per ticker):**")
    seen_syms = {}
    for r in results:
        sym = r["symbol"]
        if sym not in seen_syms and r.get("cutoff") not in ("N/A", ""):
            seen_syms[sym] = r["cutoff"]
    for sym, cutoff in seen_syms.items():
        lines.append(f"  - {sym}: {cutoff}")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## Results")
    lines.append(f"")

    # Build header row
    hdr = "| " + " | ".join(h for h, _, _ in MD_COLS) + " |"
    sep = "| " + " | ".join("-" * max(w, len(h)) for h, _, w in MD_COLS) + " |"
    lines.append(hdr)
    lines.append(sep)

    for r in results:
        cells = []
        for _, key, _ in MD_COLS:
            val = str(r.get(key, ""))
            cells.append(val)
        lines.append("| " + " | ".join(cells) + " |")

    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## Column key")
    lines.append(f"")
    lines.append(f"| Col | Meaning |")
    lines.append(f"|-----|---------|")
    lines.append(f"| C5/C10 | CONVEX flag: Y if max excursion >=5% in either direction over T+1..T+5 / T+1..T+10 |")
    lines.append(f"| UP/DN | Max up / max down excursion from T0 close over that window (DN shown negative) |")
    lines.append(f"| DIR5/DIR10 | Whether the convex trigger was continuation (same dir as gap) or reversal |")
    lines.append(f"| GAP% | (T0 open - T-1 close) / T-1 close. Sign = direction. |")
    lines.append(f"| MAG | small <3%, medium 3-7%, large >7% |")
    lines.append(f"| H/F | HOLD if T0 closed in top third (gap-up) or bottom third (gap-down); FAIL opposite; NEUTRAL middle |")
    lines.append(f"| VOL | T0 volume / 30-session average before T0 |")
    lines.append(f"| FILL | First session T0..T+10 where bar range crossed back through T-1 close |")
    lines.append(f"| T+3/T+5/T+10 | % move from T0 close to that session's close. Sign is absolute (+ = up). |")
    lines.append(f"")
    lines.append(f"*Re-run ~2026-06-15 to backfill PENDING cells for late-May names.*")
    lines.append(f"")

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Markdown written: {path}")


def write_csv(results: list, path: Path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLS, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            writer.writerow(r)
    print(f"  CSV written: {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not UW_API_KEY:
        print("ERROR: UW_API_KEY not set. Run with: railway run --service pandoras-box ...")
        sys.exit(1)

    today_str = date.today().isoformat()
    print(f"Earnings Gap Backtest -- run date {today_str}")
    print(f"Events: {len(EVENTS)} | Symbols: {len(set(e['symbol'] for e in EVENTS))}")
    print()

    # Fetch bars once per unique symbol
    unique_symbols = list(dict.fromkeys(e["symbol"] for e in EVENTS))
    bars_cache = {}
    print("Fetching OHLC bars...")
    for sym in unique_symbols:
        b = fetch_regular_bars(sym)
        if b:
            print(f"  {sym}: {len(b)} regular-session bars, last={b[-1]['date']}")
            bars_cache[sym] = b
        else:
            print(f"  {sym}: FAILED -- will skip events for this ticker")
            bars_cache[sym] = None

    print()
    print("Analysing events...")
    results = []
    skipped = []
    for event in EVENTS:
        sym = event["symbol"]
        label = event["label"]
        bars = bars_cache.get(sym)
        if bars is None:
            print(f"  {label}: SKIP (no bar data)")
            skipped.append(label)
            results.append(_error_row(event, "bar fetch failed"))
            continue
        r = analyse_event(event, bars)
        if r["error"]:
            print(f"  {label}: ERROR -- {r['error']}")
            skipped.append(label)
        else:
            cutoff_note = f"cutoff={r['cutoff']}"
            print(f"  {label}: gap={r['gap_pct']} {r['hold_fail']} C5={r['convex_5']} C10={r['convex_10']} ({cutoff_note})")
        results.append(r)

    print()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_markdown(results, today_str, skipped, OUTPUT_MD)
    write_csv(results, OUTPUT_CSV)

    # Console summary
    ok = [r for r in results if not r["error"]]
    convex_5_y   = [r for r in ok if r["convex_5"]  == "Y"]
    convex_5_n   = [r for r in ok if r["convex_5"]  == "N"]
    convex_5_p   = [r for r in ok if r["convex_5"]  == "PENDING"]
    convex_10_y  = [r for r in ok if r["convex_10"] == "Y"]

    print()
    print("=" * 60)
    print("HEADLINE SUMMARY")
    print("=" * 60)
    print(f"  Events analysed : {len(ok)}/{len(EVENTS)}")
    print(f"  CONVEX (T+5 window) : {len(convex_5_y)} Y  |  {len(convex_5_n)} N  |  {len(convex_5_p)} PENDING")
    print(f"  CONVEX (T+10 window): {len(convex_10_y)} Y  (of events with full window)")
    if convex_5_y:
        print(f"  CONVEX events (T+5) : {[r['label'] for r in convex_5_y]}")
    if convex_5_n:
        print(f"  Non-convex (T+5)    : {[r['label'] for r in convex_5_n]}")
    if convex_5_p:
        print(f"  PENDING (T+5)       : {[r['label'] for r in convex_5_p]}")
    print()
    print(f"  Output: {OUTPUT_MD}")
    print(f"          {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
