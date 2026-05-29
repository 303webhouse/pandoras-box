# Closure Note — Tier 2: Black-Scholes Greeks (DAEDALUS Full-Power) — 2026-05-29

**Outcome:** SHIPPED
**Merge commit:** `d4501fa` on `origin/main`
**Branch:** `tier2-bs-greeks` → merged via `--no-ff`
**Brief:** `docs/codex-briefs/` (Tier 2 brief provided 2026-05-29)

---

## What Shipped

Per-contract Black-Scholes Greeks (delta, gamma, theta, vega) added to `hub_get_options_chain` response. Computed hub-side from UW-provided `implied_volatility`. No new credentials, no new UW calls beyond the v1.5 baseline. DAEDALUS exits half-power entirely.

**Files changed:**

| File | Change |
|---|---|
| `backend/utils/options_math.py` | Added `bs_greeks_from_iv()` — pure stdlib Black-Scholes (math.erf normal CDF) |
| `backend/integrations/risk_free_rate.py` | New — `RISK_FREE_RATE_3M = 0.0368` (3M T-bill, 2026-05-29) |
| `backend/services/read_only/options_chain.py` | Greeks wired into per-contract envelope; `greeks_source: "bs_computed"` + `spot_source` added to chain-level metadata; `get_snapshot()` fallback for spot when chain omits `underlying_asset.price` |
| `backend/hub_mcp/tools/options_chain.py` | Description updated — "Greeks deferred (v1.5)" language removed; BS-source disclosure added |
| `scripts/bs_greeks_validation_smoke.py` | New — sanity band smoke with yfinance cross-check |
| `skills/daedalus/SKILL.md` | v1.5 qualitative-Greeks-mode caveat replaced with BS-source disclosure |

---

## Risk-Free Rate

| Field | Value |
|---|---|
| Value | `0.0368` (3.68%) |
| Instrument | 3-month T-bill (13-week) |
| Source | US Treasury daily rates — https://home.treasury.gov/resource-center/data-chart-center/interest-rates/ |
| Date set | 2026-05-29 |
| Next review | 2026-08-29 (quarterly) |

---

## Smoke Gate Result

**Verdict: PASS — 2026-05-29, live RTH**

| Metric | Value |
|---|---|
| Ticker | SPY |
| Expiry | 2026-06-05 (next Friday) |
| Contracts returned | 500 |
| Spot | 756.13 (via `snapshot_fallback` — UW chain omitted `underlying_asset.price`) |
| greeks_source | `bs_computed` |
| iv_rank | None (UW aggregate error — `field missing in response`) |
| max_pain | 740.0 |

**Note on spot_source=snapshot_fallback:** UW's `/option-contracts` endpoint did not populate `underlying_asset.price` on this run (same pattern as v1.5 smoke). The service layer fell back to `get_snapshot()` (already cached via `quote` TTL), retrieved spot 756.13, and computed Greeks from that. This is correct behavior; the fallback was added specifically for this case. `spot_source` field in the envelope distinguishes the two paths.

**5 nearest-ATM strikes — sanity bands (all PASS):**

| Strike | Type | IV | Delta | Gamma | Theta | Vega |
|---|---|---|---|---|---|---|
| 756 | call | 0.1188 | **0.5246** | 0.0320 | -0.3932 | 0.4170 |
| 757 | call | 0.1168 | **0.4923** | 0.0326 | -0.3855 | 0.4177 |
| 755 | call | 0.1213 | **0.5555** | 0.0311 | -0.4002 | 0.4137 |
| 758 | call | 0.1148 | **0.4590** | 0.0330 | -0.3752 | 0.4155 |
| 754 | call | 0.1236 | **0.5850** | 0.0301 | -0.4043 | 0.4082 |
| 756 | put  | 0.1058 | **-0.4732** | 0.0359 | -0.2784 | 0.4168 |
| 757 | put  | 0.1036 | **-0.5095** | 0.0368 | -0.2696 | 0.4176 |
| 755 | put  | 0.1070 | **-0.4381** | 0.0352 | -0.2818 | 0.4127 |
| 758 | put  | 0.1017 | **-0.5471** | 0.0372 | -0.2590 | 0.4148 |
| 754 | put  | 0.1084 | **-0.4043** | 0.0341 | -0.2831 | 0.4057 |

**Sanity band results:**
- ATM call delta [0.40, 0.60]: ✅ all 5 pass
- ATM put delta [-0.60, -0.40]: ✅ all 5 pass
- Gamma > 0: ✅ all 10 pass
- Vega > 0: ✅ all 10 pass
- Theta < 0: ✅ all 10 pass
- All four Greeks non-null: ✅ all 10 pass

