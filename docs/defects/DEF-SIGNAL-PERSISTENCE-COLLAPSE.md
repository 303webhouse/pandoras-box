# DEF-SIGNAL-PERSISTENCE-COLLAPSE

**Severity:** P0 · **Filed:** 2026-08-19 · **Status:** MECHANISM CAPTURED — FIX SHIPPED 2026-08-21
**Mechanism:** NaN-POISON — a non-finite float reaches `json.dumps`, which emits the bare
tokens `NaN`/`Infinity`/`-Infinity` (valid JavaScript, invalid JSON); Postgres rejects the
JSONB bind; the exception is swallowed; the pipeline reports success on a row that does not exist.
**Surface:** `signals` table write path (all emitters)
**Found by:** CC-SHELL, Phase-A day-two observation check

## Symptom

Signal **creation collapsed ~99% starting 2026-08-18** and has not recovered.
Counts are `COUNT(*)` from `signals`, in-DB day bucketing, UTC:

| UTC day | rows in `signals` |
|---|---|
| 2026-08-17 | **140** |
| 2026-08-18 | **2** |
| 2026-08-19 | **1** |

Baseline for comparison, same table, same method: 08-14 = 143, 08-10..08-14
HG_1H alone ran 40–73/day.

## The pipeline is running — the rows are not landing

This is not a quiet scanner. Deploy logs for `f86d2021` (commit `afef615`) show
the pipeline completing normally during 08-19 RTH:

```
INFO:signals.pipeline:✅ Pipeline complete: SBUX (cta_scanner, score=64.9) in 3003.3ms
INFO:signals.pipeline:✅ Pipeline complete: EMR  (cta_scanner, score=56.1) in 3081.0ms
INFO:signals.pipeline:✅ Pipeline complete: SOL  (crypto_scanner, score=50.0) in 2143.5ms
```

And the B2 resolver, which is called at the end of `process_signal_unified`,
names specific signal_ids it was handed on 08-19:

```
b2: create_b2_expression failed for SOL-USD_LONG_20260819_170103: …
b2: create_b2_expression failed for SOL-USD_LONG_20260819_173136: …
b2: create_b2_expression failed for SOL-USD_LONG_20260819_180210: …
```

**None of those three signal_ids exist in `signals`** (exact `IN (...)` lookup,
0 rows). So signals are being processed end-to-end — scored, logged complete,
and handed to downstream consumers — while the row is absent from the system of
record.

## Cause NOT attributed

Stated explicitly rather than guessed, per the recall/artifact convention:

- **Not attributable to the Phase-A A1 flip on mechanism.** `ae99def` changed
  frozenset membership consumed by a read-side filter and a tag computation. It
  contains no write path and cannot block an INSERT. `evaluate_l0_gate` was
  verified working at flip time and again at re-suppression.
- **Timing is nonetheless coincident** with the 08-18 deploy window and must not
  be hand-waved: the collapse begins with the first RTH session after it.
- **One row landed at 22:30:31 on 08-19** (`SOL-USD_LONG_20260819_183028`,
  TWO_CLOSE_VOLUME, Crypto Scanner) — minutes after deployment `4cc0f2cf`
  (`3549dad`). Whether that is recovery or coincidence is **not established**;
  n=1.

## Why it matters

Everything downstream reads `signals` as system of record. While this holds:

- Phase-A observation is **collecting nothing** — the 7-day HG_1H watch has no
  data for 08-18 or 08-19, independent of the suppression state. The 08-25
  reconvene cannot be graded on this window.
- EDGE Track A denominators drawn over these dates would be **silently short**,
  and the shortfall is invisible without this ticket — a deaf window that
  produces absence, not error.
- Any "no signals fired" reading of this period is an artifact, not a market
  observation.

## Next diagnostic (not run — needs an owner)

1. Determine whether `log_signal` / `update_signal_with_score` are raising, and
   where those exceptions terminate — the pipeline logs "complete" regardless.
