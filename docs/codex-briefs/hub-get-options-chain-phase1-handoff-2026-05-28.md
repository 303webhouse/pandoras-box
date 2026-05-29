# Brief — Ship `hub_get_options_chain` (Phase 1, DAEDALUS) — Handoff to Desktop CC — 2026-05-28

**Status:** READY FOR CC (desktop session, full UW API access)
**Type:** Build — ship staged work. Read-only MCP tool; non-destructive.
**Owner:** CC (desktop)
**Supersedes:** `brief-hub-get-options-chain-phase1-2026-05-27.md` (laptop-drafted). This is the canonical version — the prior brief had stale framing on the smoke history and the pre-flight (working-tree-based vs branch-based). Use this brief.
**Predecessors (mandatory reads, in this order):**
1. `docs/uw-mcp-committee-integration-audit-brief-2026-05-27.md` — the canonical audit. **Note:** Part B was corrected post-publication. A dated correction block at the top + inline in Part B replaces the original "smoke never ran" claim with the real 2026-05-27 failure-under-load history. Read the corrected version on `origin/main` (commit ≤ `414f7e4`).
2. `docs/codex-briefs/a4a-uw-overdraw-handoff-2026-05-27.md` §3 — the smoke-failure-under-load context. **This is the most important predecessor for this brief.** It explains why today's smoke is a clean-load tiebreaker rather than a first attempt.
3. `docs/codex-briefs/hub-get-options-chain-task2-schema-2026-05-26.md` — schema decision, DAEDALUS SKILL.md edit spec (lines 316–334), and v1.5 revert checklist (lines 394–405). Both are referenced verbatim by Task 6 and the revert path.
4. `docs/strategy-reviews/dual-review-hub-scope-2026-05-27.md` (currently in `outputs/`, may not be committed to `docs/strategy-reviews/` yet — read whatever's available). The Titans + Olympus RESCOPE that anchors this brief as Phase 1 of three sequenced builds.

**Approver:** Nick

---

## Purpose

`hub_get_options_chain` is built and pushed to feature branch `ship-hub-get-options-chain` (`557bda1`), awaiting a clean-load Greeks-verification smoke and a branch merge to `main`. Shipping it brings DAEDALUS from half-power ("qualitative-IV mode") to full power: per-contract Greeks (delta, gamma, theta, vega), IV rank, max pain, and the bid-ask-spread liquidity flag become available on every options pass — which lifts PIVOT's demote-only conviction cap on the most common trade type Nick runs.

The audit's original framing — "the smoke gate has never been run" — was **incorrect** and has been corrected on `origin/main`. The real history: the smoke fired 2026-05-27 ~15:14 ET and returned 0/497 contracts with non-null Greeks, but UW was at 102% of its daily 20K-call budget at that moment, and UW endpoints degrade *together* under load. So the prior result is contaminated by load, not by a real Greeks-absence on the production endpoint. Today's smoke is the **clean-load tiebreaker**, and a FAIL is only authoritative if UW daily load is confirmed low at the moment of the run.

Disposition: **ship as-is if the clean-load smoke PASSES; v1.5 revert if it FAILS at confirmed-low load.** ~1h end-to-end (excluding RTH wait).

This brief covers Phase 1 ONLY. `hub_get_chart_indicators` (PYTHAGORAS, ~6–8h) and `hub_get_market_profile` (PYTHIA, ~12–20h) are gated behind UW-overdraw headroom confirmation (A.4b/A.4c) and get their own briefs.

---

## Handoff State (what the laptop CC did; what desktop CC inherits)

**Pushed to `main`** (`2939476` → `414f7e4`):
- `docs/codex-briefs/a4a-uw-overdraw-handoff-2026-05-27.md` — the smoke-failure-under-load handoff doc.
- `docs/codex-briefs/tv-mcp-cost-benefit-analysis.md` — expanded from stub.
- 3 `pythia-market-profile-*` files — supporting docs for the deferred Phase 3 PYTHIA build (out of scope for this brief).
- `docs/uw-mcp-committee-integration-audit-brief-2026-05-27.md` (`98ee561`, was sitting unpushed) — now on `main` with dated correction block in Part B replacing the "smoke never ran" claim with the real 05-27 failure-under-load history.

**Pushed to feature branch `ship-hub-get-options-chain`** (`557bda1`):
- `backend/hub_mcp/tools/options_chain.py` (new, ~127 LoC)
- `backend/services/read_only/options_chain.py` (new, ~371 LoC)
- `backend/utils/options_math.py` (new, ~121 LoC)
- `scripts/options_chain_greeks_smoke.py` (new, ~132 LoC — **smoke criterion already tightened to ATLAS M1: 5 ATM strikes both sides, non-null delta + IV**)
- `backend/hub_mcp/tools/__init__.py` (modified — adds `options_chain` import)
- `backend/hub_mcp/decorators.py` (modified — adds `"hub_get_options_chain"` to `REGISTERED_TOOL_NAMES`)

**Why a branch and not `main`:** keeps Railway from auto-deploying an untested Greeks tool before the smoke clears. Permanently resolves the "untracked files trapped on one laptop" hazard that gave us the 121-commit drift problem. The branch IS the gate.

**Defensive smoke logic (note):** the tightened smoke now treats a null `spot` (or other load-degradation markers) as **inconclusive**, not a FAIL — surfaces this state to the operator rather than tripping the v1.5 revert by mistake. This is why we still need the explicit pre-smoke UW-load check (Task 2) in addition to the smoke's own defensive logic: belt + suspenders against the 05-27 confound recurring.

**Laptop state:** clean `main`. The only local changes left on the laptop are pre-existing RH/IBKR work that's not part of this brief.

---

## Pre-flight (mandatory)

1. **Working tree clean, on `main`, current.** From `C:\trading-hub`:
   ```cmd
   git fetch
   git status
   ```
   Confirm clean tree and `main` at or fast-forwardable to `origin/main` (`414f7e4` or later).

2. **Checkout the feature branch and verify the staged files.**
   ```cmd
   git checkout ship-hub-get-options-chain
   git log -1 --oneline
   ```
   Confirm HEAD is `557bda1` and the 6 expected files are present on this branch (4 new + 2 modified, listed in Handoff State above). If files are missing → STOP, surface to Nick.

3. **Read the predecessors in order** (especially the `a4a-uw-overdraw-handoff-2026-05-27.md` §3 — the smoke-failure-under-load context is what makes today's smoke a tiebreaker rather than a first attempt; without this context, an inconclusive result reads as a real FAIL).

4. **Confirm A.4a caller-tagging in the new service layer.** Every UW call path the options-chain service touches must pass an endpoint-grain `caller` tag (e.g., `caller="options_chain"`) to the `_uw_request` helper. The service was authored 05-26→05-27 around when A.4a landed; if any UW call is untagged, A.4a attribution is broken on this tool and that's an ATLAS data-integrity finding — fix before proceeding. If unsure, grep `backend/services/read_only/options_chain.py` for `caller=` and confirm coverage on every UW call.

5. **Read `PROJECT_RULES.md` at repo root.**

6. **Tooling discipline (PROJECT_RULES.md):** use **cmd** for all git operations on Windows. **No PowerShell for git.** PowerShell-git is a known-broken pattern and an ATLAS veto trigger.

If any pre-flight check fails, surface as the first line of output and do not proceed to Task 1.

---

## Tasks

### Task 1 — Verify the staged smoke criterion (~5 min, sanity check)

Open `scripts/options_chain_greeks_smoke.py` and confirm the pass criterion is the **ATLAS M1 tightened version**: "5 ATM strikes, both sides, must have non-null delta + IV." This was applied in `557bda1` per the laptop CC's Task 1; this step is just sanity confirmation. If the file still shows the looser "≥1 contract" criterion, the branch is wrong — STOP and surface.

### Task 2 — Confirm UW daily load is low BEFORE running smoke (new gate)

**This is the most important new gate in this brief.** Check UW daily budget consumption — early-session post-overnight reset is the cleanest window. The check can be done via the hub's overdraw instrumentation (Phase A.4a shipped this) or via UW's account dashboard directly.

- **Load is low (well below 20K/day cap):** proceed to Task 3.
- **Load is already near cap:** WAIT. Do not run smoke. A FAIL under high load is inconclusive (the 05-27 ~15:14 ET context — 0/497 Greeks at 102% load). Surface the wait condition to Nick with the current load reading.

### Task 3 — Run the smoke during live RTH at confirmed-low load

Trading day, ≥09:30 ET / 07:30 MT, immediately after the Task 2 check.

```cmd
python scripts\options_chain_greeks_smoke.py
```

Record the **UW daily load reading at the moment of the run** in the output — this is needed for the closure note and for any future Olympus or Titans review of the gate outcome.

Three possible outcomes:

- **PASS** (≥5 ATM strikes both sides return non-null delta + IV) → proceed to Task 4.
- **INCONCLUSIVE** (null `spot` or other load-degradation marker, per the smoke's defensive logic) → **do not ship, do not revert.** Surface to Nick with the load reading and the smoke output. Likely action: re-run later in the session when conditions are cleaner.
- **FAIL at confirmed-low load** (Greeks genuinely null when the endpoint is healthy) → v1.5 revert path (see below). Surface to Nick first; do not auto-revert.

### Task 4 — Merge branch to `main` and deploy (PASS only)

From `C:\trading-hub` on the branch:

```cmd
git checkout main
git pull
git merge ship-hub-get-options-chain --no-ff -m "feat(hub_mcp): ship hub_get_options_chain — DAEDALUS Greeks/IV/chain (Phase 1)"
git push origin main
```

`--no-ff` preserves the branch-as-gate history in the merge commit and ensures the specified commit message lands intact. Railway auto-deploys on push to `main`.

Verify deploy went up clean (Railway dashboard or logs). If deploy fails, do not proceed to Task 5 — surface and diagnose.

### Task 5 — Post-deploy registry verification

From a fresh Claude.ai session with Pandora MCP connected, call:

```
Pandora MCP:mcp_describe_tools
```

Confirm `hub_get_options_chain` appears in the returned tool list. This validates that the `decorators.py` + `__init__.py` registration loop is complete end-to-end (audit Q13).

If the tool does not appear, the registry didn't pick it up — likely a deploy issue or an import-time error. Diagnose before proceeding.

### Task 6 — DAEDALUS SKILL.md edit + bundle rebuild

Apply the SKILL.md edit per Task 2 schema doc lines 316–334:
- Replace the "qualitative-IV mode" caveat (current DAEDALUS SKILL.md lines 71–77) with the caveat-closed language specified in the schema doc.
- Insert the `hub_get_options_chain` tool call in the Context A list, **between `hub_get_flow_radar` and `hub_get_hydra_scores`** (the exact position is specified in the schema doc).

Then rebuild the bundle:

```cmd
scripts\package-skill.ps1 daedalus
```

*(Note: bundle packaging uses the project's PowerShell script — this is the documented exception to the "no PowerShell" rule and is fine.)*

**Nick re-uploads `daedalus.skill` to Claude.ai.** CC cannot perform the upload; flag this step for Nick in the closure note + summary.

### Task 7 — Olympus re-test (mandatory, see Olympus Impact below)

After Nick confirms the bundle re-upload, run **one full Olympus committee pass** on a known-good ticker (SPY or any active position with options exposure). Confirm:

1. DAEDALUS surfaces actual per-contract Greeks + IV rank, not the qualitative-mode caveat.
2. **Critically: nulls render as "unavailable," NOT fabricated values.** The 2026-05-21 TORO fabrication incident is the canonical lesson — committee behavior can degrade silently if upstream data assumptions shift. If any contract's Greek field comes back null and DAEDALUS invents a plausible-looking number, that's a regression that ships gets reverted, not patched.
3. PIVOT's conviction is no longer demoted by the DAEDALUS half-power cap on the test ticker.

Record the re-test ticker, the DAEDALUS output, and the PIVOT verdict in the closure note.

### Task 8 — Closure note

Write `docs/strategy-reviews/hub-get-options-chain-closure-note-2026-05-28.md` (or appropriate date) covering:
- Smoke pass evidence: the 5-ATM-strike contract list with delta + IV values
- UW daily load reading at moment of smoke run
- Merge commit SHA on `main`
- DAEDALUS SKILL.md diff (the lines 71–77 caveat-closure edit)
- Bundle hash + Nick's upload confirmation timestamp
- `mcp_describe_tools` verification output
- Olympus re-test result (ticker, DAEDALUS output excerpt, PIVOT verdict, null-handling confirmation)

Commit + push the closure note.

---

## v1.5 Revert Path (alternate — confirmed-low-load FAIL only)

Per Task 2 schema doc lines 394–405. **Surface the FAIL + load reading to Nick FIRST. Do not auto-execute the revert.** When Nick authorizes:

1. Remove the 4 Greeks fields (`delta`, `gamma`, `theta`, `vega`) from the response envelope of `backend/services/read_only/options_chain.py`.
2. Keep `implied_volatility` (the IV rank chain-level data is independent of per-contract Greeks).
3. Revert the planned DAEDALUS SKILL.md edit — keep the qualitative-Greeks-mode language in place (do not close the caveat).
4. Re-tighten the smoke or skip its Greeks-specific assertions (the chain itself still works, just without Greeks).
5. Merge branch to `main` with commit message `feat(hub_mcp): ship hub_get_options_chain v1.5 — IV-only, Greeks deferred (Phase 1)`.
6. Closure note documents the revert + the FAIL evidence + the load reading.
7. Tier-2 follow-up brief (Black-Scholes Greeks computation hub-side) becomes the next sequencing question — surface to ATHENA.

---

## Output Spec (deliverable artifacts)

On PASS:
- Branch `ship-hub-get-options-chain` (`557bda1`) merged to `main` via `--no-ff` with the specified commit message
- Railway deploy verified up
- `daedalus.skill` rebuilt; uploaded by Nick
- Closure note at `docs/strategy-reviews/hub-get-options-chain-closure-note-2026-05-XX.md`

On FAIL (confirmed-low-load):
- v1.5 changes per the revert path
- Branch merged with the v1.5 commit message
- Closure note documenting the FAIL + revert decision

On INCONCLUSIVE:
- No merge, no revert
- Surface to Nick with smoke output + UW load reading + recommended re-run window

---

## Gates / what NOT to do

- **Do NOT run the smoke outside live RTH.** Closed-market nulls are inconclusive (Memorial Day 2026-05-25 is the precedent).
- **Do NOT run the smoke if UW daily load is near cap.** A FAIL under high load is inconclusive — the 05-27 ~15:14 ET attempt at 102% load is exactly the confound this gate prevents.
- **Do NOT auto-revert on an INCONCLUSIVE smoke result** (null spot, load-degradation marker). Surface to Nick.
- **Do NOT merge to `main` without PASS.** The branch IS the gate; fast-forwarding around it defeats the architecture.
- **Do NOT ship Greeks fields if the smoke FAILS at confirmed-low load.** v1.5 revert is the path, and even then Nick approves first.
- **Do NOT do the `uw_api.py` dedupe refactor** (delete `_get_contract_mid` body, replace with `utils.options_math` import). Deferred — duplicate helpers are byte-identical so behavior is preserved (audit Q4). Schedule as a later cleanup brief.
- **Do NOT build `hub_get_chart_indicators` or `hub_get_market_profile`.** Separate, overdraw-gated briefs.
- **Do NOT add any of the ~9 enrichment wrappers** (spot-exposures, expiry-breakdown, term-structure, ownership, earnings-estimates, etf-tide, sector-tide, etc.). Dropped from scope per the dual review.
- **Do NOT use PowerShell for git operations** (PROJECT_RULES.md). cmd only. Exception: `scripts\package-skill.ps1` for bundle rebuild is the documented PowerShell exception.
- **Do NOT skip the post-deploy `mcp_describe_tools` check.** It validates the registration loop end-to-end.
- **Do NOT skip the Olympus re-test.** The TORO fabrication lesson is non-negotiable for any Olympus-skill-touching ship.
- **Do NOT upload `daedalus.skill` yourself** — CC cannot. Flag for Nick.

---

## Done-Definition

- [ ] Pre-flight: clean `main`, branch `ship-hub-get-options-chain` checked out at `557bda1`, 6 expected files present, A.4a caller-tagging confirmed, predecessor docs read (especially `a4a-uw-overdraw-handoff-2026-05-27.md` §3), `PROJECT_RULES.md` read
- [ ] Smoke criterion verified as ATLAS M1 tightened (5 ATM strikes both sides, non-null delta + IV)
- [ ] UW daily load confirmed low at moment of smoke run, reading recorded
- [ ] Smoke run during live RTH → outcome recorded (PASS / INCONCLUSIVE / FAIL-at-confirmed-low-load)
- [ ] On PASS: branch merged to `main` via `--no-ff` with specified commit message; Railway deploy verified up
- [ ] On FAIL-at-confirmed-low-load: Nick consulted; v1.5 revert path executed if authorized
- [ ] On INCONCLUSIVE: Nick consulted; no merge, no revert
- [ ] On PASS or v1.5: `mcp_describe_tools` confirms `hub_get_options_chain` is live in the registry
- [ ] DAEDALUS SKILL.md edited per schema doc lines 316–334 (caveat closed on PASS, retained on v1.5)
- [ ] `daedalus.skill` rebuilt via `scripts\package-skill.ps1 daedalus`; Nick notified for re-upload
- [ ] Olympus re-test passed on a known-good ticker: DAEDALUS surfaces real Greeks (PASS) or honest "unavailable" (v1.5); nulls render as "unavailable" NOT fabricated; PIVOT conviction cap lifted (PASS only)
- [ ] Closure note committed at `docs/strategy-reviews/hub-get-options-chain-closure-note-2026-05-XX.md`
- [ ] CC posts summary to Nick: smoke outcome + UW load reading, merge commit SHA, deploy status, mcp_describe_tools result, SKILL.md upload confirmation, Olympus re-test outcome

---

## Olympus Impact

**Skill touched:** DAEDALUS (one skill).

**Behavior change on PASS:** DAEDALUS exits qualitative-IV mode. Per-contract Greeks (delta, gamma, theta, vega), IV rank/percentile, max pain, and bid-ask-spread % become available in every options pass. PIVOT's demote-only conviction cap on options trades (one of the demote-only override rules) lifts on the DAEDALUS dimension.

**Behavior change on v1.5:** DAEDALUS retains qualitative-IV mode. IV rank and max pain become available; per-contract Greeks remain unavailable. PIVOT's demote-only cap remains in place but on narrower grounds.

**Mandatory post-ship re-test** (per `_shared/TITANS_RULES.md § Olympus Cross-Reference`):

The 2026-05-21 TORO fabrication incident is the standing lesson — committee agents can degrade silently when upstream data assumptions shift, and the only reliable detection is an explicit re-test on real data after any hub change that touches what they consume.

For this build specifically, the re-test must answer two questions:

1. **Does DAEDALUS surface real Greeks?** Run a full Olympus pass on SPY or an active options position; confirm DAEDALUS's output cites actual delta / gamma / theta / vega / IV rank values, not the qualitative-mode caveat language.

2. **Does DAEDALUS handle nulls honestly?** This is the critical fabrication check. Some contracts (deep OTM, illiquid expiries) may legitimately return null on individual Greeks. Confirm DAEDALUS renders these as "unavailable" or "data missing" — NOT as plausible-looking invented numbers. If it fabricates, the build gets reverted regardless of smoke PASS — fabricated Greeks are worse than honest unavailability.

Record both confirmations in the closure note with output excerpts.

---

## Notes for Desktop CC

- This is unblock-as-is, not a redesign. The architecture is reviewed (Titans Pass 1 + Pass 2 closed), the code is written (`557bda1`), and the smoke criterion is already tightened. Your job is the load-check gate, the smoke run, the merge, the registry verification, the SKILL.md edit, the bundle rebuild, the Olympus re-test, and the closure note. **Resist scope expansion.**
- The single most important context that's *not* in the original brief: the smoke history. Read `a4a-uw-overdraw-handoff-2026-05-27.md` §3 BEFORE deciding any smoke outcome. The 05-27 ~15:14 ET attempt at 102% load is exactly why we need the explicit load-check gate today.
- All UW data flows in this build go through `backend/integrations/uw_api.py` where A.4a caller-tagging lives. If you find any UW call in the new service that bypasses that — fix it. Untagged UW callers break overdraw attribution.
- Standard patterns per PROJECT_RULES.md: cmd for git, PowerShell exception only for `package-skill.ps1`.
- Low risk profile overall — the tool is read-only (1 UW call per invocation), the commit is reversible (revert the merge if needed), the SKILL.md edit is well-specified, the branch architecture means Railway can't auto-deploy until you explicitly merge.

---

**Estimated CC time:** ~1h active work (5 min smoke + 10 min merge/deploy/verify + 15 min SKILL.md edit/bundle + 5 min Olympus re-test orchestration + 15 min closure note + 10 min summary). Plus the live-RTH wait for the smoke window and the load-low confirmation.

**Brief drafted:** 2026-05-28 (desktop authoring after laptop CC handoff).
**Brief commit (TBD):** `docs(brief): ship hub_get_options_chain Phase 1 — desktop CC handoff revision`.
