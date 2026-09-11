-- 031_option_chain_snapshots.sql  —  S8 (R-IV.361 addition).
--
-- FORWARD COLLECTION FOR PS-02. The collector law applies: this cannot be
-- retrofitted. A day not captured is gone — there is no vendor call that
-- returns yesterday's bid/ask/IV as they stood at capture time.
--
-- WHAT IS STORED AND WHY EACH FIELD IS HERE
--   bid / ask       the SPREAD is the point; a mid alone destroys it, and a
--                   mid is recoverable from the pair while the pair is not
--                   recoverable from the mid.
--   iv              as the vendor published it AT CAPTURE. Never recomputed:
--                   a recomputed IV is a derived value that cannot witness the
--                   surface it came from (conventions #14).
--   dte             stored, not derived at read time, because the trading
--                   calendar changes and a DTE recomputed later against a
--                   different holiday set is a different number.
--   captured_at     the instant. session_date is the trading day it belongs to;
--                   they are different questions and a capture near midnight UTC
--                   answers them differently.
--
-- COMPLETENESS IS RECORDED, NOT ASSUMED
--   UW caps /option-contracts at 500 rows per call. A truncated chain looks
--   exactly like a thin one. `raw_contract_count` and `truncated` are stored so
--   a later reader can tell a quiet cap from a real market — without them this
--   table would silently disagree with itself across liquidity regimes.

CREATE TABLE IF NOT EXISTS option_chain_snapshots (
    id                  BIGSERIAL PRIMARY KEY,
    captured_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_date        DATE        NOT NULL,
    ticker              TEXT        NOT NULL,
    expiry              DATE        NOT NULL,
    dte                 INTEGER     NOT NULL,
    contract_type       TEXT        NOT NULL,      -- 'call' | 'put'
    strike              NUMERIC(12,4) NOT NULL,
    bid                 NUMERIC(12,4),
    ask                 NUMERIC(12,4),
    iv                  NUMERIC(10,6),
    open_interest       BIGINT,
    volume              BIGINT,
    raw_contract_count  INTEGER,                   -- what the vendor returned, pre-filter
    truncated           BOOLEAN     NOT NULL DEFAULT FALSE,
    source              TEXT        NOT NULL DEFAULT 'uw',
    UNIQUE (session_date, ticker, expiry, contract_type, strike)
);

-- One capture per contract per session. A re-run on the same day updates rather
-- than duplicating, so a retry after a partial failure is safe.
CREATE INDEX IF NOT EXISTS idx_option_chain_snap_session
    ON option_chain_snapshots (session_date DESC, ticker);
CREATE INDEX IF NOT EXISTS idx_option_chain_snap_ticker_expiry
    ON option_chain_snapshots (ticker, expiry, session_date DESC);

-- DOWN
-- DROP TABLE IF EXISTS option_chain_snapshots;
