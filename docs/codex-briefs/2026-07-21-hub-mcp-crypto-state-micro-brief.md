# MICRO-BRIEF — HUB-MCP-CRYPTO-STATE

**Authored:** 2026-07-21, coordination lane
**Type:** new MCP tool. Read-only wrapper over an existing endpoint. No new vendor integration.
**Origin:** DEF-FUNDING-CACHE-HEALTH closure. The assigned Olympus verification proved unrunnable — `mcp_describe_tools` returns 22 tools and **none exposes funding.** The gap is larger than funding.
**Titans review:** ATLAS sign-off required on the vendor-call question in Phase 0. Not a full pass.

---

## TASK 0 — FILING

```
cd /d C:\trading-hub
git fetch origin && git status
git mv 2026-07-21-hub-mcp-crypto-state-micro-brief.md docs\codex-briefs\
git add docs/codex-briefs/2026-07-21-hub-mcp-crypto-state-micro-brief.md
git commit -F C:\temp\commitmsg.txt
git push origin main
```

---

## THE GAP

Verified against the live registry (22 tools, schema v2.0). The crypto committee can currently see exactly two things:

| Tool | Returns |
|---|---|
| `hub_get_crypto_quote` | spot, 24h OHLCV, % change, source, timestamp |
| `hub_get_crypto_market_profile` | POC, VAH, VAL, session high/low |

**Not reachable by any committee agent:** funding rate and its health state, open interest, basis / term structure, liquidations, CVD and the spot-vs-perp split (`SPOT_LED` / `PERP_LED` / `MIXED`), regime and CTA-zone classification, tape health.

Every one of those exists in the backend. S-1 through S-4 built them. **None has an MCP surface.** So when PYTHIA reads crypto structure, THALES reads crypto regime, or DAEDALUS reads crypto positioning, they work from spot price and a volume profile while a dozen built surfaces sit unreachable behind the API.

This brief closes that gap by wrapping the endpoint that already aggregates them: `/api/crypto/state/{symbol}`.

### Why now, and one dependency that was met by luck

Nick is away 2026-08-04 → 2026-08-15, doing light trading from a phone with **no ability to deploy code.** Dashboards are awkward on mobile; committee passes are the natural interface in that window. A crypto committee pass today runs on spot and POC.

**Note the ordering that already happened:** had this tool shipped a week ago, it would have exposed the fake-degraded cache artifact (`db5e398`) to every committee agent — `degraded=true` on healthy funding, committee-wide, for an unknown period. **DEF-FUNDING-CACHE-HEALTH was a hard prerequisite for this brief and it was satisfied by sequence accident, not design.** It is satisfied now. Do not treat that as luck to be repeated.

---

## PHASE 0 — INVENTORY BEFORE BUILDING (stop-gate)

**Do not design the envelope before reading what the endpoint actually returns.** Three briefs in this workstream have now been wrong about what connects to what — twice from the coordination lane on funding alone. Read, then build.

1. **Read `/api/crypto/state/{symbol}` end to end.** Enumerate every field it returns today, with types and null-behavior. Name the file and line for the handler.
2. **Per-field health.** Which sub-blocks carry independent health/staleness state, and which are silent? Funding has `degraded`. Confirm what OI, basis, liquidations, CVD, regime, and tape-health carry.
3. **Vendor-call question — ATLAS sign-off gate.** Determine whether serving this endpoint triggers **new** outbound vendor calls (Coinalyze, Binance, OKX) or reads only existing caches. `hub_get_board_state`'s contract is explicit that it "never triggers a new UW request" — that is the pattern to match.
   - **If it reads caches only:** proceed, note it in the tool description.
   - **If it triggers vendor calls:** STOP. Report call count per invocation and hand to ATLAS for sizing against the 17K SHED / 18K ESCALATE thresholds before any build. A committee-invoked tool that fans out to vendors is a budget risk multiplied by every pass.
4. **Symbol coverage.** Confirm actual per-symbol availability across BTC, ETH, SOL, HYPE, ZEC, FARTCOIN. Known: tape health covers 5/6, FARTCOIN has a spot-fetch gap. Report the real matrix — do not assume the six are uniform.
5. **Cycle Extremes.** S-5 has not built the dial yet. Determine whether `/api/crypto/cycle-extremes` exists and returns anything today. If it does, include it. If it does not, **leave it out and note the seam** — do not stub it.

**If Phase 0 contradicts anything above, this brief is wrong, not the codebase.** Report and stop.

---

## PHASE 1 — BUILD

**Wrap the existing endpoint. Do not invent a new aggregation.** The tool's job is to expose what the backend already computes, not to compute anything.

### Envelope contract

Follow the established v2.0 pattern: `status` / `data` / `summary` / `staleness_seconds` / `schema_version` / `error`.

