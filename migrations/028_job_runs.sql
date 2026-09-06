-- 028_job_runs.sql
-- T2 of the grader-precondition build (R-IV.287(4), CC-ACTIONABLE at R-IV.289).
--
-- Durable job bookkeeping. Today the Triton grader's `last_run` lives in process
-- memory (main.py triton_grader_loop), so a restart re-arms the day and a missed
-- day leaves no trace anywhere. That is what makes "did it run?" unanswerable, and
-- it is the state half of the 07-31 outage.
--
-- SHAPE (R-IV.287(4)): the schema is job-agnostic so it can serve every job, but
-- THIS BUILD WIRES EXACTLY ONE WRITER -- the Triton grader. No other job is
-- migrated here. An empty row for a job that never wrote is indistinguishable
-- from a job that never ran, so absence of a job in this table means NOT WIRED,
-- never "did not run".
--
-- session_date is the ET trading date the run is FOR, which is not the same as
-- started_at: the post-close pass for Monday can begin at 16:15 ET Monday and, if
-- it were ever re-armed late, must not be mistaken for Tuesday's.

CREATE TABLE IF NOT EXISTS job_runs (
    id            BIGSERIAL PRIMARY KEY,
    job_name      TEXT        NOT NULL,
    session_date  DATE        NOT NULL,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at   TIMESTAMPTZ,
    -- running | ok | error | timeout | skipped
    status        TEXT        NOT NULL DEFAULT 'running',
    rows_touched  INTEGER,
    skip_reason   TEXT,
    error         TEXT
);

-- "has this job completed for this session date?" -- the query that replaces the
-- in-memory flag. Partial index: only successful runs answer that question.
CREATE INDEX IF NOT EXISTS idx_job_runs_job_session_ok
    ON job_runs (job_name, session_date DESC)
    WHERE status = 'ok';

-- "what happened last time?" -- for /health and for the build report.
CREATE INDEX IF NOT EXISTS idx_job_runs_job_started
    ON job_runs (job_name, started_at DESC);

-- DOWN
-- DROP INDEX IF EXISTS idx_job_runs_job_started;
-- DROP INDEX IF EXISTS idx_job_runs_job_session_ok;
-- DROP TABLE IF EXISTS job_runs;
