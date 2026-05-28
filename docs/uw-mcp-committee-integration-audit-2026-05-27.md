# UW MCP / Committee Integration Audit — 2026-05-27

**Status:** Audit-only. No code changes. No new MCP tools written. No resurrection of parked Task 3 code. No SKILL.md edits. All findings are empirical (file:line citations + git log + live tool inventory) or quoted from named documentation.

> **CORRECTION (2026-05-28):** This audit's Part B claim that the Greeks
> verification smoke "has never been run" is **WRONG**. The A.4a handoff doc
> (`docs/codex-briefs/a4a-uw-overdraw-handoff-2026-05-27.md` §3) — which I
> failed to read during this audit — documents that the smoke **WAS run on
> 2026-05-27 ~15:14 ET and FAILED: 0/497 SPY contracts had Greeks** (delta/
> gamma/theta/vega/IV all null, spot null; max_pain worked). **However**, UW
> was at **102% of daily budget (20,366/20,000)** at smoke time and degrades
> multiple endpoints together under load, so the failure is **confounded, not
> conclusive**. The documented disposition was to **re-smoke Thursday
> 2026-05-28 AM at low load** after the daily counter resets overnight. The
> "unblock as-is, ~1h" framing below still holds IF the clean re-smoke passes;
> if it fails at confirmed-low load, the v1.5 revert path applies. See the
> ship brief and the closure note for the authoritative smoke result.

**Predecessor:** [docs/rh-mcp-integration-audit-2026-05-27.md](rh-mcp-integration-audit-2026-05-27.md) (commit `2939476`). The RH audit confirmed RH MCP is equities-only, no Greeks, no options chain — so UW remains the only viable data source for the three half-powered committee agents. This audit answers the questions needed to draft the build brief that closes the gap.

