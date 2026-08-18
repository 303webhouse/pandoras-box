-- ============================================================================
-- STRIKE-OBS-01 — HOLY_GRAIL_1H daily observation (watch week, Phase-A A1)
-- Run each evening after close (tiny; any time of day permitted).
-- Protocol: SELECT-only, session TZ UTC, passthrough typecasters, verbatim.
-- ============================================================================

-- OBS-1: last 36h of HG_1H rows, feed-relevant fields + persisted L0 tag
SELECT created_at, ticker, direction, score, status, user_action, feed_tier_v2,
       signal_category,
       triggering_factors->'l0_shadow'->>'would_suppress' AS l0_tag
FROM signals
WHERE signal_type = 'HOLY_GRAIL_1H'
  AND created_at >= (now() AT TIME ZONE 'UTC') - interval '36 hours'
ORDER BY created_at DESC
LIMIT 100;

-- OBS-2: 8-day creation counts, 1H vs 15M control group (15M stays suppressed)
SELECT date_trunc('day', created_at) AS utc_day, signal_type, COUNT(*) AS n,
       MAX(score) AS max_score
FROM signals
WHERE signal_type IN ('HOLY_GRAIL_1H','HOLY_GRAIL_15M')
  AND created_at >= (now() AT TIME ZONE 'UTC') - interval '8 days'
GROUP BY 1, 2
ORDER BY 1, 2;
