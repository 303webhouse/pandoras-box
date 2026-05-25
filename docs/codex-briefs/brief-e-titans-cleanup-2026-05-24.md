# Brief E — Titans Skills Cleanup (Ship 1 + Ship 2)

**Date:** 2026-05-24
**Authored from:** Titans Pass 1 cross-review session 2026-05-24
**Brief letter:** E (provisional — re-letter on commit if Brief D order changes)

---

## Purpose

The four Titans skill files (ATLAS, HELIOS, AEGIS, ATHENA) and `_shared/TITANS_RULES.md` are authored at `c:\trading-hub\skills\` and ready to install as Claude.ai skills, but a Pass 1 cross-review surfaced findings that need to land before install. Two ships combined:

- **Ship 1 — pre-install blockers.** ATHENA's Pre-Review #1 requires `docs/build-backlog.md` to exist; without it every ATHENA pass surfaces a prerequisite failure. AEGIS's hard rule "always record overridden flags" requires `pre-production-override-log.md` to exist; without it overrides are unrecorded (per shared rules amendment below, that means invalid).

- **Ship 2 — skill file edits.** Five files modified per the four Titans' Pass 1 findings. Scope is tweaks, not redesigns — no veto fired in Pass 1.

Total: 2 file creates, 5 file modifies, 1 commit.

---

## Pre-flight

1. `git fetch && git status` on `C:\trading-hub` — confirm working tree is clean and at the latest remote SHA on `main`. Per cross-machine drift discipline.
2. Read `PROJECT_RULES.md` at repo root.
3. Confirm `skills/` directory exists at repo root with subdirectories: `_shared/`, `atlas/`, `helios/`, `aegis/`, `athena/`. Confirm `TITANS_RULES.md` exists at `skills/_shared/TITANS_RULES.md`.
4. Confirm `skills/aegis/references/` directory exists (create if missing — Task 2 will create the first file in it).
5. Confirm `docs/codex-briefs/` directory exists.

If any pre-flight check fails, surface the failure and halt before any file operation.

---

## Tasks

### Task 1 — Create `docs/build-backlog.md`

**Action:** create new file
**Path:** `docs/build-backlog.md`
**Content:** exact content below.

```markdown
# Build Backlog

**Last updated:** 2026-05-24
**Maintainer:** Nick + ATHENA

This file is the canonical queue of pending builds for the Pandora's Box platform. ATHENA reads this before every Pass 1 review (per `skills/_shared/TITANS_RULES.md § Pre-Review Prerequisites`). Updates to the queue happen during ATHENA closure reviews or on Nick's direct edit.

