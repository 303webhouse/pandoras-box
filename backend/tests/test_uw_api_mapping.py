"""
Sprint 1 CI Gate — UW API Schema Mapping Tests

Calls every UW API endpoint through the normalization layer and asserts
output schema matches what Polygon consumers expect.

Run: python -m pytest backend/tests/test_uw_api_mapping.py -v
  or: python backend/tests/test_uw_api_mapping.py  (standalone)
"""

import asyncio
import os
import sys

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Test runner ──────────────────────────────────────────────────

RESULTS = []


def check(name: str, condition: bool, detail: str = ""):
    status = "PASS" if condition else "FAIL"
    RESULTS.append((name, status, detail))
    icon = "  OK " if condition else " FAIL"
    print(f"  [{icon}] {name}" + (f" — {detail}" if detail and not condition else ""))
    return condition


async def test_get_snapshot():
    """Verify get_snapshot() returns Polygon-compatible schema."""
    from integrations.uw_api import get_snapshot

    result = await get_snapshot("SPY")
    check("snapshot: returns data", result is not None)
    if not result:
        return

    check("snapshot: has 'ticker'", "ticker" in result)
    check("snapshot: has 'day' dict", isinstance(result.get("day"), dict))
    check("snapshot: day has 'c' (close)", "c" in result.get("day", {}))
    check("snapshot: day has 'v' (volume)", "v" in result.get("day", {}))
    check("snapshot: has 'prevDay'", "prevDay" in result)
    check("snapshot: has 'lastTrade'", "lastTrade" in result)

    # Verify types
    day = result["day"]
    if day.get("c") is not None:
        check("snapshot: day.c is numeric", isinstance(day["c"], (int, float)),
              f"got {type(day['c']).__name__}")


async def test_get_bars():
    """Verify get_bars() returns Polygon-compatible bar list."""
    from integrations.uw_api import get_bars

    result = await get_bars("SPY", 1, "day")
    check("bars: returns list", isinstance(result, list))
    if not result:
        return

    check("bars: has items", len(result) > 0, f"got {len(result)} bars")

    bar = result[-1]
    check("bars: bar has 'o' (open)", "o" in bar)
    check("bars: bar has 'h' (high)", "h" in bar)
    check("bars: bar has 'l' (low)", "l" in bar)
    check("bars: bar has 'c' (close)", "c" in bar)
    check("bars: bar has 'v' (volume)", "v" in bar)
    check("bars: bar has 't' (timestamp ms)", "t" in bar)

    # Verify types match Polygon (numeric, not strings)
    check("bars: o is float", isinstance(bar["o"], (int, float)),
          f"got {type(bar['o']).__name__}")
    check("bars: t is int (ms)", isinstance(bar["t"], int),
          f"got {type(bar['t']).__name__}")


async def test_get_bars_as_dataframe():
    """Verify get_bars_as_dataframe() returns pandas DataFrame."""
    from integrations.uw_api import get_bars_as_dataframe

    df = await get_bars_as_dataframe("SPY", days=5)
    check("bars_df: returns DataFrame", df is not None)
    if df is None:
        return

    import pandas as pd
    check("bars_df: is DataFrame", isinstance(df, pd.DataFrame))
    check("bars_df: has 'open' column", "open" in df.columns)
    check("bars_df: has 'close' column", "close" in df.columns)
    check("bars_df: has 'volume' column", "volume" in df.columns)
    check("bars_df: index is DatetimeIndex", isinstance(df.index, pd.DatetimeIndex))
    check("bars_df: has rows", len(df) > 0, f"got {len(df)} rows")


async def test_get_previous_close():
    """Verify get_previous_close() returns Polygon-compatible schema."""
    from integrations.uw_api import get_previous_close

    result = await get_previous_close("SPY")
    check("prev_close: returns data", result is not None)
    if not result:
        return

    check("prev_close: has 'results' list", isinstance(result.get("results"), list))
    if result.get("results"):
        prev = result["results"][0]
        check("prev_close: result has 'c'", "c" in prev)
        check("prev_close: result has 'T'", "T" in prev)


async def test_get_options_snapshot():
    """Verify get_options_snapshot() returns Polygon-compatible contract list."""
    from integrations.uw_api import get_options_snapshot

    result = await get_options_snapshot("SPY")
    check("options: returns list", isinstance(result, list))
    if not result:
        return

    check("options: has items", len(result) > 0, f"got {len(result)} contracts")

    contract = result[0]
    check("options: has 'details' dict", isinstance(contract.get("details"), dict))
    check("options: has 'greeks' dict", isinstance(contract.get("greeks"), dict))
    check("options: has 'day' dict", isinstance(contract.get("day"), dict))
    check("options: has 'last_quote' dict", isinstance(contract.get("last_quote"), dict))
    check("options: has 'implied_volatility'", "implied_volatility" in contract)

    details = contract["details"]
    check("options: details has 'contract_type'", "contract_type" in details)
    check("options: details has 'strike_price'", "strike_price" in details)
    check("options: details has 'expiration_date'", "expiration_date" in details)

    greeks = contract["greeks"]
    check("options: greeks has 'delta'", "delta" in greeks)
    check("options: greeks has 'gamma'", "gamma" in greeks)
    check("options: greeks has 'theta'", "theta" in greeks)
    check("options: greeks has 'vega'", "vega" in greeks)


