-- ============================================================================
-- STRIKE-Q1 — Melt-Up Signal Census (DESCRIPTIVE ONLY)
-- Filed 2026-08-17 · Lane: STRIKE · Executor: CC (verbatim protocol)
-- ============================================================================
-- PROTOCOL (binding):
--   * SELECT-only. No DDL, no DML, no temp tables.
--   * Execute queries in order. Q0 is a GATE: verify every table and column
--     referenced in Q1–Q9/Q1a appears in Q0 output. ANY mismatch → STOP,
--     return Q0 output unedited, do not run further queries, do not rewrite.
--   * Errors are returned unedited. No query rewriting by the executor.
--   * All timestamps computed in-DB in UTC (EDGE trust rule: transport
--     timestamps unreliable). Never re-render timestamps client-side.
--   * COUNT(*) only. No planner estimates.
--   * This census is DESCRIPTIVE. No outcome grades, no expectancy, no edge
--     claims. signal_outcomes is intentionally NOT queried (EDGE's book).
--
-- WINDOWS (UTC, half-open [start, end)):
--   CORE  (melt-up):      2026-07-30T00:00Z → 2026-08-05T00:00Z
--   Q1a   (trip window):  2026-08-05T00:00Z → 2026-08-16T00:00Z
--
-- SEMIS/AI subset used throughout:
--   ('NVDA','AMD','AVGO','MRVL','ARM','INTC','MU','TSM','SMCI','ALAB',
--    'CRDO','ANET','VRT','WOLF','ENTG','LRCX','AMAT','QCOM','LSCC','MXL',
--    'UMC','ON','KLAC','COHR','AAOI','FN','SOXL','SOXS','SMH','SOXX','QQQ')
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Q0. PREFLIGHT (gate — run first, return output in full)
-- ----------------------------------------------------------------------------
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('signals','unified_positions','trades','trade_legs')
ORDER BY table_name, ordinal_position;

SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND (table_name ILIKE '%webhook%' OR table_name ILIKE '%pythia%'
       OR table_name ILIKE '%market_profile%' OR table_name ILIKE '%mp_%'
       OR table_name ILIKE '%hydra%'   OR table_name ILIKE '%b2%'
       OR table_name ILIKE '%resolver%' OR table_name ILIKE '%options%'
       OR table_name ILIKE '%tag%'     OR table_name ILIKE '%watch%')
ORDER BY table_name;

-- ============================ GATE CHECK HERE ===============================
-- Q1–Q5, Q9, Q1a reference: signals(created_at, status, score, ticker,
-- strategy) and unified_positions(ticker). Q6–Q8 are NAME-GATED (see notes
-- at each). If 'strategy' is not a signals column (e.g., it is
-- 'strategy_name' or 'signal_type'), STOP and return Q0 output.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Q1. CORE census — daily counts by status (UTC days)
-- ----------------------------------------------------------------------------
SELECT date_trunc('day', created_at AT TIME ZONE 'UTC') AS utc_day,
       status,
       COUNT(*) AS n
FROM signals
WHERE created_at >= '2026-07-30T00:00:00Z'
  AND created_at <  '2026-08-05T00:00:00Z'
GROUP BY 1, 2
ORDER BY 1, 2;

-- ----------------------------------------------------------------------------
-- Q2. CORE census — counts by raw strategy label × status
--     (labels are RAW; Rosetta translation happens in the results doc, from
--      backend/config/strategy_aliases.py — executor appends that file's
--      mapping verbatim to the results)
-- ----------------------------------------------------------------------------
SELECT strategy, status, COUNT(*) AS n,
       MIN(score) AS min_score, MAX(score) AS max_score
FROM signals
WHERE created_at >= '2026-07-30T00:00:00Z'
  AND created_at <  '2026-08-05T00:00:00Z'
GROUP BY 1, 2
ORDER BY n DESC
LIMIT 100;

-- ----------------------------------------------------------------------------
-- Q3. CORE census — semis/AI subset: daily counts + score stats
-- ----------------------------------------------------------------------------
SELECT date_trunc('day', created_at AT TIME ZONE 'UTC') AS utc_day,
       COUNT(*) AS n,
       COUNT(*) FILTER (WHERE score >= 65) AS n_ge65,
       MAX(score) AS max_score
FROM signals
WHERE created_at >= '2026-07-30T00:00:00Z'
  AND created_at <  '2026-08-05T00:00:00Z'
  AND ticker IN ('NVDA','AMD','AVGO','MRVL','ARM','INTC','MU','TSM','SMCI',
                 'ALAB','CRDO','ANET','VRT','WOLF','ENTG','LRCX','AMAT',
                 'QCOM','LSCC','MXL','UMC','ON','KLAC','COHR','AAOI','FN',
                 'SOXL','SOXS','SMH','SOXX','QQQ')
GROUP BY 1
ORDER BY 1;

-- ----------------------------------------------------------------------------
-- Q4. CORE detail — top rows by score (full rows for STRIKE review)
-- ----------------------------------------------------------------------------
SELECT *
FROM signals
WHERE created_at >= '2026-07-30T00:00:00Z'
  AND created_at <  '2026-08-05T00:00:00Z'
ORDER BY score DESC NULLS LAST
LIMIT 50;

-- ----------------------------------------------------------------------------
-- Q5. CORE — score distribution buckets × status
-- ----------------------------------------------------------------------------
SELECT width_bucket(score, 0, 100, 10) AS score_decile,
       status,
       COUNT(*) AS n
FROM signals
WHERE created_at >= '2026-07-30T00:00:00Z'
  AND created_at <  '2026-08-05T00:00:00Z'
GROUP BY 1, 2
ORDER BY 1, 2;

-- ----------------------------------------------------------------------------
-- Q6. Webhook receipt audit — NAME-GATED
--     Substitute NOTHING. If Q0's table list does not contain a table whose
--     name plainly identifies the PYTHIA/TradingView webhook event store,
--     STOP and return Q0 output. If it does and the name differs from
--     'webhook_events', return Q0 output with a note instead of running this.
-- ----------------------------------------------------------------------------
SELECT date_trunc('day', received_at AT TIME ZONE 'UTC') AS utc_day,
       COUNT(*) AS n
FROM webhook_events
WHERE received_at >= '2026-07-30T00:00:00Z'
  AND received_at <  '2026-08-16T00:00:00Z'
GROUP BY 1
ORDER BY 1;

-- ----------------------------------------------------------------------------
-- Q7. b2_options_resolver audit — NAME-GATED (same rule as Q6; expected name
--     from code is unknown; use Q0's '%b2%'/'%resolver%'/'%options%' hits)
-- ----------------------------------------------------------------------------
SELECT COUNT(*) AS n_rows FROM b2_options_shadow;
SELECT * FROM b2_options_shadow ORDER BY 1 DESC LIMIT 5;

-- ----------------------------------------------------------------------------
-- Q8. Hydra heartbeat — NAME-GATED (use Q0's '%hydra%' hit)
-- ----------------------------------------------------------------------------
SELECT COUNT(*) AS n_rows FROM hydra_scores;
SELECT * FROM hydra_scores ORDER BY 1 DESC LIMIT 10;

-- ----------------------------------------------------------------------------
-- Q9. QQQ 360/350 position row inspection (DEF candidate: negative
--     current_price rendering in unified_positions)
-- ----------------------------------------------------------------------------
SELECT *
FROM unified_positions
WHERE ticker = 'QQQ'
ORDER BY 1 DESC
LIMIT 20;

-- ----------------------------------------------------------------------------
-- Q1a. TRIP-WINDOW EXTENSION (2026-08-05 → 2026-08-16): reruns of Q1/Q2/Q3/Q5
-- ----------------------------------------------------------------------------
SELECT date_trunc('day', created_at AT TIME ZONE 'UTC') AS utc_day,
       status, COUNT(*) AS n
FROM signals
WHERE created_at >= '2026-08-05T00:00:00Z'
  AND created_at <  '2026-08-16T00:00:00Z'
GROUP BY 1, 2
ORDER BY 1, 2;

SELECT strategy, status, COUNT(*) AS n,
       MIN(score) AS min_score, MAX(score) AS max_score
FROM signals
WHERE created_at >= '2026-08-05T00:00:00Z'
  AND created_at <  '2026-08-16T00:00:00Z'
GROUP BY 1, 2
ORDER BY n DESC
LIMIT 100;

SELECT date_trunc('day', created_at AT TIME ZONE 'UTC') AS utc_day,
       COUNT(*) AS n,
       COUNT(*) FILTER (WHERE score >= 65) AS n_ge65,
       MAX(score) AS max_score
FROM signals
WHERE created_at >= '2026-08-05T00:00:00Z'
  AND created_at <  '2026-08-16T00:00:00Z'
  AND ticker IN ('NVDA','AMD','AVGO','MRVL','ARM','INTC','MU','TSM','SMCI',
                 'ALAB','CRDO','ANET','VRT','WOLF','ENTG','LRCX','AMAT',
                 'QCOM','LSCC','MXL','UMC','ON','KLAC','COHR','AAOI','FN',
                 'SOXL','SOXS','SMH','SOXX','QQQ')
GROUP BY 1
ORDER BY 1;

SELECT width_bucket(score, 0, 100, 10) AS score_decile,
       status, COUNT(*) AS n
FROM signals
WHERE created_at >= '2026-08-05T00:00:00Z'
  AND created_at <  '2026-08-16T00:00:00Z'
GROUP BY 1, 2
ORDER BY 1, 2;

-- ============================================================================
-- END STRIKE-Q1. Results file: docs/strike/queries/results/
--   2026-08-17-STRIKE-Q1-RESULTS.md  (raw outputs + Rosetta mapping appended)
-- ============================================================================
