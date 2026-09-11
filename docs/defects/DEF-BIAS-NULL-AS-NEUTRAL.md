# DEF-BIAS-NULL-AS-NEUTRAL · P1

> ## SHAPE OF RECORD (R-IV.336(a))
>
> **"A score emitted with its raw input ABSENT."** Not a score that is zero.
>
> **Live instance: `gex`, 35 of 695 readings (5.0%), INTERMITTENT.**
>
> **The discriminator, and it is now conventions #14:**
>
> ```
> raw varying under a constant score   ->  BAND         working as designed
> raw ABSENT   under any score         ->  FABRICATION  the defect
> ```
>
> **The payload is the only witness.** A derived value cannot witness its own input, and
> this file was mis-attributed twice — to four factors, then to `dxy_trend` — by reading
> scores instead of raw.

**Registered** 2026-09-08 by R-IV.321(c). **Confirmed live the same day** — measured, not
inferred. **Status:** OPEN. **P1: decision surface.**
**Census of record:** `docs/edge/results/2026-09-08-regime-factor-census.md`

---

> ## CORRECTION 2 — 2026-09-09: the instance is `gex`, 35 rows. `dxy_trend` WITHDRAWN.
>
> **CC-QUERY measured it (`docs/edge/results/2026-09-09-band-vs-dead-factor-discrimination.md`): `dxy_trend` is a BAND** — 196 distinct `current` values,
> 211 distinct `pct_change_5d`, raw present on every row. **Its no-data branch exists and is
> not being taken.**
>
> **THE LIVE POPULATION IS `gex`: 35 of 695 readings (5.0%) at score 0.0 with
> `raw_data = {}`. Every other factor has zero such rows.**
>
> **The mechanism stands and the helper is still the cause** — `gex` is one of the
> `neutral_reading()` callers. **What was wrong was the attribution**, twice: first to four factors,
> then to the wrong one of them.
>
> **The defect's true shape, and it is narrower and more precise than either earlier
> statement: a score emitted with its raw input ABSENT.** Not a score that is zero. The raw
> payload is the witness; the score never was.
>
> **P1 stands.** 5% of GEX readings tell a consumer "neutral" when the correct answer is
> "unavailable", on a decision surface, with nothing distinguishing them.

> ## CORRECTION — 2026-09-08 evening: ONE INSTANCE, NOT FOUR
>
> **This file was registered on a four-factor observation. Three of those four are
> WITHDRAWN.** `spy_trend_intraday`, `breadth_intraday` and `copper_gold_ratio` have **0.0 as their designed middle scoring
> band**, and all three correctly return `None` when data is missing — which makes
> `factor_scorer.py:87-97` delete their cache key so the composite excludes them. **The ruled fix already
> exists for them.**
>
> **The defect is real and narrow: `dxy_trend`.** Its `compute_score()` is typed `-> FactorReading` rather than
> `Optional[FactorReading]`, **so it cannot return `None`** and the exclusion path can never fire. On the
> no-data branch it returns `neutral_reading()` — score 0.0, `datetime.utcnow()` timestamp — and
> `factor_history` confirms it dead since 2026-07-23.
>
> **The severity does not move.** One fabricating factor on a decision surface, invisible by
> construction, is still P1. **What moves is the population and therefore the fix's scope.**

## The defect

**A factor with no data renders as `0.0`, is marked `is_stale: false`, and is counted
`active_weight_sum`.** `0.0` on this scale is not "absent" — it is **NEUTRAL**, a real reading. So a
dead factor votes, and votes for no change.

## Measured 2026-09-08 15:04 ET

```
spy_trend_intraday   score 0   staleness 161s   is_stale false   `active_weight_sum`
breadth_intraday     score 0   staleness 130s   is_stale false   `active_weight_sum`
copper_gold_ratio    score 0   staleness 154s   is_stale false   `active_weight_sum`
dxy_trend            score 0   staleness 153s   is_stale false   `active_weight_sum`
```

**No other factor in the roster reads 0.** The remaining fourteen all carry non-zero values,
several to fifteen decimal places. **A factor that computes something does not land on
exactly 0.000; four doing so at once is a signature, not a market state.**

**`dxy_trend` is independently confirmed dead:** the Moby Dick census measured
`factor_history` at **0 rows** for it, with `factor_history`'s last write of any factor on
**2026-07-23**. It has read a fresh, active `0` for **47 days**.

## Why P1