**Authoritative artifacts:**
- Claude.ai connector inventory (Part A.1) — captured empirically from a fresh Claude.ai chat session on 2026-05-27. Tool-list probe + named connector list reproduced verbatim in §2.1.
- `claude_desktop_config.json` (Part A.1) — read from `C:\Users\nickh\AppData\Roaming\Claude\` on 2026-05-27.
- Backend code (Part B): file:line citations inline.
- Skill files (Part C): `skills/<agent>/SKILL.md` file:line citations inline.
- UW OpenAPI spec (Part C reference): `docs/audit-artifacts/2026-05-22/uw-openapi.yaml` — the canonical 177-endpoint inventory from the [UW integration audit (2026-05-22)](uw-integration-audit-2026-05-22.md).

---

## 1. Executive Summary

- **Headline reframing on Part B:** Task 3 (`hub_get_options_chain`) is **NOT "parked with Greeks gate failed."** It is **STAGED but uncommitted** — fully built across 4 working-tree files, already wired into the tool registry, awaiting only the live-market Greeks-verification smoke and a commit. The "Greeks gate failure" framing in the predecessor brief came from a Memorial Day probe that returned null Greeks **but was inconclusive due to market closure**. The 2026-05-26 schema decision (commit `8267d3e` + `9307a9e`) restored the Greeks-present assumption based on production-code chain evidence and designed a live-market verification gate (the `scripts/options_chain_greeks_smoke.py` test). **[CORRECTED 2026-05-28 — see top-of-doc note]** The smoke WAS run on 2026-05-27 ~15:14 ET and failed (0/497 Greeks), but UW was at 102% of daily budget at the time, so the result is confounded by load, not a clean endpoint verdict. The disposition is a low-load re-smoke on 2026-05-28 AM. **Disposition: unblock as-is IF the clean re-smoke passes. ~1h to ship.**
- **Part A — UW MCP is NOT in Claude.ai connectors**, confirmed empirically by a fresh Claude.ai instance probing its own tool list on 2026-05-27. **However, Pandora MCP IS connected** — and committee skills already call it for hub state (`hub_get_quote`, `hub_get_positions`, etc.). The gap is **NOT "Pandora MCP is missing"**; the gap is **"Pandora MCP doesn't expose ticker-specific deep-dive analytical tools yet."** Three named tools — `hub_get_options_chain`, `hub_get_chart_indicators`, `hub_get_market_profile` — are explicitly called out as missing in each of [DAEDALUS](../skills/daedalus/SKILL.md), [PYTHAGORAS](../skills/pythagoras/SKILL.md), and [PYTHIA](../skills/pythia/SKILL.md)'s SKILL.md "Closing the gap" sections.
- **Part A — `claude_desktop_config.json` contains ONLY `desktop-commander`** — no UW MCP, no TradingView MCP, no Pandora MCP. **The memory note "UW MCP and TradingView MCP installed in claude_desktop_config.json" is stale.** Claude Desktop config is **also not the surface where committee skills run** — committee work happens in Claude.ai (web/mobile), which uses account-level Connectors (also called MCP servers in the UI), a separate layer from Claude Desktop. Cross-layer confusion is a real risk and should be retired from future briefs.
- **Part C / D — `hub_get_chart_indicators` doesn't need TradingView.** UW exposes `/api/stock/{ticker}/technical-indicator/{function}` ([uw-openapi.yaml:20706](audit-artifacts/2026-05-22/uw-openapi.yaml)) with 50+ functions including SMA, EMA, RSI, MACD, BBANDS, VWAP, ADX, ATR — every indicator PYTHAGORAS lists in its [SKILL.md](../skills/pythagoras/SKILL.md) Indicator Alignment section. **PYTHAGORAS becomes a pure Hub-wrap build**, same shape as Task 3, ~6–8h CC time.
- **Part C / D — `hub_get_market_profile` is the only tool that requires TradingView.** UW does NOT expose MP / TPO / value area / single prints / day-type. PYTHIA's [automation-roadmap.md](../skills/pythia/references/automation-roadmap.md) already documents the four-phase plan: TradingView Pine Script + webhook → Railway endpoint → Postgres → hub MCP tool. Phase 0 (nothing built). Phase 1 alone (key level alerts: VAH/VAL/POC broadcast + IB range alert + 80% rule + poor high/low detection) is the **minimum viable build** — ~12-20h CC time.
- **Part D recommendation — D.2 (Hub MCP wrappers).** For DAEDALUS and PYTHAGORAS, D.2 is the obvious extension of the existing pattern: both wrap UW endpoints, hub absorbs UW API changes, A.4a caller-tag discipline preserved. For PYTHIA, D.2 is the only option (D.1 direct-UW doesn't apply since UW has no MP data). The D.1 alternative (add direct UW MCP to Claude.ai connectors) is **also not blocked** but adds a new credential surface and bypasses caller-tagging — not recommended.
- **Top 3 build-brief decisions the audit unblocks:**
  1. **Phase 1 = ship the existing Task 3 work.** Run the Greeks smoke during a live market session, commit + deploy + update DAEDALUS SKILL.md. Roughly half a session of work. Unlocks DAEDALUS's "qualitative-IV-mode caveat closed" line.
  2. **Phase 2 = build `hub_get_chart_indicators` as a UW wrapper.** Same architecture as Task 3 — tool + service + math + smoke + SKILL.md edit + skill bundle rebuild. Ship 1–2 functions first (RSI + SMA for the smoke), then expand to PYTHAGORAS's full indicator inventory. ~6–8h.
  3. **Phase 3 = build `hub_get_market_profile` Phase 1.** TradingView Pine Script + webhook → Railway endpoint → hub MCP tool. The biggest of the three; new infrastructure surface (TradingView webhook receiver) not yet built. Phase 1 of Pythia's 4-phase plan = "key level broadcast" (VAH/VAL/POC + IB + 80% rule + poor high/low) is the MVP. ~12–20h.

---

## 2. Part A — UW MCP Connection State (Claude.ai-side)

### 2.1 (A.1) Configuration State

**Claude.ai connector inventory** — captured empirically by a fresh Claude.ai chat session on 2026-05-27. The instance probed its own tool list via `tool_search` queries for `unusual whales options flow` and `unusualwhales uw stock_state`. Neither query surfaced a UW-namespaced tool. Connected MCP servers (named verbatim by the Claude.ai instance):

> Gmail, Google Calendar, Canva, Figma, S&P Global, Supabase, Google Drive, PDF Viewer, Audible, Adobe Marketing Agent, Adobe Journey Optimizer, Google Cloud BigQuery, Indeed, AWS Marketplace, GovTribe, Spotify, **Pandora MCP**.

**No "Unusual Whales" entry.** Confirmed (memory note "UW MCP entry was missing from Claude.ai" reconfirmed as of 2026-05-27).

**`claude_desktop_config.json` inventory** — read from `C:\Users\nickh\AppData\Roaming\Claude\claude_desktop_config.json` on 2026-05-27. Full content (15 lines):

```json
{
  "mcpServers": {
    "desktop-commander": {
      "command": "cmd",
      "args": ["/c", "npx", "-y", "@smithery/cli@latest", "run", "@wonderwhy-er/desktop-commander"]
    }
  }
}
```

**ONLY `desktop-commander` is listed.** No UW MCP, no TradingView MCP, no Pandora MCP. **The memory note "UW MCP and TradingView MCP installed in claude_desktop_config.json (verified mid-2026 that UW MCP entry was missing from Claude.ai)" is stale on the first half** — Desktop config does not in fact contain either entry. The memory note's second half (UW missing from Claude.ai) is **reconfirmed today**.

**Cross-layer clarification (important for future briefs):** `claude_desktop_config.json` governs **Claude Desktop** only. The committee skills run in **Claude.ai (web/mobile)**, which sources its MCP servers from account-level Connectors — a completely separate configuration surface. The Claude.ai instance probing on 2026-05-27 explicitly diagnosed this: "claude_desktop_config.json is Claude Desktop only and doesn't reach the web/mobile chat surface." **The desktop config is therefore not the authoritative answer to "what tools does the committee see."** The Claude.ai connector list is.

### 2.2 (A.2) UW MCP Tool Inventory (if connected)

**N/A — UW MCP is not connected to Claude.ai per A.1.** Skipping empirical inventory.

**What the connection entry should look like if added** — based on the Anthropic MCP catalog discovery pattern and parallels to how the RH MCP is registered (see [rh-mcp-integration-audit-2026-05-27.md §2.2](rh-mcp-integration-audit-2026-05-27.md)): the user would add UW MCP via Claude.ai's Connectors UI (account settings), point at the UW-hosted MCP endpoint URL (which UW would publish if they shipped an MCP server — they have not as of 2026-05-27), and authenticate via whatever OAuth flow UW supports. **UW has not publicly shipped an MCP server.** Closest existing surfaces are community implementations (e.g., the open-stocks-mcp GitHub project surfaced during the RH audit), which would not be an Anthropic-hosted Connector and would have a different trust profile.

**Recommended follow-up (not in scope for this audit):** before any future brief assumes "UW MCP is available," check (a) UW's developer status page for an MCP announcement, (b) Anthropic's Connector catalog at claude.ai/settings/connectors. If both are silent, UW MCP is still vapor and only Hub MCP wrappers serve the committee.

### 2.3 (A.3) Empirical Connection Test

**N/A — UW MCP not connected per A.1.** Skipping. The analogous empirical test (call Pandora MCP `hub_get_quote` for SPY and confirm UW-sourced data flows through) was **offered by the Claude.ai instance** ("if you want me to smoke-test Pandora MCP:hub_get_quote on SPY as a proxy [...] say the word"). The smoke was declined because (a) Pandora MCP's working state is already established by production use, and (b) the audit's scope is the gap, not the existing working path.

**The Pandora MCP path IS the proxy for UW data into committee skills today** — confirmed by the Claude.ai instance reading the `hub_get_quote` tool description: *"Returns the current real-time quote for a single ticker from the Pandora's Box hub via Unusual Whales."* The Pandora MCP works; the half-power problem is **NOT that Pandora MCP is missing** but that Pandora MCP **does not yet expose the three ticker-specific deep-dive tools** the committee skills need.

---

## 3. Part B — Task 3 (`hub_get_options_chain`) State

### 3.1 (B.1) Working Tree State

**Reframing from the brief: Task 3 is not "parked with Greeks gate failed."** It is **STAGED but uncommitted** — fully implemented across 4 working-tree files and already wired into the tool registry. The git log shows no implementation commit; the last Task 3 commit was the schema/ATLAS-review brief, not the code.

**Branch state** — working tree on `main`. No feature branch for Task 3 (`git branch -a` shows no `task3-*` or similar). No stash entries (`git stash list` empty). The work was authored directly in the working tree of `main` and never committed.

**Parked files** (`?? ` = untracked, ` M` = modified-but-staged):

| File | Status | Lines | Purpose |
|---|---|---|---|
| [backend/hub_mcp/tools/options_chain.py](../backend/hub_mcp/tools/options_chain.py) | `??` untracked | 127 | MCP tool layer — `@mcp_tool(name="hub_get_options_chain")` with input validation, error envelope, summary string. Calls into the service layer. |
| [backend/services/read_only/options_chain.py](../backend/services/read_only/options_chain.py) | `??` untracked | 371 | Service layer — composes 3 UW endpoints (`get_options_snapshot`, `get_iv_rank`, `get_max_pain`), with module-level singleflight (`_inflight: Dict[str, asyncio.Future]`), Redis cache (25s TTL via `option_chain_live` category), partial-failure semantics (`aggregates_errors[]` array). |
| [backend/utils/options_math.py](../backend/utils/options_math.py) | `??` untracked | 121 | Extracted math helpers — `compute_mid()` (bid/ask → last_trade → day close → vwap fallback chain), `compute_bid_ask_spread_pct()` (DAEDALUS's >10% liquidity flag), `extract_greeks()` (delta/gamma/theta/vega/iv extraction with per-Greek nullability per ATLAS Pass 1 L2). |
| [scripts/options_chain_greeks_smoke.py](../scripts/options_chain_greeks_smoke.py) | `??` untracked | 132 | The Greeks-verification smoke test (ATLAS M1 fail-stop). Calls `get_options_chain("SPY", <next Friday>, "both")` and checks that ≥1 contract returns non-null delta/gamma/theta/vega. Pass criterion was sharpened in the ATLAS Pass 1 amendment to "5 strikes ATM both sides" but the smoke as currently written checks the looser ≥1-contract criterion ([options_chain_greeks_smoke.py:90-96](../scripts/options_chain_greeks_smoke.py#L90-L96)). |
| [backend/hub_mcp/tools/__init__.py](../backend/hub_mcp/tools/__init__.py) | ` M` modified | +1 | Adds `from . import options_chain as _options_chain` at line 16 — side-effect-registers the tool with the decorator registry. |
| [backend/hub_mcp/decorators.py](../backend/hub_mcp/decorators.py) | ` M` modified | +1 | Adds `"hub_get_options_chain"` to `REGISTERED_TOOL_NAMES` frozenset at line 27. |

**`backend/integrations/uw_api.py` refactor described in the Task 2 schema doc** (lines 1074-1108: delete `_get_contract_mid` body, replace with `from utils.options_math import compute_mid`) — **NOT in the current working tree.** The refactor was deferred; the new service layer calls `compute_mid` / `extract_greeks` from `utils.options_math`, but the legacy `_get_contract_mid` / `_get_contract_greeks` in `uw_api.py` still exist (4 production callers continue to use the old helpers). Behavior is preserved by the math being byte-for-byte identical; the consolidation is cosmetic.

**Disposition note for the build brief:** the `uw_api.py` refactor is a low-priority cleanup, not on the critical path. Ship Task 3 with the duplicate helpers, schedule the dedupe for a later brief.

### 3.2 (B.2) Greeks Gate Failure Root Cause

**The "Greeks gate failure" framing in the predecessor brief is incorrect.** Reconstructed timeline from git log + Task 2 schema doc:

| Date | Event | Source |
|---|---|---|
| 2026-05-24 | Initial brief: `hub_get_options_chain` MCP tool | `fc86293` |
| 2026-05-24 | ATLAS-review amendments | `eea7bc8` |
| 2026-05-24 | Task 1 spec — UW spec validation + ATLAS recon | `d4f96ae` |
| 2026-05-25 (Memorial Day) | **Empirical UW probe** — UW `/option-contracts` returned `delta/gamma/theta/vega = null` on the sample SPY contract. **Inconclusive** because market closed. | `e20a166` (Task 1 amendment) |
| 2026-05-26 | Task 1 Amendment #2 — Option C exhausted, no alternate Greeks source | `4c92db1` |
| 2026-05-26 | Task 2 schema design — Option A (no Greeks v1) | `6052e4b` |
| 2026-05-26 | **Task 2 Amendment #1 — Greeks-present assumption RESTORED** based on production-code chain evidence (4 production callers in `integrations/uw_api.py` read `c.get("delta")` and have been silently getting None for years without surfacing bugs — that's empirically strong evidence Greeks DO populate during live market sessions, the spec just lagged). | `8267d3e` |
| 2026-05-26 | Task 2 Amendment #2 — ATLAS Pass 1 resolution. Greeks-verification gate sharpened to "5 strikes ATM both sides must have non-null delta + IV." Code can begin. | `9307a9e` |
| 2026-05-26 → 2026-05-27 | **Implementation written** (4 files, ~750 LoC) — `tools/options_chain.py`, `services/read_only/options_chain.py`, `utils/options_math.py`, `scripts/options_chain_greeks_smoke.py`. **Never committed.** | working tree |
| 2026-05-27 ~15:14 ET | **[CORRECTED] Smoke WAS run and FAILED: 0/497 SPY contracts had Greeks** (spot null, iv_rank field-missing; max_pain worked). **Confound: UW at 102% daily budget (20,366/20,000).** UW degrades multiple endpoints together under load, so this is inconclusive, not a clean endpoint verdict. | `docs/codex-briefs/a4a-uw-overdraw-handoff-2026-05-27.md` §3 |
| 2026-05-28 AM | Planned clean re-smoke at low load (counter resets midnight ET + A.4a load reduction). This is the authoritative tiebreaker. | ship brief Task 2 |

**The actual gate state is "not run, not failed."** Cite [scripts/options_chain_greeks_smoke.py:1-18](../scripts/options_chain_greeks_smoke.py#L1-L18) verbatim:

> Task 7 — Greeks verification gate smoke for hub_get_options_chain.
> ATLAS M1 fail-stop: confirms UW's /option-contracts endpoint returns non-null delta/gamma/theta/vega for at least one SPY weekly contract. If this fails, the Greeks-present assumption from Task 2 is invalid and the schema must revert before Task 6 (DAEDALUS bundle rebuild).

**The smoke is the gate; the gate has not been exercised.** The 2026-05-25 Memorial Day probe ≠ the gate (it was a pre-design probe, used to inform the Task 2 schema decision). The gate is designed to run during a live market session (≥09:30 ET on a trading day) and confirm Greeks populate against UW's `/option-contracts` endpoint at that time.

**Production-code evidence for the Greeks-present assumption** — cited at [`hub-get-options-chain-task2-schema-2026-05-26.md` (Amendment #1)](codex-briefs/hub-get-options-chain-task2-schema-2026-05-26.md):

> The 4-production-consumer argument is empirically strong: zero delta on a real position priced at $1.50 mid would have produced obvious bugs (mark-to-market drift, sizing math errors, broker-quote mismatches). Nothing of the kind has been reported. Spec-lag is the overwhelmingly likely explanation.

The 4 production consumers (`get_spread_value`, `get_single_option_value`, `get_multi_leg_value`, `get_ticker_greeks_summary` in `backend/integrations/uw_api.py`) have been calling `c.get("delta")` for months. If UW returned null Greeks during live market hours, position-pricing would have been broken — and it isn't.

### 3.3 (B.3) Disposition Recommendation

**Unblock as-is.** The recommendation matrix:

| Option | Effort | Risk | Recommendation |
|---|---|---|---|
| **A. Unblock as-is** — run the Greeks smoke during a live market session (any trading-day morning ≥09:30 ET). If pass: commit the 4 untracked files + 2 modified files, push, Railway auto-deploys, then rebuild & re-upload `daedalus.skill` with the post-v1 SKILL.md edit. | ~1h total: 5 min smoke + 15 min commit/deploy/verify + 30 min SKILL.md edit + 10 min bundle rebuild + 10 min upload to Claude.ai. | LOW. Smoke is non-destructive (1 UW call); commit is reversible; the SKILL.md edit is well-specified in the Task 2 schema doc lines 316-334. | **RECOMMENDED.** |
| B. Redesign Greeks gate | ~4-8h (re-architect partial-failure semantics, write new smoke, new ATLAS review pass). | MEDIUM. The current gate design has 2 ATLAS Pass 1 amendments; it's been thoroughly reviewed. Redesigning would discard hard-won review work. | NOT recommended unless the smoke actually fails. |
| C. Abandon `hub_get_options_chain` — let DAEDALUS use UW MCP directly | N/A — UW MCP isn't connected to Claude.ai (per A.1). Adoption of UW MCP is its own multi-week brief. | HIGH. Loses caller-tag discipline; introduces new credential surface; abandons ~750 LoC of working code. | NOT recommended. |

**Disposition rationale:** Option A's effort estimate (~1h) is materially lower than Option B (~4-8h) or Option C (multi-week). The Greeks-present assumption is supported by production-code evidence, not just hope. The smoke is the verification — run it, then commit. If it fails, the v1.5 revert checklist at [hub-get-options-chain-task2-schema-2026-05-26.md:394-405](codex-briefs/hub-get-options-chain-task2-schema-2026-05-26.md) is documented and executable (drop the 4 Greeks fields, keep `implied_volatility`, revert SKILL.md to qualitative-Greeks-mode language).

**Coordination with the build brief:** Phase 1 of the eventual UW MCP / Committee Integration Build Brief should be Option A above. Phases 2 and 3 (PYTHAGORAS, PYTHIA) follow.

---

## 4. Part C — Half-powered-agent Gap Inventory

### 4.1 (C.1) DAEDALUS

**Data needs for full-power trade review** — per [skills/daedalus/SKILL.md:71-77](../skills/daedalus/SKILL.md#L71-L77) ("DAEDALUS-specific data caveat"):

> Real-time Greeks (delta, theta, gamma, vega) and IV rank / IV percentile are NOT currently exposed via the hub MCP. DAEDALUS reads structural snapshots from flow radar and infers IV regime from recent moves + VIX context. [...] Every DAEDALUS output in qualitative-IV mode must explicitly state: "Precise Greeks / IV rank require chain snapshot — current analysis uses inferred IV regime from price action + VIX context."

**Current access pattern:** Hub MCP via Pandora MCP. Calls `hub_get_quote`, `hub_get_flow_radar`, `hub_get_hydra_scores`, `hub_get_portfolio_balances`, `hub_get_positions` per [skills/daedalus/SKILL.md:61-69](../skills/daedalus/SKILL.md#L61-L69). **No ticker-specific options chain tool.** Greeks and IV rank are explicitly missing.

**Agent-specific data needs:**
- 21-DTE rule application: needs DTE awareness on each contract → satisfied by `expiry` field in chain
- Three-bucket framework: needs sizing math against live balance → already satisfied via `hub_get_portfolio_balances` (no gap)
- Canonical-walker: N/A for DAEDALUS
- **DAEDALUS-specific:** per-strike Greeks for structure selection (delta for directional exposure, theta for time-decay budget, vega for IV exposure, gamma for convexity); IV rank for buy-vs-sell-premium decision; max pain for expiry-pin analysis; bid-ask spread % for the >10% liquidity flag hard rule ([skills/daedalus/SKILL.md:172](../skills/daedalus/SKILL.md#L172)).

**Minimum-viable tool:** `hub_get_options_chain(ticker, expiry, option_type="both")` — **already built per Part B.** Returns per-contract Greeks + IV + bid-ask spread + chain-level IV rank + max pain (filtered to expiry) + total OI. Closes 100% of the documented data caveat.

### 4.2 (C.2) PYTHAGORAS

**Data needs for full-power trade review** — per [skills/pythagoras/SKILL.md:72-78](../skills/pythagoras/SKILL.md#L72-L78) ("PYTHAGORAS-specific data caveat"):

> Specific chart level values (key MAs, VWAP positions, swing highs/lows, support/resistance) require Nick to provide a chart screenshot OR specific levels via TradingView indicator. If neither is available, PYTHAGORAS frames qualitatively in trend-framework terms without fabricating specific level values.

**Current access pattern:** Hub MCP via Pandora MCP. Calls `hub_get_quote`, `hub_get_bias_composite`, `hub_get_flow_radar`, `hub_get_positions` per [skills/pythagoras/SKILL.md:63-68](../skills/pythagoras/SKILL.md#L63-L68). **No ticker-specific chart-indicator tool.** Specific MA / VWAP / RSI / MACD values are missing.

**Agent-specific data needs:**
- CTA zone system (L.06) — SMA 20/50/120/200 stack order; PYTHAGORAS cites the zone state by default
- Triple Line Trend Retracement (S.01) — VWAP + dual 200 EMA, ADX >25, time after 10 AM ET
- CTA Flow Replication (S.02) — three-speed SMA, two-close rule, Volume Lie Detector
- Volume Lie Detector (C.05) — RSI/MACD divergence + volume delta
- Indicator alignment per the output template ([skills/pythagoras/SKILL.md:109](../skills/pythagoras/SKILL.md#L109)): RSI, MACD, ATR, volume

**Decisive UW finding:** [uw-openapi.yaml:20706 — `/api/stock/{ticker}/technical-indicator/{function}`](audit-artifacts/2026-05-22/uw-openapi.yaml) supports **50+ indicator functions**, including every indicator PYTHAGORAS lists:

> Supported functions: SMA, EMA, WMA, DEMA, TEMA, TRIMA, KAMA, MAMA, T3, **MACD**, MACDEXT, STOCH, STOCHF, **RSI**, STOCHRSI, WILLR, **ADX**, ADXR, APO, PPO, MOM, BOP, CCI, CMO, ROC, ROCR, AROON, AROONOSC, MFI, TRIX, ULTOSC, DX, MINUS_DI, PLUS_DI, MINUS_DM, PLUS_DM, **BBANDS**, MIDPOINT, MIDPRICE, SAR, TRANGE, **ATR**, NATR, AD, ADOSC, OBV, HT_TRENDLINE, HT_SINE, HT_TRENDMODE, HT_DCPERIOD, HT_DCPHASE, HT_PHASOR, **VWAP**.

**`hub_get_chart_indicators` does NOT need TradingView.** This is a significant revision of the assumption in [skills/pythagoras/SKILL.md:78](../skills/pythagoras/SKILL.md#L78) ("v2 hub MCP candidate (via TradingView webhook → Railway pipeline)"). The SKILL.md prediction was wrong about the data source; UW already serves the data. **The build is a pure Hub-wrap, same architecture as Task 3.**

**Minimum-viable tool:** `hub_get_chart_indicators(ticker, function, interval="daily", time_period=14, series_type="close")` — pass-through wrapper around UW `/technical-indicator/{function}` with Hub-side caching + caller-tag + rate-limit. Initial release should expose ≥6 functions: RSI, MACD, SMA, EMA, VWAP, BBANDS. Subsequent releases expand to PYTHAGORAS's full inventory.

### 4.3 (C.3) PYTHIA

**Data needs for full-power trade review** — per [skills/pythia/SKILL.md:72-78](../skills/pythia/SKILL.md#L72-L78) ("PYTHIA-specific data caveat"):

> Market Profile data (POC, VAH, VAL, IB, single prints, day type) is NOT currently available from either the hub or web_search. PYTHIA's structural reads rely on Nick providing the levels via screenshot, TradingView indicator, or verbal description.

**Current access pattern:** Hub MCP via Pandora MCP. Calls `hub_get_quote`, `hub_get_bias_composite`, `hub_get_flow_radar`, `hub_get_positions` per [skills/pythia/SKILL.md:63-68](../skills/pythia/SKILL.md#L63-L68). **No ticker-specific Market Profile tool.** POC / VAH / VAL / IB / single prints / day type are all missing.

**Agent-specific data needs:**
- POC, VAH, VAL — value-area architecture (M.01 — liquidity clusters)
- IB (Initial Balance) — first 60 min range; narrow-IB / wide-IB classification (M.05 day types)
- Single prints — unfinished-business zones (F.02 — trapped traders)
- Poor high / poor low — repair candidates (M.04 — stop-run sequences)
- Day type classification (M.05) — normal / trend / double-distribution / P-shape / b-shape
- Value area migration — trending vs bracketing signal (the single most important PYTHIA question, per [SKILL.md:37-38](../skills/pythia/SKILL.md#L37-L38))
- 80% rule — opening outside VA then re-entering (M.04 setup family)
- Volume profile overlap with PYTHAGORAS — HVN/LVN; volume-at-price

**Decisive UW finding (negative):** UW does NOT expose Market Profile / TPO / value area data. The 22 currently-wrapped + 155 currently-unwrapped UW endpoints documented in [uw-integration-audit-2026-05-22.md §2](uw-integration-audit-2026-05-22.md) include zero MP-shaped endpoints. **`hub_get_market_profile` requires a non-UW data source.**

**Data source for the MVP:** TradingView Pine Script + webhook → Railway endpoint. [skills/pythia/references/automation-roadmap.md](../skills/pythia/references/automation-roadmap.md) documents the four-phase plan in detail:

- **Phase 1 — Key Level Alerts** (the MVP for the build brief):
  - Daily Value Area Levels Broadcast (VAH/VAL/POC of prior session + developing POC every 30 min)
  - IB Range Alert (after first 60 min — narrow/wide classification)
  - Value Area Migration Tracker (today's VA vs prior — higher/lower/overlapping/non-overlapping)
  - 80% Rule Alert (open outside VA + re-entry detection)
  - Poor High / Poor Low Detection (at session close — excess vs flat tail)
- **Phase 2 — Profile Shape Classification** (Day Type Classifier, Single Print Detection)
- **Phase 3 — Composite Profile Dashboard** (Multi-Session Composite over 5/10/20 sessions)
- **Phase 4 — Volume Delta Integration** (CVD at key MP levels)

**Phase 1 alone closes the dominant PYTHIA gap.** The build brief should scope Phase 1 as the MVP; Phases 2-4 are follow-up briefs.

**Minimum-viable tool:** `hub_get_market_profile(ticker, session="prior_day")` — returns POC, VAH, VAL, developing VAH/VAL, IB width + classification, and 80%-rule-trigger flag. Data comes from a TradingView webhook receiver (new Railway endpoint) that ingests the alerts from Pine Script indicators on Nick's TradingView account and persists to Postgres for hub-side lookup. Three new infrastructure surfaces: Pine Script indicators (Nick-side, in TradingView), Railway webhook receiver, and Postgres `market_profile_levels` table.

**Overlap with PYTHAGORAS:** PYTHAGORAS's "volume" indicator + Volume Lie Detector overlap with PYTHIA's HVN/LVN identification. **Recommend the build brief scope these tools as separate ownership** — PYTHAGORAS owns trend-context volume (delta divergence, breakout confirmation); PYTHIA owns volume-at-price structure (HVN/LVN/POC). The data sources are different (UW's `/technical-indicator/VWAP` and `/options-volume` for PYTHAGORAS; TradingView Pine Script volume profile for PYTHIA).

---

## 5. Part D — Architecture Decision

### 5.1 (D.1) Direct UW MCP Access (Claude.ai-side)

**Status:** Not currently possible. UW has not publicly shipped an MCP server. The Anthropic Connectors catalog (claude.ai/settings/connectors) does not list "Unusual Whales." If UW were to ship an MCP server in the future, this option becomes viable; until then, it's vapor.

**Even if available, the trade-offs:**
- **Pros:** no Hub-side build; lower Hub surface; UW maintains; new endpoints arrive without Hub work.
- **Cons:** no caller-tagging (the A.4a discipline lives Hub-side, in `backend/integrations/uw_api.py`); no Hub-side rate limiting under the budget pin; no central caching (each MCP call goes to UW raw); new credential surface (UW MCP would have its own OAuth flow); multi-MCP-server complexity in Claude.ai (Pandora MCP + UW MCP + future RH MCP).

### 5.2 (D.2) Hub MCP Wrappers — RECOMMENDED

**The existing pattern.** Pandora MCP already wraps UW for the 8 currently-shipped Hub tools (`hub_get_quote`, `hub_get_flow_radar`, `hub_get_sector_strength`, `hub_get_hermes_alerts`, `hub_get_hydra_scores`, `hub_get_positions`, `hub_get_portfolio_balances`, `hub_get_bias_composite`). The proposed three new tools (`hub_get_options_chain`, `hub_get_chart_indicators`, `hub_get_market_profile`) extend this pattern.

- **Pros:** consistent with the existing `hub_get_*` pattern; central rate limit + caching under the UW budget pin; single UW credential surface (existing `UW_API_KEY` continues to be the only UW credential); **A.4a caller-tag compliance** (every UW call goes through `integrations/uw_api.py` which tags the caller); protects skills from UW API changes (hub absorbs the breaking change, skill SKILL.md tool calls don't have to change).
- **Cons:** more Hub-side build (~6–8h for PYTHAGORAS, ~12–20h for PYTHIA — DAEDALUS is already built per Part B); another layer to debug.

### 5.3 (D.3) Hybrid

**N/A.** D.1 isn't currently available; the hybrid option collapses to D.2 by default. If UW ships an MCP server later, a hybrid (D.2 for hot paths + D.1 for cold paths) becomes a viable later optimization. For now, D.2 is the only viable path for DAEDALUS and PYTHAGORAS; D.2 with a TradingView pipeline is the only path for PYTHIA.

### 5.4 (D.4) Recommendation

**D.2 — Hub MCP wrappers, for all three tools.**

- **`hub_get_options_chain`** — already built per Part B; disposition is ship-as-is.
- **`hub_get_chart_indicators`** — UW-wrap, pure Hub-side, same architecture as Task 3.
- **`hub_get_market_profile`** — TradingView pipeline → Railway webhook → Hub MCP tool. Phase 1 of PYTHIA's automation-roadmap is the MVP.

**Caller-tag preservation** is the decisive factor. The A.4a discipline (caller-tagging every UW call so the budget pin can attribute the burn) was hard-won; introducing a major un-tagged caller path (UW MCP from skills) regresses that discipline. D.2 keeps all UW calls under the Hub umbrella where A.4a's caller tags are enforced.

**Cross-check against Part A findings:** A.1 confirmed UW MCP isn't connected to Claude.ai, so D.1 is moot even if it were preferable. D.2 is the only viable path. The recommendation is robust.

---

## 6. Open Questions

| # | Question | Follow-up vector |
|---|---|---|
| Q1 | Does the Greeks-verification smoke ([scripts/options_chain_greeks_smoke.py](../scripts/options_chain_greeks_smoke.py)) pass during a live market session today? | Run the smoke during 2026-05-28 (or any subsequent trading-day morning ≥09:30 ET). Pass = ship Task 3 per disposition. Fail = execute v1.5 revert checklist from Task 2 schema doc. |
| Q2 | The smoke's pass criterion is ≥1 contract with all 4 Greeks non-null ([smoke L90-96](../scripts/options_chain_greeks_smoke.py#L90-L96)); ATLAS Pass 1 Amendment sharpened the criterion to "5 strikes ATM both sides." Which criterion governs at ship-time? | Build-brief Phase 1 must tighten the smoke to the ATLAS criterion before running. ~15 min code change. |
| Q3 | DAEDALUS SKILL.md update from Task 2 schema doc lines 316-334 hasn't been applied yet. After Task 3 ships, who applies it and rebuilds `daedalus.skill`? | Build brief Phase 1 ownership. Mechanical edit + `scripts\package-skill.ps1 daedalus` + Nick re-uploads to claude.ai. |
| Q4 | The `uw_api.py` refactor described in Task 2 schema (lines 281-289: delete `_get_contract_mid` body, replace with import from `utils.options_math`) was deferred. Is it acceptable to ship the duplicate-helper state or must the refactor land first? | Recommend ship duplicate, defer refactor to a Phase 4 cleanup brief. Duplicate is byte-for-byte identical so behavior is preserved. |
| Q5 | What's the UW rate limit headroom for `hub_get_chart_indicators` if PYTHAGORAS calls it multiple times per pass (RSI + MACD + SMA + EMA + VWAP + BBANDS = 6 calls per ticker)? | Phase 2 of the build brief should measure during smoke. Initial guess: 6 calls × ~200ms = ~1.2s per ticker; well within UW rate limit (120 req/min per UW audit) for the committee's actual usage pattern (≤5 tickers per pass). |
| Q6 | Should `hub_get_chart_indicators` accept a batch parameter (`functions=["RSI","MACD","SMA"]`) to reduce N round-trips? Or keep 1 function per call for simpler caching? | Phase 2 ATLAS review. Recommend batch for cache efficiency. |
| Q7 | Pine Script indicator authoring for PYTHIA Phase 1 — Nick-side build (TradingView account work) or CC-side build (CC writes Pine Script, Nick pastes into TV)? | Phase 3 build brief decision. Recommend CC writes the Pine Script; Nick reviews + pastes (per the "Training Value for Nick" framing in [automation-roadmap.md:40-47](../skills/pythia/references/automation-roadmap.md#L40-L47), Nick benefits from understanding the indicators, so co-build rather than CC-build-and-ship). |
| Q8 | TradingView webhook signature mechanism — does TradingView sign webhooks (HMAC)? If not, how does the Railway endpoint authenticate the request is genuinely from Nick's TV account? | Phase 3 build brief. TradingView webhook auth is typically a shared-secret URL token (`https://api.../webhook?token=<secret>`); recommend that pattern. |
| Q9 | Is the TradingView Premium plan's 400-alert cap a constraint? Phase 1 alone may use 5+ alerts per ticker × N tickers Nick wants tracked. | Phase 3 brief should compute and confirm headroom against Nick's current alert usage. |
| Q10 | Does the build brief need to coordinate with the (TBD) Brief #1 VPS Decommission? Specifically: does the VPS-side committee migration to Claude.ai depend on these three tools being available, or is it independent? | Surface to Titans during final review. If VPS decommission preserves the existing committee-skill access pattern (Pandora MCP via Claude.ai), the build brief is independent. If VPS decommission introduces a new access pattern, the build brief may need to align. // backlog candidate if Brief #1 not yet in flight |
| Q11 | The brief mentioned `backend/uw_integration/api_spec.yaml` as the canonical spec location. Actual location is `docs/audit-artifacts/2026-05-22/uw-openapi.yaml`. Worth normalizing the path? | Backlog candidate — update PROJECT_RULES.md or CLAUDE.md reference. // backlog candidate |
| Q12 | The `claude_desktop_config.json` only contains `desktop-commander`; the memory note about UW + TV MCP being installed there is stale. Is desktop-commander still needed for any current workflow? | Backlog candidate — clean up memory + verify desktop-commander usage is intentional. // backlog candidate |
| Q13 | Pandora MCP's existing surface (10 tools) lists `mcp_describe_tools` and `mcp_ping`. Is `hub_get_options_chain` (registered in `REGISTERED_TOOL_NAMES` per [decorators.py:24-29](../backend/hub_mcp/decorators.py#L24-L29)) going to surface in `mcp_describe_tools` after deploy? | Phase 1 smoke should include a `mcp_describe_tools` call post-deploy to verify the new tool appears. Validates the registration loop is complete. |
| Q14 | TradingView MCP separate from PYTHIA's TradingView-webhook approach? The `docs/codex-briefs/tv-mcp-cost-benefit-analysis.md` doc exists but is only 16 lines. | Backlog candidate. The cost-benefit doc is a stub. If TradingView ships an MCP server later, it could supersede the webhook-receiver path for PYTHIA — but the webhook path is the MVP today since no TV MCP exists. // backlog candidate |
| Q15 | A Tier-2 follow-up brief was queued by Task 2 for per-contract Greeks via Black-Scholes (in case the smoke fails). Is that brief still warranted? | Defer. If Phase 1 smoke passes, Tier-2 is moot. If it fails, the v1.5 revert + Tier-2 brief becomes the path. |

