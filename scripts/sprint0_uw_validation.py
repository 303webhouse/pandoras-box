"""
Sprint 0 — UW API + yfinance Validation Script
The Great Consolidation: test-only, no code changes.

Tests 10 UW API endpoints and compares yfinance vs Polygon SPY bars.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

UW_API_KEY = os.environ.get("UW_API_KEY", "cb579cb8-6e37-46ea-b4c5-f8f3b93a025d")
UW_BASE = "https://api.unusualwhales.com"
UW_HEADERS = {"Authorization": f"Bearer {UW_API_KEY}", "Accept": "application/json"}

POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY", "")
POLYGON_BASE = "https://api.polygon.io"


def test_uw_endpoint(path: str, label: str) -> dict:
    """Hit a UW endpoint, print status + schema, return result."""
    url = f"{UW_BASE}{path}"
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  GET {path}")
    print(f"{'='*60}")

    try:
        resp = requests.get(url, headers=UW_HEADERS, timeout=15)
        print(f"  Status: {resp.status_code}")

        if resp.status_code != 200:
            print(f"  Error: {resp.text[:300]}")
            return {"status": resp.status_code, "error": resp.text[:300]}

        data = resp.json()

        # Print schema (keys + types + sample values)
        if isinstance(data, dict):
            print(f"  Top-level keys: {list(data.keys())}")
            for k, v in data.items():
                if isinstance(v, list):
                    print(f"    {k}: list[{len(v)} items]")
                    if v:
                        item = v[0]
                        if isinstance(item, dict):
                            print(f"      Item keys: {list(item.keys())}")
                            for ik, iv in list(item.items())[:8]:
                                print(f"        {ik}: {type(iv).__name__} = {str(iv)[:80]}")
                        else:
                            print(f"      Item type: {type(item).__name__} = {str(item)[:80]}")
                elif isinstance(v, dict):
                    print(f"    {k}: dict with keys {list(v.keys())[:10]}")
                    for dk, dv in list(v.items())[:5]:
                        print(f"      {dk}: {type(dv).__name__} = {str(dv)[:80]}")
                else:
                    print(f"    {k}: {type(v).__name__} = {str(v)[:80]}")
        elif isinstance(data, list):
            print(f"  Response: list[{len(data)} items]")
            if data:
                item = data[0]
                if isinstance(item, dict):
                    print(f"    Item keys: {list(item.keys())}")
                    for ik, iv in list(item.items())[:8]:
                        print(f"      {ik}: {type(iv).__name__} = {str(iv)[:80]}")
        else:
            print(f"  Response type: {type(data).__name__}")

        return {"status": 200, "data": data}

    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return {"status": "error", "error": str(e)}


def test_yfinance_vs_polygon():
    """Compare yfinance SPY bars vs Polygon bars for last 5 days."""
    print(f"\n{'='*60}")
    print(f"  YFINANCE vs POLYGON — SPY 5-Day Comparison")
    print(f"{'='*60}")

    # yfinance
    yf_bars = {}
    try:
        import yfinance as yf
        data = yf.download("SPY", period="5d", interval="1d", progress=False)
        if data is not None and not data.empty:
            # Handle MultiIndex columns from yfinance
            if hasattr(data.columns, 'nlevels') and data.columns.nlevels > 1:
                data.columns = data.columns.get_level_values(0)
            for idx in data.index:
                d = str(idx.date()) if hasattr(idx, 'date') else str(idx)[:10]
                yf_bars[d] = {
                    "open": round(float(data.loc[idx, "Open"].iloc[0] if hasattr(data.loc[idx, "Open"], 'iloc') else data.loc[idx, "Open"]), 2),
                    "high": round(float(data.loc[idx, "High"].iloc[0] if hasattr(data.loc[idx, "High"], 'iloc') else data.loc[idx, "High"]), 2),
                    "low": round(float(data.loc[idx, "Low"].iloc[0] if hasattr(data.loc[idx, "Low"], 'iloc') else data.loc[idx, "Low"]), 2),
                    "close": round(float(data.loc[idx, "Close"].iloc[0] if hasattr(data.loc[idx, "Close"], 'iloc') else data.loc[idx, "Close"]), 2),
                    "volume": int(data.loc[idx, "Volume"].iloc[0] if hasattr(data.loc[idx, "Volume"], 'iloc') else data.loc[idx, "Volume"]),
                }
        print(f"  yfinance: {len(yf_bars)} bars fetched")
    except Exception as e:
        print(f"  yfinance ERROR: {e}")

    # Polygon
    poly_bars = {}
    if POLYGON_API_KEY:
        try:
            end = datetime.utcnow().strftime("%Y-%m-%d")
            start = (datetime.utcnow() - timedelta(days=8)).strftime("%Y-%m-%d")
            url = f"{POLYGON_BASE}/v2/aggs/ticker/SPY/range/1/day/{start}/{end}"
            resp = requests.get(url, params={"apiKey": POLYGON_API_KEY, "adjusted": "true", "sort": "asc"}, timeout=10)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                for r in results:
                    d = datetime.utcfromtimestamp(r["t"] / 1000).strftime("%Y-%m-%d")
                    poly_bars[d] = {
                        "open": round(r["o"], 2),
                        "high": round(r["h"], 2),
                        "low": round(r["l"], 2),
                        "close": round(r["c"], 2),
                        "volume": int(r["v"]),
                    }
            print(f"  Polygon: {len(poly_bars)} bars fetched")
        except Exception as e:
            print(f"  Polygon ERROR: {e}")
    else:
        print("  Polygon: SKIPPED (no POLYGON_API_KEY)")

    # Compare
    if yf_bars and poly_bars:
        common_dates = sorted(set(yf_bars.keys()) & set(poly_bars.keys()))
        print(f"\n  Common dates: {len(common_dates)}")
        print(f"  {'Date':<12} {'Field':<7} {'yfinance':>10} {'Polygon':>10} {'Diff':>8} {'Material':>10}")
        print(f"  {'-'*65}")

        material_diffs = 0
        for d in common_dates[-5:]:
            yf = yf_bars[d]
            pg = poly_bars[d]
            for field in ["open", "high", "low", "close"]:
                yf_val = yf[field]
                pg_val = pg[field]
                diff = abs(yf_val - pg_val)
                pct = (diff / pg_val * 100) if pg_val else 0
                material = "YES" if pct > 0.1 else ""
                if material:
                    material_diffs += 1
                print(f"  {d:<12} {field:<7} {yf_val:>10.2f} {pg_val:>10.2f} {diff:>7.2f}  {material:>8}")
            # Volume comparison
            yf_vol = yf["volume"]
            pg_vol = pg["volume"]
            vol_diff_pct = abs(yf_vol - pg_vol) / pg_vol * 100 if pg_vol else 0
            vol_material = "YES" if vol_diff_pct > 5 else ""
            if vol_material:
                material_diffs += 1
            print(f"  {d:<12} {'volume':<7} {yf_vol:>10,} {pg_vol:>10,} {vol_diff_pct:>6.1f}%  {vol_material:>8}")

        print(f"\n  Material differences (>0.1% price, >5% volume): {material_diffs}")
        if material_diffs == 0:
            print("  VERDICT: yfinance is a viable replacement for Polygon daily bars")
        else:
            print("  VERDICT: Some differences found — review above")
    elif yf_bars and not poly_bars:
        print("\n  Cannot compare — Polygon data unavailable")
        print("  yfinance data looks healthy with", len(yf_bars), "bars")


def main():
    print("=" * 60)
    print("  SPRINT 0 — UW API + yfinance Validation")
    print(f"  {datetime.now().isoformat()}")
    print("=" * 60)

    # ── UW API Tests ──
    endpoints = [
        ("/api/stock/SPY/greek-exposure",      "1. Greek Exposure (GEX)"),
        ("/api/stock/SPY/flow-recent",          "2. Recent Flow"),
        ("/api/market/market-tide",             "3. Market Tide"),
        ("/api/stock/SPY/info",                 "4. Stock Info"),
        ("/api/stock/SPY/option-contracts",     "5. Option Contracts"),
        ("/api/stock/SPY/iv-rank",              "6. IV Rank"),
        ("/api/darkpool/recent",                "7. Dark Pool Recent"),
        ("/api/market/economic-calendar",       "8. Economic Calendar"),
        ("/api/earnings/premarket",             "9. Earnings Premarket"),
        ("/api/shorts/SPY/interest-float/v2",   "10. Short Interest / Float"),
    ]

    results = {}
    for path, label in endpoints:
        results[path] = test_uw_endpoint(path, label)
        time.sleep(0.5)  # Rate limit courtesy

    # ── Summary ──
    print(f"\n{'='*60}")
    print("  UW API ENDPOINT SUMMARY")
    print(f"{'='*60}")
    working = 0
    for path, label in endpoints:
        status = results[path].get("status", "?")
        icon = "OK" if status == 200 else "FAIL"
        print(f"  [{icon:>4}] {label:<35} -> {status}")
        if status == 200:
            working += 1
    print(f"\n  Result: {working}/{len(endpoints)} endpoints working")

    # ── yfinance vs Polygon ──
    test_yfinance_vs_polygon()

    # ── Save full results ──
    os.makedirs("scripts/output", exist_ok=True)
    report_path = "scripts/output/sprint0_uw_validation.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Full JSON saved to {report_path}")
    print("\n  SPRINT 0 COMPLETE")


if __name__ == "__main__":
    main()
