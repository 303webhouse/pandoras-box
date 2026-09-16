# LOTS / LEGS — THE DATA HALF

**R-IV.395 · CC-POSITIONS · 2026-09-15 · READ-ONLY.** No schema writes, no DDL, no live-table
writes. Five staged files produced for BUILD's migration to consume.

| provenance | value |
|---|---|
| **DB read** | 2026-09-15, `unified_positions`, **374 rows** (every row, all statuses) |
| **Exports consulted** | `rh-8.31.2026.csv` (2025-12-09 → 08-31) · `3b84f64e-…csv` (08-17 → 08-25) · `3c8dbee9-…csv` (09-01 → 09-14) |
| **Confirmations consulted** | Fidelity, confirm dates 09-01 · 09-02 · 09-03 · 09-04 · 09-08 |
| **Staged output** | `data/staging/` — 5 CSVs, **UNTRACKED**, see the warning below |

> ## ⚠ THE STAGED FILES ARE UNTRACKED AND SHOULD STAY THAT WAY UNTIL RULED
>
> `data/staging/` is **not gitignored**, so `git add` would commit it. **This repository is
> public.** The five files together are a complete dump of the book — every position, quantity,
> entry price, cost basis and account label, 374 rows.
>
> That is a materially larger exposure than the defect documents already committed, which cite
> individual rows inside narrative. `data/imports/` is gitignored for exactly this reason.
>
> **Left untracked deliberately.** Either gitignore `data/staging/` alongside `data/imports/`,
> or hand BUILD the files out of band. **Not a decision for this lane** — flagged, not acted on.

---

## (a) LOT BACKFILL — dry run

**374 positions → 374 synthetic lots** (`stage_lots.csv`), one per position, fields as ordered:
`position_id · lot_seq · quantity · price_gross · basis_gross · basis_stored · fee_delta ·
fill_time · provenance · source=BACKFILL_FROM_POSITION`.

### Both invariants hold

```
 every position has >= 1 lot ......... PASS   violations: none
 sum(lot qty) == row qty ............. PASS   violations: none
```

**These pass trivially and that is worth saying plainly.** One synthetic lot per position
cannot violate either invariant by construction — the lot's quantity *is* the row's quantity.
**The invariants become meaningful only after real fills replace the synthetic lots**, when a
position may have two lots that must sum correctly. As run here they confirm the generator, not
the data.

### Four rows cannot form a complete lot

| id | ticker | status | why |
|---|---|---|---|
| 368 | SOXS | CLOSED | `entry_price` NULL — lot has no price |
| 369 | BITX | CLOSED | `entry_price` NULL |
| 370 | SQQQ | CLOSED | `entry_price` NULL |
| 371 | HYG | CLOSED | `entry_price` NULL |

All four are closed, so they block history rather than live state. They need a price from an
export line or an explicit UNKNOWN lot — **not a zero**.

---

## (b) BROKER_REF CAPTURE — and a structural gap

`stage_broker_refs.csv`, 374 rows.

| population | count | ref available |
|---|---|---|
| September rows | 27 | **6** — Fidelity confirmation reference + order number |
| …of which Robinhood | 18 | **0** |
| pre-September rows with an entry date | 347 | export line exists for **274**; **73** have none |

### The Robinhood export has no reference column at all

Its nine columns are `Activity Date · Process Date · Settle Date · Instrument · Description ·
Trans Code · Quantity · Price · Amount`. **There is no fill id, order id or confirmation
number anywhere in the artifact.**

**This undercuts `DEF-INGEST-DUPLICATE-LOT`'s remedy on the Robinhood side.** That defect
proposes a uniqueness key on the fill, and observes that Fidelity confirmations already carry
one (`26246-P2JS0Y`, `26247-N18WRY`). **Robinhood supplies no such key.** A uniqueness
constraint there must be built from a composite — date + instrument + trans code + quantity +
price + amount — which is not guaranteed unique: the 09-01 XLF export contains **two
byte-identical three-leg fills on the same date**, and the 09-09 NVDA fills likewise. A
composite key would reject the second as a duplicate when it is a real second fill.

**Stated as a constraint on the remedy, not a solution.** The Fidelity path can be keyed on the
artifact; the Robinhood path cannot, and needs either a different key or an accepted-collision
rule.

---

## (c) STRUCTURE CENSUS — 264 option rows

`stage_structure_census.csv`. Each row carries `legs_as_stored`, `shape`, `target_legs` and
`came_from` for the migration map.

| shape | rows | meaning |
|---|---|---|
| `SINGLE_VERTICAL` | **225** | two strikes, one row — migrates to 2 legs |
| `SINGLE` | **32** | one strike — migrates to 1 leg |
| `SPLIT` | **3** | ids **300 · 301 · 420**, all XLF 10/16 |
| `COMBINED_3LEG` | **1** | id **415** NVDA — third leg in `notes` only |
| `UNKNOWN` | **3** | ids **130 SMH · 131 ONON · 132 IWM** — `structure` NULL **and no strikes at all** |

