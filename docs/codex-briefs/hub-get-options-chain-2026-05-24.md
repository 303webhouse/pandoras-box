# CC Brief: `hub_get_options_chain` MCP tool (2026-05-24)

**Bucket:** Tier 2 — committee infrastructure. Direct enabler for DAEDALUS to exit qualitative-IV mode.
**Branch strategy:** Direct on `main` (focused additive build; no risky cross-cutting changes). Standard merge-then-smoke-then-revert discipline.
**Predecessors:** DAEDALUS SKILL.md explicitly tags this as the **lowest-effort of the three v2 hub MCP tools** (UW already exposes the data; the hub just wraps it). Per `skills/daedalus/SKILL.md` line 77: *"When it lands, DAEDALUS gets live Greeks and IV rank without needing screenshots."*

## Purpose

Today DAEDALUS operates in **qualitative-IV mode** when no chain screenshot is provided: it can frame conviction around inferred IV regime from price action + VIX context, but it cannot cite specific Greeks (delta, theta, gamma, vega) or precise IV rank for the chain it's reasoning about. The 2026-05-24 DAEDALUS pass on XLE that just ran is a clean example — TORO got `hub_get_sector_strength`, `hub_get_bias_composite`, etc., but DAEDALUS would have flagged *"Precise Greeks / IV rank require chain snapshot — current analysis uses inferred IV regime from price action + VIX context."*

`hub_get_options_chain` closes that gap. It exposes the UW options chain (already wrapped at the integration layer via `get_options_snapshot`) through a stripped-down MCP envelope sized for what DAEDALUS actually consumes, plus chain-level aggregates (IV rank, max pain, total OI) for cohesion.

## Design decisions (locked, applied throughout)

These were settled in chat prior to brief authoring; the brief embeds them as constraints, not options:

1. **`expiry` parameter is REQUIRED.** No "give me all expirations" — caller must specify. Rationale: UW's `/option-contracts` endpoint has a 500-result cap (per audit doc, line 10294); requiring expiry keeps response sizes bounded and forces callers to be explicit about the contract surface they care about. DAEDALUS picks expiries; the tool doesn't dump the universe.
2. **Response shape stripped to fields DAEDALUS actually consumes.** Per output template at `skills/daedalus/SKILL.md` lines 96-121, that's: strike, expiration, option_type, bid, ask, mid (computed), volume, open_interest, delta, gamma, theta, vega, implied_volatility, and a bid-ask-spread-pct flag (DAEDALUS hard rule: >10% disqualifies). Everything else from the raw UW response is dropped at the service layer.
3. **Cache TTL < 30s in a separate namespace from the existing slower-data cache.** Existing `option_contracts` cache uses 300s TTL — that's appropriate for the position-pricing path but too long for the live-strike-selection path DAEDALUS uses. New cache category `option_chain_live` at 25s TTL. Keeps the two paths from cross-contaminating cached state.
4. **Chain-level aggregates included in same response.** IV rank (chain-level, from `/iv-rank`), max pain (from `/max-pain`), and total OI (computed sum across the chain) returned alongside the per-contract list in one envelope. Cohesion — DAEDALUS gets the full structural picture for the expiry in one call instead of three.
5. **`option_type` default = "both"** (calls + puts combined). Filterable to `"call"` or `"put"` if needed. Rationale: most DAEDALUS structures span both sides of the chain (debit/credit spreads, condors, risk reversals); combined-default avoids forcing two calls when one suffices. **Concrete revisit triggers** (ATLAS-mandated, replaces "Tier 2 follow-up"): default behavior is reviewed for a tighter filter if EITHER of these conditions holds:
   - **Budget pressure:** UW daily request counter exceeds 50% of the 20K budget (≥10K calls/day) for 3 consecutive trading days, attributable in part to `hub_get_options_chain` traffic — AND
   - **Cache inefficiency:** the `option_chain_live` cache hit rate (tracked via `get_cache_stats()` in `uw_api_cache.py`) is below 30% over a 7-day rolling window.
   
   If both fire, the default flips to `"call"` for bull-biased committee context and `"put"` for bear-biased, with `"both"` available on explicit caller request. Until both fire, default stays at `"both"`.

## Pre-flight (mandatory)

