# DEF-SIGNAL-PERSISTENCE-COLLAPSE

**Severity:** P0 (proposed) · **Filed:** 2026-08-19 · **Status:** OPEN — CAUSE UNATTRIBUTED
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
