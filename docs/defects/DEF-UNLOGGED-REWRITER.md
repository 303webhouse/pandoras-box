# DEF-UNLOGGED-REWRITER — OPEN

**Registered:** R-IV.428(e). **Origin:** the resolution of `DEF-3-10-CALIBRATION-NONREPRODUCING`.
**Filed by:** CC-BUILD from the ruling; the counts below are CC-QUERY's and are not re-measured here.

---

## THE STATEMENT

> **Something rewrites outcome rows in place and leaves no record of doing it.**

The 3-10 population was rewritten by two known passes — Phase B (2026-05-08) and Phase C
(2026-05-10/11) — and rolling past Phase B reproduces the published figure exactly. **But two
counts still do not reconcile after both known passes are accounted for, and no writer has been
found that explains them.**

## WHY IT IS ITS OWN ENTRY

A known rewrite is a history problem: the figure can be reproduced by rolling to the right point.
**An unknown rewriter is a live problem:** every figure computed from these tables can move again
with no code change and no log line, which is the failure the calibration clause (Addendum 3)
exists to make detectable.

## WHAT CLOSES IT

1. **Name the two counts** on this entry, with the queries that produce them (CC-QUERY).
2. **Enumerate every writer** of the affected tables — code paths, scripts, one-off backfills —
   and match each to a logged run. A writer with no run record is the suspect.
3. **Until then, any figure derived from the affected rows carries its read time**, so a later
   change is at least visible as a change.

## RELATED

`DEF-ADJUSTED-BARS-VS-RAW-ENTRY` — a second mechanism by which stored outcomes change value
without a row being touched by a known job.

## Status: OPEN — the two counts to be named on this face by CC-QUERY.
