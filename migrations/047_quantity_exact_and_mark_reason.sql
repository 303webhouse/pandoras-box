-- 047: the book holds the broker's quantity exactly, and a mark says how it was made (R-IV.458).
--
-- (b) QUANTITY BECOMES NUMERIC. unified_positions.quantity was INTEGER, so a fractional broker
-- fill -- GUSH 358's 0.35049 share bought at 39.09, export line 149 -- could not be recorded at all.
-- The ruling is that the book matches the broker INCLUDING FRACTIONS and does not round the
-- broker to fit the book. INTEGER -> NUMERIC widens without loss: every existing value is kept
-- exactly. No view depends on the column (measured before this migration).
--
-- The application reads the column as Decimal from here on. Every place that did arithmetic on
-- a stored quantity was changed in the same commit to coerce it, because Decimal times a float
-- price raises -- the mark loop, the close path, the create-merge path, the summary, the risk
-- calculation and the legacy portfolio shim.
--
-- (a) mark_reason: a mark carries HOW it was made or why it could not be. A position with legs
-- is marked from its legs ("priced from 3 leg(s) (put_butterfly)"); one that cannot be priced
-- that way reads UNAVAILABLE with the reason ("no quote for the 2027-01-15 leg(s) ...", or "legs
-- hold 10 contracts; the row says quantity 8"). Only a legs-derived mark survives a failed cycle.
--
-- Also created at boot from backend/database/postgres_client.py (keep the two in sync).

ALTER TABLE unified_positions ALTER COLUMN quantity TYPE NUMERIC USING quantity::numeric;
ALTER TABLE unified_positions ADD COLUMN IF NOT EXISTS mark_reason TEXT;

-- DOWN
-- ALTER TABLE unified_positions DROP COLUMN IF EXISTS mark_reason;
-- ALTER TABLE unified_positions ALTER COLUMN quantity TYPE INTEGER USING round(quantity)::integer;
-- (The DOWN ROUNDS every fractional quantity -- exactly the loss this migration exists to end.
--  Refuse it while any row carries a fraction.)
