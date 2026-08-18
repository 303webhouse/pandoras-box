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

## 2026-08-18 — CR-5 reshape (STRIKE-Q2)

The STRIKE-Q2 code read (CR-5) reshapes this ticket. Recorded as an addendum;
the original text above stands unaltered.

**The table is `squeeze_scores`, not a `%hydra%` table.**
`hub_get_hydra_scores` imports `get_squeeze_scores` from
`backend/services/read_only/squeezes.py` and issues a direct
`SELECT * FROM squeeze_scores` (`squeezes.py:39,48`). It is a Postgres read —
not Redis, not an external API.

**Consequence for step 1 of the fix path above:** STRIKE-Q1 §Q8 could never have
inspected it. Q8 was name-gated on `hydra_scores`, and Q1's Q0.2 preflight
searched `%hydra%`, which cannot match `squeeze_scores`. Q8 was correctly
STOPPED, not run. The absence of a `%hydra%` table is therefore **not** evidence
of a missing table — the table is named after the mechanism, not the codename.

**The "job dead" branch is the live one.** `backend/hub_mcp/tools/hydra_scores.py`
states it in code, verbatim:

```python
HYDRA_STALE_SECONDS = 86_400  # 1 day; no rescan cron exists, so older = stale
```

and at `:122-126`:

> *"FLOOR: derive honest staleness from the freshest row's updated_at. No rescan
> cron exists, so April-1 data must NOT be served as if live. This replaces the
> previously hardcoded staleness_seconds=1800 (fake-healthy)."*

So the `stale:false` half of the original symptom has already been partially
repaired — a hardcoded 1800 was replaced by a real `updated_at`-derived age.
The **empty-result-with-null-provenance** half remains: when `candidates` is
empty, `hydra_scores.py:105-120` returns `stale: False` with
`last_scan_at: null` and `data_age_seconds: null`, because staleness is derived
from returned rows and there are none to derive from.

**Fix (unchanged in substance, now specific):** build/restore the scan cron that
populates `squeeze_scores`, and emit `last_scan_at` unconditionally — sourced
from the scan job's own run record rather than from the returned rows, so an
empty scan still carries proof it ran.

**Not fixed this session** (Phase-A scope fence: one code line, the A1 set edit).
