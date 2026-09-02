# TRITON — HOLDOUT REGISTRATION · 2026-09-01

Registration of record. PIN authored by CC-QUERY; amendments per R-IV.138 / R-IV.140.
The residue census that originally shipped with this PIN is re-filed to
`docs/edge/results/2026-09-01-triton-holdout-pin-and-residue-census.md` (R-IV.140).

**Section numbering note:** the artifact as originally filed carried PART 1 / PART 2,
not §1–§6. The ordered amendments address §2, §4 and §6, so the sections below are
numbered to give those amendments anchors. **§3 is intentionally vacant.** §1 is
CC-QUERY's PIN text verbatim; no PIN value is re-derived.

---

## §1 · PIN

**Registration instant (in-DB UTC): `2026-09-01 03:28:12.361091+00`**

```
MAX_ID at registration : 377783
holdout row count      : 843
holdout id range       : 305533 … 377783
holdout fired range    : 2026-08-17 13:30:25.003237+00 … 2026-08-31 19:57:40.858307+00
rows already graded     : 0
table total            : 7,014
```

Dual-run stable. The predicate

```sql
fired_at >= TIMESTAMPTZ '2026-08-17 00:00:00+00' AND id <= 377783
```

selects exactly 843 rows and is **grading-independent** — it survives the P2 fix that would
dissolve a `graded_at IS NULL` definition.

**Shelf life, and it matters.** The poller is dark overnight; nothing has fired since
`2026-08-31 19:57:40Z`. It resumes at the 09-01 open (~13:30Z), at which point `MAX(id)`
starts moving. **File the value 377783 as captured — do not re-derive `MAX(id)` at filing
time**, or the pin silently absorbs a day of new rows and reintroduces exactly the
"growing holdout" defect the re-registration exists to close.

**Prior contact, stated so the registration can be exact.** These 843 rows were touched by
my Step-1 census: `id`, `fired_at`, `graded_at` existence, and counts. Never read on them:
`fwd_ret_1d/3d/5d`, `direction`, `ticker`, or any conditioning field. The set is
**metadata-inspected, outcome-untouched** — sound as out-of-sample, but that is the accurate
phrase rather than "unqueried."

---

---

## §2 · HANDLES AND TRIPWIRE (R-IV.138)

Computed and reported **before any outcome is read**.

**Three handles**

1. `fired_at < 2026-08-17 00:00:00Z`
2. `id < 305533` — sound **at pin vintage**, and cited as such
3. **Completeness identity** on `id ≤ 377783`:
   `audit_n + residue_pending + 843 = 7,014` — invariant under grading

**TRIPWIRE.** `audit_n ∈ [6,045, 6,099]` and `residue_pending ≥ 72`. Outside the bound →
**HALT, report, no computation.**

Rows with `id > 377783` are the **FUTURE cohort** and sit outside the identity entirely.

---

## §4 · BOUNDARY (EDGE ITEM-1 text, R-IV.138)

> The holdout boundary is a date boundary (fired_at ≥ 2026-08-17 00:00:00Z), so no
> fired-date contributes to both populations and no straddle rule is required. Pre-holdout
> rows are training data if and when graded, including the 55 stalled 08-14 rows; the
> artifact states n at execution vintage.

---

## §5 · k-CAPTURE — PENDING

`k` = index-symbol rows inside the 843. Capture AUTHORIZED (R-IV.140), one aggregate read.
**Result not yet received by this lane.** Effective validation n = 843 − k.

Single-regime caveat, binding on any read of this set: a failure here cannot separate
"no edge" from "not this regime" — **state both readings or neither**.

---

## §6 · NOT A KILL ON ITS OWN EVIDENCE (R-IV.146)

*The R-IV.140 wording did not survive the context-1 retirement. This text is authored
fresh by the successor spine and supersedes it — a ruling, not a reconstruction.*

A negative result on this holdout is **not, on its own evidence, a KILL** of the sweep
premise or of any pillar. Three grounds, each sufficient alone:

1. **SINGLE REGIME.** The set spans one fired-window (2026-08-17 → 08-31). A failure
   cannot separate "no edge" from "not this regime" — state both readings or neither
   (§5).
2. **NO REGISTERED CRITERION.** Validation n = 843 − k; no confirmatory criterion has
   been registered against this set, and none may be fixed after outcomes are read. An
   unregistered failure adjudicates nothing.
3. **REGISTERED ROLE.** KILL/survive semantics for the premise are pre-registered to the
   audit's explore population (H1 follow / H2 fade, R-IV.131 brief). This set's role is
   **CONFIRM material** for an edge the explore step surfaces — under its own CONFIRM
   registration, criterion fixed before any split.

**Symmetrically:** a positive result here cannot rescue a premise the audit killed, and
neither outcome on this set speaks to the untested pillars (dark-pool, absorption, tide,
timing) — the founding scope boundary binds.

---

## CHAIN OF RECORD

- CC-QUERY PIN capture, registered_at `2026-09-01 03:28:12.361091+00`
- R-IV.136 — filed as registration of record
- → EDGE §4 amendment (straddle clause struck: inert for purpose, wrong in side effect)
  → R-IV.138
- → R-IV.140 — §2 handles + tripwire, §6 clause ordered, census re-filed to
  `docs/edge/results/`
- → R-IV.145 — edit list relayed to CC-BUILD; applied except §6, whose text was not
  received
- → R-IV.146 — §6 authored fresh by successor spine (R-IV.140 wording lost with
  context 1)
