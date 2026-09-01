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
