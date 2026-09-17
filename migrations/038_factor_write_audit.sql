-- 038: every accepted write into the regime engine leaves a line (R-IV.442(b)).
--
-- A factor POST changes a score the composite reads and recomputes on the spot. What it left
-- behind was the reading's own `source` string -- a label the CALLER chose, which answers
-- "what does this claim to be" rather than "who sent it". The second question is the one that
-- can be checked, and nothing recorded it.
--
-- WHAT THIS MAKES ANSWERABLE, stated as the partition it is: before this table, "no factor
-- reading carries the label that endpoint applies by default" was the strongest negative
-- available, and it is NOT the same as "nobody has called it" -- a caller passing any other
-- source string is invisible to that read. From here forward the two are different questions
-- with different answers.
--
-- The caller column holds a client address, a user agent, and an optional X-Caller name. It
-- never holds a credential: the auth dependency returns the API key itself on the header path,
-- and only the WORD for the mode (api_key / session / none) is stored.
--
-- Also created at boot from backend/database/postgres_client.py (keep the two in sync).

CREATE TABLE IF NOT EXISTS factor_write_audit (
    id              BIGSERIAL   PRIMARY KEY,
    endpoint        TEXT        NOT NULL,
    factor_id       TEXT,
    caller          TEXT        NOT NULL,
    auth_mode       TEXT        NOT NULL,
    claimed_source  TEXT,
    score           NUMERIC,
    accepted_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_factor_write_audit_time
    ON factor_write_audit (accepted_at DESC);
CREATE INDEX IF NOT EXISTS idx_factor_write_audit_factor
    ON factor_write_audit (factor_id, accepted_at DESC);

-- DOWN
-- DROP TABLE IF EXISTS factor_write_audit;
