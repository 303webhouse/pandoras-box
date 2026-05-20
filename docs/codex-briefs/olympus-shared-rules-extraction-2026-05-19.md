# Brief: Olympus Shared Rules Extraction (2026-05-19)

**Scope:** Pure refactor. Extract the architectural sections that are duplicated across TORO, URSA, and PYTHIA skill files into a single shared reference at `skills/_shared/COMMITTEE_RULES.md`. Update each agent's SKILL.md to reference the shared file instead of duplicating the content. Zero change to agent behavior, persona content, or analytical framework. Zero new features.

**Why this matters:** As of 2026-05-19 with three agents shipped (TORO, URSA, PYTHIA), the duplicated architectural sections add up to ~40-60 lines per skill — Context A/B Pre-Output Data Checklist framing, Scope Boundary pattern, Account Context pattern, Knowledge Architecture, Committee Coordination, and several Hard Rules. With four more agents coming (PYTHAGORAS, DAEDALUS, THALES, PIVOT), continuing the duplication creates a 7-way diff problem when something needs to update (e.g., a new MCP tool, a new account, a refined fabrication rule). Extracting now means PYTHAGORAS / DAEDALUS / THALES / PIVOT inherit clean shared content; updates land in one file and propagate; drift risk drops to near zero.

**Architectural promise:** Anything in `skills/_shared/` is binding on every committee agent. Anything in an agent's own SKILL.md is agent-specific. This split has to be sharp and visible — the brief includes a self-check at the end to confirm.

**Estimated CC effort:** 2-3 hours. Pure read-existing-content / move-to-new-location / update-references work. No new copy needs to be written.

---

## Pre-Flight

```
cd C:\trading-hub
git fetch
git status
```

Confirm working tree is clean. Confirm HEAD includes PYTHIA shipped (`025d7dd` per Nick's update).

Read the three current skill files BEFORE writing anything:
- `skills/toro/SKILL.md`
- `skills/ursa/SKILL.md`
- `skills/pythia/SKILL.md`

The shared content lives in those files. CC's job is to identify the duplicated content (the brief specifies which sections), move it to the new shared file, and update each skill to reference the shared file with one-line pointers.

---

## Deliverables Summary

1. **New file `skills/_shared/COMMITTEE_RULES.md`** — single canonical location for all shared architectural patterns. The content for this file comes ENTIRELY from existing TORO/URSA/PYTHIA SKILL.md files; no new copy needs to be written.
2. **Updated `skills/toro/SKILL.md`** — duplicated sections replaced with one-line pointers to the shared file; TORO-specific content preserved verbatim.
3. **Updated `skills/ursa/SKILL.md`** — same treatment.
4. **Updated `skills/pythia/SKILL.md`** — same treatment.
5. **Re-package all three via `scripts\package-skill.bat all`** — `dist/skills/toro.skill`, `dist/skills/ursa.skill`, `dist/skills/pythia.skill` rebuilt.
6. **`scripts/package-skill.bat` (or `.ps1`) updated if needed** — each `.skill` archive MUST include `_shared/COMMITTEE_RULES.md` so the skill is self-contained when uploaded to Claude.ai. CC verifies this is handled correctly; if the packaging script doesn't already pick up the shared file, update it to do so.

---

## What Goes Into `skills/_shared/COMMITTEE_RULES.md`

The new shared file contains these sections, sourced from existing TORO/URSA/PYTHIA SKILL.md files. Use TORO's wording as canonical for any text that appears in all three (TORO is the original; URSA and PYTHIA inherited from it).

### Section 1: Pre-Output Data Checklist Framework

The Context A vs Context B intro paragraph and structure. Specifically:

- The opening paragraph describing the two contexts (hub MCP reachable vs Claude.ai chat with web_search fallback)
- The Context A intro: "The Pandora's Box hub MCP server is the authoritative data source. Begin by calling `mcp_ping` to confirm connection state..."
- The Context B GROUND TRUTH block format (verbatim)
- The web_search verification mandate
- The error-handling rules ("if any MCP tool returns `status='unavailable'` or `status='stale'`, append a DATA NOTE block...")

Each agent's SKILL.md will still list its OWN MCP tool calls (TORO calls 7 tools; URSA calls 7 with portfolio coherence emphasis; PYTHIA calls 3). Those tool lists stay in each agent's own file. What moves to shared is the FRAMEWORK around those lists.

### Section 2: Scope Boundary Pattern

The boilerplate Scope Boundary paragraph that appears (with minor agent-name variations) in all three skills:

> "<AGENT> produces ONLY the <AGENT> output block. Do not simulate <OTHER AGENTS> — each speaks for itself when installed. If a committee pass is requested and only <AGENT> (or <AGENT> + a subset) is installed, <AGENT> does her/his own job and notes plainly which members would normally weigh in but aren't yet available. Do not write synthesizer-style intros or wrap-ups. Do not summarize 'what <OTHER AGENT> would say.' Do not introduce other agents' voices."

In the shared file, write this as a generic template the agents reference. Each agent's SKILL.md retains a one-line "PYTHIA reads STRUCTURE..." style sentence describing its specific lane (the WHAT-IT-OWNS line that's genuinely agent-specific).