1. `cd /d C:\trading-hub`
2. `git fetch && git status` — confirm clean tree on `main` at the post-Phase-B SHA (currently `70ed5a8` or later).
3. Read `PROJECT_RULES.md` § Data Source Hierarchy.
4. Read `docs/uw-integration-audit-2026-05-22.md` § 2.1 (existing wrapper inventory) — confirm `get_options_snapshot`, `get_iv_rank`, `get_max_pain` are the right composition primitives.
5. Read `backend/hub_mcp/tools/quote.py` and `backend/hub_mcp/tools/flow_radar.py` — pattern references for the new tool.
6. Read `skills/daedalus/SKILL.md` Output Format template (lines 92-121) — definitive list of consumed fields.
7. Confirm `UW_API_KEY` set in Railway env. Do NOT print, log, or commit values.

## Tasks

### Task 1 — Validate UW response shape + reconnaissance for Task 2 inputs

**Before any schema design or code.** Three investigation threads, all output to the Task 1 findings note:

#### 1A — OpenAPI spec validation

Open `docs/audit-artifacts/2026-05-22/uw-openapi.yaml` and read the three relevant endpoint definitions:

- `/api/stock/{ticker}/option-contracts` (line 20043 region) — confirm field availability and types: `option_symbol`, `nbbo_bid`, `nbbo_ask`, `last_price`, `volume`, `open_interest`, `delta`, `gamma`, `theta`, `vega`, `implied_volatility`. Note the 500-result cap (line 10294 advisory).
- `/api/stock/{ticker}/iv-rank` (line 19566 region) — confirm `iv_rank` field shape and whether it's per-expiry or chain-wide.
- `/api/stock/{ticker}/max-pain` (line 19614 region) — confirm `max_pain` field and series structure.

#### 1B — Cache-stampede / singleflight reconnaissance (ATLAS-mandated)

Read the existing hub tool service layers (`backend/services/read_only/quote.py`, `backend/services/read_only/flow.py`) to determine whether they implement any concurrency coalescing for the "many requests for the same cache-missed key arrive simultaneously" scenario.

Background: a cache stampede happens when N concurrent callers all hit a cache MISS for the same key and each independently fires the expensive upstream call. Singleflight (a.k.a. request coalescing) ensures only ONE upstream call fires; the others wait for the in-flight result. For option chains specifically, cold-cache fetch = 3 UW calls (chain + iv_rank + max_pain), each multi-hundred-ms; concurrent DAEDALUS invocations across overlapping committee passes are a realistic load profile.

Output:
- Whether existing tools have singleflight (yes / no / partial).
- If absent: a recommended implementation approach for the new tool — likely a module-level `dict[str, asyncio.Future]` keyed by cache key, populated on miss, awaited by subsequent callers within the window. ~30 lines.
- If present in some form: pattern reference for the new tool to adopt.

Singleflight is a Task 2 schema decision (it affects whether the service layer signature is `async def get_options_chain(...)` vs. a coalesced variant) and a Task 3 implementation decision. Task 1 just collects the evidence.

#### 1C — Options-math extraction reconnaissance (ATLAS-mandated)

Read `backend/integrations/uw_api.py` `_get_contract_mid()` (lines ~858-880) and the surrounding helpers. Confirm that the `mid` computation (bid/ask mid with fallbacks to last_price, day close, vwap) is the canonical implementation in the codebase. Identify all callers — should be the get_spread_value / get_single_option_value / get_multi_leg_value / get_ticker_greeks_summary chain (per the audit).

The brief's Task 2 schema needs a `mid` and `bid_ask_spread_pct` on every contract. The naive implementation duplicates the computation in the new service layer. ATLAS pushed back on the duplication risk (drift between the position-pricing path and the chain-display path is exactly the kind of subtle bug that causes "the quote and the live chain disagree by 2¢"). Instead:

- Extract `_get_contract_mid()` and a new `compute_bid_ask_spread_pct(contract_dict)` helper to a new module `backend/utils/options_math.py`.
- Update `uw_api.py` to import + delegate to the new module (preserves all existing callers; one import-line change per call site).
- The new service layer (`backend/services/read_only/options_chain.py`) imports the same module.
- Single source of truth eliminates drift.

Output:
- Confirm `_get_contract_mid()` is the canonical implementation and no rival mid-computation exists elsewhere.
- Confirm all callers can be updated with a single import-line change.
- Propose the `backend/utils/options_math.py` module signature: `compute_mid(contract: dict) -> Optional[float]` and `compute_bid_ask_spread_pct(contract: dict) -> Optional[float]`. The contract dict format is the existing `get_options_snapshot` normalized shape (with `last_quote.bid`, `last_quote.ask`, `last_trade.price`, `day.close`, `day.vwap` fields).
- Flag any caller whose semantics differ from `_get_contract_mid()` and would break under a shared extraction (expected: none, but verify).