**It is a decision surface.** The composite feeds every committee member's directional
context. A dead factor does not abstain — **it dilutes**, pulling the composite toward
neutral in proportion to its weight, and nothing downstream can tell that vote from a
measured one.

**And neutral is the most expensive place to be wrong.** A wrong directional read is
argued with; a spurious NEUTRAL suppresses the argument.

## The distinction the code does not make

```
absent   ->  exclude from the mean; the denominator shrinks; coverage falls
neutral  ->  include at 0.0; the denominator holds; coverage unchanged
```

**These are different facts and the system has one representation for both.** Kin to
`DEF-MP-DEAD-RENDERS-AS-QUIET`, where a dead feed rendered as a quiet market, and to the `compute-then-discard`
family generally: **the failure is never the absence, it is the absence wearing a value.**

## MECHANISM — FOUND IN CODE, AND IT IS NAMED (added 2026-09-08, R-IV.326(b))

`neutral_reading()` (`backend/bias_engine/factor_utils.py:497`) is the helper, and it does **two** things, of which
only the first is obvious:

```
def neutral_reading(factor_id, detail, source="system", raw_data=None) -> FactorReading:
    return FactorReading(
        factor_id = factor_id,
        score     = 0.0,                    # <- a REAL score
        signal    = score_to_signal(0.0),
        detail    = detail,
        timestamp = datetime.utcnow(),      # <- a FRESH timestamp, stamped NOW
        source    = source,
    )
```

**`score = 0.0` is the defect this file registers. `timestamp = datetime.utcnow()` is why
it is invisible.** The helper stamps the *current moment* onto a reading that measured
nothing, so **the staleness check sees a brand-new value and reports `is_stale: false`** — which is
exactly what the census observed on all four dead factors, at 130–161 seconds old.

**That is the fake-healthy-vintage family, not a new one.** Same shape as the balance
`updated_at` facet on `DEF-BALANCE-COLUMN-SEMANTICS`: **a value that never measured anything wearing a current
timestamp.** There, a cash-only write refreshed a row's age; here, a failure path stamps a
reading's age.

### The fix is broader than deleting one helper

`neutral_reading()` is called from **`dxy_trend.py` (2 sites), `gex.py` (2), `vix_term_structure.py` (1)** — and
`mcclellan_oscillator.py` imports it. **But three of the four dead factors do NOT call it:**
`copper_gold_ratio.py`, `spy_trend_intraday.py` and `breadth_intraday.py` read a fresh `0.0` by some other route.

**So there is more than one path to a fresh zero**, and a fix that removes the helper would
close one of them and leave the rest — which is how a defect survives being fixed. **The
remaining routes are unread; that is the next question, not this one.**

**And two callers are currently HEALTHY:** `gex.py` reads `-0.2` and `vix_term_structure.py` reads `0.6`
in the same payload. **The helper is not always wrong** — it is wrong when it fires, and
nothing on the reading says whether it fired. That is why the fix is exclusion rather than
a different constant: **any constant is indistinguishable from a measurement.**

## Fix shape — not chosen here

**A factor with no reading must be EXCLUDED, not scored 0.0**, and its exclusion must reach
`coverage_ratio` so the loss is visible. That is the same fix as
`DEF-BIAS-COVERAGE-OMITS-ABSENT` and the two should ship together — excluding a factor that
coverage cannot report is a half fix.

## Not determined here

**Why each of the four is dead.** Source paths were not traced; that needs the per-factor
map the census could not build from the live payload. **Four are identified; none is
diagnosed.**

---

## READING THIS DEFECT: THE CADENCE, AND THE TRAP (R-IV.352(a))

**One cadence, not two.** `refresh_composite_bias()` calls `score_all_factors()`
(`bias_scheduler.py:2444`) then `compute_composite()` (`:2457`) **sequentially in the same
coroutine**, on a **15-minute** interval registered at `:2746`, with **no market-hours gate**.
**96 cycles per 24 h, around the clock.** The gex reading interval and the composite cycle
interval are the same number and cannot drift apart.

**The apparent second schedule is DEAD CODE.** `_fallback_scheduler()` (`:3110`) carries its
own 15-minute composite branch at `:3163`, but it is launched **only** from
`except ImportError:` at `:2894-2897`. **`apscheduler>=3.10.0` is at `requirements.txt:45`,
so that branch never runs.** The two are mutually exclusive, not additive — **there is no
doubling, and anyone reconciling row counts against 192/day is reconciling against a number
that does not exist.**

