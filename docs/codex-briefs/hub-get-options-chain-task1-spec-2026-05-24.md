# Task 1 Findings — `hub_get_options_chain` Pre-Schema Reconnaissance (2026-05-25)

**Status:** Task 1 complete. Three threads investigated (1A spec, 1B singleflight, 1C math extraction). One material finding flagged for Nick before Task 2 proceeds.

**Predecessor:** `docs/codex-briefs/hub-get-options-chain-2026-05-24.md` (brief + ATLAS amendments at `fc86293`, `eea7bc8`).

---

## 1A — OpenAPI spec validation

### `/api/stock/{ticker}/option-contracts` (spec line 20043)

Query parameters confirmed: `expiry`, `option_type`, `limit` (default 500, max 500, min 1), `page`, plus convenience filters `vol_greater_oi`, `exclude_zero_vol_chains`, `exclude_zero_dte`, `exclude_zero_oi_chains`, `maybe_otm_only`, `option_symbol[]`. Brief's plan of "require `expiry` + optional `option_type`" maps cleanly.

**Schema (lines 6490-6577) — what the spec documents in `properties`:**

| Field | Type | Purpose |
|---|---|---|
| `option_symbol` | string | OCC-format symbol (e.g., `AAPL240202P00185000`) — encodes strike, expiry, type |
| `nbbo_bid` | string-numeric | Best bid |
| `nbbo_ask` | string-numeric | Best ask |
| `last_price` | string-numeric | Last trade price |
| `avg_price` | string-numeric | Day average |
| `high_price` / `low_price` | string-numeric | Day high/low |
| `volume` | int | Day volume |
| `open_interest` | int | OI |
| `prev_oi` | int | Previous day OI |
| `implied_volatility` | string-numeric | IV |
| `ask_volume` / `bid_volume` / `mid_volume` / `no_side_volume` | int | Volume by trade venue/side |
| `sweep_volume` / `floor_volume` / `multi_leg_volume` / `stock_multi_leg_volume` / `cross_volume` | int | Trade-type volume breakdowns |
| `total_premium` | string-numeric | Day notional |

### ⚠️ Critical finding: Greeks NOT in the documented schema

**The Option contracts schema (lines 6534-6577) does NOT list `delta`, `gamma`, `theta`, or `vega` as properties.** This is a real spec-vs-reality discrepancy:

- The OpenAPI spec we have (cached 2026-05-22) lists no Greeks fields.
- Existing `backend/integrations/uw_api.py` at lines 527-533 in `get_options_snapshot()` reads Greeks directly: `c.get("delta")`, `c.get("gamma")`, `c.get("theta")`, `c.get("vega")` — top-level fields on the UW contract object.
- The helper `_get_contract_greeks()` at line 1099 then reads from the normalized `greeks` sub-dict.

There are three possible explanations, ranked:
1. **The OpenAPI spec is incomplete for this endpoint.** Greeks are returned by UW but not documented in this version of the spec. Likeliest — UW spec docs are known to lag behind the actual API surface for newer fields, and Greeks are a relatively recent UW addition per the audit doc.
2. **Existing code reads non-existent fields and silently gets `None`.** This would mean every DAEDALUS-adjacent call path that uses `get_spread_value` / `get_single_option_value` / `get_multi_leg_value` / `get_ticker_greeks_summary` has been returning `None` Greeks all along. Less likely — there are 4 production callers and no bug reports about consistently-null Greeks.
3. **Greeks live elsewhere in the response under a different key** (e.g., nested under `greeks: {}` like the normalized output mirrors).

**Required before Task 3:** empirical probe of the live `/api/stock/SPY/option-contracts?expiry=2026-06-20` UW endpoint to confirm presence and field names of Greeks. Easiest path: a one-shot Python script run during market hours (or against the most recent close) that prints one raw UW contract object. Should be ~5 UW budget cost.

