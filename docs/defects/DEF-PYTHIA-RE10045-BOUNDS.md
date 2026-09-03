# DEF-PYTHIA-RE10045-BOUNDS · P1

**Root cause of the 2026-07/08 feed collapse.** Registered R-IV.236(a) on the principal's
TradingView panel read. **Confirmed, not hypothesised** — the panel carries the runtime
error text.

---

## The bug

Pine runtime error at `#main():153`:

```
array.get() index 50, array size 50
```

A zero-indexed array of size 50 has no index 50. The call is off by one at the boundary,
so it raises **only when the index reaches the array's length** — which is why the
indicator ran correctly for months before dying.

## Why it kills permanently

TradingView treats a runtime calculation error as **fatal to the alert**, not to the bar.
The alert transitions to **STOPPED — "Calculation error"** and **does not resume**. There
is no retry, no backoff, no self-heal. **Kill-on-compute.**

That is the mechanism behind the shape: an alert does not degrade, thin out, or become
intermittent. It runs, hits the bad index once, and stops forever.

## The wave shape is the platform, not the market

Deaths clustered on 07-27 (39), 07-28 (39), 07-30 (20), 08-04 (25) rather than arriving
evenly. Those are **platform recalculation sweeps** marching symbols across the bug: a
recalc forces the indicator to re-evaluate, the array reaches index 50, the alert dies.
Symbols die in the batch their recalc lands in, not in the order they were created.

## STALE = 0 IS THIS MECHANISM'S FINGERPRINT

Cited on the face per R-IV.236(a). Measured 2026-09-03 across all 212 tickers:

```
ok 6   stale 0   dark 206
```

**Not one ticker is exactly one session behind.** Every ticker is either current or long
dead — the collapse has **no gradient**.

That is exactly what kill-on-compute predicts and exactly what gradual delivery decay
does not. A degrading delivery path produces a spread of ages: some tickers one session
behind, some three, some ten. **A binary distribution across 212 symbols is the signature
of an instantaneous per-alert kill**, and it was measurable from the database before the
panel was read.

## The delivery layer is EXONERATED

R-IV.236(b): the TradingView log carries **1,571 rows and zero webhook failures**. The
webhook, the endpoint, and the network were never implicated. The taxonomy correction:
QQQ and SMH move from `fired-delivery-failed` to **DIED-AT-SOURCE**, and so do the other ~204.

**The falsified claim was red-exclamation-equals-delivery-failure** — platform semantics
asserted from general knowledge without reading the panel. That entry is spine's, addressed
to the R-IV.228 text. This lane's contribution to the error was carrying the assertion
forward into the taxonomy without marking it as unread; the taxonomy did fence the ~204 as
**NOT SEPARABLE from inside the DB**, which is why the correction lands on one row rather than the whole table.

## Remediation topology (R-IV.236(c))

| alert | id | state |
|---|---|---|
| PREY LIST watchlist (mass coverage) | 5223594262 | live |
| dedicated IWM | 5223596038 | live |
| recreated SPY | 5223591988 | live |
| QQQ, SMH | — | **stopped** |

**Alerts must be RESTARTED after the script fix to bind the new version.** A fixed script
does not revive a stopped alert on its own. Expect the universe to restore **in waves as
restarts land**, not at once.

**Watermark baselines begin incrementing only then.** Until a restart lands for a given
ticker, `DEF-STRIKE-WATERMARK-NEVER-ALIVE` holds it at `baseline_sessions = 1`, which is the interaction to watch: the
never-alive defect and this one clear together or not at all.

## What this does NOT unblock

**SPEC-01 re-derivation still gates on a stable universe** (R-IV.233(c)). A restored feed
is not a stable one, and rates re-derived mid-restoration would be measured over a moving
population — the same error class as the 8–34/day figure read off 12 survivors of 203.

## Open

The fix itself is with the principal. R-IV.236(d): 3DTE's "v2.5 delivered 09-02" is
contradicted, and classification is held until the closing handoff shows what exists —
if it carries the script, deployment is the next step; if not, the line-153 fix is
authored from the editor read.
