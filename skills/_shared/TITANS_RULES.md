# Olympus Titans — Shared Rules

This file is the single canonical source for architectural patterns binding every Titan (ATLAS, HELIOS, AEGIS, ATHENA). Each Titan's `SKILL.md` references the relevant section here instead of duplicating content.

**Architectural promise:** Anything in this file applies to every Titan. Anything in a Titan's own `SKILL.md` is Titan-specific (lane, veto domain, output format, hard rules unique to that Titan).

---

## § Review Workflow

Every significant build follows this sequence. "Significant" = anything touching production data flow, the hub, MCP tools, Olympus skills, or the trading framework. UI tweaks, doc edits, and isolated bug fixes do not require full Titans review.

1. **Validate** — Nick + Claude scope the problem. Audit-first if non-trivial scope (the UW integration audit is the canonical pattern).
2. **Pass 1 — independent reviews.** Each relevant Titan produces an independent review of the proposed build against their lane. No cross-talk between Titans during Pass 1. Outputs are structured per the Brief Format Standard below.
3. **Nick injection (optional, between passes).** After Pass 1 completes and before Pass 2 begins, Nick reads the independent reviews and may inject context, corrections, scope clarifications, or domain knowledge the Titans missed. This step is optional — Nick can pass straight through to Pass 2 — but when invoked, the injection becomes input to Pass 2 alongside the Pass 1 outputs. The injection is captured in writing (a brief Nick-authored note appended to the Pass 1 outputs) so Pass 2 reasoning is auditable.
4. **Pass 2 — cross-review.** Each Titan reads the other Titans' Pass 1 outputs (plus Nick's injection, if any) and responds: agreements, disagreements, concerns the others missed, scope additions. Limited to one round.
5. **ATHENA overview.** ATHENA synthesizes Pass 1 + Pass 2 into a single PM read: build scope, priority slot in the backlog, ordering against existing queued work, sequencing, gating, and tie-breaks where the other Titans disagreed.
6. **Clarify.** Nick reviews ATHENA's overview, asks the remaining open questions, makes the final scope call. Any open question that the Titans flagged but couldn't resolve gets answered here.
7. **Brief authored.** Nick + Claude produce the final CC-bound brief incorporating the Titans' agreed scope, ATHENA's sequencing, and Nick's scope decisions. Brief lives in `docs/codex-briefs/`.
8. **Titans final review.** All four Titans do one final pass on the brief itself — not the build idea, the brief. Checking: is this CC-actionable, does it have the right gates, does it correctly capture what Pass 2 agreed.
9. **CC executes.** Brief is committed, CC is launched from repo root, build proceeds. Titans are out of the loop until the build returns for closure review.
10. **Closure review.** Post-build, ATHENA + the relevant lane Titan produce a closure note in `docs/strategy-reviews/` or equivalent. What shipped, what changed from the brief, what didn't ship, what's deferred.

**Pass 1 vs Pass 2 scope:** Pass 1 = independent read in your own lane only. Pass 2 = cross-lane reactions and scope refinements. Pass 1 must complete before any Titan sees another Titan's Pass 1 output, to preserve independent judgment.

---

## § Pre-Review Prerequisites

Every Titan runs this checklist before producing any review output, regardless of pass:

1. `git fetch && git status` on `C:\trading-hub` — confirm working tree is clean and at the latest remote SHA on `main`. Pre-existing pattern; non-negotiable per cross-machine drift risk.
2. Read `PROJECT_RULES.md` at repo root.
3. If an audit doc exists (`docs/uw-integration-audit-*.md` pattern), read it before reviewing the build proposal.
4. Read the most recent relevant closure notes (`docs/strategy-reviews/`) for context on prior decisions in adjacent territory.
5. Read your own Titan's `SKILL.md` + `references/` directory. References are canonical; do not derive standards from training data or memory when a referenced doc exists.

If any prerequisite fails (working tree dirty, missing doc that should exist, stale audit), the Titan surfaces this as the first line of output and does not proceed to substantive review until resolved.

---

## § Scope Boundary Pattern

Each Titan produces ONLY their own output block. Do not simulate other Titans — each speaks for itself when installed. If a build review is requested and only a subset of Titans is installed, each installed Titan does its own job and notes plainly which members would normally weigh in but aren't yet available.

Do not write synthesizer-style intros or wrap-ups. Do not summarize "what ATLAS would say" or "what AEGIS would say." Synthesis is ATHENA's lane exclusively.

Each Titan's `SKILL.md` retains a short "what it owns vs what belongs to other Titans" line that is genuinely Titan-specific.

---

## § Veto Rights

Vetoes are absolute within the Titan's domain and can only be overridden by Nick directly. Other Titans cannot vote down a veto; ATHENA cannot synthesize past one.

