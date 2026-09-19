-- R-IV.463(e): INSERTS ARE AUDITED. The trigger covered UPDATE and DELETE only, so a row written
-- straight into the book -- ids 512/513, 2026-09-19 -- was the one write with no trail: a
-- fabricated row and a real one looked the same. An INSERT is now recorded like any other write,
-- with no before-state, the whole row after, and the actor that wrote it.
-- Mirrors backend/database/postgres_client.py (boot DDL). The trigger is re-created only when
-- it does not already fire on INSERT (tgtype bit 4), so a boot does not re-lock the table.

CREATE OR REPLACE FUNCTION unified_positions_audit() RETURNS trigger AS $$
BEGIN
    IF (TG_OP = 'INSERT') THEN
        INSERT INTO position_sync_audit
            (operation, position_id, ticker, structure,
             before_state, after_state, actor, reason, executed_at)
        VALUES ('INSERT', NEW.position_id, NEW.ticker, NEW.structure,
                NULL, to_jsonb(NEW),
                COALESCE(NULLIF(current_setting('app.actor', true), ''), 'legacy-ui'),
                NULLIF(current_setting('app.reason', true), ''), now());
        RETURN NEW;
    ELSIF (TG_OP = 'UPDATE') THEN
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

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                    WHERE tgname = 'trg_unified_positions_audit'
                      AND tgrelid = 'unified_positions'::regclass
                      AND (tgtype & 4) = 4) THEN
        DROP TRIGGER IF EXISTS trg_unified_positions_audit ON unified_positions;
        CREATE TRIGGER trg_unified_positions_audit
            AFTER INSERT OR UPDATE OR DELETE ON unified_positions
            FOR EACH ROW EXECUTE FUNCTION unified_positions_audit();
    END IF;
END $$;