---

## 7. Implications for Build Brief

The eventual UW MCP / Committee Integration Build Brief (Brief #3 in the queue) is sequenced and shaped by this audit as follows:

### 7.1 Phase 1 — Ship `hub_get_options_chain` (DAEDALUS)

**Unblocked by:** Part B disposition (Option A — Unblock as-is). All architectural decisions made, code written, registry wired. Only the live-market smoke + commit + deploy + SKILL.md edit remain.

**Effort:** ~1h end-to-end.

**Sequence:**
1. Tighten [options_chain_greeks_smoke.py:90-96](../scripts/options_chain_greeks_smoke.py#L90-L96) pass criterion from "≥1 contract" to "5 ATM strikes both sides" per ATLAS Pass 1 Amendment (~15 min). _(Q2)_
2. Run smoke during a live market session ≥09:30 ET on a trading day. If pass: proceed to step 3. If fail: execute v1.5 revert checklist from Task 2 schema doc (drop Greeks fields, keep IV, revert SKILL.md, ship as v1.5).
3. Commit the 4 untracked files + 2 modified files. Push. Railway auto-deploys.
4. Verify post-deploy: call `mcp_describe_tools` via Pandora MCP from a fresh Claude.ai session; confirm `hub_get_options_chain` appears in the tool list. _(Q13)_
5. Apply DAEDALUS SKILL.md edit per Task 2 schema doc lines 316-334 (caveat-closed language + insert tool call between flow_radar and hydra_scores). _(Q3)_
6. Rebuild bundle: `scripts\package-skill.ps1 daedalus`. Nick re-uploads to Claude.ai.

**Olympus impact:** DAEDALUS comes up to full power. The "qualitative-IV-mode" caveat closes. Committee analytical quality improves on every trade idea touching options.

### 7.2 Phase 2 — Build `hub_get_chart_indicators` (PYTHAGORAS)

**Unblocked by:** Part C.2 finding (UW exposes `/api/stock/{ticker}/technical-indicator/{function}` with 50+ functions including every indicator PYTHAGORAS lists). PYTHAGORAS's SKILL.md prediction of "TradingView webhook → Railway pipeline" is **incorrect**; UW serves the data directly.

**Effort estimate:** ~6–8h CC time. Same architecture as Task 3 — MCP tool + service layer + smoke + SKILL.md edit + bundle.

**Sequence:**
1. New brief: `hub-get-chart-indicators-2026-XX-XX.md` — scope: 6 initial functions (RSI, MACD, SMA, EMA, VWAP, BBANDS), batch parameter, 60s cache TTL.
2. Implement: `backend/hub_mcp/tools/chart_indicators.py`, `backend/services/read_only/chart_indicators.py`, smoke at `scripts/chart_indicators_smoke.py`. Reuse Task 3's singleflight + cache pattern.
3. Smoke: ≥1 successful call per function for SPY. Pass criterion = all 6 functions return data.
4. Update [skills/pythagoras/SKILL.md:72-78](../skills/pythagoras/SKILL.md#L72-L78) — replace "TradingView webhook → Railway pipeline" prediction with "hub_get_chart_indicators is live; Pythagoras gets RSI/MACD/SMA/EMA/VWAP/BBANDS via UW wrap." Insert tool call in Context A list.
5. Rebuild + upload `pythagoras.skill`.

**Olympus impact:** PYTHAGORAS comes up to full power on indicator analysis. Specific SMA / VWAP / RSI / MACD values become available without Nick providing a screenshot. "Indicator alignment" output field in the PYTHAGORAS committee template fills with real numbers, not framework-only language.

**Still gated:** Phase 2 brief should clarify Q5 (rate-limit headroom under realistic committee usage) and Q6 (batch parameter). Both are easy to answer during the brief draft, not blockers.

### 7.3 Phase 3 — Build `hub_get_market_profile` Phase 1 (PYTHIA)

**Unblocked by:** Part C.3 finding (UW does NOT expose MP; TradingView pipeline is the only path). PYTHIA's [automation-roadmap.md](../skills/pythia/references/automation-roadmap.md) has the four-phase plan; Phase 1 = key-level broadcast.

**Effort estimate:** ~12–20h CC time. Largest of the three. New infrastructure surfaces:
- Pine Script indicators (Nick-side, TradingView) — co-build with CC per [automation-roadmap.md:40-47](../skills/pythia/references/automation-roadmap.md#L40-L47)
- Railway webhook receiver — new endpoint `POST /webhook/tv-market-profile` with signature auth (Q8)
- Postgres `market_profile_levels` table — new schema
- Hub MCP tool `hub_get_market_profile` — pure read against the table

**Sequence:**
1. New brief: `hub-get-market-profile-phase1-2026-XX-XX.md` — scope: 5 alert types (VA broadcast, IB range, VA migration, 80% rule, poor high/low).
2. Pine Script authoring (CC writes drafts, Nick reviews + pastes into TV) — 5 indicators × ~30 min each = ~2.5h.
3. Railway webhook receiver + signature auth + Postgres write — ~3-4h.
4. Postgres schema migration: `market_profile_levels(id, ticker, session_date, level_type, value, fired_at)`.
5. Hub MCP tool — read from Postgres, return latest VAH/VAL/POC + IB + 80%-rule flag.
6. Smoke: trigger a Pine Script alert manually; verify it lands in Postgres; verify Hub MCP tool returns the level.
7. Update [skills/pythia/SKILL.md:72-78](../skills/pythia/SKILL.md#L72-L78) — replace caveat with "hub_get_market_profile Phase 1 is live; PYTHIA gets VAH/VAL/POC + IB + 80%-rule from Nick's TradingView Pine indicators via webhook → Postgres → Hub. Phases 2-4 deferred to follow-up briefs."
8. Rebuild + upload `pythia.skill`.

**Olympus impact:** PYTHIA comes up to half power (Phase 1 only — Phases 2-4 are follow-up briefs for full power). Key level values become available without Nick providing a screenshot. The dominant PYTHIA output ("MP data not provided — analysis is auction-theory framework only, not session-specific levels") goes away on the 5 Phase 1 alert types.

**Still gated:** Q7 (Pine Script ownership split), Q8 (webhook auth), Q9 (TV alert quota). Phase 3 brief draft must resolve these before code begins.

### 7.4 Olympus impact summary

**Phase 1 closes:** DAEDALUS qualitative-IV-mode caveat (line 71-77).
**Phase 2 closes:** PYTHAGORAS specific-chart-levels caveat (line 72-78).
**Phase 3 (Phase 1 only) partially closes:** PYTHIA MP-data-not-provided caveat (line 72-78) — for the 5 specific alert types; Phases 2-4 of automation-roadmap close it fully.

**Closure-note re-test coverage:**
- Each phase ships with its own closure note in `docs/strategy-reviews/` (`hub-get-options-chain-closure-note-YYYY-MM-DD.md`, etc.).
- Each closure note documents: smoke pass evidence, SKILL.md diff, bundle hash, post-deploy `mcp_describe_tools` verification.
- After all three phases ship, a committee re-test pass should run an Olympus committee pass on a single ticker (SPY or any active position) and confirm DAEDALUS / PYTHAGORAS / PYTHIA all surface real data instead of qualitative-only language.

### 7.5 Coordination with Brief #1 (VPS Decommission)

**Independent if Brief #1 preserves Pandora MCP access** (committee skills continue to call `hub_get_*` via Pandora MCP from Claude.ai). The three new tools land via the same Pandora MCP surface; no committee-skill access-pattern change.

**Coordinated if Brief #1 changes the committee access pattern** (e.g., moves committee runs to a Railway-side service that calls the UW client directly). In that case, the build brief's new tools need to be exposed via whatever new surface Brief #1 introduces. Surface to Titans during final review.

**Audit assumption:** Brief #1 preserves the current Pandora MCP access pattern. Build brief is therefore independent.

---

**Audit drafted:** 2026-05-27
**Audit committed:** TBD — `docs(audit): UW MCP / committee integration audit`
**Next action:** Titans Final Review pass (ATLAS, AEGIS, HELIOS, ATHENA) on this audit; build brief drafted only after Titans approval.
