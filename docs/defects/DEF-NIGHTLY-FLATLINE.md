# DEF-NIGHTLY-FLATLINE

**Severity:** P2 · **Filed:** 2026-08-18 · **Amended:** 2026-08-25 (R-IV.70(c))
**Status:** OPEN — recharacterised. The job is not the defect; the instrument is.
**Surface:** `backend/stable_engine/job_status.py` (SLO table + `health_summary`),
`/health` → `stable_jobs`

## HEADLINE

**Recurrence claim retracted (weekend-gate artifact, verified); original instance
re-attribution pending timestamp verification.**

`backend/jobs/stable_jobs.py:216` gates the whole schedule on `is_weekday(et)`
(`dt.weekday() < 5`) and `NIGHTLY_TIME = (21, 0)` ET. The job therefore cannot run
Sat or Sun, and the maximum legitimate gap is **Fri 21:00 ET → Mon 21:00 ET = 72h**.

## Defect 1 — weekend-SLO false red

`job_status.py:29` sets `"nightly": 26 * 3600`. A **26h SLO on a weekday-only job
with a 72h maximum legitimate gap** renders `flatline` every weekend, **by
construction** — roughly **104 false reds per year**.

This is the alarm-fatigue class (cf. DEF-SIGNALS-WATCHDOG-STALE-REFIRE facet 1): an
alarm that cries on a standing, correct condition trains its reader to discount it.
It has already produced one wrong finding — CC-BUILD reported a recurrence on
2026-08-24 off a 70.6h age that was the gate working correctly (retracted same
session, R-IV.70(a)).

The ticket's own original fix path already specified the right shape — "add stall
alert (age > 26h **during weekdays**)". The deployed SLO carries no weekday scoping.

## Defect 2 — multi-writer feed semantics

`JOB_FEEDS` maps **both** `nightly` and `provisional` to the single feed `"nightly"`.
But `health_summary()` evaluates **each job's own age** against that **feed's** SLO,
and computes `oldest_feed_age_s` with `max()` across jobs. For a feed with more than
one writer the true age is the **min** — the most recent write wins.

Observed 2026-08-24 23:39Z: reported `oldest_feed_age_s = 254,208`; the freshest
write to that same feed was **12,822s** (the `provisional` job). The instrument
reported a feed 20× staler than it was.

Note, no action: `stable_engine/signals_freshness.py` mirrors this per-class
contract, but every signals class is single-writer, so the same shape is harmless
there. Left as-is deliberately.

## Honest-seam observation — `as_of` vs `date`

Adjudicated from the data, not the job ledger. `stable_theme_scores` on
2026-08-25 00:0xZ:

- `MAX(as_of)` = `2026-08-24 20:05:55Z` — **3.9h old** (a fresh write)
- `MAX(date)` = **`2026-08-21`** — Friday content
- latest `close`-anchored rows are trading day 08-21; none for 08-22/23/24

The `provisional` job re-stamps **prior-trading-day content with a current
`as_of`**. A consumer reading `as_of` sees 3.9h fresh; a consumer reading `date`
sees Friday. Both fields are individually truthful; read alone, `as_of` overstates
the vintage.

## STRIKE LINEAGE

- **2026-08-24 recurrence claim — STRUCK.** "Last success 08-22 01:02:48Z, 70.6h,
  therefore recurred" ignored the weekday gate. Verified: last fire was 21:02 ET
  **Fri 08-21**; Sat 08-22 and Sun 08-23 were correctly skipped; the next due window
  was 21:00 ET Mon 08-24. **No window was missed.** `consecutive_failures: 0` and
  `last_error: null` were accurate throughout.

  **CONFIRMED by the next window.** The 21:00 ET Mon 08-24 run fired normally:

  ```
  2026-08-25T01:00:37  [stable_jobs] nightly close recompute starting
  2026-08-25T01:03:36  [stable_jobs] nightly close recompute done:
      {'coverage': 98.41, 'degraded': False, 'metrics_rows': 861543, 'themes_stored': 21}
  ```

  Clean run, no intervention, no kick. The job was never broken.
- **Absence-law violation, self-named.** The claim was made without first
  establishing the expected event rate across the absence — the same law the
  author had applied correctly twenty minutes earlier on a different check in the
  same session. Recorded as the era's evidence that laws need instruments, not
  memory.
- **Original 2026-08-18 instance — re-attribution PENDING** per R-IV.70(b).
  Log verification is **unavailable, not negative**: Railway logs are
  deployment-scoped and the current deployment was created 2026-08-21T05:31Z; a
  sanity probe returned zero lines for *any* message in 08-14–08-18, so the query
  is dead rather than clean.
  What *is* available is arithmetic on the ticket's own recorded numbers, and both
  observations reconstruct onto weekday 21:0x ET windows:
  - age ~242,518s observed 08-17 20:5xZ → last success `2026-08-15T01:28Z` =
    **Fri 21:28 ET 08-14**
  - age 3.6h observed 08-18 04:42Z → last success `2026-08-18T01:06Z` =
    **Mon 21:06 ET 08-17**
  The recorded 04:42Z was the **observation** moment, not the recovery moment —
  which resolves the 3.7h offset R-IV.70(b) flagged. Ruling on whether this
  evidence class suffices is spine's; the ticket does not flip on it here.

## Original text, retained for lineage

> **Symptom.** Nightly job age reached ~242,518s (~2.8 days) as of 2026-08-17 20:5x
> UTC (pre-existing before that day's pushes; delta across the STRIKE push equaled
> wall-time exactly, proving push-independence). Self-recovered by the Q2 session:
> age 3.6h at 2026-08-18 04:42 UTC, /health "healthy".
>
> **Why it matters.** The nightly performs outcome grading and terminal-status
> transitions; a silent multi-day stall contaminates status distributions
> (STRIKE-Q1 Q1a late-window counts carry this caveat) and delays expiries.
>
> **Open questions.** What killed it ~2026-08-14/15, and what revived it
> ~2026-08-17? No alert fired for a 2.8-day stall — alerting gap is part of this
> ticket.

The "open questions" above are now believed malformed: they presuppose a fault.
Nothing killed it — Fri 08-14 was its last weekday window — and Mon 08-17's
scheduled run revived it. Retained verbatim per strike convention.

## Fix path

1. Scope the nightly SLO to weekdays, or size it to the 72h Fri→Mon gap. A
   discriminating test must fail on a Saturday-evening clock and pass on a
   Tuesday-evening one — a single-clock assertion could not fail.
2. Give `health_summary` multi-writer feed semantics: feed age = `min()` across the
   jobs that freshen it; `oldest_feed_age_s` = max over **feeds**, not over jobs.
3. Optional, separate: surface `date` alongside `as_of` wherever theme scores are
   rendered, so prior-day content cannot read as current.

Close on 1 + 2 shipped with fail-first tests. Defect 3 rides its own line.
