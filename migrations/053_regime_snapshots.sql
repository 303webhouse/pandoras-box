-- 053: regime_snapshots + regime_audit (R-IV.1195(b), the v1 nightly classifier going live)
--
-- MIRRORS the DDL in backend/database/postgres_client.py init_database(). Nothing in the app
-- executes migrations/*.sql; this file is the reviewable copy. Keep the two in sync.
--
-- DISPLAY ONLY (#42). These rows drive the Regime Strategy card and nothing else. No gate, no
-- kill-switch, no cap, no Kairos input and no grade reads them. Enforced by a CI check,
-- backend/tests/test_regime_live_r1195.py.
--
-- APPEND-ONLY, per section 8. One row per (as_of, rules_version). A re-run that disagreed with
-- an earlier one must not overwrite the evidence of the disagreement -- it is refused by the
-- unique key and recorded in regime_audit instead.

CREATE TABLE IF NOT EXISTS regime_snapshots (
    id              SERIAL PRIMARY KEY,
    as_of           DATE NOT NULL,          -- the SETTLED SESSION the label describes
    rules_version   TEXT NOT NULL,          -- which regime_rules.vN.json produced it
    regime          TEXT,                   -- the RAW section 2 verdict; NULL = no row matched
    shown_regime    TEXT,                   -- what the card may display, after hysteresis
    label           TEXT,                   -- the display label for `regime`
    tags            TEXT[] NOT NULL DEFAULT '{}',
    basis           TEXT,                   -- the clause and the numbers, for a reader
    not_evaluable   TEXT[] NOT NULL DEFAULT '{}',  -- rows that could not be tested, by name
    settled         BOOLEAN NOT NULL,       -- always true for a written row; false is refused
    pending         TEXT,                   -- a candidate accumulating closes
    pending_closes  INT,
    held_sessions   INT,
    change          TEXT,                   -- why the label moved on this session
    blocked         TEXT,                   -- a qualifying candidate hysteresis held back
    inputs_json     JSONB,                  -- the inputs the verdict was computed from
    seeded          BOOLEAN NOT NULL DEFAULT FALSE,  -- written by the backfill, not a live close
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (as_of, rules_version)
);

CREATE INDEX IF NOT EXISTS idx_regime_snapshots_as_of
    ON regime_snapshots (as_of DESC);

-- Why a run did what it did, including the runs that wrote nothing. A nightly job that skipped
-- a session silently is the fault R-IV.1175 was about, so a refusal is a ROW, not an absence.
CREATE TABLE IF NOT EXISTS regime_audit (
    id              SERIAL PRIMARY KEY,
    as_of           DATE,
    rules_version   TEXT,
    action          TEXT NOT NULL,          -- seed | nightly | refused | conflict
    detail          TEXT NOT NULL,
    rows_written    INT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_regime_audit_created
    ON regime_audit (created_at DESC);
