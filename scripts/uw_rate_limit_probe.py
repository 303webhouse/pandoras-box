"""
UW Rate-Limit Burst-Test Probe
================================
ONE-SHOT DIAGNOSTIC. Do NOT run in any cron or automated pipeline.
Run manually on VPS OUTSIDE RTH (13:30-20:00 UTC weekdays).

Usage:
    python3 scripts/uw_rate_limit_probe.py

Writes findings to:
    docs/strategy-reviews/backtest/uw-rate-limit-findings.md

Ref: docs/codex-briefs/brief-phase-0-5-uw-forward-logger.md §Phase A
"""

import os
import sys
import time
from datetime import datetime, timezone

import requests

UW_BASE = "https://api.unusualwhales.com"
TEST_ENDPOINT = "/api/stock/SPY/flow-alerts"

# Load API key
UW_API_KEY = os.environ.get("UW_API_KEY", "")
if not UW_API_KEY:
    print("ERROR: UW_API_KEY not set. Source /etc/openclaw/openclaw.env first.")
    sys.exit(1)

HEADERS = {"Authorization": f"Bearer {UW_API_KEY}"}


def _fire_single() -> tuple[int, str | None]:
    """Fire one request. Returns (status_code, retry_after_header_or_None)."""
    r = requests.get(UW_BASE + TEST_ENDPOINT, headers=HEADERS, timeout=10)
    retry_after = r.headers.get("Retry-After")
    return r.status_code, retry_after


def fire_burst(n: int, label: str) -> dict:
    """Fire N requests as fast as possible. Returns result dict."""
    successes = 0
    rate_limited = 0
    first_429_at = None
    retry_after_values = []
    t0 = time.time()

    for i in range(1, n + 1):
        try:
            code, retry_after = _fire_single()
            if code == 200:
                successes += 1
            elif code == 429:
                rate_limited += 1
                if first_429_at is None:
                    first_429_at = i
                if retry_after:
                    retry_after_values.append(retry_after)
            else:
                print(f"  Unexpected status {code} at request #{i}")
        except Exception as e:
            print(f"  Request #{i} error: {e}")

    elapsed = time.time() - t0
    result = {
        "label": label,
        "total": n,
        "successes": successes,
        "rate_limited": rate_limited,
        "first_429_at": first_429_at,
        "retry_after_values": list(set(retry_after_values)),
        "elapsed_s": round(elapsed, 2),
    }
    print(f"  {label}: {successes}/{n} ok, {rate_limited} 429s, "
          f"first_429=#{first_429_at}, elapsed={elapsed:.1f}s")
    return result


def fire_sustained(n: int, interval_s: float, label: str) -> dict:
    """Fire N requests at interval_s seconds apart. Returns result dict."""
    successes = 0
    rate_limited = 0
    t0 = time.time()

    for i in range(1, n + 1):
        try:
            code, _ = _fire_single()
            if code == 200:
                successes += 1
            elif code == 429:
                rate_limited += 1
        except Exception as e:
            print(f"  Request #{i} error: {e}")
        if i < n:
            time.sleep(interval_s)

    elapsed = time.time() - t0
    result = {
        "label": label,
        "total": n,
        "successes": successes,
        "rate_limited": rate_limited,
        "elapsed_s": round(elapsed, 2),
    }
    print(f"  {label}: {successes}/{n} ok, {rate_limited} 429s, elapsed={elapsed:.1f}s")
    return result


