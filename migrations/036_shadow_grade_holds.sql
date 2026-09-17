-- 036: holds for rows the second vendor disagrees with (R-IV.432(e)).
--
-- A graded row whose window spans a calendar event is written only if UW's closes agree with
-- the primary vendor's on the anchor and across the window. When they disagree the row is HELD:
-- flagged, never graded. Keyed on the basis, so a new basis looks again. Same-vendor
-- verification cannot detect a same-vendor error (the HON case) -- the module's first Law 2
-- instance.
--
-- Also created at boot from backend/backtest/store.py (keep the two in sync).

CREATE TABLE IF NOT EXISTS shadow_grade_holds (
    id              BIGSERIAL PRIMARY KEY,
    signal_id       TEXT        NOT NULL,
    population      TEXT        NOT NULL,
    method          TEXT        NOT NULL,
    horizon         INTEGER     NOT NULL,
    basis_id        TEXT        NOT NULL,
    reason          TEXT        NOT NULL,
    detail          JSONB       NOT NULL,
    tags            JSONB,
    grader_version  TEXT        NOT NULL,
    run_id          BIGINT,
    held_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (signal_id, population, method, horizon, basis_id)
);
CREATE INDEX IF NOT EXISTS idx_shadow_grade_holds_population
    ON shadow_grade_holds (population, method, horizon);

-- DOWN
-- DROP TABLE IF EXISTS shadow_grade_holds;
