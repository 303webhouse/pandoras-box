# Task 2 — `hub_get_options_chain` Schema Design (2026-05-26)

**Status:** Task 2 deliverable. Schema design only; no code. PAUSE #2 next — canonical ATLAS skill review before Task 3 implementation.

**Predecessors:**
- Brief: [hub-get-options-chain-2026-05-24.md](hub-get-options-chain-2026-05-24.md) (`fc86293`)
- ATLAS amendments: (`eea7bc8`)
- Task 1 findings + amendments: [hub-get-options-chain-task1-spec-2026-05-24.md](hub-get-options-chain-task1-spec-2026-05-24.md) (`d4f96ae`, `e20a166`, `4c92db1`)

> **AMENDMENT 2026-05-26 — Greeks-present assumption restored, Option-A fallback gated to Task 3.**
>
> The 2026-05-25 Memorial Day probe returned `delta/gamma/theta/vega = null` on the sample SPY contract. Two equally-consistent explanations:
> 1. **Spec-correct interpretation:** Greeks are genuinely not in `/option-contracts` responses; existing 4 production-code consumers (`get_spread_value`, `get_single_option_value`, `get_multi_leg_value`, `get_ticker_greeks_summary`) read `c.get("delta")` and have been silently getting None for years without anyone noticing.
> 2. **Market-closed interpretation:** UW doesn't refresh per-contract Greeks on non-trading days; the spec is just lagging. Greeks DO populate during live market sessions — that's why the 4 production consumers haven't surfaced visible bugs.
>
> The 4-production-consumer argument is empirically strong: zero delta on a real position priced at $1.50 mid would have produced obvious bugs (mark-to-market drift, sizing math errors, broker-quote mismatches). Nothing of the kind has been reported. Spec-lag is the overwhelmingly likely explanation.
>
> **Decision:** revert to Greeks-present assumption. Schema includes `delta/gamma/theta/vega` fields. Task 3 implementation must include an **empirical verification probe during a live market session** (Tuesday 2026-05-26 ≥09:30 ET) as the first smoke check — fail-stop if Greeks remain null then, with a documented Option-A fallback path (drop Greeks fields, ship as v1.5 with the qualitative-Greeks-mode caveat from the prior Task 1 Amendment #2).
>
> The earlier Task 1 Amendment #2 (Option C exhausted, Option A recommendation) is now superseded by this revision. The follow-up brief for per-contract Greeks (Black-Scholes / UW subscription tier / alternate provider) is descoped from v1 since Greeks are expected to populate from UW directly; it remains a useful Tier 2 item only if Task 3's empirical verification fails.

**Nick decisions applied (final):**
- PAUSE #1: empirical UW probe ran on Memorial Day, returned nulls (inconclusive due to market closure)
- Greeks: **Greeks-present assumption restored** based on production-code chain evidence; Task 3 verification gate during live market session is fail-stop
- Two Task 2 schema tweaks approved: `max_pain` filtered to requested expiry with `aggregates_errors` markers; `iv_rank` list-or-scalar normalization
- PAUSE #2: canonical ATLAS skill review (not CC self-review) before Task 3 code

---

## Tool signature (final)

```python
@mcp_tool(name="hub_get_options_chain", description=DESCRIPTION)
async def hub_get_options_chain(
    ticker: str,
    expiry: str,                     # REQUIRED. ISO date "YYYY-MM-DD".
    option_type: str = "both",       # "both" | "call" | "put"
) -> dict:
```

Input validation:
- `ticker`: non-empty string, uppercased internally
- `expiry`: parseable as ISO date `YYYY-MM-DD` (the wrapper raises `400 invalid_request` semantically — envelope `status="unavailable"` with `error` field)
- `option_type`: enum check — `{"both", "call", "put"}`; anything else → `status="unavailable"` with `error` field

DESCRIPTION (visible to Claude as tool capability) — strawman to refine at Task 3:

> Returns the live options chain for a single ticker + expiry from Pandora's Box hub via Unusual Whales: per-contract bid/ask/mid/volume/OI/implied-volatility/liquidity-flag, plus chain-level aggregates (IV rank, max pain, total OI). Use when DAEDALUS needs to evaluate specific strikes for structure selection (debit/credit spreads, condors, risk reversals) or read current IV regime quantitatively rather than inferring from price action.
>
> Greeks (delta/gamma/theta/vega) are NOT in v1 — UW's chain endpoint does not expose them. DAEDALUS continues to operate in qualitative-Greeks-mode for now; a Tier 2 follow-up brief is queued to add Greeks via Black-Scholes computation or an alternate source. IV rank + per-contract implied_volatility ARE quantitative in v1 — DAEDALUS gets the IV side of the qualitative-IV-mode caveat closed immediately.
>
> `expiry` is REQUIRED. No "give me all expirations" calls; UW's 500-result cap means callers must pick the contract surface they care about. PKCE-enforced, allowlisted, gated by `_shared/COMMITTEE_RULES.md § Hub MCP Preflight`.

---

## Response envelope (final)

```json
{
  "status": "ok" | "stale" | "unavailable",
  "summary": "AAPL 2026-06-19 chain: 142 contracts (71C/71P), IVR 42.1, max pain $190, total OI 387,412",
  "staleness_seconds": null | <int>,
  "error": null | "<short reason>",
  "data": {
    "ticker": "AAPL",
    "expiry": "2026-06-19",
    "spot": 185.42,
    "uw_timestamp": "2026-05-26T20:15:33Z",

    "iv_rank": 42.1,
    "max_pain": 190.0,
    "total_open_interest": 387412,
    "total_call_oi": 198330,
    "total_put_oi": 189082,

    "aggregates_errors": null,

    "contracts": [
      {
        "strike": 185.0,
        "option_type": "call",
        "bid": 4.20,
        "ask": 4.35,
        "mid": 4.275,
        "bid_ask_spread_pct": 3.51,
        "volume": 1240,
        "open_interest": 8420,
        "implied_volatility": 0.28,
        "delta": 0.52,
        "gamma": 0.045,
        "theta": -0.08,
        "vega": 0.18
      },
      ...
    ]
  }
}
```

### Field-by-field decisions

**Envelope (top-level):**
- `status` — `ok` / `stale` / `unavailable`. `stale` fires if `uw_timestamp` is more than 5 minutes old during market hours (matches `hub_get_quote` precedent).
- `summary` — terse one-liner for the tool selector / DATA NOTE block. Adapts when aggregates fail (e.g., "max pain unavailable").
- `staleness_seconds` — populated when `status="stale"`.
- `error` — populated when `status="unavailable"`. Short string naming the failure (e.g., "UW chain endpoint returned no data" or "invalid expiry format").

**`data` block (chain-level):**
- `ticker` — uppercased symbol.
- `expiry` — echoed back as ISO date for caller verification.
- `spot` — current underlying spot price. Either propagated from the `/option-contracts` response's `stock_price` field (the schema confirms its presence) or derived via a separate `get_snapshot()` call if `stock_price` is null. **Decision:** prefer `stock_price` from the chain response (1 call vs. 2); fall back to `get_snapshot()` only if absent.
- `uw_timestamp` — propagated from the `/option-contracts` response's `last_fill` field on the most recent contract, OR `datetime.now(timezone.utc).isoformat()` with a synthetic flag if absent. **Decision:** use the chain response's freshest `last_fill` as authoritative; synthetic fallback (with no flag — keep envelope clean, log a WARNING at the service layer).
- `iv_rank` — chain-level scalar from `/iv-rank`. Extracted via `latest = response[0] if isinstance(response, list) else response; latest.get("iv_rank")`. Type: float (0-100) or null.
- `max_pain` — filtered to the requested `expiry` from the `/max-pain` multi-expiry response. Type: float or null.
- `total_open_interest`, `total_call_oi`, `total_put_oi` — computed at the service layer by summing `open_interest` across the filtered contract list. Integer.
- `aggregates_errors` — null if no aggregate failures; otherwise an array of `{field, reason}` objects naming which aggregates couldn't be populated. Per Task 3's partial-failure semantics.

**`contracts[]` (per-contract):**
- `strike` — float, parsed from option_symbol's 8-digit strike segment (already done in `uw_api._parse_option_symbol`).
- `option_type` — `"call"` or `"put"` (lowercase, normalized).
- `bid` — float or null. Maps to `nbbo_bid` in the UW response.
- `ask` — float or null. Maps to `nbbo_ask`.
- `mid` — computed via `backend/utils/options_math.py` `compute_mid()` (extracted per Task 1C from existing `_get_contract_mid()`). Same fallback chain: bid/ask mid → last_trade → day close → vwap. Float or null.
- `bid_ask_spread_pct` — computed via `backend/utils/options_math.py` `compute_bid_ask_spread_pct()`. Float or null. Used by DAEDALUS's >10%-liquidity-flag hard rule.
- `volume` — int. Maps to `volume`.
- `open_interest` — int. Maps to `open_interest`.
- `implied_volatility` — float or null. Maps to `implied_volatility`.
- `delta`, `gamma`, `theta`, `vega` — float or null. Maps to `delta`/`gamma`/`theta`/`vega` on the UW contract response. **Subject to Task 3 empirical verification gate**: if a live-market probe confirms these stay null during a real session, drop the fields and fall back to the Option-A v1.5 schema (qualitative-Greeks-mode caveat per prior Task 1 Amendment #2).

**Why `last_price` / `last_trade` are not surfaced separately:**
- They feed `compute_mid()`'s fallback chain at the service layer. Exposing them again at the consumer interface would invite drift; DAEDALUS only ever needs `mid` for premium math.

**Sorting:**
- `contracts[]` sorted ascending by `strike`. Within same strike: calls before puts.

---

## Partial-failure semantics (final per Task 3)

| Upstream call | Criticality | Failure behavior |
|---|---|---|
| `get_options_snapshot` (the chain) | **REQUIRED** | If returns None → envelope `status="unavailable"`, `error="UW chain endpoint returned no data"`. No partial data shipped. |
| `get_iv_rank` (chain-level aggregate) | OPTIONAL | If returns None → `data.iv_rank = null`, append to `data.aggregates_errors`: `{"field": "iv_rank", "reason": "upstream unavailable"}`. Envelope `status="ok"`. |
| `get_max_pain` (filtered to expiry) | OPTIONAL | If returns None OR requested expiry not in response → `data.max_pain = null`, append `{"field": "max_pain", "reason": "no max-pain data for this expiry"}`. Envelope `status="ok"`. |

Edge case: if BOTH `iv_rank` AND `max_pain` fail, `aggregates_errors` has 2 entries. Chain still succeeds. Summary text becomes: *"AAPL 2026-06-19 chain: 142 contracts, aggregates partial (iv_rank+max_pain unavailable), total OI 387k"*.

`aggregates_errors` is OMITTED from the response (key absent or `null`) when no errors — keeps the envelope clean for the happy path. Present and populated only when failures occurred.

---

## Singleflight pattern (final per Task 3 implementation)

Per Task 1B reconnaissance: existing hub tools (`quote.py`, `flow.py`) lack singleflight; new tool adds it because cold-cache fetch = 3 UW calls multi-hundred-ms each, and concurrent DAEDALUS invocations during committee passes are a realistic load profile.

Implementation (~25 lines at the service layer):

```python
# backend/services/read_only/options_chain.py — module-level
_inflight: dict[str, asyncio.Future] = {}
_inflight_lock = asyncio.Lock()


async def get_options_chain(ticker, expiry, option_type="both"):
    key = f"{ticker.upper()}:{expiry}:{option_type.lower()}"
    cached = await cache_get("option_chain_live", key)
    if cached:
        return cached

    # Coalesce concurrent cache-miss callers for the same key.
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

`_fetch_uncached()` is where the 3 UW calls compose (chain + iv_rank + max_pain). Errors propagate to all coalesced callers (one upstream blip → all N callers see the same error, not N independent retries blowing the rate limit).

---

## Cache key format (final per Task 4)

Per ATLAS amendment (c):

```
Full Redis key:  uw:option_chain_live:{TICKER}:{expiry}:{option_type}
                 │         │             │        │       └─ "both" | "call" | "put" (lowercase)
                 │         │             │        └─ "YYYY-MM-DD" (ISO)
                 │         │             └─ uppercase symbol
                 │         └─ TTL category (25s)
                 └─ existing uw_api_cache.py wrapper prefix
```

Service-layer call: `await cache_get("option_chain_live", f"{ticker.upper()}:{expiry}:{option_type.lower()}")`. Separator throughout is `:` (not `|`), conforming to ATLAS's literal specification.

---

## `backend/utils/options_math.py` extraction (final per Task 1C)

New module signature:

```python
"""Shared options-math helpers consumed by both integrations/uw_api.py
(spread/single/multi-leg valuators) and the new hub_get_options_chain
service layer. Single source of truth eliminates drift between
position-pricing and chain-display computations.
"""

from typing import Any, Dict, Optional


def compute_mid(contract: Dict[str, Any]) -> Optional[float]:
    """Mid-price from bid/ask, falling back to last trade, day close, vwap.

    Operates on the normalized contract dict shape from
    integrations.uw_api.get_options_snapshot(). Fallback chain identical
    to the prior _get_contract_mid() implementation.
    """
    # body lifted byte-for-byte from existing _get_contract_mid()


def compute_bid_ask_spread_pct(contract: Dict[str, Any]) -> Optional[float]:
    """Bid-ask spread as % of mid. Used by DAEDALUS's >10% liquidity flag.

    Returns None if mid is unavailable/zero, or if bid/ask are missing.
    """
    # new helper — see Task 1 findings for body
```

### Refactor at `backend/integrations/uw_api.py`

- Lines 1074-1096 (`_get_contract_mid`): delete the body; replace with `from utils.options_math import compute_mid` at top of file.
- Lines 1099-1108 (`_get_contract_greeks`): delete the body; replace with `from utils.options_math import extract_greeks` at top of file.
- 3 + 4 = **7 call-site replacements** total: `_get_contract_mid(c)` → `compute_mid(c)`; `_get_contract_greeks(c)` → `extract_greeks(c)`.

The Greeks extraction comes back in scope under the Greeks-present assumption (the new service layer needs `extract_greeks` for the per-contract Greeks list, and consolidating with the 4 existing callers is the same single-source-of-truth ATLAS pattern from amendment (b)).

Net effect: byte-for-byte identical position-pricing behavior; new chain-display path uses the same canonical `compute_mid` + `extract_greeks` helpers.

`backend/utils/options_math.py` module signature gains a third function vs. the prior Option-A version:

```python
def extract_greeks(contract: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Greeks dict from normalized contract. Single source of truth.
    
    Returns {delta, gamma, theta, vega, iv} — float-or-None values
    propagated as-is from the normalized contract dict. The chain-display
    path surfaces these in the contracts[] array; the position-pricing
    path (get_spread_value etc.) consumes them via the same function.
    """
    # body identical to current _get_contract_greeks()
```

---

## DAEDALUS SKILL.md edit at Task 6 (final under Greeks-present assumption)

Replace `skills/daedalus/SKILL.md` lines 71-77 (the "DAEDALUS-specific data caveat") with:

> **Caveat closed (post-`hub_get_options_chain` v1):** DAEDALUS now gets per-contract Greeks (delta/gamma/theta/vega) + implied_volatility, chain-level IV rank, max pain (per expiry), and full chain pricing (bid/ask/mid/volume/OI/spread-pct) via `hub_get_options_chain(ticker, expiry, option_type="both")`. The qualitative-IV-mode fallback from the pre-v1 caveat is no longer the operating mode; DAEDALUS now reasons quantitatively about Greeks and IV regime by default.
>
> Fallback contract: if `hub_get_options_chain` returns `status="unavailable"` (UW outage, rate-limit-induced failure, expiry not on the chain), DAEDALUS reverts to the original qualitative-IV/Greeks-inference mode — same as the pre-v1 default — and surfaces "chain unavailable" in the DATA NOTE.
>
> Per-aggregate degradation: when `hub_get_options_chain` returns `aggregates_errors` populated (e.g., `iv_rank` missing but chain succeeded), surface in the DATA NOTE and degrade conviction one notch per missing aggregate, same as the existing `hub_get_quote` staleness protocol.

**If Task 3's empirical verification reveals Greeks come back null during live market hours:** revert the SKILL.md edit to the Option-A "qualitative-Greeks-mode" language from prior Task 1 Amendment #2. Schema also drops the four Greeks fields. This is the v1.5 fallback path documented above.

Add `hub_get_options_chain` to the Context A tool calls list (lines 61-69), between current entries 2 (`hub_get_flow_radar`) and 3 (`hub_get_hydra_scores`):

> 3. `hub_get_options_chain(ticker=<the ticker>, expiry=<chosen DTE expiry>)` — chain pricing + IV rank + per-contract IV + max pain for the expiry DAEDALUS is reasoning about. Required when proposing specific strikes, expirations, or evaluating bid-ask liquidity for structure selection. The `bid_ask_spread_pct` field directly feeds DAEDALUS's >10%-liquidity-flag hard rule.

Renumber subsequent entries.

`daedalus.skill` bundle rebuild via `scripts\package-skill.ps1 daedalus`. Nick re-uploads to claude.ai manually post-merge (same workflow as the Hub MCP Preflight rollout).

---

## Updated Output spec (vs. brief's original)

```
Modified:  backend/integrations/uw_api_cache.py       (new option_chain_live: 25 TTL entry)
Modified:  backend/integrations/uw_api.py             (import compute_mid from new module; 3 call sites)
New:       backend/utils/options_math.py              (compute_mid + compute_bid_ask_spread_pct)
New:       backend/services/read_only/options_chain.py (service layer w/ singleflight + composition)
New:       backend/hub_mcp/tools/options_chain.py     (MCP tool layer)
Modified:  skills/daedalus/SKILL.md                   (tool-list insertion + qualitative-Greeks-mode caveat update)
New:       dist/skills/daedalus.skill                 (rebuilt bundle — dist/ is gitignored)
New:       docs/strategy-reviews/hub-get-options-chain-closure-note-YYYY-MM-DD.md

Deferred to Tier 2 follow-up brief:
  - _get_contract_greeks extraction to options_math.py (no consumer until Greeks land)
  - Per-contract Greeks (Black-Scholes compute, UW tier inquiry, or alternate provider)
```

Estimated implementation time: ~3-4 hours code + ~1 hour smoke + ~30 min closure note. Roughly halved from the brief's estimate because Greeks-handling is now scope-out.

---

## Task 3 first-smoke gate (Greeks verification)

Before any other smoke check runs, Task 3 implementation must do an empirical live-market probe:

```
GATE: hub_get_options_chain(ticker="SPY", expiry=<next monthly>, option_type="both")
      called at ≥09:30 ET Tuesday 2026-05-26 (or any future trading-day open)

Pass criterion: ≥ 50% of contracts in the response have non-null delta AND
                non-null implied_volatility.

If pass: proceed with the rest of Task 7 smoke checks; schema as designed is valid.
If fail: stop. Drop delta/gamma/theta/vega from the schema. Revert SKILL.md edit to
        the qualitative-Greeks-mode language from Task 1 Amendment #2. Ship as v1.5
        (Option A schema) and queue the per-contract-Greeks follow-up brief.
```

The 50% threshold accounts for the long tail of OTM/illiquid strikes UW may not bother computing Greeks for, while requiring the broad-strike bulk of the chain be populated.

---

## PAUSE #2 — canonical ATLAS skill review checklist

Nick will invoke the canonical ATLAS skill (not CC self-review) for the architectural pass. Items the review should confirm:

1. **Schema completeness:** does the response give DAEDALUS everything it needs to produce its committee-mode output template (`skills/daedalus/SKILL.md` lines 96-121) including the Greeks lines under the Greeks-present assumption?
2. **Greeks verification gate logic:** is the 50%-of-contracts threshold the right pass/fail criterion for the Task 3 first-smoke? Should the gate require non-null on a specific set of liquid ATM strikes instead, or is the simpler population-rate check sufficient?
3. **Singleflight pattern:** is the module-level dict + asyncio.Future approach idiomatic for this codebase? Or should it borrow from an existing helper somewhere?
4. **Cache key correctness:** does the literal `uw:option_chain_live:{TICKER}:{expiry}:{option_type}` shape match what ATLAS specified, including the `:` separator throughout?
5. **Partial-failure asymmetry:** are the chain-required / aggregates-optional split + `aggregates_errors[]` array shape sensible? Does omitting the field when empty (vs. always returning `null`) match the codebase's existing envelope conventions?
6. **`compute_mid` + `extract_greeks` extraction:** is it safe to move both functions while preserving exact behavior? (Spot check: the bid/ask-mid → last_trade → day.close → day.vwap fallback chain in `compute_mid`; the contract.get("greeks", {}) sub-dict reads in `extract_greeks`.)
7. **`compute_bid_ask_spread_pct` denominator:** spread = `abs(ask - bid)`, denominator = `mid`. Some shops compute as `spread/mid_at_mid_price`; some as `spread/ask`. Confirm `mid` is the right denominator for DAEDALUS's >10% gate.
8. **DAEDALUS SKILL.md edit (Greeks-present version):** does the "caveat closed" language correctly describe the post-v1 state, and is the Context A tool-list insertion position right (after `flow_radar`, before `hydra_scores`)? Plus: does the documented Option-A v1.5 fallback path read cleanly if Task 3's verification gate fails?

If any flag, surface before Task 3 code starts.

Holding here.
