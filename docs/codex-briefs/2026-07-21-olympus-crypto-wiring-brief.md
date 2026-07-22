# BRIEF — OLYMPUS-CRYPTO-WIRING

**Authored:** 2026-07-21, coordination lane
**Type:** skill-file edits. No backend code, no migrations, no deploys.
**Origin:** HUB-MCP-CRYPTO-STATE Phase 3 handback (tool `9038164`, docs `6332f0a`).
**Blocking:** `hub_get_crypto_state` is live and deploy-verified but **inert** — no agent's tool list names it, so no agent will call it.
**Titans review:** not required. Skill-file content edits, no production surface.

---

## TASK 0 — FILING

```
cd /d C:\trading-hub
git fetch origin && git status
git mv 2026-07-21-olympus-crypto-wiring-brief.md docs\codex-briefs\
git add docs/codex-briefs/2026-07-21-olympus-crypto-wiring-brief.md
git commit -F C:\temp\commitmsg.txt
git push origin main
```

---

## THE LOAD-BEARING PART — READ THIS FIRST

**A shared rule and the new tool's contract are in direct conflict, and shipping the tool list without fixing it makes every crypto committee pass worse, not better.**

`skills/_shared/COMMITTEE_RULES.md` (line ~23):

> *"If ANY MCP tool returns `status="unavailable"` or `status="stale"`, append a DATA NOTE block at the end of the output naming which tool failed and degrade conviction by one notch per missing input."*

`hub_get_crypto_state` reports **top-level status = WORST across blocks** — correct design, matching the `hub_get_stable_rates_fx` precedent. But COMMITTEE_RULES was written when every tool carried a single status.

**The collision:** FARTCOIN's cycle row lags ~3.2h → top-level `stale`. Or a deploy restarts the in-process writers → tape-health `degraded` for ~2 minutes → top-level `degraded`. In both cases funding, OI, basis, and liquidations are healthy — and every agent that called the tool docks conviction anyway.

**It compounds.** Six agents each read top-level `degraded` from one stale sub-block, each degrade a notch, then PIVOT synthesizes six degraded verdicts into a low-conviction call on data that was fine.

**The tool is right. The rule reading it needs one clause.** Fix this in Task 1 before touching any agent file.

---

## PHASE 0 — LOCATE ANCHORS BEFORE EDITING

This brief specifies **content**, not exact anchors — the coordination lane has not read all seven agent files and will not invent line targets it cannot see.

1. Read `skills/_shared/COMMITTEE_RULES.md`. Report the exact surrounding text of the degrade-conviction rule (~line 23).
2. For each of the seven agents — **TORO, URSA, PYTHAGORAS, PYTHIA, DAEDALUS, THALES, PIVOT** — locate the Context A MCP tool list in its `SKILL.md`. Per COMMITTEE_RULES line 21 these lists are agent-specific and each begins with `mcp_ping` then `hub_get_quote`. Report the exact anchor text per agent.
3. Report whether any agent **already** references `hub_get_crypto_quote` or `hub_get_crypto_market_profile` — that reveals the established crypto-tool formatting to match.

**If any agent's file structure differs materially from the above, report and stop.** Do not improvise a placement.

---

## TASK 1 — COMMITTEE_RULES AMENDMENT (do first)

Add to the degrade-conviction rule. Content, to be phrased in the file's existing voice:

> **Multi-block tools.** Some tools (`hub_get_crypto_state`, `hub_get_stable_rates_fx`) return independently-timed sub-blocks, each with its own status, and roll the TOP-LEVEL status up to the WORST block. For these, the conviction penalty applies **only when the block the agent actually used is degraded, stale, or unavailable** — not on the top-level rollup. A healthy block behind a degraded sibling is still a healthy input. Always name the specific block in the DATA NOTE, never just the tool. Never read a value out of a block whose own status is `degraded` or `unavailable`.

---

## TASK 2 — PER-AGENT TOOL-LIST ADDITIONS

Add `hub_get_crypto_state(symbol)` to all seven Context A lists, positioned **after** `hub_get_crypto_quote` — the quote is the price anchor per COMMITTEE_RULES line 17 and must be called first.

Per-agent framing, matching each file's existing style:

| Agent | Blocks in their lane | One-line framing |
|---|---|---|
| **DAEDALUS** | funding, open_interest, basis, liquidations | Primary crypto positioning tool. Funding + basis = the carry read; OI divergence = positioning build or unwind; liquidations = forced-flow context. His crypto equivalent of `hub_get_options_chain` |
| **THALES** | regime, cta_zone, basis | Regime and CTA-zone classification are his macro read on crypto. Basis is the term-structure/carry signal |
| **PYTHIA** | tape_health, session, regime | Spot-led vs perp-led IS an auction-participation read — who is actually transacting versus who is levered. Session partition (ASIA/LONDON/NY) contextualizes her profile levels |
| **URSA** | liquidations, funding, open_interest | Cascade risk and crowded positioning. Negative funding with rising OI is a crowded short; heavy liquidations are the tell for a forced move already underway |
| **TORO** | funding, open_interest | Negative funding = crowded shorts = squeeze fuel. The bull-case counterpart to URSA's read on the same blocks |
| **PYTHAGORAS** | — (**warning only**) | **`atr` is NOT served by this tool.** It returns `available=false` and is excluded from the health rollup. For crypto stop distance, fall back to `hub_get_crypto_market_profile` session high/low or a chart screenshot. **Never fabricate a crypto ATR** |
| **PIVOT** | block health, all | Check per-block status before synthesis and before any sizing. Do not degrade the whole pass on a top-level rollup — read the blocks the other agents actually used |

---

## TASK 3 — SHARED DISCIPLINE LINES

Add to each agent alongside the tool entry (or once in COMMITTEE_RULES if the file's structure suits it better — CC's call, report which):

1. **Hourly vintage.** `funding`, `open_interest`, `basis`, and `liquidations` come from the cycle engine's hourly snapshot. **Suitable for positioning and regime context; NOT for intraday timing or B3 scalp triggers.** Liquidations especially — an hourly snapshot can miss a cascade that fired and resolved between samples.
2. **Never call `hub_get_quote` bare** for BTC, ETH, SOL, HYPE, ZEC, or FARTCOIN. It returns an equity/ETF collision. Use `hub_get_crypto_quote`.
3. **No inferred scores.** `regime` and `cta_zone` are labeled engine classifications, not numbers. Never convert them to a score, and never infer the −45..+35 Market Structure Filter value — it is deliberately not exposed.
4. **Known coverage gap:** FARTCOIN's cycle row lags materially behind its regime and tape blocks. Expect per-block divergence on that symbol; it is correctly reported, not a bug.

---

## VERIFY

1. All seven `SKILL.md` files updated; COMMITTEE_RULES amended.
2. `scripts\package-skill.bat` runs clean for each of the seven.
3. No backend changes — `git diff --stat` touches only `skills/` and `docs/`.
4. Suite unchanged: **18f / 510p / 1s / 200e** byte-identical (skill files are not code, so any movement means something else was touched).

---

## HAND BACK

CC stops after commit. Remaining steps are Nick's and the coordination lane's:

| Step | Owner |
|---|---|
| Package + upload all seven `.skill` files | **Nick** |
| Toggle Pandora connector | **Nick** |
| Fresh chat → crypto committee pass on BTC or ETH | coordination lane |

**Post-pass fabrication check** — per the TORO precedent, verify specifically that: no agent asserts an ATR value for crypto; no agent cites a value from a block whose own status was `degraded`; no agent converts `cta_zone` or `regime` into a number; PIVOT degrades on block status, not the top-level rollup.

---

## KNOWN REMAINING GAP — NOT IN SCOPE, BUT SAY IT PLAINLY

**The committee can now READ crypto. It still cannot SIZE crypto.**

`hub_get_portfolio_balances` returns four accounts — robinhood, fidelity 401a, fidelity 403b, fidelity roth — and **`breakout_prop` is absent entirely.** That is the only account structurally able to hold a crypto position. DAEDALUS has a standing sizing veto on exactly this basis.

So after this brief lands, a crypto committee pass can produce a full positioning read and still cannot produce a sizing recommendation. **Closing that is the reconciliation apply (rulings locked 2026-07-18, dry-run at `c7df849`) plus the `breakout_prop` fake-healthy fix (Tier 1 #3)** — the recommended next build, tracked separately.

Data visibility and actionability are two different unlocks. This brief delivers the first.