#### Task 1 deliverable

A single findings note at `docs/codex-briefs/hub-get-options-chain-task1-spec-2026-05-24.md` covering all three threads (1A, 1B, 1C):
- Each endpoint's actual field names + types (1A)
- Singleflight finding + recommendation (1B)
- options_math extraction plan (1C)
- Confirmation that DAEDALUS's required fields are all available in the UW response
- Any fields the spec exposes that DAEDALUS would benefit from but the brief didn't account for

**If any required field is missing or named differently from what the brief assumes, surface BEFORE proceeding to Task 2.** Don't silently substitute. Same for the singleflight and math-extraction decisions — they feed Task 2 and any deviation from this brief's strawman should be flagged.

### Task 2 — Response schema design

Based on Task 1 findings, finalize the response envelope shape. Strawman (subject to Task 1 corrections):

```json
{
  "status": "ok" | "stale" | "unavailable",
  "summary": "AAPL 2026-06-21 chain: 142 contracts (71C/71P), IVR 42.1, max pain $190, total OI 387k",
  "staleness_seconds": null | <int>,
  "data": {
    "ticker": "AAPL",
    "expiry": "2026-06-21",
    "spot": 185.42,
    "uw_timestamp": "2026-05-24T20:15:33Z",
    "iv_rank": 42.1,
    "max_pain": 190.0,
    "total_open_interest": 387412,
    "total_call_oi": 198330,
    "total_put_oi": 189082,
    "contracts": [
      {
        "strike": 185.0,
        "option_type": "call",
        "bid": 4.20,
        "ask": 4.35,
        "mid": 4.275,
        "bid_ask_spread_pct": 3.5,
        "volume": 1240,
        "open_interest": 8420,
        "delta": 0.52,
        "gamma": 0.045,
        "theta": -0.08,
        "vega": 0.18,
        "implied_volatility": 0.28
      },
      ...
    ]
  }
}
```

Rules baked into the schema:
- `contracts` is the per-strike list; sorted ascending by strike, then by option_type (calls first within each strike).
- `bid_ask_spread_pct` is COMPUTED at the service layer (= `(ask - bid) / mid * 100`); not a raw UW field. Enables DAEDALUS's 10%-liquidity-flag hard rule without re-computing.
- `mid` is COMPUTED at the service layer (= `(bid + ask) / 2`, or fallback to `last_price` if bid/ask are zero/missing — same pattern as `uw_api._get_contract_mid()`).
- Chain-level aggregates (`iv_rank`, `max_pain`, `total_*_oi`) returned at the top of `data`, not inside each contract row. DAEDALUS reads them once for the chain, then iterates contracts for strike-level math.
- `uw_timestamp` propagated from the source endpoint(s) — used by DAEDALUS to anchor its DATA NOTE.

**PAUSE HERE for ATLAS-style review of the brief before Task 3 (code).** Per Nick's instruction. The review confirms the schema choice is sensible, the pattern parity vs. `hub_get_quote` / `hub_get_flow_radar` is intact, and there's no blind spot in the design. No code work until ATLAS sign-off.

### Task 3 — Service layer

Create `backend/services/read_only/options_chain.py`. Pattern matches `backend/services/read_only/quote.py` and `backend/services/read_only/flow.py`.

```python
async def get_options_chain(
    ticker: str,
    expiry: str,                     # REQUIRED per design decision #1
    option_type: str = "both",       # "both" | "call" | "put"
) -> Optional[Dict[str, Any]]:
    """Fetch chain for one expiry, compose with aggregates, return envelope shape."""
```

Composition logic:
1. Call `integrations.uw_api.get_options_snapshot(ticker, expiration_date=expiry, contract_type=...)` — already exists, returns the contract list normalized to Polygon shape.
2. Call `integrations.uw_api.get_iv_rank(ticker)` — already exists.
3. Call `integrations.uw_api.get_max_pain(ticker)` — already exists.
4. Filter contracts to the requested expiry (the wrapper already does this, but defensive re-filter is cheap).
5. Compute `mid` and `bid_ask_spread_pct` per contract via the shared `backend/utils/options_math.py` module (extracted in Task 1C). **No new computation site introduced in the service layer.**
6. Compute `total_open_interest`, `total_call_oi`, `total_put_oi` by summing across `contracts`.
7. Build the envelope (see Task 2 schema), populate `uw_timestamp` from whichever upstream call carries it.
8. Wrap with the 25s cache (new category `option_chain_live` in `uw_api_cache.py`) — see Task 4.
9. Apply singleflight coalescing per the Task 1B recommendation (if absent in existing tools and adopted for this one).

