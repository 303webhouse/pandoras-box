-- 044: a terminal status is reachable only with an exit recorded (R-IV.454(c)(d)).
--
-- THE RULE. A position reaches CLOSED or EXPIRED only through a path that records how it ended:
-- the close endpoint (exit price and realized), the reduce path, or the expiry sweep (the expiry
-- date and an explicit UNKNOWN result). The application routes are closed in code; THIS is what
-- closes the door for everything else -- a script, a manual statement, a job nobody remembers.
--
-- WHY A TRIGGER AND NOT A CHECK. A CHECK constrains every write to a row, so the 23 historical
-- rows that ended with no result could not have their notes edited again. The rule is about the
-- TRANSITION -- reaching a terminal status -- so the trigger fires only on an INSERT of a
-- terminal row or an UPDATE that CHANGES status, and history stays editable.
--
-- WHAT IT ACCEPTS AS AN EXIT: an exit price, a realized figure, or an outcome -- any one. An
-- outcome of UNKNOWN counts, deliberately: "we know it ended and do not know the result" is a
-- recorded fact; a status with nothing beside it is the absence this rule exists to end.
--
-- KNOWN CONSEQUENCE, stated here so it is not discovered as an outage: scripts/sync_rh_csv.py's
-- close action writes CLOSED with the SYNC's date and no result. It is refused from this
-- migration on, with the message below, and has to route through the close path.
--
-- GROUP E (R-IV.454(c)): ids 298, 311, 341, 342 are honest absences under R-IV.112-b -- closed,
-- with no realized figure the record can support -- and are EXEMPT from any backfill. The mark
-- is a reason, not a flag, so the next sweep that meets it reads WHY it must not write, and the
-- rule sits beside it: no blanket backfill of "closed with no realized", ever.
--
-- Also created at boot from backend/database/postgres_client.py (keep the two in sync).

CREATE OR REPLACE FUNCTION unified_positions_terminal_needs_exit() RETURNS trigger AS $$
BEGIN
    IF NEW.status IN ('CLOSED', 'EXPIRED')
       AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM NEW.status)
       AND NEW.exit_price IS NULL
       AND NEW.realized_pnl IS NULL
       AND NEW.trade_outcome IS NULL THEN
        RAISE EXCEPTION
            'R-IV.454(d): % would reach % with no exit recorded (no exit_price, realized_pnl or trade_outcome). Use the close or reduce path, or record the outcome explicitly -- UNKNOWN is a valid one.',
            NEW.position_id, NEW.status
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_unified_positions_terminal_needs_exit ON unified_positions;
CREATE TRIGGER trg_unified_positions_terminal_needs_exit
    BEFORE INSERT OR UPDATE OF status ON unified_positions
    FOR EACH ROW EXECUTE FUNCTION unified_positions_terminal_needs_exit();

ALTER TABLE unified_positions ADD COLUMN IF NOT EXISTS backfill_exempt_reason TEXT;

UPDATE unified_positions
   SET backfill_exempt_reason = 'R-IV.454(c) GROUP E: honest absence under R-IV.112-b -- closed with no realized figure the record can support. EXEMPT from any backfill; no blanket backfill of closed-with-no-realized, ever.'
 WHERE position_id IN ('POS_GUSH_20260609_232044',   -- id 298
                       'POS_SOXS_20260610_154556',   -- id 311
                       'POS_GDXJ_20260618_174846',   -- id 341
                       'POS_XLE_20260618_174913')    -- id 342
   AND backfill_exempt_reason IS NULL;

-- DOWN
-- DROP TRIGGER IF EXISTS trg_unified_positions_terminal_needs_exit ON unified_positions;
-- DROP FUNCTION IF EXISTS unified_positions_terminal_needs_exit();
-- ALTER TABLE unified_positions DROP COLUMN IF EXISTS backfill_exempt_reason;
-- (A DOWN reopens every door the trigger closed, and removes the only mark telling the next
--  backfill which four rows it must not touch.)
