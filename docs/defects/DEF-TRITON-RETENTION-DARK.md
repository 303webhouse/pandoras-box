# DEF-TRITON-RETENTION-DARK

**Class:** policy-absent — a retention policy believed to be running that has never run
**Severity:** **P3** (as stated in the citing documents)
**Status:** **OPEN · FIX BLOCKED BY LAW** — see the block below. The block is deliberate and
must not be lifted by whoever implements the fix.
**Surface:** `triton_flow_shadow` retention — the 30-day deletion of ungraded rows
**Stubbed:** 2026-09-05 per R-IV.262(b), from citing documents only. **No new
investigation was performed for this stub.**

**First citation:** `docs/codex-briefs/2026-09-01-triton-handoff-to-olympus.md:28`

> **This stub is the residue documentation the fix is blocked on.** R-IV.262(b) designates it
> as that document's home; the residue census is recorded below so the block has something to
> resolve against.

## What is known

The stated policy is that retention **deletes ungraded rows at 30 days**. It does not run:

- **46 ungraded rows were older than 30 days** (measured 2026-09-02)
- the oldest pending row is `2026-07-02 14:06:53Z` — **60 days 07:22** old and still present

Under the stated policy none of those could exist. **Nothing is being deleted at all.**

## Residue census — the rows the block protects

Pending rows interior to the graded period (`fired_at < 2026-08-17`):

| | at 2026-09-02 | after the 09-02 grading pass |
|---|---|---|
| residue total | **126** | **73** |
| — 08-14 mid-cohort stall | 55 | 2 |
| — pre-08-14, cause unstated | 71 | 71 |
| — of which fired before 08-01 | 46 | 46 |

The **cause is established**: **70 of the 71** pre-08-14 rows lack `prior_5d_ret`, against 7
of 5,967 in the graded population. They are the cash-settled index symbols of
`DEF-TRITON-INDEX-UNGRADEABLE` — **72 rows, 0 ever graded, no price series.**

**53 gradeable residue rows were graded on 09-02**, leaving 73. The remaining floor is
**72 permanently ungradeable + 1**.

## Why the fix is BLOCKED, and what would unblock it

Ruled law: **"no deletion policy may run while the reason rows are undeleted is itself
unexplained."** Generalized at receipt: *no deletion policy may outrun the liveness of any
consumer holding an unexercised claim on the row.*

The stake is concrete. The 46 pre-08-01 rows are **not a random sample of the residue** —
they are predominantly the index-symbol rows, and they are the **only physical evidence that
an entire instrument class is ungradeable**. A 30-day sweep would erase the evidence *and*
leave the defect, because new ungradeable rows keep arriving.

**Unblocks when** the grader records skip reasons (`DEF-TRITON-GRADER-NO-SKIP-REASON`) **and**
index rows are classified `UNGRADEABLE-NO-SERIES` (`DEF-TRITON-INDEX-UNGRADEABLE`). Until
both, the current accident — a policy that does not run — is the **correct behaviour by luck**,
and restoring the stated policy would be a regression.

## What is FALSIFIED — do not re-derive these

- that rows **were being deleted** — nothing has been; the 60-day-old row is the proof
- that the residue **aged out** — the U2 silent-bleed case did not occur, ruled out **by
  mechanism**, not merely by count
- that the **46 are a random sample** — they are predominantly one instrument class
- that retention can be fixed **independently of the grader** — the block is a sequencing
  dependency, a P3 ticket gating a P1/P2 investigation, and that inversion is intentional
- that **`id_gaps` evidences deletion** — the raw arithmetic (min 1, max 377,783, 7,014 rows →
  370,769 "gaps") is **sequence burn** from `ON CONFLICT DO NOTHING` on `uw_alert_id`,
  ~54 values per stored row. It is not 370k deleted rows.

## Lineage

Cited in **3 documents**, on **3 lines** (counts stated separately per R-IV.262(c)):

- `docs/codex-briefs/2026-09-01-triton-handoff-to-olympus.md:28`
- `docs/defects/DEF-TRITON-GRADER-DARK.md:57`
- `docs/strategy-reviews/2026-09-03-triton-rescope-proposal.md:57`
