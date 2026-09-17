-- 035: the backtest module's tables (R-IV.429(b)).
--
-- shadow_grades    one row per GRADED (signal, population, method, horizon). INSERT-ONLY:
--                  a grade is never rewritten, and a row stored on another basis is left
--                  alone (R-IV.428(a)(3)). The basis is on every row (R-IV.428(a)(1)).
-- backtest_runs    every pass, with the code commit, the bar vintage and the counts
--                  (the calibration clause, R-IV.425(d)).
-- backtest_results cell summaries per run (Titans review section 13, extended with
--                  population / cell / method / stratum).
--
-- Also created at boot from backend/backtest/store.py (keep the two in sync).

CREATE TABLE IF NOT EXISTS shadow_grades (
    id              BIGSERIAL PRIMARY KEY,
    signal_id       TEXT        NOT NULL,
    population      TEXT        NOT NULL,
    method          TEXT        NOT NULL,
    horizon         INTEGER     NOT NULL,
    anchor_session  DATE        NOT NULL,
    exit_session    DATE        NOT NULL,
    entry_raw       NUMERIC,
    entry_factor    NUMERIC     NOT NULL,
    entry_basis     NUMERIC     NOT NULL,
    anchor_close    NUMERIC,
    exit_price      NUMERIC     NOT NULL,
    ret_pct         NUMERIC     NOT NULL,
    ret_raw_pct     NUMERIC     NOT NULL,
    ret_v2_pct      NUMERIC,
    r_multiple      NUMERIC,
    outcome         TEXT,
    direction_sign  SMALLINT    NOT NULL,
    basis_id        TEXT        NOT NULL,
    basis           JSONB       NOT NULL,
    flags           TEXT[]      NOT NULL DEFAULT '{}',
    tags            JSONB,
    grader_version  TEXT        NOT NULL,
    run_id          BIGINT,
    graded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (signal_id, population, method, horizon)
);
CREATE INDEX IF NOT EXISTS idx_shadow_grades_population
    ON shadow_grades (population, method, horizon, anchor_session);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id              BIGSERIAL PRIMARY KEY,
    kind            TEXT        NOT NULL,
    population      TEXT        NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    status          TEXT        NOT NULL DEFAULT 'running',
    grader_version  TEXT        NOT NULL,
    code_commit     TEXT,
    params          JSONB,
    counts          JSONB,
    error           TEXT
);

CREATE TABLE IF NOT EXISTS backtest_results (
    id              BIGSERIAL PRIMARY KEY,
    run_id          BIGINT      NOT NULL,
    population      TEXT        NOT NULL,
    cell            TEXT        NOT NULL,
    method          TEXT        NOT NULL,
    horizon         INTEGER     NOT NULL,
    stratum         TEXT        NOT NULL DEFAULT 'ALL',
    symbol          TEXT        NOT NULL DEFAULT 'ALL',
    first_anchor    DATE,
    last_anchor     DATE,
    trades          INTEGER     NOT NULL,
    win_rate        NUMERIC,
    mean_ret_pct    NUMERIC,
    profit_factor   NUMERIC,
    avg_winner_r    NUMERIC,
    avg_loser_r     NUMERIC,
    expectancy_r    NUMERIC,
    max_dd_r        NUMERIC,
    sharpe          NUMERIC,
    summary         JSONB       NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_backtest_results_run ON backtest_results (run_id);

-- DOWN
-- DROP TABLE IF EXISTS backtest_results;
-- DROP TABLE IF EXISTS backtest_runs;
-- DROP TABLE IF EXISTS shadow_grades;
