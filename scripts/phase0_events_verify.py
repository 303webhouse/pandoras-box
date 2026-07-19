"""
Phase 0 verification -- confirm earnings dates/sessions for all 10 events in the brief.

Fetches ALL past earnings rows per ticker from UW and finds the closest match
to the expected date, so we can verify CONFIRM items and cross-check confirmed ones.

Run with: railway run --service pandoras-box python scripts/phase0_events_verify.py
"""

import os
import sys
from datetime import date, timedelta

import httpx

UW_BASE = "https://api.unusualwhales.com"
UW_API_KEY = os.getenv("UW_API_KEY", "")

# All 10 events from the brief. PLTR appears twice.
EVENTS = [
    {"symbol": "NOW",  "label": "NOW Q4",  "expected_date": "2026-01-28", "expected_session": "AMC", "status": "CONFIRM date"},
    {"symbol": "PLTR", "label": "PLTR Q4", "expected_date": "2026-02-02", "expected_session": "AMC", "status": "confirmed"},
    {"symbol": "NXPI", "label": "NXPI Q1", "expected_date": "2026-04-27", "expected_session": "AMC", "status": "CONFIRM date"},
    {"symbol": "F",    "label": "F Q1",    "expected_date": "2026-04-29", "expected_session": "AMC", "status": "confirmed"},
    {"symbol": "TSN",  "label": "TSN Q2",  "expected_date": "2026-05-04", "expected_session": "BMO", "status": "CONFIRM date+session"},
    {"symbol": "PLTR", "label": "PLTR Q1", "expected_date": "2026-05-04", "expected_session": "AMC", "status": "confirmed"},
    {"symbol": "NVDA", "label": "NVDA Q1", "expected_date": "2026-05-20", "expected_session": "AMC", "status": "confirmed"},
    {"symbol": "WMT",  "label": "WMT Q1",  "expected_date": "2026-05-21", "expected_session": "BMO", "status": "confirmed"},
    {"symbol": "ZS",   "label": "ZS Q3",   "expected_date": "2026-05-26", "expected_session": "AMC", "status": "confirmed"},
    {"symbol": "DELL", "label": "DELL Q1", "expected_date": "2026-05-28", "expected_session": "AMC", "status": "confirmed"},
]

# Optional: MU and INTC if they look like clean single-stock earnings gaps
OPTIONAL = [
    {"symbol": "MU",   "label": "MU Q?",   "expected_date": None, "expected_session": None, "status": "optional"},
    {"symbol": "INTC", "label": "INTC Q?",  "expected_date": None, "expected_session": None, "status": "optional"},
]


def _headers():
    return {"Authorization": f"Bearer {UW_API_KEY}", "Accept": "application/json"}


def next_trading_day(d: date) -> date:
    next_d = d + timedelta(days=1)
    while next_d.weekday() >= 5:
        next_d += timedelta(days=1)
    return next_d


def fetch_all_past_earnings(ticker: str):
    """Return all past earnings rows sorted descending by report_date."""
    url = f"{UW_BASE}/api/stock/{ticker}/earnings"
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, headers=_headers())
    if resp.status_code == 429:
        print(f"  [{ticker}] 429 daily limit hit")
        return None
    if resp.status_code != 200:
        print(f"  [{ticker}] HTTP {resp.status_code}")
        return None
    rows = resp.json().get("data", [])
    today_str = date.today().isoformat()
    past = [r for r in rows if (r.get("report_date") or "") <= today_str]
    past.sort(key=lambda r: r.get("report_date") or "", reverse=True)
    return past


def find_closest(rows, target_date_str):
    """Find the row whose report_date is closest to target_date_str."""
    if not rows or not target_date_str:
        return None
    target = date.fromisoformat(target_date_str)
    best = None
    best_delta = None
    for r in rows:
        d_str = r.get("report_date") or ""
        if not d_str:
            continue
        try:
            d = date.fromisoformat(d_str)
            delta = abs((d - target).days)
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best = r
        except ValueError:
            continue
    return best, best_delta


def verify_event(event: dict, all_earnings: dict):
    """Verify one event against UW data. Returns a result dict."""
    sym = event["symbol"]
    label = event["label"]
    expected_date = event["expected_date"]
    expected_session = event["expected_session"]
    status = event["status"]

    rows = all_earnings.get(sym)
    if rows is None:
        return {
            "label": label, "symbol": sym,
            "expected_date": expected_date, "expected_session": expected_session,
            "uw_date": "API_ERROR", "uw_session": "API_ERROR",
            "t0": "ERROR", "delta_days": None,
            "verdict": "API_ERROR", "status": status,
        }

    if not rows:
        return {
            "label": label, "symbol": sym,
            "expected_date": expected_date, "expected_session": expected_session,
            "uw_date": "NO_DATA", "uw_session": "NO_DATA",
            "t0": "NO_DATA", "delta_days": None,
            "verdict": "NO_DATA", "status": status,
        }

    matched, delta = find_closest(rows, expected_date)
    uw_date = matched.get("report_date") if matched else "NO_MATCH"
    uw_session_raw = matched.get("report_time") if matched else None

    if uw_session_raw == "premarket":
        uw_session = "BMO"
        t0 = uw_date
    elif uw_session_raw == "postmarket":
        uw_session = "AMC"
        try:
            t0 = next_trading_day(date.fromisoformat(uw_date)).isoformat()
        except Exception:
            t0 = "ERROR"
    else:
        uw_session = f"UNKNOWN({uw_session_raw})"
        t0 = "UNKNOWN"

    # Verdict
    date_ok = (uw_date == expected_date) if expected_date else True
    session_ok = (uw_session == expected_session) if expected_session else True

    if delta is not None and delta > 5:
        verdict = f"DATE_MISMATCH(delta={delta}d)"
    elif not date_ok:
        verdict = f"DATE_DIFFERS(got {uw_date})"
    elif not session_ok:
        verdict = f"SESSION_DIFFERS(got {uw_session})"
    else:
        verdict = "OK"

    return {
        "label": label, "symbol": sym,
        "expected_date": expected_date or "?",
        "expected_session": expected_session or "?",
        "uw_date": uw_date,
        "uw_session": uw_session,
        "t0": t0,
        "delta_days": delta,
        "verdict": verdict,
        "status": status,
        "reaction": matched.get("reaction") if matched else None,
        "pre_close": matched.get("pre_earnings_close") if matched else None,
        "post_close": matched.get("post_earnings_close") if matched else None,
    }


