# Phase-A Approval Record — Staged Un-Suppression

**Decision date:** 2026-08-18 (Olympus double-pass) · **Operator sign-off:** Nick, 2026-08-18 (STRIKE lane, verbatim: "Approved")
**Verdict:** APPROVE PHASE A — WITH FOUR BINDING CONDITIONS · **Conviction:** MEDIUM
(capped by stale balances, unknown HG_1H/15M split, unread suppress-set origin — each repaired by a condition below)

## Scope approved
- **A1:** Remove HOLY_GRAIL_1H (only) from `SUPPRESS_ALWAYS` (l0_routing.py, per STRIKE-Q2 CR-1). 7-day watch-only observation.
- **A2:** Semis/AI universe expansion — INVESTIGATION ONLY this phase (scanner universe source + UW quota math for ATLAS ruling).
- **A3:** Committee bridge revival — P1 ops ticket (DEF-COMMITTEE-BRIDGE-DEAD), VPS-side, separate session.
- **A4:** B2 resolver zero-rows — DIAGNOSIS ONLY this phase (DEF-B2-RESOLVER-ZERO-ROWS).
- **Phase B:** SPEC-01 proceeds to ATLAS review as sequenced; SPEC-02/03/04 re-scope after observation week.

## The four binding conditions
1. **Archaeology first.** Suppress-set git history read and reported before the flip. Documented HG_1H malfunction in the history → HALT, reconvene.
2. **Split-count gate.** HG_1H ≥ 12 rows in 2026-07-30→08-16 window, else HALT, reconvene.
3. **Watch-only week one.** Surface-to-eyes only; zero live dollars (also arithmetic-enforced: RH at-risk $1,413.48 vs stale $835.69 balance reading; 20% portfolio cap ~full at 19.4%). Success = sane counts, feed hygiene, daily EOD behavior review. **P&L is explicitly not a criterion.**
4. **Kill criteria pre-written.** Rollback = revert + push. Triggers: >10 surfaced HG_1H/session · pipeline error attributable to the flip · kill-switch activation.

## Amendment 2026-08-18 — Spine countersign (riders R1, R2)

Countersigned by Spine (Fable) 2026-08-18, cc EDGE/recon. Amendment appended by
Claude Code during Phase-A execution under Spine's explicit instruction
("Confirm the approval record reads that way; amend if it doesn't"). The
original text above is unaltered.

**R2 — KILL CRITERIA ARE SELF-EXECUTING.** Condition 4 above is hereby read and
amended to state explicitly: **any trip of a kill criterion restores suppression
IMMEDIATELY.** Nobody waits for the 2026-08-25 reconvene to act on a tripped
criterion. The rollback (`git revert ae99def && git push origin main`, then
four-way verify) is executed on the trip, by whoever observes it, and the
committee is informed after the fact — not asked in advance.

This closes an ambiguity in the original record: the *Observation protocol*
section lists "revert" among the week-two options the 2026-08-25 reconvene may
rule on, which could be misread as making revert a reconvene decision. It is
not. The reconvene rules on **continuation**; the kill criteria are automatic
and self-executing at any time.

**R1 — WATCH-ONLY MUST BE MECHANISM, NOT INTENTION.** At HG_1H's first fire,
rendered evidence goes to Spine before the observation is graded:
1. the signal row **and** a PENDING outcome row both present (three-ledger law —
   no new orphan), and
2. the signal **absent from every actionable surface** (feed, committee packet,
   Agora).

If watch-only turns out to be enforced only by operator intention ("Nick just
won't trade it"), that is the fake-healthy family and it gets a technical gate
**before day two**.

> **UNRESOLVED CONFLICT — flagged, not self-adjudicated.** R1 names the *feed* as
> an actionable surface from which HG_1H must be absent. Removing HOLY_GRAIL_1H
> from `SUPPRESS_ALWAYS` (A1) does the opposite by construction: the L0 gate is
> surface-suppression, so un-suppressing is precisely what puts HG_1H **into**
> the feed. "Surface-to-eyes only" in the original record and "absent from the
> feed" in R1 cannot both hold under the A1 mechanism as built. Either
> (a) "actionable" means the accept/trade path rather than visibility, and the
> feed is the intended eyes-surface, or (b) A1 needs a different mechanism that
> observes without surfacing. **STRIKE/Spine to rule.** Recorded here so the
> first-fire evidence is graded against a settled definition.

**Standing exposure noted at flip time (Gate 3):** 64 HG_1H rows are currently
`status='ACTIVE'`, `user_action IS NULL`, inside the 24h window, and satisfy
every feed predicate except the persisted L0 tag. They do **not** surface from
the flip itself (the read filter consults the persisted tag, which still reads
`would_suppress: true`). They would surface in one shot if anything rewrites
`triggering_factors` without re-including the `l0_shadow` tag — see
`DEF-L0-TAG-STRIP-ON-RESCORE`. 64 is well above the >10-surfaced kill threshold.

## Observation protocol
- Daily EOD: run `docs/strike/queries/STRIKE-OBS-01-hg1h-daily.sql` (CC or Nick) + STRIKE runs hub-side feed checks in-chat.
- Week-one review: committee reconvenes ~2026-08-25 to rule week two (continue watching / allow B3-minimum live / revert).
- Judged on signal behavior and counts in context (PYTHAGORAS note: ADX 23.6 SPY / 15.3 SMH sits below HG's native regime — a thin week is expected, not a failure).

## Key data-note carryovers from the pass
Balances stale (RH 7/31) · flow db_fallback (Mon close) · tide unavailable · HG_1H/15M split unknown at ruling time (Condition 2 closes it) · Hermes earnings-blind · quote prior_close defect (spot-only discipline). Kill-switch inactive, modifier 1.0.
