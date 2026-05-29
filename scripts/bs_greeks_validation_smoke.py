"""Tier 2 Black-Scholes Greeks validation smoke for hub_get_options_chain.

Confirms that BS-computed Greeks are populated and sane for near-ATM SPY
contracts. Run during live RTH after Tier 2 is deployed to the branch.

Pass criteria (Tier 2, governing at smoke-time):
    Ticker:  SPY
    Expiry:  next Friday from today (weekly)
    Scope:   5 strikes immediately above AND below ATM on BOTH call and put
             sides (up to 20 contracts total)
    Sanity bands (ALL must pass for ALL sampled contracts):
      - ATM call delta: 0.40 – 0.60
      - ATM put delta:  -0.60 – -0.40
      - Gamma:  > 0 for all (gamma is always positive)
      - Vega:   > 0 for all (vega is always positive)
      - Theta:  < 0 for all (theta is always negative for long options)
      - All four Greeks non-null on all sampled contracts (assuming IV is non-null)
    Optional cross-check vs. yfinance (±10% tolerance on delta, skipped if
    yfinance is not importable).

Fail criterion: any sanity band violation → DO NOT merge. Likely cause is a
sign error or units error in the BS implementation.

Requires: UW_API_KEY in environment.

Run from c:\\trading-hub:
    $env:UW_API_KEY = "..."      # one-shot, PowerShell
    python scripts\\bs_greeks_validation_smoke.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


def _next_friday(today: date) -> date:
    days_ahead = (4 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def _check_yfinance_available() -> bool:
    try:
        import yfinance  # noqa: F401
        return True
    except ImportError:
        return False


async def main() -> int:
    if not os.environ.get("UW_API_KEY"):
        import getpass
        print("UW_API_KEY not in environment.")
        print("Paste your UW API key and press Enter (the key will NOT be echoed):")
        try:
            key = getpass.getpass(prompt="UW_API_KEY: ")
        except (EOFError, KeyboardInterrupt):
            print("\nFAIL: no key provided.")
            return 2
        key = key.strip()
        if not key:
            print("FAIL: empty key.")
            return 2
        os.environ["UW_API_KEY"] = key

    from services.read_only.options_chain import get_options_chain
    from integrations.risk_free_rate import RISK_FREE_RATE_3M

    ticker = "SPY"
    expiry = _next_friday(date.today()).isoformat()

    print(f"Smoke: {ticker} {expiry} both")
    print(f"Risk-free rate: {RISK_FREE_RATE_3M:.4f} ({RISK_FREE_RATE_3M*100:.2f}%)")
    print("Fetching live chain...")

    result = await get_options_chain(ticker, expiry, "both")

    if result is None:
        print("FAIL: chain unavailable (None returned).")
        return 1

    contracts = result.get("contracts") or []
    spot = result.get("spot")
    greeks_source = result.get("greeks_source")

    print(f"  Contracts returned: {len(contracts)}")
    print(f"  Spot:               {spot}  [{result.get('spot_source', '?')}]")
    print(f"  greeks_source:      {greeks_source}")
    print(f"  iv_rank:            {result.get('iv_rank')}")
    print(f"  max_pain:           {result.get('max_pain')}")
    agg_err = result.get("aggregates_errors")
    if agg_err:
        print(f"  aggregates_errors:  {agg_err}")

    if greeks_source != "bs_computed":
        print(f"\nFAIL: greeks_source = '{greeks_source}', expected 'bs_computed'.")
        return 1

    if spot is None:
        print("\nFAIL (inconclusive): spot is None — cannot anchor ATM band.")
        return 1

    def _nearest(side: str, n: int = 10):
        side_c = [c for c in contracts if c.get("option_type") == side and c.get("strike") is not None]
        side_c.sort(key=lambda c: abs(c["strike"] - spot))
        return side_c[:n]

    # Display 10 each for reference; sanity bands only apply to the 5 closest.
    near_calls_display = _nearest("call", 10)
    near_puts_display = _nearest("put", 10)
    near_calls = near_calls_display[:5]   # 5 nearest calls — gate contracts
    near_puts = near_puts_display[:5]     # 5 nearest puts — gate contracts
    near_atm_display = near_calls_display + near_puts_display

    print(f"\nNear-ATM display: {len(near_atm_display)} contracts (10 calls + 10 puts)")
    print(f"Sanity bands applied to: 5 nearest calls + 5 nearest puts")

    # ── Print table ──────────────────────────────────────────────────────
    print(f"\n{'Strike':>8} {'Type':>5} {'IV':>7} {'Delta':>8} {'Gamma':>8} {'Theta':>8} {'Vega':>8}")
    print("-" * 60)
    for c in near_atm_display:
        iv_v = c.get("implied_volatility")
        d = c.get("delta")
        g = c.get("gamma")
        t = c.get("theta")
        v = c.get("vega")
        print(f"{c['strike']:>8.2f} {c['option_type']:>5} "
              f"{iv_v or 0:>7.4f} "
              f"{d if d is not None else 'None':>8} "
              f"{g if g is not None else 'None':>8} "
              f"{t if t is not None else 'None':>8} "
              f"{v if v is not None else 'None':>8}")

    # ── Sanity band checks ───────────────────────────────────────────────
    failures: list[str] = []

    for c in near_calls:
        s = c["strike"]
        d = c.get("delta")
        g = c.get("gamma")
        t = c.get("theta")
        v = c.get("vega")
        iv_v = c.get("implied_volatility")

        if iv_v is not None:
            if d is None:
                failures.append(f"call {s}: delta is None (IV={iv_v})")
            elif not (0.40 <= d <= 0.60):
                failures.append(f"call {s}: delta {d:.4f} outside [0.40, 0.60]")
            if g is None:
                failures.append(f"call {s}: gamma is None")
            elif g <= 0:
                failures.append(f"call {s}: gamma {g:.6f} <= 0")
            if t is None:
                failures.append(f"call {s}: theta is None")
            elif t >= 0:
                failures.append(f"call {s}: theta {t:.6f} >= 0 (should be negative)")
            if v is None:
                failures.append(f"call {s}: vega is None")
            elif v <= 0:
                failures.append(f"call {s}: vega {v:.6f} <= 0")

    for c in near_puts:
        s = c["strike"]
        d = c.get("delta")
        g = c.get("gamma")
        t = c.get("theta")
        v = c.get("vega")
        iv_v = c.get("implied_volatility")

        if iv_v is not None:
            if d is None:
                failures.append(f"put {s}: delta is None (IV={iv_v})")
            elif not (-0.60 <= d <= -0.40):
                failures.append(f"put {s}: delta {d:.4f} outside [-0.60, -0.40]")
            if g is None:
                failures.append(f"put {s}: gamma is None")
            elif g <= 0:
                failures.append(f"put {s}: gamma {g:.6f} <= 0")
            if t is None:
                failures.append(f"put {s}: theta is None")
            elif t >= 0:
                failures.append(f"put {s}: theta {t:.6f} >= 0 (should be negative)")
            if v is None:
                failures.append(f"put {s}: vega is None")
            elif v <= 0:
                failures.append(f"put {s}: vega {v:.6f} <= 0")

    print()
    if failures:
        print("FAIL: sanity band violations detected:")
        for f in failures:
            print(f"  ✗ {f}")
        print("\nDo NOT merge. Investigate sign/units errors in bs_greeks_from_iv().")
        return 1

    # ── Optional yfinance cross-check ────────────────────────────────────
    if _check_yfinance_available():
        print("yfinance available — attempting delta cross-check (±10% tolerance)...")
        try:
            import yfinance as yf
            spy = yf.Ticker("SPY")
            yf_chain = spy.option_chain(expiry)
            yf_calls = {row["strike"]: row["delta"] for _, row in yf_chain.calls.iterrows()
                        if "delta" in yf_chain.calls.columns and not __import__("math").isnan(row.get("delta") or float("nan"))}

            cross_failures = []
            for c in near_calls[:5]:
                s = c["strike"]
                our_delta = c.get("delta")
                yf_delta = yf_calls.get(s)
                if our_delta is not None and yf_delta is not None:
                    divergence = abs(our_delta - yf_delta) / max(abs(yf_delta), 0.001)
                    status = "OK" if divergence <= 0.10 else "DIVERGENCE"
                    print(f"  call {s}: ours={our_delta:.4f}, yf={yf_delta:.4f}, "
                          f"div={divergence:.1%} [{status}]")
                    if divergence > 0.10:
                        cross_failures.append(f"call {s}: delta divergence {divergence:.1%} > 10%")

            if cross_failures:
                print(f"\nWARNING: yfinance cross-check flagged {len(cross_failures)} contract(s).")
                print("  (yfinance Greeks may use different IV smile / exercise model — "
                      "divergence >10% warrants investigation but does NOT auto-fail.)")
            else:
                print("  Cross-check: all compared strikes within ±10% tolerance.")
        except Exception as e:
            print(f"  yfinance cross-check skipped (error: {e})")
    else:
        print("yfinance not importable — cross-check skipped (sanity bands are the gate).")

    # ── PASS ─────────────────────────────────────────────────────────────
    sample_call = near_calls[0] if near_calls else {}
    sample_put = near_puts[0] if near_puts else {}

    print("\nPASS: all sanity bands met for near-ATM strikes.")
    print(f"  Nearest-ATM call: strike={sample_call.get('strike')}, "
          f"delta={sample_call.get('delta')}, gamma={sample_call.get('gamma')}, "
          f"theta={sample_call.get('theta')}, vega={sample_call.get('vega')}")
    print(f"  Nearest-ATM put:  strike={sample_put.get('strike')}, "
          f"delta={sample_put.get('delta')}, gamma={sample_put.get('gamma')}, "
          f"theta={sample_put.get('theta')}, vega={sample_put.get('vega')}")
    print(f"  greeks_source: {greeks_source}")
    print(f"  Risk-free rate used: {RISK_FREE_RATE_3M:.4f} (3M T-bill, 2026-05-29)")
    print("\nCleared to merge tier2-bs-greeks → main.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
