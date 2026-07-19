"""
Phase 0 probe -- options-layer validation brief.
Tests which IV endpoints return historical data for past T0 dates.

Run: railway run --service pandoras-box python scripts/phase0_options_probe.py
"""

import os
import sys
import httpx

UW_BASE = "https://api.unusualwhales.com"
UW_API_KEY = os.getenv("UW_API_KEY", "")

PROBE_CASES = [
    {"ticker": "NXPI", "t0": "2026-04-29", "label": "NXPI Q1 (5 wks ago)"},
    {"ticker": "NOW",  "t0": "2026-01-29", "label": "NOW Q4 (4 mo ago)"},
    {"ticker": "PLTR", "t0": "2026-02-03", "label": "PLTR Q4 (4 mo ago)"},
]


def _headers():
    return {"Authorization": f"Bearer {UW_API_KEY}", "Accept": "application/json"}


def probe_endpoint(label, url, params=None):
    print(f"\n  -- {label}")
    print(f"     {url}" + (f"?{'&'.join(f'{k}={v}' for k,v in (params or {}).items())}" if params else ""))
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers=_headers(), params=params or {})
        print(f"     HTTP {resp.status_code}")
        if resp.status_code == 200:
            body = resp.json()
            data = body.get("data", body)
            print(f"     data type: {type(data).__name__}")
            if isinstance(data, dict):
                print(f"     keys: {list(data.keys())}")
                for k, v in list(data.items())[:8]:
                    print(f"       {k}: {v}")
            elif isinstance(data, list) and data:
                print(f"     rows: {len(data)}")
                print(f"     first row keys: {list(data[0].keys()) if data else 'empty'}")
                for row in data[:4]:
                    print(f"       {row}")
            return data
        else:
            print(f"     body: {resp.text[:300]}")
            return None
    except Exception as e:
        print(f"     ERROR: {e}")
        return None


def main():
    if not UW_API_KEY:
        print("ERROR: UW_API_KEY not set.")
        sys.exit(1)

    print("Phase 0 Options Probe")
    print("=" * 70)

    for case in PROBE_CASES:
        ticker = case["ticker"]
        t0 = case["t0"]
        label = case["label"]

        print(f"\n{'=' * 70}")
        print(f"TICKER: {ticker}  T0={t0}  ({label})")
        print(f"{'=' * 70}")

        # 1. volatility/stats -- single ATM IV for the date
        probe_endpoint(
            "volatility/stats (ATM IV for date)",
            f"{UW_BASE}/api/stock/{ticker}/volatility/stats",
            {"date": t0},
        )

        # 2. interpolated-iv -- IV per DTE horizon
        probe_endpoint(
            "interpolated-iv (IV by DTE, for date)",
            f"{UW_BASE}/api/stock/{ticker}/interpolated-iv",
            {"date": t0},
        )

        # 3. volatility/term-structure -- ATM IV per expiry
        probe_endpoint(
            "volatility/term-structure (IV per expiry, for date)",
            f"{UW_BASE}/api/stock/{ticker}/volatility/term-structure",
            {"date": t0},
        )

    print("\n" + "=" * 70)
    print("PHASE 0 ENDPOINT SUMMARY")
    print("=" * 70)
    print("Review output above to determine:")
    print("  - Which endpoints return data for past dates")
    print("  - How far back coverage goes (compare NXPI 5wk vs NOW 4mo)")
    print("  - Which IV field to use for BS pricing (want: ATM IV decimal)")


if __name__ == "__main__":
    main()
# Additional: check all 8 in-window events
