# DEF-B2-RESOLVER-ZERO-ROWS

**Severity:** P2 · **Filed:** 2026-08-18 · **Status:** OPEN (diagnosis assigned: Phase-A Phase 4)
**Surface:** jobs/b2_options_resolver -> `signal_options_expressions`

## Symptom
Both entry points live (fire-and-forget pipeline.py:1540; 15-min market-hours
task main.py:1046; B2_SHADOW_MODE default true) yet the output table holds
0 rows ever (STRIKE-Q2 Q2.0b/CR-6).

## Why it matters
This job is the designed collector of shadow options expressions — the friction
snapshots STRIKE-SPEC-02/03 need for the $100-300 clip math. Fire-and-forget
architecture means its failures are silent by construction.

## ROOT CAUSE OBSERVED — A4/OBS-01 EOD RTH grep, 2026-08-19

Spine approved the EOD `b2:` grep as the day-one observation artifact. Run by
CC-SHELL against RTH 2026-08-19 13:30–20:00Z (500 log lines in window).

**10 matches, every one the same failure. Zero successes.**

```
WARNING:jobs.b2_options_resolver:b2: create_b2_expression failed for
  ARTEMIS_SPGI_20260819_195624_767882: invalid input for query argument $3:
  '2026-08-28' ('str' object has no attribute 'toordinal')
```

Identical for `ARTEMIS_UPS_…`, `ARTEMIS_HYG_…`, `SOL-USD_LONG_20260819_155944`
and four UUID-keyed signals. Affected signals span equity and crypto emitters.

**The job is not skipping — it is reaching the write and failing there.** The
early-return skip conditions (`:206-216`) are not the cause: those return
silently without logging, and we observe the exception path at `:371` instead.
No `b2: expression created` INFO line appears anywhere in the window, and
`signal_options_expressions` remains at **0 rows** (confirmed same-session).

**Mechanism:** asyncpg is rejecting a Python `str` where its inferred parameter
type is `date`. `'str' object has no attribute 'toordinal'` is raised by
asyncpg's DATE encoder — the expiry is being passed as the string `'2026-08-28'`
rather than a `datetime.date`. Because `create_b2_expression` swallows every
exception (`:370-371`, WARNING only) and the pipeline call site is
fire-and-forget (`pipeline.py:1540`), this has failed silently since the job
was wired. That is the "silent by construction" property this ticket already
named, now with the concrete failure behind it.

**Discrepancy the fix session must reconcile, stated rather than guessed:** the
log names `$3`, but in the INSERT at `b2_options_resolver.py:340-352` the third
bound argument is `long_strike` and the date-cast parameter is `$5::date`. Either
the deployed code differs from HEAD, or a second statement inside the same `try`
(e.g. `_capture_entry_mark`, `:365-368`) owns the failing bind. **Not resolved
here** — A4 is diagnosis-only and identifying the exact bind site requires
reading the running revision. The *class* of defect is established; the precise
line is not.

## Fix path
Phase-A Phase 4 delivers root cause + minimal fix proposal (no fix in-session).
Acceptance after fix: >=1 row written during one RTH session with plausible
contents. Direction now known: pass a real `datetime.date` for expiry (and audit
every other date-typed bind in this module), then re-run this same EOD grep —
absence of the `$3` warning plus a non-zero row count is the acceptance signal.
