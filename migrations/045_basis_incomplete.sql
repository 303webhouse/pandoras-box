-- 045: a basis that covers less than the quantity says so (R-IV.456(a)).
--
-- THE RULE: recompute-on-write NEVER PRICES UNPRICED QUANTITY. When quantity grows with units
-- that carry no price, the basis is NOT recomputed -- it was right for everything priced -- and
-- the row is marked basis-incomplete, naming how much is uncovered.
--
-- THE CASE THAT RULED IT: NVDA 415, quantity 2 -> 3. The old recompute priced the third
-- structure at the first two's 0.16 and wrote 48.00 over a correct 32.00: sixteen dollars of basis
-- invented by assumption, with no fill behind it. Recompute-on-write assumed quantity was right and
-- basis stale; here basis was right for everything priced, and quantity grew with unpriced units.
-- That is DEF-COST-BASIS-NOT-RESCALED's own warning arriving through its remedy.
--
-- The mark is a REASON, not a flag, so a reader learns what is uncovered and by how much.
--
-- Also created at boot from backend/database/postgres_client.py (keep the two in sync).

ALTER TABLE unified_positions ADD COLUMN IF NOT EXISTS basis_incomplete_reason TEXT;

UPDATE unified_positions
   SET basis_incomplete_reason = 'R-IV.456(a): quantity 3, basis 32.00 covers 2 structures (net 0.16); the third structure has no recorded fill. Legs entered from a broker screen showing marks, not fills.'
 WHERE position_id = 'POS_NVDA_20260911_001150'   -- id 415
   AND basis_incomplete_reason IS NULL;

-- DOWN
-- ALTER TABLE unified_positions DROP COLUMN IF EXISTS basis_incomplete_reason;