**Per-block health with top-level worst-case rollup.** `hub_get_stable_rates_fx` is the precedent — it carries two independently-timed sub-blocks, each with its own `as_of` / `anchor` / `degraded`, and the top-level status is the **worse** of the two. Crypto state has many more sub-blocks and they fail independently. A single flat status would hide a dead liquidations feed behind healthy funding.

### Three non-negotiables

1. **No fail-open defaults. Anywhere.** Do not write `.get("health_status", "LIVE")` or any equivalent that coerces a missing value into a healthy one. That exact pattern is what hid the same cache bug on OI and term_structure for its entire life while funding's fail-closed path was the only thing that surfaced it. **Missing state renders as unknown or degraded, never as healthy.**
2. **Surface `degraded`, never hide it.** D1.4's contract — a degraded funding input cannot report FIRING — depends on degraded state being visible downstream. The tool exposes the flag; it does not interpret it.
3. **Honest `unavailable` per symbol.** `hub_get_crypto_quote` sets the precedent: `status='unavailable'` with `spot=null` for HYPE/FARTCOIN is "expected and correctly reported, not a bug." Match it. **Never fabricate a value for a symbol the vendor does not cover.**

### Scope boundaries

- **Raw state, not scores.** `hub_get_crypto_market_profile` states plainly that the −45..+35 Market Structure Filter scoring is not exposed and must not be inferred. Same discipline here. Regime and CTA-zone *classifications* are fine — they are labeled engine outputs with provenance, not derived scores.
- **Read-only.** No writes, no cache warming, no side effects.
- **One tool, not several.** The endpoint already aggregates. Splitting it into six tools multiplies committee call volume for no gain.

### Tool description

Write it to the standard of the existing 22 — they are unusually good and they are how agents decide whether to call. It must state: the tracked six symbols and both accepted forms; **which sub-blocks exist and which are independently health-flagged**; that it reads caches and does not trigger vendor calls (assuming Phase 0 confirms); the per-symbol coverage matrix including the FARTCOIN gap; explicit "do NOT call this for spot price (`hub_get_crypto_quote`) or structural levels (`hub_get_crypto_market_profile`)"; and that scores are not exposed and must not be inferred.

---

## PHASE 2 — VERIFY

1. Unit tests on envelope shape, per-block rollup (worst-case wins), and the no-fail-open guarantee. **Include a test that a missing health field renders as unknown/degraded, never healthy** — this is the regression guard for the class of bug that just cost two briefs.
2. Live call per symbol across all six. Confirm the real coverage matrix matches Phase 0's finding, including honest `unavailable` where expected.
3. Confirm funding now reports `degraded=false` with a sane rate post-`db5e398`.
4. Full suite. Bar: byte-identical known-red **18 failed / 1 skipped / 200 errors**, passed rises by the new test count.
5. Four-step deploy verification. `/health=OK` is not proof.
6. Confirm `mcp_describe_tools` returns **23 tools** and the new description renders in full.

---

## PHASE 3 — HAND BACK (do not skip; the tool is inert without it)

**Shipping the tool does not make agents use it.** Three steps are required and missing any one leaves the work invisible:

| Step | Owner |
|---|---|
| Tool ships + deploy-verified | CC |
| **Olympus skill files updated** to reference `hub_get_crypto_state` — PYTHIA, THALES, DAEDALUS at minimum; likely TORO/URSA/PIVOT for crypto passes | coordination lane |
| **Pandora connector toggled** — a fresh chat reloads skills but does *not* refresh the connector's tool manifest | **Nick** |

CC: report the tool SHA and stop there. Do not edit skill files.

---

## DONE DEFINITION

1. Phase 0 inventory reported with named files/lines, or a contradiction reported and stopped.
2. ATLAS sign-off obtained **if** the endpoint triggers vendor calls.
3. Tool ships wrapping the existing endpoint, no new aggregation.
4. Per-block health with worst-case top-level rollup.
5. Zero fail-open defaults, with a test proving it.
6. Honest per-symbol `unavailable`; nothing fabricated.
7. Known-red byte-identical; four-step deploy verified; `mcp_describe_tools` shows 23.
8. `workstreams.md` updated. Skill-update + connector-toggle handed back, explicitly.

---

## OUT OF SCOPE

- Cycle Extremes dial (S-5). If the endpoint does not exist yet, note the seam and leave it.
- Any change to D1.4's suppression contract.
- Olympus skill file edits — coordination lane.
- `Funding_Rate_Fade`'s zero-signal problem — W2-4 triage.

---

## OLYMPUS IMPACT

**The largest of any brief in this window, and it is the entire point.** This changes what PYTHIA, THALES, and DAEDALUS can see on crypto from two surfaces to roughly ten.

Required post-ship, after the skill update and connector toggle: **one full crypto committee pass on BTC or ETH**, confirming each agent reaches the new blocks and that degraded sub-blocks are surfaced rather than silently skipped. Per the TORO-fabrication precedent, watch specifically for agents asserting values for sub-blocks that returned `unavailable`. A tool that makes ten new fields visible is also a tool that makes ten new fields fabricable.
