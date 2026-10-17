-- 054: signals.artemis_mode (R-IV.1198(b), salvage fix-first #4)
--
-- MIRRORS the DDL in backend/database/postgres_client.py init_database(). Nothing in the app
-- executes migrations/*.sql; this file is the reviewable copy. Keep the two in sync.
--
-- WHY IT WAS MISSING. webhooks/tradingview.py:803 has populated
-- signal_data["artemis_mode"] since Artemis shipped, and the INSERT in _log_signal_insert
-- bound 40 named columns with this one not among them. The value was built, logged once in the
-- acceptance line, and discarded at the write -- the swallowed-write class the log_signal
-- docstring describes, except silent rather than raising: a key in the dict that no column
-- received, which raises nothing and simply never appears.
--
-- It is the only thing separating a Normal fire (trend plus a confirmation candle at the VWAP
-- band) from a Flush fire (exhaustion reversal after a 3%+ move into the band). Every Artemis
-- outcome question turns on that distinction, and none of it was on record.
--
-- TEXT, NOT VARCHAR(n), deliberately. The value arrives from a webhook payload through
-- `(alert.mode or "Normal").capitalize()`, so its length is the sender's choice. On a VARCHAR a
-- long one raises inside the INSERT, and log_signal re-raises by design -- which would mean
-- losing the whole SIGNAL over a label. A label must never be able to reject a fire.
--
-- NO BACKFILL. R-IV.1198(b): the field starts recording from the deploy. Rows written before it
-- are NULL, and NULL here means "not recorded" -- never "Normal".

ALTER TABLE signals
    ADD COLUMN IF NOT EXISTS artemis_mode TEXT;

-- Partial: only Artemis rows carry a mode, so the index covers the rows anyone will query by
-- it and stays off every other signal type.
CREATE INDEX IF NOT EXISTS idx_signals_artemis_mode
    ON signals(artemis_mode) WHERE artemis_mode IS NOT NULL;
