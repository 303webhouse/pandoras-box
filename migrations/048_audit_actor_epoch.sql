-- R-IV.462(b): machine writers name themselves in app.actor, in their own transaction.
-- Mirrors backend/database/postgres_client.py (boot DDL), which applies it; the first boot of the
-- build that names its writers records began_at, so the cutover is a measured instant, not a date
-- someone remembered. Historical rows are NOT rewritten: they stay ambiguous, and say so.

CREATE TABLE IF NOT EXISTS audit_actor_epochs (
    epoch     TEXT        PRIMARY KEY,
    began_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    note      TEXT        NOT NULL
);

INSERT INTO audit_actor_epochs (epoch, note)
VALUES ('machine-writers-named', 'R-IV.462(b): from began_at every machine writer names itself in app.actor (mark-to-market, boot-migration, expiry-sweep, a script by its file name). Before began_at the audit trigger''s default legacy-ui also covered machine writes -- the mark job, boot backfills and scripts -- so a legacy-ui row before began_at is AMBIGUOUS: it may be a person or a job. A deploy runs the old and new builds side by side for a few minutes, so old-build legacy-ui mark writes can appear shortly after began_at.')
ON CONFLICT (epoch) DO NOTHING;

COMMENT ON COLUMN position_sync_audit.actor IS 'Who made the change: the writer sets app.actor in the same transaction; absent, the trigger records legacy-ui. BEFORE audit_actor_epochs.began_at (epoch machine-writers-named) legacy-ui is AMBIGUOUS -- measured 2026-09-19 05:30 UTC, 6,271 such UPDATE rows since 2026-08-27, 3,239 of them the mark job -- and cannot be read as a person. Rows before 2026-08-27 carry no actor at all. AFTER it, legacy-ui means a request to an endpoint whose caller named no actor (R-IV.116). R-IV.462(b).';