### THE TRAP — rows are not cycles

**`compute_composite()` calls `log_composite()` ITSELF** (`composite.py:989`), so **every
caller writes a `bias_composite_history` row** — eight call sites in `api/bias.py`, one in
`api/uw_integration.py`, one in the scheduler. **Row arrival = 96/day PLUS one per API hit,
at arbitrary times.**

**And an HTTP-triggered composite re-reads the SAME Redis state.** The `gex` key stays as the
last scoring pass left it, so **one event is observed by every row until the next pass** —
**COUNTING ROWS OVER-COUNTS EVENTS by a factor set by API traffic**, which is not a constant
and is not recorded.

**Count cycles, not rows.** The clean counter is `factor_readings`: **one write per scoring
pass, no HTTP path.**

## THE CONSUMER-SIDE INSTANCE (R-IV.352(d))

**484 of 867 composite cycles carry `gex` 0.0 with no flat-vs-unavailable distinction.**
**55.8%**, and **13.8× the 35 readings** the producer-side instance counts.

**This is the same defect one layer down the pipe:** at the reading, `0.0` with `raw_data {}`
is a fabrication; **by the time it reaches the composite, the `raw_data` is gone and `0.0` is
just `0.0`.** The consumer cannot tell a measured-flat gex from an unavailable one **because
the distinguishing field does not survive the hop.**

### What 484 does NOT establish, and the check that would settle it

**DO NOT read 484 as 449 genuinely-flat readings plus 35 fabrications.** Two readings fit, and
this file does not choose between them:

1. **Genuine flat band.** `gex` really scores 0.0 about half the time and the fabrications are
   a small slice — in which case **the fix removes ~5% and the 0.0s largely REMAIN, correctly.**
2. **Persistence amplification.** The trap above: each reading is observed by more than one
   composite row, so a smaller set of underlying 0.0 readings is counted many times.

**SCOPE NOT ESTABLISHED, and it governs the arithmetic:** 484/867 and 35/695 were measured by
different lanes and **a common window has NOT been shown.** `867 / 695 = 1.25` is consistent
with the HTTP surplus over the same span — **consistent with, not evidence of.** Until the
windows are stated, the ratio 13.8 is **not interpretable** as a rate relationship.

**The settling read:** join each 0.0 composite cycle to the `factor_readings` row it was
computed from and ask whether that row's `raw_data` is `{}` or populated. **`{}` is a
fabrication; populated is a band.** That is conventions #14's discriminator applied at the
consumer, and it needs no new instrumentation.

### THE PREDICTION THIS MAKES, stated before the read

**After the fix, `gex` 0.0 does NOT disappear from composite rows.** Only the ~5% that were
fabrications become `null`. **A reader expecting the 0.0s to vanish will call a working fix
broken** — which is why the expectation is written down here rather than discovered against
the data.

## RULED — THE DELETE MUST NOT BE LOAD-BEARING (R-IV.352(c))

**A failed delete must not leave a fabricated-active state.**

**On delete failure the scorer writes an EXPLICIT EXCLUDED MARKER that the composite honours
— a TOMBSTONE, not an absence.** So **exclusion never depends on a delete succeeding.**

**Why a tombstone and not a retry:** a retry still has a failure mode that ends in silence,
and **the current design fails OPEN** — `factor_scorer.py:96-99` logs a warning and continues,
leaving the prior key live and `gex` counted **active** for up to its 4-hour staleness window.
**A tombstone fails CLOSED:** the composite sees an explicit "excluded" state and excludes,
whatever happened to the delete.

**Note which bound applies.** The Redis TTL is
`max(REDIS_FACTOR_LATEST_TTL 86400, 4 × 3600) = 86400 s`, but **TTL does not gate `active` —
the 4-hour staleness window does** (`composite.py:769-775`). The key outlives its usefulness by
20 h; **the damage window is 4 h.**

**Consequence for reading the current deploy:** **a `gex` still in `active_factors` does NOT
falsify the shipped fix** without first checking whether
`"Failed to clear stale key for %s"` fired in the same interval. **That is the line to grep.**

### Scheduling

**RIDES WITH THE REGIME FIX IN THE AGORA BRIEF. NOT FRIDAY.**

**The Agora brief is not yet drafted** — the panel-by-panel census (R-IV.338(a)) that feeds it
is still owed — **so the ruled design is recorded HERE so it is not lost to a file that does
not exist yet**, and moves to the brief when the brief is written.
