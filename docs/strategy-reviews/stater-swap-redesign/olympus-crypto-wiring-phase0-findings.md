# OLYMPUS-CRYPTO-WIRING — Phase 0 findings

**Brief:** `docs/codex-briefs/2026-07-21-olympus-crypto-wiring-brief.md`
**Executed:** 2026-07-21. **Task 1 shipped (`cd2cf83`). Tasks 2/3 STOPPED at the Phase 0 gate.**
**Reason:** the agent-file structure differs materially from the brief's placement model, and the brief says explicitly: "If any agent's file structure differs materially, report and stop. Do not improvise a placement."

---

## Task 1 — DONE (`cd2cf83`)

COMMITTEE_RULES degrade-conviction rule confirmed verbatim at line 23. Added the
multi-block clause in the file's voice: penalize the specific block the agent
used, never the top-level worst-of-blocks rollup; name the block in the DATA
NOTE; never read a value from a degraded/unavailable block. Suite byte-identical
(18f/510p/1s/200e). This fix stands regardless of how Tasks 2/3 resolve.

---

## Phase 0 anchors (as the brief requested)

### COMMITTEE_RULES.md
- Degrade-conviction rule: **line 23**, exactly as the brief quoted.
- Line 21: "Each agent's own `SKILL.md` lists the specific MCP tools it calls in
  Context A ... `hub_get_quote` is the first data-tool call after `mcp_ping`."

### The seven agents' Context A tool lists (SKILL.md)
Each has a numbered "specific tool calls (Context A)" list beginning with
`hub_get_quote`. **These lists are EQUITY-ONLY.** No crypto tool appears in any
of them.

| Agent | Context A list anchor (SKILL.md line of item 1) |
|---|---|
| TORO | 61 |
| URSA | 85 |
| PYTHAGORAS | 65 (item 2 = `hub_get_chart_indicators` at 66) |
| PYTHIA | 65 |
| DAEDALUS | 63 (list at 61–68) |
| THALES | 113 |
| PIVOT | 48 |

### Where crypto tools actually live
Not in the Context A lists — in **`references/crypto.md`**, loaded per the
asset-class routing line in each SKILL.md ("Crypto → `references/crypto.md`").
All seven exist (incl. DAEDALUS). These already list the crypto MCP tools under a
"What's real now" / "Currently Available Crypto Tooling" section:

- `hub_get_crypto_quote` and `hub_get_crypto_market_profile` appear in TORO, URSA,
  PYTHIA (MP only), THALES (MP only), PYTHAGORAS (MP only), PIVOT.
- Raw endpoints referenced: `/api/crypto/regime`, `/api/crypto/tape-health`,
  `/api/crypto/cycle-extremes`, `/api/crypto/clock`.

**So the brief's anchor "positioned after `hub_get_crypto_quote`" points into
`references/crypto.md`, not the Context A SKILL.md list.** The brief conflated
the two surfaces.

---

## Why Tasks 2/3 stopped — three material divergences

### 1. Crypto tools are not in the Context A lists at all
The brief's model is "add after `hub_get_crypto_quote` in each Context A list."
`hub_get_crypto_quote` is not in any Context A list. Placing `hub_get_crypto_state`
in the equity numbered list would put a crypto tool in the AAPL/SPY flow and
contradict the codebase's equity(SKILL.md)/crypto(references/crypto.md)
separation. The correct home is `references/crypto.md` — but that changes the
edit from "one line in a tool list" to "reconcile a stubbed playbook," which
raises #2 and #3.

### 2. DAEDALUS's ratified mandate contradicts his assigned role
The brief's Task 2 table makes **DAEDALUS the PRIMARY crypto-positioning agent**
("His crypto equivalent of `hub_get_options_chain`", reading
funding/OI/basis/liquidations). But DAEDALUS's own files say the opposite, and
say it deliberately:
- `daedalus/SKILL.md:51`: "DAEDALUS does NOT recommend options structures on
  crypto ... outside DAEDALUS's lane."
- `daedalus/references/crypto.md`: "the structural questions belong to PYTHIA ...
  the directional questions belong to TORO/URSA."
- `pivot/references/crypto.md`: "the DAEDALUS framework does NOT change
  (Breakout Prop still has no options venue)."

Making DAEDALUS the primary crypto-positioning reader reverses a ratified,
cross-referenced persona boundary. That is a committee-design decision, not a
tool-list placement — I will not make it unilaterally. (The funding/OI/basis/liq
blocks may fit URSA/TORO's existing crowded-positioning lanes more naturally than
DAEDALUS's — but that reassignment is the coordination lane's call.)

### 3. Stale content the new tool contradicts + the stub/methodology guard
- TORO and URSA `references/crypto.md` both say: "`/api/crypto/tape-health` —
  Currently `NA:SPOT_FEED_UNAVAILABLE` for all symbols ... do not treat this
  field as a real read until [S-3b] lands." **S-3b landed; `hub_get_crypto_state`
  now serves spot/perp CVD.** Adding the tool beside that text is directly
  contradictory — the stubs need reconciling, not just appending.
- Those files reference raw endpoints (`/api/crypto/regime`, `/tape-health`)
  that `hub_get_crypto_state` now supersedes via MCP — leaving both creates two
  ways to read the same thing.
- The brief's per-agent framings ("funding + basis = the carry read", "negative
  funding = crowded shorts = squeeze fuel") are crypto **methodology**.
  `PROJECT_RULES.md` and every one of these stubs say crypto playbooks stay
  stubbed and methodology must come from Nick's strategy work, "not general LLM
  pretrained priors." Writing those framings into the stubs brushes against that
  rule and should be Nick's/coordination-lane's explicit call, not CC's.

---

## Recommendation (for the coordination lane's decision)

The tool wiring is worth doing; the placement and framing need re-targeting.
Suggested path, pending your ruling:

1. **Wire into `references/crypto.md`, not the Context A SKILL.md lists** — that
   is where the sibling crypto tools already live and where asset-class routing
   sends crypto passes. Add `hub_get_crypto_state` to each "What's real now /
   Currently Available Crypto Tooling" section.
2. **Reconcile, don't just append**: update the now-false tape-health
   "NA:SPOT_FEED_UNAVAILABLE" note (TORO/URSA) and point the regime/tape reads at
   the MCP tool that supersedes the raw endpoints.
3. **Re-decide the DAEDALUS assignment.** Either keep DAEDALUS out of crypto
   positioning (my lean, matching his ratified mandate) and route funding/OI/
   basis/liq to URSA (cascade/crowding) and TORO (squeeze fuel) — both already
   own that lane in their stubs — or explicitly ratify a DAEDALUS mandate change.
4. **Confirm the methodology framings are Nick-authored** (or reduce them to
   pure tool-capability descriptions, no directional-read methodology) to stay
   inside the PROJECT_RULES "stubs stay stubbed" guard.
5. PYTHAGORAS warning-only (ATR not served) is clean and uncontested — that one
   can go in as-is once the placement question is settled.

Give me the ruling and I'll execute in one pass. Task 1 already protects every
agent from the compounding-conviction bug in the meantime.
