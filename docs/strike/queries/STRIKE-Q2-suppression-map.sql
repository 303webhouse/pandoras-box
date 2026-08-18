-- ============================================================================
-- STRIKE-Q2 — The Suppression Map (DESCRIPTIVE ONLY)
-- Filed 2026-08-17 · Lane: STRIKE · Executor: CC (verbatim protocol)
-- Companion brief: docs/codex-briefs/2026-08-17-strike-q2-suppression-map-brief.md
-- ============================================================================
-- PURPOSE: Map the mechanism that buries Holy_Grail (610 fired / 0 surfaced)
-- and Artemis (482 / 6) while CTA Scanner passes. Evidence from STRIKE-Q1:
-- an L0 gate logging {mode:'enforce', rule:'SUPPRESS', reason:'signal_type in
-- unconditional suppress set'} plus feed_tier / gate_type columns on signals.
--
-- PROTOCOL (binding, same as STRIKE-Q1):
--   * SELECT-only. Execute in order. Errors returned unedited. No rewrites,
--     no substitutions. Session TZ pinned UTC; passthrough typecasters
--     (reuse the Q1 method). COUNT(*) only.
--   * Q2.0a is the schema authority for pythia_events and
--     signal_options_expressions. PER-QUERY GATES: if a query references a
--     column absent from Q2.0a (including `id` used by the sample ORDER BYs),
--     STOP THAT QUERY, note it, and CONTINUE the session. Q1's whole-census
--     stop does not apply here — Q2.1–Q2.6 reference only columns already
--     verified present in Q1's Q0.1 output for `signals`.
--   * COLUMN-SCOPE LAW (STRIKE-Q1 anomaly 16): no jsonb columns anywhere in
--     this package. The two SELECT * samples target small unknown tables at
--     LIMIT 5 and are the only unscoped statements.
--
-- WINDOW: full span 2026-07-30T00:00 → 2026-08-16T00:00, NAIVE literals —
-- deliberate. signals.created_at is `timestamp without time zone` storing UTC
-- wall time (Q1 anomaly 3: Z-suffixed literals were silently stripped; the
-- naive-UTC reading is corroborated by hour_of_day values and Sat/Sun gaps
-- aligning on UTC dates). Boundaries below are therefore written naive.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Q2.0a — PREFLIGHT: columns of the two new tables (schema authority)
-- ----------------------------------------------------------------------------
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('pythia_events','signal_options_expressions')
ORDER BY table_name, ordinal_position;

-- ----------------------------------------------------------------------------
-- Q2.0b — PREFLIGHT: raw row counts (tables confirmed to exist in Q1's Q0.2)
-- ----------------------------------------------------------------------------
SELECT COUNT(*) AS pythia_events_rows FROM pythia_events;

SELECT COUNT(*) AS signal_options_expressions_rows FROM signal_options_expressions;

-- ----------------------------------------------------------------------------
-- Q2.1 — THE CROSSTAB: signal_type x strategy x direction x status
--        (maps the suppress set against reality; unlocks the signal_type-keyed
--         Rosetta that Q1's strategy-only grouping could not reach)
-- ----------------------------------------------------------------------------
SELECT strategy, signal_type, direction, status, COUNT(*) AS n,
       MIN(score) AS min_score, MAX(score) AS max_score
FROM signals
WHERE created_at >= '2026-07-30T00:00:00'
  AND created_at <  '2026-08-16T00:00:00'
GROUP BY 1, 2, 3, 4
ORDER BY n DESC
LIMIT 300;

-- ----------------------------------------------------------------------------
-- Q2.2 — FEED-TIER MAP: where each strategy's signals land in the surfacing
--        pipeline (top_feed / watchlist / NULL tells us who is allowed upstairs)
-- ----------------------------------------------------------------------------
SELECT strategy, feed_tier_v2, feed_tier_v2_path, status, COUNT(*) AS n
FROM signals
WHERE created_at >= '2026-07-30T00:00:00'
  AND created_at <  '2026-08-16T00:00:00'
GROUP BY 1, 2, 3, 4
ORDER BY n DESC
LIMIT 300;

-- ----------------------------------------------------------------------------
-- Q2.3 — GATE ANNOTATIONS: distribution of gate_type / ceilings by strategy
-- ----------------------------------------------------------------------------
SELECT strategy, gate_type, feed_tier_ceiling, score_ceiling_reason, COUNT(*) AS n
FROM signals
WHERE created_at >= '2026-07-30T00:00:00'
  AND created_at <  '2026-08-16T00:00:00'
GROUP BY 1, 2, 3, 4
ORDER BY n DESC
LIMIT 200;

-- ----------------------------------------------------------------------------
-- Q2.4 — BEST OF THE BURIED: highest-scoring Holy_Grail / Artemis rows that
--        never surfaced. Column-scoped; `notes` carries auto-dismiss reasons.
-- ----------------------------------------------------------------------------
SELECT id, created_at, strategy, signal_type, ticker, direction, score, score_v2,
       adjusted_score, status, user_action, feed_tier, feed_tier_v2,
       feed_tier_v2_path, gate_type, feed_tier_ceiling, score_ceiling_reason,
       bias_alignment, risk_reward, entry_price, stop_loss, target_1, timeframe,
       source, signal_category, outcome, outcome_source, notes
FROM signals
WHERE created_at >= '2026-07-30T00:00:00'
  AND created_at <  '2026-08-16T00:00:00'
  AND strategy IN ('Holy_Grail','Artemis')
  AND status <> 'COMMITTEE_REVIEW'
  AND score >= 80
ORDER BY score DESC
LIMIT 30;

-- ----------------------------------------------------------------------------
-- Q2.5 — COMMITTEE BRIDGE LIVENESS: requested vs completed by UTC day
--        (Q1's AMD record showed committee_requested_at set, completed NULL)
-- ----------------------------------------------------------------------------
SELECT date_trunc('day', created_at) AS utc_day,
       COUNT(*) FILTER (WHERE committee_requested_at IS NOT NULL) AS requested,
       COUNT(*) FILTER (WHERE committee_completed_at IS NOT NULL) AS completed,
       COUNT(*) FILTER (WHERE committee_requested_at IS NOT NULL
                          AND committee_completed_at IS NULL)     AS requested_never_completed
FROM signals
WHERE created_at >= '2026-07-30T00:00:00'
  AND created_at <  '2026-08-16T00:00:00'
GROUP BY 1
ORDER BY 1;

-- ----------------------------------------------------------------------------
-- Q2.6 — SATURDAY ATTRIBUTION: the 12 EXPIRED rows created Sat 2026-08-15
--        (hypothesis: Crypto Scanner, the only 24/7 strategy)
-- ----------------------------------------------------------------------------
SELECT strategy, asset_class, ticker, COUNT(*) AS n
FROM signals
WHERE created_at >= '2026-08-15T00:00:00'
  AND created_at <  '2026-08-16T00:00:00'
GROUP BY 1, 2, 3
ORDER BY n DESC
LIMIT 50;

-- ----------------------------------------------------------------------------
-- Q2.7 — pythia_events SAMPLE (newest 5) — [GATE: `id` per Q2.0a]
-- ----------------------------------------------------------------------------
SELECT * FROM pythia_events ORDER BY id DESC LIMIT 5;

-- ----------------------------------------------------------------------------
-- Q2.8 — pythia_events RECEIPT CENSUS — [GATE: `created_at`, `event_type`
--        per Q2.0a; if either is absent, STOP this query — Q2.7's sample
--        already gives us the schema for a round-3 rewrite]
-- ----------------------------------------------------------------------------
SELECT date_trunc('day', created_at) AS utc_day, event_type, COUNT(*) AS n
FROM pythia_events
WHERE created_at >= '2026-07-30T00:00:00'
  AND created_at <  '2026-08-16T00:00:00'
GROUP BY 1, 2
ORDER BY 1, 2
LIMIT 200;

-- ----------------------------------------------------------------------------
-- Q2.9 — signal_options_expressions SAMPLE (newest 5) — [GATE: `id`]
-- ----------------------------------------------------------------------------
SELECT * FROM signal_options_expressions ORDER BY id DESC LIMIT 5;

-- ----------------------------------------------------------------------------
-- Q2.10 — signal_options_expressions RANGE — [GATE: `created_at`]
-- ----------------------------------------------------------------------------
SELECT COUNT(*) AS n, MIN(created_at) AS earliest, MAX(created_at) AS latest
FROM signal_options_expressions;

-- ============================================================================
-- END STRIKE-Q2 SQL. Code-read tasks CR-1..CR-7 are in the companion brief.
-- Results file: docs/strike/queries/results/<RUN-DATE>-STRIKE-Q2-RESULTS.md
-- ============================================================================
