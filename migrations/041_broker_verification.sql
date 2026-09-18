-- 041: BROKER_VERIFIED becomes reachable, and only on evidence (R-IV.447(b)).
--
-- The vocabulary has always had the value; nothing could write it. That was deliberate while
-- no path matched a broker record -- a stamp nothing checked is an assertion about an
-- assertion. A reconciliation against the Fidelity confirmations is such a match, so the
-- transition now exists, and it carries what T6d requires it to carry: the verifying event and
-- its timestamp, stamped AT the transition.
--
-- THE CONSTRAINT IS THE POINT. A row may only be BROKER_VERIFIED when it names:
--   * broker_ref      -- the broker's own identity for the fill (already required),
--   * verified_event  -- what it was matched against, in words a human can re-check,
--   * verified_at     -- when the match was made.
-- Take any of the three away and the claim becomes unfalsifiable again, which is the condition
-- this value was invented to escape.
--
-- verified_at is the time of the MATCH, not of the fill. The fill's time is fill_time and has
-- its own meaning; conflating them would make a row look as though it was confirmed the day it
-- traded, which is exactly the fiction a verification stamp must not manufacture.
--
-- Also created at boot from backend/database/postgres_client.py (keep the two in sync).

ALTER TABLE position_lots ADD COLUMN IF NOT EXISTS verified_at    TIMESTAMPTZ;
ALTER TABLE position_lots ADD COLUMN IF NOT EXISTS verified_event TEXT;
ALTER TABLE position_legs ADD COLUMN IF NOT EXISTS verified_at    TIMESTAMPTZ;
ALTER TABLE position_legs ADD COLUMN IF NOT EXISTS verified_event TEXT;

-- The old constraint required a reference. The new one requires the whole evidence set, and
-- replaces it rather than sitting beside it, so there is one rule and not two.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint
                WHERE conname = 'position_lots_verified_needs_ref') THEN
        ALTER TABLE position_lots DROP CONSTRAINT position_lots_verified_needs_ref;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'position_lots_verified_needs_evidence') THEN
        ALTER TABLE position_lots ADD CONSTRAINT position_lots_verified_needs_evidence
            CHECK (provenance <> 'BROKER_VERIFIED'
                   OR (broker_ref IS NOT NULL AND verified_event IS NOT NULL
                       AND verified_at IS NOT NULL));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'position_legs_verified_needs_evidence') THEN
        ALTER TABLE position_legs ADD CONSTRAINT position_legs_verified_needs_evidence
            CHECK (provenance <> 'BROKER_VERIFIED'
                   OR (broker_ref IS NOT NULL AND verified_event IS NOT NULL
                       AND verified_at IS NOT NULL));
    END IF;
END $$;

-- DOWN
-- ALTER TABLE position_legs DROP CONSTRAINT IF EXISTS position_legs_verified_needs_evidence;
-- ALTER TABLE position_lots DROP CONSTRAINT IF EXISTS position_lots_verified_needs_evidence;
-- ALTER TABLE position_legs DROP COLUMN IF EXISTS verified_event;
-- ALTER TABLE position_legs DROP COLUMN IF EXISTS verified_at;
-- ALTER TABLE position_lots DROP COLUMN IF EXISTS verified_event;
-- ALTER TABLE position_lots DROP COLUMN IF EXISTS verified_at;
-- (A DOWN discards every verification ever recorded and leaves the stamps behind it
--  unfalsifiable -- restore the constraint before restoring the columns' absence.)
