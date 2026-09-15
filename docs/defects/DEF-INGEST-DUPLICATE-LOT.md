# DEF-INGEST-DUPLICATE-LOT

**Severity:** P1 · **Filed:** 2026-09-15 (R-IV.387(b)) · **Status:** OPEN
**Author:** CC-POSITIONS — sole author under convention #9.
**Surface:** the position write path — whatever ingests broker fills into `unified_positions`
**Class:** silent corruption. Not a missing row; a row that is **present, plausible, and wrong**.

## THE DEFECT

**One broker fill was ingested twice, and the duplicate was absorbed into a single row's
quantity and basis rather than appearing as a second row.**

Confirmed instance — **id 409, SOXS, FIDELITY_ROTH.**

```
 BROKER (Fidelity confirmations)          HUB (as originally written)
   09-03  10 @ 51.5850  =   515.85          qty 30
   09-04  10 @ 46.6601  =   466.60          cost_basis 1,498.30
   ------------------------------          avg 49.9433
   20 shares        =   982.45
                        avg 49.1225

 1,498.30  =  515.85 × 2  +  466.60        <-- the 09-03 lot, counted TWICE
```

The arithmetic is exact. **Ten shares that never existed sat in the book for twelve days**
(2026-09-03 → 09-15) carrying $515.85 of basis that was never spent.

## WHY THIS IS P1 AND NOT A TIDYING ITEM

A duplicated fill does not look like an error from inside the database:

- the row **balances** — `cost_basis` really is `qty × entry_price`
- the quantity is **plausible** — 30 is a reasonable size for this account
- the average price is **plausible** — 49.9433 sits between the two real fills
- **no orphan, no imbalance, no NULL** — every integrity check passes

It is only detectable by **comparing the row to the broker**, which is the same instrument
`DEF-EXPORT-COVERAGE-GAP` says was unavailable for September until 2026-09-15. The defect and
the thing that detects it were mutually blocked for twelve days.

**It also inflates sizing.** The tracked book carried $515.85 of phantom basis, against a D5
sleeve cap of $3,850 — a 13% phantom against the cap that governs whether new positions may
be opened at all.

## WHAT IT CONTAMINATED

Every downstream figure derived from the bad quantity inherited it:

- **`max_loss` 1,547.70** — the scale-IN handler multiplied the first lot's price by `30/10`.
  The handler did exactly what it was written to do; its **input** was corrupt.
- **Two published decompositions** reasoned from `qty = 30` and are superseded — see
  `DEF-HUB-MAXLOSS-OPTIONS` → *SUPERSEDED BY THE EXPORT*.
- **A conditional annotation** on `DEF-RH-COVERAGE-GAP` asked whether a 10-share sale had gone
  unlogged. It resolves **NEGATIVE**: the ten shares were never bought, so they were never
  sold. **A duplicate masqueraded as a departure.**

That last one is the general lesson. **An over-count and an unlogged closure look identical
from inside the book** — both present as "the quantity does not match what I expect." Only the
broker artifact separates them, and the two have opposite remedies: one deletes, one inserts.

## WHAT IS NOT ESTABLISHED

- **The write path.** Which ingest produced the duplicate is untraced — the row's `source` is
  `MANUAL` and no importer is named. That trace is BUILD's.
- **Whether it is a singleton.** One instance is confirmed. **No census has been run**, and the
  detection instrument (a broker export covering the fill date) exists for only one month of
  one account. Any claim that this is rare is currently unsupported.
- **Whether the mechanism is retry, double-submit, or re-ingest.** Not proposed.

## REMEDY

**A uniqueness constraint on the fill, not on the position.** The duplicate survived because
the write path has no notion of "this fill is already recorded" — it merged into an existing
row instead of colliding with one. The ledger build's `position_lots` model is where that
constraint belongs: one row per fill, keyed on broker reference, so a second ingest of the
same confirmation **fails loudly instead of adding quantity**.

Note the two Fidelity confirmations carry reference numbers (`26246-P2JS0Y`, `26247-N18WRY`)
and order numbers. **The uniqueness key already exists in the artifact**; nothing in the book
stores it.

## STATUS

Registration only. **id 409 was corrected under R-IV.312(c) and is now BROKER_VERIFIED at
20 @ 49.1225, basis $982.45.** No census, no trace, no write-path change authorized here.