**yfinance cross-check:** ✅ all compared strikes within ±10% tolerance.

**Put-call delta parity (unit test):** `call_delta - put_delta = 1.0000` ✅

---

## Merge Commit Log

```
d4501fa feat(hub_mcp): Black-Scholes Greeks computation — Tier 2 closes DAEDALUS half-power  [merge]
567e954 fix(smoke): tighten sanity bands to 5 nearest strikes per side
b19a4ad fix(options_chain): fall back to get_snapshot() for spot when chain omits underlying_asset.price
18abc5e feat(hub_mcp): Tier 2 Black-Scholes Greeks — DAEDALUS full-power
```

---

## DAEDALUS SKILL.md Changes

**Replaced** (lines ~72–82, v1.5 qualitative-Greeks-mode caveat):
- "Greeks side remains open (qualitative-mode)..." → retired
- Required disclaimer "Per-contract Greeks not available via hub..." → retired

**Replaced with** Tier 2 disclosure:
- Greeks are now available, computed via Black-Scholes (`greeks_source: "bs_computed"`)
- BS assumes European exercise and zero dividends — disclosed explicitly
- Null-IV contracts → null Greeks; DAEDALUS must render as "unavailable" (hard rule)
- DAEDALUS is now fully quantitative — PIVOT conviction cap fully lifted

**Tool list entry (line 65):** updated to include "Black-Scholes Greeks (delta, gamma, theta, vega)" and remove "(v1.5 — Greeks not yet available; see caveat below.)"

**Hard rule (line ~181):** updated from "never fabricate specific Greeks numbers" to explicit null-IV → null-Greeks hard rule.

---

## Bundle

| Artifact | Value |
|---|---|
| File | `dist/skills/daedalus.skill` |
| Size | 27,798 bytes |
| SHA256 | `52936649BD8EC3086177E6526BFF30C86D2CC193132B97E56E42C420D81A2229` |

**⚠️ Action required for Nick:** re-upload `dist/skills/daedalus.skill` to Claude.ai. (Bundle was uploaded before smoke per Nick's confirmation during the session.)

---

## Post-Deploy Verification

**Railway deploy:** pushed to `origin/main` at ~14:20 MT 2026-05-29. Verify health endpoint after deploy settles.

**mcp_describe_tools verification:** PENDING — confirm from a fresh Claude.ai session that `hub_get_options_chain` description no longer carries "Greeks deferred (v1.5)" language and mentions Black-Scholes / modeled Greeks.

---

## Olympus Re-Test

**Status:** PENDING — requires Olympus committee pass after Nick confirms bundle upload landed.

Confirm:
1. DAEDALUS surfaces real numeric Greeks (delta/gamma/theta/vega) — values consistent with smoke output above.
2. DAEDALUS includes BS-source disclosure in prose (modeled, not market-observed; dividend/American-exercise caveat).
3. DAEDALUS renders null-IV contracts as "unavailable" — NOT fabricated numbers.
4. PIVOT's demote-only conviction cap on options trades is fully lifted.

Record re-test outcome as addendum to this note.

---

## DAEDALUS Impact

**Before Tier 2:** IV quantitative (v1.5), Greeks qualitative. PIVOT conviction cap partially lifted (IV dimension only).

**After Tier 2:** Both IV and Greeks quantitative. Greeks-aware structure selection, theta-budget math, vega-exposure reads, and gamma-convexity sizing all become real numerical reads. PIVOT conviction cap fully lifted — no remaining DAEDALUS dimension degraded.

---

## Known Issues Carried Forward

- **iv_rank consistently None:** UW's `/iv-rank` endpoint returned `field missing in response` on both the v1.5 smoke (2026-05-29 RTH) and this Tier 2 smoke. The chain tool degrades gracefully (`aggregates_errors` populated, iv_rank=null), but the root cause has not been investigated. Schedule as a separate brief.
- **`spot_source: "snapshot_fallback"` on every run:** UW `/option-contracts` has not returned `underlying_asset.price` on any observed run (two smokes). The fallback is working correctly, but this means one extra `get_snapshot()` call per chain fetch on every cold-cache miss. Monitor for UW-budget impact.
- **Tier 3 (deferred):** Dividend-yield input and American-exercise adjustment for BS. Relevant for HYG, XLY, high-yield sector ETFs. Not scheduled.
