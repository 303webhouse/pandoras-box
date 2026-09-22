-- R-IV.470(a): SCREEN_VERIFIED is a rung of its own between PRINCIPAL_REPORTED and
-- BROKER_VERIFIED: the broker DISPLAYED the figure and someone transcribed it. Its
-- evidence is what the screen showed, when it was captured and who read it across, and
-- the database refuses the value without the last two, as it does for BROKER_VERIFIED.
-- An export line (IMPORTED) always supersedes a screen.
-- Mirrors backend/database/postgres_client.py (boot DDL).

DO $$
BEGIN
    ALTER TABLE unified_positions DROP CONSTRAINT IF EXISTS unified_positions_provenance_check;
    ALTER TABLE unified_positions ADD CONSTRAINT unified_positions_provenance_check
        CHECK (provenance IS NULL OR provenance IN
               ('PRINCIPAL_REPORTED', 'SCREEN_VERIFIED', 'BROKER_VERIFIED',
                'IMPORTED', 'UNKNOWN'));
END $$;
DO $$
BEGIN
    ALTER TABLE position_lots DROP CONSTRAINT IF EXISTS position_lots_provenance_check;
    ALTER TABLE position_lots ADD CONSTRAINT position_lots_provenance_check
        CHECK (provenance IN ('PRINCIPAL_REPORTED', 'SCREEN_VERIFIED',
                              'BROKER_VERIFIED', 'IMPORTED', 'UNKNOWN'));
END $$;
DO $$
BEGIN
    ALTER TABLE position_legs DROP CONSTRAINT IF EXISTS position_legs_provenance_check;
    ALTER TABLE position_legs ADD CONSTRAINT position_legs_provenance_check
        CHECK (provenance IN ('PRINCIPAL_REPORTED', 'SCREEN_VERIFIED',
                              'BROKER_VERIFIED', 'IMPORTED', 'UNKNOWN'));
END $$;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'unified_positions_screen_needs_evidence') THEN
        ALTER TABLE unified_positions ADD CONSTRAINT unified_positions_screen_needs_evidence
            CHECK (provenance <> 'SCREEN_VERIFIED'
                   OR (verified_event IS NOT NULL AND verified_at IS NOT NULL));
    END IF;
END $$;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'position_lots_screen_needs_evidence') THEN
        ALTER TABLE position_lots ADD CONSTRAINT position_lots_screen_needs_evidence
            CHECK (provenance <> 'SCREEN_VERIFIED'
                   OR (verified_event IS NOT NULL AND verified_at IS NOT NULL));
    END IF;
END $$;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'position_legs_screen_needs_evidence') THEN
        ALTER TABLE position_legs ADD CONSTRAINT position_legs_screen_needs_evidence
            CHECK (provenance <> 'SCREEN_VERIFIED'
                   OR (verified_event IS NOT NULL AND verified_at IS NOT NULL));
    END IF;
END $$;