async def test_get_flow_recent():
    """Verify get_flow_recent() returns flow data."""
    from integrations.uw_api import get_flow_recent

    result = await get_flow_recent("SPY")
    check("flow: returns list", isinstance(result, list))
    if not result:
        return
    check("flow: has items", len(result) > 0)
    item = result[0]
    check("flow: item has 'premium'", "premium" in item)
    check("flow: item has 'option_type'", "option_type" in item)
    check("flow: item has 'strike'", "strike" in item)


async def test_get_greek_exposure():
    """Verify get_greek_exposure() returns GEX data."""
    from integrations.uw_api import get_greek_exposure

    result = await get_greek_exposure("SPY")
    check("gex: returns list", isinstance(result, list))
    if not result:
        return
    check("gex: has items", len(result) > 0)
    item = result[0]
    check("gex: item has 'date'", "date" in item)
    check("gex: item has 'call_gamma'", "call_gamma" in item)
    check("gex: item has 'put_gamma'", "put_gamma" in item)


async def test_get_market_tide():
    """Verify get_market_tide() returns tide data."""
    from integrations.uw_api import get_market_tide

    result = await get_market_tide()
    check("tide: returns dict", isinstance(result, dict))
    if not result:
        return
    check("tide: has 'data'", "data" in result)


async def test_get_darkpool_recent():
    """Verify get_darkpool_recent() returns dark pool prints."""
    from integrations.uw_api import get_darkpool_recent

    result = await get_darkpool_recent()
    check("darkpool: returns list", isinstance(result, list))
    if not result:
        return
    check("darkpool: has items", len(result) > 0)
    item = result[0]
    check("darkpool: item has 'ticker'", "ticker" in item)
    check("darkpool: item has 'price'", "price" in item)
    check("darkpool: item has 'size'", "size" in item)


async def test_get_iv_rank():
    """Verify get_iv_rank() returns IV data."""
    from integrations.uw_api import get_iv_rank

    result = await get_iv_rank("SPY")
    check("iv_rank: returns list", isinstance(result, list))
    if not result:
        return
    check("iv_rank: has items", len(result) > 0)
    item = result[0]
    check("iv_rank: item has 'iv_rank_1y'", "iv_rank_1y" in item)


async def test_get_earnings():
    """Verify get_earnings_premarket() returns earnings data."""
    from integrations.uw_api import get_earnings_premarket

    result = await get_earnings_premarket()
    check("earnings: returns list", isinstance(result, list))
    # Earnings may be empty outside season — just check it doesn't error


async def test_get_economic_calendar():
    """Verify get_economic_calendar() returns events."""
    from integrations.uw_api import get_economic_calendar

    result = await get_economic_calendar()
    check("calendar: returns list", isinstance(result, list))
    if not result:
        return
    check("calendar: has items", len(result) > 0)
    item = result[0]
    check("calendar: item has 'event'", "event" in item)


async def test_get_short_interest():
    """Verify get_short_interest() returns SI data."""
    from integrations.uw_api import get_short_interest

    result = await get_short_interest("SPY")
    check("short_interest: returns list", isinstance(result, list))
    if not result:
        return
    check("short_interest: has items", len(result) > 0)
    item = result[0]
    check("short_interest: has 'short_interest'", "short_interest" in item)
    check("short_interest: has 'days_to_cover'", "days_to_cover" in item)


async def test_health():
    """Verify health check returns expected structure."""
    from integrations.uw_api import get_health

    result = await get_health()
    check("health: returns dict", isinstance(result, dict))
    check("health: has 'status'", "status" in result)
    check("health: has 'circuit_breaker'", "circuit_breaker" in result)
    check("health: has 'daily_requests'", "daily_requests" in result)
    check("health: has 'cache'", "cache" in result)


async def run_all():
    print("=" * 60)
    print("  Sprint 1 — UW API Schema Mapping Tests")
    print("=" * 60)

    tests = [
        test_get_snapshot,
        test_get_bars,
        test_get_bars_as_dataframe,
        test_get_previous_close,
        test_get_options_snapshot,
        test_get_flow_recent,
        test_get_greek_exposure,
        test_get_market_tide,
        test_get_darkpool_recent,
        test_get_iv_rank,
        test_get_earnings,
        test_get_economic_calendar,
        test_get_short_interest,
        test_health,
    ]

    for test_fn in tests:
        print(f"\n--- {test_fn.__name__} ---")
        try:
            await test_fn()
        except Exception as e:
            check(f"{test_fn.__name__}: no exception", False, str(e))

    # Summary
    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    total = len(RESULTS)

    print(f"\n{'='*60}")
    print(f"  RESULTS: {passed}/{total} passed, {failed} failed")
    print(f"{'='*60}")

    if failed > 0:
        print("\n  FAILURES:")
        for name, status, detail in RESULTS:
            if status == "FAIL":
                print(f"    - {name}" + (f": {detail}" if detail else ""))

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all())
    sys.exit(0 if success else 1)