def main():
    now_utc = datetime.now(timezone.utc)
    print(f"\nUW Rate-Limit Probe — {now_utc.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Endpoint: {UW_BASE}{TEST_ENDPOINT}")
    print("=" * 60)

    # Sanity check — fire 1 request, must succeed before probe runs
    print("\nSanity check (1 request)...")
    code, _ = _fire_single()
    if code != 200:
        print(f"ERROR: Sanity check failed with status {code}. Aborting.")
        sys.exit(1)
    print("  OK")

    results = []

    # Step 1: burst 10
    print("\nStep 1: Burst 10 requests (no sleep)...")
    r = fire_burst(10, "burst_10")
    results.append(r)
    if r["rate_limited"] > 0:
        print("  429s on 10-request burst. Stopping burst tests early.")
    else:
        # Step 2: burst 30
        print("\nStep 2: Burst 30 requests (no sleep)...")
        r = fire_burst(30, "burst_30")
        results.append(r)
        if r["rate_limited"] > 0:
            print("  429s on 30-request burst. Stopping burst tests.")
        else:
            # Step 3: burst 100
            print("\nStep 3: Burst 100 requests (no sleep)...")
            r = fire_burst(100, "burst_100")
            results.append(r)

    # Check if any 429 was hit
    any_429 = any(r["rate_limited"] > 0 for r in results)
    first_429_global = next(
        (r["first_429_at"] for r in results if r["first_429_at"] is not None), None
    )
    all_retry_after = []
    for r in results:
        all_retry_after.extend(r.get("retry_after_values", []))

    # Step 5: wait 60s
    print("\nStep 5: Waiting 60s before sustained-rate test...")
    for i in range(6, 0, -1):
        print(f"  {i * 10}s remaining...", end="\r")
        time.sleep(10)
    print("  Done waiting.          ")

    # Step 6: sustained 60 requests over 60s (1 rps)
    print("\nStep 6: Sustained 60 requests over 60s (1 rps)...")
    r_sus = fire_sustained(60, 1.0, "sustained_60rps")
    results.append(r_sus)

    # Derive recommended throttle
    # If no 429s at 100-burst: safe burst limit is ~50 (50% safety margin)
    # If 429s at burst N: safe burst is N // 2
    if not any_429 and len(results) >= 3:
        recommended_burst = 50
        recommended_rpm = 30
    elif first_429_global:
        recommended_burst = max(1, first_429_global // 2)
        recommended_rpm = recommended_burst
    else:
        recommended_burst = 10
        recommended_rpm = 10

    sustained_success_rate = (r_sus["successes"] / r_sus["total"]) * 100

    # Compose findings
    today = now_utc.strftime("%Y-%m-%d")
    lines = [
        f"# UW Rate Limit Findings — {today}",
        "",
        f"**Endpoint tested:** `{TEST_ENDPOINT}`",
        "**Plan tier:** Basic ($150/mo)",
        f"**Run time:** {now_utc.strftime('%Y-%m-%d %H:%M UTC')} (outside RTH)",
        "",
        "## Burst behavior",
    ]

    for r in results:
        if r["label"].startswith("burst_"):
            lines.append(
                f"- {r['total']} requests @ max speed: "
                f"{r['successes']} succeeded, {r['rate_limited']} 429s, "
                f"elapsed {r['elapsed_s']}s"
            )

    lines += [
        "",
        "## Sustained behavior",
        f"- {r_sus['total']} requests over ~{r_sus['elapsed_s']}s (1 rps): "
        f"{r_sus['successes']} succeeded, {r_sus['rate_limited']} 429s "
        f"({sustained_success_rate:.0f}% success rate)",
        "",
        "## First 429 trigger point",
        f"- Fired at request #{first_429_global}" if first_429_global else "- No 429s observed in burst tests",
        f"- Retry-After header values: {all_retry_after if all_retry_after else 'none observed'}",
        "",
        "## Recommended logger throttle",
        f"- Max burst: {recommended_burst} requests before pausing",
        f"- Steady-state rate: {recommended_rpm} requests per minute",
        "- Safety margin: values above are already at ~50% of observed limit to avoid live-committee contention",
        "",
        "## Raw results",
        "```",
    ]
    for r in results:
        lines.append(str(r))
    lines.append("```")

    findings = "\n".join(lines)

    out_path = "docs/strategy-reviews/backtest/uw-rate-limit-findings.md"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(findings)

    print(f"\n{'=' * 60}")
    print(f"Findings written to {out_path}")
    print(f"\nRecommended throttle:")
    print(f"  Max burst: {recommended_burst} req")
    print(f"  Steady-state: {recommended_rpm} req/min")
    print(f"  Any 429s observed: {any_429}")
    print(f"  Sustained success rate: {sustained_success_rate:.0f}%")


if __name__ == "__main__":
    main()