def verify_optional(sym: str, rows_cache: dict):
    """Show the most recent 3 earnings rows for an optional ticker."""
    rows = rows_cache.get(sym)
    if not rows:
        return None
    return rows[:3]


def main():
    if not UW_API_KEY:
        print("ERROR: UW_API_KEY not set. Run with: railway run --service pandoras-box ...")
        sys.exit(1)

    print(f"Phase 0 Event Verification -- {date.today().isoformat()}")
    print("Fetching earnings history for all symbols...")
    print()

    # Deduplicate symbols so we don't double-hit the same ticker
    all_symbols = list(dict.fromkeys([e["symbol"] for e in EVENTS]))
    optional_symbols = [e["symbol"] for e in OPTIONAL]
    all_to_fetch = all_symbols + optional_symbols

    all_earnings = {}
    for sym in all_to_fetch:
        rows = fetch_all_past_earnings(sym)
        all_earnings[sym] = rows
        count = len(rows) if rows else 0
        print(f"  {sym}: {count} past earnings rows fetched")

    print()
    print("=" * 80)
    print("EVENT VERIFICATION TABLE")
    print("=" * 80)

    results = []
    for event in EVENTS:
        r = verify_event(event, all_earnings)
        results.append(r)

    # Header
    hdr = (f"{'LABEL':<12} {'BRIEF DATE':<13} {'BRIEF SES':<10} "
           f"{'UW DATE':<13} {'UW SES':<8} {'T0':<13} {'DELTA':<7} {'VERDICT'}")
    print(hdr)
    print("-" * len(hdr))

    for r in results:
        verdict_str = r["verdict"]
        status_tag = f"[{r['status']}]" if "CONFIRM" in r["status"] else ""
        print(
            f"{r['label']:<12} "
            f"{r['expected_date']:<13} "
            f"{r['expected_session']:<10} "
            f"{r['uw_date']:<13} "
            f"{r['uw_session']:<8} "
            f"{r['t0']:<13} "
            f"{str(r['delta_days']) + 'd':<7} "
            f"{verdict_str} {status_tag}"
        )

    print()
    print("=" * 80)
    print("CONFIRMED EVENTS CONFIG (update brief's EVENTS list with these):")
    print("=" * 80)
    print("EVENTS = [")
    for r in results:
        if r["verdict"] == "OK":
            print(
                f'    {{"symbol":"{r["symbol"]}", "label":"{r["label"]}", '
                f'"report_date":"{r["uw_date"]}", "session":"{r["uw_session"]}", '
                f'"t0":"{r["t0"]}", "status":"VERIFIED"}},'
            )
        else:
            print(
                f'    {{"symbol":"{r["symbol"]}", "label":"{r["label"]}", '
                f'"report_date":"NEEDS_REVIEW({r["uw_date"]})", "session":"{r["uw_session"]}", '
                f'"t0":"{r["t0"]}", "status":"REVIEW -- {r["verdict"]}"}},'
            )
    print("]")

    print()
    print("=" * 80)
    print("OPTIONAL TICKERS (MU, INTC) -- recent earnings rows:")
    print("=" * 80)
    for sym in optional_symbols:
        rows = all_earnings.get(sym) or []
        print(f"\n  {sym} -- last 3 past earnings:")
        for row in rows[:3]:
            rt = row.get("report_time", "?")
            rd = row.get("report_date", "?")
            rxn = row.get("reaction", "?")
            pre = row.get("pre_earnings_close", "?")
            post = row.get("post_earnings_close", "?")
            print(f"    date={rd}  session={rt}  reaction={rxn}  pre_close={pre}  post_close={post}")

    # Summary
    errors = [r for r in results if r["verdict"] not in ("OK",)]
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    ok_count = sum(1 for r in results if r["verdict"] == "OK")
    print(f"  {ok_count}/10 events verified OK")
    if errors:
        print(f"  Events needing review:")
        for r in errors:
            print(f"    {r['label']}: {r['verdict']}")
    else:
        print("  All 10 events match brief. Ready for Phase 1 go-ahead.")


if __name__ == "__main__":
    main()
