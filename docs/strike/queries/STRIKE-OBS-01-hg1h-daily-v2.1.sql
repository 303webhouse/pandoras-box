-- ============================================================
-- OBS-01 v2.1 — REGISTERED TEXT
-- Author 3DTE · co-author EDGE (signed 2026-08-25 pre-session)
-- Amendment authority R-IV.61(e); adoption conditions R-IV.82(c)
-- Supersedes v1 (sha256 a3ac7063f1d4fd14) on adoption.
--
-- OBSERVATION-DAY DEFINITION (D1, R-IV.82(b), binding):
--   An observation day is a US equity RTH session on which the
--   emitter was LIVE. A DARK session is RECORDED and DOES NOT
--   consume an observation day; the terminus shifts accordingly.
--   Calendar of record: d0 08-21 · d1 08-24 · d2 08-25 · d3 08-26
--   · d4 08-27 · d5 08-28 · d6 08-31 · d7 09-01.
--   LIVENESS PER READ (R-IV.82(d)): every read states EMITTER LIVE
--   or DARK with its OBS-0 basis. OBS-0 — not row presence — is the
--   deciding instrument; row-presence alone yields INDETERMINATE.
--
-- STAMP LAW (header requirement): every read carries as-of (in-DB
--   UTC), read path, registered-text sha256, dual provenance
--   (working-tree SHA + origin/main), dual-run stability hash,
--   manifest v2 fingerprints. Drift-checks use MSYS_NO_PATHCONV=1
--   with known-present/known-absent controls.
--
-- LABELS RIDING EVERY READ:
--   L1 suppression premise (creation-side under suppression,
--      R-IV.58(b)) · L2 record-death window (retires 08-28)
--   L3 HG_15M documented null · L4 RETIRED by OBS-2's epoch anchor
--   L5 OBS-1 cap (see OBS-1 note) · TRIPWIRE: immutable prior-day
--      counts detect record mutation, never market behavior.
--
-- EXPECTED-EVENT RATES (trading days; artifact-cited; weekend ≈ 0
-- for equity types) — population-scoped per the render-scope law:
--   HOLY_GRAIL_1H   ≈ 36–73/day (observed 73·36·63·66·58)
--   ARTEMIS_LONG    ≈ 15–20/day (622 rows 07-03→08-17, TAG-STRIP-1)
--   PULLBACK_ENTRY  ≈ 7–16/day CTA arm (Q2 127 rows 07-30→08-16;
--     ORPH-SRC-C 16 on 08-20); DUAL-EMITTER — crypto arm dark since
--     ~08-23; rate is CTA-only until stated otherwise
--   TRAPPED_LONGS   ≈ 0.1/day (4 rows / 6.5wks) — NEAR-NULL: daily
--     zeros EXPECTED; absence is neither deafness nor suppression
--   HOLY_GRAIL_15M  documented null (1 row lifetime; PR-105-c)
-- ABSENT-BUCKET RULE: GROUP BY emits no row for a zero type-day;
--   absence is adjudicated ONLY against these rates plus system
--   freshness — never read directly as deafness, death, or
--   suppression effect.
-- ============================================================

-- OBS-1 v2.1 — last 36h of HG_1H rows.
-- L5 FIX: cap raised 100 → 400 (36h span now exceeds 100; observed
-- max 124). ORDER BY created_at DESC trims OLDEST on truncation, so
-- a capped result looks complete — if this ever returns exactly 400,
-- treat every count as a FLOOR and take per-day figures from OBS-2.
SELECT created_at, ticker, direction, score, status, user_action,
       feed_tier_v2, signal_category,
       triggering_factors->'l0_shadow'->>'would_suppress' AS l0_tag
FROM signals
WHERE signal_type = 'HOLY_GRAIL_1H'
  AND created_at >= (now() AT TIME ZONE 'UTC') - interval '36 hours'
ORDER BY created_at DESC
LIMIT 400;

-- OBS-2 v2.1 — 8 prior FULL UTC days + today-partial.
-- Epoch-anchored: completed-day buckets are INVARIANT across reads;
-- partiality lives at the labeled, self-healing youngest edge.
-- This retires L4 (no oldest-bucket truncation exists by design).
-- Controls per the cca7e4b addendum; HG_15M retained as documented null.
SELECT date_trunc('day', created_at) AS utc_day, signal_type,
       COUNT(*) AS n, MAX(score) AS max_score
FROM signals
WHERE signal_type IN ('HOLY_GRAIL_1H','HOLY_GRAIL_15M','PULLBACK_ENTRY',
                      'TRAPPED_LONGS','ARTEMIS_LONG')
  AND created_at >= date_trunc('day', (now() AT TIME ZONE 'UTC'))
                    - interval '8 days'
GROUP BY 1, 2
ORDER BY 1, 2;
