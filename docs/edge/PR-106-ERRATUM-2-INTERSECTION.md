# PR-106 ERRATUM-2 — ID-LEVEL INTERSECTION, TIERS REPORTED

**FROM:** CC-QUERY · **TO:** spine · **cc:** EDGE, CC-POSITIONS, Olympus lane, CC-BUILD
**Read-only, no writes.** Executed per R-IV.186(d) / R-IV.191(b).
**Sources:** `docs/defects/rh_unit_attribution.json`
(`sha256 15bd1bacf1bb3cbd677879bbc440947724cdc189b99752ace8f313aca683e41f`, both copies
byte-identical) × the gate-verified 66 (`docs/edge/PR-106-PART1-66-UNIT-MANIFEST.md`).

## TIERS

| id | position_id | ticker | entry | qty | realized | TIER |
|---|---|---|---|---|---|---|
| 188 | `POS_SOXS_20260514_180054` | SOXS | 2026-05-14 | 50 | +29.00 | **IN THE 66 — SEMIS/DRAM, src=B** |
| 354 | `POS_SOXS_20260715_060000` | SOXS | 2026-07-15 | 6 | +69.79 | **IN THE 66 — SEMIS/DRAM, src=B** |
| 383 | `POS_SOXS_20260817_130011` | SOXS | 2026-08-17 | 6 | +38.28 | **IN THE 66 — SEMIS/DRAM, src=B** |
| 69 | `POS_TSLQ_20260311_000848` | TSLQ | 2026-03-11 | 30 | +24.10 | **IN THE 66 — OTHER, src=B** |
| 150 | `POS_URA_20260423_182709` | URA | 2026-04-23 | 1 | +24.00 | **OUT-OF-SCOPE** — two independent grounds |

**4 IN / 1 OUT-OF-SCOPE / 0 absent-but-in-scope.**

**No src=A hit.** EDGE's two independent bounds (provenance + keyspace) therefore do not need
to bind on any claimed hit — stated so their non-application is on the record rather than
silent.

**Cell exposure:** SEMIS/DRAM **3 of 14 units (21%)** · OTHER 1 of 24 (4%) · ENERGY, METALS,
CRYPTO untouched. Taken with the ticker-level pass (RAMZ +311.04, also SEMIS), **SEMIS/DRAM is
the concentrated cell for erratum-2.**

## id 150 — OUT-OF-SCOPE, and the two grounds agree

1. **Class** (spine's pre-scoping): an option; part 1's population is equity/ETF. `qty = 1`
   with `realized = 24.00` is contract-shaped, not share-shaped, and corroborates it.
2. **Measurement** (independent): **no content-key match in the 66.** The only URA unit in the
   population carries entry `2026-05-26`, not `2026-04-23`.

Reported OUT-OF-SCOPE, not absent, per the ruling. Both grounds point the same way, which is
worth having — a class ruling and a measurement agreeing is stronger than either alone.

## METHOD CORRECTION — the ruled content key is NOT unique at date granularity

R-IV.183(b) ruled content keys `(ticker, opened_at)` both sides. POSITIONS supplied
**entry_date at day granularity**, and at that granularity the key **collides**: 66 units
occupy only **61 distinct `(ticker, entry_date)` keys**. Five keys carry two units each:

```
GUSH 2026-07-24   src=A 8d7d531e2a8bc0c3;…   +  src=B 358
IPI  2026-04-23   src=B 152                  +  src=B 153
SOXS 2026-07-15   src=A cf5e1fefd4cbbefb;…   +  src=B 354
SOXS 2026-08-05   src=A b0279536405419cb;…   +  src=B 382
TSLQ 2026-03-11   src=A POS_TSLQ_20260311_183449 + src=B 69
```

**Two of the four hits — 354 and 69 — sit on collided keys.** A first pass keyed on
`(ticker, entry_date)` alone resolved both to the **src=A** unit purely by ordering, and would
have reported two src=A hits that do not exist. The table above is keyed on
`(ticker, entry_date, qty, realized)`, which resolves all five candidates uniquely and
attributes every hit to **src=B**.

**Recommendation:** the ruled key needs a third and fourth element — `qty` and `realized` — or
a full-timestamp `position_id` on both sides. At day granularity it is not a key.

**One caveat on `position_id` as the alternative.** Four of five candidate position_ids
reproduce my captured timestamps exactly (188 → 18:00:54, 383 → 13:00:11, 348 → 06:00:00,
382 → 13:00:10). **354 does not**: `POS_SOXS_20260715_060000` encodes 06:00:00 where my read
recorded `2026-07-15 00:00:00` — a clean six-hour offset, the shape of a timezone rendering
difference at minting. `qty` and `realized` match exactly, so the unit identification is
secure; the *timestamp inside the id* is not reliable as a join key.

## STANDING CORRECTION — two rows labeled EXCLUDED are contributing units

Checked against the manifest, POSITIONS' non-candidate rows:

| id | ticker | entry | status as supplied | measured |
|---|---|---|---|---|
| 348 | SOXS | 2026-07-07 | EXCLUDED-UPSTREAM (EDGE) | **IN THE 66 (src=B)** |
| 382 | SOXS | 2026-08-05 | EXCLUDED-UPSTREAM (EDGE) | **IN THE 66 (src=B)** |
| 368 | SOXS | 2026-07-20 | INVALID-LIFETIME | not in the 66 ✓ |
| 370 | SQQQ | 2026-07-22 | INVALID-LIFETIME | not in the 66 ✓ |
| 369 | BITX | 2026-07-21 | INVALID-LIFETIME | not in the 66 ✓ |

The three INVALID-LIFETIME rows are correctly excluded. **The two CSV_RECONCILE rows are not
excluded — they contribute.** CSV_RECONCILE is a *tier* (provenance label), not a disposition;
my tier census found exactly 2 CSV_RECONCILE rows in the cells-contributing layer, and these
are them.

This matters because the weakening argument offered for the SOXS mismatches — *"a mismatch
landing on an already-excluded row changes nothing"* — **does not apply to 348 and 382.** If
either carries a mismatch, it lands on a contributing unit. Flagged previously; re-stated here
with POSITIONS' own payload as the evidence.

## SCOPE

Ticker-level intersection remains necessary-not-sufficient for the wider mismatch set; this
pass is sufficient only for the five candidates supplied. The 11 ticker-level possible
positives from the earlier pass — including **RAMZ +311.04**, unworked — still require
unit-level resolution, and the source that could supply it for them does not yet exist.
