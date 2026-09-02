# Board conventions

Rules that generalize past the incident that produced them. Each entry names its origin
and, where one exists, a worked example — a convention without a worked example is a
slogan.

---

## A header states settled buckets only

**R-IV.136(c), generalized. Two instances.**

Where a series is bucketed by period, a header count describes **settled** buckets. The
current bucket is **PARTIAL by default, not by exception** — it is incomplete by
construction until its period closes, and a reader must not have to infer that from
context.

This is not a caveat to add when someone notices; it is the default state of the newest
bucket in every such rendering. A header that silently includes a partial bucket
understates or overstates without ever being wrong on its face, which is why it survives
review.

---

## A PERIOD AVERAGE IS NOT A DAILY BAND

**EDGE-authored. Worked examples: ARTEMIS_LONG, crypto_scanner.**

Expected-rate bands derive from **observed daily distributions**, never from a period
total divided by its days. Below the n-gate they render **INSUFFICIENT**, never a number.

A period average and a daily band answer different questions, and the average's narrowness
is an artifact of aggregation rather than a property of the series. Dividing 622 rows by
their 41-day span yields ≈15/day and looks like a band; the days themselves ran
`20 · 5 · 10 · 23 · 13 · 12 · 30 · 11`. **One of eight days fell inside the derived band**,
with a 6× spread across the range — not a band with outliers, a band that fails to
characterize the series it claims to describe.

**Worked examples**

- **ARTEMIS_LONG** — band ≈15–20/day, derived as a period average from 622 rows over
  07-03 → 08-17. Measured d0–d7: `20 · 5 · 10 · 23 · 13 · 12 · 30 · 11`. **1 of 8 in
  band.** WITHDRAWN by its author.
- **PULLBACK_ENTRY, CTA arm** — band ≈7–16/day; observed `17 · 20 · 17`, all above.
  Flagged same class.
- **crypto_scanner** — the inverse failure, and the reason this convention has teeth: a
  rate stated without its distribution cannot tell a live emitter from a dying one. Its
  daily counts decayed `161 → 93 → 47 → 14` before stopping entirely; any period average
  over that window would have described none of those days.

Both re-derivations live in SPEC-01's watermark work, from observed daily distributions,
n-gated.

**Why it matters beyond tidiness.** An expected-rate band is the instrument that decides
whether an absence is a defect. A band that does not characterize its series will call a
healthy day anomalous and a dead day normal — and per the absence law, *an absence dates
nothing until you establish the expected event rate across it*. A wrong rate is worse than
no rate, because it licenses a conclusion.

---

## SCOPE BY A COLUMN THAT SPANS THE WINDOW

**R-IV.151(b). Worked example: the Triton element census.**

A column populated from date X **cannot scope a query whose window opens before X**.
Absence seen through such a filter is a **population-boundary artifact, not a
measurement** — the rows are there; the filter cannot see them.

This is inference-from-absence, mechanized. The query returns a smaller number, no error,
and every downstream reader takes the shortfall for a finding about the world.

**Worked example.** `source` was populated from 2026-07-21. Filtering
`source = 'footprint'` returns **148 of 558 rows (27%)** — reading four months of live
history as absent. `strategy` and `signal_type` span the full window and return **558**.
Same population, same question, three columns; two answer it and one reports a boundary.

**The check, before any scoped query is trusted:** establish that the scoping column is
populated across the whole window, not merely present in the schema. A column's existence
says nothing about its coverage, and `NOT NULL` on new rows is compatible with NULL on
every old one.

Kin to the absence law — *an absence dates nothing until you establish the expected event
rate across it* — and to the vacuous-column family, where a filter that matches nothing
runs clean and returns something shaped like an answer.

## AN AMENDMENT CITES THE BYTES IT CHANGES

**R-IV.162(e).**

Every **replacement** quotes the exact text it replaces, verified against the filed blob at
cut time. Every **addition** declares ADDITION and names its insertion point by quoted
neighbor text. **Bare section numbers are not anchors.**

**Worked example.** Three amendments in one week — §4 (R-IV.138) · §6 (R-IV.145) · §8
(Amendment 1B) — were cut against a section numbering the filed artifact never had. Each
converted a replacement into a stop or an improvised insertion: §4 had nothing to replace and
forced a restructure, §6's clause text never arrived and the section was opened as a
placeholder, §8 did not exist and the gate was applied as an addition with the substitution
flagged on its face.

The failure is not that the amendments were wrong — their content was correct every time. It
is that a bare section number cannot be verified before the cut, so the mismatch surfaces at
apply time in the receiving lane rather than at authoring time in the sending one.

Origin: R-IV.162.
