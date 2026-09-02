# DEF-TRITON-GRADER-DARK

**Severity:** P1 · **Escalated:** 2026-09-02 (R-IV.151(c)), was P2 · **Status:** OPEN
**Surface:** Triton shadow grader — the writer of `triton_flow_shadow.graded_at` and the
`fwd_ret_*` fields

## Symptom

`max(graded_at)` is **frozen at 2026-08-27 20:28:16Z** while gradeable rows keep
accumulating. Holdout rows fired 2026-08-17 → 08-27 have **fully closed 1d/3d/5d windows
and zero grades.**

## Why P1 rather than P2

The escalation is not about volume. The grading windows for a growing set of rows have
*already closed* — those rows are gradeable now, and every day the grader stays dark the
backlog of already-answerable rows grows. This is a component that has stopped doing the
one thing it exists to do, on data that is ready.

It also sits directly under a registered holdout (843 rows, pinned 2026-09-01), so the
defect is adjacent to a live study. **The pin is grading-independent by construction**
(`fired_at >= '2026-08-17 00:00:00+00' AND id <= 377783`) and **stays untouched** — that
predicate was chosen precisely so a grading fix could not move the holdout.

## Sequence (R-IV.151(c))

1. **After the SPEC-01 push.** This does not preempt it.
2. **Phase 0 — read-only diagnosis first.** Logs, scheduler state, last write. No fix, no
   restart, no backfill.
3. **Diagnosis to spine by Friday 2026-09-05 EOD.**
4. **Fix on greenlight only.**

## Required finding — loud or silent

The diagnosis must state **on the record** whether the grader died **loud** (errored into
a log nobody was watching) or **silent** (stopped with no error at all). Either answer
registers it to the **self-recovery family** exhibit for the 09-15 supervision brief —
alongside the flow poller, the 08-18 nightly, and `crypto_scanner`, all of which went dark
for days without an error and, in two cases, recovered unattended with no root cause ever
established.

The distinction matters because the two failures need different instruments: a loud death
needs a log consumer, a silent one needs a watermark. Answering "it stopped" without
answering which is not a diagnosis.

## Not folded in

`DEF-TRITON-GRADER-NO-SKIP-REASON` (P3) is filed separately per the residue census's own
recommendation. It is a design gap in what the grader records, not a cause of this outage,
and folding it in would let a P3 ride a P1's urgency while obscuring the P1's actual cause.

## Related

- `DEF-TRITON-INDEX-UNGRADEABLE` — SPX/SPXW/RUT/RUTW/VIX, 72 rows, 0 ever graded, no price
  series. A grader fix must classify these `UNGRADEABLE-NO-SERIES` rather than leaving them
  indistinguishable from a backlog.
- `DEF-TRITON-RETENTION-DARK` (P3) — fix BLOCKED by law while the reason rows are undeleted
  is itself unexplained.
