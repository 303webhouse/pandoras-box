"""v1.5 chain smoke for hub_get_options_chain.

Confirms UW's /option-contracts endpoint returns a live SPY chain with
non-null implied_volatility on near-ATM contracts. Greeks (delta/gamma/
theta/vega) are NOT checked — confirmed absent from UW /option-contracts
on 2026-05-29 at confirmed-low load (0/500 contracts with delta across
the full SPY call chain). Greeks are deferred to a Tier 2 follow-up brief.

Pass criteria (v1.5, governing at ship-time 2026-05-29):
    Ticker:  SPY
    Expiry:  next Friday from today (weekly)
    Min:     the 5 strikes immediately above ATM AND the 5 immediately below
             ATM, on BOTH call and put sides (up to 20 contracts), must ALL
             have non-null implied_volatility. Anchors the gate to the
             near-ATM strikes DAEDALUS actually trades.
    Guard:   a null `spot` in the response is treated as FAIL/inconclusive — a
             null spot co-occurred with the load-degraded 2026-05-27 chain.

Requires: UW_API_KEY in environment. Does NOT echo, log, or persist the key.

Run from c:\\trading-hub:
    $env:UW_API_KEY = "..."      # one-shot, PowerShell
    python scripts\\options_chain_greeks_smoke.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta

# Ensure backend/ is on path so we can import the real service layer.
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


def _next_friday(today: date) -> date:
    """Next Friday strictly after `today`. If today IS Friday, pick the one after."""
    # Monday=0 ... Friday=4 ... Sunday=6
    days_ahead = (4 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


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

    # Import after path setup and env-var population.
    from services.read_only.options_chain import get_options_chain  # noqa: E402

    ticker = "SPY"
    expiry = _next_friday(date.today()).isoformat()
    option_type = "both"

    print(f"Smoke: {ticker} {expiry} {option_type}")
    print("Fetching live chain (UW /option-contracts + /iv-rank + /max-pain)...")

    result = await get_options_chain(ticker, expiry, option_type)

    if result is None:
        print("FAIL: chain unavailable (None returned). Possible causes:")
        print("  - UW_API_KEY invalid")
        print("  - SPY has no options at the chosen expiry")
        print("  - UW endpoint errored")
        return 1

    contracts = result.get("contracts") or []
    print(f"  Contracts returned: {len(contracts)}")
    print(f"  Chain spot:         {result.get('spot')}")
    print(f"  uw_timestamp:       {result.get('uw_timestamp')}")
    print(f"  uw_timestamp_source:{result.get('uw_timestamp_source')}")
    print(f"  iv_rank:            {result.get('iv_rank')}")
    print(f"  max_pain:           {result.get('max_pain')}")
    agg_err = result.get("aggregates_errors")
    if agg_err:
        print(f"  aggregates_errors:  {agg_err}")

    # Pass criterion (ATLAS M1, Pass-1 amendment): the 5 strikes immediately
    # above ATM AND the 5 immediately below ATM — on BOTH call and put sides —
    # must have non-null delta AND non-null implied_volatility. Anchors the
    # gate to the strikes DAEDALUS actually picks (near-ATM structures), not a
    # loose population-rate check that could pass on deep-OTM strikes DAEDALUS
    # never uses. See hub-get-options-chain-task2-schema-2026-05-26.md L377-390.
    spot = result.get("spot")
    print()
    if spot is None:
        print("FAIL (inconclusive): response has no spot price — cannot anchor")
        print("  the ATM band. A null spot co-occurred with the load-degraded")
        print("  2026-05-27 over-budget smoke (spot:None + 0/497 Greeks). Treat")
        print("  as inconclusive, NOT a genuine endpoint verdict; re-run at")
        print("  confirmed low UW daily load before any schema revert.")
        return 1

    def _nearest(side: str, n: int = 10):
        side_contracts = [
            c for c in contracts
            if c.get("option_type") == side and c.get("strike") is not None
        ]
        side_contracts.sort(key=lambda c: abs(c["strike"] - spot))
        return side_contracts[:n]

    near_calls = _nearest("call", 10)
    near_puts = _nearest("put", 10)
    near_atm = near_calls + near_puts

    def _ok(c):
        return c.get("implied_volatility") is not None

    passing = [c for c in near_atm if _ok(c)]
    failing = [c for c in near_atm if not _ok(c)]

    print(f"Spot: {spot}")
    print(f"Near-ATM contracts checked: {len(near_atm)} "
          f"({len(near_calls)} calls + {len(near_puts)} puts within ~5 strikes of ATM)")
    print(f"With non-null IV: {len(passing)} / {len(near_atm)}")

    if failing or len(near_atm) < 2:
        print()
        print("FAIL: IV not populated for near-ATM strikes (or chain too narrow).")
        print("  >=1 near-ATM strike has null implied_volatility. The chain")
        print("  endpoint may be degraded or the expiry has no data.")
        print("  Surface to Nick before shipping.")
        for c in failing[:6]:
            print(f"    strike {c.get('strike')} {c.get('option_type')}: "
                  f"iv={c.get('implied_volatility')}")
        return 1

    sample = near_atm[0]
    print()
    print("PASS: every near-ATM strike (up to 5 each side, both call + put) has")
    print("      non-null implied_volatility. (v1.5 — Greeks not checked.)")
    print(f"  Sample (nearest-ATM contract):")
    print(f"    strike:      {sample.get('strike')}")
    print(f"    option_type: {sample.get('option_type')}")
    print(f"    iv:          {sample.get('implied_volatility')}")
    print(f"    bid:         {sample.get('bid')}")
    print(f"    ask:         {sample.get('ask')}")
    print(f"    mid:         {sample.get('mid')}")
    print()
    print("Cleared to commit + proceed to Task 5 (DAEDALUS SKILL.md + bundle).")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
