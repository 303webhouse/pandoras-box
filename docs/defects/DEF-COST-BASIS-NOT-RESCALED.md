# DEF-COST-BASIS-NOT-RESCALED

**Severity:** P1 — **live risk understated** · **Filed:** 2026-09-15 (R-IV.397(d)) · **Status:** OPEN
**Author:** CC-POSITIONS — sole author under convention #9.
**Surface:** `unified_positions.cost_basis` on option rows
**Sibling:** `DEF-HUB-MAXLOSS-OPTIONS` — same mechanism, different column.

## THE DEFECT

**Ten option rows store a `cost_basis` that disagrees with `quantity × entry_price × 100`, and
nine of them disagree by an exact factor.** Measured across all 264 option rows (175 consistent,
74 uncomputable):

| id | ticker | stored | qty × price × 100 | ratio |
|---|---|---|---|---|
| 50 | XLF | 25.50 | 51.00 | **0.5000** |
| 51 | AMZN | 24.00 | 48.00 | **0.5000** |
| 300 | XLF | 58.20 | 116.40 | **0.5000** |
| 301 | XLF | 33.04 | 66.08 | **0.5000** |
| **355** | **QQQ** | **112.40** | **224.80** | **0.5000** |
| **356** | **QQQ** | **21.40** | **42.80** | **0.5000** |
| 360 | TSLA | 106.28 | 212.56 | **0.5000** |
| 131 | ONON | 130.00 | 65.00 | **2.0000** |
| 343 | DRAM | 70.00 | 35.00 | **2.0000** |
| 347 | XLE | **0.00** | 29.00 | **0.0000** |

**Exactly 0.5× or exactly 2.0× is not a fee.** Fees move a basis by cents — the four fee-family
rows found in the same census differ by at most **$0.17**. A factor of two is **quantity changed
without basis following**: the same failure `DEF-HUB-MAXLOSS-OPTIONS` records for `max_loss`,
occurring independently on `cost_basis`.

Several carry a `BLENDED-UNRECORDED` note saying so outright — *"qty raised from RH activity CSV
8/24; entry_price/cost_basis left at original vintage."* **The note documents the defect and the
row was left in it.**

## WHY P1 — two live rows

**ids 355 and 356 are the QQQ 10/16 tails that D4 rules don't-close.** Both store **half** the
basis their quantity implies. If the derived figures are right, the standing tail position cost
**$133.80 more** than the book says, and every risk and return figure computed over it is
understated by half. These are not history — they are the book's standing downside hedge.

**id 347 XLE stores `cost_basis` 0.00** — a position recorded as acquired for nothing, so any
percentage return over it is undefined or infinite.

> **CORRECTED 2026-09-15 (R-IV.400(b)): id 347 is CLOSED, not live.** `POS_XLE_20260707_06000002`,
> call_spread 60/65, expiry 08-21, closed **2026-07-31** with realized +53.90. It therefore
> contaminates **realized and historical aggregates**, not live exposure, and **is not in the D5
> sleeve**. The original wording here said "any sleeve or exposure sum treats it as free," which
> implied a live row. **ids 355 and 356 are the live ones; 347 is history.** The zero almost
> certainly arrived through the partial-CLOSE path — the row's own note records
> *"Partial close 1/2 @ 0.58"* — which is the same non-rescaling mechanism, driven to zero
> rather than to half.

## ADJUDICATION — ALL TEN **UNRESOLVED**, and the reason is worth recording

R-IV.397(d) requires each row to carry an export line or an explicit UNRESOLVED mark before
anything is written. **A first adjudication pass produced a number for all ten. Those numbers
are wrong and are not filed.** Three defects in the matcher, each of which produced
*plausible* output:

1. **Legs dropped.** Candidate lines were filtered by strike, so on a vertical only the leg whose
   strike matched survived. id 355 came back "632.00" from the long 510P alone, with the short
   500P silently excluded — a basis inflated by the entire credit leg.
2. **Cross-file double counting.** `3b84f64e-…csv` is a **complete subset of `rh-8.31.2026.csv`
   — all 61 of its lines appear in both.** Any pass reading both counts those fills twice.
3. **Partial baskets.** Multi-fill positions were resolved to a single "best day" cluster, so
   id 300 (qty 8) was adjudicated from one 1-lot fill.

**Every one of those produced a confident-looking figure.** Filing them would have replaced a
known-wrong basis with an unknown-wrong basis and marked it BROKER_VERIFIED. **All ten are
staged UNRESOLVED**, with candidate export lines retained as leads in
`data/staging/stage_basis_adjudication.csv`.

**Correct adjudication needs the leg model.** A vertical's basis is the net of two legs; no
matcher that works one leg at a time can compute it. This defect's resolution therefore
**depends on the lots/legs build**, not merely on an export.

## WHAT THIS MEASUREMENT ALSO ESTABLISHED

**Composite field keys cannot dedup Robinhood fills — measured, not argued.** Byte-identical
repeated lines within one export: **94 collisions in `rh-8.31.2026.csv`**, 8 in the September
export, including two identical VIX 10/21 legs on 09-11 and three identical XLF legs on 09-01.
These are **real separate fills**, not duplicates. Confirms R-IV.397(b): the fill identity is
**(export file sha256, line number)**, never a composite of the fields.

## WHAT IS NOT ESTABLISHED

- **Which direction each row is wrong.** A 0.5× ratio is equally consistent with a doubled
  quantity or a halved basis. **The ratio says they disagree; it does not say which is right.**
- **Whether the population is ten.** 74 option rows are UNCOMPUTABLE — a NULL in the inputs — and
  cannot be tested at all. The ten are the ten *detectable* instances.
- **Cause.** Not proposed. `BLENDED-UNRECORDED` notes on some rows describe *when* it happened,
  not what wrote it.

## REMEDY

**Recompute-on-write**, jointly with `DEF-HUB-MAXLOSS-OPTIONS` — a derived quantity that is
stored and then maintained by event handlers will drift on whichever event type nobody fixed.
Covering `cost_basis` and `max_loss` together is the test of the fix.

**Nothing is written until each row has an export line resolved through the leg model, or an
explicit UNRESOLVED mark that survives into the migration.**

## STATUS

Registration only. **No row corrected. All ten UNRESOLVED.** Trade Analysis is told that ids
355 and 356 display a basis that is under review.