**Required before Task 2:** Nick decision on whether to proceed with Task 2 schema design assuming Greeks ARE returned (matching the existing code's read pattern), or wait for the empirical probe first. Recommendation: **proceed with Task 2 on the assumption Greeks are returned, since existing code paths read them with no observed null-Greeks bug reports.** Probe + revise schema at Task 3 if reality differs.

### `/api/stock/{ticker}/iv-rank` (spec line 19566)

Query params: optional `date` + `timespan`. Response schema name: `IV Rank`. The endpoint returns a list (the brief's existing wrapper `get_iv_rank` returns `data["data"]` as `Optional[List[Dict]]`). Confirms chain-LEVEL (not per-expiry) IV rank — single value at the ticker.

The wrapper's caller `sectors.py:_get_iv_rank_for_ticker` already extracts `latest = data[0] if isinstance(data, list) else data` and reads `latest.get("iv_rank")` — handles both list and dict shapes.

**For Task 2 schema:** `iv_rank` is a scalar at the chain level, not per-contract.

### `/api/stock/{ticker}/max-pain` (spec line 19614)

Query params: optional `date`. Description: *"Returns the max pain for all expirations for the given ticker for the last 120 days."* Response schema name: `Max Pain`.

The existing wrapper `get_max_pain` returns `data["data"]` as `Optional[Dict[str, Any]]` (per uw_api.py:851-866) — likely a dict keyed by expiry, since the description says "for all expirations." The brief's Task 2 strawman returns a SINGLE `max_pain` scalar.

**For Task 2 schema:** the service layer needs to **filter `max_pain` to the requested expiry only**. If the response is shaped `{expiry_date: max_pain_value, ...}`, lookup the requested expiry's value. If the response is shaped as a list of `{expiry, max_pain}` rows, find the matching expiry. Either way: surface a single scalar `max_pain` to the consumer; if the requested expiry isn't present in the max_pain response, return `null` for `max_pain` + add `aggregates_errors[]` row.

---

## 1B — Singleflight reconnaissance

### Existing hub tools: NO singleflight present

- `backend/services/read_only/quote.py` (210 lines): `get_quote()` makes 2-3 sequential UW calls (`/stock-state`, `/info`, `/ohlc/1d`) per invocation. **No coalescing.** Two concurrent `hub_get_quote SPY` calls = 2× the UW work.
- `backend/services/read_only/flow.py` (24 lines): thin wrapper around `api.flow_radar.get_flow_radar()`. No singleflight at this layer; underlying API endpoint uses Redis SCAN + Postgres SELECT (no UW calls per-request), so the stampede surface is non-existent here.

**Pattern: existing hub tools don't have singleflight because their UW-call profile is light (`hub_get_quote` ~3 UW calls cold) and the rate-limiter + circuit-breaker handle saturation.**

### Recommendation for `hub_get_options_chain`: **ADD singleflight**

Three reasons:
1. Cold-cache fetch = 3 UW calls (chain + iv_rank + max_pain), each multi-hundred-ms — **3× the cost** of `hub_get_quote`'s cold path.
2. The 500-result chain payload is large; concurrent fetches multiply Redis-side cache write pressure too.
3. DAEDALUS-heavy committee passes (e.g., a 7-agent Olympus pass with DAEDALUS being asked for multiple structures on the same ticker/expiry) are a realistic concurrent-caller scenario.

### Implementation approach (~25 lines)

Module-level coalesce dict in the service file:

```python
# backend/services/read_only/options_chain.py
import asyncio
from typing import Dict, Optional

_inflight: Dict[str, asyncio.Future] = {}
_inflight_lock = asyncio.Lock()


async def get_options_chain(ticker, expiry, option_type="both"):
    key = f"{ticker.upper()}:{expiry}:{option_type.lower()}"
    cached = await cache_get("option_chain_live", key)
    if cached:
        return cached

    # Singleflight: if a fetch for this key is in-flight, await its result.
    async with _inflight_lock:
        future = _inflight.get(key)
        if future is None:
            future = asyncio.get_event_loop().create_future()
            _inflight[key] = future
            owner = True
        else:
            owner = False

    if not owner:
        return await future

    try:
        result = await _fetch_uncached(ticker, expiry, option_type)
        await cache_set("option_chain_live", key, result)
        future.set_result(result)
        return result
    except Exception as e:
        future.set_exception(e)
        raise
    finally:
        async with _inflight_lock:
            _inflight.pop(key, None)
```

`_fetch_uncached()` is where the 3 UW calls happen (chain + iv_rank + max_pain composition).

The pattern: callers waiting on `future` get the same result the owner fetched; the in-flight future is cleaned up in `finally` so the next post-TTL-expiry fetch starts fresh. The `_inflight_lock` is a short-held mutex around dict mutation only.

**Edge case to handle:** if a cached result lands DURING an in-flight fetch (e.g., a separate process wrote to Redis), the in-flight fetch still completes — wasted work, not a correctness issue. Acceptable; could be optimized later if it shows up in metrics.

---

## 1C — `_get_contract_mid` extraction reconnaissance

### Callers inventory

`_get_contract_mid()` (`uw_api.py:1074`) has **exactly 3 call sites**, all within `uw_api.py`:

| Caller | Line(s) | Purpose |
|---|---|---|
| `get_spread_value` | 1143, 1144 (long + short legs) | Spread mark-to-market |
| `get_single_option_value` | 1191 | Single-leg position pricing |
| `get_multi_leg_value` | 1252 | Multi-leg position pricing (3+ legs) |

`_get_contract_greeks()` (`uw_api.py:1099`) has **4 call sites**, also all within `uw_api.py`:

| Caller | Line(s) | Purpose |
|---|---|---|
| `get_spread_value` | 1164, 1165 | Spread greeks output |
| `get_single_option_value` | 1202 | Single-leg greeks output |
| `get_multi_leg_value` | 1270 | Multi-leg greeks output |
| `get_ticker_greeks_summary` | 1315, 1329 | Ticker-level greeks aggregation |

`_find_contract()` (`uw_api.py:1060`) has multiple call sites in the same family.

### Recommendation: **extract `_get_contract_mid` + `_get_contract_greeks` to `backend/utils/options_math.py`**

ATLAS's specific concern was the `_get_contract_mid` duplication risk. Extracting BOTH at once is the same effort (~10 minutes), and both have the same drift-risk profile: the chain-display path and the position-pricing path will both reference the canonical implementation.

Proposed module signature:

```python
# backend/utils/options_math.py
"""Shared options-math helpers consumed by both the integrations layer
(uw_api.py spread/single/multi-leg valuators) and the hub_get_options_chain
service layer. Single source of truth for mid-price and Greeks extraction
prevents drift between position-pricing and chain-display computations.
"""

from typing import Any, Dict, Optional


def compute_mid(contract: Dict[str, Any]) -> Optional[float]:
    """Mid-price from bid/ask, falling back to last trade, day close, vwap.

    Operates on the normalized contract dict shape returned by
    integrations.uw_api.get_options_snapshot() — keys:
        last_quote.{bid, ask}
        last_trade.price
        day.{close, vwap}
    """
    # ... same body as current _get_contract_mid ...


def compute_bid_ask_spread_pct(contract: Dict[str, Any]) -> Optional[float]:
    """Bid-ask spread as % of mid. Used by DAEDALUS's >10% liquidity flag.

    Returns None if mid is unavailable or zero, or if bid/ask are missing.
    """
    quote = contract.get("last_quote", {})
    bid = quote.get("bid")
    ask = quote.get("ask")
    if not (bid and ask) or not (float(bid) > 0 and float(ask) > 0):
        return None
    mid = compute_mid(contract)
    if mid is None or mid == 0:
        return None
    spread = abs(float(ask) - float(bid))
    return round((spread / mid) * 100, 2)


def extract_greeks(contract: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Greeks dict from normalized contract. Single source of truth."""
    greeks = contract.get("greeks", {})
    return {
        "delta": greeks.get("delta"),
        "gamma": greeks.get("gamma"),
        "theta": greeks.get("theta"),
        "vega": greeks.get("vega"),
        "iv": contract.get("implied_volatility"),
    }
```

### Refactor surface in `uw_api.py`

- Lines 1074-1096 (`_get_contract_mid`): delete; replace with `from utils.options_math import compute_mid` at top.
- Lines 1099-1108 (`_get_contract_greeks`): delete; replace with `from utils.options_math import extract_greeks` at top.
- 3 + 4 = **7 call-site replacements** (each is a name change: `_get_contract_mid(c)` → `compute_mid(c)`, `_get_contract_greeks(c)` → `extract_greeks(c)`).

**No semantic change.** Behavior is byte-for-byte identical to the existing implementation.

### `compute_bid_ask_spread_pct` is genuinely new

It's not in `uw_api.py` today (Phase B didn't need it; DAEDALUS used a screenshot or qualitative inference). New function in `options_math.py`. No existing caller to refactor; only the new `hub_get_options_chain` service layer uses it.

---

## Pre-Task-2 surfacing for Nick

**Greens (proceed to Task 2 as designed):**
- ✅ Endpoint surface (1A): `/option-contracts` accepts `expiry` + `option_type` natively; the 500-cap is respected by requiring `expiry`.
- ✅ Singleflight (1B): clean 25-line pattern; existing tools lack it but new tool should add it given the 3-UW-call cold profile.
- ✅ Math extraction (1C): 7 call sites, no semantic change, ~10-minute refactor. ATLAS push-back validated.
- ✅ Aggregates: `iv_rank` is chain-level scalar; `max_pain` requires filtering the multi-expiry response to the requested expiry — Task 2 schema needs to handle this.

**Yellow (proceed to Task 2 with explicit assumption to revisit at Task 3):**
- ⚠️ Greeks presence in `/option-contracts` response (1A critical finding): OpenAPI spec doesn't document `delta/gamma/theta/vega` as properties, but existing `uw_api.py` code reads them via `c.get("delta")` etc. Either the spec is incomplete (most likely) or existing code silently gets None. Recommendation: **proceed with Task 2 schema assuming Greeks ARE returned** (matches existing code reads), and run a 5-UW-call empirical probe during Task 3 to verify. If reality differs, revise schema.

**No reds.** No blocker requiring a brief rewrite. Material assumption (Greeks presence) flagged with explicit revisit gate.

---

## Recommended Task 2 schema adjustments (from 1A findings)

Brief's Task 2 strawman is mostly intact. Two specific tweaks the findings recommend:

1. **`max_pain` selection logic.** Service layer must filter the multi-expiry `get_max_pain()` response to the requested `expiry`. If the requested expiry isn't present in the max_pain response (possible on a 120-day max-pain coverage gap), set `max_pain: null` + add `aggregates_errors[{"field": "max_pain", "reason": "no max-pain data for this expiry"}]`.
2. **`iv_rank` shape handling.** The wrapper returns `Optional[List[Dict]]`. The service layer extracts `latest = response[0] if isinstance(response, list) else response`; reads `latest.get("iv_rank")` as a float (or null). Surface single scalar to the consumer.

Other Task 2 schema fields stay as the strawman specifies.

---

## What this enables for Task 2

Task 2 schema design can now proceed with:
- Confirmed input parameters (`ticker`, `expiry` required, `option_type` default "both")
- Confirmed per-contract field set (with Greeks-assumption flag)
- Confirmed aggregates flow (`iv_rank` scalar, `max_pain` filtered to expiry)
- Confirmed partial-failure semantics (chain required, aggregates optional with `aggregates_errors[]`)
- Confirmed singleflight pattern (add to service layer)
- Confirmed math-extraction plan (new `backend/utils/options_math.py` module, refactor 7 call sites in `uw_api.py`)

PAUSE #2 is the next stop — post-Task 2 schema design, before Task 3 code. Nick gets the schema for ATLAS sign-off.
