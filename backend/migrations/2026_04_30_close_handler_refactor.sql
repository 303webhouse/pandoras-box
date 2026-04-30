-- Migration: close-handler TOCTOU fix (2026-04-30)
-- Applied to Railway Postgres before code deploy.
-- Creates audit and observability tables for the atomic close handler.

CREATE TABLE IF NOT EXISTS close_attempts (
    id              BIGSERIAL    PRIMARY KEY,
    position_id     TEXT         NOT NULL,
    attempted_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    exit_price      NUMERIC(12,4),
    status          TEXT         NOT NULL DEFAULT 'started',
    trade_id        BIGINT,
    error_message   TEXT,
    CONSTRAINT close_attempts_status_chk
        CHECK (status IN ('started', 'completed', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_close_attempts_position_id
    ON close_attempts(position_id);

CREATE INDEX IF NOT EXISTS idx_close_attempts_attempted_at
    ON close_attempts(attempted_at DESC);

-- background_task_failures: captures exceptions from asyncio.ensure_future tasks
-- (signal resolution, proximity attribution) that run off the main request path.
CREATE TABLE IF NOT EXISTS background_task_failures (
    id              BIGSERIAL    PRIMARY KEY,
    task_name       TEXT         NOT NULL,
    related_id      TEXT,
    error_class     TEXT,
    error_message   TEXT,
    stack_trace     TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bg_failures_task_name
    ON background_task_failures(task_name);

CREATE INDEX IF NOT EXISTS idx_bg_failures_created_at
    ON background_task_failures(created_at DESC);
