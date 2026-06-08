-- Migration 020: committee_passes verdict + idempotency
--
-- 019 created committee_passes without a column for the committee's actual
-- decision (ENTER / PASS / WATCH / HEDGE) — the single most important field for
-- calibration ("when the committee said ENTER, was it right?"). This adds it,
-- plus committee_run_id (idempotency against VPS bridge retries via ON CONFLICT)
-- and key_risk (the one-line risk PIVOT flags in its decision block).
--
-- All additive. committee_passes is empty, so the ALTERs and the UNIQUE
-- constraint are zero-risk and touch no existing rows.
--
-- Rollback:
--   ALTER TABLE committee_passes DROP CONSTRAINT IF EXISTS committee_passes_run_id_unique;
--   ALTER TABLE committee_passes DROP COLUMN IF EXISTS recommendation;
--   ALTER TABLE committee_passes DROP COLUMN IF EXISTS committee_run_id;
--   ALTER TABLE committee_passes DROP COLUMN IF EXISTS key_risk;

BEGIN;

ALTER TABLE committee_passes ADD COLUMN IF NOT EXISTS recommendation   VARCHAR(16);  -- ENTER / PASS / WATCH / HEDGE
ALTER TABLE committee_passes ADD COLUMN IF NOT EXISTS committee_run_id TEXT;
ALTER TABLE committee_passes ADD COLUMN IF NOT EXISTS key_risk         TEXT;

-- Idempotency guard for ON CONFLICT (committee_run_id) DO NOTHING in the
-- submit handler. Wrapped so the migration is safely re-runnable.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'committee_passes_run_id_unique'
    ) THEN
        ALTER TABLE committee_passes
            ADD CONSTRAINT committee_passes_run_id_unique UNIQUE (committee_run_id);
    END IF;
END $$;

COMMIT;