### Section 3: Account Context Framework

The runtime-tool-call rule that's identical across all three:

- "Agents pull account balances at runtime via `hub_get_portfolio_balances()` (Context A) when sizing-relevant. NEVER hardcode dollar amounts. NEVER cite a specific account balance unless it came from a live tool call within this conversation."
- The four-account structural shape descriptions (Robinhood / Fidelity Roth IRA / 401k BrokerageLink / Breakout Prop) with their role-only characterizations — the structural descriptions are uniform across agents.

The role-only account descriptions: write the canonical version once in shared. Each agent's SKILL.md retains any agent-specific note about how that agent uses those accounts (e.g., URSA's "Robinhood — defined-risk only, no naked shorts"; PYTHIA's "Robinhood — PYTHIA's MP levels inform strike anchoring and timing; DAEDALUS owns the structure choice"). Those role-specific notes stay in each agent's file as a short addendum.

### Section 4: Knowledge Architecture

The three-layer description that appears verbatim in all three:

1. Layer 1 (always in context): `docs/committee-training-parameters.md` — 130-rule Training Bible
2. Layer 2 (loaded when triggered): the agent's own SKILL.md + references files
3. Layer 3 (on-demand, rarely needed): 27 raw Stable education docs in Google Drive

Move to shared verbatim. Each agent's SKILL.md retains nothing about this section.

### Section 5: Committee Coordination

The paragraph that appears in all three:

> "When running as part of a full Olympus pass, <AGENT> outputs are passed to PIVOT alongside <OTHER AGENT> reads. <AGENT> does not negotiate with <OTHER AGENT> in real time — each produces independent reads. PIVOT synthesizes. If <AGENT> and <OTHER AGENT> reach the same directional conclusion despite their opposing/different mandates, that is a high-conviction signal worth flagging explicitly in the output."

Write the generic version in shared. Each agent's SKILL.md retains nothing about this.

### Section 6: Shared Hard Rules

These specific Hard Rules appear in all three skills and move to shared verbatim:

- "Never hardcode account dollar amounts in output — pull from hub at runtime or describe by role only."
- "Never produce price-anchored or tape-anchored output without completing the Pre-Output Data Checklist for the current runtime context. In Claude.ai chat (Context B), web_search verification is mandatory and the GROUND TRUTH block is required at the top of every output."
- "Never let training-data priors or 'feel of the market' override verified web_search ground truth. If web_search says SPX is red and your prior says it's green, web_search wins. Update the analysis accordingly."
- "Never simulate other committee members' output. <AGENT> produces only the <AGENT> block. Other agents speak for themselves when installed."
- "Below 21 DTE on any options expression, recommend closing at 60–70% of max value — don't hold for perfection." (TORO/URSA only — note in shared that this rule applies to agents that recommend options trades.)
- "Never recommend sizing that violates three-bucket caps: B2 $200–300 max with max 2 open; B3 $100 cap until cash infusion lands, max 2 concurrent, max 3/day, same-day close, structural Pythia VA trigger required." (TORO/URSA — same caveat; note this is for agents that recommend trades.)

Agent-specific Hard Rules STAY in each agent's SKILL.md. Examples that must remain agent-specific:

- TORO: "Never recommend a long entry without an explicit invalidation level." TORO: "If the bull thesis is fighting the tape, conviction caps at LOW."
- URSA: "Always run the bias-challenge check — every URSA output names whether the trade aligns with a documented Nick bias." URSA: "Always run the portfolio coherence check." URSA: "Never recommend a naked short call without explicit Nick approval."
- PYTHIA: "Never fabricate Market Profile data." PYTHIA: "Never recommend specific trade structures (calls vs puts, spread widths, strike selection) — that's DAEDALUS's lane."

The agent-specific Hard Rules are part of WHAT MAKES EACH AGENT DIFFERENT. They never move to shared.

### Section 7: Asset-Class Routing Framework

The "don't blend playbooks; crypto-adjacent equities use the equities playbook" rule appears in all three. Move to shared.

Each agent's SKILL.md retains its specific routing block (e.g., PYTHIA's "default profile periods: composite over prior 5 sessions for indices..."). Those routing specifics are agent-specific configuration.

---

## What Stays In Each Agent's SKILL.md

Critically, the agent's IDENTITY and ANALYTICAL FRAMEWORK never move to shared. After the refactor, each agent's SKILL.md should still contain:

1. **Frontmatter** (YAML name + description) — agent-specific
2. **Identity section** — agent-specific persona, voice, mandate
3. **Operating Principles / Core Philosophy** — agent-specific analytical framework
4. **The agent's specific MCP tool call list under Context A** — each agent uses a different subset; the list stays in each agent's file
5. **The agent's specific asset-class routing configuration** (default profile periods, sub-asset-class branching) — agent-specific
6. **The agent's specific role-in-account notes** (e.g., URSA: "Robinhood — defined-risk only, no naked shorts")
7. **Output Format template** — each agent's committee-mode output template is different; stays in each agent's file
8. **Direct Conversation Mode personality + behavior** — agent-specific
9. **Agent-specific Hard Rules** — the rules that make each agent distinctive
10. **Cross-references to PYTHIA's automation roadmap, Whale Hunter, etc.** for agents that need them — agent-specific

After refactor, each agent's SKILL.md should be 50-80 lines shorter, with one-line pointers like:

```markdown
## Pre-Output Data Checklist

See `_shared/COMMITTEE_RULES.md § Pre-Output Data Checklist Framework` for the universal Context A / Context B framework.

### TORO's specific tool calls (Context A)

After running the universal framework, TORO calls these MCP tools in order:

1. `hub_get_bias_composite(timeframe="swing")` ...
[the existing list]
```

This pattern — shared framework + agent-specific list — keeps the agent's file readable and focused while removing the duplication.

---

## Reference Pattern: How Agents Cite the Shared File

Every cross-reference from an agent's SKILL.md to the shared file uses this format:

```markdown
See `_shared/COMMITTEE_RULES.md § <Section Name>` for <one-line description of what's there>.
```

Examples:

- `See _shared/COMMITTEE_RULES.md § Scope Boundary Pattern for the standard "produce only your own output, no simulating other agents" rule.`
- `See _shared/COMMITTEE_RULES.md § Knowledge Architecture for the three-layer Training-Bible-and-references structure shared by all committee agents.`

When PYTHAGORAS, DAEDALUS, THALES, and PIVOT are built later, they use the same reference pattern. The shared file becomes the single source of truth for all committee-wide architecture.

---

## Build Sequence

