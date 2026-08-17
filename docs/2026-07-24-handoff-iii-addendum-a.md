# HANDOFF III — ADDENDUM A (events after authoring, 2026-07-24 ~23:00 MT)
Seed the new spine with the main handoff + this addendum together. This supersedes where it conflicts.

## SHELL Phase 0 closure (Mobile Shell) — intaken, triaged, ruled
Brief v1.2 filed (Phase 1 = T1.0–T1.7; Phase 2 simplified to layout_key rows, no DDL — scope-reducing delta, self-certification accepted; delta note requested for the file). Five pre-existing flags surfaced, spine rulings:

1. **DEF-GREEKS-ZERO (P1, pre-freeze).** `/api/v2/positions/greeks` returns all-zeros from a branch bug; desktop Book tile renders zeros as measured — live fake-healthy on an operator risk surface. Fix = the branch bug + honest seam (unavailable → N/A, never zeros). Micro-brief early next week. **Interim caveat, active now: Book-tile greeks are untrusted; zeros mean UNKNOWN.**
2. **DEF-KILLSWITCH-FAILOPEN (P1, MANDATORY pre-freeze — vacation-critical.)** Kill-switch UI shows "CLEAR" on fetch error; no UNKNOWN state. A phone-only operator with a safety display that fails open is the exact trip failure mode. Fix = UNKNOWN/fail-closed display state. **Merged with A-4 (kill-switch arm-path verification: one controlled arm/reset), which — honest ledger note — silently fell off the board across both handoffs; SHELL's flag resurrected it. One combined pass, one brief, must land before 8/4.**
3. **Layout endpoint auth/CSRF:** accepted as recorded — Phase 2 AEGIS riders (post-8/15). Phase 2 adds one question: confirm layout POST values can't carry stored-XSS.
4. **Touch-resize clobber:** accepted as structured (backup-row mitigation now, Phase 1 fix). **Hotfix carve-out PRE-APPROVED conditionally:** if Phase 1 misses the 8/1 gate, the clobber-guard hotfix alone may ship by 8/1 as a minimal deploy.
5. **S-6 ledger divergence = the +24 mystery, solved.** The uncommitted s6-brief edit re-scopes the discipline endpoint that the committed ledger descoped (ratified Option A). Saturday's BUILDER-2 diff ruling is therefore a SCOPE decision: spine default = **DISCARD** (Option A stands; enforced-discipline endpoint remains a post-vacation design question per SG-0). If Nick wants the re-scope, it routes as a proper change request, not a working-tree edit.

## Revised early-week priority (supersedes the handoff's implicit order)
Mon–Tue: (1) KILLSWITCH-FAILOPEN + A-4 combined pass → (2) GREEKS-ZERO → (3) R5 micro-brief → (4) rotation pile only if a gap remains. Monday's confirmations (PYTHIA round-trip, silent-strategy triage, Triton gate) run in parallel on their own lanes as scheduled.

## Saturday list: unchanged, with item 3 now informed
The BUILDER-2 diff session proceeds as written; the +24 ruling arrives pre-briefed by flag 5 above (default: discard). Everything else on the Saturday list stands.
