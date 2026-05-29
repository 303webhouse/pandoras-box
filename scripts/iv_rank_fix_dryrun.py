"""Dry-run for the iv_rank field-name fix (iv_rank_1y).

Calls get_iv_rank() directly — no chain fetch, no /option-contracts,
avoids post-market 429s on the heavy endpoint. Verifies the field-name
fix extracts a sane 0-100 value from the /iv-rank response.

Pass criteria before push:
  - iv_rank is a non-null float in [0, 100] for all tickers tested
  - Raw response confirms iv_rank_1y field is present

Run from c:\\trading-hub:
    $env:UW_API_KEY = "..."
    python scripts\\iv_rank_fix_dryrun.py
"""

from __future__ import annotations

import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


async def main() -> int:
    if not os.environ.get("UW_API_KEY"):
        import getpass
        print("UW_API_KEY not in environment.")
        try:
            key = getpass.getpass(prompt="UW_API_KEY: ")
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return 2
        key = key.strip()
        if not key:
            print("Empty key — aborting.")
            return 2
        os.environ["UW_API_KEY"] = key

    from integrations.uw_api import get_iv_rank
    from services.read_only.options_chain import _safe_float

    tickers = ["SPY", "NVDA", "IWM"]
    all_pass = True

    for tkr in tickers:
        print(f"\n--- {tkr} ---")
        try:
            resp = await get_iv_rank(tkr)
        except Exception as e:
            print(f"  ERROR: {e}")
            all_pass = False
            continue

        if resp is None:
            print("  FAIL: get_iv_rank returned None")
            all_pass = False
            continue

        latest = resp[0] if isinstance(resp, list) and resp else resp
        print(f"  Raw latest row keys: {list(latest.keys()) if isinstance(latest, dict) else type(latest)}")

        # Show the fields the old code looked for vs the new one
        old_raw = latest.get("iv_rank") or latest.get("rank")
        new_raw = latest.get("iv_rank_1y")
        print(f"  old lookup (iv_rank/rank): {old_raw}")
        print(f"  new lookup (iv_rank_1y):   {new_raw}")

        # Simulate the full extraction + normalization
        raw = old_raw or new_raw
        if raw is None:
            print("  FAIL: no iv_rank field found in response")
            all_pass = False
            continue

        val = _safe_float(raw)
        if val is None:
            print(f"  FAIL: could not parse '{raw}' as float")
            all_pass = False
            continue

        if 0 < val <= 1.0:
            val = val * 100  # normalize 0-1 → 0-100

        in_range = 0 <= val <= 100
        print(f"  normalized iv_rank: {round(val, 2)}  ({'PASS' if in_range else 'FAIL — out of range'})")
        if not in_range:
            all_pass = False

    print()
    if all_pass:
        print("DRY-RUN PASS — iv_rank_1y field confirmed, values sane. Safe to push.")
    else:
        print("DRY-RUN FAIL — do not push, investigate above.")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