**Tier definitions** (build-side analog of the three-bucket trading framework, per ATHENA's `bucket-framework-builds.md` reference):
- **Foundation** — long-cycle, multi-day, high-leverage. Establishes capability for downstream work.
- **Tactical** — short-cycle, days, medium-leverage. Targeted fixes or feature additions.
- **Quick win** — hours, low-leverage. Bug fixes, doc updates, isolated tweaks.

---

## P0 — In flight

| ID | Build | Tier | Status | Displaces |
|----|-------|------|--------|-----------|
| E | Titans skills cleanup (this brief) | Tactical | In flight | Nothing — pre-Olympus-cross-review foundation work |

## P1 — Immediate next (post Ship E)

| ID | Build | Tier | Status | Gated on | Displaces |
|----|-------|------|--------|----------|-----------|
| — | Olympus committee cross-reviews (each Olympus skill reviewed by the others) | Foundation | Queued | Brief E ship | Brief D (D unblocks once cross-reviews surface MCP-touching issues) |
| D | Hub MCP OAuth state persistence on Railway redeploys | Foundation | Drafted, queued | Cross-reviews complete | None — unblocks production MCP stability |
| — | TORO H.01 citation fix (wrong code, needs grep/codification) | Quick win | Open | None | Nothing |

## P2 — Real-time data tools for technical analysts (post-cross-review)

Three v2 hub MCP tools that unblock half-power technical analysts in committee. Effort order:

| ID | Build | Tier | Status | Gated on | Unblocks |
|----|-------|------|--------|----------|----------|
| — | `hub_get_options_chain` (DAEDALUS — UW chain + Greeks + IV) | Foundation | Spec'd | P1 complete | DAEDALUS full power |
| — | `hub_get_chart_indicators` (PYTHAGORAS — TV webhook pipeline) | Foundation | Spec'd | options chain ship | PYTHAGORAS full power |
| — | `hub_get_market_profile` (PYTHIA — TV MP webhook pipeline) | Foundation | Spec'd | chart indicators ship | PYTHIA full power, MP automation roadmap Phase 1 |

## P3 — Data integrity / outcome tracking

| ID | Build | Tier | Status | Gated on | Notes |
|----|-------|------|--------|----------|-------|
| — | Phase C brief — outcome tracking re-walk projection | Foundation | Brief not yet authored | P1 complete | Canonical-walker policy: daily for B1/B2, 15-min for B3 |
| — | 3-10 promotion re-audit | Tactical | Re-audit verdict NOT YET as of 2026-05-08 | Phase C ship + n≥250 post-Phase-B `both`-gate signals + leave-one-out robustness | Closure note at `docs/strategy-reviews/raschke/3-10-promotion-reaudit-2026-05-08.md` |
| — | URSA stop-tightness recalibration | Tactical | Queued | Phase C ship | Bounded MFE/MAE semantic shift post-Phase-B |
| — | `score_signals` pre-walk age cap remediation | Tactical | Queued | Phase C ship | Backend data integrity |
| — | BTCUSDT crypto ticker support | Tactical | Queued | None | Enables crypto playbook substrate for Stater rebuild |

## P4 — Queued strategies (gated on 3-10 promotion clearing)

| Build | Notes |
|-------|-------|
| HG Tier 1 | Hunter removed; HG tier candidate |
| 80-20 | Strategy candidate |
| Anti HG | Strategy candidate |
| News Reversal | Strategy candidate |
| Stater Swap crypto re-evaluation | Full strategy redesign around UW + TV MCPs; current strategies pre-date MCP availability |

## P5 — Infrastructure / UI

| Build | Tier | Status | Gated on |
|-------|------|--------|----------|
| Committee review logging | Foundation | Required infra for outcome attribution at n≥250 | MCP v2 write-tool gates OR direct `/api/committee/log` endpoint |
| Trading hub UI v3 (real-time UW + TV MCP streams) | Foundation | Queued | ZEUS Phase 3 |
| Abacus widget overhaul (display strategies in use post-ZEUS tier routing) | Tactical | Queued | ZEUS Phase 3 |
| X API Bookmark Intel Stream | Tactical | Evaluation queued | Post-ZEUS; Titans one-pager required first |
| THALES module (deployed cross-sectional sector RS, narrow-leadership detection, sector divergence alerts) | Tactical | Tier 2/3 candidate | Post-ZEUS |

## Displacement chains (ATHENA reads these for sequencing decisions)

- **Brief E displaces nothing.** Foundation prerequisite for Titans to function on subsequent reviews.
- **Olympus cross-reviews displace Brief D shipping.** Cross-reviews may surface MCP-touching findings that change Brief D's scope.
- **v2 hub MCP tools (options chain → chart indicators → market profile) are sequenced by effort and dependency, not by user priority.** Options chain is lowest effort and DAEDALUS unlocks fastest.
- **Phase C displaces 3-10 promotion re-audit.** Re-audit is gated on Phase C.
- **3-10 promotion clearing displaces HG Tier 1, 80-20, Anti HG, News Reversal.** Strategy queue items are gated on 3-10 closure.
- **ZEUS Phase 3 displaces trading hub UI v3, Abacus overhaul, X API Intel Stream, THALES module.** All Tier 5 items are post-ZEUS.

## Open questions for Nick (resolve when this file is reviewed)

1. **Is "ZEUS" defined anywhere yet?** Referenced repeatedly as a gating dependency for P5 items but not in any current docs. Either author a ZEUS scope doc or rename the gate.
2. **Brief letter assignment.** Brief E is provisional in this file. If Brief D's order changes, re-letter accordingly.
3. **Olympus cross-reviews** — does this need a separate brief or is it executed inline? Currently treated as a P1 queued build without a brief.
```

**Acceptance:** file exists, parses as markdown, all tables render.

---

### Task 2 — Create `skills/aegis/references/pre-production-override-log.md`

**Action:** create new file (parent directory may need creation — see pre-flight #4)
**Path:** `skills/aegis/references/pre-production-override-log.md`
**Content:** exact content below.

```markdown
# AEGIS Pre-Production Override Log

Running record of every pre-production override invoked per `skills/_shared/TITANS_RULES.md § Veto Rights`.

**Purpose:** When Nick invokes the pre-production override on an AEGIS data-API credential flag, the flag is recorded here — the override is acknowledgment, not dismissal. Every entry feeds into the comprehensive security review backlog.

**Override eligibility:** Data-API credentials only (UW API key, alternative data sources). Broker/trading API credentials (Robinhood, IBKR, Fidelity, Breakout Prop) are NOT eligible regardless of phase.

**Override expiry triggers:**
1. Any broker trading API is connected to the hub.
2. Nick formally schedules the comprehensive security review.

When either trigger fires, all overrides expire and the recorded flags become active review items.

---

## Override entries

_No overrides recorded yet._

<!-- Entry format:
### YYYY-MM-DD — [build name / brief ID]
- **Flag:** [original AEGIS finding]
- **File:line:** [where the flag fires]
- **Override conditions at invocation:** [broker connected? security review scheduled?]
- **Nick written acknowledgment:** [link to chat transcript or commit comment]
- **Resolution plan:** [what gets fixed in the comprehensive security review]
-->
```

**Acceptance:** file exists at the exact path, the parent `references/` directory exists.

---

### Task 3 — Modify `skills/_shared/TITANS_RULES.md`

**Action:** two `str_replace` edits.

**Edit 3a — Add override-persistence sentence to § Veto Rights.**

Find this exact text:

```
  When the override is invoked, AEGIS still records the flag in the review output. The override is acknowledgment, not dismissal — the flag remains a TODO for the comprehensive security pass.
```

Replace with:

```
  When the override is invoked, AEGIS still records the flag in the review output. The override is acknowledgment, not dismissal — the flag remains a TODO for the comprehensive security pass.

  **Override invocations MUST be recorded in `skills/aegis/references/pre-production-override-log.md` at the time of invocation. Unrecorded overrides are invalid.** AEGIS appends a new entry to the override log every time the override is invoked.
```

**Edit 3b — Add new § References Authoring Status section.**

Find this exact text:

```
## § Shared Hard Rules
```

Replace with:

```
## § References Authoring Status

Each Titan's `SKILL.md` references files in its own `references/` directory. Those reference files may or may not exist at the time any Titan reads its own skill. Before treating an item as a known gap:

1. Verify file existence at `skills/<titan>/references/<filename>`.
2. If the file exists, read it as authoritative — the skill file may not have been updated to reflect the authoring.
3. If the file does not exist, treat as a known pending-authoring gap and work from `PROJECT_RULES.md` + the codebase / Nick's memory snapshot / `docs/operations/mcp-token-rotation.md` as appropriate to the Titan's lane.

This pattern applies to all four Titans uniformly.

---

## § Shared Hard Rules
```

**Acceptance:** both edits land, file still parses cleanly, no other sections altered.

---

### Task 4 — Modify `skills/atlas/SKILL.md`

**Action:** three `str_replace` edits.

**Edit 4a — Remove "hardcoded API keys" from Veto Domain (AEGIS jurisdiction).**

Find this exact text:

```
- **Known-broken backend pattern:** PowerShell for git operations on Windows, unbounded UW `/option-contracts` queries (no `?expiry=` + `?option_type=`), bypassing `get_postgres_client()`, hardcoded Railway URLs, hardcoded API keys.
```

Replace with:

```
- **Known-broken backend pattern:** PowerShell for git operations on Windows, unbounded UW `/option-contracts` queries (no `?expiry=` + `?option_type=`), bypassing `get_postgres_client()`, hardcoded Railway URLs. (Hardcoded API keys = AEGIS jurisdiction; see `_shared/TITANS_RULES.md § Veto Rights`.)
```

**Edit 4b — Add SEVERITY tag to Findings format.**

Find this exact text:

```
FINDINGS:
- [Specific issue + file:line reference where possible — e.g., "backend/api/sectors.py:462 has a stale comment claiming yfinance migration is complete; get_bars is still yfinance-backed"]
- [Specific issue + reference]
- [3-6 findings; quality over quantity]
```

Replace with:

```
FINDINGS:
- [Specific issue + file:line reference + SEVERITY where possible — e.g., "backend/api/sectors.py:462 has a stale comment claiming yfinance migration is complete; get_bars is still yfinance-backed. SEVERITY: MEDIUM."]
- [Specific issue + reference + SEVERITY]
- [3-6 findings; quality over quantity]

SEVERITY scale (matches AEGIS):
- HIGH = build blocker or active data integrity risk
- MEDIUM = correctness concern, addressable with concrete fix
- LOW = observation worth noting but not blocking
```

**Edit 4c — Replace the inline authoring-status note with a back-reference.**

Find this exact text:

```
ATLAS-specific Layer 2 references (in `skills/atlas/references/`):

**Authoring status note:** The references below may or may not exist at the time any agent reads this skill. Before treating an item as a known gap, verify file existence at `skills/atlas/references/<filename>`. If the file exists, read it as authoritative — this skill file may not have been updated to reflect the authoring. If the file does not exist, treat as a known pending-authoring gap and work from `PROJECT_RULES.md` + the codebase.
```

Replace with:

```
ATLAS-specific Layer 2 references (in `skills/atlas/references/`):

See `_shared/TITANS_RULES.md § References Authoring Status` for how to handle references that may not be authored yet. ATLAS-specific fallback: work from `PROJECT_RULES.md` + the codebase.
```

**Acceptance:** all three edits land, file still parses, YAML frontmatter intact, no other sections altered.

---

### Task 5 — Modify `skills/helios/SKILL.md`

**Action:** two `str_replace` edits.

**Edit 5a — Clarify Pre-Review #4 reads response envelope contracts, not route handlers.**

Find this exact text:

```
4. **The backend endpoint(s) the affected UI calls.** Even though backend correctness is ATLAS's lane, HELIOS needs to know what data shape the UI expects vs. what the backend currently returns — that's how UI gaps get correctly attributed to backend root causes (the Sector Heatmap lesson).
```

Replace with:

```
4. **The backend endpoint(s) response envelope contracts — not the route handler implementations.** Read the OpenAPI spec entries or response schema docs for the affected endpoints. Even though backend correctness is ATLAS's lane, HELIOS needs to know what data shape the UI expects vs. what the backend currently returns — that's how UI gaps get correctly attributed to backend root causes (the Sector Heatmap lesson). Reading the route handler itself crosses into ATLAS's lane; reading the contract does not.
```

**Edit 5b — Replace the inline authoring-status note with a back-reference.**

Find this exact text:

```
HELIOS-specific Layer 2 references (in `skills/helios/references/`):

**Authoring status note:** The references below may or may not exist at the time any agent reads this skill. Before treating an item as a known gap, verify file existence at `skills/helios/references/<filename>`. If the file exists, read it as authoritative — this skill file may not have been updated to reflect the authoring. If the file does not exist, treat as a known pending-authoring gap and work from `PROJECT_RULES.md` + the existing `app.js` patterns + Nick's stated preferences.
```

Replace with:

```
HELIOS-specific Layer 2 references (in `skills/helios/references/`):

See `_shared/TITANS_RULES.md § References Authoring Status` for how to handle references that may not be authored yet. HELIOS-specific fallback: work from `PROJECT_RULES.md` + the existing `app.js` patterns + Nick's stated preferences (dark teal palette, vanilla JS, single-file architecture).
```

**Acceptance:** both edits land, file still parses, YAML frontmatter intact, no other sections altered.

---

### Task 6 — Modify `skills/aegis/SKILL.md`

**Action:** two `str_replace` edits.

**Edit 6a — Mark `claude_desktop_config.json` read as Nick-local-machine only.**

Find this exact text:

```
3. **`claude_desktop_config.json`** structure (per Nick's memory: only desktop-commander entry as of May 2026). Builds that introduce new MCP servers need to update this file safely.
```

Replace with:

```
3. **`claude_desktop_config.json`** structure (per Nick's memory: only desktop-commander entry as of May 2026). Builds that introduce new MCP servers need to update this file safely. **NOTE: this file lives at `AppData\Roaming\Claude\` on Nick's Windows machines — read is only possible when AEGIS runs from one of Nick's local machines (laptop or office PC). When AEGIS runs from a remote runner (headless CC, future automation), surface this prerequisite as unmet rather than skipping it silently.**
```

**Edit 6b — Replace the inline authoring-status note with a back-reference.**

Find this exact text:

```
AEGIS-specific Layer 2 references (in `skills/aegis/references/`):

**Authoring status note:** The references below may or may not exist at the time any agent reads this skill. Before treating an item as a known gap, verify file existence at `skills/aegis/references/<filename>`. If the file exists, read it as authoritative — this skill file may not have been updated to reflect the authoring. If the file does not exist, treat as a known pending-authoring gap and work from `PROJECT_RULES.md` + `docs/operations/mcp-token-rotation.md` + the codebase.
```

Replace with:

```
AEGIS-specific Layer 2 references (in `skills/aegis/references/`):

See `_shared/TITANS_RULES.md § References Authoring Status` for how to handle references that may not be authored yet. AEGIS-specific fallback: work from `PROJECT_RULES.md` + `docs/operations/mcp-token-rotation.md` + the codebase.
```

**Acceptance:** both edits land, file still parses, YAML frontmatter intact, no other sections altered.

---

### Task 7 — Modify `skills/athena/SKILL.md`

**Action:** three `str_replace` edits.

**Edit 7a — Reorder Overview template to lead with VERDICT + CONVICTION.**

Find this exact text:

```
### Overview (Unique to ATHENA — Step 5 of Workflow)

```
ATHENA — OVERVIEW
BUILD: [brief name]

PASS 1 SUMMARY:
- ATLAS: [verdict + conviction]
- HELIOS: [verdict + conviction]
- AEGIS: [verdict + conviction]
- ATHENA (self): [verdict + conviction]

NICK INJECTION: [Summary of any context Nick added between passes]

PASS 2 RESOLUTION:
- [Agreements that emerged]
- [Disagreements + ATHENA's tie-break + reasoning]
- [Vetoes in play, if any]

AGREED SCOPE:
[One paragraph. What the build will actually include after Pass 1 + Pass 2 + Nick injection.]

SEQUENCING:
[Where in the queue this build now sits. What it defers. What dependencies it has on other queued work.]

OLYMPUS IMPACT:
[Final assessment. Which skills are touched, what re-test is required, what closure-note coverage is expected.]

OPEN QUESTIONS FOR NICK:
- [Any question the Titans flagged but couldn't resolve — Nick decides here]

RECOMMENDED VERDICT: [PROCEED TO BRIEF / RESCOPE / DEFER / AUDIT-FIRST]
CONVICTION: [LOW / MODERATE / HIGH]
```
```

Replace with:

```
### Overview (Unique to ATHENA — Step 5 of Workflow)

Per ADHD-friendly principle: lead with the verdict and conviction. Supporting blocks follow for drill-down. Nick sees the answer first.

```
ATHENA — OVERVIEW
BUILD: [brief name]

RECOMMENDED VERDICT: [PROCEED TO BRIEF / RESCOPE / DEFER / AUDIT-FIRST]
CONVICTION: [LOW / MODERATE / HIGH] — [one-sentence justification]

---

PASS 1 SUMMARY:
- ATLAS: [verdict + conviction]
- HELIOS: [verdict + conviction]
- AEGIS: [verdict + conviction]
- ATHENA (self): [verdict + conviction]

NICK INJECTION: [Summary of any context Nick added between passes]

PASS 2 RESOLUTION:
- [Agreements that emerged]
- [Disagreements + ATHENA's tie-break + reasoning]
- [Vetoes in play, if any]

AGREED SCOPE:
[One paragraph. What the build will actually include after Pass 1 + Pass 2 + Nick injection.]

SEQUENCING:
[Where in the queue this build now sits. What it defers. What dependencies it has on other queued work.]

OLYMPUS IMPACT:
[Final assessment. Which skills are touched, what re-test is required, what closure-note coverage is expected.]

OPEN QUESTIONS FOR NICK:
- [Any question the Titans flagged but couldn't resolve — Nick decides here]
```
```

**Edit 7b — Add credential-quote prohibition to Hard Rules.**

Find this exact text:

```
- Never produce a "weigh the considerations" Overview — always produce a recommended verdict.
- Always check `docs/build-backlog.md` (or memory equivalent) before any Pass 1. If the backlog is not persisted, flag it.
- Always cite the displaced queued work by name. "Defers other work" is not specific enough.
```

Replace with:

```
- Never produce a "weigh the considerations" Overview — always produce a recommended verdict.
- Never quote credential values, token strings, or secret env var contents in Overview output, even when summarizing AEGIS findings. Refer to credentials by name and location only (e.g., "UW_API_KEY in Railway env vars" not "UW_API_KEY=uw_xxx...").
- Always check `docs/build-backlog.md` before any Pass 1. If the backlog is not persisted, flag it.
- Always cite the displaced queued work by name. "Defers other work" is not specific enough.
```

**Edit 7c — Replace the inline authoring-status note with a back-reference.**

Find this exact text:

```
ATHENA-specific Layer 2 references (in `skills/athena/references/`):

**Authoring status note:** The references below may or may not exist at the time any agent reads this skill. Before treating an item as a known gap, verify file existence at `skills/athena/references/<filename>`. If the file exists, read it as authoritative — this skill file may not have been updated to reflect the authoring. If the file does not exist, treat as a known pending-authoring gap and work from `PROJECT_RULES.md` + Nick's memory snapshot.
```

Replace with:

```
ATHENA-specific Layer 2 references (in `skills/athena/references/`):

See `_shared/TITANS_RULES.md § References Authoring Status` for how to handle references that may not be authored yet. ATHENA-specific fallback: work from `PROJECT_RULES.md` + `docs/build-backlog.md` (now canonical post-Brief-E) + Nick's memory snapshot for anything not yet in the backlog.
```

**Acceptance:** all three edits land, file still parses, YAML frontmatter intact, no other sections altered. Note: `docs/build-backlog.md` is now mentioned as canonical (not "memory equivalent") since Task 1 creates it.

---

## Output spec

**File creates (2):**
- `docs/build-backlog.md`
- `skills/aegis/references/pre-production-override-log.md`

**File modifies (5):**
- `skills/_shared/TITANS_RULES.md` (2 str_replace edits)
- `skills/atlas/SKILL.md` (3 str_replace edits)
- `skills/helios/SKILL.md` (2 str_replace edits)
- `skills/aegis/SKILL.md` (2 str_replace edits)
- `skills/athena/SKILL.md` (3 str_replace edits)

**Total str_replace operations:** 12.

**Single commit on `main`.**

**Commit message:**

```
Brief E: Titans skills cleanup (Ship 1 + Ship 2)

Pre-install blockers + Pass 1 cross-review tweaks.

Creates:
- docs/build-backlog.md (canonical queue, replaces memory snapshot)
- skills/aegis/references/pre-production-override-log.md (stub for override discipline)

Modifies _shared/TITANS_RULES.md:
- Adds override-persistence sentence to § Veto Rights
- Adds new § References Authoring Status

Modifies skills/atlas/SKILL.md:
- Removes "hardcoded API keys" from Veto Domain (AEGIS jurisdiction)
- Adds SEVERITY tags to Findings format
- Replaces inline authoring-status note with shared-rules ref

Modifies skills/helios/SKILL.md:
- Pre-Review #4: reads response envelope contracts, not route handlers
- Replaces inline authoring-status note with shared-rules ref

Modifies skills/aegis/SKILL.md:
- Pre-Review #3: marks claude_desktop_config.json read as Nick-local-machine only
- Replaces inline authoring-status note with shared-rules ref

Modifies skills/athena/SKILL.md:
- Reorders Overview template to lead with VERDICT + CONVICTION
- Adds credential-quote prohibition to Hard Rules
- Replaces inline authoring-status note with shared-rules ref

Pass 1 findings addressed:
- ATLAS: build-backlog persistence, claude_desktop_config Nick-local note
- HELIOS: ATHENA Overview reorder, SEVERITY tags on ATLAS
- AEGIS: ATLAS hardcoded API keys jurisdiction, override persistence path, credential-quote prohibition
- ATHENA: deduplication via shared-rules references

Deferred to Ship 3 / Ship 4:
- Reference file tiering
- Lightweight-review path definition
- "Read the actual code" principle consolidation
- ATLAS/AEGIS persona/voice differentiation
```

---

## Gates / what NOT to do

- **DO NOT modify any Olympus skill files.** This brief touches Titans only. The seven `skills/{toro,ursa,pythagoras,pythia,daedalus,thales,pivot}/` directories are out of scope.
- **DO NOT modify `skills/_shared/COMMITTEE_RULES.md`.** That's the Olympus shared file. Only `TITANS_RULES.md` is in scope.
- **DO NOT consolidate the "Read the actual code" principle in this ship.** Each Titan's lane-specific version is genuinely different (backend files / frontend files / credential patterns). Deferred to Ship 3.
- **DO NOT author additional reference files** beyond the two specified (build-backlog.md and pre-production-override-log.md). Reference tiering is Ship 3.
- **DO NOT add SEVERITY tags to HELIOS or AEGIS findings** — they're already differentiated. SEVERITY is added only to ATLAS to match AEGIS's existing format.
- **DRY-RUN PROTOCOL:** stage all changes (`git add -A`), then `git diff --cached` and visually confirm no surprise edits crept in (especially in the str_replace operations). Only after Nick approves the staged diff do you commit and push.
- **DO NOT push without Nick's explicit `--apply` approval.** Per ATLAS phase-gate discipline, even non-destructive multi-file edits go through dry-run + apply.

---

## Done definition

1. All 9 file operations complete: 2 creates + 7 file modifies (containing 12 total str_replace edits).
2. `git status` shows exactly the expected modified files: no untracked changes outside the brief's scope.
3. `git diff --cached` reviewed by Nick before commit. Surprise changes (even formatting drift) get reverted.
4. All 5 modified SKILL.md files still parse as valid markdown with intact YAML frontmatter.
5. Single commit on `main`, message per Output spec.
6. Pushed to remote.
7. Closure note appended to this brief (inline in `docs/codex-briefs/brief-e-titans-cleanup-2026-05-24.md`) under a `## Closure` heading, listing: what shipped, what changed from this brief if anything, what didn't ship.
8. Brief E committed to `docs/codex-briefs/` (this file).

---

## Olympus Impact

**None.** This is Titans-internal work. No Olympus skill file is modified. No `_shared/COMMITTEE_RULES.md` change. No hub MCP tool change. No data source change. No committee re-test required.

---

## Sequencing note for Nick

After this brief ships and the Titans skill files are installed in Claude.ai, the **next** action is the P1 build "Olympus committee cross-reviews" — each Olympus skill (TORO, URSA, PYTHIA, PYTHAGORAS, DAEDALUS, THALES, PIVOT) reviewed by the others, in the same Pass 1 / Pass 2 / ATHENA Overview pattern that the Titans review themselves.

That cross-review may surface MCP-touching findings that affect Brief D (Hub MCP OAuth state persistence). Brief D should not ship until the cross-reviews complete.

---

*End of Brief E.*
