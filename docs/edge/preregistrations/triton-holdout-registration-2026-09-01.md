# TRITON — HOLDOUT REGISTRATION · 2026-09-01

Registration of record. PIN authored by CC-QUERY; amendments per R-IV.138 / R-IV.140.
The residue census that originally shipped with this PIN is re-filed to
`docs/edge/results/2026-09-01-triton-holdout-pin-and-residue-census.md` (R-IV.140).

**Section numbering note:** the artifact as originally filed carried PART 1 / PART 2,
not §1–§6. The ordered amendments address §2, §4 and §6, so the sections below are
numbered to give those amendments anchors. **§3 and §7 are intentionally vacant.** §1 is
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

## §5 · k-CAPTURE — CAPTURED (Amendment 1A)

**k = 15**, captured 2026-09-02 18:48:49Z: SPX 6 · SPXW 6 · RUTW 2 · VIX 1 · RUT 0.
Control: the same predicate returns 843 rows across 152 tickers, so 15 is a measurement,
not an empty result.

**EFFECTIVE VALIDATION n = 843 − 15 = 828.**

PERMANENCE IS INFERRED, NOT MEASURED — stated as the limit it is: these 15 are held
ungradeable by symbol class (0 of 72 same-symbol residue rows ever graded; all carry NULL
`prior_5d_ret`), not by a read of `prior_5d_ret` on the 15 themselves. That read sits
outside the R-IV.140 authorization and has not been taken. If it is ever taken and any of
the 15 carries a backward series, effective n rises accordingly.

ONGOING, not historical: 3 index-symbol rows have already entered the FUTURE cohort
(`id > 377783`). The coverage defect keeps producing rows; it is not closed by the pin.

Single-regime caveat, binding on any read of this set: a failure here cannot separate
"no edge" from "not this regime" — **state both readings or neither**.

**Amendment 1C — cross-reference.** The 72 index rows named in the residue census are
RESIDUE-SCOPED (`fired_at < 08-17`) and disjoint from this holdout. The table-wide index
population is **90: 72 residue · 15 holdout · 3 future cohort**. A scoped count is not a
population count — the two must not be netted or substituted for one another.

**Note for the record, no action:** the registration's caveat form worked as intended. §5
filed "effective validation n = 843 − *k*, *k* unknown" rather than assuming zero, so the
shortfall arrives as an expected quantity rather than a surprise at validation time. That
is the whole function of stating an unknown at registration.

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

## §8 · VALIDATION GATE (Amendment 1B — ADDED, see note)

*The registration carried no §8 and no gate clause. Amendment 1B is phrased as a
replacement; there was nothing to replace, so it is applied as an ADDITION. The text is
EDGE's, verbatim. Ratified as applied, R-IV.162.*

**LINEAGE, R-IV.184(c) — the note above describes the committed file accurately, and is
wrong about the lineage.** `docs/defects/R-IV.170d-ARCHAEOLOGY.md` recovered the context-1
draft (7,850 B, sha256 `b60518b7…`): it numbered its sections plainly, `## 1 ·` through
`## 10 ·` with no section sign, and **its §8 "Gates and counter" carried a GATE clause** —
*"validation use is gated on `DEF-TRITON-GRADER-DARK` remediation"*. The literal strings
`§7`/`§8` missed on grep because the draft never used the glyph, not because the sections
were absent.

All three §-anchored amendments were cut against **that** outline. So **Amendment 1B was
the replacement it claimed to be**; this file concluded otherwise because it was reading
the PIN-based rebuild, not the draft. The phantom outline was never phantom.

**Nothing was lost and nothing is reopened** — the committed version supersedes on content,
carrying every amendment through R-IV.162. The three-amendment anchor mystery is CLOSED,
on an artifact rather than on a recollection. It is also the worked example for
`verification-laws.md` §5: identity first, and a bare section number is not an anchor.

> **GATE:** validation use is gated on `DEF-TRITON-GRADER-DARK` remediation AND on the
> holdout being graded **except the enumerated ungradeable set (k = 15,
> SPX/SPXW/RUTW/VIX)**. A "fully graded" condition is unsatisfiable by construction and
> must not be used as the trigger. Effective validation population at trigger: **828**.

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
- → R-IV.162 — Amendment 1 ratified as applied — §5 k captured (k=15, effective n=828), §8 gate ADDED, §5 cross-reference appended
