"""
Phase 0 probe -- confirm UW endpoints and earnings dates for the gap backtest.

Primary path: UW API (railway run python scripts/phase0_probe.py)
Fallback path: yfinance (python scripts/phase0_probe.py --yf)
  Use --yf when UW daily limit is exhausted; yfinance does not expose
  BMO/AMC timing so session will show MANUAL_NEEDED for those tickers.

Checks:
  1. Smoke-test OHLC endpoint for DELL (30-day daily window)
  2. Fetch earnings dates + report_time (premarket/postmarket) for all 6 tickers
  3. Derive T0 -- same day if BMO, next trading day if AMC
"""

import os
import sys
from datetime import date, timedelta

import httpx

UW_BASE = "https://api.unusualwhales.com"
UW_API_KEY = os.getenv("UW_API_KEY", "")

TICKERS = ["ZS", "DELL", "HPE", "F", "WMT", "CRDO"]


def _headers():
    return {
        "Authorization": f"Bearer {UW_API_KEY}",
        "Accept": "application/json",
    }


def next_trading_day(d: date) -> date:
    """Advance one calendar day, skipping weekends. Does NOT check market holidays."""
    next_d = d + timedelta(days=1)
    while next_d.weekday() >= 5:  # 5=Sat, 6=Sun
        next_d += timedelta(days=1)
    return next_d


# ----------------------------------------------------------------------------
# UW path
# ----------------------------------------------------------------------------

def check_ohlc_smoke_uw():
    """Smoke-test: fetch DELL daily OHLC for the last 30 days via UW."""
    print("\n" + "=" * 60)
    print("0.1 -- OHLC SMOKE TEST via UW (DELL, 30 days)")
    print("=" * 60)

    date_from = (date.today() - timedelta(days=30)).isoformat()
    url = f"{UW_BASE}/api/stock/DELL/ohlc/1d"
    params = {"date_from": date_from}

    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, headers=_headers(), params=params)

    print(f"  URL  : {url}?date_from={date_from}")
    print(f"  HTTP : {resp.status_code}")

    if resp.status_code == 429:
        err = resp.json()
        print(f"  429 DAILY LIMIT HIT: {err.get('code')}")
        print("  Re-run tomorrow (limit resets at midnight UTC) or use --yf flag")
        return False

    if resp.status_code != 200:
        print(f"  ERROR: {resp.text[:300]}")
        return False

    payload = resp.json()
    bars = payload.get("data", [])
    print(f"  Bars returned: {len(bars)}")

    if bars:
        b = bars[0]
        print(f"  First bar keys : {list(b.keys())}")
        reg = [b for b in bars if b.get("market_time") == "r"]
        print(f"  Regular-session bars: {len(reg)} of {len(bars)}")
        if reg:
            print("  Last 3 regular bars:")
            for bar in reg[-3:]:
                print(
                    f"    open={bar.get('open')} high={bar.get('high')} "
                    f"low={bar.get('low')} close={bar.get('close')} "
                    f"vol={bar.get('total_volume') or bar.get('volume')} "
                    f"start={bar.get('start_time')}"
                )

    return True


def check_earnings_uw(ticker: str):
    """Fetch earnings history from UW. Returns most recent entry or None."""
    url = f"{UW_BASE}/api/stock/{ticker}/earnings"
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, headers=_headers())

    if resp.status_code == 429:
        print(f"  [{ticker}] 429 daily limit -- skipping")
        return None
    if resp.status_code != 200:
        print(f"  [{ticker}] HTTP {resp.status_code}: {resp.text[:200]}")
        return None

    rows = resp.json().get("data", [])
    if not rows:
        return None

    today_str = date.today().isoformat()
    past_rows = [r for r in rows if (r.get("report_date") or "") <= today_str]
    if not past_rows:
        print(f"  [{ticker}] no past earnings rows (all future?)")
        return None
    past_rows.sort(key=lambda r: r.get("report_date") or "", reverse=True)
    return past_rows[0]


# ----------------------------------------------------------------------------
# yfinance fallback path
# ----------------------------------------------------------------------------

def check_ohlc_smoke_yf():
    """Smoke-test: fetch DELL daily OHLC for the last 30 days via yfinance."""
    print("\n" + "=" * 60)
    print("0.1 -- OHLC SMOKE TEST via yfinance (DELL, 30 days)")
    print("=" * 60)
    import yfinance as yf
    date_from = (date.today() - timedelta(days=30)).isoformat()
    data = yf.download("DELL", start=date_from, interval="1d", progress=False)
    if data is None or data.empty:
        print("  yfinance returned no data for DELL")
        return False

    if hasattr(data.columns, "nlevels") and data.columns.nlevels > 1:
        data.columns = data.columns.get_level_values(0)

    print(f"  Bars returned: {len(data)}")
    print(f"  Columns: {list(data.columns)}")
    print("  Last 3 bars:")
    for idx in list(data.index)[-3:]:
        row = data.loc[idx]
        print(
            f"    {str(idx)[:10]}  open={float(row['Open']):.2f}  "
            f"high={float(row['High']):.2f}  low={float(row['Low']):.2f}  "
            f"close={float(row['Close']):.2f}  vol={int(row['Volume'])}"
        )
    return True


def check_earnings_yf(ticker: str):
    """
    Get the most recent past earnings date via yfinance.
    BMO/AMC timing is not reliably available -- returns 'MANUAL_NEEDED'.
    """
    import yfinance as yf
    tk = yf.Ticker(ticker)
    try:
        df = tk.earnings_dates
    except Exception as e:
        print(f"  [{ticker}] yfinance earnings_dates error: {e}")
        return None

    if df is None or df.empty:
        return None

    today_str = date.today().isoformat()
    past = [(idx, row) for idx, row in df.iterrows() if str(idx)[:10] <= today_str]
    if not past:
        return None

    past.sort(key=lambda x: str(x[0]), reverse=True)
    idx, row = past[0]
    return {
        "report_date": str(idx)[:10],
        "report_time": "MANUAL_NEEDED",
        "actual_eps": row.get("Reported EPS"),
        "street_mean_est": row.get("EPS Estimate"),
        "expected_move_perc": None,
    }