### The XLF group holds both conventions at once

ids 300, 301 and 420 share ticker, expiry and account. Grouping by that key returns a vertical
(300), a single (301) **and** a combined 3-leg row (420) in the same bucket. **`DEF-STRUCTURE-
STORED-TWO-WAYS` is not two rows disagreeing across the book — it is one position group
internally storing itself two ways simultaneously.** Any migration keyed on ticker+expiry hits
this group first and has no rule for it.

### The three UNKNOWN rows have no structure to migrate

130, 131 and 132 carry `structure` NULL, `long_strike` NULL and `short_strike` NULL, on rows
typed `OPTION`. **There is nothing to convert into legs.** They need a source read before the
migration touches them, or explicit exclusion.

---

## (d) GROSS / NET — the P0.6 census

`stage_gross_net_p06.csv`, 264 option rows, testing `cost_basis` against
`quantity × entry_price × 100`.

```
 CONSISTENT (stored == qty x price x 100) ....... 175
 INCONSISTENT ...................................  15
 UNCOMPUTABLE (a NULL in the inputs) ............  74
 adjudicable against an export on disk .......... 206 of 264
```

### The 15 are two different defects, not one

| id | ticker | stored | derived | delta | ratio | family |
|---|---|---|---|---|---|---|
| 38 | META | 173.00 | 173.01 | −0.01 | 0.9999 | **fee / net basis** |
| 109 | IGV | 85.09 | 85.00 | +0.09 | 1.0011 | **fee / net basis** |
| 110 | SPY | 180.17 | 180.00 | +0.17 | 1.0009 | **fee / net basis** |
| 130 | SMH | 178.11 | 178.00 | +0.11 | 1.0006 | **fee / net basis** |
| 50 | XLF | 25.50 | 51.00 | −25.50 | **0.5000** | qty-basis desync |
| 51 | AMZN | 24.00 | 48.00 | −24.00 | **0.5000** | qty-basis desync |
| 300 | XLF | 58.20 | 116.40 | −58.20 | **0.5000** | qty-basis desync |
| 301 | XLF | 33.04 | 66.08 | −33.04 | **0.5000** | qty-basis desync |
| **355** | **QQQ** | **112.40** | **224.80** | **−112.40** | **0.5000** | qty-basis desync |
| **356** | **QQQ** | **21.40** | **42.80** | **−21.40** | **0.5000** | qty-basis desync |
| 360 | TSLA | 106.28 | 212.56 | −106.28 | **0.5000** | qty-basis desync |
| 131 | ONON | 130.00 | 65.00 | +65.00 | **2.0000** | qty-basis desync |
| 343 | DRAM | 70.00 | 35.00 | +35.00 | **2.0000** | qty-basis desync |
| 310 | XLE | 110.00 | 132.00 | −22.00 | 0.8333 (5/6) | other |
| 347 | XLE | **0.00** | 29.00 | −29.00 | **0.0000** | **ZERO BASIS** |

**Only four rows are the P0.6 question.** META, IGV, SPY and SMH differ by cents — stored
basis includes fees, i.e. **net where the convention is gross** (R-IV.312(a)). Those are the
normalization targets and the fee deltas are staged per row.

**Nine rows are a different defect entirely.** Sitting at **exactly 0.5× or exactly 2.0×** is
not a fee — it is **quantity changed without basis following**, the same mechanism
`DEF-HUB-MAXLOSS-OPTIONS` records for `max_loss`, now measured on `cost_basis` across nine
rows. Normalizing these as if they were fee deltas would write a fabricated number.

### Two rows that need naming before any migration

**ids 355 and 356 are the QQQ 10/16 tails** that D4 rules *don't-close*. Both store **half**
the basis their quantity implies — 112.40 against 224.80, and 21.40 against 42.80. **If the
derived figures are right, the standing tail position cost twice what the book says**, and
every risk figure over it is understated by half. These are **live rows**, not history.

**id 347 XLE stores `cost_basis` 0.00** against a derived 29.00. A zero basis reads as a
position acquired for nothing — fake-healthy in the flattering direction, and it will produce
an infinite or undefined return in any percentage calculation.

**Neither is corrected here.** Both need an export line, and 206 of 264 option rows are
adjudicable against an export on disk — these two are in scope for that read, which is not
this pass.

---

## WHAT THIS PASS DID NOT DO

- **No schema writes, no DDL, no live-table writes.** Five CSVs, one document.
- **No lot was written.** The staged lots are a dry run; nothing entered the database.
- **The invariants were not tested in anger** — see (a).
- **The gross/net question is answered for 4 rows and open for 74** that carry a NULL in the
  inputs and cannot be computed at all.
