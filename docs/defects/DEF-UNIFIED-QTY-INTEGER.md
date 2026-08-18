# DEF-UNIFIED-QTY-INTEGER

**Severity:** P3 (data model) · **Filed:** 2026-08-18 · **Status:** OPEN
**Surface:** `unified_positions.quantity` (integer)

## Symptom
Fractional share quantities cannot be stored. Known instances: GUSH 15.35 sh
stored as 15; SOXS 6.185477 sh stored as 6 (2026-08-17 recon insert). In both,
realized/basis dollars are correct but `entry_price x quantity` no longer
reproduces `cost_basis`.

## Interim convention (recon lane, item-19)
True fractional quantity + true basis recorded in the row's `notes`; dollars
preserved as authoritative; nobody rebuilds dollars from parts.

## Fix path
Migration to numeric quantity (ATLAS review required — schema change), or
formalize the notes convention + add a `quantity_exact` column. Decide post
observation week; not urgent while the convention holds.