The `get_options_snapshot` call already pushes native `expiry` + `option_type` filters down to UW (the 2026-04-28 P2.0 fix), keeping the response inside the 500-result cap.

#### Partial-failure semantics (ATLAS-mandated)

The 3-call composition has asymmetric criticality. The brief locks in **best-effort with status markers** for the aggregates, **hard fail for the chain**:

| Upstream call | Criticality | Failure behavior |
|---|---|---|
| `get_options_snapshot` (the chain) | **REQUIRED.** Without it the response is empty. | If returns None → entire envelope returns `status="unavailable"` with `error` field naming the missing call. No partial data shipped. |
| `get_iv_rank` (chain-level aggregate) | OPTIONAL. DAEDALUS can frame qualitatively if absent. | If returns None → `data.iv_rank = null`, add to `data.aggregates_errors` array: `{"field": "iv_rank", "reason": "upstream unavailable"}`. Envelope `status="ok"` (chain itself succeeded). |
| `get_max_pain` (chain-level aggregate) | OPTIONAL. Same as iv_rank. | If returns None → `data.max_pain = null`, add to `data.aggregates_errors` array: `{"field": "max_pain", "reason": "upstream unavailable"}`. Envelope `status="ok"`. |

Rationale: the chain is the consumer's primary need. The aggregates enrich the chain. If iv_rank or max_pain blip transiently (UW timeout, rate limit), DAEDALUS still gets the per-contract Greeks and can degrade to qualitative-IV-mode for the missing aggregate rather than getting nothing. If the chain itself is unavailable, there's no value in shipping aggregates alone — surface the failure cleanly.

The `aggregates_errors` field is OMITTED from the envelope when empty (no error rows). When present, it's an array of `{field, reason}` objects so DAEDALUS can name in its DATA NOTE which aggregates were unavailable.

`_summary()` text adapts to partial failures: e.g., *"AAPL 2026-06-21 chain: 142 contracts, IVR 42.1, max pain unavailable, total OI 387k"* if max_pain failed.

### Task 4 — Cache layer entry

In `backend/integrations/uw_api_cache.py`, add to the `CACHE_TTLS` dict:

```python
"option_chain_live": 25,  # 25s — DAEDALUS strike-selection path; separate
                          # namespace from "option_contracts" (300s) which
                          # serves position-pricing. Per Brief design #3.
```

**Cache key format (literal, ATLAS-mandated):**

```
option_chain_live:{TICKER}:{expiry}:{option_type}
```

- `{TICKER}` is uppercase symbol (e.g., `SPY`, `AAPL`).
- `{expiry}` is ISO date `YYYY-MM-DD` (e.g., `2026-06-20`).
- `{option_type}` is lowercase: `both`, `call`, or `put`.
- Separator throughout is `:` (NOT `|`), conforming to the format ATLAS specified.

In the service layer:
```python
key = f"{ticker.upper()}:{expiry}:{option_type.lower()}"
cached = await cache_get("option_chain_live", key)
# resulting full Redis key per uw_api_cache.py:53 pattern:
#   uw:option_chain_live:SPY:2026-06-20:both
```

Note: the `cache_get` / `cache_set` helpers in `uw_api_cache.py` prepend `uw:{category}:` to the passed `key` argument, so the literal Redis-side key is `uw:option_chain_live:{TICKER}:{expiry}:{option_type}` — matching ATLAS's specified shape with the existing `uw:` wrapper prefix preserved.

### Task 5 — MCP tool layer

Create `backend/hub_mcp/tools/options_chain.py`. Pattern matches `backend/hub_mcp/tools/quote.py`.

```python
@mcp_tool(name="hub_get_options_chain", description=DESCRIPTION)
async def hub_get_options_chain(
    ticker: str,
    expiry: str,
    option_type: str = "both",
) -> dict:
```

Validate inputs (ticker non-empty; expiry parseable as YYYY-MM-DD; option_type ∈ {"both", "call", "put"}). Delegate to the service layer. Wrap with `make_response` envelope. Build `_summary()` per the format in Task 2's strawman.

