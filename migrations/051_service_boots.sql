-- R-IV.464(f): every boot of the app records itself, so a restart is visible without the
-- deployment CLI. An aaf9163 process restarted at about 16:32 UTC on 2026-09-19 with no deploy;
-- the CLI was not linked to the service, so the cause could not be read at all. An unverified
-- restart on a system whose state is partly in memory (mark loop timers, SWR caches, the
-- breaker's in-process reading) is not a footnote.
-- Mirrors backend/database/postgres_client.py (boot DDL).

CREATE TABLE IF NOT EXISTS service_boots (
    id          BIGSERIAL   PRIMARY KEY,
    booted_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    commit_sha  TEXT,
    note        TEXT
);

CREATE INDEX IF NOT EXISTS idx_service_boots_at ON service_boots (booted_at DESC);
