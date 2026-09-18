-- 046: a correction to a cash snapshot is recorded as a correction (R-IV.456(b)).
--
-- account_balances.cash is a SNAPSHOT the hub adjusts as positions change and reconciles to the
-- broker. When the hub itself moves it wrongly -- as the PATCH recompute did on 2026-09-18,
-- debiting ROBINHOOD 16.00 for a record correction that moved no money -- the reversal is neither
-- a deposit (cash_flows records money crossing the account boundary; this did not) nor a raw SQL
-- write (which leaves no reason and no author). It is its own event, and this is its table: the
-- amount, the balance before and after, the reason, the ruling that authorised it, and who ran it.
--
-- Kept OUT of cash_flows on purpose. Every return and deposit calculation reads cash_flows as
-- external money; an internal correction written there would be read as the principal adding or
-- withdrawing funds, and the correction would become the next error.
--
-- Also created at boot from backend/database/postgres_client.py (keep the two in sync).

CREATE TABLE IF NOT EXISTS cash_adjustments (
    id           BIGSERIAL   PRIMARY KEY,
    account      TEXT        NOT NULL,
    amount       NUMERIC     NOT NULL,
    cash_before  NUMERIC,
    cash_after   NUMERIC,
    reason       TEXT        NOT NULL,
    ruling       TEXT        NOT NULL,
    actor        TEXT        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- DOWN
-- DROP TABLE IF EXISTS cash_adjustments;
-- (A DOWN deletes the only record of why the snapshot moved; the balances themselves are not
--  reverted by it.)
