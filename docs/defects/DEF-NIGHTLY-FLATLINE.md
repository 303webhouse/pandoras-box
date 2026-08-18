# DEF-NIGHTLY-FLATLINE

**Severity:** P2 (root-cause owed; symptom cleared) · **Filed:** 2026-08-18 · **Status:** MONITORING
**Surface:** nightly job (outcome walk / recompute chain), /health job-age field

## Symptom
Nightly job age reached ~242,518s (~2.8 days) as of 2026-08-17 20:5x UTC
(pre-existing before that day's pushes; delta across the STRIKE push equaled
wall-time exactly, proving push-independence). Self-recovered by the Q2
session: age 3.6h at 2026-08-18 04:42 UTC, /health "healthy".

## Why it matters
The nightly performs outcome grading and terminal-status transitions; a silent
multi-day stall contaminates status distributions (STRIKE-Q1 Q1a late-window
counts carry this caveat) and delays expiries.

## Open questions
What killed it ~2026-08-14/15, and what revived it ~2026-08-17? No alert fired
for a 2.8-day stall — alerting gap is part of this ticket.

## Fix path
Pull job scheduler/logs for 08-13->08-17; add stall alert (age > 26h during
weekdays). Close on root cause identified + alert deployed.