1. **Read TORO, URSA, PYTHIA SKILL.md files** to identify the exact shared content
2. **Create `skills/_shared/COMMITTEE_RULES.md`** with the seven sections specified above, sourcing content from existing files (TORO's wording canonical where the three differ)
3. **Update `skills/toro/SKILL.md`** — replace shared sections with one-line pointers to `_shared/COMMITTEE_RULES.md`, preserve all TORO-specific content
4. **Update `skills/ursa/SKILL.md`** — same treatment
5. **Update `skills/pythia/SKILL.md`** — same treatment
6. **Verify the packaging script** picks up `skills/_shared/COMMITTEE_RULES.md` and includes it in every `.skill` archive. If the script doesn't already handle this (current packager iterates `skills/<agent>/` directories with `_archive` excluded — `_shared` may or may not be picked up depending on logic), update the script so each `.skill` archive includes both the agent's directory contents AND the shared file at a predictable path like `_shared/COMMITTEE_RULES.md` inside the archive.
7. **Run `scripts\package-skill.bat all`** — produces `dist/skills/toro.skill`, `dist/skills/ursa.skill`, `dist/skills/pythia.skill`
8. **Verify each `.skill` archive** by unzipping to a temp directory and confirming `_shared/COMMITTEE_RULES.md` is present alongside the agent's `SKILL.md` and `references/` directory
9. **Run any existing tests** to confirm nothing else broke
10. **Commit and push** with message: `refactor(skills): extract shared committee rules to _shared/COMMITTEE_RULES.md, deduplicate TORO/URSA/PYTHIA`

---

## Self-Check Before Declaring Done

Before reporting build complete, CC verifies all five:

1. **Behavior preservation:** Read TORO, URSA, PYTHIA SKILL.md (with their shared-file pointers) end-to-end. Does each agent still have access to the same architectural rules they had before the refactor? No rule has been lost, watered down, or accidentally removed.

2. **Sharp split confirmed:** Every sentence in `skills/_shared/COMMITTEE_RULES.md` applies to EVERY committee agent (current and future). If any sentence is agent-specific (e.g., "PYTHIA must explicitly note 'MP data not provided'"), it does not belong in shared — move back to agent file.

3. **Conversely:** Every sentence remaining in an agent's SKILL.md is genuinely agent-specific (about that agent's persona, mandate, tools, output format, personality). If any sentence is universal (e.g., "Never hardcode account dollar amounts"), it belongs in shared — move there.

4. **Reference resolution works:** A Claude.ai session loading TORO's skill would have access to both `SKILL.md` and `_shared/COMMITTEE_RULES.md` via the packaged `.skill` archive. Verify the package structure supports this.

5. **No new analytical content added.** This is a pure refactor. If CC was tempted to "clean up" the wording while moving content, RESIST. Wording stays exactly as it is in the source files. The refactor is location, not content.

---

## Out of Scope (do NOT do)

- Do NOT modify any analytical content (personas, philosophies, output formats, hard rules) — pure refactor only
- Do NOT add new sections, rules, or guidance — only move existing content
- Do NOT modify MCP code, hub services, or any backend
- Do NOT build PYTHAGORAS, DAEDALUS, THALES, or PIVOT — separate briefs after this lands
- Do NOT modify `docs/committee-training-parameters.md`
- Do NOT modify the references files (`references/equities.md`, `references/crypto.md`) for any agent
- Do NOT upload `.skill` files to Claude.ai — Nick handles uploads manually after CC reports done
- Do NOT edit the canonical archived skills under `skills/_archive/`

---

## Acceptance Criteria

All five must hold:

1. `skills/_shared/COMMITTEE_RULES.md` exists with the seven specified sections
2. TORO, URSA, PYTHIA SKILL.md each contain ONLY agent-specific content + one-line pointers to `_shared/COMMITTEE_RULES.md`
3. The three `.skill` archives in `dist/skills/` each contain the agent's content AND the shared file at a predictable path
4. The five self-check criteria above pass
5. Git commit pushed with the refactor

---

## Questions to Resolve Before Starting

If any of these are unclear, ASK NICK before coding:

1. **Packaging script behavior:** Does `scripts/package-skill.bat` currently iterate all directories under `skills/` (excluding `_archive`), or does it have a hardcoded list? If the latter, the script needs an update to include `_shared` in every agent's archive. Check the script before starting and propose the right pattern.
2. **Shared file path inside the archive:** Should `_shared/COMMITTEE_RULES.md` appear at the same relative path inside every `.skill` archive (e.g., `_shared/COMMITTEE_RULES.md` from archive root), or should it be flattened into each agent's directory (e.g., `toro/_shared/COMMITTEE_RULES.md`)? Recommend the former — it's cleaner and makes the "this file is shared across agents" semantics explicit.
3. **Reference pattern wording:** Confirm the pointer format `See _shared/COMMITTEE_RULES.md § <Section> for <description>.` works for Claude.ai's skill loader. If skill loader strips relative paths or requires absolute paths within the archive, adjust the pattern accordingly.

Otherwise, proceed.
