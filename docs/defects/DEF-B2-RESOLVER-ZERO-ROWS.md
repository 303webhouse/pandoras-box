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

## Fix path
Phase-A Phase 4 delivers root cause + minimal fix proposal (no fix in-session).
Acceptance after fix: >=1 row written during one RTH session with plausible
contents.
