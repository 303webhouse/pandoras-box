# DEF-HYDRA-NULL-SCAN

**Severity:** P2 · **Filed:** 2026-08-17 · **Status:** OPEN
**Surface:** `hub_get_hydra_scores`

## Symptom
Global read returns `candidates: []`, `candidate_count: 0`, `last_scan_at:
null`, `data_age_seconds: null`, `stale: false` — an empty result that cannot
be distinguished from "scanner never ran." Observed 2026-08-04 during the
largest short-squeeze-favorable tape of the year (SOXL +19.9% day).

## Why it matters
Honest-seam violation: `stale:false` with no scan timestamp is a confident
answer with no provenance. Squeeze detection silent during a squeeze is either
a coverage gap or a dead job — both are P2, but which one determines the fix.

## Verification / fix path
1. STRIKE-Q1 §Q8 inspects the hydra table directly (row count + latest rows).
2. If job dead: restore scan cron; emit `last_scan_at` unconditionally.
3. If job alive but empty: emit `last_scan_at` + scan universe size so empty
   results carry proof of scan; `stale` computed off `last_scan_at`, never
   defaulted false.
