-- FEAT-POSITION-LIFECYCLE Phase 2 — audit trigger captures actor + reason.
-- Applied to production 2026-08-27. Derivation of record for the DB-side change.
--
-- R-IV.116: `reason` is OPTIONAL at the API layer. Absent -> actor defaults to
-- 'legacy-ui' and reason is NULL; the legacy PATCH caller (app.js:11073) is
-- untouched and needs no coordinated frontend change. The new lifecycle UI sets
-- both via SET LOCAL inside the same transaction as its UPDATE.
--
-- Proven fireable before commit, both paths, inside a savepoint:
--   no settings   -> actor='legacy-ui',    reason=NULL
--   with settings -> actor='lifecycle-ui', reason='corrected qty from broker fill'

CREATE OR REPLACE FUNCTION unified_positions_audit() RETURNS trigger AS $$
BEGIN
    IF (TG_OP = 'UPDATE') THEN
        IF to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
            INSERT INTO position_sync_audit
                (operation, position_id, ticker, structure,
                 before_state, after_state, actor, reason, executed_at)
            VALUES ('UPDATE', NEW.position_id, NEW.ticker, NEW.structure,
                    to_jsonb(OLD), to_jsonb(NEW),
                    COALESCE(NULLIF(current_setting('app.actor', true), ''), 'legacy-ui'),
                    NULLIF(current_setting('app.reason', true), ''), now());
        END IF;
        RETURN NEW;
    ELSIF (TG_OP = 'DELETE') THEN
        INSERT INTO position_sync_audit
            (operation, position_id, ticker, structure,
             before_state, after_state, actor, reason, executed_at)
        VALUES ('DELETE', OLD.position_id, OLD.ticker, OLD.structure,
                to_jsonb(OLD), NULL,
                COALESCE(NULLIF(current_setting('app.actor', true), ''), 'legacy-ui'),
                NULLIF(current_setting('app.reason', true), ''), now());
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