DESCRIPTION should be explicit that this is **DAEDALUS's primary tool for strike selection, Greeks, IV rank, and liquidity checks**, that `expiry` is REQUIRED, and that the response includes chain-level aggregates alongside the per-contract list. Reference the Olympus exemption: this is a trade-setup-supporting tool, gated by `§ Hub MCP Preflight` like the others.

### Task 6 — Update DAEDALUS SKILL.md to call the new tool

In `skills/daedalus/SKILL.md`, the "DAEDALUS's specific tool calls (Context A)" list at lines 61-69. Insert `hub_get_options_chain` between the existing calls 2 (`hub_get_flow_radar`) and 3 (`hub_get_hydra_scores`):

```
3. `hub_get_options_chain(ticker=<the ticker>, expiry=<chosen DTE expiry>)` — chain + Greeks + IV rank + max pain for the expiry DAEDALUS is reasoning about. Required for live-Greeks structure output; replaces the qualitative-IV-mode fallback documented in the agent's data caveat.
```

Renumber subsequent entries. Remove or update the "DAEDALUS-specific data caveat" paragraph (lines 71-77) — the gap it documents is now closed. Replace with a shorter note that pre-`hub_get_options_chain` qualitative-IV-mode is still the fallback when the tool returns `status="unavailable"`.

Rebuild `daedalus.skill` bundle via `scripts\package-skill.ps1 daedalus`. Nick re-uploads to claude.ai manually post-merge.

### Task 7 — Smoke tests

After deploy (and ATLAS review-pass on Task 2):

1. **Tool response shape** — direct curl or Python script hitting the deployed MCP endpoint via auth (or alternatively, invoke from a fresh claude.ai chat with DAEDALUS): `hub_get_options_chain(ticker="SPY", expiry="2026-06-20")`. Confirm response is a single envelope, `status="ok"`, `data.contracts` is a non-empty list, `data.iv_rank` is a float, `data.max_pain` is a float, `data.total_open_interest` is an int. Spot-check a contract: has `strike`, `delta`, `gamma`, `theta`, `vega`, `implied_volatility`, `bid_ask_spread_pct`.
2. **DAEDALUS smoke** — fresh claude.ai chat with the new bundle loaded + Pandora MCP connected. Ask: *"DAEDALUS, walk me through the right structure for a 2-week tactical bullish SPY trade. Use the 6/20 expiry."* Expected: DAEDALUS calls `hub_get_options_chain(ticker="SPY", expiry="2026-06-20")` as part of its checklist, cites specific delta / IV rank / max pain values from the response in its output (no more qualitative-IV-mode caveat).
3. **Cache behavior** — call the same `hub_get_options_chain` twice within 25s. Confirm second response is < 100ms (cache hit). Wait > 30s; call again. Confirm > 1s (cache miss, fresh fetch).
4. **Filter behavior** — call with `option_type="call"`; confirm `contracts` contains only calls. Same for `"put"`. With `"both"` (default), confirm both present.
5. **Required-expiry guard** — call with no `expiry` parameter. Expected: `status="unavailable"`, `error` field naming the missing parameter.
6. **Olympus impact verification** — run a small DAEDALUS-included committee pass. Confirm DAEDALUS uses the new tool, the rest of the committee unchanged. No regression on TORO/URSA/PYTHIA/PYTHAGORAS/THALES/PIVOT behavior.

### Task 8 — Closure note

Author `docs/strategy-reviews/hub-get-options-chain-closure-note-YYYY-MM-DD.md`. Cover:
- Task 1 findings on UW field shape (any surprises vs. brief assumptions)
- Schema final form (post-ATLAS-review adjustments if any)
- All 6 smoke results
- DAEDALUS qualitative-IV-mode caveat status: closed
- Tier 2 follow-ups: `option_type="both"` quota review after 7 days of soak; consider extending to a `expiries=[...]` multi-expiry variant if a real consumer asks (skip until consumer exists).

## Output spec

- Modified: `backend/integrations/uw_api_cache.py` (one new TTL entry: `option_chain_live: 25`)
- Modified: `backend/integrations/uw_api.py` (`_get_contract_mid` extracted; one import-line change per call site — per Task 1C reconnaissance)
- New: `backend/utils/options_math.py` (shared `compute_mid`, `compute_bid_ask_spread_pct` helpers — per Task 1C extraction)
- New: `backend/services/read_only/options_chain.py` (service layer; optionally includes singleflight per Task 1B finding)
- New: `backend/hub_mcp/tools/options_chain.py` (MCP tool layer)
- Modified: `skills/daedalus/SKILL.md` (tool-list insertion + caveat update)
- New: `dist/skills/daedalus.skill` rebuild (bundle artifact, dist/ is gitignored)
- New: `docs/codex-briefs/hub-get-options-chain-task1-spec-2026-05-24.md` (Task 1 findings — three threads 1A/1B/1C — committed BEFORE Task 2)
- New: `docs/strategy-reviews/hub-get-options-chain-closure-note-YYYY-MM-DD.md`

