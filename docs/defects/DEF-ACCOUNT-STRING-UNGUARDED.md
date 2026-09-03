# DEF-ACCOUNT-STRING-UNGUARDED

**Severity:** P2 · **Filed:** 2026-09-03 (R-IV.205(c)) · **Class:** DATA INTEGRITY / INGEST
**Status:** OPEN — registration only. Fix HELD and unsequenced.
**Owner:** CC-POSITIONS (evidence) · CC-BUILD (surface)
**Surface:** `unified_positions.account` — write paths outside the guarded UI modal

## THE DEFECT

`unified_positions.account` accepts any string. Five rows — ids **402 GDX · 403 SQQQ ·
404 IEO · 405 SIL · 406 COPX**, all `source='MANUAL'`, all created inside a **three-minute
window** on 2026-09-02 (18:17:49Z → 18:20:49Z) — were written with `account='FIDELITY'`, a
value that is a **UI filter label, not an account identity**. It appears exactly once in the
frontend, at `frontend/index.html:498`, as a positions-tab button (`data-account="FIDELITY"`,
matched by prefix in `matchesAccountFilter`); it is **not an option in any entry select**
(`index.html:855`, `app.js:10701` offer `ROBINHOOD` and `FIDELITY_ROTH`). The canonical value
is `FIDELITY_ROTH`. The guarded entry modal already defends against this exact leak —
`app.js:10786-10788` explicitly excludes `FIDELITY` when seeding the entry default and falls
back to `ROBINHOOD` — so the five rows did **not** come through it; they came through an
unguarded write path, and id 402's note (`"Filled at price recommended by Olympus"`) points at
an Olympus-driven entry. **There is no CHECK constraint, enum, or foreign key on
`unified_positions.account`**, so nothing at the storage layer stops recurrence, and the
existing UI guard cannot help a caller that never touches the UI. The five rows were remapped
to `FIDELITY_ROTH` under R-IV.192(d)/R-IV.200(c) with the evidence recorded per row (account
scope: 652303158 is the only tradeable Fidelity account, AHRP descoped; ETF-only invariant) —
**the remap corrects the instances; it does not close the path.**

## CORRECTION TO THE FILING RECORD

R-IV.192(d) described **four** rows. The reading found **five** — id 405 (SIL) carries the
identical string and was written in the same three-minute window, making it a fifth *member*
of one defect, not a fifth *variant*. Corrected on this lane's reading and accepted
R-IV.205(c).

## BLAST RADIUS

Account-scoped reads are the exposure: any query filtering `account='FIDELITY_ROTH'` silently
omitted these five while they carried the wrong string. The Fidelity open set read as three
rows when it was six. Aggregations by account, the ETF-only invariant check, and cash
reconciliation all inherit the omission for as long as a mis-stringed row survives undetected.

## WHAT IS NOT ESTABLISHED

- **The specific write path.** Inferred as non-UI from the guard and the row notes; not traced
  to a handler. That trace is CC-BUILD's surface, not this lane's.
- **Whether other unmapped values exist or have existed.** Only three distinct values are
  present now (`ROBINHOOD` 285 · `FIDELITY_ROTH` 66 · zero `FIDELITY`). Historical values that
  were remapped or deleted before this pass would not appear.

## REMEDIATION

**HELD.** No fix attempted. Recorded shape only: the storage layer has no constraint, and a
UI-side guard cannot bind callers that bypass the UI.
