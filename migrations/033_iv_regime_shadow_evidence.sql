-- 033: Pass 9 shadow evidence on the signal row (R-IV.423(b)).
--
-- The 04-24 lock specified iv_regime_legacy / iv_regime_v2 / iv_regime_diverged inside
-- signals.committee_data, but the signals INSERT never wrote committee_data, so no signal
-- carried them. Own columns, because committee_bridge replaces committee_data wholesale.
-- Also created at boot by database/postgres_client.py (keep the two in sync).
--
-- The 60-day review restarts from the first day these columns are populated.

ALTER TABLE signals ADD COLUMN IF NOT EXISTS iv_regime_legacy   JSONB;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS iv_regime_v2       JSONB;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS iv_regime_diverged BOOLEAN;

-- DOWN
-- ALTER TABLE signals DROP COLUMN IF EXISTS iv_regime_diverged;
-- ALTER TABLE signals DROP COLUMN IF EXISTS iv_regime_v2;
-- ALTER TABLE signals DROP COLUMN IF EXISTS iv_regime_legacy;
