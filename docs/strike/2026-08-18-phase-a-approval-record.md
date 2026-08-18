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

## Observation protocol
- Daily EOD: run `docs/strike/queries/STRIKE-OBS-01-hg1h-daily.sql` (CC or Nick) + STRIKE runs hub-side feed checks in-chat.
- Week-one review: committee reconvenes ~2026-08-25 to rule week two (continue watching / allow B3-minimum live / revert).
- Judged on signal behavior and counts in context (PYTHAGORAS note: ADX 23.6 SPY / 15.3 SMH sits below HG's native regime — a thin week is expected, not a failure).

## Key data-note carryovers from the pass
Balances stale (RH 7/31) · flow db_fallback (Mon close) · tide unavailable · HG_1H/15M split unknown at ruling time (Condition 2 closes it) · Hermes earnings-blind · quote prior_close defect (spot-only discipline). Kill-switch inactive, modifier 1.0.