Commit messages:
- Task 1: `docs(brief): hub_get_options_chain Task 1 — UW spec validation`
- Tasks 3-5 implementation: `feat(hub_mcp): hub_get_options_chain tool — Greeks + IV rank + max pain for DAEDALUS`
- Task 6: `feat(skills): DAEDALUS calls hub_get_options_chain; close qualitative-IV-mode caveat`
- Task 8 closure: `docs(strategy-reviews): hub_get_options_chain closure note`

## Gates / what NOT to do

- Do NOT skip Task 1 (OpenAPI validation). Spec-vs-assumption mismatches are real (the audit found `option_symbol` shape that needed parsing — `_parse_option_symbol` in `uw_api.py` exists for that reason).
- Do NOT proceed to Task 3 code until the ATLAS-style review of Task 2's schema design is signed off by Nick.
- Do NOT bypass the 500-result cap by removing the `expiry` requirement. Per design decision #1, the parameter is required.
- Do NOT change the existing `option_contracts` cache (300s TTL) — it serves the position-pricing path and must stay separate.
- Do NOT add direct UW endpoint calls in the service layer. Compose via existing wrappers (`get_options_snapshot`, `get_iv_rank`, `get_max_pain`) which already respect token bucket + circuit breaker.
- Do NOT touch `unified_positions`, `signal_outcomes`, `signals`, or any canonical strategy data table.
- Do NOT introduce new credentials.
- Do NOT print, log, or commit any tokens.
- Do NOT bundle other v2 hub tools (`hub_get_chart_indicators`, `hub_get_market_profile`) into this brief — they're separate scope per the audit.

## Olympus Impact

**Direct impact on DAEDALUS:** transitions from qualitative-IV-mode to live-Greeks-and-IV mode. The data caveat at `skills/daedalus/SKILL.md` lines 71-77 is closed. Every DAEDALUS output going forward will cite specific delta / theta / vega / IV rank values when chain data is available, instead of inferring IV regime from price action + VIX context.

**No direct impact on other 6 agents** (TORO, URSA, PYTHIA, PYTHAGORAS, THALES, PIVOT) — their tool lists in their respective SKILL.md files are unchanged.

**Indirect impact:** PIVOT synthesizes DAEDALUS's reads alongside the rest of the committee. With DAEDALUS now operating with live Greeks, PIVOT's structure-and-sizing verdicts get sharper input. No PIVOT code change required.

**Required post-build re-test (Task 7.6):** small DAEDALUS-included committee pass on SPY or a Robinhood-eligible name to confirm no regression in any of the other agents' behavior. The Hub MCP Preflight gate that just shipped covers the connector-required case; this build is purely additive on top of that.

## Done definition

- Task 1 spec-validation note committed BEFORE any code.
- ATLAS-style review on Task 2 schema design signed off by Nick BEFORE Task 3 code.
- Tasks 3-5 implementation committed and deployed.
- Tasks 6 (DAEDALUS SKILL.md update + bundle rebuild) committed; bundle ready for Nick's manual upload.
- All 6 smoke checks passing.
- Closure note authored.
- Stop and notify Nick after closure note.

## Notes for the implementer

- The service-layer composition (3 UW wrappers per call) means a cold cache fetch = 3 UW calls. With 25s TTL, that's ~7 cache misses per minute worst-case during DAEDALUS-heavy committee passes. Well within the 120/min UW budget given the rest of the system. If a hot path emerges that thrashes the cache (e.g., a frontend that polls DAEDALUS), revisit the TTL — but don't pre-optimize.
- The `uw_timestamp` field needs care. UW returns it on `/option-contracts` directly; for the aggregates, the timestamp is implicit ("when did we fetch"). Use the `/option-contracts` timestamp as authoritative; if absent, fall back to `datetime.now(timezone.utc).isoformat()` at the service layer with a flag indicating it's synthetic.
- This is a small build. ~150 lines of new code across the service + tool layers, plus the SKILL.md edits. If the diff balloons past 300 lines, scope check — something has crept in.
- Standard direct-merge-then-smoke-then-revert-if-fails discipline. Same as Phase B yesterday.
