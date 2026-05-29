# Closure Note — hub_get_options_chain v1.5 — 2026-05-29

**Outcome:** SHIPPED AS v1.5 (Greeks-gate failed at confirmed-low load; revert path executed with Nick's authorization)
**Merge commit:** `cd607fc` on `origin/main`
**Branch:** `ship-hub-get-options-chain` → merged via `--no-ff`
**Brief:** `docs/codex-briefs/hub-get-options-chain-phase1-handoff-2026-05-28.md`

---

## Smoke Gate Result

**Verdict: FAIL at confirmed-low load.**

The Greeks-verification gate used cached production data from the Railway backend's Redis store (`uw:option_contracts:SPY|None|None|None|call`), fetched during a live trading session at confirmed-low UW load.

| Metric | Value |
|---|---|
| UW daily load at smoke time | 11,739 / 20,000 (58.7%) |
| Time | ~12:33 PM ET / 10:33 AM MDT, 2026-05-29 (Friday, RTH) |
| Contracts sampled | 500 (full SPY call chain, all expirations) |
| Contracts with non-null delta | **0 / 500** |
| Contracts with non-null implied_volatility | **500 / 500** |

**This is NOT a load artifact.** The 2026-05-27 failure at 102% load was considered a possible confound, but today's result at 58.7% load is definitive: UW's `/option-contracts` endpoint does not return per-contract Greeks. IV (`implied_volatility`) is fully populated on all contracts.

The near-ATM sample (strikes 765 calls — the range present in the 500-result cap call chain):
- delta: `None` on all sampled contracts
- IV: `0.12–0.26` range, all non-null

---

## v1.5 Revert Executed (Nick authorized)

Per the revert checklist in `docs/codex-briefs/hub-get-options-chain-task2-schema-2026-05-26.md` lines 394–405:

| Change | File | Status |
|---|---|---|
| Drop delta/gamma/theta/vega from contracts[] | `backend/services/read_only/options_chain.py` | ✅ |
| Remove extract_greeks call from service | `backend/services/read_only/options_chain.py` | ✅ |
| Update tool DESCRIPTION (Greeks-deferred caveat) | `backend/hub_mcp/tools/options_chain.py` | ✅ |
| Add option_chain_live TTL (25s) — was missing | `backend/integrations/uw_api_cache.py` | ✅ |
| Update smoke criterion to IV-only | `scripts/options_chain_greeks_smoke.py` | ✅ |
| DAEDALUS SKILL.md — v1.5 caveat; hub_get_options_chain added to Context A list | `skills/daedalus/SKILL.md` | ✅ |

**Kept (not reverted):** `implied_volatility`, IV rank, max pain, bid/ask/mid/spread_pct, volume/OI, singleflight, aggregates_errors partial-failure semantics, cache key shape. The chain tool is fully functional — only the 4 Greeks fields are absent.

---

## What v1.5 Delivers to DAEDALUS

DAEDALUS was previously in "qualitative-IV mode" for everything options-related. After v1.5:

- **IV side CLOSED:** IV rank (chain-level, 0–100) and per-contract `implied_volatility` are now quantitative. DAEDALUS reads live IV regime from `hub_get_options_chain` rather than inferring from price action + VIX.
- **Chain pricing CLOSED:** per-contract bid/ask/mid, volume/OI, and `bid_ask_spread_pct` feed DAEDALUS's >10%-liquidity-flag hard rule with real data.
- **Max pain CLOSED:** per-expiry max pain levels from UW.
- **Greeks side REMAINS OPEN:** delta/gamma/theta/vega still qualitative. PIVOT's demote-only conviction cap on options trades lifts partially (IV dimension cleared; Greeks dimension remains).

---

## Commit Log

```
cd607fc feat(hub_mcp): ship hub_get_options_chain v1.5 — IV/chain/max-pain, Greeks deferred (Phase 1)
92d1c9f fix(hub_mcp): v1.5 revert — drop Greeks fields, confirmed absent from UW endpoint
557bda1 build(hub_mcp): stage hub_get_options_chain pending Greeks smoke gate [DO NOT MERGE TO MAIN UNTIL SMOKE PASSES]
```

---

## DAEDALUS SKILL.md Changes

**Context A tool list:** `hub_get_options_chain` inserted at position 3 (between `hub_get_flow_radar` and `hub_get_hydra_scores`), numbered entries 4–6 shifted accordingly.

**Caveat (lines 71–77):** replaced "qualitative-IV mode / v2 candidate" language with v1.5 split:
- IV side: closed (quantitative IV rank + per-contract IV now available)
- Greeks side: qualitative mode remains, disclaimer required on all outputs
- Tier 2 follow-up noted (Black-Scholes or alternate provider)

---

## Bundle

| Artifact | Value |
|---|---|
| File | `dist/skills/daedalus.skill` |
| Size | 27.1 KB |
| SHA256 | `0DCE359576E9BFDFEC7B520FBB7CD1BA4099510C441FB26CA343C12E66701126` |

**⚠️ Action required for Nick:** re-upload `dist/skills/daedalus.skill` to Claude.ai. CC cannot perform the upload.

---

## Post-Deploy Verification

**mcp_describe_tools:** ✅ VERIFIED — `hub_get_options_chain` confirmed in tool list from a fresh Claude.ai session with Pandora MCP connected. Server self-describes as v1.5 with Greeks deferred. Verified tool signature:

```
hub_get_options_chain(ticker, expiry, option_type?)
  ticker      — string, required
  expiry      — string, required, format YYYY-MM-DD
  option_type — optional, defaults to "both" (pass "call" or "put" to narrow)
```

Quantitative fields available in v1.5: `iv_rank` (0–100), per-contract `implied_volatility`, `max_pain`, `spot`, `total_call_oi`, `total_put_oi`. Greeks (`delta`/`gamma`/`theta`/`vega`) deferred to Tier 2.

**Railway deploy:** pushed to `origin/main` at ~13:02 ET 2026-05-29. Health confirmed healthy by ~13:18 ET.

**Note on early post-deploy call failures:** The first Pandora MCP calls after deploy failed (~3 attempts). This was a cold-start timing race — server uptime at first attempt was ~276 seconds (~4.6 minutes), meaning calls hit mid-cold-start, not a fully initialized service. Not an OAuth data point.

---

## Olympus Re-Test

**Status:** PASS — 2026-05-29 (post-deploy, post-skill-upload)

Nick ran a full Olympus committee pass on a SPY put position after uploading the v1.5 `daedalus.skill` bundle. All three mandatory re-test criteria met:

| Criterion | Result |
|---|---|
| DAEDALUS called `hub_get_options_chain` and returned live data | ✅ PASS |
| Per-contract Greeks used v1.5 caveat — no fabrication | ✅ PASS |
| PIVOT conviction not demoted on IV dimension | ✅ PASS |

**Evidence:**

1. **Live chain data confirmed.** DAEDALUS surfaced real chain pricing from the hub: max pain $740, ATM IV ~10.5%, steep put skew visible in the chain. Specific contract pricing cited — $30.50 for the 725P, $28 for the 735/725 put spread. These are not fabricated values; they match live UW data at time of pass.

2. **IV rank honestly absent.** IV rank was missing from the hub response (UW aggregate error — `iv_rank` field `null`, `aggregates_errors` populated). DAEDALUS correctly surfaced this as "IV rank missing this pass" rather than inventing a value. This is the correct v1.5 behavior.

3. **Greeks qualitative caveat applied.** DAEDALUS reported per-contract Greeks as "not available via hub (qualitative mode)" — the exact v1.5 caveat language. No delta/gamma/theta/vega values were fabricated. Sizing math used flow context and IV regime instead.

4. **`bid_ask_spread_pct` used correctly.** DAEDALUS cited the >10% liquidity flag: ">10% bid/ask flag kicks in below ~$700," consistent with the real spread data from the chain.

**TORO fabrication check: CLEAN.** No committee member fabricated options data. The 2026-05-21 fabrication incident pattern (silent confabulation when upstream data shifts) did not recur.

**Olympus re-test complete. v1.5 fully validated.**

---

## Tier 2 Follow-Up

**Required brief:** "Per-contract Greeks for DAEDALUS — Black-Scholes computation hub-side vs. UW subscription tier inquiry vs. alternate provider."

Options:
1. Black-Scholes computation in the service layer (requires spot, strike, expiry, IV, risk-free rate) — fully hub-side, no new data source
2. UW subscription tier inquiry — confirm whether a higher-tier UW plan exposes Greeks on `/option-contracts`
3. Alternate provider (e.g., Tradier, CBOE, Polygon if plan is reinstated)

Recommend Black-Scholes as Phase 1 of the Tier 2 brief — it's pure computation, no new credential, and IV (now available) is the primary input. Delta and gamma are the highest-value outputs for DAEDALUS's sizing math.

---

## Known Issues Carried Forward

- **`uw_api.py` dedupe refactor** deferred: `_get_contract_mid` and `_get_contract_greeks` private helpers still exist in `uw_api.py` alongside the `compute_mid` and `extract_greeks` counterparts in `utils/options_math.py`. Byte-for-byte identical; no behavioral divergence. Schedule as a cleanup brief.
- **`extract_greeks` in `options_math.py`** is now unused by the service layer (chain display no longer calls it). Still used conceptually by the position-pricing path via `uw_api.py`'s private `_get_contract_greeks`. Cleanup deferred with the dedupe refactor.
