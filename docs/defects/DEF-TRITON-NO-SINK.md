# DEF-TRITON-NO-SINK — two defects, one class

**Registered:** 2026-09-02 (R-IV.156). **Fixes HELD** per R-IV.152 — registration is
bookkeeping; the defects exist regardless and are recorded so they cannot be rediscovered
as new.

Both are the same shape: a Triton pillar **computes a value that nothing persists.** The
component works; the output evaporates. Neither is a crash, neither logs an error, and
neither is visible from any surface that reads the pillar — which is why both survived
until a census went looking.

---

## DEF-TRITON-DARKPOOL-NO-SINK · P2

`darkpool_enrichment.py` computes and returns a dict **that no caller persists.**

- `signals` has **no metadata column** to receive it.
- The natural sink, `enrichment_data`, **exists** and has **never received a dark-pool
  key** — established by census **with a KNOWN-PRESENT control**, so the empty result is
  a measurement rather than a query that could not have found anything.

**History is irrecoverable for the unsunk period.** This is the part that fixes severity
at P2 rather than P3: a sink added today starts accumulating today, and every dark-pool
enrichment computed before that point is gone. The defect's cost grows with every day it
stays open, and no later fix recovers it.

**QUANTIFIED (R-IV.162, carried from R-IV.160.7).** Measured by CC-QUERY's
`TRITON-K-CAPTURE-AND-BURN-SWEEP`, filed at
`docs/edge/results/2026-09-02-triton-k-capture-and-burn-sweep.md`:

| path | calls | days active | rate | share of metered spend |
|---|---|---|---|---|
| `darkpool_ticker` — **this defect** | **12,320** | 49 | **~251/day** | **2.19%** |
| `market_tide` — `DEF-TRITON-TIDE-NO-SINK` below | 2,926 | 41 | ~71/day | 0.52% |
| **combined, both unsunk paths** | **15,246** | — | — | **2.7%** |

Window **2026-07-09 → 2026-09-01**, against `_TOTAL` 562,421 metered UW calls.

**The 15,246 figure spans BOTH no-sink paths — it is not this defect's count.** This
defect's own count is **12,320**. The combined figure is carried here because the sweep
measures both in one read and the relay states them together; it must not be cited as the
dark-pool total.

**ACCRUING, NOT HISTORICAL.** The window closes at the measurement, not at the defect — the
calls are still being made and still not sunk. Every figure above is a floor that rises while
this stays open.

**Denominator caveat, from the source:** the named callers sum to 562,415 against `_TOTAL`
562,421 — a 6-call gap, so `_TOTAL` is maintained independently rather than as an exact sum
of parts. The percentages are accurate to ~0.001%, but `_TOTAL` is not a derived figure.

The founding design lists `darkpool_enrichment` as **SHADOW ONLY** — `confluence_bonus=0`,
annotates never scores. That is why it was never noticed: an annotation nobody scores on
is an annotation nobody misses. It is also the top rung of the data-fidelity ladder
(dark-pool prints > footprint > tape > 1-min POC proxy), so the unsunk data is the
highest-quality evidence the ladder defines.

---

## DEF-TRITON-TIDE-NO-SINK · P3

`get_market_tide()` **live-fetches to Redis with a 60s TTL** and serves **ten-plus
consumers**. There is **zero Postgres persistence.**

Loss is **historical queryability only** — the current value is always available, and
every consumer reading it now reads a real number. Nothing is wrong with the live path.
What does not exist is any way to ask what the tide *was*.

P3 rather than P2 on that distinction: no live surface is degraded, and no decision made
today is worse for it. The cost is that tide can never be a conditioning field in a study
of the past, and any such study would have to start collecting first.

**Candidate sink `uw_snapshots`, under OLYMPUS-TRITON evaluation.** Not chosen here.

---

## Why one document

These are two defects, not one — separate IDs, separate severities, separate surfaces —
but a single class, and the class is the useful unit for whoever fixes them. A sink
decision for one informs the other, and splitting them would hide that.

Contrast `DEF-TRITON-GRADER-NO-SKIP-REASON`, which was deliberately **not** folded into
`DEF-TRITON-GRADER-DARK`: those share a surface but not a class, and folding a P3 into a
P1 would have let it ride the P1's urgency while blurring the P1's cause. Here the
grouping runs the other way — same class, and neither inherits the other's urgency
because both are held.

## Class note for the 09-15 supervision brief

Compute-then-discard, fourth and fifth instances, after `active_weight_sum`, the
`UWUnavailable` sentinel at the flow-poller call site, and per-row `is_stale` in
`total_balance`. The family's signature: **the information exists at the point of failure
and is thrown away**, so nothing downstream can detect the loss — there is no error to
catch and no gap to measure, only an absence that looks like a design.
