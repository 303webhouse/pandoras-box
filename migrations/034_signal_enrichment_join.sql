-- 034: the enrichment join on the signal row (R-IV.422).
--
-- va_location           outside | edge | mid, located against the PRIOR session's developing
--                       VA as it stood before the signal's session (never cumulative: no
--                       lookahead). NULL = no usable prior-session VA.
-- sector_rotation_state the rotation REGIME label (CONCENTRATED_LEADERSHIP | BROAD_ROTATION |
--                       ACTIVE_DISTRIBUTION | REGIME_AGNOSTIC) from the one classifier in
--                       services/read_only/sectors.py -- distinct from sector_3_10 momentum.
--
-- CIRCE'S STEW writes both first; every scanner follows. Also created at boot by
-- database/postgres_client.py (keep the two in sync). Written by a separate statement after
-- the insert, so a missing column fails the join write loudly and never the signal.

ALTER TABLE signals ADD COLUMN IF NOT EXISTS va_location           TEXT;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS sector_rotation_state TEXT;

-- DOWN
-- ALTER TABLE signals DROP COLUMN IF EXISTS sector_rotation_state;
-- ALTER TABLE signals DROP COLUMN IF EXISTS va_location;