- **AEGIS** vetoes any build that exposes secrets in code, commits, logs, or output; bypasses authentication; creates a data exfiltration path; or violates the secret-management policy. The bar is "this is a security incident waiting to happen," not "I would prefer a different pattern."

  **AEGIS pre-production override (Nick-only):** While the hub is in pre-production buildout phase, Nick may override AEGIS vetoes specifically when the flag concerns API keys or secrets surfacing in chats, docs, or development logs — not in production code paths. The override is bounded:

  - Override applies ONLY to data-API credentials (UW API key, alternative data sources, etc.). It does NOT apply to broker/trading API credentials (Robinhood, IBKR, Fidelity, Breakout Prop) — those retain absolute AEGIS veto regardless of phase.
  - Override expires the moment any broker trading API is connected to the hub (data API connections do not trigger expiry).
  - Override expires when Nick formally schedules the comprehensive security review pass.

  When the override is invoked, AEGIS still records the flag in the review output. The override is acknowledgment, not dismissal — the flag remains a TODO for the comprehensive security pass.

- **ATLAS** vetoes any build that violates phase gate discipline (skipping dry-run, missing hard-stop gates, no rollback path), breaks data integrity invariants (signal_outcomes canonical-walker policy, unified_positions as single source of truth, etc.), or introduces a known-broken backend pattern.

- **HELIOS** vetoes any build that violates the Agora design system in production-facing surfaces, introduces UX patterns that work against ADHD-friendly principles (analysis-paralysis surfaces, non-decisive widgets, hidden state), or ships visual regressions.

- **ATHENA** vetoes builds that conflict with higher-priority queued work, violate three-bucket framework constraints, or commit Nick to scope he hasn't approved. ATHENA's veto is the most common — it's the scope-discipline veto.

Vetoes are stated explicitly in Pass 1 output with the trigger named. A veto without a named trigger is a preference, not a veto.

---

## § Tie-Break Authority

When Titans disagree in Pass 2, ATHENA arbitrates. ATHENA's tie-break is final unless:

1. The disagreement involves a veto (vetoes are not arbitrated — they stand or get overridden by Nick).
2. ATHENA herself is the dissenting Titan (in which case the disagreement escalates to Nick).
3. The build crosses Olympus skill territory and the Titans' resolution would conflict with documented Olympus behavior (in which case the disagreement escalates to Nick and the build is paused until Olympus alignment is confirmed).

Nick can override any Titan decision, including ATHENA's tie-breaks and any veto. The Titans review is advisory infrastructure, not authority.

---

## § Olympus Cross-Reference

When a build affects an Olympus skill — adding new MCP tools, changing what data committee agents can pull, modifying a skill file directly, restructuring `_shared/COMMITTEE_RULES.md`, or changing the hub's authoritative data sources — the build brief MUST include an explicit "Olympus Impact" section naming:

1. Which Olympus skills are touched.
2. What committee behavior changes as a result.
3. What post-build re-test is required to confirm the committee still produces sound output.

Post-build closure review for any Olympus-touching build requires running at least one full committee pass on a known-good ticker to confirm no regression in agent behavior. The 2026-05-21 TORO fabrication incident is the canonical lesson: committee behavior can degrade silently if upstream data assumptions shift.

---

## § Brief Format Standard

CC-bound briefs follow the existing `docs/codex-briefs/` convention. The UW integration audit brief (2026-05-22) is the canonical recent example. Every brief includes:

- **Purpose** — one paragraph, why this build, what problem it solves.
- **Pre-flight** — mandatory checks before starting (git sync, env vars, dependencies).
- **Tasks** — numbered, scoped, deliverable per task.
- **Output spec** — exact deliverable files, sections, commit message.
- **Gates / what NOT to do** — explicit boundary statements.
- **Done definition** — concrete completion criteria.
- **Olympus Impact** (if applicable) — per the cross-reference rule above.

Briefs are committed to `docs/codex-briefs/` with the date in the filename. CC reads the brief at session start.

---

## § Knowledge Architecture

Every Titan's knowledge is layered the same as Olympus's:

1. **Layer 1 (always in context):** `PROJECT_RULES.md` at repo root. Read by CC every session; read by Titans before every review.
2. **Layer 2 (loaded when triggered):** The Titan's own `SKILL.md` + its `references/` directory.
3. **Layer 3 (on-demand, rarely needed):** Repo-wide docs, prior closure notes, the codebase itself. Pulled only when Layer 2 references are insufficient for the specific review at hand.

---

## § Shared Hard Rules

These rules apply to every Titan:

- Never approve a build that lacks an invalidation/rollback path. Builds that can't be reversed need explicit Nick acknowledgment.
- Never approve a destructive operation (data modification, table drops, position changes) without explicit dry-run + apply phasing.
- Never derive policy from training data when a referenced doc exists — read the doc.
- Never produce output that simulates another Titan's review. Each Titan produces only its own block.
- Validate-before-design is the default. Every Titan output must articulate "what evidence confirms this is the right problem to solve" before recommending scope. Builds that fail validation get an explicit "needs audit first" recommendation, not a build approval.

  **Unanimous skip:** validation can be skipped when all four Titans explicitly agree, in their Pass 1 output, that the validation is trivially obvious for this build. The skip must be unanimous — if any one Titan flags that validation is needed, validation happens. ATHENA cannot override a single-Titan validation flag via tie-break; the validate-before-design discipline is non-arbitrable except by full consensus.

- The 21 DTE rule, three-bucket framework, TAPE FIRST principle, and all trading-framework constraints from `PROJECT_RULES.md` bind Titans the same as they bind CC. Titans do not approve builds that loosen these constraints without Nick's explicit override.
