# Committee Data Integrity Patch — Build Brief

**Date:** 2026-05-21 (afternoon, second build of the day)
**Author:** Olympus build chat (continuing from PIVOT skill build earlier today, commit `fd0419b`)
**Status:** Green-lit for CC execution. No Titans pass — scope decisions, not design.
**Target commit:** Single commit to main with conventional message format.

---

## Why this build exists

The 2026-05-21 7-agent committee validation pass on TSLA exposed two real bugs in the committee architecture. Both must be patched before the post-build cross-review can run meaningfully.

**Bug 1 (foundational): Web search returns stale price data with current-day timestamps.** The TSLA validation pass cited "today's low $406.39" — but that was May 20's low, not May 21's (May 21's actual low was ~$413). Multiple web sources display previous-trading-day OHLCV under current-date page timestamps, and nothing in the GROUND TRUTH discipline forces a data-date cross-check. Every directional agent's intraday narrative was built on the wrong day's tape.

**Bug 2 (logic): URSA + THALES bias-alignment flag counts directional positions without checking thesis coherence.** The validation pass classified seven positions as "macro-bearish bias stacking" when the actual book is a multi-leg Iran-escalation thesis with intentional long legs (XLE, CF) hedging short legs (growth/credit put spreads). A coherent multi-directional macro thesis is not bias-alignment.

Both bugs trigger false positives that PIVOT's Hard Gates trust. PIVOT's architecture (independent gates) is sound — DON'T TRADE verdict survives this incident on the DAEDALUS sizing gate alone — but the inputs feeding the synthesizer were corrupted.

---

## Build scope summary

1. **New hub MCP tool `hub_get_quote(ticker)`** — wraps UW's `/stock-state` endpoint. Returns real-time spot + OHLCV + UW server timestamp.
2. **`_shared/COMMITTEE_RULES.md` update** — `hub_get_quote` mandatory in Context A for any price-anchored output. Web_search for spot deprecated in Context A; tightened date-attribution discipline in Context B.
3. **All seven agent SKILL.md files updated** — `hub_get_quote` added to each agent's tool list.
4. **URSA + THALES thesis-coherence patch** — distinguish "thesis concentration" from "bias-alignment" before flagging.

Single commit. Single push. Then Nick re-packages all seven `.skill` files and uploads.

---

## Part 1 — New hub MCP tool: `hub_get_quote`

### Backend location

`backend/hub_mcp/` per the existing pattern. Add as the tenth tool in the existing read-only set. Same FastMCP wrapper pattern as the existing nine.

### UW endpoint to wrap

UW REST endpoint: `/stock-state` (kebab-case per UW convention). UW already serves this; bearer token auth already in Railway env vars. MCP tool name (snake_case per Nick's documented pattern): `hub_get_quote`.

### Tool signature

```python
hub_get_quote(ticker: str) -> dict
```

### Expected return schema

```json
{
  "ticker": "TSLA",
  "spot": 414.75,
  "prior_close": 417.26,
  "open": 416.50,
  "high": 418.42,
  "low": 413.10,
  "volume": 45290000,
  "avg_volume_30d": 57960000,
  "pct_change": -0.60,
  "wk52_high": 498.83,
  "wk52_low": 273.21,
  "market_state": "open",
  "source": "UW",
  "uw_timestamp": "2026-05-21T20:42:00Z",
  "status": "live"
}
```

Field definitions:
- `spot` — current price (last trade if market open, last close if closed)
- `prior_close` — close of the previous completed trading session
- `open`, `high`, `low` — current session intraday (if market open) or last session (if closed)
- `volume` — current session volume (or last session if closed)
- `avg_volume_30d` — 30-day average daily volume
- `pct_change` — percent change from prior_close
- `wk52_high`, `wk52_low` — 52-week range
- `market_state` — enum: `pre_market`, `open`, `post_market`, `closed`, `halted`
- `source` — always `"UW"` for this tool
- `uw_timestamp` — ISO 8601 UTC timestamp from UW server (THE critical field — agents must cite this in output)
- `status` — enum: `live`, `stale` (if UW response timestamp is >5 minutes old during market hours), `unavailable` (if UW errors or rate-limits)

### Error handling

- If UW returns an error or times out: `status="unavailable"`, all other fields null.
- If UW response timestamp is more than 5 minutes old during market open hours: `status="stale"`, fields populated with whatever UW returned.
- Never fabricate data. Never fall back to other providers (yfinance, polygon, FMP) — those are deprecated per project rules.

### Tests

Follow whatever test pattern the existing nine tools use. At minimum: one happy-path test (returns live data on a known liquid ticker), one error test (UW unreachable → status="unavailable"), one stale-data test (mock UW response with old timestamp → status="stale").

### Deployment

Standard Railway deploy from main. After push, verify the tool surfaces in `mcp_describe_tools` output.

---

## Part 2 — `_shared/COMMITTEE_RULES.md` updates

### Section to modify: § Pre-Output Data Checklist Framework

**Context A (Hub reachable) — add `hub_get_quote` as MANDATORY for price-anchored output**

Insert this rule into the Context A section, after the `mcp_ping` requirement, before the agent-specific tool lists:

> **Mandatory call for any price-anchored output:** `hub_get_quote(ticker)` MUST be called before any output that cites a specific spot price, intraday level, or anchors analysis to "today's" tape. The UW timestamp from the response MUST be cited in the DATA NOTE block at the end of the output. If `hub_get_quote` returns `status="unavailable"`, the agent cannot produce price-anchored analysis — degrade to qualitative framing only or wait for hub recovery. If `status="stale"`, surface the staleness in the DATA NOTE and degrade conviction by one notch.
>
> **Web search for spot price is DEPRECATED in Context A.** Agents must not call web_search for current price, today's range, or intraday levels when the hub is reachable. The hub's UW data is authoritative; web search introduces stale-data risk via page-refresh-timestamp confusion (the 2026-05-21 TSLA pass surfaced this failure mode explicitly).

**Context B (Hub unreachable) — tighten the GROUND TRUTH discipline**

Replace the existing GROUND TRUTH block specification with this tightened version:

> Mandatory GROUND TRUTH block at the top of every output:
>
> ```
> GROUND TRUTH (web_search fallback, hub unreachable):
> - [TICKER]: $XXX spot (source: [name], data date: YYYY-MM-DD HH:MM TZ)
> - Tape: SPX ±X.X%, Nasdaq ±X.X%, VIX ±X.X% (sources + dates per ticker)
> - Macro context: [one-sentence summary]
> ```
>
> **Date-attribution requirements (hard rule):**
> - Every price citation must include the data DATE explicitly, not the page-refresh timestamp.
> - Cross-source consistency check: if two sources show the same numbers but different date stamps, that is a red flag — the data is likely from a previously-completed session being served under current-date cache headers. Verify with at least one source that explicitly shows real-time updating.
> - If intraday data is required and no source can be verified as fresh within the last 30 minutes during market hours, frame qualitatively only — no precision levels, no "today's low" claims, no anchored entries/stops.
> - If the data date can only be verified as "previous trading session," the agent must explicitly say so in output and frame all analysis as based on the last completed session, not "today."

### Section to modify: § Shared Hard Rules

Add this rule to the existing list:

> - Never cite a current spot price, intraday level, or today's range without either (a) `hub_get_quote` result with UW timestamp (Context A) or (b) a fully date-verified web source per the Context B GROUND TRUTH discipline. Web pages displaying yesterday's data under today's page-refresh timestamp are a known failure mode — date attribution on the data itself is mandatory.

---

## Part 3 — All seven agent SKILL.md updates

Each agent's `Pre-Output Data Checklist` section currently lists its agent-specific MCP tools. Add `hub_get_quote(ticker)` to each list as the FIRST call after `mcp_ping`, before any other agent-specific tool. Rationale: every agent except possibly THALES (when sitting out) anchors to spot price at some point in its output; the quote must be fetched before any downstream call uses it.

### Files to update

```
skills/toro/SKILL.md
skills/ursa/SKILL.md
skills/pythia/SKILL.md
skills/pythagoras/SKILL.md
skills/daedalus/SKILL.md
skills/thales/SKILL.md
skills/pivot/SKILL.md
```

For each file:
1. Locate the `## § Pre-Output Data Checklist` (or equivalent) section.
2. Find the agent's MCP tool list under Context A.
3. Insert `hub_get_quote(ticker)` as the first item after `mcp_ping`.
4. Add a sentence: "The UW timestamp from `hub_get_quote` is the authoritative anchor for all price-anchored claims in this agent's output."

For PIVOT specifically (`skills/pivot/SKILL.md`):
- Add `hub_get_quote` to PIVOT's tool list as well — PIVOT needs the quote to verify sizing math against accurate spot. Already calls `hub_get_portfolio_balances` and `hub_get_positions`; add `hub_get_quote` before these.

---

## Part 4 — URSA + THALES thesis-coherence patch

### Problem statement

Both agents currently check portfolio coherence by reading positions from `hub_get_positions` and counting directional exposure. If they see ≥5 positions on the same directional side, both flag bias-alignment. This logic fires false positives on coherent multi-leg macro theses.

The 2026-05-21 TSLA pass surfaced the canonical example: Nick's book contains XLE long (energy), CF long (ag/fertilizer), and seven put spreads on growth/credit names. URSA and THALES both classified this as "macro-bearish bias stacking." Actual structure: an Iran-escalation thesis where the long legs (energy, ag) intentionally hedge or amplify the short legs (growth compression, credit stress). Multi-directional by design.

### Fix: thesis-coherence pre-check before bias-alignment flag

Both URSA and THALES SKILL.md files need a new step in their portfolio-analysis logic. Before flagging bias-alignment, the agent must:

1. **Read all positions** from `hub_get_positions` (existing step, unchanged).
2. **Enumerate inferred thesis groupings** — group positions by the underlying macro thesis they appear to express, not by directional label. Common groupings to recognize:
   - **Iran-escalation thesis:** Long energy (XLE, USO, oil-equity), long ag (CF, MOS, food), short consumer discretionary (XLY), short high-multiple growth, short credit (HYG)
   - **AI-bubble-deflation thesis:** Short AI names (IGV, software), short semis, short hyperscaler infrastructure
   - **Fed-hawkish thesis:** Short long-duration (TLT puts), short rate-sensitive (XLF puts, REITs), long short-duration cash equivalents
   - **Pure macro-bearish bias stack:** Broad short index, no offsetting long structure, no thematic coherence
3. **Classification:**
   - If positions span multiple directions tied to a single coherent thesis → **THESIS CONCENTRATION** (not a bias flag — note thesis name in output, evaluate execution quality not bias)
   - If positions cluster on single direction with NO hedging long structure AND no coherent narrative tying them together → **BIAS-ALIGNMENT** (flag fires)
4. **If THESIS CONCENTRATION is the correct classification:** the agent does NOT flag bias-alignment, but it MUST evaluate execution quality:
   - Are the legs that should be working (per the thesis) actually working? (E.g., for Iran-escalation: is XLE up? is CF holding?)
   - Are the bleeding legs bleeding because the THESIS is wrong, or because TIMING/SIZING/STRUCTURE was wrong?
   - Surface this as a distinct finding: "thesis appears intact but execution on [specific legs] is failing — investigate timing/sizing/structure."

### Output format change for URSA

Add a new sub-block under URSA's PORTFOLIO COHERENCE section:

```
THESIS GROUPING:
- [thesis name]: [positions in this group]
- [classification: THESIS CONCENTRATION | BIAS-ALIGNMENT | NEUTRAL]

EXECUTION QUALITY (if THESIS CONCENTRATION):
- Winning legs: [legs that are working as the thesis predicts]
- Bleeding legs: [legs that are not working]
- Read: [thesis intact + execution failing | thesis appears wrong | mixed]
```

### Output format change for THALES

THALES's macro lens reads this differently — THALES looks for whether the WORLD supports the thesis, while URSA looks at whether the BOOK is coherent. Both must agree on classification before the bias dual-flag fires.

Add to THALES's output (when bias-alignment is being considered):

```
THESIS WORLD-CHECK:
- Macro environment supports [thesis name]: [YES / NO / PARTIAL]
- Specific catalysts aligned with thesis: [list]
- Specific catalysts contradicting thesis: [list]
- Read: [thesis remains macro-coherent | thesis is fading | thesis was always bias-dressed-as-thesis]
```

### Effect on PIVOT's bias-alignment Hard Gate

PIVOT's Hard Gate logic is UNCHANGED. It still fires when both URSA and THALES flag bias-alignment. But the bar for flagging is now higher — both agents must first rule out thesis-coherent multi-leg structure. A coherent thesis with execution problems is NOT a bias-alignment finding.

This means PIVOT's bias gate will fire less often, which is the correct behavior. False-positive reduction without weakening true-positive detection.

---

## Implementation steps for CC

1. `cd C:\trading-hub && git fetch && git status` — verify clean main branch (cross-machine drift risk per PROJECT_RULES.md). If laptop is behind, sync first.

2. **Build the `hub_get_quote` MCP tool:**
   a. Add to `backend/hub_mcp/` following the existing nine-tool pattern.
   b. Wrap UW's `/stock-state` endpoint with bearer-token auth pulled from Railway env vars (same auth path as existing UW calls).
   c. Implement the return schema in Part 1 exactly.
   d. Implement error handling per Part 1.
   e. Add tests following the existing test pattern.
   f. Verify via local FastMCP test run if possible, otherwise rely on Railway deploy verification.

3. **Deploy backend to Railway:**
   a. Commit + push (interim commit OK if needed for Railway autodeploy to pick up).
   b. After deploy, hit `mcp_describe_tools` and verify `hub_get_quote` is listed.
   c. Call `hub_get_quote("TSLA")` against the live MCP and confirm it returns a populated response with current UW timestamp.

4. **Update `skills/_shared/COMMITTEE_RULES.md`:**
   a. Add the Context A mandatory-call rule for `hub_get_quote` per Part 2.
   b. Tighten the Context B GROUND TRUTH block per Part 2.
   c. Add the new Shared Hard Rule per Part 2.

5. **Update all seven `skills/{agent}/SKILL.md` files** per Part 3 — add `hub_get_quote` to each tool list, add the UW-timestamp anchoring sentence.

6. **Patch URSA + THALES `SKILL.md` files** per Part 4:
   a. URSA — add THESIS GROUPING and EXECUTION QUALITY sub-blocks; add thesis-coherence pre-check before bias-alignment flag fires.
   b. THALES — add THESIS WORLD-CHECK sub-block; require thesis-coherence pre-check before bias-alignment flag fires.

7. **Sanity-check read** of all eight modified skill files (seven agents + COMMITTEE_RULES.md). Confirm:
   - No hardcoded account balances introduced anywhere.
   - All `hub_get_quote` additions are consistent in wording.
   - URSA and THALES thesis-coherence patches use the same classification labels (THESIS CONCENTRATION, BIAS-ALIGNMENT, NEUTRAL).

8. **Single commit + push** with the commit message template below.

9. **Re-package skills** — run `scripts/package-skill.ps1` for each of the seven agents. Confirm all seven `.skill` files are produced under `dist/skills/`.

10. **Report back:**
    - Commit SHA
    - Railway deploy confirmation (or note if Railway needs re-deploy)
    - Confirmation that `mcp_describe_tools` lists `hub_get_quote`
    - Confirmation that `hub_get_quote("TSLA")` returns live data with UW timestamp
    - Confirmation that all seven `.skill` files re-packaged successfully

### Commit message template

```
feat(committee): hub_get_quote MCP tool + data integrity patches

- New hub MCP tool: hub_get_quote(ticker) wrapping UW /stock-state.
  Returns real-time spot, OHLCV, UW timestamp. Tenth tool in the
  read-only hub MCP set.
- _shared/COMMITTEE_RULES.md: hub_get_quote mandatory in Context A
  for price-anchored output. Web search for spot deprecated in
  Context A. Context B GROUND TRUTH block tightened with mandatory
  date-attribution discipline.
- All 7 agent SKILL.md files: hub_get_quote added to tool lists,
  UW timestamp anchoring required for price-anchored output.
- URSA + THALES SKILL.md: thesis-coherence pre-check before
  bias-alignment flag. Distinguishes THESIS CONCENTRATION
  (coherent multi-leg macro thesis) from BIAS-ALIGNMENT
  (single-direction stack with no hedging structure).

Fixes two bugs surfaced in 2026-05-21 TSLA validation pass:
(1) Web search stale-data with current-date timestamps caused
    agents to anchor intraday narrative to wrong day's tape.
(2) URSA/THALES bias-flag counted directional positions without
    checking thesis coherence; false-positive on Iran-escalation
    multi-leg book.

Per build brief docs/codex-briefs/committee-data-integrity-patch-2026-05-21.md.
```

---

## Acceptance criteria

- `backend/hub_mcp/` contains a new `hub_get_quote` tool wrapping UW `/stock-state`. Tool returns the schema in Part 1, handles errors per Part 1, and has tests.
- Railway deploy succeeds and `mcp_describe_tools` lists `hub_get_quote` as the tenth tool.
- Live call to `hub_get_quote("TSLA")` returns a populated response with a UW timestamp from the current trading day.
- `skills/_shared/COMMITTEE_RULES.md` contains:
  - Context A mandatory-call rule for `hub_get_quote`
  - Tightened Context B GROUND TRUTH block with date-attribution requirements
  - New Shared Hard Rule on price-citation provenance
- All seven `skills/{agent}/SKILL.md` files list `hub_get_quote` in their Context A tool lists, positioned as the first call after `mcp_ping`, with UW-timestamp anchoring language added.
- URSA SKILL.md includes THESIS GROUPING and EXECUTION QUALITY sub-blocks. Thesis-coherence pre-check runs before bias-alignment flag.
- THALES SKILL.md includes THESIS WORLD-CHECK sub-block. Thesis-coherence pre-check runs before bias-alignment flag.
- All seven `.skill` files re-package successfully under `dist/skills/` with the new tool calls present in the bundled SKILL.md files.
- No hardcoded account-balance dollar amounts introduced anywhere.

---

## Post-build next steps (not CC's responsibility)

After CC reports the push and Railway deploy:

1. Nick uploads all seven re-packaged `.skill` files to Claude.ai (replacing the previous versions for the six already uploaded, plus first upload of PIVOT).
2. Fresh 7-agent committee validation pass on a current ticker — confirm:
   - `hub_get_quote` fires in Context A and the UW timestamp shows in DATA NOTE
   - Date-attribution discipline holds in Context B if the hub is unreachable for any reason
   - URSA + THALES correctly classify the book as THESIS CONCENTRATION (Iran-escalation), NOT bias-alignment
   - PIVOT's bias-gate does NOT fire on the same book that triggered it in the 2026-05-21 pass
3. Post-build committee cross-review kicks off as the next workstream — 7-agent peer review of each other's SKILL.md files.
4. After cross-review closes out, the v2 hub MCP work continues: `hub_get_chart_indicators` (PYTHAGORAS full power), `hub_get_options_chain` (DAEDALUS full power), `hub_get_market_profile` (PYTHIA full power).

---

## End-of-brief notes

- This build patches data integrity at the SOURCE (the hub MCP), not the discipline workaround (tightening web_search rules). The Context B web_search discipline is still tightened as a fallback, but Context A is now the default for any price-anchored output. This is the architectural correct fix.
- The thesis-coherence patch is contained to URSA + THALES. PIVOT's logic is unchanged — it still fires the bias Hard Gate when BOTH agents flag, but the upstream bar for flagging is higher. False-positive reduction without weakening true-positive detection.
- After this build ships and validates, the committee will have ten hub MCP tools, real-time UW data anchoring all price-sensitive output, and thesis-aware portfolio coherence analysis. That's a meaningful capability jump.
