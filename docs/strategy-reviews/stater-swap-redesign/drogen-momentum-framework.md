# Drogen Momentum Framework — Recovery Note

**Provenance:** recovered from the 2026-05-22 session record. This file was referenced by the Stater Swap v2 committee brief (`docs/strategy-reviews/stater-swap-redesign/2026-07-12-stater-swap-v2-committee-brief.md`, Part 1) as "never committed" — the path 404'd in the repo. Content below is reconstructed from the session record only; nothing here is elaborated beyond what that record documents. Per `PROJECT_RULES.md`'s bar on authoring crypto methodology "from general pretrained priors," this note is deliberately terse where the source record was terse — it is not padded out with invented detail.

**Status:** framework note only. Not implemented. Drogen Module B is explicitly **deferred** per the committee brief's R-3 recommendation stack (capital-constrained and architecturally overlapping a queued THALES module) — see committee brief Part 4. Modules A and C are recovery items for future R-stack phases to build from, not S-1 deliverables.

---

## Module A — BTC 50-DMA regime filter

A trend-regime classifier gating which strategies may fire, based on BTC's price relative to its 50-day moving average. This is the module the committee brief's PYTHAGORAS seat explicitly built on for the R-1 regime classifier recommendation ("BTC regime gate: Drogen Module A (50-DMA) upgraded with ADX and DMA slope, mirroring the shipped equity regime classifier"). R-1 is the build target for this upgrade; this note is the recovered origin point, not the R-1 spec itself.

## Module B — Cross-sectional momentum (DEFERRED)

Long the top 20% / short the bottom 20% of a crypto universe ranked by 30-day return. Per the committee brief's Pass-2 resolution (#3): this hypothesis is **deferred**, not rejected — it stays out of scope until capital constraints ease and/or the queued THALES sector-rotation-style module (which overlaps architecturally) is resolved one way or the other. Do not build Module B without a fresh Titans pass revisiting this deferral.

## Module C — Broken-parabolic short

A short-side pattern on assets that have gone parabolic and then broken structure. Per the committee brief: **already handled at prompt level** (i.e., in the Olympus committee agent prompts, not as a standalone coded strategy). The committee brief's URSA seat ties this directly to ZEC's specific risk profile ("post-parabolic structure after the late-2025 run means broken-parabola dynamics (Drogen Module C class) are the operative pattern — rips into prior supply are suspect" — Addendum A-4). Relevant to R-1+ symbol-specific gating for ZEC, not a new build in itself.

---

## Relationship to the R-stack

None of these three modules are S-1 (foundation) deliverables. They are recorded here so R-1 (regime/session layer) and any future strategy-portfolio phase have the original framework to build from, per the committee brief's instruction: "the recovered Drogen framework note" is a **recovery item**, distinct from and prerequisite to the R-1/R-3 work that consumes it.
