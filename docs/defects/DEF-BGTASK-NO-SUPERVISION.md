# DEF-BGTASK-NO-SUPERVISION · P2 (per citation)

> **STUB — R-IV.263(c), 2026-09-05.** Filed to retire a phantom, not to diagnose one.
> **Everything below is read from CITING CONTEXT ONLY. No investigation was performed**,
> no code was read for this stub, and nothing here is a measurement by this lane.
> Citations counted mechanically over `docs/` at HEAD `727d609`.

**Cited:** 4 times across 2 files, principally `docs/codex-briefs/2026-08-20-brief-def-signal-persistence-collapse.md`.

## What the citations say

> a dead background task never exits the process. This is DEF-BGTASK-NO-SUPERVISION (P2)

> … so it can die silently like any other. It reduces detection time from …

## Status: OPEN on the citations, UNVERIFIED here

The class is stated plainly: an `asyncio.create_task` loop that dies takes nothing down with it.
The process stays healthy, the endpoint stays up, and the work simply stops.

**Adjacent and probably the same family** — flagged as a lead, not a conclusion: the
grader diagnosis at `docs/edge/results/2026-09-04-triton-grader-diagnosis-and-external-arm.md` found exactly this shape in
`main.py:914-931`, where the loop is fail-open by design, `last_run` is process
memory, and a multi-day silence is indistinguishable from idleness. **DEF-TRITON-GRADER-DARK
may be an instance of this defect rather than a sibling of it**, and the precondition
build's supervision task may close both. Not asserted — the two have not been compared
under a common reading.

## What a real artifact would need

An enumeration of the `asyncio.create_task` loops in `backend/main.py` and which, if any, are supervised.
That is a code read this stub deliberately did not perform.
