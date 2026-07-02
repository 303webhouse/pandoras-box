-- 021_triton_flow_shadow.sql
-- Triton Track Step-0: whale-flow forward-edge shadow logger (SHADOW-ONLY).
--
-- Captures market-wide whale option-flow prints (UW /api/option-trades/flow-alerts,
-- ask-side sweeps >= $250k) with fire-time context, graded later with
-- direction-adjusted forward returns. Feeds the pre-registered follow-vs-fade study
-- (n>=150) that is Triton's greenlight/kill gate. NOTHING reads this table for
-- scoring/pipeline — inert evidence data.
--
-- NOTE ON APPLICATION: this repo has no migration runner; tables are created at
-- boot via backend/database/postgres_client.py::init_database() (CREATE TABLE IF
-- NOT EXISTS). This file is the human record; the authoritative DDL is mirrored
-- verbatim in init_database(). Keep the two in sync.
--
-- Retention (Nick 2026-07-01): 90d, UNGRADED rows only. Graded rows
-- (graded_at IS NOT NULL) are exempt until docs/strategy-reviews/triton-forward-edge-*.md
-- exists. Daily insert cap (500 rows) enforced in the poller, not here.
-- Bumped 30d->90d after Railway CLI verified the postgres volume at 816/5000 MB
-- (16%) — the "94% full" flag (6/23) was STALE. (B1 shipped at 30d out of caution
-- while the volume % was unknown.)

CREATE TABLE IF NOT EXISTS triton_flow_shadow (
    id                  SERIAL PRIMARY KEY,
    uw_alert_id         TEXT UNIQUE NOT NULL,        -- dedup / idempotency (UW alert UUID)
    fired_at            TIMESTAMPTZ,                 -- UW alert timestamp (created_at)
    ticker              TEXT NOT NULL,
    direction           TEXT,                        -- 'BULL' = ask-side calls / 'BEAR' = ask-side puts
    premium_usd         BIGINT,                      -- total_premium
    is_sweep            BOOLEAN,
    liquidity_bucket    TEXT,                        -- 'small_mid' | 'large' | 'index' (flow_scanner buckets)
    spot_at_fire        NUMERIC(12,4),
    chg_pct_day         NUMERIC(8,4),
    prior_5d_ret        NUMERIC(8,4),
    is_liquid20         BOOLEAN,                     -- config/liquid_universe.LIQUID_UNIVERSE
    is_megacap_ai       BOOLEAN,                     -- config/liquid_universe.SEMIS_AI_TECH (Pass-2 split)
    bias_level_at_fire  TEXT,                        -- nullable (utils/bias_snapshot)
    gex_regime_at_fire  TEXT,                        -- nullable
    fwd_ret_1d          NUMERIC(8,4),                -- nullable until graded (direction-adjusted)
    fwd_ret_3d          NUMERIC(8,4),
    fwd_ret_5d          NUMERIC(8,4),
    graded_at           TIMESTAMPTZ,                 -- nullable until graded
    raw                 JSONB,                       -- small, selected fields only (no full payload / no secrets)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_triton_flow_shadow_ungraded
    ON triton_flow_shadow (fired_at) WHERE graded_at IS NULL;   -- grader queue
CREATE INDEX IF NOT EXISTS idx_triton_flow_shadow_fired
    ON triton_flow_shadow (fired_at DESC);
CREATE INDEX IF NOT EXISTS idx_triton_flow_shadow_ticker
    ON triton_flow_shadow (ticker, fired_at DESC);

-- Retention: purge UNGRADED rows older than 90d; graded rows retained.
DELETE FROM triton_flow_shadow
    WHERE created_at < NOW() - INTERVAL '90 days' AND graded_at IS NULL;