# ----------------------------------------------------------------------------
# Shared output logic
# ----------------------------------------------------------------------------

def build_results(raw_rows: dict) -> dict:
    """Convert raw UW/yfinance rows into normalized dicts with session + T0."""
    results = {}
    for ticker, row in raw_rows.items():
        if row is None:
            results[ticker] = {"error": "no data"}
            continue

        report_date_str = row.get("report_date") or "UNKNOWN"
        report_time = row.get("report_time", "unknown")

        if report_time == "premarket":
            session = "BMO"
            t0 = report_date_str if report_date_str != "UNKNOWN" else "UNKNOWN"
        elif report_time == "postmarket":
            session = "AMC"
            if report_date_str != "UNKNOWN":
                t0 = next_trading_day(date.fromisoformat(report_date_str)).isoformat()
            else:
                t0 = "UNKNOWN"
        elif report_time == "MANUAL_NEEDED":
            session = "MANUAL_NEEDED"
            t0 = "MANUAL_NEEDED"
        else:
            session = "UNKNOWN"
            t0 = "UNKNOWN"

        results[ticker] = {
            "report_date": report_date_str,
            "report_time_raw": report_time,
            "session": session,
            "t0": t0,
            "actual_eps": row.get("actual_eps"),
            "street_est": row.get("street_mean_est"),
            "expected_move_perc": row.get("expected_move_perc"),
        }
    return results


def print_results(results: dict, smoke_ok: bool):
    print()
    print("EARNINGS CONFIG DICT (paste into analysis script):")
    print("EARNINGS = {")
    for ticker, info in results.items():
        if "error" in info:
            print(f'    "{ticker}": {{"error": "{info["error"]}"}},')
        else:
            print(
                f'    "{ticker}": {{"report_date": "{info["report_date"]}", '
                f'"session": "{info["session"]}", '
                f'"t0": "{info["t0"]}", '
                f'"report_time_raw": "{info["report_time_raw"]}"}},')
    print("}")

    print()
    hdr = f"{'TICKER':<8} {'REPORT DATE':<14} {'SESSION':<16} {'T0':<14} {'EPS ACT':<10} {'EPS EST':<10} {'EXP MOVE%'}"
    print(hdr)
    print("-" * len(hdr))
    for ticker, info in results.items():
        if "error" in info:
            print(f"{ticker:<8} ERROR -- no data returned")
        else:
            print(
                f"{ticker:<8} "
                f"{info['report_date']:<14} "
                f"{info['session']:<16} "
                f"{info['t0']:<14} "
                f"{str(info.get('actual_eps') or 'N/A'):<10} "
                f"{str(info.get('street_est') or 'N/A'):<10} "
                f"{info.get('expected_move_perc') or 'N/A'}"
            )

    print("\n" + "=" * 60)
    print("0.3 -- PHASE 0 SUMMARY")
    print("=" * 60)
    print(f"  OHLC smoke test   : {'CONFIRMED' if smoke_ok else 'FAILED or LIMIT HIT'}")
    print(f"  UW OHLC path      : /api/stock/{{ticker}}/ohlc/1d")
    print(f"  UW query param    : date_from=YYYY-MM-DD")
    print(f"  UW bar fields     : open, high, low, close, total_volume, start_time, market_time")
    print(f"  UW earnings path  : /api/stock/{{ticker}}/earnings")
    print(f"  Timing field      : report_time ('premarket'=BMO, 'postmarket'=AMC)")

    errors = [t for t, v in results.items() if "error" in v]
    manuals = [t for t, v in results.items() if "error" not in v and v.get("session") in ("UNKNOWN", "MANUAL_NEEDED")]
    if errors:
        print(f"  TICKERS WITH NO DATA              : {errors}")
    if manuals:
        print(f"  TICKERS NEEDING MANUAL BMO/AMC    : {manuals}")
    if not errors and not manuals:
        print("  All 6 tickers confirmed. Ready for Phase 1 go-ahead from Nick.")
    elif manuals:
        print("  ACTION REQUIRED: Nick to confirm BMO/AMC for flagged tickers before Phase 1.")


def main():
    use_yf = "--yf" in sys.argv

    if not use_yf and not UW_API_KEY:
        print("ERROR: UW_API_KEY not set.")
        print("Run with: railway run python scripts/phase0_probe.py")
        print("Or use yfinance fallback: python scripts/phase0_probe.py --yf")
        sys.exit(1)

    print(f"Phase 0 Probe -- {date.today().isoformat()}")
    if use_yf:
        print("Mode: yfinance fallback (UW daily limit exhausted)")
    else:
        print("Mode: UW API -- UW_API_KEY: [SET]")

    if use_yf:
        smoke_ok = check_ohlc_smoke_yf()
    else:
        smoke_ok = check_ohlc_smoke_uw()

    print("\n" + "=" * 60)
    print("0.2 -- EARNINGS DATES + SESSION + T0 (all 6 tickers)")
    print("=" * 60)

    raw_rows = {}
    for ticker in TICKERS:
        if use_yf:
            raw_rows[ticker] = check_earnings_yf(ticker)
        else:
            raw_rows[ticker] = check_earnings_uw(ticker)

    results = build_results(raw_rows)
    print_results(results, smoke_ok)


if __name__ == "__main__":
    main()