2. Check for a failing INSERT constraint, connection-pool exhaustion, or a
   swallowed write error on the persistence path.
3. Confirm whether the 08-19 22:30 row indicates recovery by watching the next
   full RTH session's count against the ~140/day baseline.

**Do not close on the single 22:30 row.**


---

## RESOLUTION (2026-08-21)

**Census of record: 459 signals lost** — 08-18: 249, 08-19: 210, 08-20: 0. Measured
from orphan `signal_outcomes` rows: `write_signal_outcome` runs six lines after
`log_signal`, in a separate transaction, binds no JSON, and succeeded throughout, so
outcome rows without a matching signal are an exact census. This supersedes the
earlier log-derived floors (188/128), which were flagged as floors at filing.

**Signature:** healthy writer, per-row JSONB rejection of a globally poisoned payload.
The sole `INSERT INTO signals` (`postgres_client.py:1646`) binds 37 columns of which
exactly two are JSONB — `$19 triggering_factors` and `$20 bias_at_signal` — so the
failing bind is one of those two.

**Triplet of record:** last good write 2026-08-18 04:12:38Z · death expression
2026-08-18 13:23:37.8Z (first orphan, `HG_SPY_20260818_132235_both`) · restoration
2026-08-19 22:30:31Z. Poison-entry bracket (07:17:00Z, 13:23:37.8Z] on 08-18.
**Clearing mechanism FORMALLY OPEN:** no write was attempted in
[22:02:11Z → 22:27:44Z], so restart/container-wipe cannot be distinguished from
independent clearing inside that attempt-free interval.

### Retractions, on the record

* **ATR/enrichment attribution — WITHDRAWN.** `enrich_signal()` runs at
  `pipeline.py:1447`, **69 lines after** `log_signal()` at `:1378`; the `ATR=nan`
  log line is emitted *after* that signal's INSERT was already attempted. Adjacent
  log lines belong to different signals. `enrichment_data` is not in the INSERT at
  all. Lost signals include `SOL-USD_*`, and `signal_enricher.py:53-54` returns early
  for CRYPTO before any enrichment dict exists. **ATR NaN was a concurrent
  non-lethal decoy.** Caught by an adversarial reviewer pre-ship.
* **`ae99def` (HOLY_GRAIL_1H un-suppression) — EXONERATED.** Independent code proof:
  `SUPPRESS_ALWAYS` membership is tested at exactly 2 lines repo-wide, reachable only
  via `evaluate_l0_gate()`, which has 1 production caller that is pure and never
  diverts; `should_divert()` has 0 production call sites. L0 is surface-only and sits
  after persistence.
* **`bias_at_signal["scheduler_bias"]` — NAMED CANDIDATE, NOT CAUSE.** Sourced from
  `data/bias_history.json`, NaN-permissive in both directions, global to every signal,
  untracked in git so it lives on ephemeral container FS. Matches the deploy bracket.
  **Cannot be proven — the value is retained nowhere.** The fix closes the class, not
  the instance.

### Fix

`utils/json_sanitize.dumps_jsonb()` is now the single chokepoint for every JSONB
bind: non-finite → `null` + named degraded path, never zero, never silent;
`allow_nan=False` locked. **51 call sites routed**, fence-asserted in CI with
multi-line, variable-held and `*params` detection. Completion status is now the
persistence outcome (persisted / dedupe / failed). `signals_freshness` in `/health`
carries table-sourced staleness plus an issued-vs-persisted reconciliation counter,
with a Discord watchdog consumer — `/health` had **zero clients**, so the surface
alone would have been another fake-healthy seam.

See `docs/codex-briefs/2026-08-20-brief-def-signal-persistence-collapse.md`.

### Still open, filed separately

DEF-BGTASK-NO-SUPERVISION (nothing restarts a dead background task; 0 clients of
`/health`) · REC-008 swallow hardening (139 broad handlers, 0 re-raise, 109 swallows)
· read-side reservoir sanitize (`json.loads` accepts bare NaN) · `bias_history.json`
provenance (→ T8).
